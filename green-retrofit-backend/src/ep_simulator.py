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

from src.cost_analyzer import LCCAnalyzer, is_non_habitable
from src.activity_schedules import (
    load_activity_names, classify_activity, build_schedules, get_archetype_loads,
    daily_op_hours, cooling_compact_with_season, monthly_ground_temperatures,
)

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

# 요금·효율 상수는 cost_analyzer.LCCAnalyzer가 단일 소스다.
# (과거 이곳에 값이 다른 복제본이 있었으나 사용처가 없는 죽은 코드였음 — 재정의 금지)

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

def _weather_rank(path):
    """EPW 선택 우선순위. 값이 클수록 우선한다.

    같은 도시에 여러 관측 파일이 있을 때 알파벳 순으로 고르면 더 오래된 기간이나
    공항 관측소가 뽑힌다(대전 2007-2021, 수원·청주·여수 AP 등). 기준을 명시한다.
    """
    b = os.path.basename(path)
    m = re.search(r"TMYx\.(\d{4})-(\d{4})", b)
    end_year = int(m.group(2)) if m else 0
    is_ws = 1 if ".WS." in b else 0     # 관측소 > 공항
    return (end_year, is_ws)


def compute_zone_floor_areas(zones, surfaces):
    """존별 바닥면적을 한 번만 계산해 돌려준다. {zone_id: area}

    이 값이 내부발열(조명·기기·인체)을 주입하는 기준면적이자, 면적당 지표의
    분모다. 예전에는 두 곳에서 따로 계산했고 폴백 때문에 서로 어긋났다 —
    바닥 폴리곤이 없는 존은 천장/지붕 면적으로 대체되는데 그 면적은 전체
    floor/slab 합에는 없어서, 내부발열은 1,050㎡ 기준으로 넣고 지표는 964㎡로
    나누는 9% 불일치가 생겼다. 한 곳에서 계산해 양쪽이 같은 값을 쓰게 한다.
    """
    areas = {}
    for z in zones:
        zid = z['id']
        # gbXML이 선언한 면적이 있으면 그것이 단일 기준이다. 기하 합산은 층간
        # 슬래브가 space_1 존에만 귀속되는 탓에 아래층은 바닥+천장을 이중 계산하고
        # 최상층은 바닥을 못 받는다 (101 화장실 24.85 vs 선언 11.22).
        declared = z.get("declaredArea") or 0.0
        if declared > 0:
            areas[zid] = declared
            continue
        # 선언 면적이 없으면 **파서가 계산한 값**을 쓴다. 여기서 다시 계산하면
        # 파서는 층간면 귀속을 보정한 값(101 화장실 12.42)을 쓰는데 시뮬레이터는
        # 귀속된 면을 단순 합산해(24.84) 두 값이 갈린다.
        parsed = z.get("geometricArea") or z.get("area") or 0.0
        if parsed > 0:
            areas[zid] = parsed
            continue
        z_area = sum(
            calculate_surface_area(s.get("vertices", []))
            for s in surfaces
            if s.get("zone") == zid
            and ("floor" in s.get("type", "").lower() or "slab" in s.get("type", "").lower())
        )
        if z_area < 1.0:
            # 바닥 폴리곤이 없거나 퇴화된 존(샤프트·설비존, 바닥면 누락 화장실 등):
            # 천장/지붕 면적으로 대체하고, 그래도 없으면 1㎡ 하한만 적용.
            # 기존 100㎡ 고정 폴백은 실면적 ~5㎡ 존에 100㎡분 내부발열을 주입해
            # 한겨울에도 냉방이 도는 왜곡을 만들었음 (1월 냉방 버그).
            ceil_area = sum(
                calculate_surface_area(s.get("vertices", []))
                for s in surfaces
                if s.get("zone") == zid
                and ("ceiling" in s.get("type", "").lower() or "roof" in s.get("type", "").lower())
            )
            z_area = max(z_area, ceil_area, 1.0)
        areas[zid] = z_area
    return areas


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

# ── 실기기 성능 매핑 (사용자 입력 등급/연식 → 물리 파라미터) ──
# 냉방 COP: 에너지소비효율등급(신형) + 노후 성능저하(냉매 열화·열교환기 오염) 반영
COOLING_COP_BY_GRADE = {
    "grade1": 4.0,   # 1등급 신형
    "grade3": 3.3,   # 일반(3등급) — 미입력 기본값(기존 WINDOW_AC_COP와 동일)
    "grade5": 2.9,   # 5등급
    "old10":  2.6,   # 10년 노후
    "old15":  2.2,   # 15년 이상 노후
}
# PTHP(히트펌프)용 (냉방COP, 난방COP) — 창문형보다 높은 기저 효율
PTHP_COP_BY_GRADE = {
    "grade1": (4.8, 4.1),
    "grade3": (4.2, 3.5),   # 기본값(기존과 동일)
    "grade5": (3.7, 3.1),
    "old10":  (3.2, 2.6),
    "old15":  (2.7, 2.2),
}
# 난방기(보일러) 연식 → 효율 보정 계수 (버너 열화·스케일 침착)
HEATING_EFF_FACTOR_BY_AGE = {"new": 1.0, "mid": 0.93, "old": 0.85}
# 에어컨 '평형' → 냉방능력 kW (예: 6평형 ≈ 2.3kW)
PYEONG_TO_KW = 0.383


def resolve_hvac_equipment(project_data: dict) -> dict:
    """projectData.hvacEquipment(사용자 입력) → 물리 파라미터. 미입력 시 현행 기본값.

    hvacUpgradeActive(설비 교체 토글)가 켜지면 개선 후 모델은 1등급 신형 성능
    (COP 4.0 / PTHP 4.8·4.1, 보일러 신형 효율)으로 돌아간다 — 노후 설비 건물의
    설비 교체 리트로핏 효과를 에너지에 반영. 기준선(개선 전) 실행은 이 플래그가
    제거된 payload로 돌므로 원래 노후 성능을 유지한다.
    """
    eq = project_data.get("hvacEquipment") or {}
    cooling_grade = eq.get("coolingGrade") or "grade3"
    heating_age = eq.get("heatingAge") or "new"
    if cooling_grade not in COOLING_COP_BY_GRADE:
        cooling_grade = "grade3"
    if heating_age not in HEATING_EFF_FACTOR_BY_AGE:
        heating_age = "new"

    upgraded = bool(project_data.get("hvacUpgradeActive"))
    if upgraded:
        cooling_grade = "grade1"
        heating_age = "new"

    return {
        "cooling_grade": cooling_grade,
        "heating_age": heating_age,
        "cool_cop": COOLING_COP_BY_GRADE[cooling_grade],
        "pthp_cops": PTHP_COP_BY_GRADE[cooling_grade],
        "heat_factor": HEATING_EFF_FACTOR_BY_AGE[heating_age],
        "is_user_input": bool(eq.get("coolingGrade") or eq.get("heatingAge")),
        "upgraded": upgraded,   # 설비 교체 토글 반영 여부 (UI 표기용)
    }


def zone_cooling_plan(zone: dict, default_capacity_w: float) -> dict:
    """존별 냉방기 설치 계획: 사용자 오버라이드 > 자동(비거주 제외).

    zone.coolingInstalled: 'yes' | 'no' | 그 외/'auto'(자동)
    zone.coolingCapacityPyeong: 평형 입력 시 실기기 용량으로 사용
    """
    override = (zone.get("coolingInstalled") or "auto").lower()
    if override == "no":
        return {"installed": False, "capacity_w": 0.0, "source": "user"}
    if override == "yes":
        installed = True
        source = "user"
    else:
        installed = not is_non_habitable(zone)
        source = "auto"
    capacity_w = default_capacity_w
    try:
        pyeong = float(zone.get("coolingCapacityPyeong") or 0)
    except (TypeError, ValueError):
        pyeong = 0.0
    if pyeong > 0:
        capacity_w = pyeong * PYEONG_TO_KW * 1000.0
        source = "user"
    return {"installed": installed, "capacity_w": capacity_w, "source": source}


def build_window_geometries(surface: dict, wall_verts: list) -> list:
    """벽면의 창 형상 목록 생성 — 실측 opening 우선.

    규칙(정확도·안전성 순):
    1) gbXML opening 실좌표가 있고 WWR 미수정 → 실형상 그대로 (위치·개수·모양 보존)
    2) 실좌표가 있고 WWR을 원본보다 '축소' → 각 창을 자기 중심으로 축소 (벽 안 보장)
    3) 실좌표가 없거나 WWR을 '확대' → 기존 합성 창(벽 중앙 √WWR) 폴백
       (실형상 확대는 벽 경계를 벗어나 E+ Severe를 유발할 수 있어 폴백이 안전)
    """
    wwr = surface.get("wwr", 0)
    if not wwr or wwr <= 0:
        return []

    openings = [op for op in (surface.get("openings") or [])
                if (op.get("type") or "").lower() != "air"
                and len(op.get("vertices", [])) >= 3]
    if not openings:
        wv = get_scaled_window_vertices(wall_verts, wwr)
        return [wv] if wv else []

    wall_area = calculate_surface_area(wall_verts)
    orig_area = sum(calculate_surface_area(op["vertices"]) for op in openings)
    if wall_area <= 0 or orig_area <= 0:
        wv = get_scaled_window_vertices(wall_verts, wwr)
        return [wv] if wv else []

    orig_pct = orig_area / wall_area * 100.0
    # 파서는 wwr=int(원본비율)로 저장 → 1.5%p 이내 차이는 '미수정'으로 간주
    if wwr > orig_pct + 1.5:
        wv = get_scaled_window_vertices(wall_verts, wwr)   # 확대 → 합성 폴백
        return [wv] if wv else []

    scale2 = 100.0 if abs(wwr - orig_pct) <= 1.5 else (wwr / orig_pct) * 100.0

    result = []
    for op in openings:
        ov = op["vertices"]
        if len(ov) <= 4:
            # 중심 축소(scale²=wwr 인자). 100.0이면 원형 유지
            wv = ov if scale2 >= 100.0 else get_scaled_window_vertices(ov, scale2)
        else:
            # E+는 창 꼭짓점 4개 제한 → 동일 면적의 직사각형 근사
            bbox = get_scaled_window_vertices(ov, 100.0)
            bbox_area = calculate_surface_area(bbox)
            op_area = calculate_surface_area(ov)
            eff = min((op_area * (scale2 / 100.0)) / bbox_area * 100.0, 100.0) if bbox_area > 0 else scale2
            wv = get_scaled_window_vertices(ov, eff)
        if wv:
            result.append(wv)
    return result


def _build_variant_payload(payload: dict, rec_type: str):
    """비용 절감 추천 1건을 적용한 시뮬레이션 페이로드 생성.

    프론트(utils/recommendationActions.js)의 적용 규칙과 동일해야 '적용 시 실제 차액'
    원칙이 유지된다. 열모델이 바뀌지 않는 대안(hvac 표준 하향·hvac_scope·led)은
    None을 반환한다 — 에너지 변화가 모델에 없으므로 재시뮬레이션이 무의미하다.
    """
    import copy
    project_data = payload.get("projectData", {}) or {}

    if rec_type == "window":
        surfaces = copy.deepcopy(payload.get("surfaces", []))
        changed = 0
        for s in surfaces:
            has_glass = (
                s.get("type") in ("Window", "Skylight")
                or s.get("glazingId") is not None
                or ((s.get("wwr") or 0) > 0 and "wall" in (s.get("type") or "").lower())
            )
            if has_glass and s.get("glazingId") != 42:
                s["glazingId"] = 42  # 일반 복층 유리로 하향 (glazingId가 windowU보다 우선)
                changed += 1
        if not changed:
            return None
        v = dict(payload)
        v["surfaces"] = surfaces
        return v

    if rec_type == "insulation":
        surfaces = copy.deepcopy(payload.get("surfaces", []))
        materials = payload.get("materials", {}) or {}
        constructions = {c.get("id"): c for c in materials.get("constructions", [])}
        overrides = copy.deepcopy(payload.get("constructionOverrides", {}) or {})
        insul_overrides = {}
        changed = 0
        for s in surfaces:
            s_id = s.get("id")
            c_ref = s.get("constructionRef") or s.get("constructionId")
            ov = overrides.get(s_id)
            if ov and ov.get("tier") in ("premium", "high"):
                t = ov.get("thickness", 100)
                overrides[s_id] = {"insulationId": 1, "tier": "standard", "thickness": t}
                if c_ref:
                    # λ0.036 = 실제 적용 제품(비드법 1종 1호) — tier 대표값(0.055)이 아닌 제품 물성
                    insul_overrides[c_ref] = {"tier": "standard", "thickness": t, "conductivity": 0.036}
                changed += 1
            elif not ov and c_ref in constructions:
                insul = next((l for l in constructions[c_ref].get("layers", [])
                              if l.get("isInsulation")), None)
                if insul and (insul.get("conductivity") or 1.0) <= 0.045:
                    t = insul.get("thickness") or 100
                    overrides[s_id] = {"insulationId": 1, "tier": "standard", "thickness": t}
                    insul_overrides[c_ref] = {"tier": "standard", "thickness": t, "conductivity": 0.036}
                    changed += 1
        if not changed:
            return None
        v = dict(payload)
        v["surfaces"] = surfaces
        v["constructionOverrides"] = overrides
        # insulationOverrides는 시뮬 진입부에서 c_ref 기준으로 U값을 재계산해 준다
        v["insulationOverrides"] = insul_overrides
        return v

    if rec_type == "hvac" and project_data.get("geothermalApplied"):
        v = dict(payload)
        pd2 = dict(project_data)
        pd2["geothermalApplied"] = False
        v["projectData"] = pd2
        return v

    # ── 상향(성능 개선) 변형 — 전부 열모델이 바뀌므로 재시뮬레이션 필수 ──
    if rec_type == "hvac_upgrade":
        if project_data.get("hvacUpgradeActive"):
            return None
        v = dict(payload)
        pd2 = dict(project_data)
        pd2["hvacUpgradeActive"] = True   # resolve_hvac_equipment가 1등급 신형 COP로 전환
        v["projectData"] = pd2
        return v

    if rec_type == "window_upgrade":
        # 일반 복층 → 고성능 Low-E+Ar 복층 (ID 154, U 1.32/SHGC 0.34)
        surfaces = copy.deepcopy(payload.get("surfaces", []))
        changed = 0
        for s in surfaces:
            has_glass = (
                s.get("type") in ("Window", "Skylight")
                or s.get("glazingId") is not None
                or ((s.get("wwr") or 0) > 0 and "wall" in (s.get("type") or "").lower())
            )
            if has_glass and s.get("glazingId") != 154:
                s["glazingId"] = 154
                changed += 1
        if not changed:
            return None
        v = dict(payload)
        v["surfaces"] = surfaces
        return v

    if rec_type == "insulation_upgrade":
        # 일반/저성능 단열(λ>0.045) → 중성능(high, λ0.035, 비드법 1종 2호 id 2)
        surfaces = copy.deepcopy(payload.get("surfaces", []))
        materials = payload.get("materials", {}) or {}
        constructions = {c.get("id"): c for c in materials.get("constructions", [])}
        overrides = copy.deepcopy(payload.get("constructionOverrides", {}) or {})
        insul_overrides = {}
        changed = 0
        for s in surfaces:
            s_id = s.get("id")
            c_ref = s.get("constructionRef") or s.get("constructionId")
            ov = overrides.get(s_id)
            if ov and ov.get("tier") in ("standard", "basic"):
                t = ov.get("thickness", 100)
                overrides[s_id] = {"insulationId": 2, "tier": "high", "thickness": t}
                if c_ref:
                    # λ0.031 = 실제 적용 제품(비드법 1종 2호) — 프론트 적용과 동일 물성
                    insul_overrides[c_ref] = {"tier": "high", "thickness": t, "conductivity": 0.031}
                changed += 1
            elif not ov and c_ref in constructions:
                insul = next((l for l in constructions[c_ref].get("layers", [])
                              if l.get("isInsulation")), None)
                if insul and (insul.get("conductivity") or 0) > 0.045:
                    t = insul.get("thickness") or 100
                    overrides[s_id] = {"insulationId": 2, "tier": "high", "thickness": t}
                    insul_overrides[c_ref] = {"tier": "high", "thickness": t, "conductivity": 0.031}
                    changed += 1
        if not changed:
            return None
        v = dict(payload)
        v["surfaces"] = surfaces
        v["constructionOverrides"] = overrides
        v["insulationOverrides"] = insul_overrides
        return v

    return None


def _evaluate_alternatives(payload: dict, result_data: dict, temp_dir: str, stage_fn):
    """추천 대안별 정량 영향(kWh/㎡·운영비·LCC 순효과) 산출.

    열모델이 바뀌는 대안(창호·단열 하향, 지열 해제)은 EnergyPlus를 실제로 재실행해
    소요량과 요금 변화를 계산하고, 비용만 바뀌는 대안은 에너지 delta 0으로 표기한다.
    각 recommendation에 impact 블록을 붙인다 (financial과 result.financial은 동일 객체
    이므로 여기서의 변형이 응답 양쪽에 반영된다).
    """
    fin = result_data.get("financial", {})
    recs = fin.get("recommendations") or []
    if not recs:
        return
    base_summary = result_data.get("summary", {})
    base_bill = fin.get("total_energy_bill") or 0
    base_capital = fin.get("capital_cost") or 0
    lccp = fin.get("lcc_parameters", {})
    dr = (lccp.get("discount_rate") or 5.0) / 100.0
    ui = (lccp.get("utility_inflation") or 4.0) / 100.0
    years = int(lccp.get("lifecycle_years") or 20)

    def _net_effect(saved_cost, bill_delta):
        # 대안 적용의 분석기간 순효과 = 공사비 절감 − 운영비 증가분의 현재가치 합.
        # 양수면 하향해도 경제적으로 이득, 음수면 절감액보다 운영비 손실이 크다.
        pv_extra = sum(bill_delta * ((1 + ui) ** y) / ((1 + dr) ** y)
                       for y in range(1, years + 1))
        return int(saved_cost - pv_extra)

    for rec in recs:
        variant = _build_variant_payload(payload, rec.get("type", ""))
        if variant is None:
            # 열모델 불변 — 시뮬레이션상 에너지 변화 없음 (LED 조명 효과 등은 미모델 → performance_note로 고지)
            rec["impact"] = {
                "simulated": False,
                "delta_kwh_m2": 0.0,
                "annual_bill_delta": 0,
                "net_effect": int(rec.get("saved_cost", 0)),
                "lifecycle_years": years,
            }
            continue

        variant["_variantOf"] = rec["type"]
        variant.pop("baselineModel", None)  # 대안 평가에 전-시뮬 불필요 (기준은 현재 개선안)
        stage_fn(f"alt:{rec['type']}")
        print(f"🔀 [대안 평가] '{rec['title']}' 적용 모델 재시뮬레이션 시작...")
        try:
            vres = generate_idf_and_simulate(
                variant, os.path.join(temp_dir, f"alt_{rec['type']}"))
        except Exception as e:
            # 대안 평가 실패가 본 결과를 막으면 안 됨 — 정량 영향만 생략하고 정성 주석 유지
            print(f"⚠️ [대안 평가] '{rec['type']}' 재시뮬레이션 실패 → 정량 영향 생략: {e}")
            continue

        v_sum = vres.get("summary", {})
        v_fin = vres.get("financial", {})
        bill_delta = int((v_fin.get("total_energy_bill") or 0) - base_bill)
        capital_delta = int((v_fin.get("capital_cost") or 0) - base_capital)
        # 단순 회수기간: 공사비가 늘고 운영비가 줄 때만 의미 (상향 대안의 핵심 지표)
        payback_years = (round(capital_delta / (-bill_delta), 1)
                         if bill_delta < 0 and capital_delta > 0 else None)
        rec["impact"] = {
            "payback_years": payback_years,
            "simulated": True,
            "consume_per_m2": v_sum.get("consume_per_m2"),
            "delta_kwh_m2": round((v_sum.get("consume_per_m2") or 0)
                                  - (base_summary.get("consume_per_m2") or 0), 1),
            "co2_delta": round((v_sum.get("co2_per_m2") or 0)
                               - (base_summary.get("co2_per_m2") or 0), 2),
            "annual_bill_delta": bill_delta,
            "capital_delta": capital_delta,
            # 순효과는 자재 단가 차액(saved_cost)이 아닌 '실제 총공사비 변화' 기준.
            # 예: 창호 하향 → 열손실 증가 → 피크부하·설비 용량 증가 → 설비비 상승까지
            # 재시뮬레이션이 잡아내므로, saved_cost보다 -capital_delta가 정직한 절감액이다.
            "net_effect": _net_effect(-capital_delta, bill_delta),
            "lifecycle_years": years,
        }
        # 순효과가 음수면 '비권장' — 시스템이 손해로 판명한 대안을 그대로 제안하면
        # 사용자가 적용 → 반대 대안 제안 → 재적용의 핑퐁에 빠진다. 예산 제약 시에만 고려하도록 명시.
        rec["advisable"] = rec["impact"]["net_effect"] >= 0
        print(f"✅ [대안 평가] '{rec['title']}': ΔkWh/㎡ {rec['impact']['delta_kwh_m2']:+.1f}, "
              f"운영비 {bill_delta:+,}원/년, {years}년 순효과 {rec['impact']['net_effect']:+,}원"
              f"{'' if rec['advisable'] else ' → 비권장(장기 손해)'}")


def generate_idf_and_simulate(payload: dict, temp_dir: str, on_stage=None):
    project_data = payload.get("projectData", {})
    zones = payload.get("zones", [])
    surfaces = payload.get("surfaces", [])

    def _stage(name):
        if on_stage:
            try:
                on_stage(name)
            except Exception:
                pass   # 진행 표시 실패가 시뮬레이션을 막으면 안 됨

    # ── 전/후 비교: 업로드 원본(개선 전)을 별도 시뮬레이션해 물리 기반 기준선 산출 ──
    # 실측 요금/사용량이 입력됐으면 그쪽이 더 정확한 기준선이므로 전-시뮬은 생략(시간 절약).
    baseline_result = None
    baseline_same = False
    baseline_model = payload.get("baselineModel") or {}
    _ba = project_data.get("baselineActual") or {}

    def _is_pos(v):
        try:
            return float(v) > 0
        except (TypeError, ValueError):
            return False

    has_actuals = any(_is_pos(_ba.get(k)) for k in ("elecBill", "heatBill", "elecKwh", "heatKwh"))

    if baseline_model.get("zones") and baseline_model.get("surfaces") and not has_actuals:
        # 편집이 전혀 없으면(전=후) 시뮬 1회 낭비 + '×1.6 추정 절감' 착시 대신
        # '동일 모델 → 절감 0'으로 정직하게 처리
        baseline_same = (
            baseline_model["zones"] == zones
            and baseline_model["surfaces"] == surfaces
            and not payload.get("constructionOverrides")
            and not project_data.get("pvCapacity")
            and not project_data.get("geothermalApplied")
            and not project_data.get("ledReductionActive")
            and not project_data.get("hvacExcludeNonHabitable")
            and not project_data.get("hvacUpgradeActive")
        )
        if baseline_same:
            print("⏮️ [전/후 비교] 개선 전후 모델 동일 → 전-시뮬 생략 (절감 0으로 처리)")
        else:
            print("⏮️ [전/후 비교] 개선 전(업로드 원본) 건물 시뮬레이션 시작...")
            _stage("baseline")
            base_project = dict(project_data)
            # 리모델링 요소 제거 — 기존 건물엔 PV·지열·LED 축소·설비 범위 조정이 없다
            for k in ("pvCapacity", "geothermalApplied", "ledReductionActive",
                      "hvacExcludeNonHabitable", "hvacUpgradeActive", "constructionOverrides"):
                base_project.pop(k, None)
            base_payload = {
                "projectData": base_project,
                "zones": baseline_model["zones"],
                "surfaces": baseline_model["surfaces"],
                "materials": payload.get("materials", {}),
                "constructionOverrides": {},
                "_variantOf": "baseline",  # 기준선 실행은 자기 대안 평가를 돌지 않는다
            }
            baseline_result = generate_idf_and_simulate(base_payload, os.path.join(temp_dir, "baseline"))
            print("⏮️ [전/후 비교] 개선 전 시뮬레이션 완료 → 기준선으로 사용")
    _stage("retrofit")
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
                        # 제품 λ가 명시되면 tier 대표값 대신 사용 — 실제 적용 제품
                        # (예: 비드법 1종 1호 λ0.036)과 재시뮬레이션 U가 일치해야
                        # '약속 = 실제 차액' 원칙이 에너지에서도 유지된다.
                        lambda_new = (float(override["conductivity"])
                                      if override.get("conductivity")
                                      else TIER_CONDUCTIVITY.get(new_tier, 0.04))
                        r_insul_new = (new_thickness / 1000.0) / lambda_new
                        r_total_new = r_other + r_insul_new
                        new_u = 1.0 / r_total_new
                        
                        s["uValue"] = round(new_u, 4)
                        print(f"🔄 [Simulation] Construction '{c_ref}' insulation override: {new_tier} ({new_thickness}mm) -> U-value {orig_u:.4f} -> {new_u:.4f}")
    
    pv_capacity_kw = project_data.get("pvCapacity", 0)
    is_geothermal = project_data.get("geothermalApplied", False)
    location_key = project_data.get("location", "KOR_SO_Seoul")
    
    # 존별 바닥면적 — 내부발열 주입 기준이자 면적당 지표의 분모. 반드시 같은 값을 써야 한다.
    zone_floor_areas = compute_zone_floor_areas(zones, surfaces)
    calculated_floor_area = sum(zone_floor_areas.values())

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
    for s in surfaces:
        s_area = calculate_surface_area(s.get("vertices", []))
        wwr = s.get("wwr", 0)
        s_type = s.get("type", "").lower()

        if "wall" in s_type or "roof" in s_type:
            total_wall_area += s_area
            if "wall" in s_type and wwr > 0:
                total_window_area += s_area * (wwr / 100.0)

    temp_dir_abs = os.path.abspath(temp_dir)
    os.makedirs(temp_dir_abs, exist_ok=True)

    
    # 💡 [핵심 경로 수정] 데이터 폴더 탐색: 환경변수 우선, 없으면 상위 폴더에서 _data 탐색
    db_dir = os.environ.get("GBXML_DATA_DIR", "")
    if not db_dir or not os.path.isdir(db_dir):
        search_ptr = os.path.dirname(os.path.abspath(__file__))
        db_dir = ""
        for _ in range(5):
            potential = os.path.join(search_ptr, "_data")
            if os.path.isdir(potential):
                db_dir = potential
                break
            search_ptr = os.path.dirname(search_ptr)

    if not db_dir:
        raise RuntimeError(
            "_data 폴더를 찾을 수 없습니다. 프로젝트 루트에 _data를 두거나 "
            "GBXML_DATA_DIR 환경변수로 경로를 지정하세요."
        )
    
    GLAZING_DB = load_databases(db_dir)

    # 창호 속성: 우선순위 = 사용자 튜닝 glazingId → gbXML 실측 windowU → 기본(일반 이중유리 42)
    _DEFAULT_GLZ = GLAZING_DB.get(42, {"u": 2.74, "shgc": 0.60})

    def _window_ushgc(s):
        gid = s.get("glazingId")
        if gid:
            g = GLAZING_DB.get(gid)
            if g:
                return g["u"], g["shgc"]
        if s.get("windowU") is not None:
            return s["windowU"], s.get("windowShgc", _DEFAULT_GLZ["shgc"])
        return _DEFAULT_GLZ["u"], _DEFAULT_GLZ["shgc"]

    # 건물 대표 창호 U/SHGC(창 면적가중) — 비용 등급 매칭용. 기존엔 대표 glazingId 1개로
    # 잡아 모든 건물이 동일 창호로 계상되던 문제를 면적가중 실측값으로 교체.
    _win_u_sum = 0.0
    _win_shgc_sum = 0.0
    for s in surfaces:
        if "wall" in s.get("type", "").lower() and s.get("wwr", 0) > 0:
            win_area = calculate_surface_area(s.get("vertices", [])) * (s["wwr"] / 100.0)
            wu, wsh = _window_ushgc(s)
            _win_u_sum += wu * win_area
            _win_shgc_sum += wsh * win_area
    if total_window_area > 0:
        target_u = round(_win_u_sum / total_window_area, 4)
        target_shgc = round(_win_shgc_sum / total_window_area, 4)
    else:
        target_u = _DEFAULT_GLZ["u"]
        target_shgc = _DEFAULT_GLZ["shgc"]
    
    # 💡 [날씨 파일 자동 탐색] — _data/weather 우선, 없으면 _data 전체.
    # (예전처럼 프로젝트 루트 전체를 걸으면 node_modules/.git까지 매 요청마다 순회하게 됨)
    weather_dir = os.path.join(db_dir, "weather")
    search_root = weather_dir if os.path.isdir(weather_dir) else db_dir

    epw_files = []
    for root_walk, dirs, files in os.walk(search_root):
        for f in files:
            if f.lower().endswith('.epw'):
                epw_files.append(os.path.join(root_walk, f))
    epw_files.sort()  # 동일 조건 다중 매칭 시 선택이 순회 순서에 좌우되지 않도록 고정

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
            # 여러 파일이 걸리면 알파벳 순이 아니라 명시적 기준으로 고른다.
            #   1) 최신 TMYx 기간 (대전은 2007-2021 과 2009-2023 이 함께 있다)
            #   2) 공항(AP)보다 관측소(WS) — 도시 대표 기상에 가깝다
            matched.sort(key=_weather_rank, reverse=True)
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

    # 지중온도 — 없으면 EnergyPlus 가 연중 18℃ 를 가정한다. Ground 경계면의 열손실이
    # 여기에 전적으로 좌우되므로 가정을 코드에 명시한다. 존별 설정온도가 제각각일 수
    # 있으므로 대표값(최빈 설정온도)으로 계산한다.
    _heat_sp = [z.get("heatingSetpoint") for z in zones if z.get("heatingSetpoint")]
    _cool_sp = [z.get("coolingSetpoint") for z in zones if z.get("coolingSetpoint")]
    _gt = monthly_ground_temperatures(
        heat_setpoint=max(set(_heat_sp), key=_heat_sp.count) if _heat_sp else 20.0,
        cool_setpoint=max(set(_cool_sp), key=_cool_sp.count) if _cool_sp else 26.0,
    )
    idf.add_ground_temperatures(_gt)
    print(f"🌡️ 지중온도(슬래브 하부 가정, 실내−2K): {_gt[0]}~{max(_gt)}℃")
    
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
            # 창호 U/SHGC: glazingId(튜닝) → 실측 windowU → 기본. 에너지·비용을 동일 기준으로.
            wu, wsh = _window_ushgc(s)
            idf.add_glazing_simple(f"Glass_{s['id']}", wu, wsh)
            idf.add_construction(f"WinConst_{s['id']}", [f"Glass_{s['id']}"])

    # 스케줄
    idf.add_standard_schedules()

    # 용도(Activity)별 표준 스케줄용: ActivityIdList.txt 로드 + 아키타입 op 스케줄 캐시
    activity_names = load_activity_names(db_dir)
    created_op_sch = set()

    # ── 실기기 HVAC 모드 선택 ──
    # 전기 열원(2)/지열 → PTHP(히트펌프 실기기, 실소비+COP)
    # 가스(1)/등유(4)/지역난방(11) → UnitHeater(연료 보일러 실기기) + WindowAC(개별 냉방 DX)
    #   연료 소비가 Heating:<연료> 미터로 산출돼 COP 나눗셈 근사를 대체한다.
    #   지역난방은 OtherFuel1 + 효율 0.95(열교환 손실)로 모델링.
    # 매핑 불가한 열원만 이상부하 폴백.
    FUEL_SYSTEMS = {
        1:  ("NaturalGas", 0.87),   # 가스보일러 (콘덴싱 반영 평균 효율)
        4:  ("FuelOilNo2", 0.83),   # 등유보일러
        11: ("OtherFuel1", 0.95),   # 지역난방 (열교환 손실)
    }
    _heat_src_id = int(project_data.get("heatSource", 11))
    use_pthp = bool(is_geothermal or _heat_src_id == 2)
    fuel_type, fuel_eff = FUEL_SYSTEMS.get(_heat_src_id, (None, None)) if not use_pthp else (None, None)
    use_fuel_system = fuel_type is not None
    hvac_mode = "pthp" if use_pthp else ("fuel" if use_fuel_system else "ideal")

    # 사용자 입력 실기기(등급/연식) → COP·효율. 미입력이면 기존 기본값과 동일.
    equip = resolve_hvac_equipment(project_data)
    window_ac_cop = equip["cool_cop"]
    if use_fuel_system:
        fuel_eff = round(fuel_eff * equip["heat_factor"], 3)   # 보일러 연식 열화 반영
    # 지열은 신설 전제(고정 COP), 일반 히트펌프는 등급/연식 반영
    pthp_ccop, pthp_hcop = (5.0, 4.5) if is_geothermal else equip["pthp_cops"]
    if equip["is_user_input"]:
        print(f"🎛️ 실기기 입력: 냉방 {equip['cooling_grade']}(COP {window_ac_cop}), "
              f"난방 연식 {equip['heating_age']}(계수 {equip['heat_factor']})")
    if hvac_mode in ("pthp", "fuel"):
        idf.enable_sizing()   # 실기기 autosize용 사이징 활성화(1회)
    if use_fuel_system:
        # 연료 미터 출력 (해당 연료만 — 없는 미터는 경고 유발)
        idf.add("Output:Meter", [f"Heating:{fuel_type}", "Hourly"])
    _mode_label = {"pthp": "PTHP 실기기(전기/지열)",
                   "fuel": f"연료 보일러+개별냉방 실기기({fuel_type}, 효율 {fuel_eff})",
                   "ideal": "이상부하(폴백)"}[hvac_mode]
    print(f"🌀 HVAC 모드: {_mode_label} (heatSource={_heat_src_id}, geo={is_geothermal})")

    # 적용된 설비 내역 — 결과 화면 '설비 내역' 패널용 (입력값/자동 추정 구분)
    equipment_log = []
    fuel_label = {"NaturalGas": "가스보일러", "FuelOilNo2": "등유보일러",
                  "OtherFuel1": "지역난방"}.get(fuel_type, fuel_type or "")

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
            if not ("interior" in t or adj_zone_raw or s.get("selfAdjacent")):
                z = s.get("zone")
                if z:
                    outdoor_counts[z] = outdoor_counts.get(z, 0) + 1
    
    valid_afn_zones = set(z for z, count in outdoor_counts.items() if count >= 2)

    # 존별 설정
    for z in zones:
        z_id = z['id'].replace(" ", "_")
        # total_area 와 같은 출처를 쓴다 — 여기서 다시 계산하면 분모와 어긋난다.
        z_area = zone_floor_areas[z['id']]
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
            
            # 24시간 커스텀 스케줄도 연중 상시 적용 시 냉방기간 밖(11~4월)에 냉방이
            # 발생한다 — 표준 스케줄과 동일하게 냉방기간(5~10월) 밖은 미가동 처리.
            # (공휴일 프로파일은 별도 인자가 없는 cooling_compact_with_season 특성상
            #  평일/주말 배열만 전달 — 공휴일은 주말 프로파일로 근사)
            cool_wd_day = profiles.get("weekday", {}).get("cooling", [30]*24)
            cool_we_day = profiles.get("weekend", {}).get("cooling", [30]*24)
            cool_sch_text = cooling_compact_with_season(cool_wd_day, cool_we_day)
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
            if use_pthp:
                idf.add_zone_sizing(z_id)
                idf.add_pthp(z_id, cooling_cop=pthp_ccop, heating_cop=pthp_hcop,
                             op_schedule=op_sch)
                equipment_log.append({
                    "zone": z['id'],
                    "heating": f"{'지열 ' if is_geothermal else ''}히트펌프 난방 · COP {pthp_hcop}",
                    "cooling": f"히트펌프 냉방 · COP {pthp_ccop} (용량 자동산정)",
                    "source": "user" if equip["is_user_input"] else "auto",
                })
            elif use_fuel_system:
                idf.add_zone_sizing(z_id)
                idf.add_unit_heater(z_id, fuel_type=fuel_type, efficiency=fuel_eff,
                                    op_schedule=op_sch)
                # 냉방기 설치: 사용자 오버라이드 > 자동(비거주 제외).
                # 용량 기본은 면적 기반 명시값(150W/㎡, 최소 600W — 냉방부하 0존의
                # autosize=0 Fatal 방지), 평형 입력 시 실기기 용량 사용.
                plan = zone_cooling_plan(z, default_capacity_w=max(z_area * 150.0, 600.0))
                if plan["installed"]:
                    idf.add_window_ac(z_id, cooling_cop=window_ac_cop,
                                      cooling_capacity_w=plan["capacity_w"],
                                      op_schedule=op_sch)
                equipment_log.append({
                    "zone": z['id'],
                    "heating": f"{fuel_label} 난방기 (효율 {fuel_eff})",
                    "cooling": (f"에어컨 {plan['capacity_w']/1000.0:.1f}kW · COP {window_ac_cop}"
                                if plan["installed"] else "냉방 없음"),
                    "source": plan["source"],
                })
            else:
                idf.add_ideal_hvac(z_id, op_sch)
                equipment_log.append({
                    "zone": z['id'],
                    "heating": "이상부하(간이 모델)", "cooling": "이상부하(간이 모델)",
                    "source": "auto",
                })
            idf.add_schedule_compact(f"{z_id}_HeatSch", "AnyNumber", heat_sch_text)
            idf.add_schedule_compact(f"{z_id}_CoolSch", "AnyNumber", cool_sch_text)
            idf.add_thermostat(z_id, f"{z_id}_HeatSch", f"{z_id}_CoolSch")

        # 키가 있어도 값이 None 이면 '미지정'으로 보고 용도별 기본값을 쓴다.
        # z.get(k, default) 는 키가 존재하면 None 을 그대로 돌려주므로 방어가 필요하다.
        def _load_or_default(key, fallback):
            v = z.get(key)
            return fallback if v is None else v

        ppl_dens = _load_or_default("peopleDensity", loads["people"])
        light_p = _load_or_default("lightingPower", loads["lighting"])

        base_equip_p = _load_or_default("equipmentPower", loads["equipment"])
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
    air_boundary_count = 0
    ground_promoted = 0
    # 자기참조로 걷어낸 최하층 바닥을 지면 경계로 되살릴지. 기본 off.
    promote_ground_floors = bool(project_data.get("promoteGroundFloors"))
    # 개방 경계(Air 표면)용 공유 AirBoundary construction (콘크리트 벽 대신 공기혼합)
    idf.add_air_boundary_construction("AirBoundary_Const")

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

            # Air(개방 경계)면은 콘크리트 벽 대신 AirBoundary(공기혼합+복사교환) 사용
            is_air = "air" in t
            const_name = "AirBoundary_Const" if is_air else f"Const_{s['id']}"
            if is_air:
                air_boundary_count += 1

            # 원본: Zone A (gbXML에서 직접 연결된 Zone)
            idf.add_surface(
                s['id'], ep_type, const_name, z_id,
                "Surface", "NoSun", "NoWind", verts,
                adj_surface_id=mirror_id
            )

            # 미러: Zone B (인접 Zone) — 동일 Construction 재사용
            idf.add_surface(
                mirror_id, ep_type, const_name, adj_zone_id,
                "Surface", "NoSun", "NoWind", mirror_verts,
                adj_surface_id=s['id']
            )
            zone_to_zone_count += 1

        else:
            # 지면 접촉 승격(옵션): 자기참조로 걷어낸 최하층 바닥을 Ground 로 둔다.
            # 익스포터가 SlabOnGrade 대신 자기참조 InteriorFloor 로 내보낸 경우를
            # 되살리는 용도이며, 기본값은 꺼져 있다 — 지하층·필로티·외기노출 바닥을
            # 오분류할 수 있어 사용자가 명시적으로 켜야 한다.
            if promote_ground_floors and s.get("selfAdjacent") and "floor" in t \
                    and s.get("vertices") and all(abs(p[2]) < 1e-6 for p in s["vertices"]):
                idf.add_surface(s['id'], ep_type, f"Const_{s['id']}", z_id,
                                "Ground", "NoSun", "NoWind", verts)
                ground_promoted += 1
                continue

            # 외벽 또는 인접 Zone이 없는 내부면 → 기존 로직
            # selfAdjacent: 파서가 자기참조 인접을 걷어낸 면. 타입에 'interior'가 없는
            # Air 같은 면이 여기서 외기 노출(일사·풍압)로 빠지면 없던 외피가 생긴다.
            if "interior" in t or adj_zone_raw or s.get("selfAdjacent"):
                # adjacentZone이 있지만 유효하지 않은 Zone → Adiabatic fallback
                obc, sun, wind = "Adiabatic", "NoSun", "NoWind"
            else:
                obc, sun, wind = "Outdoors", "SunExposed", "WindExposed"

            idf.add_surface(s['id'], ep_type, f"Const_{s['id']}", z_id,
                            obc, sun, wind, verts)

            wwr = s.get("wwr", 0)
            if ep_type == "Wall" and wwr > 0 and obc == "Outdoors":
                # 실측 opening 형상 우선 (위치·개수·모양 보존 → 일사 계산 정확도)
                win_list = build_window_geometries(s, verts)
                for wi, wv in enumerate(win_list):
                    # 첫 창은 기존 명명 유지 (AFN·surfaceAirflow 계약 호환)
                    wname = f"Win_{s['id']}" if wi == 0 else f"Win_{s['id']}_{wi + 1}"
                    idf.add_window(wname, f"WinConst_{s['id']}", s['id'], wv)

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
    if ground_promoted > 0:
        print(f"🌍 최하층 자기참조 바닥 {ground_promoted}개를 Ground 경계로 승격")

    # 실기기 HVAC 누적분 일괄 emit (PTHP 존별 EquipmentConnections/List 등)
    idf.finalize_hvac()

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
        heat_source = int(project_data.get('heatSource', 11))   # 난방 열원(1가스/2전기/4등유/11지역난방)

        lcc_parameters = project_data.get('lccParameters', {})

        # 기존 건물 실측 기준값 (선택): 비어 있으면 cost_analyzer가 1.6배 추정으로 fallback
        baseline_actual = project_data.get('baselineActual', {}) or {}
        def _pos_num(v):
            try:
                n = float(v)
                return n if n > 0 else None
            except (TypeError, ValueError):
                return None

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
            cooling_grade=equip["cooling_grade"],
            heating_age=equip["heating_age"],
            hvac_upgraded=equip.get("upgraded", False),
            hvac_exclude_non_habitable=project_data.get('hvacExcludeNonHabitable', False),
            heat_source=heat_source,
            use_pthp=use_pthp,
            hvac_mode=hvac_mode,
            heating_fuel=fuel_type,
            heating_fuel_eff=fuel_eff,
            discount_rate=float(lcc_parameters.get('discountRate', 5.0)) / 100.0,
            inflation_rate=float(lcc_parameters.get('inflationRate', 3.0)) / 100.0,
            utility_inflation=float(lcc_parameters.get('utilityInflation', 4.0)) / 100.0,
            lifecycle_years=int(lcc_parameters.get('lifecycleYears', 20)),
            actual_elec_bill=_pos_num(baseline_actual.get('elecBill')),
            actual_heat_bill=_pos_num(baseline_actual.get('heatBill')),
            actual_elec_kwh=_pos_num(baseline_actual.get('elecKwh')),
            actual_heat_kwh=_pos_num(baseline_actual.get('heatKwh')),
            sim_base_elec_bill=(baseline_result["financial"]["annual_elec_bill"] if baseline_result else None),
            sim_base_heat_bill=(baseline_result["financial"]["annual_heat_bill"] if baseline_result else None),
            sim_base_same=baseline_same
        )

        # 계산에 쓴 가정을 결과에 남긴다. 특히 면적은 지표의 분모이자 내부발열의
        # 기준이라, 어떤 출처의 값을 썼는지 모르면 결과를 해석할 수 없다.
        # 개방 계단실의 Air 경계 면적처럼 '실제 사용 바닥면적이 아닐 수 있는' 값을
        # 폴백으로 쓰는 경우가 있어 반드시 드러내야 한다.
        _area_sources = {"declared": 0, "parser_geometry": 0, "recomputed": 0}
        _low_conf_zones = []
        for _z in zones:
            if (_z.get("declaredArea") or 0) > 0:
                _area_sources["declared"] += 1
            elif (_z.get("geometricArea") or _z.get("area") or 0) > 0:
                _area_sources["parser_geometry"] += 1
                _low_conf_zones.append(_z.get("id"))
            else:
                _area_sources["recomputed"] += 1
                _low_conf_zones.append(_z.get("id"))

        assumptions = [{
            "key": "floor_area_basis",
            "label": "바닥면적 기준",
            "value": f"선언 {_area_sources['declared']}개 실 / 도형 추정 "
                     f"{_area_sources['parser_geometry'] + _area_sources['recomputed']}개 실",
            "note": ("gbXML 이 선언한 실 면적을 우선 사용합니다."
                     + (f" 선언값이 없는 {len(_low_conf_zones)}개 실은 도형에서 추정했으며, "
                        f"개방 계단실처럼 바닥 슬래브가 없는 실은 개방부 경계로 추정하므로 "
                        f"실제 사용 바닥면적과 다를 수 있습니다: "
                        f"{', '.join(str(z) for z in _low_conf_zones[:5])}"
                        if _low_conf_zones else "")),
            "confidence": "low" if _low_conf_zones else "high",
        }, {
            "key": "ground_temperature",
            "label": "지중온도",
            "value": f"{min(_gt)}~{max(_gt)}℃ (월별)",
            "note": "EnergyPlus 지침에 따라 실내 설정온도보다 2K 낮은 슬래브 하부 온도를 "
                    "가정합니다. 기상데이터의 비교란 토양온도가 아닙니다.",
            "confidence": "medium",
        }, {
            "key": "ground_contact",
            "label": "최하층 바닥 경계",
            "value": ("지면 접촉" if promote_ground_floors else "단열 경계"),
            "note": ("자기참조로 기록된 최하층 바닥의 경계조건입니다. "
                     "지면 접촉으로 바꾸면 지면 열손실이 반영됩니다."),
            "confidence": "medium",
        }]

        # 적용된 설비 내역 동봉 (입력/자동 배지 표시용)
        hvac_equipment_block = {
            "building": {
                "mode": hvac_mode,
                "coolingGrade": equip["cooling_grade"],
                "heatingAge": equip["heating_age"],
                "upgraded": equip.get("upgraded", False),  # 설비 교체 토글로 신형 적용됨
                "userInput": equip["is_user_input"],
            },
            "zones": equipment_log,
        }
        result_data["hvacEquipment"] = hvac_equipment_block
        result_data["result"]["hvacEquipment"] = hvac_equipment_block
        result_data["assumptions"] = assumptions
        result_data["result"]["assumptions"] = assumptions

        # 개선 전 시뮬 결과를 응답에 동봉 → UI가 전/후 에너지를 나란히 비교 가능
        if baseline_result:
            baseline_block = {
                "summary": baseline_result.get("summary"),
                "monthly": baseline_result.get("monthly"),
                "annual_elec_bill": baseline_result["financial"]["annual_elec_bill"],
                "annual_heat_bill": baseline_result["financial"]["annual_heat_bill"],
            }
            result_data["baseline"] = baseline_block
            result_data["result"]["baseline"] = baseline_block

        # ── 대안별 정량 평가: 추천 대안을 실제 적용해 재시뮬레이션 → kWh/㎡·운영비 변화 산출 ──
        # 재귀 방지: 대안 평가로 생성된 변형 실행(_variantOf)은 자기 대안을 다시 평가하지 않는다.
        if not payload.get("_variantOf"):
            _evaluate_alternatives(payload, result_data, temp_dir, _stage)

        return result_data

    # 시뮬레이션 실패 시 가짜 데이터 대신 명시적으로 실패 처리
    # (eplusout.err의 Severe/Fatal 줄을 추려 원인을 함께 전달)
    err_path = os.path.join(temp_dir_abs, "eplusout.err")
    err_hint = ""
    if os.path.exists(err_path):
        with open(err_path, "r", encoding="utf-8", errors="ignore") as f:
            critical = [ln.strip() for ln in f if "** Severe" in ln or "**  Fatal" in ln]
        if critical:
            err_hint = " | " + " / ".join(critical[:3])
    raise RuntimeError(f"EnergyPlus 시뮬레이션 실패{err_hint}")