#!/usr/bin/env bash
# relay.sh — Claude → codex(검토) → ollama(분류) → Claude 릴레이 파이프라인
#
#   ./scripts/relay.sh "이번 턴에 무엇을 바꿨는지 브리핑"
#   echo "브리핑" | ./scripts/relay.sh
#
# 결과: .relay/round-N/{brief.md,codex.md,summary.md}
# 종료코드: 0 = P0 없음(DONE) / 10 = P0 있음(CONTINUE) / 20 = 라운드 상한 도달
set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
RELAY_DIR="$ROOT/.relay"
MAX_ROUNDS=${RELAY_MAX_ROUNDS:-3}
OLLAMA_MODEL=${RELAY_OLLAMA_MODEL:-qwen3.5}

# --- 라운드 결정 (기존 round-N 중 최대값 + 1) ---------------------------------
mkdir -p "$RELAY_DIR"
last=0
for d in "$RELAY_DIR"/round-*; do
  [ -d "$d" ] || continue
  n=${d##*/round-}
  [ "$n" -gt "$last" ] 2>/dev/null && last=$n
done
ROUND=${RELAY_ROUND:-$((last + 1))}

if [ "$ROUND" -gt "$MAX_ROUNDS" ]; then
  echo "STOP: 라운드 상한($MAX_ROUNDS) 도달. 더 돌리려면 .relay/ 를 비우거나 RELAY_MAX_ROUNDS 를 올리세요." >&2
  exit 20
fi

OUT="$RELAY_DIR/round-$ROUND"
mkdir -p "$OUT"

# --- 1) 브리핑 수집 ------------------------------------------------------------
if [ $# -gt 0 ]; then
  printf '%s\n' "$*" > "$OUT/brief.md"
elif [ ! -t 0 ]; then
  cat > "$OUT/brief.md"
else
  echo "(브리핑 없음 — 커밋되지 않은 변경 전체를 검토합니다)" > "$OUT/brief.md"
fi

if git diff --quiet && git diff --cached --quiet; then
  echo "SKIP: 커밋되지 않은 변경이 없습니다." >&2
  exit 0
fi

echo "▸ round $ROUND/$MAX_ROUNDS — codex 검토 중..." >&2

# --- 2) codex 검토 -------------------------------------------------------------
# read-only 샌드박스: codex 는 읽기만 하고 코드를 고치지 않는다.
# `codex exec review --uncommitted` 는 커스텀 프롬프트와 함께 못 쓰므로
# (--uncommitted 와 [PROMPT] 가 배타적) 일반 exec 에 diff 를 직접 읽게 시킨다.
codex exec -s read-only -o "$OUT/codex.md" "$(cat <<EOF
이 저장소의 커밋되지 않은 변경을 검토하라.
\`git diff\` 와 \`git diff --cached\` 로 변경을 확인하고, 필요하면 해당 파일을 읽어 맥락을 파악하라.

브리핑:
$(cat "$OUT/brief.md")

규칙:
- 보강이 필요한 지점만 지적한다. 잘 된 점 칭찬은 쓰지 않는다.
- 각 지적은 한 줄로 시작하고 'file:line — 문제 — 왜 문제인지' 형식을 지킨다.
- 추측이 아니라 실제 코드 근거를 인용한다. 근거가 없으면 쓰지 않는다.
- 지적할 게 없으면 정확히 'NO_FINDINGS' 한 줄만 출력한다.
EOF
)" >"$OUT/codex.log" 2>&1 || {
  echo "ERROR: codex 실패. $OUT/codex.log 확인" >&2
  exit 1
}

if [ ! -s "$OUT/codex.md" ]; then
  echo "ERROR: codex 결과가 비어있음. $OUT/codex.log 확인" >&2
  exit 1
fi

echo "▸ ollama($OLLAMA_MODEL) 분류 중..." >&2

# --- 3) ollama 분류 ------------------------------------------------------------
# 요약이 아니라 '분류'다. 원문을 그대로 두고 우선순위 태그만 붙인다.
ollama run "$OLLAMA_MODEL" --hidethinking --nowordwrap "$(cat <<EOF
너는 코드리뷰 결과 분류기다. 요약하지 마라. 새로운 지적을 만들지 마라.

아래 리뷰의 각 지적을 원문 문장 그대로 유지한 채 우선순위 태그만 앞에 붙여 다시 출력하라.
  [P0] 동작이 깨지거나 잘못된 결과를 내는 것 — 지금 고쳐야 함
  [P1] 정확하지만 취약하거나 유지보수를 해치는 것
  [P2] 스타일·취향 수준

출력 형식: 한 줄에 하나씩 '[P0] file:line — 원문 그대로'. 다른 말은 쓰지 마라.
리뷰가 'NO_FINDINGS' 이면 'NO_FINDINGS' 한 줄만 출력하라.

--- 리뷰 원문 ---
$(cat "$OUT/codex.md")
EOF
)" 2>/dev/null \
  | perl -pe 's/\e\[[0-9;?]*[a-zA-Z]//g; s/\e\][^\a]*\a//g' \
  | sed '/^[[:space:]]*$/d' > "$OUT/summary.md"

# --- 4) 종료 조건 --------------------------------------------------------------
echo "" >&2
echo "=== round $ROUND 결과: $OUT/summary.md ===" >&2
cat "$OUT/summary.md"

if grep -q '^\[P0\]' "$OUT/summary.md"; then
  echo "" >&2
  echo "CONTINUE: P0 있음 — 반영 후 다시 실행하세요." >&2
  exit 10
fi

echo "" >&2
echo "DONE: P0 없음 — 릴레이 종료." >&2
exit 0
