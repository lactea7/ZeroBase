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
from src.activity_schedules import load_activity_names, classify_activity, build_schedules, get_archetype_loads, daily_op_hours

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

def calc_outlet_power_density(zone, floor_area):
    """콘센트 수 기반 전기 부하 밀도 산정 (NREL 2012 기준)"""
    outlet_count = zone.get("outletCount", 0)
    if outlet_count <= 0:
        return 0.0
    
    activity = zone.get("activityId", 1105)
    # 용도별 콘센트당 정격 전력 (W)
    W_PER_OUTLET = {
        "office": 150,
        "residential": 80,
        "lab": 200,
        "restaurant": 120,
        "warehouse": 50,
        "default": 100
    }
    
    def get_activity_type(act_id):
        try:
            act_id = int(act_id)
        except (ValueError, TypeError):
            return "default"
        if act_id in [1105, 1106, 1103, 1113, 1116, 1119, 1122]:
            return "office"
        elif act_id in [1440, 1441, 1442, 1443, 1444, 1114, 1115, 1107, 1112, 1120, 1121, 1445]:
            return "residential"
        elif act_id in [1447, 1448, 1449, 1104, 1457, 1458, 1452]:
            return "lab"
        elif act_id in [1108, 1109, 1117, 1118]:
            return "restaurant"
        return "default"
        
    category = get_activity_type(activity)
    w_per = W_PER_OUTLET.get(category, 100)
    diversity = 0.5   # NREL 권장
    utilization = 0.7 # IEC 60364-8-1 ku 평균
    
    outlet_load_w = outlet_count * w_per * diversity * utilization
    power_density = outlet_load_w / max(floor_area, 1.0)
    return min(power_density, 25.0)  # ASHRAE 90.1 상한

def get_scaled_window_vertices(vertices, wwr):
    """벽면 꼭짓점과 WWR로부터 창호 꼭짓점(최대 4개)을 생성합니다.
    
    EnergyPlus FenestrationSurface:Detailed는 최대 4개 꼭짓점만 허용하므로,
    벽면이 5각형 이상이면 직사각형 근사로 창호를 생성합니다.
    """
    if not vertices or wwr <= 0: 
        return []
    
    # 4개 이하면 기존 방식 (중심 축소)
    if len(vertices) <= 4:
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
    
    # 5개 이상 꼭짓점 → 벽 평면 위에 직사각형 창호를 근사 생성
    # 벽의 법선벡터 계산
    v0 = vertices[0]
    v1 = vertices[1]
    v2 = vertices[2]
    
    edge1 = [v1[i] - v0[i] for i in range(3)]
    edge2 = [v2[i] - v0[i] for i in range(3)]
    
    # 법선 = edge1 x edge2
    normal = [
        edge1[1]*edge2[2] - edge1[2]*edge2[1],
        edge1[2]*edge2[0] - edge1[0]*edge2[2],
        edge1[0]*edge2[1] - edge1[1]*edge2[0]
    ]
    n_len = math.sqrt(sum(n*n for n in normal))
    if n_len < 1e-10:
        return []
    normal = [n/n_len for n in normal]
    
    # 벽 평면의 로컬 좌표계 구성 (U, V축)
    # U축: 첫 번째 edge 방향
    u_len = math.sqrt(sum(e*e for e in edge1))
    if u_len < 1e-10:
        return []
    u_axis = [e/u_len for e in edge1]
    
    # V축: normal x U
    v_axis = [
        normal[1]*u_axis[2] - normal[2]*u_axis[1],
        normal[2]*u_axis[0] - normal[0]*u_axis[2],
        normal[0]*u_axis[1] - normal[1]*u_axis[0]
    ]
    
    # 모든 꼭짓점을 로컬 좌표로 변환
    cx = sum(v[0] for v in vertices) / len(vertices)
    cy = sum(v[1] for v in vertices) / len(vertices)
    cz = sum(v[2] for v in vertices) / len(vertices)
    
    local_u = []
    local_v = []
    for v in vertices:
        dx, dy, dz = v[0]-cx, v[1]-cy, v[2]-cz
        local_u.append(dx*u_axis[0] + dy*u_axis[1] + dz*u_axis[2])
        local_v.append(dx*v_axis[0] + dy*v_axis[1] + dz*v_axis[2])
    
    # 로컬 좌표 바운딩 박스
    u_min, u_max = min(local_u), max(local_u)
    v_min, v_max = min(local_v), max(local_v)
    
    # WWR 비율로 축소
    scale = math.sqrt(wwr / 100.0)
    half_w = (u_max - u_min) / 2 * scale
    half_h = (v_max - v_min) / 2 * scale
    
    # 4개 직사각형 꼭짓점 (중심 기준)
    corners = [
        (-half_w, -half_h),
        ( half_w, -half_h),
        ( half_w,  half_h),
        (-half_w,  half_h),
    ]
    
    win_verts = []
    for cu, cv in corners:
        wx = cx + cu*u_axis[0] + cv*v_axis[0]
        wy = cy + cu*u_axis[1] + cv*v_axis[1]
        wz = cz + cu*u_axis[2] + cv*v_axis[2]
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
    insulation_overrides = payload.get("insulationOverrides", {})
    materials_data = payload.get("materials", {})
    
    # 💡 단열재 오버라이드 및 U-value 재계산 반영
    if insulation_overrides and materials_data:
        constr_map = {c["id"]: c for c in materials_data.get("constructions", [])}
        for s in surfaces:
            c_ref = s.get("constructionRef")
            if c_ref and c_ref in insulation_overrides:
                override = insulation_overrides[c_ref]
                c_info = constr_map.get(c_ref)
                if c_info:
                    orig_insul = None
                    for layer in c_info.get("layers", []):
                        if layer.get("isInsulation"):
                            orig_insul = layer
                            break
                    orig_u = c_info.get("uValue")
                    if orig_u is None:
                        orig_u = s.get("uValue", 0.8)
                    
                    if orig_u > 0:
                        r_total = 1.0 / orig_u
                        if orig_insul:
                            d_orig = orig_insul.get("thickness", 0.0) # mm
                            lambda_orig = orig_insul.get("conductivity", 0.04)
                            r_insul_orig = (d_orig / 1000.0) / (lambda_orig if lambda_orig else 0.04)
                        else:
                            r_insul_orig = 0.0
                            
                        r_other = max(0.01, r_total - r_insul_orig)
                        
                        new_tier = override.get("tier")
                        new_thickness = float(override.get("thickness", 0.0)) # mm
                        
                        TIER_CONDUCTIVITY = {
                            "premium": 0.025,
                            "high": 0.035,
                            "standard": 0.055,
                            "basic": 0.085
                        }
                        lambda_new = TIER_CONDUCTIVITY.get(new_tier, 0.04)
                        r_insul_new = (new_thickness / 1000.0) / lambda_new
                        r_total_new = r_other + r_insul_new
                        new_u = 1.0 / r_total_new
                        
                        s["uValue"] = round(new_u, 4)
                        print(f"🔄 [Simulation] Construction '{c_ref}' insulation override: {new_tier} ({new_thickness}mm) -> U-value {orig_u:.4f} -> {new_u:.4f}")
    
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
    
    # 재료 물성치 DB (프론트엔드와 동기화)
    STRUCT_DB = {
        'O1': {'n': 'Brickwork', 'c': 0.84, 'd': 1700, 'sh': 800},
        'O2': {'n': 'Ext_Rendering', 'c': 0.50, 'd': 1300, 'sh': 1000},
        'O3': {'n': 'Stone', 'c': 1.50, 'd': 2500, 'sh': 800},
        'O4': {'n': 'Asphalt', 'c': 0.70, 'd': 2100, 'sh': 1000},
        'O5': {'n': 'Aluminum_Panel', 'c': 200.0, 'd': 2700, 'sh': 900},
        'O6': {'n': 'Stucco', 'c': 0.72, 'd': 1850, 'sh': 840},
        'O7': {'n': 'Zinc_Panel', 'c': 110.0, 'd': 7140, 'sh': 390},
        'O8': {'n': 'Wood_Siding', 'c': 0.14, 'd': 600, 'sh': 1200},
        'O9': {'n': 'Granite', 'c': 2.80, 'd': 2600, 'sh': 1000},
        'O10': {'n': 'Steel_Panel', 'c': 50.0, 'd': 7800, 'sh': 450},
        'C1': {'n': 'Concrete', 'c': 1.13, 'd': 2000, 'sh': 1000},
        'C2': {'n': 'Concrete_Dense', 'c': 1.40, 'd': 2100, 'sh': 840},
        'C3': {'n': 'Concrete_Block', 'c': 0.51, 'd': 1400, 'sh': 1000},
        'C4': {'n': 'Timber', 'c': 0.14, 'd': 650, 'sh': 1200},
        'C5': {'n': 'Structural_Brick', 'c': 0.84, 'd': 1700, 'sh': 800},
        'C6': {'n': 'ALC_Block', 'c': 0.11, 'd': 500, 'sh': 1000},
        'C7': {'n': 'Precast_Concrete', 'c': 1.63, 'd': 2200, 'sh': 840},
        'C8': {'n': 'Light_Gauge_Steel', 'c': 50.0, 'd': 7800, 'sh': 450},
        'C9': {'n': 'Mud_Brick', 'c': 0.60, 'd': 1600, 'sh': 850},
        'I1': {'n': 'Gypsum_Board', 'c': 0.25, 'd': 900, 'sh': 1000},
        'I2': {'n': 'Plastering', 'c': 0.40, 'd': 1000, 'sh': 1000},
        'I3': {'n': 'Screed', 'c': 0.41, 'd': 1200, 'sh': 840},
        'I4': {'n': 'Wood_Panel', 'c': 0.14, 'd': 650, 'sh': 1200},
        'I5': {'n': 'Ceramic_Tile', 'c': 1.20, 'd': 2300, 'sh': 840},
        'I6': {'n': 'Plywood', 'c': 0.13, 'd': 540, 'sh': 1210},
        'I7': {'n': 'Marble', 'c': 2.80, 'd': 2600, 'sh': 800},
        'I8': {'n': 'Acoustic_Tile', 'c': 0.06, 'd': 300, 'sh': 1300},
        'I9': {'n': 'Wallpaper', 'c': 0.10, 'd': 600, 'sh': 1200}
    }
    
    # 프론트엔드는 payload 최상위에, 일부 경로에서는 projectData 안에 넣을 수 있음 → 양쪽 모두 체크
    construction_overrides = payload.get("constructionOverrides", {}) or project_data.get("constructionOverrides", {})
    print(f"🔧 construction_overrides 수신: {len(construction_overrides)}건")
    
    # 표면별 단열재 + 구조체 + 유리
    for s in surfaces:
        u_val = max(0.1, s.get("uValue", 0.8))
        c_ref = s.get("constructionRef") or s.get("constructionId")
        
        override = construction_overrides.get(s['id'])
        is_custom = override and override.get("isCustom")
        
        if is_custom and override.get("uValue"):
            u_val = max(0.1, override.get("uValue"))
            
        if is_custom:
            # 4중 레이어 커스텀 모드
            layer_names = []
            
            # 1. 외장재
            out_mat = STRUCT_DB.get(override.get("outerId"), STRUCT_DB['O1'])
            t_out = max(0.001, override.get("outerThick", 10) / 1000.0)
            mat_name_out = f"{out_mat['n']}_{s['id']}"
            idf.add_material(mat_name_out, "Smooth", t_out, out_mat['c'], out_mat['d'], out_mat['sh'])
            layer_names.append(mat_name_out)
            
            # 2. 단열재 (U-value를 맞추기 위해 역계산, 프론트에서 넘어온 두께 사용)
            t_insul = max(0.001, override.get("insulThick", 100) / 1000.0)
            # R_total = 1/U = R_film + R_out + R_insul + R_core + R_in
            r_film = 0.17
            r_out = t_out / out_mat['c']
            
            core_mat = STRUCT_DB.get(override.get("coreId"), STRUCT_DB['C1'])
            t_core = max(0.001, override.get("coreThick", 150) / 1000.0)
            r_core = t_core / core_mat['c']
            
            in_mat = STRUCT_DB.get(override.get("innerId"), STRUCT_DB['I1'])
            t_in = max(0.001, override.get("innerThick", 10) / 1000.0)
            r_in = t_in / in_mat['c']
            
            r_insul_target = (1.0 / u_val) - r_film - r_out - r_core - r_in
            c_insul = t_insul / max(0.01, r_insul_target) if r_insul_target > 0 else 0.04
            
            mat_name_insul = f"Insul_{s['id']}"
            idf.add_material(mat_name_insul, "Smooth", t_insul, c_insul, 50, 800)
            layer_names.append(mat_name_insul)
            
            # 3. 구조체
            mat_name_core = f"{core_mat['n']}_{s['id']}"
            idf.add_material(mat_name_core, "MediumRough", t_core, core_mat['c'], core_mat['d'], core_mat['sh'])
            layer_names.append(mat_name_core)
            
            # 4. 내장재
            mat_name_in = f"{in_mat['n']}_{s['id']}"
            idf.add_material(mat_name_in, "Smooth", t_in, in_mat['c'], in_mat['d'], in_mat['sh'])
            layer_names.append(mat_name_in)
            
            idf.add_construction(f"Const_{s['id']}", layer_names)
            
        else:
            # 기본 모드 (단열재만 변경 또는 원본)
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

    # 용도(Activity)별 표준 스케줄용: ActivityIdList.txt 로드 + 아키타입 op 스케줄 캐시
    activity_names = load_activity_names(db_dir)
    created_op_sch = set()

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
    
    # AirflowNetwork 기본 설정 기동
    idf.setup_airflow_network()

    # Zone별 실제 Outdoors 표면 개수 사전 계산 (AFN 최소 표면 제약 조건 해결)
    valid_zone_ids = set(z['id'].replace(" ", "_") for z in zones)
    outdoor_counts = {}
    for s in surfaces:
        z_id = s.get('zone', '').replace(" ", "_")
        if z_id == "Unknown" or z_id not in valid_zone_ids:
            continue
        
        t = s.get("type", "").lower()
        adj_zone_raw = s.get("adjacentZone")
        adj_zone_id = adj_zone_raw.replace(" ", "_") if adj_zone_raw else None
        
        if adj_zone_id and adj_zone_id in valid_zone_ids:
            continue
        else:
            if not ("interior" in t or adj_zone_raw):
                z = s.get("zone")
                if z:
                    outdoor_counts[z] = outdoor_counts.get(z, 0) + 1
    
    valid_afn_zones = set(z for z, count in outdoor_counts.items() if count >= 2)

    # 존별 설정
    for z in zones:
        z_id = z['id'].replace(" ", "_")
        z_area_list = [calculate_surface_area(s.get("vertices", [])) for s in surfaces if s.get("zone") == z['id'] and ("floor" in s.get("type", "").lower() or "slab" in s.get("type", "").lower())]
        z_area = sum(z_area_list) if sum(z_area_list) >= 1.0 else 100.0
        z_height = z.get("height", 3.0)  # 💡 Zone별 자동역산 높이 사용
        
        idf.add_zone(z_id, z_area, z_height)
        
        # AirflowNetwork Zone 등록 (외기 접촉면이 2개 이상인 Zone만 등록)
        if z['id'] in valid_afn_zones:
            idf.add("AirflowNetwork:MultiZone:Zone", [
                z_id, "Temperature", f"{z_id}_CoolSch", 0.0, 0.0, 100.0, 0.0, 300000.0, "AlwaysOn"
            ])
        
        activity = z.get("activityId", 1105)
        arch_key = classify_activity(activity_names.get(activity, ""))
        loads = get_archetype_loads(arch_key)   # 용도별 표준 부하/급탕 기본값
        heat_set = z.get("heatingSetpoint", 20.0)
        cool_set = z.get("coolingSetpoint", 26.0)

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
            # 용도(activityId) 아키타입별 표준 스케줄 (ASHRAE/DOE 프로파일)
            sched = build_schedules(arch_key, heat_set, cool_set)
            op_sch = f"Op_{arch_key}"
            if op_sch not in created_op_sch:
                idf.add_schedule_compact(op_sch, "Fraction", sched["op"])
                created_op_sch.add(op_sch)
            heat_sch_text = sched["heating"]
            cool_sch_text = sched["cooling"]

        if z.get("isConditioned", True):
            idf.add_ideal_hvac(z_id, op_sch)
            idf.add_schedule_compact(f"{z_id}_HeatSch", "AnyNumber", heat_sch_text)
            idf.add_schedule_compact(f"{z_id}_CoolSch", "AnyNumber", cool_sch_text)
            idf.add_thermostat(z_id, f"{z_id}_HeatSch", f"{z_id}_CoolSch")

        ppl_dens = z.get("peopleDensity", loads["people"])
        light_p = z.get("lightingPower", loads["lighting"])

        base_equip_p = z.get("equipmentPower", loads["equipment"])
        outlet_p = calc_outlet_power_density(z, z_area)
        load_type = z.get("outletLoadType", "sum")
        if load_type == "max":
            equip_p = max(base_equip_p, outlet_p)
        else:
            equip_p = base_equip_p + outlet_p
            
        if outlet_p > 0:
            print(f"   Zone \"{z['id']}\" 콘센트 부하 계산: 개수={z.get('outletCount')}, 면적={z_area:.1f}m², 부하량={outlet_p:.2f} W/m² (방식={load_type}) → 최종 기기부하={equip_p:.2f} W/m²")
        
        if ppl_dens > 0:
            idf.add_people(f"{z_id}_Ppl", z_id, op_sch, ppl_dens)
            # 동적 급탕(DHW) — 용도별 1인당 온수사용량(L/인·일).
            # peak_flow는 op 스케줄로 변조되므로, 일일 사용량이 맞도록 '하루 운영시간 적분'
            # 으로 나눈다 (기존엔 /3600으로 1시간 가정 → 스케줄 적분만큼 ~10배 과다였음).
            people_count = z_area * ppl_dens
            if people_count > 0:
                op_h = daily_op_hours(arch_key)
                peak_dhw_flow = people_count * (loads["dhw_lpd"] / 1000.0) / (op_h * 3600.0)  # m3/s
                idf.add_dhw(f"{z_id}_DHW", z_id, op_sch, peak_dhw_flow)
        if light_p > 0:
            idf.add_lights(f"{z_id}_Lgt", z_id, op_sch, light_p)
        if equip_p > 0:
            idf.add_equipment(f"{z_id}_Eqp", z_id, op_sch, equip_p)
        
        idf.add_infiltration(f"{z_id}_Inf", z_id)

    # 표면 지오메트리
    valid_zone_ids = set(z['id'].replace(" ", "_") for z in zones)
    skipped_count = 0
    zone_to_zone_count = 0

    for s in surfaces:
        z_id = s['zone'].replace(" ", "_")

        # 💡 Zone이 "Unknown"이거나 유효한 Zone 목록에 없으면 IDF에서 제외
        if z_id == "Unknown" or z_id not in valid_zone_ids:
            skipped_count += 1
            continue
        
        ep_type = "Wall"
        t = s.get("type", "").lower()
        if "roof" in t:
            ep_type = "Roof"
        elif "floor" in t or "slab" in t:
            ep_type = "Floor"

        verts = s.get('vertices', [])
        adj_zone_raw = s.get("adjacentZone")
        adj_zone_id = adj_zone_raw.replace(" ", "_") if adj_zone_raw else None

        # =========================================================
        # 💡 인접존 처리: Zone-to-Zone 양방향 Surface 쌍 생성
        #
        # gbXML은 공유면을 하나만 정의하지만, EnergyPlus는
        # 각 Zone이 독립적으로 해당 면을 정의하고 서로 참조해야 함.
        #
        #  원본  su5        → Zone A, boundary=Surface, obj=su5_mirror
        #  미러  su5_mirror → Zone B, boundary=Surface, obj=su5
        #                    (정점 역순 = 법선 반전)
        # =========================================================
        if adj_zone_id and adj_zone_id in valid_zone_ids:
            mirror_id = f"{s['id']}_mirror"
            mirror_verts = list(reversed(verts))  # 법선벡터 반전

            # 원본: Zone A (gbXML에서 직접 연결된 Zone)
            idf.add_surface(
                s['id'], ep_type, f"Const_{s['id']}", z_id,
                "Surface", "NoSun", "NoWind", verts,
                adj_surface_id=mirror_id
            )

            # 미러: Zone B (인접 Zone) — 동일 Construction 재사용
            idf.add_surface(
                mirror_id, ep_type, f"Const_{s['id']}", adj_zone_id,
                "Surface", "NoSun", "NoWind", mirror_verts,
                adj_surface_id=s['id']
            )
            zone_to_zone_count += 1

        else:
            # 외벽 또는 인접 Zone이 없는 내부면 → 기존 로직
            if "interior" in t or adj_zone_raw:
                # adjacentZone이 있지만 유효하지 않은 Zone → Adiabatic fallback
                obc, sun, wind = "Adiabatic", "NoSun", "NoWind"
            else:
                obc, sun, wind = "Outdoors", "SunExposed", "WindExposed"

            idf.add_surface(s['id'], ep_type, f"Const_{s['id']}", z_id,
                            obc, sun, wind, verts)

            wwr = s.get("wwr", 0)
            if ep_type == "Wall" and wwr > 0 and obc == "Outdoors":
                win_verts = get_scaled_window_vertices(verts, wwr)
                if win_verts:
                    idf.add_window(f"Win_{s['id']}", f"WinConst_{s['id']}", s['id'], win_verts)

            # AirflowNetwork Surface 및 개구부(Window) 등록
            if obc == "Outdoors" and s.get("zone") in valid_afn_zones:
                idf.add("AirflowNetwork:MultiZone:Surface", [
                    s['id'], "WallCrack", "", 1.0
                ])
                if ep_type == "Wall" and wwr > 0:
                    win_id = f"Win_{s['id']}"
                    idf.add("AirflowNetwork:MultiZone:Surface", [
                        win_id, "WindowOpening", "", 1.0,
                        "NoVent", "", 0.0, 0.0, 100.0, 0.0, 300000.0, "AlwaysOn"
                    ])

    if skipped_count > 0:
        print(f"⏭️ Zone 미소속 Surface {skipped_count}개 제외 (차양/지형면)")
    if zone_to_zone_count > 0:
        print(f"🔗 Zone-to-Zone 경계 Surface {zone_to_zone_count}개 양방향 쌍 생성 완료")

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
        target_budget = float(project_data.get('targetBudget', 0.0)) * 10000.0
        led_reduction_active = project_data.get('ledReductionActive', False)
        # 💡 hvacUpgradeActive / lccParameters는 projectData 안에 있다.
        # (payload 최상위로 보내도 SimulationPayload 모델에 없어 Pydantic이 떨궈 항상 기본값이 됨)
        hvac_upgrade_active = project_data.get('hvacUpgradeActive', False)

        lcc_parameters = project_data.get('lccParameters', {})
        
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
            act_main=act_main,
            surfaces=surfaces,
            materials=materials_data,
            construction_overrides=construction_overrides,
            target_budget=target_budget,
            led_fixture_count=sum(int(z.get('ledFixtureCount', 0)) for z in zones),
            led_reduction_active=led_reduction_active,
            hvac_upgrade_active=hvac_upgrade_active,
            discount_rate=float(lcc_parameters.get('discountRate', 5.0)) / 100.0,
            inflation_rate=float(lcc_parameters.get('inflationRate', 3.0)) / 100.0,
            utility_inflation=float(lcc_parameters.get('utilityInflation', 4.0)) / 100.0,
            lifecycle_years=int(lcc_parameters.get('lifecycleYears', 20))
        )
        return result_data

    # 시뮬레이션 실패 시 fallback 반환
    return analyzer._fallback_data()