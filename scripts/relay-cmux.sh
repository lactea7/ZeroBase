#!/usr/bin/env bash
# relay-cmux.sh — cmux 패널을 통한 '보이는' 릴레이
#
#   Claude(좌상단) → codex 패널(좌하단) → ollama 패널(우하단) → Claude
#
# relay.sh 와 달리 헤드리스로 돌리지 않고, 사용자가 켜 둔 실제 세션에
# 텍스트를 밀어넣고 화면을 읽어온다. 그래서 진행 상황이 눈에 보인다.
#
#   ./scripts/relay-cmux.sh "이번 턴에 무엇을 바꿨는지 브리핑"
#
# 결과: .relay/round-N/{brief.md,codex.md,summary.md}
# 종료코드: 0 = P0 없음(DONE) / 10 = P0 있음(CONTINUE) / 20 = 라운드 상한
set -euo pipefail

CMUX=${CMUX_BIN:-/Applications/cmux.app/Contents/Resources/bin/cmux}
ROOT=$(git rev-parse --show-toplevel)
RELAY_DIR="$ROOT/.relay"
MAX_ROUNDS=${RELAY_MAX_ROUNDS:-3}
POLL_TIMEOUT=${RELAY_POLL_TIMEOUT:-600}   # 한 단계 최대 대기(초)

# 마커는 실행마다 고유해야 한다. 고정 문자열이면 이전 라운드가 화면에 남긴
# 마커를 그대로 집어서, 상대가 아직 답을 쓰는 중인데 끝난 줄 알고 잘라낸다.
NONCE=$(date +%H%M%S)-$$
CODEX_BEGIN="<<<CDX_BEGIN_$NONCE>>>"
CODEX_DONE="<<<CDX_DONE_$NONCE>>>"
OLLAMA_BEGIN="<<<OLM_BEGIN_$NONCE>>>"
OLLAMA_DONE="<<<OLM_DONE_$NONCE>>>"

# --- 패널 자동 탐지 -----------------------------------------------------------
# 화면 내용으로 codex/ollama 패널을 식별한다. 세션마다 surface 번호가 바뀌므로
# 매번 새로 찾고, 환경변수로 강제 지정도 가능하게 둔다.
detect_surfaces() {
  local surfaces screen self
  # 나 자신(Claude 가 돌고 있는 패널)은 반드시 제외한다. 이 패널에는 codex/ollama
  # 이야기가 그대로 적혀 있어서 내용 기반 탐지에 걸려든다.
  self=$("$CMUX" identify 2>/dev/null | grep -A1 '"caller"' -A8 \
         | grep '"surface_ref"' | head -1 | sed 's/.*: *"\(.*\)".*/\1/')
  surfaces=$("$CMUX" tree 2>/dev/null | grep -o 'surface:[0-9]*' | sort -u)
  for s in $surfaces; do
    [ "$s" = "$self" ] && continue
    screen=$("$CMUX" read-screen --surface "$s" --lines 60 2>/dev/null || true)
    [ -z "$screen" ] && continue
    # codex TUI 는 하단에 'Implement {feature}' 힌트와 'gpt-...' 모델명을 띄운다.
    if [ -z "${CODEX_SURFACE:-}" ] && grep -qE 'Implement \{feature\}|gpt-[0-9]' <<<"$screen"; then
      CODEX_SURFACE=$s; continue
    fi
    # ollama REPL 은 하단에 모델 태그(gemma4:e4b 등)를 띄운다.
    if [ -z "${OLLAMA_SURFACE:-}" ] && grep -qE '^ *(gemma|qwen|llama|mistral|phi)[0-9a-z._]*:' <<<"$screen"; then
      OLLAMA_SURFACE=$s; continue
    fi
  done
}

CODEX_SURFACE=${RELAY_CODEX_SURFACE:-}
OLLAMA_SURFACE=${RELAY_OLLAMA_SURFACE:-}
[ -z "$CODEX_SURFACE" ] || [ -z "$OLLAMA_SURFACE" ] && detect_surfaces

if [ -z "${CODEX_SURFACE:-}" ] || [ -z "${OLLAMA_SURFACE:-}" ]; then
  echo "ERROR: 패널을 찾지 못했습니다. codex/ollama 세션이 떠 있는지 확인하거나" >&2
  echo "       RELAY_CODEX_SURFACE / RELAY_OLLAMA_SURFACE 로 직접 지정하세요." >&2
  "$CMUX" tree >&2
  exit 1
fi
echo "▸ codex=$CODEX_SURFACE  ollama=$OLLAMA_SURFACE" >&2

# --- TUI 줄바꿈 되돌리기 -------------------------------------------------------
# 패널 폭에 맞춰 접힌 줄은 다음 줄이 공백으로 들여쓰여 온다. 그대로 두면 지적
# 하나가 여러 줄로 쪼개져 분류기가 헷갈린다. 들여쓴 줄은 앞줄에 이어 붙인다.
# 들여쓰기로는 '접힌 줄'과 '다음 지적'을 구분할 수 없다(둘 다 들여쓰여 온다).
# 그래서 `path.ext:숫자` 로 시작하는 줄을 새 지적의 시작으로 본다.
unwrap_lines() {
  awk '
    { line = $0; sub(/^[[:space:]]*[•*-][[:space:]]*/, "", line); sub(/^[[:space:]]+/, "", line) }
    line == "" { next }
    line ~ /^\[?P[0-2]?\]?[[:space:]]*[^[:space:]]+\.[A-Za-z]+:[0-9]+/ ||
    line ~ /^[^[:space:]]+\.[A-Za-z]+:[0-9]+/ {
      if (cur != "") print cur
      cur = line; next
    }
    { cur = (cur == "" ? line : cur " " line) }
    END { if (cur != "") print cur }
  '
}

# --- 패널에 보내고 마커가 나올 때까지 기다리기 --------------------------------
send_and_wait() {
  local surface=$1 begin=$2 marker=$3 text=$4
  local before after waited=0

  # 보내기 직전 화면을 기록해 두고, 이후 새로 생긴 부분만 잘라낸다.
  # macOS 의 wc 는 공백으로 패딩된 숫자를 내놓는다. 그대로 tail -n +N 에 넣으면
  # 'illegal offset' 으로 매번 실패해 마커를 영영 못 본다.
  before=$("$CMUX" read-screen --surface "$surface" --scrollback 2>/dev/null | wc -l | tr -d '[:space:]')
  before=$((before + 1))

  "$CMUX" send --surface "$surface" "$text" >/dev/null
  sleep 1
  "$CMUX" send-key --surface "$surface" Enter >/dev/null

  local extracted
  while [ "$waited" -lt "$POLL_TIMEOUT" ]; do
    sleep 3
    waited=$((waited + 3))

    after=$("$CMUX" read-screen --surface "$surface" --scrollback 2>/dev/null | tail -n +"$before")

    # 사용 한도에 걸리면 즉시 멈춘다. 계속 폴링하거나 재시도하면 과금으로 이어진다.
    if grep -qiE 'usage limit|rate limit|quota exceeded|out of credits|insufficient credit|한도|사용량 초과|limit reached|try again (later|in [0-9])|429' <<<"$after"; then
      echo "" >&2
      echo "🛑 STOP: $surface 에서 사용 한도/레이트 리밋 신호를 감지했습니다. 즉시 중단합니다." >&2
      grep -iE 'usage limit|rate limit|quota exceeded|out of credits|insufficient credit|한도|사용량 초과|limit reached|try again (later|in [0-9])|429' <<<"$after" | head -3 >&2
      return 99
    fi
    # BEGIN~DONE 사이만 잘라낸다. 이렇게 하지 않으면 TUI 의 도구 실행 로그
    # (`• Ran git diff ...`)와 박스 그림까지 결과로 섞여 들어간다.
    extracted=$(printf '%s\n' "$after" \
      | awk -v b="$begin" -v d="$marker" '
          index($0,b) { buf=""; on=1; next }
          index($0,d) { if (on) { out=buf; on=0 } next }
          on { buf = buf $0 "\n" }
          END { printf "%s", out }
        ' \
      | unwrap_lines)

    # 화면에 되비친 프롬프트에도 마커가 들어 있고, TUI 줄바꿈 탓에 두 마커가
    # 서로 다른 줄로 갈라지면 그 사이(빈칸)를 응답으로 착각한다. 그래서
    # '마커를 봤다'가 아니라 '마커 사이에 내용이 있다'를 완료 조건으로 삼는다.
    if [ -n "$extracted" ]; then
      printf '%s\n' "$extracted"
      return 0
    fi
  done
  echo "TIMEOUT: $surface 에서 ${POLL_TIMEOUT}초 안에 마커를 못 받았습니다." >&2
  return 1
}

# 한도 감지(99)는 재시도 없이 그대로 종료시킨다. set -e 가 파이프라인 안에서는
# 종료코드를 삼키므로 각 단계 뒤에서 명시적으로 확인한다.
abort_if_limited() {
  local rc=$1
  if [ "$rc" -eq 99 ]; then
    "$CMUX" clear-status relay >/dev/null 2>&1 || true
    echo "릴레이를 중단했습니다. 한도가 회복된 뒤 다시 실행하세요." >&2
    exit 99
  fi
}

# --- 라운드 결정 ---------------------------------------------------------------
mkdir -p "$RELAY_DIR"
last=0
for d in "$RELAY_DIR"/round-*; do
  [ -d "$d" ] || continue
  n=${d##*/round-}
  [ "$n" -gt "$last" ] 2>/dev/null && last=$n
done
ROUND=${RELAY_ROUND:-$((last + 1))}

if [ "$ROUND" -gt "$MAX_ROUNDS" ]; then
  echo "STOP: 라운드 상한($MAX_ROUNDS) 도달." >&2
  exit 20
fi
OUT="$RELAY_DIR/round-$ROUND"
mkdir -p "$OUT"

# --- 브리핑 --------------------------------------------------------------------
if [ $# -gt 0 ]; then
  printf '%s\n' "$*" > "$OUT/brief.md"
elif [ ! -t 0 ]; then
  cat > "$OUT/brief.md"
else
  echo "(브리핑 없음 — 커밋되지 않은 변경 전체를 검토합니다)" > "$OUT/brief.md"
fi

# --- 1) codex 패널로 검토 요청 -------------------------------------------------
echo "▸ round $ROUND/$MAX_ROUNDS — codex 패널로 전달 (좌하단을 보세요)" >&2
"$CMUX" set-status relay "round $ROUND: codex 검토중" >/dev/null 2>&1 || true

# TUI 는 줄바꿈을 곧 '전송'으로 처리하므로 보내는 텍스트는 반드시 한 줄이어야 한다.
# 긴 지시는 파일에 적고 경로만 넘긴다.
REL_OUT=${OUT#"$ROOT"/}
cat > "$OUT/task.md" <<EOF
# 검토 요청 (round $ROUND)

커밋되지 않은 변경을 검토하라. \`git diff\` 와 \`git diff --cached\` 로 확인하고
필요하면 해당 파일을 읽어 맥락을 파악하라. **코드는 절대 수정하지 마라.**

## 브리핑
$(cat "$OUT/brief.md")

## 규칙
- 보강이 필요한 지점만 지적한다. 잘 된 점은 쓰지 않는다.
- 각 지적은 \`file:line — 문제 — 왜 문제인지\` 형식으로 한 줄씩.
- 실제 코드 근거만 쓴다. 추측은 쓰지 마라.
- 지적할 게 없으면 NO_FINDINGS 라고만 쓴다.

## 출력 형식 (반드시 지킬 것)
지적 목록은 아래 두 마커 **사이에만** 출력하라. 마커 밖의 설명은 무시된다.

$CODEX_BEGIN
(여기에 지적을 한 줄씩)
$CODEX_DONE
EOF

send_and_wait "$CODEX_SURFACE" "$CODEX_BEGIN" "$CODEX_DONE" \
  "[RELAY round $ROUND] $REL_OUT/task.md 파일을 읽고 그 지시대로 수행하라. 지적 목록은 반드시 $CODEX_BEGIN 줄과 $CODEX_DONE 줄 사이에만 출력하라." \
  > "$OUT/codex.md" || abort_if_limited $?

if [ ! -s "$OUT/codex.md" ]; then
  echo "ERROR: codex 응답이 비어있습니다." >&2
  exit 1
fi

# --- 2) ollama 패널로 분류 요청 ------------------------------------------------
echo "▸ ollama 패널로 전달 (우하단을 보세요)" >&2
"$CMUX" set-status relay "round $ROUND: ollama 분류중" >/dev/null 2>&1 || true

# ollama REPL 은 파일을 못 읽으므로 본문을 인라인으로 넣되, 역시 한 줄로 눌러 보낸다.
# 지적 사이 구분자는 ||| 로 두고 그 단위로 나누라고 지시한다.
FINDINGS=$(sed '/^[[:space:]]*$/d' "$OUT/codex.md" | grep -vF "$CODEX_DONE" | paste -sd '|' - | sed 's/|/ ||| /g')

send_and_wait "$OLLAMA_SURFACE" "$OLLAMA_BEGIN" "$OLLAMA_DONE" \
  "너는 분류기다. 요약하지 마라. 새 지적을 만들지 마라. 아래는 ||| 로 구분된 코드리뷰 지적들이다. 각 지적을 원문 그대로 두고 앞에 태그만 붙여 한 줄에 하나씩 출력하라. [P0]=동작이 깨지거나 잘못된 결과를 냄 [P1]=취약하거나 유지보수를 해침 [P2]=스타일. 형식은 '[P0] file:line — 원문 그대로'. file:line 형태가 없는 항목은 코드 지적이 아니므로 통째로 버려라. 결과는 반드시 $OLLAMA_BEGIN 줄과 $OLLAMA_DONE 줄 사이에만 출력하고 다른 말은 쓰지 마라. 지적들: $FINDINGS" \
  > "$OUT/summary.md" || abort_if_limited $?

# --- 3) 종료 조건 --------------------------------------------------------------
"$CMUX" clear-status relay >/dev/null 2>&1 || true

# 빈 결과를 'P0 없음'으로 오해하면 안 된다 — 그건 통과가 아니라 실패다.
if [ ! -s "$OUT/summary.md" ]; then
  echo "ERROR: ollama 분류 결과가 비어있습니다. 우하단 패널을 확인하세요." >&2
  echo "       (codex 원문은 $OUT/codex.md 에 남아 있습니다)" >&2
  exit 1
fi

echo "" >&2
echo "=== round $ROUND 결과: $OUT/summary.md ===" >&2
cat "$OUT/summary.md"

if grep -q '\[P0\]' "$OUT/summary.md"; then
  echo "" >&2
  echo "CONTINUE: P0 있음 — 반영 후 다시 실행하세요." >&2
  exit 10
fi
echo "" >&2
echo "DONE: P0 없음 — 릴레이 종료." >&2
exit 0
