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

# 한도/레이트 리밋 신호. 맨 숫자 '429' 를 그대로 넣으면 안 된다 —
# 커밋 해시(ef429e3), 파일 크기, 줄 번호 등 어디에나 나타나 오탐한다.
# 실제로 커밋 해시 때문에 정상 검토가 중단됐다. HTTP 문맥이 있을 때만 인정한다.
# 여기 넣는 것은 '기다려도 안 풀리는 한도'만이어야 한다.
# 넣지 말 것:
#   - 맨 숫자 429 → 커밋 해시(ef429e3)·줄 번호·면적값에 걸린다 (실제로 겪음)
#   - 'try again later' → 503/500 같은 **일시적** 과부하도 이렇게 말한다.
#     게다가 CLI 가 자체 백오프 재시도 중인 로그를 보고 중단시켜, 성공할 호출을 죽였다.
# 503·UNAVAILABLE·high demand 는 재시도하면 풀리므로 한도로 취급하지 않는다.
LIMIT_RE='usage limit|rate limit|quota exceeded|out of credits|insufficient credit|사용 한도|사용량 초과|limit reached|too many requests|http[^0-9]{0,12}429|status[^0-9]{0,12}429|RESOURCE_EXHAUSTED'

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
  local after waited=0 extracted

  # 절대 행 오프셋은 쓰지 않는다. read-screen --scrollback 은 버퍼 상한에 걸리면
  # 오래된 줄을 버리므로, 전송 전에 센 행 번호가 그 뒤로 밀려 응답 구간을 통째로
  # 건너뛴다(긴 답변에서 실제로 발생했다). 마커에 실행별 논스가 붙어 있어
  # 이전 라운드와 충돌하지 않으므로 전체 스크롤백을 그대로 검색하면 된다.

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

    after=$("$CMUX" read-screen --surface "$surface" --scrollback 2>/dev/null)

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

# --- Gemini 중재 (패널을 거치지 않는 직접 호출) --------------------------------
# cmux 패널 방식은 마커·청크 분할·화면 파싱이 필요해 실패 지점이 많았다.
# gemini 는 -p 로 헤드리스 실행되고 stdin 을 프롬프트에 덧붙이므로 그 전부가 불필요하다.
#
# 역할 분담 근거(실측):
#   codex  — 저장소를 읽고 근거를 대는 코드 검토
#   gemma  — 단일 문서 압축·분류 (20,662자까지 성공, 로컬이라 한도를 쓰지 않음)
#   gemini — 문서 간 상태 대조(중재). gemma 는 13,433자 입력에서 두 번 실패했고,
#            더 큰 20,662자 단일 문서 요약은 성공했다 → 크기가 아니라 과업 성격 문제다.
GEMINI_BIN=${GEMINI_BIN:-gemini}
GEMINI_PROMPT='아래는 한 코드 수정을 놓고 두 검토자(Claude, codex)가 시간순으로 주고받은 기록이다.
[round N] 표시로 순서가 적혀 있다. 뒤 라운드가 앞 라운드를 덮어쓴다 — 앞 라운드에서 codex 가
지적한 것을 뒤 라운드에서 Claude 가 "반영했다"고 적었으면 그것은 해결된 항목이므로 미해결
쟁점에 넣지 마라. 원문에 없는 사실이나 수치를 지어내지 마라.

다음 형식으로만 답하라.

## 1. 이미 해결된 것
- 항목 — (round N 지적 → round M 반영)

## 2. 아직 갈리거나 미해결로 남은 것
- 항목 — Claude 입장: … / codex 지적: …

## 3. 판정하려면 확인해야 할 것
- …' 

# 패널에서 gemini 를 실행하고 **파일**로 결과를 회수한다.
# 화면을 긁지 않으므로 마커·청크 분할·줄바꿈 복원이 전혀 필요 없다 —
# 보이는 것은 사용자를 위한 것이고, 읽는 것은 파일이다.
_arbitrate_in_panel() {
  local surface=$1 history_file=$2 out_file=$3
  local rc_file="$out_file.rc" err_file="$out_file.err"
  local prompt_file="$out_file.prompt"
  rm -f "$rc_file" "$err_file" "$out_file"
  printf '%s' "$GEMINI_PROMPT" > "$prompt_file"

  # 보내는 명령은 반드시 한 줄이어야 한다(TUI 는 줄바꿈이 곧 전송).
  # 긴 프롬프트·이력은 파일 경로로만 참조해 명령을 짧게 유지한다.
  local cmd="$GEMINI_BIN -p \"\$(cat '$prompt_file')\" --skip-trust < '$history_file' > '$out_file' 2> '$err_file'; echo \$? > '$rc_file'"
  "$CMUX" send --surface "$surface" "$cmd" >/dev/null || {
    echo "ERROR: $surface 에 명령 전송 실패" >&2; return 1; }
  sleep 1
  "$CMUX" send-key --surface "$surface" Enter >/dev/null

  echo "▸ gemini 실행 중 ($surface 패널에서 진행 상황을 볼 수 있습니다)" >&2
  local waited=0
  while [ "$waited" -lt "$POLL_TIMEOUT" ]; do
    sleep 3; waited=$((waited + 3))
    [ -f "$rc_file" ] && break
  done
  [ -f "$rc_file" ] || { echo "TIMEOUT: ${POLL_TIMEOUT}초 안에 gemini 가 끝나지 않았습니다." >&2; return 1; }

  if grep -qiE "$LIMIT_RE" "$out_file" "$err_file" 2>/dev/null; then
    echo "🛑 STOP: gemini 에서 사용 한도 신호를 감지했습니다." >&2
    grep -ihE "$LIMIT_RE" "$out_file" "$err_file" 2>/dev/null | head -3 >&2
    return 99
  fi
  if [ "$(cat "$rc_file")" != "0" ]; then
    echo "ERROR: gemini 실패 (rc=$(cat "$rc_file"))" >&2
    tail -5 "$err_file" >&2
    return 1
  fi
  sed -i '' '/^Ripgrep is not available/d' "$out_file" 2>/dev/null || true
  [ -s "$out_file" ] || { echo "ERROR: gemini 응답이 비어있습니다." >&2; return 1; }
  return 0
}

# Gemini 전용 패널을 확보한다.
#
# ⚠️ 예전엔 "codex 도 ollama 도 아니면 빈 셸"이라는 내용 기반 추측으로 패널을 골랐다.
# 그 결과 **다른 Claude Code 세션을 빈 셸로 오인해 셸 명령을 채팅 메시지로 보냈다.**
# 남의 패널을 추측으로 건드리면 안 된다. 전용 패널을 직접 만들어 제목으로 식별한다.
GEMINI_PANEL_TITLE=${GEMINI_PANEL_TITLE:-relay-gemini}

ensure_gemini_panel() {
  # 1) 사용자가 직접 지정했으면 그대로 쓴다
  if [ -n "${RELAY_GEMINI_SURFACE:-}" ]; then
    echo "$RELAY_GEMINI_SURFACE"; return 0
  fi
  # 2) 이전에 만든 전용 패널이 있으면 재사용한다 (제목으로만 식별 — 내용 추측 금지)
  local found
  found=$("$CMUX" tree 2>/dev/null \
          | grep -F "\"$GEMINI_PANEL_TITLE\"" \
          | grep -o 'surface:[0-9]*' | head -1)
  if [ -n "$found" ]; then
    echo "$found"; return 0
  fi
  # 3) 없으면 새로 만든다. 포커스는 뺏지 않는다.
  local created ref
  created=$("$CMUX" new-pane --type terminal --direction right --focus false 2>/dev/null) || return 1
  ref=$(grep -o 'surface:[0-9]*' <<<"$created" | head -1)
  [ -n "$ref" ] || return 1
  "$CMUX" rename-tab --surface "$ref" "$GEMINI_PANEL_TITLE" >/dev/null 2>&1 || true
  echo "$ref"
}

arbitrate_with_gemini() {
  local history_file=$1 out_file=$2
  [ -s "$history_file" ] || { echo "ERROR: 이력 파일이 비어있습니다: $history_file" >&2; return 1; }

  # 패널에서 돌릴 수 있으면 그렇게 한다 — 사용자가 진행을 볼 수 있어야 한다.
  # 결과는 화면이 아니라 파일로 읽으므로 마커·청크 분할·스크래핑이 필요 없다.
  local panel
  if [ "${GEMINI_IN_PANEL:-1}" = "1" ] && panel=$(ensure_gemini_panel); then
    _arbitrate_in_panel "$panel" "$history_file" "$out_file"
    return $?
  fi

  # --skip-trust: 헤드리스 실행 시 신뢰 디렉터리 확인을 건너뛴다.
  if ! "$GEMINI_BIN" -p "$GEMINI_PROMPT" --skip-trust < "$history_file" > "$out_file" 2>"$out_file.err"; then
    echo "ERROR: gemini 호출 실패" >&2
    tail -5 "$out_file.err" >&2
    return 1
  fi

  # 한도 신호는 응답·에러 양쪽에서 본다.
  if grep -qiE "$LIMIT_RE" "$out_file" "$out_file.err" 2>/dev/null; then
    echo "🛑 STOP: gemini 에서 사용 한도/레이트 리밋 신호를 감지했습니다." >&2
    grep -ihE "$LIMIT_RE" "$out_file" "$out_file.err" 2>/dev/null | head -3 >&2
    return 99
  fi

  # 도구 폴백 경고 등 잡음 제거
  sed -i '' '/^Ripgrep is not available/d' "$out_file" 2>/dev/null || true
  [ -s "$out_file" ] || { echo "ERROR: gemini 응답이 비어있습니다." >&2; return 1; }
  return 0
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
