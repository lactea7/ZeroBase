#!/usr/bin/env bash
# review-loop.sh — 코드 수정 검토 루프
#
#   Claude 1차 작성 → codex 검토 → (이견 반영 → codex 재검토)
#   → 3회차에도 합의가 안 되면 codex 왕복을 멈추고 gemini 가 상황을 정리해 돌려준다.
#
#   ./scripts/review-loop.sh <질문파일.md> [주제이름]
#
# 라운드는 .relay/loop-<주제>/round-N/ 에 쌓인다.
# 종료코드: 0 = codex 검토 수신(계속 진행) / 3 = gemini 중재본 수신(판단 필요)
#           1 = 오류 / 99 = 사용 한도 감지
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=/dev/null
source "$HERE/relay-lib.sh"

ROOT=$(git rev-parse --show-toplevel)
QFILE=${1:?"질문 파일 경로가 필요합니다"}
[ -f "$QFILE" ] || { echo "ERROR: $QFILE 없음" >&2; exit 1; }
TOPIC=${2:-$(basename "$QFILE" .md)}
LOOP_DIR="$ROOT/.relay/loop-$TOPIC"
ARBITRATE_AT=${REVIEW_ARBITRATE_AT:-3}   # 이 회차에 gemma 중재로 전환
# 중재에 실을 최근 라운드 수. gemini 직접 호출로 바뀌어 컨텍스트 제약이 사라졌으므로
# 기본값은 '전부'다. (로컬 모델을 쓰던 시절엔 2라운드로 잘라도 13,433자에서 실패했다)
ARBITRATE_HISTORY_ROUNDS=${ARBITRATE_HISTORY_ROUNDS:-99}
ARBITRATE_MAX_CHARS=${ARBITRATE_MAX_CHARS:-200000}

mkdir -p "$LOOP_DIR"
last=0
for d in "$LOOP_DIR"/round-*; do
  [ -d "$d" ] || continue
  n=${d##*/round-}
  [ "$n" -gt "$last" ] 2>/dev/null && last=$n
done
ROUND=$((last + 1))
OUT="$LOOP_DIR/round-$ROUND"
mkdir -p "$OUT"
cp "$QFILE" "$OUT/question.md"

# 패널은 codex 검토에만 필요하다. 중재는 gemini 를 직접 호출하므로 패널이 없어도 된다.
if [ "$ROUND" -lt "$ARBITRATE_AT" ]; then
  require_surfaces
fi
REL_Q=${QFILE#"$ROOT"/}

# ── 1~2회차: codex 검토 ────────────────────────────────────────────────────────
if [ "$ROUND" -lt "$ARBITRATE_AT" ]; then
  echo "▸ round $ROUND — codex 검토 (좌하단)" >&2
  UNWRAP_FN=unwrap_prose send_and_wait "$CODEX_SURFACE" "$CODEX_BEGIN" "$CODEX_DONE" \
    "[REVIEW round $ROUND] $REL_Q 파일을 읽고 그 안의 질문에 답하라. 저장소의 실제 코드를 근거로 확인하고, 틀린 판단이 있으면 어디가 왜 틀렸는지 지적하라. 동의하는 부분은 짧게만 쓰라. 답은 반드시 $CODEX_BEGIN 줄과 $CODEX_DONE 줄 사이에만 쓰라." \
    > "$OUT/codex.md" || abort_if_limited $?

  [ -s "$OUT/codex.md" ] || { echo "ERROR: codex 응답이 비어있습니다." >&2; exit 1; }

  echo "" >&2
  echo "=== round $ROUND codex ($OUT/codex.md) ===" >&2
  cat "$OUT/codex.md"
  echo "" >&2
  echo "다음: 이견을 반영해 코드를 고치고 다시 실행하면 round $((ROUND + 1)) 이 된다." >&2
  [ "$((ROUND + 1))" -ge "$ARBITRATE_AT" ] && \
    echo "      (다음 회차는 $ARBITRATE_AT 회차 → gemma 중재로 전환된다)" >&2
  exit 0
fi

# ── 3회차: gemma 중재 ──────────────────────────────────────────────────────────
# 합의가 안 된 상태다. codex 왕복을 멈추고 지금까지의 쟁점을 정리시킨다.
echo "▸ round $ROUND — 합의 미도달. codex 왕복을 멈추고 gemini 중재로 전환" >&2

HISTORY="$OUT/history.md"
# ⚠️ 이력은 반드시 시간순으로 교차 배치해야 한다.
# 예전에는 '최신 질문 하나 + 모든 codex 의견'을 나열했는데, 그러면 정리하는 쪽이
# round 1 지적이 round 2 에서 이미 고쳐졌다는 사실을 알 수 없다.
# 실제로 gemma 가 해결된 항목 3건을 '아직 갈리는 쟁점'으로 올렸다.
# 각 라운드의 question.md 는 직전 codex 지적에 대한 Claude 의 반영 보고이므로,
# Q1 → C1 → Q2 → C2 → … 순서로 두면 무엇이 처리됐는지 드러난다.
{
  echo "# 쟁점 정리 요청 (round $ROUND)"
  echo
  echo "아래는 시간순 대화 기록이다. **뒤 라운드가 앞 라운드를 덮어쓴다** —"
  echo "Claude 가 이후 라운드에서 '반영했다'고 적은 항목은 이미 해결된 것이므로"
  echo "미해결 쟁점으로 올리면 안 된다."
  echo
  # 전체 이력을 다 넣으면 로컬 모델의 컨텍스트를 넘긴다. 실측: 4라운드 누적 31KB →
  # 한 줄 16,972자로 gemma(16384 토큰)가 600초 안에 응답하지 못했다.
  # 살아있는 쟁점은 '가장 최근 라운드'에 담겨 있으므로 최근 N라운드만 싣고,
  # 그 이전은 제목만 남긴다.
  _from=$((ROUND - ARBITRATE_HISTORY_ROUNDS + 1))
  [ "$_from" -lt 1 ] && _from=1
  if [ "$_from" -gt 1 ]; then
    echo "## [round 1~$((_from - 1))] 이전 라운드"
    echo "이 라운드들의 지적은 이후 라운드에서 반영됐다. 미해결 쟁점으로 올리지 마라."
    echo
  fi
  for r in $(seq "$_from" "$ROUND"); do
    if [ -s "$LOOP_DIR/round-$r/question.md" ]; then
      echo
      echo "## [round $r] Claude 의 입장/반영 보고"
      cat "$LOOP_DIR/round-$r/question.md"
    fi
    if [ -s "$LOOP_DIR/round-$r/codex.md" ]; then
      echo
      echo "## [round $r] codex 지적"
      cat "$LOOP_DIR/round-$r/codex.md"
    fi
  done
} > "$HISTORY"

# 그래도 크면 정리 자체가 실패하므로 미리 알린다.
_hsize=$(sed '/^[[:space:]]*$/d' "$HISTORY" | tr -d '\n' | wc -c | tr -d '[:space:]')
if [ "$_hsize" -gt "$ARBITRATE_MAX_CHARS" ]; then
  echo "⚠️ 중재 입력이 ${_hsize}자로 상한(${ARBITRATE_MAX_CHARS}자)을 넘습니다." >&2
  echo "   ARBITRATE_HISTORY_ROUNDS 를 줄이거나 질문 파일을 요약하세요." >&2
fi

# 중재는 gemma 패널이 아니라 gemini 를 직접 호출한다.
# gemma 는 문서 간 상태 대조에서 두 번 실패했다(13,433자 입력, 600초 타임아웃).
# 같은 모델이 20,662자 단일 문서 요약은 성공했으므로 크기가 아니라 과업 성격 문제다.
arbitrate_with_gemini "$HISTORY" "$OUT/arbitration.md" || abort_if_limited $?

[ -s "$OUT/arbitration.md" ] || { echo "ERROR: gemma 정리본이 비어있습니다." >&2; exit 1; }

echo "" >&2
echo "=== round $ROUND gemini 중재본 ($OUT/arbitration.md) ===" >&2
cat "$OUT/arbitration.md"
echo "" >&2
echo "codex 왕복을 종료했다. 위 정리를 근거로 Claude 가 판단할 차례다." >&2
exit 3
