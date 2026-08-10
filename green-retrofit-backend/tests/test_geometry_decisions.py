"""지오메트리 조립의 **결정**을 호출 단위로 검사한다.

golden IDF 는 1,300줄 문자열 비교라 "무엇이 바뀌었는지"는 알려줘도 "왜 그렇게
결정했는지"는 못 지킨다. 그리고 대표 payload 가 지나지 않는 분기가 많다.

여기서는 `add_surface()` / `add_window()` 호출을 **기록해** 경계조건·일사노출·
인접면 짝짓기 같은 판단을 직접 본다. 지오메트리 emit 을 별도 모듈로 떼기 전의
안전망이다 — 떼고 나서 이 시험이 그대로 통과해야 한다.
"""
import os
import sys
from collections import namedtuple

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(BACKEND, "src"))

SurfaceCall = namedtuple("SurfaceCall",
                         "id type construction zone boundary sun wind verts adj")
WindowCall = namedtuple("WindowCall", "id construction parent verts")


class AssemblyComplete(Exception):
    """지오메트리 조립이 끝났다는 신호. **이 예외만** 기대한다."""

# 4x5 바닥의 남향 외벽 (z 0~3)
SOUTH_WALL = [(0, 0, 3), (0, 0, 0), (4, 0, 0), (4, 0, 3)]
NORTH_WALL = [(4, 5, 3), (4, 5, 0), (0, 5, 0), (0, 5, 3)]
FLOOR = [(0, 0, 0), (0, 5, 0), (4, 5, 0), (4, 0, 0)]


@pytest.fixture
def record(monkeypatch):
    """payload → (표면 호출들, 창 호출들). EnergyPlus 는 돌리지 않는다."""
    import ep_simulator

    def _run(payload, tmp_path):
        surfaces, windows = [], []

        # ⚠️ **시그니처가 실제 호출과 정확히 같아야 한다.** 인접면 경로는
        # `adj_surface_id=` 를 키워드로 넘기는데 예전 fake 는 `adj=` 였다.
        # 그때는 fixture 가 `except Exception` 으로 조립 오류를 전부 삼켜서
        # **인접면 시험이 빈 리스트로 통과**했다.
        def fake_surface(self, surface_id, ep_type, construction, zone_id,
                         boundary, sun, wind, vertices, adj_surface_id=""):
            surfaces.append(SurfaceCall(surface_id, ep_type, construction, zone_id,
                                        boundary, sun, wind, vertices, adj_surface_id))
            return self

        def fake_window(self, window_id, construction, parent_surface, vertices):
            windows.append(WindowCall(window_id, construction, parent_surface, vertices))
            return self

        # 지오메트리·블라인드 emit 직후, EnergyPlus 실행 훨씬 전에 멈춘다.
        # ⚠️ 여기서 **이 예외만** 기대한다(`pytest.raises`). 넓은 except 로 감싸면
        # fake 시그니처 불일치 같은 조립 오류가 조용히 묻혀 시험이 빈 결과로 통과한다.
        def stop_after_geometry(self):
            raise AssemblyComplete

        monkeypatch.setattr(ep_simulator.IdfBuilder, "add_surface", fake_surface)
        monkeypatch.setattr(ep_simulator.IdfBuilder, "add_window", fake_window)
        monkeypatch.setattr(ep_simulator.IdfBuilder, "finalize_hvac",
                            stop_after_geometry)

        with pytest.raises(AssemblyComplete):
            ep_simulator.generate_idf_and_simulate(payload, str(tmp_path))
        return surfaces, windows

    return _run


def _payload(surfaces, zones=None, project=None):
    return {
        "projectData": {"name": "T", "location": "KOR_SO_Seoul",
                        "heatSource": 11, **(project or {})},
        "zones": zones or [{"id": "Z1", "floor": 1, "height": 3.0, "area": 20.0,
                            "activityId": None, "isConditioned": True}],
        "surfaces": surfaces,
        "materials": {"constructions": []},
    }


def _wall(sid, verts, zone="Z1", **extra):
    return {"id": sid, "type": "ExteriorWall", "zone": zone, "vertices": verts,
            "uValue": 0.5, "area": 12.0, **extra}


# ── 경계조건 판정 ────────────────────────────────────────

def test_exterior_wall_is_sun_and_wind_exposed(record, tmp_path):
    surfaces, _ = record(_payload([_wall("S1", SOUTH_WALL)]), tmp_path)
    s = next(x for x in surfaces if x.id == "S1")
    assert (s.boundary, s.sun, s.wind) == ("Outdoors", "SunExposed", "WindExposed")


def test_interior_surface_is_never_sun_exposed(record, tmp_path):
    """⚠️ 내부면이 외기 노출로 빠지면 없던 외피가 생겨 부하가 통째로 커진다."""
    surfaces, _ = record(
        _payload([{"id": "S1", "type": "InteriorWall", "zone": "Z1",
                   "vertices": SOUTH_WALL, "uValue": 2.0, "area": 12.0}]), tmp_path)
    s = next(x for x in surfaces if x.id == "S1")
    assert s.sun == "NoSun" and s.wind == "NoWind"
    assert s.boundary != "Outdoors"


def test_self_adjacent_surface_does_not_become_envelope(record, tmp_path):
    """⚠️ 파서가 자기참조 인접을 걷어낸 면(`selfAdjacent`)은 타입에 'interior' 가
    없어도 외기로 빠지면 안 된다 — Air 경계 같은 면이 여기 걸린다."""
    surfaces, _ = record(
        _payload([_wall("S1", SOUTH_WALL, type="Air", selfAdjacent=True)]), tmp_path)
    s = next(x for x in surfaces if x.id == "S1")
    assert s.boundary == "Adiabatic"
    assert s.sun == "NoSun"


def test_explicit_boundary_overrides_inference(record, tmp_path):
    """ASHRAE 140 바닥은 Outdoors 이면서 NoSun/NoWind 다 — 자동 추정으로는
    표현할 수 없어 표면별 지정을 허용한다."""
    surfaces, _ = record(_payload([
        _wall("S1", FLOOR, type="Floor", boundaryCondition="Outdoors",
              sunExposure="NoSun", windExposure="NoWind")]), tmp_path)
    s = next(x for x in surfaces if x.id == "S1")
    assert (s.boundary, s.sun, s.wind) == ("Outdoors", "NoSun", "NoWind")


def test_surface_without_a_zone_is_skipped(record, tmp_path):
    """차양·지형면은 존에 안 붙는다 — 존에 넣으면 부하가 생긴다."""
    surfaces, _ = record(
        _payload([_wall("S1", SOUTH_WALL), _wall("S2", NORTH_WALL, zone="없는존")]),
        tmp_path)
    assert {x.id for x in surfaces} == {"S1"}


# ── 창 ───────────────────────────────────────────────────

def test_window_is_created_only_on_exterior_walls(record, tmp_path):
    """⚠️ 내부벽에 창이 생기면 존 사이에 일사가 흐른다."""
    _s, windows = record(_payload([
        _wall("EXT", SOUTH_WALL, wwr=40, windowU=2.5, windowShgc=0.6),
        {"id": "INT", "type": "InteriorWall", "zone": "Z1", "vertices": NORTH_WALL,
         "uValue": 2.0, "area": 12.0, "wwr": 40},
    ]), tmp_path)
    assert {w.parent for w in windows} == {"EXT"}


def test_zero_wwr_makes_no_window(record, tmp_path):
    _s, windows = record(_payload([_wall("S1", SOUTH_WALL, wwr=0)]), tmp_path)
    assert windows == []


def test_first_window_keeps_the_legacy_name(record, tmp_path):
    """⚠️ `Win_{면id}` 는 AFN·surfaceAirflow 응답과의 계약이다 — 바꾸면
    3D 뷰어의 창 기류 오버레이가 끊긴다."""
    _s, windows = record(
        _payload([_wall("S1", SOUTH_WALL, wwr=40, windowU=2.5)]), tmp_path)
    assert windows[0].id == "Win_S1"


def test_window_area_follows_wwr(record, tmp_path):
    """WWR 이 클수록 창이 커야 한다 — 방향이 뒤집히면 개선/악화가 반대로 나온다."""
    def area(wwr):
        _s, w = record(_payload([_wall("S1", SOUTH_WALL, wwr=wwr, windowU=2.5)]),
                       tmp_path)
        v = w[0].verts
        xs = [p[0] for p in v]
        zs = [p[2] for p in v]
        return (max(xs) - min(xs)) * (max(zs) - min(zs))

    assert area(80) > area(20)


def test_window_stays_inside_its_host_wall(record, tmp_path):
    """⚠️ 창이 벽 밖으로 나가면 EnergyPlus 가 Severe 로 죽는다."""
    _s, windows = record(
        _payload([_wall("S1", SOUTH_WALL, wwr=90, windowU=2.5)]), tmp_path)
    wall_x = [p[0] for p in SOUTH_WALL]
    wall_z = [p[2] for p in SOUTH_WALL]
    for p in windows[0].verts:
        assert min(wall_x) - 1e-6 <= p[0] <= max(wall_x) + 1e-6
        assert min(wall_z) - 1e-6 <= p[2] <= max(wall_z) + 1e-6


# ── 존 간 인접면 ─────────────────────────────────────────

def test_interzone_surfaces_are_paired_both_ways(record, tmp_path):
    """⚠️ 한쪽만 만들면 EnergyPlus 가 경계를 못 닫는다."""
    zones = [{"id": "Z1", "floor": 1, "height": 3.0, "area": 20.0,
              "activityId": None, "isConditioned": True},
             {"id": "Z2", "floor": 1, "height": 3.0, "area": 20.0,
              "activityId": None, "isConditioned": True}]
    surfaces, _w = record(_payload([
        {"id": "P1", "type": "InteriorWall", "zone": "Z1", "adjacentZone": "Z2",
         "vertices": NORTH_WALL, "uValue": 2.0, "area": 12.0},
    ], zones=zones), tmp_path)
    paired = [s for s in surfaces if s.boundary == "Surface"]
    # ⚠️ `if paired:` 로 감싸면 빈 목록에서 통과한다 — 개수를 못 박는다.
    assert len(paired) == 2, f"인접면 쌍이 2개가 아니다: {[s.id for s in paired]}"
    a, b = paired
    assert a.adj == b.id and b.adj == a.id, "서로를 가리키지 않는다"
    assert {a.zone, b.zone} == {"Z1", "Z2"}, "쌍이 서로 다른 존에 붙어야 한다"
    for s in paired:
        assert s.adj != s.id, "자기 자신을 상대로 지정했다"
        assert s.sun == "NoSun" and s.wind == "NoWind"


def test_every_surface_belongs_to_a_declared_zone(record, tmp_path):
    zones = [{"id": "Z1", "floor": 1, "height": 3.0, "area": 20.0,
              "activityId": None, "isConditioned": True}]
    surfaces, _w = record(_payload([_wall("S1", SOUTH_WALL)], zones=zones), tmp_path)
    declared = {z["id"] for z in zones}
    for s in surfaces:
        assert s.zone in declared, f"{s.id} 이 선언되지 않은 존 {s.zone} 에 붙었다"


def test_each_surface_gets_its_own_construction(record, tmp_path):
    """면마다 U 값이 다를 수 있다 — 구성체를 공유하면 개별 개선이 반영되지 않는다."""
    surfaces, _w = record(_payload([
        _wall("S1", SOUTH_WALL, uValue=0.3),
        _wall("S2", NORTH_WALL, uValue=1.2),
    ]), tmp_path)
    assert len(surfaces) == 2, '면이 기록되지 않았다 — 빈 결과로 통과하면 안 된다'
    constructions = [s.construction for s in surfaces]
    assert len(set(constructions)) == len(constructions)


# ── 인접면 미러 형상 ─────────────────────────────────────
# ⚠️ EnergyPlus 는 짝이 되는 두 면의 정점이 **서로 역순**이어야 법선이 마주 본다.
# 같은 순서로 만들면 두 면이 등을 돌려 열이 엉뚱하게 흐른다.

def test_mirror_vertices_are_exactly_reversed(record, tmp_path):
    zones = [{"id": "Z1", "floor": 1, "height": 3.0, "area": 20.0,
              "activityId": None, "isConditioned": True},
             {"id": "Z2", "floor": 1, "height": 3.0, "area": 20.0,
              "activityId": None, "isConditioned": True}]
    surfaces, _w = record(_payload([
        {"id": "P1", "type": "InteriorWall", "zone": "Z1", "adjacentZone": "Z2",
         "vertices": NORTH_WALL, "uValue": 2.0, "area": 12.0},
    ], zones=zones), tmp_path)
    a, b = [s for s in surfaces if s.boundary == "Surface"]
    assert [tuple(v) for v in b.verts] == [tuple(v) for v in reversed(a.verts)]


def test_mirror_pair_shares_one_construction(record, tmp_path):
    """구성이 다르면 같은 벽이 양쪽에서 다른 U 값을 갖는다."""
    zones = [{"id": "Z1", "floor": 1, "height": 3.0, "area": 20.0,
              "activityId": None, "isConditioned": True},
             {"id": "Z2", "floor": 1, "height": 3.0, "area": 20.0,
              "activityId": None, "isConditioned": True}]
    surfaces, _w = record(_payload([
        {"id": "P1", "type": "InteriorWall", "zone": "Z1", "adjacentZone": "Z2",
         "vertices": NORTH_WALL, "uValue": 2.0, "area": 12.0},
    ], zones=zones), tmp_path)
    a, b = [s for s in surfaces if s.boundary == "Surface"]
    assert a.construction == b.construction


# ── 지면 승격 (opt-in) ───────────────────────────────────
# ⚠️ 세 조건(selfAdjacent · 바닥 · z≈0)이 **전부** 맞아야 한다. 하나라도 느슨하면
# 지하층·필로티·외기노출 바닥이 지면 접촉으로 오분류돼 열손실이 통째로 달라진다.

def _ground_boundary(record, tmp_path, surface, promote=True):
    surfaces, _w = record(
        _payload([surface], project={"promoteGroundFloors": promote}), tmp_path)
    return next(s for s in surfaces if s.id == surface["id"]).boundary


def test_ground_promotion_applies_when_all_conditions_hold(record, tmp_path):
    assert _ground_boundary(record, tmp_path, {
        "id": "F1", "type": "InteriorFloor", "zone": "Z1", "vertices": FLOOR,
        "uValue": 0.5, "area": 20.0, "selfAdjacent": True}) == "Ground"


def test_ground_promotion_is_off_by_default(record, tmp_path):
    """기본값이 켜져 있으면 오분류가 조용히 퍼진다."""
    assert _ground_boundary(record, tmp_path, {
        "id": "F1", "type": "InteriorFloor", "zone": "Z1", "vertices": FLOOR,
        "uValue": 0.5, "area": 20.0, "selfAdjacent": True},
        promote=False) == "Adiabatic"


@pytest.mark.parametrize("surface,why", [
    ({"id": "F1", "type": "InteriorFloor", "zone": "Z1", "vertices": FLOOR,
      "uValue": 0.5, "area": 20.0}, "selfAdjacent 아님"),
    ({"id": "F1", "type": "InteriorWall", "zone": "Z1", "vertices": SOUTH_WALL,
      "uValue": 0.5, "area": 12.0, "selfAdjacent": True}, "바닥 아님"),
    ({"id": "F1", "type": "InteriorFloor", "zone": "Z1",
      "vertices": [(0, 0, 3), (0, 5, 3), (4, 5, 3), (4, 0, 3)],
      "uValue": 0.5, "area": 20.0, "selfAdjacent": True}, "z≠0 (상층 바닥·필로티)"),
])
def test_ground_promotion_needs_every_condition(record, tmp_path, surface, why):
    assert _ground_boundary(record, tmp_path, surface) != "Ground", why


# ── 실측 opening 여러 개 ─────────────────────────────────

def _opening(x0, x1, z0=0.8, z1=2.2):
    return {"id": f"op_{x0}", "type": "FixedWindow",
            "vertices": [(x0, 0, z1), (x0, 0, z0), (x1, 0, z0), (x1, 0, z1)]}


# 벽 4×3=12㎡ 에 1.0×1.4 창 2개 = 2.8㎡ → 실측 WWR 23.3%.
# ⚠️ `wwr` 이 실측보다 1.5%p 넘게 크면 "확대"로 보고 합성 창 1개로 폴백한다
# (실형상 확대는 벽을 벗어나 E+ Severe 를 유발한다). 실측값을 그대로 준다.
MEASURED_WWR = 23


def test_multiple_openings_are_all_preserved(record, tmp_path):
    """⚠️ 실좌표가 있으면 개수·위치·모양을 보존해야 한다 — 하나로 합치면
    일사 분포가 달라진다."""
    wall = _wall("S1", SOUTH_WALL, wwr=MEASURED_WWR)
    wall["openings"] = [_opening(0.3, 1.3), _opening(2.3, 3.3)]
    _s, windows = record(_payload([wall]), tmp_path)
    assert len(windows) == 2


def test_second_window_gets_a_suffixed_name(record, tmp_path):
    """첫 창만 `Win_{면id}` 를 유지한다(AFN·surfaceAirflow 계약).
    나머지는 겹치지 않는 이름이어야 EnergyPlus 가 중복으로 죽지 않는다."""
    wall = _wall("S1", SOUTH_WALL, wwr=MEASURED_WWR)
    wall["openings"] = [_opening(0.3, 1.3), _opening(2.3, 3.3)]
    _s, windows = record(_payload([wall]), tmp_path)
    assert [w.id for w in windows] == ["Win_S1", "Win_S1_2"]


def test_air_openings_are_not_windows(record, tmp_path):
    """Air 개구부는 개방 경계이지 유리가 아니다 — 창으로 만들면 없던 일사가 생긴다."""
    wall = _wall("S1", SOUTH_WALL, wwr=MEASURED_WWR)
    wall["openings"] = [{**_opening(0.3, 1.3), "type": "Air"}]
    _s, windows = record(_payload([wall]), tmp_path)
    # 실좌표가 전부 Air 면 합성 창 폴백으로 1개만 생긴다
    assert len(windows) == 1
    assert windows[0].id == "Win_S1"


def test_enlarging_wwr_falls_back_to_a_synthetic_window(record, tmp_path):
    """⚠️ 실형상을 그대로 키우면 창이 벽을 벗어나 EnergyPlus 가 Severe 로 죽는다.
    실측보다 큰 WWR 을 요구하면 벽 중앙 합성 창 1개로 물러선다."""
    wall = _wall("S1", SOUTH_WALL, wwr=MEASURED_WWR + 40)
    wall["openings"] = [_opening(0.3, 1.3), _opening(2.3, 3.3)]
    _s, windows = record(_payload([wall]), tmp_path)
    assert len(windows) == 1
    wall_x = [p[0] for p in SOUTH_WALL]
    for p in windows[0].verts:
        assert min(wall_x) - 1e-6 <= p[0] <= max(wall_x) + 1e-6


# ── gbXML 이 선언한 지면 접촉 ────────────────────────────
# ⚠️ 예전에는 이 타입들을 경계조건 판정에서 **아예 안 봤다.** 짝이 없으면 무조건
# 외기 노출로 떨어져 **지면에 묻힌 슬래브가 햇빛과 바람을 받았다.**
# 실측: 회의실.xml `SlabOnGrade` 41면(IDF 표면적의 10.5%),
#       운동시설.xml `UndergroundSlab` 12면(35.8%).

@pytest.mark.parametrize("gbxml_type", [
    "SlabOnGrade", "UndergroundSlab", "UndergroundWall", "UndergroundCeiling",
    "slabongrade",          # 대소문자 무관
])
def test_declared_ground_contact_is_never_sun_exposed(record, tmp_path, gbxml_type):
    surfaces, _w = record(_payload([
        _wall("G1", FLOOR, type=gbxml_type)]), tmp_path)
    s = next(x for x in surfaces if x.id == "G1")
    assert (s.boundary, s.sun, s.wind) == ("Ground", "NoSun", "NoWind")


def test_ground_contact_does_not_need_the_opt_in_flag():
    """⚠️ `promoteGroundFloors` 와 혼동하면 안 된다.

    그쪽은 자기참조 최하층 바닥을 보고 **추정**하는 것이라 opt-in 이 맞다.
    여기는 gbXML 이 **선언**한 정보이므로 조건 없이 따라야 한다.
    """
    from src.simulation.geometry import GROUND_CONTACT_TYPES
    src = open(os.path.join(BACKEND, "src", "simulation", "geometry.py"),
               encoding="utf-8").read()
    # 선언 기반 판정이 promote_ground_floors 아래에 들어가 있으면 안 된다
    decl = src.index("GROUND_CONTACT_TYPES)")
    promote = src.index("if promote_ground_floors")
    assert decl > promote, "선언 기반 판정이 opt-in 분기보다 앞에 있으면 안 된다"
    assert len(GROUND_CONTACT_TYPES) >= 4


def test_declared_ground_wins_over_self_adjacent(record, tmp_path):
    """자기참조로 걷어낸 면이라도 타입이 지면 접촉이면 Ground 다."""
    surfaces, _w = record(_payload([
        _wall("G1", FLOOR, type="SlabOnGrade", selfAdjacent=True)]), tmp_path)
    assert next(x for x in surfaces if x.id == "G1").boundary == "Ground"


def test_raised_floor_stays_outdoors(record, tmp_path):
    """⚠️ `RaisedFloor` 는 필로티·주차장 위 바닥이라 **외기 노출이 맞다.**
    지면 접촉으로 잘못 넣으면 겨울 열손실이 사라진다."""
    surfaces, _w = record(_payload([_wall("R1", FLOOR, type="RaisedFloor")]), tmp_path)
    s = next(x for x in surfaces if x.id == "R1")
    assert (s.boundary, s.sun) == ("Outdoors", "SunExposed")


def test_explicit_override_still_wins_over_declared_type(record, tmp_path):
    """ASHRAE 140 처럼 표면별 지정이 필요한 경우가 있다."""
    surfaces, _w = record(_payload([
        _wall("G1", FLOOR, type="SlabOnGrade",
              boundaryCondition="Outdoors", sunExposure="NoSun", windExposure="NoWind")]),
        tmp_path)
    s = next(x for x in surfaces if x.id == "G1")
    assert (s.boundary, s.sun, s.wind) == ("Outdoors", "NoSun", "NoWind")


def test_interzone_pairing_still_wins(record, tmp_path):
    """양쪽 존이 유효하면 지면이 아니라 인접면이다 — 지하층 사이 슬래브."""
    zones = [{"id": "Z1", "floor": 1, "height": 3.0, "area": 20.0,
              "activityId": None, "isConditioned": True},
             {"id": "Z2", "floor": 2, "height": 3.0, "area": 20.0,
              "activityId": None, "isConditioned": True}]
    surfaces, _w = record(_payload([
        {"id": "P1", "type": "UndergroundSlab", "zone": "Z1", "adjacentZone": "Z2",
         "vertices": FLOOR, "uValue": 0.5, "area": 20.0}], zones=zones), tmp_path)
    assert [x for x in surfaces if x.boundary == "Surface"]
