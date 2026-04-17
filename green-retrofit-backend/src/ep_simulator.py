# src/ep_simulator.py
import os
import math
import subprocess
import glob
import traceback
import shutil
import sys
import re

try:
    import pandas as pd
except ImportError:
    pd = None

# ---------------------------------------------------------
# [상용 데이터베이스 동적 파싱 로직]
# 💡 파일 이름 대소문자 완벽 무시! 내용 기반 오토 스캔 로직
# ---------------------------------------------------------
def clean_price(price_str):
    """가격 문자열에서 콤마(,)와 공백을 제거하고 숫자로 변환합니다."""
    if pd.isna(price_str): 
        return 0.0
    
    cleaned = re.sub(r'[^\d.]', '', str(price_str))
    
    if cleaned:
        return float(cleaned)
    else:
        return 0.0

def safe_read_csv(filepath):
    """
    💡 엑셀에서 파일명을 바꿀 때 발생하는 인코딩(CP949) 변환 문제와
    헤더 라인이 0번 줄로 밀려 올라가는 문제를 모두 극복하고
    가장 안전하게 CSV 데이터를 읽어내는 함수입니다.
    """
    encodings_to_try = ['utf-8', 'cp949', 'euc-kr', 'utf-8-sig']
    skips_to_try = [0, 1, 2]
    
    for enc in encodings_to_try:
        for skip in skips_to_try:
            try:
                df = pd.read_csv(filepath, skiprows=skip, encoding=enc)
                # 주요 키워드가 컬럼에 하나라도 잡히면 제대로 읽은 것으로 판정!
                if '공급가격' in df.columns or '적용단가' in df.columns or '재료비' in df.columns or '거래가격' in df.columns or '품명' in df.columns:
                    return df
            except Exception:
                continue
                
    # 모든 조합이 실패하면 에러를 뱉지 않고 빈 데이터프레임 대신 None 반환
    return None

def load_databases(db_dir):
    print(f"\n🔍 [DB 로딩] 데이터베이스 탐색 폴더: {db_dir}")
            
    glazing_db = { 
        42: {"name": "Dbl Clr 6mm/13mm Air", "u": 2.74, "shgc": 0.60} 
    }
    
    cost_db_dict = {
        "status": {"eco_loaded": False, "nara_loaded": False, "items": 0},
        "avg_prices": {
            "window": 250000,   # 기본값 (원/m2)
            "insulation": 45000,
            "led": 120000,
            "hvac_kw": 200000
        },
        "window_db": [] # 창호 상세 맵핑을 위해 데이터 보관
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
            
            # 2. CSV 파일(.csv) 검사 -> 원가/단가 DB
            elif f_lower.endswith('.csv'):
                try:
                    # 💡 강제 스킵(skiprows=2) 대신 안전한 커스텀 함수로 읽어옵니다.
                    df = safe_read_csv(f_path)
                    
                    if df is None or df.empty:
                        print(f"⚠️ [{f_name}] 데이터를 읽을 수 없습니다 (인코딩/형식 문제)")
                        continue
                    
                    # 💡 파일 내용으로 어떤 DB인지 자동 감지
                    if '공급가격' in df.columns:
                        df['price_num'] = df['공급가격'].apply(clean_price)
                        row_texts = df.astype(str).apply(lambda x: ' '.join(x), axis=1)
                        
                        # 창호/유리 항목 탐색
                        window_items = df[row_texts.str.contains('창호|유리|복층|로이', na=False, case=False)]
                        
                        for idx, row in window_items.iterrows():
                            price = row.get('price_num', 0)
                            if price > 0:
                                text_chunk = row_texts[idx]
                                u_match = re.search(r'U[-]?value.*?([\d.]+)', text_chunk, re.IGNORECASE)
                                shgc_match = re.search(r'SHGC.*?([\d.]+)', text_chunk, re.IGNORECASE)
                                
                                u_val = float(u_match.group(1)) if u_match else None
                                shgc_val = float(shgc_match.group(1)) if shgc_match else None
                                
                                if len(row) > 10:
                                    name_val = str(row.iloc[10])
                                else:
                                    name_val = "친환경 창호"
                                
                                cost_db_dict["window_db"].append({
                                    "name": name_val, 
                                    "u": u_val, 
                                    "shgc": shgc_val, 
                                    "price": price
                                })
                        
                        # LED 등기구 평균 단가 추출
                        led_items = df[row_texts.str.contains('LED', na=False, case=False)]
                        if not led_items.empty: 
                            cost_db_dict["avg_prices"]["led"] = led_items['price_num'].mean()
                            
                        cost_db_dict["status"]["eco_loaded"] = True
                        cost_db_dict["status"]["items"] += len(df)
                        print(f"✅ 친환경 자재 DB [{f_name}] 자동 로드 완료: {len(df)}건")
                    
                    # 나라장터 DB 감별
                    elif any(col in df.columns for col in ['적용단가', '단위', '재 료 비', '거래가격']):
                        cost_db_dict["status"]["nara_loaded"] = True
                        cost_db_dict["status"]["items"] += len(df)
                        print(f"✅ 나라장터 조달청 DB [{f_name}] 자동 로드 완료: {len(df)}건")
                        
                except Exception as e:
                    print(f"⚠️ CSV 파일 파싱 실패 ({f_name}): {e}")
    else:
        print(f"⚠️ 에러: _data 폴더를 찾을 수 없습니다! ({db_dir})")
            
    return glazing_db, cost_db_dict

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
    idf_path_abs = os.path.join(temp_dir_abs, "generated_model.idf")
    
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
    
    GLAZING_DB, COST_DB = load_databases(db_dir)
    
    # 창호 매핑 (1순위, 2순위 정밀 추적 로직 압축 해제)
    target_window_price = COST_DB["avg_prices"]["window"]
    selected_glazing = GLAZING_DB.get(target_glazing_id)
    mapped_window_name = "기본 단가 반영 (DB 미매칭)"
    
    if selected_glazing and COST_DB["window_db"]:
        target_u = selected_glazing["u"]
        target_shgc = selected_glazing["shgc"]
        best_match = None
        min_diff = float('inf')
        
        for w_item in COST_DB["window_db"]:
            if w_item["u"] is not None:
                diff = abs(w_item["u"] - target_u)
                if w_item["shgc"] is not None and target_shgc is not None:
                    diff += abs(w_item["shgc"] - target_shgc)
                    
                if diff < min_diff:
                    min_diff = diff
                    best_match = w_item
                    
        if best_match and min_diff < 1.5:
            target_window_price = best_match["price"]
            mapped_window_name = best_match["name"]
    
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
    # 💡 2단계: IDF 생성 (압축 해제 및 정렬)
    # =========================================================
    with open(idf_path_abs, "w", encoding="utf-8") as f:
        f.write("Version, 25.2;\n")
        f.write("SimulationControl, No, No, No, No, Yes;\n")
        f.write(f"Building, {project_data.get('name', 'BEM_Project')}, {project_data.get('orientation', 0)}, Suburbs, 0.04, 0.4, FullExterior, 25, 6;\n")
        f.write("SurfaceConvectionAlgorithm:Inside, TARP;\n")
        f.write("SurfaceConvectionAlgorithm:Outside, DOE-2;\n")
        f.write("HeatBalanceAlgorithm, ConductionTransferFunction;\n")
        f.write("Timestep, 4;\n")
        f.write("GlobalGeometryRules, UpperLeftCorner, CounterClockwise, World;\n")
        f.write("RunPeriod, AnnualRun, 1, 1, 2024, 12, 31, 2024, Sunday, Yes, Yes, No, Yes, Yes;\n")
        f.write("Material, Concrete_Heavy, MediumRough, 0.2, 1.95, 2240, 900, 0.9, 0.7, 0.7;\n")

        for s in surfaces:
            u_val = max(0.1, s.get("uValue", 0.8))
            r_insul = max(0.01, (1.0 / u_val) - 0.102)
            t_insul = r_insul * 0.04
            
            f.write(f"Material, Insul_{s['id']}, Smooth, {t_insul:.4f}, 0.04, 50, 800, 0.9, 0.7, 0.7;\n")
            f.write(f"Construction, Const_{s['id']}, Concrete_Heavy, Insul_{s['id']}, Concrete_Heavy;\n")
            
            wwr = s.get("wwr", 0)
            if wwr > 0:
                g_id = s.get("glazingId", 42)
                g_info = GLAZING_DB.get(g_id, GLAZING_DB.get(42, {"u": 2.74, "shgc": 0.60}))
                
                f.write(f"WindowMaterial:SimpleGlazingSystem, Glass_{s['id']}, {g_info['u']:.2f}, {g_info['shgc']:.2f}, 0.8;\n")
                f.write(f"Construction, WinConst_{s['id']}, Glass_{s['id']};\n")

        f.write("ScheduleTypeLimits, AnyNumber;\n")
        f.write("ScheduleTypeLimits, Fraction, 0.0, 1.0, Continuous;\n")
        f.write("ScheduleTypeLimits, ControlType, 0, 4, Discrete;\n")
        
        f.write("Schedule:Compact, AlwaysOn, Fraction, Through: 12/31, For: AllDays, Until: 24:00, 1.0;\n")
        f.write("Schedule:Compact, ActivitySch, AnyNumber, Through: 12/31, For: AllDays, Until: 24:00, 120.0;\n")
        f.write("Schedule:Compact, DualZoneControlSch, ControlType, Through: 12/31, For: AllDays, Until: 24:00, 4;\n")
        f.write("Schedule:Compact, Sch_Office, Fraction, Through: 12/31, For: Weekdays, Until: 08:00, 0.0, Until: 18:00, 1.0, Until: 24:00, 0.0, For: AllOtherDays, Until: 24:00, 0.0;\n")
        f.write("Schedule:Compact, Sch_Res, Fraction, Through: 12/31, For: Weekdays, Until: 08:00, 1.0, Until: 18:00, 0.0, Until: 24:00, 1.0, For: AllOtherDays, Until: 24:00, 1.0;\n")
        f.write("Schedule:Compact, Sch_Rest, Fraction, Through: 12/31, For: AllDays, Until: 10:00, 0.0, Until: 14:00, 1.0, Until: 17:00, 0.2, Until: 21:00, 1.0, Until: 24:00, 0.0;\n")
        f.write("Schedule:Compact, Sch_Lab, Fraction, Through: 12/31, For: AllDays, Until: 24:00, 1.0;\n")

        for z in zones:
            z_id = z['id'].replace(" ", "_")
            z_area_list = [calculate_surface_area(s.get("vertices", [])) for s in surfaces if s.get("zone") == z['id'] and "floor" in s.get("type", "").lower()]
            z_area = sum(z_area_list)
            
            if z_area < 1.0: 
                z_area = 100.0 
                
            f.write(f"Zone, {z_id}, 0, 0, 0, 0, 1, 1, 3.0, {(z_area * 3.0):.2f}, {z_area:.2f};\n")
            
            heat_set = z.get("heatingSetpoint", 20.0)
            cool_set = z.get("coolingSetpoint", 26.0)
            activity = z.get("activityId", 1105)
            
            if activity in [1440, 1441, 1442, 1443, 1444, 1114, 1115, 1107, 1112, 1120, 1121, 1445]: 
                op_sch = "Sch_Res"
                sch_prefix = f"Through: 12/31, For: Weekdays, Until: 08:00, {heat_set}, Until: 18:00, 15.0, Until: 24:00, {heat_set}, For: AllOtherDays, Until: 24:00, {heat_set}"
                cool_prefix = f"Through: 12/31, For: Weekdays, Until: 08:00, {cool_set}, Until: 18:00, 30.0, Until: 24:00, {cool_set}, For: AllOtherDays, Until: 24:00, {cool_set}"
            elif activity in [1108, 1109, 1117, 1118]: 
                op_sch = "Sch_Rest"
                sch_prefix = f"Through: 12/31, For: AllDays, Until: 10:00, 15.0, Until: 21:00, {heat_set}, Until: 24:00, 15.0"
                cool_prefix = f"Through: 12/31, For: AllDays, Until: 10:00, 30.0, Until: 21:00, {cool_set}, Until: 24:00, 30.0"
            elif activity in [1447, 1448, 1449, 1104, 1457, 1458, 1452]: 
                op_sch = "Sch_Lab"
                sch_prefix = f"Through: 12/31, For: AllDays, Until: 24:00, {heat_set}"
                cool_prefix = f"Through: 12/31, For: AllDays, Until: 24:00, {cool_set}"
            else: 
                op_sch = "Sch_Office"
                sch_prefix = f"Through: 12/31, For: Weekdays, Until: 08:00, 15.0, Until: 18:00, {heat_set}, Until: 24:00, 15.0, For: AllOtherDays, Until: 24:00, 15.0"
                cool_prefix = f"Through: 12/31, For: Weekdays, Until: 08:00, 30.0, Until: 18:00, {cool_set}, Until: 24:00, 30.0, For: AllOtherDays, Until: 24:00, 30.0"

            if z.get("isConditioned", True):
                f.write(f"ZoneHVAC:EquipmentConnections, {z_id}, {z_id}_Equip, {z_id}_Inlet, , {z_id}_Node, {z_id}_Return;\n")
                f.write(f"ZoneHVAC:EquipmentList, {z_id}_Equip, SequentialLoad, ZoneHVAC:IdealLoadsAirSystem, {z_id}_Ideal, 1, 1;\n")
                f.write(f"DesignSpecification:OutdoorAir, {z_id}_OA, Sum, 0.0025, 0.0008, , , {op_sch};\n")
                f.write(f"ZoneHVAC:IdealLoadsAirSystem, {z_id}_Ideal, , {z_id}_Inlet, , , 50, 13, 0.015, 0.008, NoLimit, , , NoLimit, , , , , , , , {z_id}_OA;\n")
                f.write(f"Schedule:Compact, {z_id}_HeatSch, AnyNumber, {sch_prefix};\n")
                f.write(f"Schedule:Compact, {z_id}_CoolSch, AnyNumber, {cool_prefix};\n")
                f.write(f"ThermostatSetpoint:DualSetpoint, {z_id}_DualSetp, {z_id}_HeatSch, {z_id}_CoolSch;\n")
                f.write(f"ZoneControl:Thermostat, {z_id}_Thermostat, {z_id}, DualZoneControlSch, ThermostatSetpoint:DualSetpoint, {z_id}_DualSetp;\n")

            ppl_dens = z.get("peopleDensity", 0.1)
            light_p = z.get("lightingPower", 10.0)
            equip_p = z.get("equipmentPower", 15.0)
            
            if ppl_dens > 0: 
                f.write(f"People, {z_id}_Ppl, {z_id}, {op_sch}, People/Area, , {ppl_dens}, , , , ActivitySch;\n")
            if light_p > 0: 
                f.write(f"Lights, {z_id}_Lgt, {z_id}, {op_sch}, Watts/Area, , {light_p};\n")
            if equip_p > 0: 
                f.write(f"ElectricEquipment, {z_id}_Eqp, {z_id}, {op_sch}, Watts/Area, , {equip_p};\n")
                
            f.write(f"ZoneInfiltration:DesignFlowRate, {z_id}_Inf, {z_id}, AlwaysOn, AirChanges/Hour, , , , 0.5, 1.0, 0.0, 0.0, 0.0;\n")
            
        for s in surfaces:
            ep_type = "Wall"
            t = s.get("type", "").lower()
            
            if "roof" in t: 
                ep_type = "Roof"
            elif "floor" in t or "slab" in t: 
                ep_type = "Floor"
                
            obc = "Outdoors"
            sun = "SunExposed"
            wind = "WindExposed"
            
            if "interior" in t or s.get("adjacentZone"): 
                obc = "Adiabatic"
                sun = "NoSun"
                wind = "NoWind"
                
            z_id = s['zone'].replace(" ", "_")
            verts = s.get('vertices', [])
            
            f.write(f"BuildingSurface:Detailed, {s['id']}, {ep_type}, Const_{s['id']}, {z_id}, , {obc}, , {sun}, {wind}, Autocalculate, {len(verts)}")
            if verts:
                f.write(",\n")
                for i, v in enumerate(verts):
                    terminator = ";" if i == len(verts) - 1 else ","
                    f.write(f"  {v[0]:.4f}, {v[1]:.4f}, {v[2]:.4f}{terminator}\n")
            else: 
                f.write(";\n")
            
            wwr = s.get("wwr", 0)
            if ep_type == "Wall" and wwr > 0:
                win_verts = get_scaled_window_vertices(verts, wwr)
                if win_verts:
                    f.write(f"FenestrationSurface:Detailed, Win_{s['id']}, Window, WinConst_{s['id']}, {s['id']}, , Autocalculate, , 1, {len(win_verts)}")
                    f.write(",\n")
                    for i, v in enumerate(win_verts):
                        terminator = ";" if i == len(win_verts) - 1 else ","
                        f.write(f"  {v[0]:.4f}, {v[1]:.4f}, {v[2]:.4f}{terminator}\n")
                
        f.write("Output:Variable, *, Zone Ideal Loads Supply Air Total Heating Energy, Monthly;\n")
        f.write("Output:Variable, *, Zone Ideal Loads Supply Air Total Cooling Energy, Monthly;\n")
        f.write("Output:Variable, *, Lights Electricity Energy, Monthly;\n")
        f.write("Output:Variable, *, Electric Equipment Electricity Energy, Monthly;\n")
        f.write("OutputControl:Table:Style, Comma;\n")
        f.write("Output:Table:SummaryReports, AllSummary;\n")

    # =========================================================
    # 💡 3단계: 시뮬레이션 실행 (압축 해제)
    # =========================================================
    ep_success = False
    try:
        print(f"\n▶️ EnergyPlus 경제성(LCC) 통합 시뮬레이션 가동 중... (지역: {location_key})")
        ep_cmd = "energyplus"
        
        if shutil.which(ep_cmd) is None:
            for p in ["/Applications/EnergyPlus-25-2-0/energyplus", "/usr/local/bin/energyplus"]:
                if os.path.exists(p): 
                    ep_cmd = p
                    break

        cmd = [ep_cmd, "-w", weather_file_abs, "-r", idf_path_abs]
        process = subprocess.Popen(cmd, cwd=temp_dir_abs, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        
        for line in process.stdout: 
            sys.stdout.write(line)
            sys.stdout.flush()
            
        process.wait()
        
        err_path = os.path.join(temp_dir_abs, "eplusout.err")
        fatal_error = False
        
        if os.path.exists(err_path):
            with open(err_path, "r", encoding="utf-8", errors="ignore") as f_err:
                if "Fatal" in f_err.read(): 
                    fatal_error = True
                    
        if process.returncode == 0 and not fatal_error: 
            ep_success = True
            
    except Exception as e: 
        print(f"⚠️ 엔진 에러: {e}")

    # =========================================================
    # 💡 4단계: 에너지 공과금 및 공사원가 산출 (압축 해제)
    # =========================================================
    if ep_success and pd is not None:
        try:
            csv_path = os.path.join(temp_dir_abs, "eplusout.csv")
            df = pd.read_csv(csv_path).fillna(0)
            df.columns = [c.strip() for c in df.columns]
            
            h_cols = [c for c in df.columns if 'Ideal Loads' in c and 'Heating' in c and '[J]' in c]
            c_cols = [c for c in df.columns if 'Ideal Loads' in c and 'Cooling' in c and '[J]' in c]
            l_cols = [c for c in df.columns if 'Lights' in c and 'Electricity' in c and '[J]' in c]
            e_cols = [c for c in df.columns if 'Electric Equipment' in c and 'Electricity' in c and '[J]' in c]

            monthly_data = []
            a_h_req = 0.0
            a_c_req = 0.0
            a_h_con = 0.0
            a_c_con = 0.0
            a_l_con = 0.0
            a_e_con = 0.0
            
            annual_elec_bill = 0
            annual_heat_bill = 0
            peak_elec_kwh = 0
            
            for m in range(min(12, len(df))):
                m_h_req = 0.0
                m_c_req = 0.0
                m_h_con = 0.0
                m_c_con = 0.0
                m_l_con = 0.0
                m_e_con = 0.0
                
                for z in zones:
                    z_id = z['id'].replace(" ", "_").upper()
                    
                    zh_kwh = sum(float(df.iloc[m][c]) for c in h_cols if z_id in c.upper()) / 3600000.0
                    zc_kwh = sum(float(df.iloc[m][c]) for c in c_cols if z_id in c.upper()) / 3600000.0
                    zl_kwh = sum(float(df.iloc[m][c]) for c in l_cols if z_id in c.upper()) / 3600000.0
                    ze_kwh = sum(float(df.iloc[m][c]) for c in e_cols if z_id in c.upper()) / 3600000.0
                    
                    m_h_req += zh_kwh
                    m_c_req += zc_kwh
                    m_l_con += zl_kwh
                    m_e_con += ze_kwh
                    
                    if not z.get("isConditioned", True): 
                        continue
                        
                    hvac_sys = z.get('hvacSystemId', 5)
                    fuel_type = z.get('heatingFuelId', 2)
                    
                    if is_geothermal: 
                        h_cop = 4.5
                        c_cop = 5.0
                    else:
                        c_cop = COOLING_EFF_DB.get(hvac_sys, 2.8)
                        h_cop = HEATING_EFF_DB.get(hvac_sys, {}).get(fuel_type, 1.0)
                        
                    m_h_con += zh_kwh / h_cop
                    m_c_con += zc_kwh / c_cop
                
                a_h_req += m_h_req
                a_c_req += m_c_req
                a_h_con += m_h_con
                a_c_con += m_c_con
                a_l_con += m_l_con
                a_e_con += m_e_con
                
                month_num = m + 1
                month_elec_kwh = m_c_con + m_l_con + m_e_con
                month_heat_kwh = m_h_con
                
                if month_elec_kwh > peak_elec_kwh: 
                    peak_elec_kwh = month_elec_kwh
                
                if month_num in [6, 7, 8]: 
                    elec_rate = ELEC_RATE_SUMMER
                elif month_num in [11, 12, 1, 2]: 
                    elec_rate = ELEC_RATE_WINTER
                else: 
                    elec_rate = ELEC_RATE_SPRING
                
                annual_elec_bill += month_elec_kwh * elec_rate
                annual_heat_bill += month_heat_kwh * HEAT_RATE_KWH
                
                monthly_data.append({
                    "name": f"{month_num}월", 
                    "heating": round(m_h_con / total_area, 1), 
                    "cooling": round(m_c_con / total_area, 1)
                })

            if pv_capacity_kw and total_area > 0:
                pv_gen = (pv_capacity_kw * 1300) / total_area 
            else:
                pv_gen = 0.0
                
            act_main = project_data.get('activityId', 1105)
            
            if act_main in [1440, 1114]:
                hw_base = 25.0
            elif act_main in [1108, 1109]:
                hw_base = 15.0
            else:
                hw_base = 5.0
                
            if act_main in [1447, 1448]:
                vent_base = 12.0
            else:
                vent_base = 8.0
                
            annual_elec_bill += (vent_base * total_area) * ELEC_RATE_SPRING
            annual_heat_bill += ((hw_base * 1.1) * total_area) * HEAT_RATE_KWH
            
            if peak_elec_kwh:
                peak_kw_estimate = peak_elec_kwh / 200 
            else:
                peak_kw_estimate = total_area * 0.1
                
            annual_elec_bill += peak_kw_estimate * ELEC_BASE_CHARGE * 12
            
            window_cost = total_window_area * target_window_price
            insulation_cost = total_wall_area * COST_DB["avg_prices"]["insulation"]
            led_cost = total_area * COST_DB["avg_prices"]["led"]
            hvac_cost = peak_kw_estimate * COST_DB["avg_prices"]["hvac_kw"]
            
            total_capital_cost = window_cost + insulation_cost + led_cost + hvac_cost

            matrix = {
                "heating": {"req": round(a_h_req/total_area, 1), "con": round(a_h_con/total_area, 1)},
                "cooling": {"req": round(a_c_req/total_area, 1), "con": round(a_c_con/total_area, 1)},
                "hotwater": {"req": hw_base, "con": hw_base * 1.1},
                "lighting": {"req": round(a_l_con/total_area, 1), "con": round(a_l_con/total_area, 1)},
                "ventilation": {"req": vent_base, "con": vent_base},
                "renewable": {"req": -round(pv_gen, 1), "con": -round(pv_gen, 1)}
            }
            
            total_con = sum(v["con"] for k,v in matrix.items() if k != "renewable")
            
            independence_val = min(100, (abs(matrix["renewable"]["con"]) / total_con * 100)) if total_con > 0 else 0
            
            summary = {
                "demand_per_m2": sum(v["req"] for k,v in matrix.items() if k != "renewable"), 
                "consume_per_m2": total_con, 
                "primary_per_m2": total_con * 2.75, 
                "co2_per_m2": total_con * 0.466, 
                "independence": independence_val
            }
            
            financial = {
                "annual_elec_bill": int(annual_elec_bill),
                "annual_heat_bill": int(annual_heat_bill),
                "total_energy_bill": int(annual_elec_bill + annual_heat_bill),
                "capital_cost": int(total_capital_cost),
                "cost_details": {
                    "window": int(window_cost), 
                    "insulation": int(insulation_cost), 
                    "led": int(led_cost), 
                    "hvac": int(hvac_cost)
                },
                "mapped_window_name": mapped_window_name,
                "csv_db_loaded": COST_DB["status"]
            }
            
            final_data = { 
                "summary": summary, 
                "monthly": monthly_data, 
                "matrix": matrix, 
                "financial": financial 
            }
            
            return { **final_data, "result": final_data }
            
        except Exception as e: 
            print(f"⚠️ 파싱 에러: {e}")

    fallback_data = {
        "summary": {"demand_per_m2": 50, "consume_per_m2": 30, "primary_per_m2": 80, "co2_per_m2": 15, "independence": 10}, 
        "monthly": [{"name": f"{i}월", "heating": 5, "cooling": 5} for i in range(1, 13)], 
        "matrix": {},
        "financial": {
            "mapped_window_name": "기본 단가 반영 (DB 미매칭)", 
            "annual_elec_bill": 0, 
            "annual_heat_bill": 0, 
            "capital_cost": 0, 
            "cost_details": {"window": 0, "insulation": 0, "led": 0, "hvac": 0},
            "csv_db_loaded": {"eco_loaded": False, "nara_loaded": False, "items": 0}
        }
    }
    return { **fallback_data, "result": fallback_data }