#!/usr/bin/env bash
# review-loop.sh — 코드 수정 검토 루프
#
#   Claude 1차 작성 → codex 검토 → (이견 반영 → codex 재검토)
#   → 3회차에도 합의가 안 되면 codex 왕복을 멈추고 gemma 가 상황을 정리해 돌려준다.
#
#   ./scripts/review-loop.sh <질문파일.md> [주제이름]
#
# 라운드는 .relay/loop-<주제>/round-N/ 에 쌓인다.
# 종료코드: 0 = codex 검토 수신(계속 진행) / 3 = gemma 중재본 수신(판단 필요)
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

require_surfaces
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
echo "▸ round $ROUND — 합의 미도달. codex 왕복을 멈추고 gemma 중재로 전환 (우하단)" >&2

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
  for r in $(seq 1 "$ROUND"); do
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

QTEXT=$(sed '/^[[:space:]]*$/d' "$HISTORY" | paste -sd '|' - | sed 's/|/ ▮ /g')

UNWRAP_FN=unwrap_prose send_and_wait "$OLLAMA_SURFACE" "$OLLAMA_BEGIN" "$OLLAMA_DONE" \
  "아래 ▮ 로 줄이 구분된 글은 한 코드 수정을 놓고 두 검토자(Claude, codex)가 시간순으로 주고받은 기록이다. [round N] 표시로 순서가 적혀 있다. **뒤 라운드가 앞 라운드를 덮어쓴다** — 앞 라운드에서 codex 가 지적한 것을 뒤 라운드에서 Claude 가 '반영했다'고 적었으면 그것은 해결된 항목이므로 미해결 쟁점에 넣지 마라. 새로운 주장을 만들지 말고 원문에 있는 내용만 쓰라. 형식: (1) 이미 해결된 것 — 어느 라운드에서 지적되고 어느 라운드에서 반영됐는지 (2) 아직 갈리거나 미해결로 남은 것 — 각 항목마다 Claude 입장과 codex 지적을 한 줄씩 대조 (3) 판정하려면 무엇을 확인해야 하는지. 원문에 없는 수치를 지어내면 안 된다. 답은 반드시 $OLLAMA_BEGIN 줄과 $OLLAMA_DONE 줄 사이에만 쓰라. 글: $QTEXT" \
  > "$OUT/arbitration.md" || abort_if_limited $?

[ -s "$OUT/arbitration.md" ] || { echo "ERROR: gemma 정리본이 비어있습니다." >&2; exit 1; }

echo "" >&2
echo "=== round $ROUND gemma 중재본 ($OUT/arbitration.md) ===" >&2
cat "$OUT/arbitration.md"
echo "" >&2
echo "codex 왕복을 종료했다. 위 정리를 근거로 Claude 가 판단할 차례다." >&2
exit 3
