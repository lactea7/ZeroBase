# src/ep_simulator.py
import os
import math
import subprocess
import glob
import traceback
import shutil
import sys
import re

from src.idf_builder import IdfBuilder

try:
    import pandas as pd
except ImportError:
    pd = None

from src.cost_analyzer import LCCAnalyzer

# ---------------------------------------------------------
# [상용 데이터베이스 동적 파싱 로직]
# 💡 파일 이름 대소문자 완벽 무시! 내용 기반 오토 스캔 로직
# ---------------------------------------------------------
def load_databases(db_dir):
    print(f"\n🔍 [DB 로딩] 데이터베이스 탐색 폴더: {db_dir}")
            
    glazing_db = { 
        42: {"name": "Dbl Clr 6mm/13mm Air", "u": 2.74, "shgc": 0.60} 
    }
    
    if os.path.exists(db_dir):
        # 💡 _data 폴더 내의 모든 파일을 리스팅하여 대소문자 구분 없이 처리
        for f_name in os.listdir(db_dir):
            f_path = os.path.join(db_dir, f_name)
            
            if not os.path.isfile(f_path): 
                continue
            
            f_lower = f_name.lower()
            
            # 1. 텍스트 파일(.txt) 검사 -> Glazing.txt 매핑
            if f_lower.endswith('.txt') and 'glazing' in f_lower:
                try:
                    with open(f_path, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            parts = line.strip().split('#')
                            if len(parts) >= 7 and parts[0].isdigit():
                                glazing_id = int(parts[0])
                                u_value = float(parts[4]) if parts[4] else 2.74
                                shgc_value = float(parts[6]) if parts[6] else 0.70
                                
                                glazing_db[glazing_id] = {
                                    "name": parts[1].strip(), 
                                    "u": u_value, 
                                    "shgc": shgc_value
                                }
                    print(f"✅ 상용 창호 DB [{f_name}] 완벽 맵핑 완료!")
                except Exception as e: 
                    print(f"⚠️ Glazing DB 파싱 에러: {e}")
    else:
        print(f"⚠️ 에러: _data 폴더를 찾을 수 없습니다! ({db_dir})")
            
    return glazing_db

# ---------------------------------------------------------
# [에너지 요금제 완벽 매핑 - 2026 KEPCO & 지역난방 PDF 기반]
# ---------------------------------------------------------
ELEC_RATE_SUMMER = (183.6 + 128.9 + 98.1) / 3   # 6~8월 가중평균: 약 136.86원
ELEC_RATE_WINTER = (138.5 + 112.2 + 98.1) / 3   # 11~2월 가중평균: 약 116.26원
ELEC_RATE_SPRING = (121.7 + 103.9 + 98.1) / 3   # 3~5, 9~10월 가중평균: 약 107.9원
ELEC_BASE_CHARGE = 4910    # 기본요금 (원/kW)
HEAT_RATE_MCAL = 145.82    
HEAT_RATE_KWH = HEAT_RATE_MCAL * 0.8604

HEATING_EFF_DB = { 
    1: {1: 0.85, 2: 2.50, 4: 0.80, 11: 0.95}, 
    2: {2: 3.50, 11: 1.00}, 
    3: {1: 0.82, 2: 3.00, 11: 0.95}, 
    5: {1: 0.80, 2: 2.80, 4: 0.75} 
}

COOLING_EFF_DB = { 
    1: 3.50, 
    2: 4.20, 
    3: 3.20, 
    5: 2.80 
}

def calculate_surface_area(vertices):
    if len(vertices) < 3: 
        return 0.0
        
    nx, ny, nz = 0.0, 0.0, 0.0
    for i in range(len(vertices)):
        v1 = vertices[i]
        v2 = vertices[(i + 1) % len(vertices)]
        nx += (v1[1] - v2[1]) * (v1[2] + v2[2])
        ny += (v1[2] - v2[2]) * (v1[0] + v2[0])
        nz += (v1[0] - v2[0]) * (v1[1] + v2[1])
        
    return math.sqrt(nx*nx + ny*ny + nz*nz) / 2.0

def get_scaled_window_vertices(vertices, wwr):
    if not vertices or wwr <= 0: 
        return []
        
    cx = sum(v[0] for v in vertices) / len(vertices)
    cy = sum(v[1] for v in vertices) / len(vertices)
    cz = sum(v[2] for v in vertices) / len(vertices)
    scale = math.sqrt(wwr / 100.0)
    
    win_verts = []
    for v in vertices:
        wx = cx + (v[0] - cx) * scale
        wy = cy + (v[1] - cy) * scale
        wz = cz + (v[2] - cz) * scale
        win_verts.append([wx, wy, wz])
        
    return win_verts

def condense_daily_schedule(day_type_str: str, hourly_values: list) -> str:
    """24시간 배열을 EnergyPlus Schedule:Compact의 하루치 문자열로 압축"""
    if not hourly_values or len(hourly_values) != 24:
        return ""
    
    parts = [f"For: {day_type_str}"]
    current_val = hourly_values[0]
    
    for i in range(1, 25):
        if i == 24 or hourly_values[i] != current_val:
            parts.append(f"Until: {i:02d}:00")
            parts.append(str(current_val))
            if i < 24:
                current_val = hourly_values[i]
                
    return ", ".join(parts)

def generate_idf_and_simulate(payload: dict, temp_dir: str):
    project_data = payload.get("projectData", {})
    zones = payload.get("zones", [])
    surfaces = payload.get("surfaces", [])
    
    pv_capacity_kw = project_data.get("pvCapacity", 0)
    is_geothermal = project_data.get("geothermalApplied", False)
    location_key = project_data.get("location", "KOR_SQ_Seoul")
    
    calculated_floor_area = 0.0
    for s in surfaces:
        if "floor" in s.get("type", "").lower() or "slab" in s.get("type", "").lower():
            calculated_floor_area += calculate_surface_area(s.get("vertices", []))
            
    if calculated_floor_area > 1.0:
        total_area = calculated_floor_area
    else:
        total_area = len(zones) * 100.0
    
    total_lighting_power = 0.0
    for z in zones:
        total_lighting_power += z.get("lightingPower", 10.0)
    avg_light = total_lighting_power / max(len(zones), 1)
    
    total_window_area = 0.0
    total_wall_area = 0.0
    target_glazing_id = 42
    
    for s in surfaces:
        s_area = calculate_surface_area(s.get("vertices", []))
        wwr = s.get("wwr", 0)
        s_type = s.get("type", "").lower()
        
        if "wall" in s_type or "roof" in s_type:
            total_wall_area += s_area
            if "wall" in s_type and wwr > 0:
                total_window_area += s_area * (wwr / 100.0)
                if s.get("glazingId"): 
                    target_glazing_id = s.get("glazingId")

    temp_dir_abs = os.path.abspath(temp_dir)
    os.makedirs(temp_dir_abs, exist_ok=True)

    
    # 💡 [핵심 경로 수정] 프로젝트 구조에 최적화된 탐색
    search_ptr = os.path.dirname(os.path.abspath(__file__))
    db_dir = ""
    
    for _ in range(5):
        potential = os.path.join(search_ptr, "_data")
        if os.path.exists(potential):
            db_dir = potential
            break
        search_ptr = os.path.dirname(search_ptr)
        
    if not db_dir:
        db_dir = "/Users/minkimac/Desktop/gbXML_server/_data" 
    
    GLAZING_DB = load_databases(db_dir)
    
    # 창호 속성
    selected_glazing = GLAZING_DB.get(target_glazing_id)
    target_u = selected_glazing["u"] if selected_glazing else None
    target_shgc = selected_glazing["shgc"] if selected_glazing else None
    
    # 💡 [날씨 파일 자동 탐색]
    epw_files = []
    parent_of_db = os.path.dirname(db_dir)
    
    for root_walk, dirs, files in os.walk(parent_of_db):
        for f in files:
            if f.lower().endswith('.epw'):
                epw_files.append(os.path.join(root_walk, f))
    
    if epw_files:
        target_key = location_key.lower()
        city_name = location_key.split('_')[-1].lower()
        
        matched = []
        for f in epw_files:
            if target_key in os.path.basename(f).lower():
                matched.append(f)
                
        if not matched: 
            for f in epw_files:
                if city_name in os.path.basename(f).lower():
                    matched.append(f)
                    
        if not matched: 
            for f in epw_files:
                if "kor" in os.path.basename(f).lower():
                    matched.append(f)
                    
        if matched:
            weather_file_abs = os.path.abspath(matched[0])
        else:
            weather_file_abs = os.path.abspath(epw_files[0])
            
        print(f"🌤️ 엔진 기상 데이터 세팅 완료: {os.path.basename(weather_file_abs)}")
    else:
        weather_file_abs = os.path.join(temp_dir_abs, "default.epw")
        print("🚨 치명적 경고: .epw 날씨 파일을 찾을 수 없습니다!")

    # =========================================================
    # 💡 2단계: IDF 생성 (IdfBuilder 객체 패턴)
    # =========================================================
    idf_version = os.environ.get("EP_VERSION", "25.2")
    idf = IdfBuilder(version=idf_version)
    
    # 건물 기본 정보
    idf.add_building(project_data.get('name', 'BEM_Project'), project_data.get('orientation', 0))
    idf.add_run_period()
    
    # 기본 재료
    idf.add_material("Concrete_Heavy", "MediumRough", 0.2, 1.95, 2240, 900)
    
    # 표면별 단열재 + 구조체 + 유리
    for s in surfaces:
        u_val = max(0.1, s.get("uValue", 0.8))
        r_insul = max(0.01, (1.0 / u_val) - 0.102)
        t_insul = r_insul * 0.04
        
        idf.add_material(f"Insul_{s['id']}", "Smooth", t_insul, 0.04, 50, 800)
        idf.add_construction(f"Const_{s['id']}", ["Concrete_Heavy", f"Insul_{s['id']}", "Concrete_Heavy"])
        
        wwr = s.get("wwr", 0)
        if wwr > 0:
            g_id = s.get("glazingId", 42)
            g_info = GLAZING_DB.get(g_id, GLAZING_DB.get(42, {"u": 2.74, "shgc": 0.60}))
            idf.add_glazing_simple(f"Glass_{s['id']}", g_info['u'], g_info['shgc'])
            idf.add_construction(f"WinConst_{s['id']}", [f"Glass_{s['id']}"])

    # 스케줄
    idf.add_standard_schedules()
    
    custom_sch = project_data.get("customSchedule", {})
    use_custom = custom_sch.get("useCustom", False)
    
    if use_custom:
        holidays = custom_sch.get("holidays", [])
        for i, h_date in enumerate(holidays):
            idf.add_special_day(f"CustomHoliday_{i}", h_date)
            
        profiles = custom_sch.get("profiles", {})
        
        op_wd = condense_daily_schedule("Weekdays", profiles.get("weekday", {}).get("operation", [1]*24))
        op_we = condense_daily_schedule("Weekends", profiles.get("weekend", {}).get("operation", [0]*24))
        op_ho = condense_daily_schedule("Holidays", profiles.get("holiday", {}).get("operation", [0]*24))
        custom_op_text = f"Through: 12/31, {op_wd}, {op_we}, {op_ho}, For: AllOtherDays, Until: 24:00, 0.0"
        idf.add_schedule_compact("CustomOpSch", "AnyNumber", custom_op_text)
    
    # 존별 설정
    for z in zones:
        z_id = z['id'].replace(" ", "_")
        z_area_list = [calculate_surface_area(s.get("vertices", [])) for s in surfaces if s.get("zone") == z['id'] and "floor" in s.get("type", "").lower()]
        z_area = sum(z_area_list) if sum(z_area_list) >= 1.0 else 100.0
        z_height = z.get("height", 3.0)  # 💡 Zone별 자동역산 높이 사용
        
        idf.add_zone(z_id, z_area, z_height)
        
        heat_set = z.get("heatingSetpoint", 20.0)
        cool_set = z.get("coolingSetpoint", 26.0)
        activity = z.get("activityId", 1105)
        
        # 용도별 운영 스케줄 결정
        if use_custom:
            op_sch = "CustomOpSch"
            
            heat_wd = condense_daily_schedule("Weekdays", profiles.get("weekday", {}).get("heating", [15]*24))
            heat_we = condense_daily_schedule("Weekends", profiles.get("weekend", {}).get("heating", [15]*24))
            heat_ho = condense_daily_schedule("Holidays", profiles.get("holiday", {}).get("heating", [15]*24))
            heat_sch_text = f"Through: 12/31, {heat_wd}, {heat_we}, {heat_ho}, For: AllOtherDays, Until: 24:00, 15.0"
            
            cool_wd = condense_daily_schedule("Weekdays", profiles.get("weekday", {}).get("cooling", [30]*24))
            cool_we = condense_daily_schedule("Weekends", profiles.get("weekend", {}).get("cooling", [30]*24))
            cool_ho = condense_daily_schedule("Holidays", profiles.get("holiday", {}).get("cooling", [30]*24))
            cool_sch_text = f"Through: 12/31, {cool_wd}, {cool_we}, {cool_ho}, For: AllOtherDays, Until: 24:00, 30.0"
        else:
            if activity in [1440, 1441, 1442, 1443, 1444, 1114, 1115, 1107, 1112, 1120, 1121, 1445]:
                op_sch = "Sch_Res"
                heat_sch_text = f"Through: 12/31, For: Weekdays, Until: 08:00, {heat_set}, Until: 18:00, 15.0, Until: 24:00, {heat_set}, For: AllOtherDays, Until: 24:00, {heat_set}"
                cool_sch_text = f"Through: 12/31, For: Weekdays, Until: 08:00, {cool_set}, Until: 18:00, 30.0, Until: 24:00, {cool_set}, For: AllOtherDays, Until: 24:00, {cool_set}"
            elif activity in [1108, 1109, 1117, 1118]:
                op_sch = "Sch_Rest"
                heat_sch_text = f"Through: 12/31, For: AllDays, Until: 10:00, 15.0, Until: 21:00, {heat_set}, Until: 24:00, 15.0"
                cool_sch_text = f"Through: 12/31, For: AllDays, Until: 10:00, 30.0, Until: 21:00, {cool_set}, Until: 24:00, 30.0"
            elif activity in [1447, 1448, 1449, 1104, 1457, 1458, 1452]:
                op_sch = "Sch_Lab"
                heat_sch_text = f"Through: 12/31, For: AllDays, Until: 24:00, {heat_set}"
                cool_sch_text = f"Through: 12/31, For: AllDays, Until: 24:00, {cool_set}"
            else:
                op_sch = "Sch_Office"
                heat_sch_text = f"Through: 12/31, For: Weekdays, Until: 08:00, 15.0, Until: 18:00, {heat_set}, Until: 24:00, 15.0, For: AllOtherDays, Until: 24:00, 15.0"
                cool_sch_text = f"Through: 12/31, For: Weekdays, Until: 08:00, 30.0, Until: 18:00, {cool_set}, Until: 24:00, 30.0, For: AllOtherDays, Until: 24:00, 30.0"

        if z.get("isConditioned", True):
            idf.add_ideal_hvac(z_id, op_sch)
            idf.add_schedule_compact(f"{z_id}_HeatSch", "AnyNumber", heat_sch_text)
            idf.add_schedule_compact(f"{z_id}_CoolSch", "AnyNumber", cool_sch_text)
            idf.add_thermostat(z_id, f"{z_id}_HeatSch", f"{z_id}_CoolSch")

        ppl_dens = z.get("peopleDensity", 0.1)
        light_p = z.get("lightingPower", 10.0)
        equip_p = z.get("equipmentPower", 15.0)
        
        if ppl_dens > 0:
            idf.add_people(f"{z_id}_Ppl", z_id, op_sch, ppl_dens)
        if light_p > 0:
            idf.add_lights(f"{z_id}_Lgt", z_id, op_sch, light_p)
        if equip_p > 0:
            idf.add_equipment(f"{z_id}_Eqp", z_id, op_sch, equip_p)
        
        idf.add_infiltration(f"{z_id}_Inf", z_id)

    # 표면 지오메트리
    for s in surfaces:
        ep_type = "Wall"
        t = s.get("type", "").lower()
        if "roof" in t:
            ep_type = "Roof"
        elif "floor" in t or "slab" in t:
            ep_type = "Floor"
        
        obc, sun, wind = "Outdoors", "SunExposed", "WindExposed"
        if "interior" in t or s.get("adjacentZone"):
            obc, sun, wind = "Adiabatic", "NoSun", "NoWind"
        
        z_id = s['zone'].replace(" ", "_")
        verts = s.get('vertices', [])
        
        idf.add_surface(s['id'], ep_type, f"Const_{s['id']}", z_id, obc, sun, wind, verts)
        
        wwr = s.get("wwr", 0)
        if ep_type == "Wall" and wwr > 0:
            win_verts = get_scaled_window_vertices(verts, wwr)
            if win_verts:
                idf.add_window(f"Win_{s['id']}", f"WinConst_{s['id']}", s['id'], win_verts)

    # 출력 변수
    idf.add_output_variables()

    # =========================================================
    # 💡 3단계: 시뮬레이션 실행 (IdfBuilder.run 패턴)
    # =========================================================
    ep_success = False
    try:
        print(f"\n▶️ EnergyPlus 경제성(LCC) 통합 시뮬레이션 가동 중... (지역: {location_key})")
        ep_success = idf.run(weather_file_abs, temp_dir_abs)
    except Exception as e:
        print(f"⚠️ 엔진 에러: {e}")
    # 💡 4단계: 에너지 공과금 및 공사원가 산출 (LCCAnalyzer 연동)
    # =========================================================
    analyzer = LCCAnalyzer(db_dir)
    
    if ep_success:
        csv_path = os.path.join(temp_dir_abs, "eplusout.csv")
        act_main = project_data.get('activityId', 1105)
        
        result_data = analyzer.calculate(
            eplus_csv_path=csv_path,
            zones=zones,
            total_area=total_area,
            total_window_area=total_window_area,
            total_wall_area=total_wall_area,
            target_u=target_u,
            target_shgc=target_shgc,
            pv_capacity_kw=pv_capacity_kw,
            is_geothermal=is_geothermal,
            act_main=act_main
        )
        return result_data

    # 시뮬레이션 실패 시 fallback 반환
    return analyzer._fallback_data()