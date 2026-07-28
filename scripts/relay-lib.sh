#!/usr/bin/env bash
# relay-lib.sh — cmux 패널 제어 공통 함수. 직접 실행하지 말고 source 할 것.
#
#   source "$(dirname "$0")/relay-lib.sh"
#
# 제공: detect_surfaces / send_and_wait / abort_if_limited
#       unwrap_findings (file:line 목록용) / unwrap_prose (산문용)
# 사용처: relay-cmux.sh (코드 검토 릴레이), ask-panels.sh (자유 질문)

CMUX=${CMUX_BIN:-/Applications/cmux.app/Contents/Resources/bin/cmux}
POLL_TIMEOUT=${RELAY_POLL_TIMEOUT:-600}   # 한 단계 최대 대기(초)

# 마커는 실행마다 고유해야 한다. 고정 문자열이면 이전 라운드가 화면에 남긴
# 마커를 그대로 집어서, 상대가 아직 답을 쓰는 중인데 끝난 줄 알고 잘라낸다.
NONCE=$(date +%H%M%S)-$$
CODEX_BEGIN="<<<CDX_BEGIN_$NONCE>>>"
CODEX_DONE="<<<CDX_DONE_$NONCE>>>"
OLLAMA_BEGIN="<<<OLM_BEGIN_$NONCE>>>"
OLLAMA_DONE="<<<OLM_DONE_$NONCE>>>"

LIMIT_RE='usage limit|rate limit|quota exceeded|out of credits|insufficient credit|한도|사용량 초과|limit reached|try again (later|in [0-9])|429'

# --- 패널 자동 탐지 -----------------------------------------------------------
# 화면 내용으로 codex/ollama 패널을 식별한다. 세션마다 surface 번호가 바뀌므로
# 매번 새로 찾고, 환경변수로 강제 지정도 가능하게 둔다.
detect_surfaces() {
  local surfaces screen self
  # 나 자신(Claude 가 돌고 있는 패널)은 반드시 제외한다. 이 패널에는 codex/ollama
  # 이야기가 그대로 적혀 있어서 내용 기반 탐지에 걸려든다.
  self=$("$CMUX" identify 2>/dev/null | grep -A8 '"caller"' \
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

require_surfaces() {
  CODEX_SURFACE=${RELAY_CODEX_SURFACE:-}
  OLLAMA_SURFACE=${RELAY_OLLAMA_SURFACE:-}
  # read-screen 은 앱이 막 뜬 직후 등에 일시적으로 빈 화면을 돌려준다.
  # 한 번 비었다고 탐지 전체를 포기하면 재부팅 직후마다 실패한다.
  local attempt=1
  while [ "$attempt" -le 3 ]; do
    if [ -n "${CODEX_SURFACE:-}" ] && [ -n "${OLLAMA_SURFACE:-}" ]; then break; fi
    [ "$attempt" -gt 1 ] && sleep 2
    detect_surfaces
    attempt=$((attempt + 1))
  done
  if [ -z "${CODEX_SURFACE:-}" ] || [ -z "${OLLAMA_SURFACE:-}" ]; then
    echo "ERROR: 패널을 찾지 못했습니다. codex/ollama 세션이 떠 있는지 확인하거나" >&2
    echo "       RELAY_CODEX_SURFACE / RELAY_OLLAMA_SURFACE 로 직접 지정하세요." >&2
    "$CMUX" tree >&2
    exit 1
  fi
  echo "▸ codex=$CODEX_SURFACE  ollama=$OLLAMA_SURFACE" >&2
}

# --- TUI 줄바꿈 되돌리기 -------------------------------------------------------
# 패널 폭에 맞춰 접힌 줄은 다음 줄이 공백으로 들여쓰여 온다. 그대로 두면 한 항목이
# 여러 줄로 쪼개진다.

# 지적 목록용: 들여쓰기로는 '접힌 줄'과 '다음 지적'을 구분할 수 없으므로
# `path.ext:숫자` 로 시작하는 줄을 새 항목의 시작으로 본다.
unwrap_findings() {
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

# 산문용: 빈 줄을 문단 경계로 보고, 들여쓴 줄만 앞줄에 이어 붙인다.
# 자유 질문 답변에 unwrap_findings 를 쓰면 문장이 통째로 뭉개진다.
unwrap_prose() {
  awk '
    /^[[:space:]]*$/ { if (cur != "") { print cur; cur="" } print ""; next }
    /^[[:space:]]/   { sub(/^[[:space:]]+/, " "); cur = cur $0; next }
    { if (cur != "") print cur; cur = $0 }
    END { if (cur != "") print cur }
  ' | cat -s
}

# --- 패널에 보내고 마커 사이 내용이 나올 때까지 기다리기 ----------------------
# UNWRAP_FN 으로 후처리 함수를 고른다 (기본 unwrap_findings).
send_and_wait() {
  local surface=$1 begin=$2 marker=$3 text=$4
  local unwrap=${UNWRAP_FN:-unwrap_findings}
  local before after waited=0 extracted

  # 보내기 직전 화면 길이를 기록해 이후 새로 생긴 부분만 본다.
  # macOS 의 wc 는 공백으로 패딩된 숫자를 내놓는다. 그대로 tail -n +N 에 넣으면
  # 'illegal offset' 으로 매번 실패해 마커를 영영 못 본다.
  before=$("$CMUX" read-screen --surface "$surface" --scrollback 2>/dev/null | wc -l | tr -d '[:space:]')
  before=$((before + 1))

  # cmux send 는 한 번에 보낼 수 있는 양에 한계가 있다. 실측으로 2800자는 통과하고
  # 3082자는 15초 뒤 "Command timed out" 으로 실패했다(길이보다 공백·줄바꿈 렌더링
  # 비용에 좌우된다). 나눠 보내면 입력창이 누적하므로 안전한 크기로 쪼갠다.
  local pos=0 chunk
  while [ "$pos" -lt "${#text}" ]; do
    chunk=${text:$pos:1200}
    if ! "$CMUX" send --surface "$surface" "$chunk" >/dev/null 2>&1; then
      echo "ERROR: $surface 에 전송 실패 (offset $pos)" >&2
      return 1
    fi
    pos=$((pos + 1200))
  done
  sleep 1
  "$CMUX" send-key --surface "$surface" Enter >/dev/null

  while [ "$waited" -lt "$POLL_TIMEOUT" ]; do
    sleep 3
    waited=$((waited + 3))

    after=$("$CMUX" read-screen --surface "$surface" --scrollback 2>/dev/null | tail -n +"$before")

    # 사용 한도에 걸리면 즉시 멈춘다. 계속 폴링하거나 재시도하면 과금으로 이어진다.
    if grep -qiE "$LIMIT_RE" <<<"$after"; then
      echo "" >&2
      echo "🛑 STOP: $surface 에서 사용 한도/레이트 리밋 신호를 감지했습니다. 즉시 중단합니다." >&2
      grep -iE "$LIMIT_RE" <<<"$after" | head -3 >&2
      return 99
    fi

    # BEGIN~DONE 사이만 잘라낸다. 이렇게 하지 않으면 TUI 의 도구 실행 로그와
    # 박스 그림까지 결과로 섞여 들어간다.
    extracted=$(printf '%s\n' "$after" \
      | awk -v b="$begin" -v d="$marker" '
          index($0,b) { buf=""; on=1; next }
          index($0,d) { if (on) { out=buf; on=0 } next }
          on { buf = buf $0 "\n" }
          END { printf "%s", out }
        ' \
      | "$unwrap")

    # 화면에 되비친 프롬프트에도 마커가 들어 있고, TUI 줄바꿈 탓에 두 마커가
    # 서로 다른 줄로 갈라지면 그 사이(빈칸)를 응답으로 착각한다. 그래서
    # '마커를 봤다'가 아니라 '마커 사이에 내용이 있다'를 완료 조건으로 삼는다.
    if [ -n "$(tr -d '[:space:]' <<<"$extracted")" ]; then
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
    echo "중단했습니다. 한도가 회복된 뒤 다시 실행하세요." >&2
    exit 99
  fi
}
