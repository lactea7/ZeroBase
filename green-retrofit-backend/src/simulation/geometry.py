"""표면 지오메트리 → IDF 객체.

`generate_idf_and_simulate` 안에서 128줄을 차지하던 표면 루프와, 그것이 쓰던
순수 기하 함수들을 옮겼다. 순수 이동이며 판정 규칙을 바꾸지 않았다.

**여기서 끝나는 것**: 경계조건·일사노출 판정, 인접면 짝짓기, 창 형상, AFN 균열,
내부 블라인드 제어.
**여기 오면 안 되는 것**: 재료·구성체 정의, 스케줄, 설비. 그건 각자의 몫이다.

⚠️ 이 판정들은 골든 IDF 문자열 비교만으로는 지켜지지 않는다("무엇이 바뀌었는지"는
알려줘도 "왜 그렇게 결정했는지"는 못 지킨다). `tests/test_geometry_decisions.py`
가 호출 단위로 고정한다 — 이 모듈을 고치면 그쪽이 먼저 반응해야 한다.
"""
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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


#: gbXML 이 **명시적으로** 지면 접촉이라고 선언한 표면 타입.
#
# ⚠️ 예전에는 이 타입들을 경계조건 판정에서 아예 안 봤다. 짝이 없으면 무조건
# `Outdoors + SunExposed + WindExposed` 로 떨어져, **지면에 묻힌 슬래브가 햇빛과
# 바람을 받았다.** 실측: 회의실.xml 의 `SlabOnGrade` 41면 1,107㎡(IDF 표면적의
# 10.5%), 운동시설.xml 의 `UndergroundSlab` 12면 1,672㎡(**35.8%**).
#
# ⚠️ `promoteGroundFloors` 와 혼동하지 말 것. 그쪽은 자기참조 최하층 바닥을 보고
# **추정**하는 것이라 opt-in 이 맞다. 여기는 gbXML 이 **선언**한 정보이므로
# 조건 없이 따른다.
#
# ⚠️ `RaisedFloor` 는 넣지 않는다 — 필로티·주차장 위 바닥이라 **외기 노출이 맞다.**
GROUND_CONTACT_TYPES = (
    "slabongrade", "undergroundslab", "undergroundwall", "undergroundceiling",
)


@dataclass
class GeometryResult:
    """표면 emit 결과. 로그 문자열이 아니라 값으로 돌려준다."""
    skipped: int = 0                 # 존에 안 붙은 면(차양·지형)
    zone_to_zone: int = 0            # 양방향 쌍을 만든 인접면
    air_boundary: int = 0            # AirBoundary 로 처리한 개방 경계
    ground_promoted: int = 0         # 지면 접촉으로 **승격**한 최하층 바닥(추정)
    ground_declared: int = 0         # gbXML 이 지면 접촉이라 **선언**한 면
    #: 존 → 그 존에 붙은 창 이름들. 내부 블라인드 제어를 존 단위로 걸 때 쓴다.
    windows_by_zone: Dict[str, List[str]] = field(default_factory=dict)


def _ep_type(surface_type: str) -> str:
    """gbXML 표면 타입 → EnergyPlus 표면 종류."""
    t = (surface_type or "").lower()
    if "roof" in t:
        return "Roof"
    if "floor" in t or "slab" in t:
        return "Floor"
    return "Wall"


def _is_slab_on_grade(surface: Dict[str, Any], surface_type: str) -> bool:
    """자기참조로 걷어낸 최하층 바닥인가.

    ⚠️ 세 조건이 **전부** 맞아야 한다(자기참조 · 바닥 · z≈0). 하나라도 느슨하면
    지하층·필로티·상층 바닥이 지면 접촉으로 오분류돼 열손실이 통째로 달라진다.
    """
    verts = surface.get("vertices")
    return bool(
        surface.get("selfAdjacent")
        and "floor" in (surface_type or "").lower()
        and verts
        and all(abs(p[2]) < 1e-6 for p in verts)
    )


def emit_surfaces(idf, surfaces: List[Dict[str, Any]], *,
                  valid_zone_ids, valid_afn_zones,
                  promote_ground_floors: bool = False) -> GeometryResult:
    """표면·창·AFN 균열을 IDF 에 넣는다."""
    result = GeometryResult()
    # 개방 경계(Air 표면)용 공유 AirBoundary construction (콘크리트 벽 대신 공기혼합)
    idf.add_air_boundary_construction("AirBoundary_Const")

    for s in surfaces:
        z_id = s['zone'].replace(" ", "_")

        # 💡 Zone이 "Unknown"이거나 유효한 Zone 목록에 없으면 IDF에서 제외
        if z_id == "Unknown" or z_id not in valid_zone_ids:
            result.skipped += 1
            continue

        t = s.get("type", "").lower()
        ep_type = _ep_type(s.get("type", ""))
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
                result.air_boundary += 1

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
            result.zone_to_zone += 1
            continue

        # ⚠️ 부분 문자열이 아니라 **정확 일치**다. 파서가 타입을 이미 정규화해서
        # 넘기므로 느슨하게 볼 이유가 없고, `in` 매칭은 새 타입이 생겼을 때
        # 조용히 오분류된다.
        declared_ground = t in GROUND_CONTACT_TYPES

        # 지면 접촉 승격(옵션): 자기참조로 걷어낸 최하층 바닥을 Ground 로 둔다.
        # 익스포터가 SlabOnGrade 대신 자기참조 InteriorFloor 로 내보낸 경우를
        # 되살리는 용도이며, 기본값은 꺼져 있다 — 지하층·필로티·외기노출 바닥을
        # 오분류할 수 있어 사용자가 명시적으로 켜야 한다.
        #
        # ⚠️ **선언된 면은 여기 들어오면 안 된다.** 결과 IDF 는 어차피 `Ground` 로
        # 같지만, `SlabOnGrade` + selfAdjacent + z≈0 인 면이 `ground_promoted` 로
        # 세어져 **선언된 사실이 추정으로 기록된다.** 카운터와 로그가 거짓이 된다.
        if not declared_ground and promote_ground_floors \
                and _is_slab_on_grade(s, s.get("type", "")):
            idf.add_surface(s['id'], ep_type, f"Const_{s['id']}", z_id,
                            "Ground", "NoSun", "NoWind", verts)
            result.ground_promoted += 1
            continue

        # ⚠️ gbXML 이 지면 접촉이라고 **선언**한 면은 조건 없이 Ground 다.
        # 이건 추정이 아니라 입력에 적힌 사실이고, 안 읽으면 묻힌 슬래브가
        # 햇빛·바람을 받는다.
        if declared_ground:
            obc, sun, wind = "Ground", "NoSun", "NoWind"
            result.ground_declared += 1
        # 외벽 또는 인접 Zone이 없는 내부면 → 기존 로직
        # selfAdjacent: 파서가 자기참조 인접을 걷어낸 면. 타입에 'interior'가 없는
        # Air 같은 면이 여기서 외기 노출(일사·풍압)로 빠지면 없던 외피가 생긴다.
        elif "interior" in t or adj_zone_raw or s.get("selfAdjacent"):
            # adjacentZone이 있지만 유효하지 않은 Zone → Adiabatic fallback
            obc, sun, wind = "Adiabatic", "NoSun", "NoWind"
        else:
            obc, sun, wind = "Outdoors", "SunExposed", "WindExposed"

        # 경계조건·노출 명시 지정. 예를 들어 ASHRAE 140 의 바닥은 Outdoors 이면서
        # NoSun/NoWind 다(고단열 바닥으로 지면 결합을 무시하는 5.2절 관례).
        # 자동 추정으로는 표현할 수 없어 표면별로 덮어쓸 수 있게 한다.
        # gbXML 파서는 이 키들을 만들지 않으므로 기존 경로에는 영향이 없다.
        if s.get("boundaryCondition"):
            obc = s["boundaryCondition"]
        if s.get("sunExposure"):
            sun = s["sunExposure"]
        if s.get("windExposure"):
            wind = s["windExposure"]

        idf.add_surface(s['id'], ep_type, f"Const_{s['id']}", z_id,
                        obc, sun, wind, verts)

        wwr = s.get("wwr", 0)
        if ep_type == "Wall" and wwr > 0 and obc == "Outdoors":
            # 실측 opening 형상 우선 (위치·개수·모양 보존 → 일사 계산 정확도)
            for wi, wv in enumerate(build_window_geometries(s, verts)):
                # 첫 창은 기존 명명 유지 (AFN·surfaceAirflow 계약 호환)
                wname = f"Win_{s['id']}" if wi == 0 else f"Win_{s['id']}_{wi + 1}"
                idf.add_window(wname, f"WinConst_{s['id']}", s['id'], wv)
                result.windows_by_zone.setdefault(z_id, []).append(wname)

        # AirflowNetwork Surface 및 개구부(Window) 등록
        if obc == "Outdoors" and s.get("zone") in valid_afn_zones:
            # ⚠️ 균열 계수를 **표면 면적에 비례**시킨다. 예전엔 모든 면이
            # 같은 `WallCrack`(계수 0.01) 을 factor 1.0 으로 공유해서, 총 누기가
            # 외피 기밀성이 아니라 **표면 개수**에 좌우됐다 — 같은 벽을 8개
            # 폴리곤으로 쪼개면 난방이 +33.5% 뛰었다.
            crack = idf.add_surface_crack(s['id'], calculate_surface_area(verts))
            idf.add("AirflowNetwork:MultiZone:Surface", [
                s['id'], crack, "", 1.0
            ])
            if ep_type == "Wall" and wwr > 0:
                idf.add("AirflowNetwork:MultiZone:Surface", [
                    f"Win_{s['id']}", "WindowOpening", "", 1.0,
                    "NoVent", "", 0.0, 0.0, 100.0, 0.0, 300000.0, "AlwaysOn"
                ])

    return result


def emit_interior_blinds(idf, windows_by_zone: Dict[str, List[str]],
                         setpoint_w_m2: float) -> int:
    """창이 있는 존마다 내부 블라인드 일사 제어를 건다. 건 존 수를 돌려준다.

    ⚠️ 차양이 전혀 없으면 결과가 통째로 왜곡된다. 용호동 시간별 결과: 순 일사
    취득 117 kWh/㎡·년 이 겨울 난방을 상쇄하고 여름 냉방을 밀어 올려, 서울
    사무소인데 난방 10.6 / 냉방 54.1 kWh/㎡ 가 나왔다. 블라인드를 넣자 난방
    19.0 (+80%). 실제 사무실은 눈부심 때문에 해가 강하면 내린다.

    ⚠️ ASHRAE 140 에는 **절대 걸면 안 된다.** 600 vs 610 의 유일한 차이가 외부
    차양이라, 내부 블라인드가 붙으면 그 델타가 오염되고 참조값 비교가 무의미해진다.
    호출자가 `benchmark.noInteriorBlind` 로 막는다.
    """
    if not windows_by_zone:
        return 0
    idf.add_interior_blind()
    for zone_id, window_ids in windows_by_zone.items():
        idf.add_window_shading_control(zone_id, window_ids,
                                       setpoint_w_m2=setpoint_w_m2)
    return len(windows_by_zone)
