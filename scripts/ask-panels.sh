#!/usr/bin/env bash
# ask-panels.sh — codex 패널과 ollama 패널에 같은 질문을 던지고 두 답을 모은다.
#
#   ./scripts/ask-panels.sh [--codex-only|--ollama-only] <질문파일.md> [출력디렉터리]
#
# relay-cmux.sh 가 '커밋 안 된 코드 변경 검토' 전용인 것과 달리, 이쪽은
# 임의의 질문(분석이 맞는지, 판단이 타당한지 등)을 두 모델에게 교차 검증시킨다.
# codex 는 파일을 직접 읽으므로 저장소 근거를 확인할 수 있고,
# ollama 는 파일을 못 읽으므로 질문 본문을 한 줄로 눌러 인라인으로 넘긴다.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=/dev/null
source "$HERE/relay-lib.sh"

ROOT=$(git rev-parse --show-toplevel)

# 대상 선택. 사실 검증에는 codex 만 쓰는 편이 낫다 — 로컬 소형 모델은 파일을
# 읽지 못해 '판단보류'만 늘고, 실측에서 유일하게 동의한 항목이 오히려 틀렸다.
#
# --chain 은 다르다: 두 모델에게 같은 질문을 따로 던지는 대신, codex 의 답변을
# ollama 에게 넘겨 정리시킨다 (codex → ollama 연쇄).
#
# --reuse-codex <파일>: 이미 받아둔 codex 답변을 재사용한다. ollama 단계만 실패했을 때
# codex 를 다시 호출하면 사용 한도를 헛되이 태운다.
ASK_CODEX=1; ASK_OLLAMA=1; CHAIN=0; REUSE_CODEX=""
while : ; do
  case "${1:-}" in
    --codex-only)  ASK_OLLAMA=0; shift ;;
    --ollama-only) ASK_CODEX=0;  shift ;;
    --chain)       CHAIN=1;      shift ;;
    --reuse-codex) REUSE_CODEX=${2:?"--reuse-codex 에 파일 경로가 필요합니다"}; ASK_CODEX=0; CHAIN=1; shift 2 ;;
    *) break ;;
  esac
done

QFILE=${1:?"질문 파일 경로가 필요합니다"}
[ -f "$QFILE" ] || { echo "ERROR: $QFILE 없음" >&2; exit 1; }
OUT=${2:-"$ROOT/.relay/ask-$(date +%H%M%S)"}
mkdir -p "$OUT"
cp "$QFILE" "$OUT/question.md"

if [ -n "$REUSE_CODEX" ]; then
  [ -f "$REUSE_CODEX" ] || { echo "ERROR: $REUSE_CODEX 없음" >&2; exit 1; }
  cp "$REUSE_CODEX" "$OUT/codex.md"
  echo "▸ codex 답변 재사용: $REUSE_CODEX" >&2
fi

require_surfaces

REL_Q=${QFILE#"$ROOT"/}

# --- codex: 파일을 읽고 저장소 근거로 검증 ------------------------------------
if [ "$ASK_CODEX" = 1 ]; then
  echo "▸ codex 패널에 질문 전달 (좌하단)" >&2
  UNWRAP_FN=unwrap_prose send_and_wait "$CODEX_SURFACE" "$CODEX_BEGIN" "$CODEX_DONE" \
    "[ASK] $REL_Q 파일을 읽고 그 안의 질문에 답하라. 저장소의 실제 코드와 파일을 근거로 확인하고, 틀린 주장이 있으면 어디가 왜 틀렸는지 지적하라. 답은 반드시 $CODEX_BEGIN 줄과 $CODEX_DONE 줄 사이에만 쓰라." \
    > "$OUT/codex.md" || abort_if_limited $?

  if [ ! -s "$OUT/codex.md" ]; then
    echo "ERROR: codex 응답이 비어있습니다." >&2
    exit 1
  fi
fi

# --- ollama: 파일을 못 읽으므로 본문을 한 줄로 눌러 전달 ----------------------
if [ "$ASK_OLLAMA" = 1 ] || [ "$CHAIN" = 1 ]; then
  # TUI 는 줄바꿈이 곧 전송이라 개행을 모두 제거해야 한다.
  if [ "$CHAIN" = 1 ]; then
    # 연쇄 모드: 질문이 아니라 codex 의 답변을 넘겨 정리시킨다.
    SRC="$OUT/codex.md"
    PROMPT_HEAD="아래 ▮ 로 줄이 구분된 글은 코드/시뮬레이션 분석가(codex)가 낸 검토 의견이다. 이 의견을 항목별로 정리하라. 새로운 주장을 만들어내지 말고 원문에 있는 내용만 쓴다. 각 항목은 '결론 → 근거' 순서로 한 줄씩, 심각한 것부터 배열하라. 원문에 없는 수치를 지어내면 안 된다."
  else
    SRC="$OUT/question.md"
    PROMPT_HEAD="아래 ▮ 로 줄이 구분된 글은 어떤 분석 결과다. 이 분석이 타당한지 판단하라. 동의하는 점과 동의하지 않는 점을 각각 짧게 쓰고, 근거가 부족해 판단할 수 없는 항목은 '판단보류'라고 명시하라. 추측으로 사실을 만들어내지 마라."
  fi
  QTEXT=$(sed '/^[[:space:]]*$/d' "$SRC" | paste -sd '|' - | sed 's/|/ ▮ /g')

  echo "▸ ollama 패널에 전달 (우하단)$([ "$CHAIN" = 1 ] && echo ' — codex 답변 정리')" >&2
  UNWRAP_FN=unwrap_prose send_and_wait "$OLLAMA_SURFACE" "$OLLAMA_BEGIN" "$OLLAMA_DONE" \
    "$PROMPT_HEAD 답은 반드시 $OLLAMA_BEGIN 줄과 $OLLAMA_DONE 줄 사이에만 쓰라. 글: $QTEXT" \
    > "$OUT/ollama.md" || abort_if_limited $?

  if [ ! -s "$OUT/ollama.md" ]; then
    echo "ERROR: ollama 응답이 비어있습니다." >&2
    exit 1
  fi
fi

echo "" >&2
if [ "$ASK_CODEX" = 1 ]; then
  echo "=== codex ($OUT/codex.md) ===" >&2
  cat "$OUT/codex.md"
fi
if [ "$ASK_OLLAMA" = 1 ] || [ "$CHAIN" = 1 ]; then
  echo "" >&2
  echo "=== ollama ($OUT/ollama.md)$([ "$CHAIN" = 1 ] && echo ' — codex 답변 정리본') ===" >&2
  cat "$OUT/ollama.md"
fi
