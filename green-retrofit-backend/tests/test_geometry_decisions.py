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

# 4x5 바닥의 남향 외벽 (z 0~3)
SOUTH_WALL = [(0, 0, 3), (0, 0, 0), (4, 0, 0), (4, 0, 3)]
NORTH_WALL = [(4, 5, 3), (4, 5, 0), (0, 5, 0), (0, 5, 3)]
FLOOR = [(0, 0, 0), (0, 5, 0), (4, 5, 0), (4, 0, 0)]


@pytest.fixture
def record(monkeypatch):
    """payload → (표면 호출들, 창 호출들). EnergyPlus 는 돌리지 않는다."""
    import ep_simulator

    def _run(payload, tmp_path):
        surfaces, windows, errors = [], [], []

        # ⚠️ **시그니처가 실제 호출과 정확히 같아야 한다.** 인접면 경로는
        # `adj_surface_id=` 를 키워드로 넘기는데 예전 fake 는 `adj=` 였다.
        # TypeError 가 나면 `generate_idf_and_simulate` 가 그것을 자체적으로
        # `RuntimeError("EnergyPlus 시뮬레이션 실패")` 로 바꿔 던지므로 **타입으로는
        # 구분할 수 없다.** 그래서 fake 안에서 난 오류를 따로 모아 검사한다.
        # (예전엔 이걸 안 해서 인접면 시험이 빈 리스트로 통과하고 있었다)
        def _guard(fn):
            def wrapper(*args, **kwargs):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:      # noqa: BLE001 - 아래에서 반드시 다시 올린다
                    errors.append(f"{fn.__name__}: {e!r}")
                    raise
            return wrapper

        @_guard
        def fake_surface(self, surface_id, ep_type, construction, zone_id,
                         boundary, sun, wind, vertices, adj_surface_id=""):
            surfaces.append(SurfaceCall(surface_id, ep_type, construction, zone_id,
                                        boundary, sun, wind, vertices, adj_surface_id))
            return self

        @_guard
        def fake_window(self, window_id, construction, parent_surface, vertices):
            windows.append(WindowCall(window_id, construction, parent_surface, vertices))
            return self

        def stop(self, weather_file, out_dir):
            raise RuntimeError("stop-after-assembly")

        monkeypatch.setattr(ep_simulator.IdfBuilder, "add_surface", fake_surface)
        monkeypatch.setattr(ep_simulator.IdfBuilder, "add_window", fake_window)
        monkeypatch.setattr(ep_simulator.IdfBuilder, "run", stop)
        try:
            ep_simulator.generate_idf_and_simulate(payload, str(tmp_path))
        except Exception:
            pass    # EnergyPlus 실행은 일부러 막았다 — 조립까지만 본다

        assert not errors, f"기록용 fake 가 실제 호출과 맞지 않는다: {errors}"
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
    constructions = [s.construction for s in surfaces]
    assert len(set(constructions)) == len(constructions)
