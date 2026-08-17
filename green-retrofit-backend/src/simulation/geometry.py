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


#: 짝이 없을 때 **아래쪽**에 이웃이 있는지 보는 타입(바닥 계열).
#
# ⚠️ `RaisedFloor` 를 노려 봤자 소용없다 — 파서가 `"floor" in type` 으로 잡아
# **`Floor` 로 매핑**하기 때문에 여기 도달할 땐 이미 `Floor` 다. 실제로 회의실.xml
# 의 `RaisedFloor` 64면이 전부 `Floor` 로 들어온다. 그래도 payload 를 직접 넣는
# 경로(벤치마크·시험)를 위해 원래 이름도 함께 둔다.
#
# ⚠️ `InteriorFloor`·`InteriorCeiling` 은 **일부러 뺐다.** 이름에 `interior` 가
# 있어서 위쪽 분기가 먼저 Adiabatic 으로 처리한다 — 여기 적어 두면 이 규칙이
# 그것들까지 담당하는 것처럼 읽히지만 실제로는 도달하지 않는 죽은 항목이다.
#
# ⚠️ `ExteriorFloor` 는 **넣지 않는다.** 그건 gbXML 이 외기 노출이라고 선언한 것이다.
INTERSTITIAL_FLOOR_TYPES = ("floor", "raisedfloor")

#: 짝이 없을 때 **위쪽**에 이웃이 있는지 보는 타입(천장 계열).
#
# ⚠️ `Roof` 는 **넣지 않는다.** `SlabOnGrade` 가 지면 접촉을 선언하듯 `Roof` 는
# 하늘 노출을 선언한다 — 선언은 따른다. (`Floor` 는 아무것도 선언하지 않는다.
# 그래서 바닥만 추론 대상이다.) ARK 파일에 건물 중간 높이의 `Roof` 가 107면
# 있는 건 별개 문제이고, 여기서 조용히 뒤집지 않는다.
INTERSTITIAL_CEILING_TYPES = ("ceiling",)

#: 이웃 존의 반대편 끝과 이만큼 이내로 붙어 있어야 "층층이 쌓였다"고 본다(m).
# 실측: 회의실 64면의 간격은 0.00~2.44m(아래 존 벽이 슬래브까지 안 올라온 경우
# 포함), ARK 84면은 −0.15~0.00m. 한 층(약 3.5m)을 넘으면 사이에 빈 공간이 있다는
# 뜻이므로 이웃으로 치지 않는다.
INTERSTITIAL_MAX_GAP = 3.0

#: 면적의 이만큼이 이웃 존 윤곽 안에 들어와야 인정한다.
# ⚠️ 캔틸레버·처마처럼 일부만 걸친 면을 통째로 단열로 만들지 않기 위한 하한이다.
INTERSTITIAL_MIN_OVERLAP = 0.5


@dataclass
class GeometryResult:
    """표면 emit 결과. 로그 문자열이 아니라 값으로 돌려준다."""
    skipped: int = 0                 # 존에 안 붙은 면(차양·지형)
    zone_to_zone: int = 0            # 양방향 쌍을 만든 인접면
    air_boundary: int = 0            # AirBoundary 로 처리한 개방 경계
    ground_promoted: int = 0         # 지면 접촉으로 **승격**한 최하층 바닥(추정)
    ground_declared: int = 0         # gbXML 이 지면 접촉이라 **선언**한 면
    #: 짝은 없지만 위/아래에 존이 실재해 Adiabatic 으로 둔 층간 바닥·천장.
    #: ⚠️ **저신뢰 fallback 이다.** 개수를 값으로 돌려 호출자가 사용자에게
    #: 알릴 수 있게 한다 — 조용히 처리하면 안 된다.
    interstitial_adiabatic: int = 0
    #: 존 → 그 존에 붙은 창 이름들. 내부 블라인드 제어를 존 단위로 걸 때 쓴다.
    windows_by_zone: Dict[str, List[str]] = field(default_factory=dict)


def _ep_type(surface_type: str) -> str:
    """gbXML 표면 타입 → EnergyPlus 표면 종류.

    ⚠️ **`Ceiling` 분기가 없어서 천장이 `Wall` 로 들어가고 있었다.** `roof` 도
    `floor`/`slab` 도 아니면 전부 `Wall` 로 떨어지는 구조였다. 수평 천장이 벽으로
    선언되면 EnergyPlus 가 기울기·면 종류로 하는 검사가 전부 어긋난다
    (`InterZone Surface Tilts/Classes do not match`가 여기서도 나온다).
    `ee931c7` 로 `UndergroundCeiling` 을 `Ground` 로 보내기 시작했는데 그것도
    **`Ground` 벽**이었다.

    ⚠️ `ceiling` 은 `floor` 보다 **먼저** 봐야 한다 — 순서를 바꾸면 그만이지만,
    실제 파일 4개엔 `Ceiling` 타입이 하나도 없어서 골든 IDF 로는 안 잡힌다.
    """
    t = (surface_type or "").lower()
    if "roof" in t:
        return "Roof"
    if "ceiling" in t:
        return "Ceiling"
    if "floor" in t or "slab" in t:
        return "Floor"
    return "Wall"


def _convex_hull_xy(points) -> List[tuple]:
    """XY 평면 볼록 껍질(Andrew monotone chain).

    ⚠️ **볼록 껍질은 존 윤곽의 과대 근사다.** ㄱ자·ㄷ자 평면에서는 실제로 비어
    있는 안뜰까지 덮는다. 그래서 이 함수로 판정하면 오차 방향이 **Adiabatic 쪽으로
    치우친다** — 안뜰 위 바닥이 외기 노출인데 단열로 잡힐 수 있다.
    받아들인 이유: 여기서 필요한 건 "아래에 건물이 있나"이지 정확한 면적이 아니고,
    반대 방향 오류(층간 바닥이 햇빛·바람을 받는 것)가 훨씬 크기 때문이다.
    """
    pts = sorted(set((round(p[0], 6), round(p[1], 6)) for p in points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _signed_area_xy(poly: List[tuple]) -> float:
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return s / 2.0


def _ccw(poly: List[tuple]) -> List[tuple]:
    """반시계 방향으로 맞춘다.

    ⚠️ `_clip_convex` 의 안/밖 판정은 **감김 방향에 의존한다.** 시계 방향이 섞여
    들어오면 교차가 통째로 빈 다각형이 되어 겹침이 0 으로 나온다.
    """
    return poly if _signed_area_xy(poly) >= 0 else list(reversed(poly))


def _polygon_area_xy(poly: List[tuple]) -> float:
    """XY 다각형 면적(신발끈). 방향과 무관하게 양수."""
    if len(poly) < 3:
        return 0.0
    return abs(_signed_area_xy(poly))


def _clip_convex(subject: List[tuple], clip: List[tuple]) -> List[tuple]:
    """Sutherland–Hodgman. **두 다각형이 모두 볼록**할 때만 옳다."""
    out = list(subject)
    n = len(clip)
    for i in range(n):
        if not out:
            return []
        ax, ay = clip[i]
        bx, by = clip[(i + 1) % n]

        def inside(p):
            return (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax) >= -1e-12

        clipped = []
        for j in range(len(out)):
            cur, prv = out[j], out[j - 1]
            if inside(cur):
                if not inside(prv):
                    clipped.append(_edge_intersection(prv, cur, (ax, ay), (bx, by)))
                clipped.append(cur)
            elif inside(prv):
                clipped.append(_edge_intersection(prv, cur, (ax, ay), (bx, by)))
        out = [p for p in clipped if p is not None]
    return out


def _edge_intersection(p1, p2, a, b):
    """선분 p1→p2 와 직선 a→b 의 교점."""
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = a
    x4, y4 = b
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-15:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def _overlap_fraction(target: List[tuple], other: List[tuple]) -> float:
    """`target` 중 `other` 와 겹치는 **면적 비율**.

    ⚠️ 예전엔 6×6 격자 표본이었고 "존 윤곽이 오목해서 다각형 클리핑을 못 쓴다"고
    적어 뒀었다. **그 근거가 틀렸다**(codex 지적) — 두 인자 모두 `_convex_hull_xy`
    를 거쳐 들어오므로 **항상 볼록**이다. 정확한 교차면적을 구할 수 있는데 표본을
    쓸 이유가 없었다.

    격자 표본은 실제로 해를 끼쳤다: 가늘고 비스듬한 면에서 표본이 하나도 안 걸려
    `0.0`(→ 외기 노출 유지)이 되고, 0.5 문턱 근처에서 표본 한두 개로 판정이 뒤집혔다.
    """
    if len(target) < 3 or len(other) < 3:
        return 0.0
    area = _polygon_area_xy(target)
    if area <= 1e-12:
        return 0.0
    return _polygon_area_xy(_clip_convex(_ccw(target), _ccw(other))) / area


def _zone_extents(surfaces: List[Dict[str, Any]], valid_zone_ids) -> Dict[str, tuple]:
    """존별 (z_min, z_max, XY 볼록껍질). **모든** 면의 꼭짓점에서 뽑는다.

    ⚠️ 바닥·천장만 보면 안 된다. 회의실.xml 은 최하층(z 8.99) 존들에 바닥 면이
    **아예 없어서** 그 존들이 통째로 안 보이고, 바로 위 층 바닥 20면이 "아래에
    아무것도 없다"로 오판된다. 벽 꼭짓점이 z 범위와 평면 윤곽을 둘 다 준다.
    """
    acc: Dict[str, list] = {}
    for s in surfaces:
        zone = (s.get("zone") or "").replace(" ", "_")
        if zone == "Unknown" or zone not in valid_zone_ids:
            continue
        verts = s.get("vertices")
        if not verts:
            continue
        acc.setdefault(zone, []).extend(verts)
    out = {}
    for zone, pts in acc.items():
        zs = [p[2] for p in pts]
        out[zone] = (min(zs), max(zs), _convex_hull_xy(pts))
    return out


def _is_horizontal(verts) -> bool:
    """법선이 거의 수직인가(=수평면인가). 경사로·비스듬한 면은 대상이 아니다."""
    if not verts or len(verts) < 3:
        return False
    nx = ny = nz = 0.0
    for i in range(len(verts)):
        v1, v2 = verts[i], verts[(i + 1) % len(verts)]
        nx += (v1[1] - v2[1]) * (v1[2] + v2[2])
        ny += (v1[2] - v2[2]) * (v1[0] + v2[0])
        nz += (v1[0] - v2[0]) * (v1[1] + v2[1])
    mag = math.sqrt(nx * nx + ny * ny + nz * nz)
    if mag <= 0:
        return False
    return abs(nz) / mag > 0.95


def _stacked_neighbor(surface: Dict[str, Any], zone_id: str, look_below: bool,
                      extents: Dict[str, tuple]) -> Optional[str]:
    """이 수평면의 반대편에 실재하는 이웃 존. 없으면 None.

    ⚠️ **z 부호만으로 판정하면 안 된다**(codex 지적). 높이가 0 보다 크다는 사실은
    언덕 위 필로티·단차·캔틸레버와 층간 슬래브를 구분하지 못한다. 그래서 세 가지를
    **모두** 요구한다: ① 반대편에 존이 실재하고 ② 그 존의 맞닿는 끝이 한 층 이내로
    붙어 있으며 ③ XY 투영이 절반 이상 겹친다.
    """
    verts = surface.get("vertices") or []
    if not _is_horizontal(verts):
        return None
    z = sum(p[2] for p in verts) / len(verts)
    poly = _convex_hull_xy(verts)
    if len(poly) < 3:
        return None

    best = None
    best_gap = None
    for other, (lo, hi, hull) in extents.items():
        if other == zone_id:
            continue
        if look_below:
            # 아래 존: 이 면보다 아래에서 시작해, 윗면이 이 면 근처까지 올라와야 한다.
            if not (lo < z - 1e-6 and z - INTERSTITIAL_MAX_GAP <= hi <= z + 0.3):
                continue
            gap = abs(z - hi)
        else:
            if not (hi > z + 1e-6 and z - 0.3 <= lo <= z + INTERSTITIAL_MAX_GAP):
                continue
            gap = abs(lo - z)
        if _overlap_fraction(poly, hull) < INTERSTITIAL_MIN_OVERLAP:
            continue
        if best_gap is None or gap < best_gap:
            best, best_gap = other, gap
    return best


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

    # 짝없는 층간 바닥·천장 판정에 쓸 존별 수직 범위·평면 윤곽. 루프 밖에서 한 번만.
    extents = _zone_extents(surfaces, valid_zone_ids)

    for s in surfaces:
        z_id = s['zone'].replace(" ", "_")

        # 💡 Zone이 "Unknown"이거나 유효한 Zone 목록에 없으면 IDF에서 제외
        if z_id == "Unknown" or z_id not in valid_zone_ids:
            result.skipped += 1
            continue

        t = s.get("type", "").lower()
        interstitial = False
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
        # 외벽 또는 인접 Zone이 없는 내부면 → 기존 로직
        # selfAdjacent: 파서가 자기참조 인접을 걷어낸 면. 타입에 'interior'가 없는
        # Air 같은 면이 여기서 외기 노출(일사·풍압)로 빠지면 없던 외피가 생긴다.
        elif "interior" in t or adj_zone_raw or s.get("selfAdjacent"):
            # adjacentZone이 있지만 유효하지 않은 Zone → Adiabatic fallback
            obc, sun, wind = "Adiabatic", "NoSun", "NoWind"
        # ⚠️ **짝없는 층간 바닥·천장.** gbXML 이 인접을 안 적었지만 위/아래에 존이
        # 실재하는 면이다. 예전엔 여기가 통째로 `Outdoors + SunExposed` 로 떨어져
        # **건물 14층 높이의 층간 슬래브가 겨울 외기와 햇빛을 받았다.**
        # 실측 영향: 회의실 난방 −41.3%, 냉방 +9%.
        #
        # ⚠️ **타입만으로 결정하지 않는다.** 회의실의 `RaisedFloor` 64면은 전부
        # 층간 슬래브지만, 같은 타입이 진짜 필로티인 파일도 있다. 반대편에 존이
        # 실재하는지를 기하로 확인한다(`_stacked_neighbor`).
        #
        # ⚠️ 이건 **저신뢰 fallback 이지 복원이 아니다.** 아래층이 비슷하게 냉난방된다는
        # 가정이 깔려 있고, 아래가 비난방 주차장이면 난방을 과소평가, 더 찬 냉방존이면
        # 냉방을 과대평가한다. 짝을 실제로 이어 붙이는 건 canonical boundary 작업이다.
        elif (t in INTERSTITIAL_FLOOR_TYPES or t in INTERSTITIAL_CEILING_TYPES) \
                and _stacked_neighbor(s, z_id, t in INTERSTITIAL_FLOOR_TYPES, extents):
            obc, sun, wind = "Adiabatic", "NoSun", "NoWind"
            interstitial = True
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

        # ⚠️ **카운터는 덮어쓰기 뒤에 센다.** 예전엔 판정 분기 안에서 바로 올렸는데,
        # 그러면 명시 지정으로 최종 `Outdoors` 가 된 면까지 "단열로 처리했다"고
        # 기록됐다. 사용자에게 나가는 `assumptions` 숫자가 IDF 와 어긋난다.
        # (round-1 에서 `ground_promoted` 를 두고 지적받은 것과 같은 종류의 오류다.)
        if obc == "Ground" and declared_ground:
            result.ground_declared += 1
        if obc == "Adiabatic" and interstitial:
            result.interstitial_adiabatic += 1

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
