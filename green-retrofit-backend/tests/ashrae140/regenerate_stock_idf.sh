#!/usr/bin/env bash
# stock IDF 를 BESTEST-GSR measure 로 정식 재생성한다.
#
# **평상시엔 실행할 필요가 없다.** 생성된 IDF 가 커밋돼 있고 테스트는 그것만 돌린다.
# OpenStudio 는 런타임·CI 의존성이 아니다 — 여기서 한 번 만들고 끝이다.
#
# 재생성이 필요한 때:
#   - EnergyPlus 를 새 버전으로 올릴 때 (기준값 CSV 도 함께 갱신해야 한다)
#   - BESTEST-GSR 배포본이 갱신됐을 때
#   - 케이스를 추가할 때 (CASES 에 추가)
#
# 사용법:
#   ./regenerate_stock_idf.sh <OpenStudio 루트> <BESTEST-GSR 체크아웃>
#
# 예:
#   ./regenerate_stock_idf.sh ~/dl/OpenStudio-3.11.0+241b8abb4d-Darwin-arm64 ~/dl/BESTEST-GSR
set -euo pipefail

OS_ROOT=${1:?OpenStudio 루트 경로가 필요하다}
GSR=${2:?BESTEST-GSR 체크아웃 경로가 필요하다}
OS_CLI="$OS_ROOT/bin/openstudio"
HERE=$(cd "$(dirname "$0")" && pwd)
SEED="$GSR/measures/bestest_building_thermal_envelope_and_fabric_load/tests/seed_empty.osm"

[ -x "$OS_CLI" ] || { echo "openstudio CLI 를 찾을 수 없다: $OS_CLI" >&2; exit 1; }
[ -f "$SEED" ]   || { echo "seed 모델을 찾을 수 없다: $SEED" >&2; exit 1; }

# 케이스 번호 | measure 의 case_num 인자 (문자열이 정확히 일치해야 한다)
CASES=$(cat <<'EOF'
600|600 - Base Case
610|610 - South Shading
620|620 - East/West Window Orientation
630|630 - East/West Shading
640|640 - Thermostat Setback
650|650 - Night Ventilation
660|660 - Glazing Low E
670|670 - Glazing Single Pane
680|680 - Increased Opaque Surface Insulation
685|685 - Thermostat Deadband
695|695 - Thermostat Deadband and Increased Opaque Surface Insulation
900|900 - High-Mass Base Case
910|910 - High-Mass South Shading
920|920 - High-Mass East/West Window Orientation
930|930 - High-Mass East/West Shading
940|940 - High-Mass Thermostat Setback
950|950 - High-Mass Night Ventilation
985|985 - Thermostat Deadband
995|995 - Thermostat Deadband and Increased Opaque Surface Insulation
EOF
)

WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
cp "$SEED" "$WORK/"
cd "$WORK"

while IFS='|' read -r id name; do
  [ -z "$id" ] && continue
  python3 - "$id" "$name" "$GSR" > "osw_$id.osw" <<'PY'
import json, sys
case_id, case_name, gsr = sys.argv[1:4]
json.dump({
    "seed_file": "seed_empty.osm",
    "measure_paths": [gsr + "/measures"],
    "file_paths": [gsr + "/shared_resources"],   # measure 가 725650TYCST.epw 를 여기서 찾는다
    "run_directory": f"./run{case_id}",
    "steps": [{
        "measure_dir_name": "bestest_building_thermal_envelope_and_fabric_load",
        "arguments": {"case_num": case_name},
    }],
}, sys.stdout, indent=1)
PY
  if "$OS_CLI" run -w "osw_$id.osw" > "log_$id.txt" 2>&1 && [ -f "run$id/in.idf" ]; then
    cp "run$id/in.idf" "$HERE/stock_idf/case$id.idf"
    printf '%s ✓  ' "$id"
  else
    printf '\n%s 실패 — %s/log_%s.txt 확인\n' "$id" "$WORK" "$id" >&2
    trap - EXIT       # 실패 로그를 볼 수 있게 작업 디렉터리를 남긴다
    exit 1
  fi
done <<< "$CASES"

echo
{
  echo "# stock IDF provenance (이 파일은 regenerate_stock_idf.sh 가 만든다)"
  echo "생성일: $(date '+%Y-%m-%d %H:%M:%S %z')"
  echo "OpenStudio: $("$OS_CLI" --version)"
  echo "EnergyPlus(동봉): $(ls "$OS_ROOT/EnergyPlus" | grep -E '^energyplus-[0-9]' | head -1)"
  echo "BESTEST-GSR: $(cd "$GSR" && git rev-parse HEAD 2>/dev/null || echo '(git 아님)')"
  echo "measure: bestest_building_thermal_envelope_and_fabric_load"
  echo "기상(measure 내부 고정): 725650TYCST.epw"
} > "$HERE/stock_idf/PROVENANCE.txt"
cat "$HERE/stock_idf/PROVENANCE.txt"
