# 시뮬레이션 진입점의 무결성 검증 (신뢰 경계).
#
# 업로드 모달의 '그대로 진행' 차단은 클라이언트 UX 일 뿐이다. 다른 클라이언트나
# 변조된 요청은 그 화면을 거치지 않고 /api/simulate 로 직접 들어올 수 있다.
from src.model_validation import validate_simulation_payload

WALL = [[0, 0, 0], [4, 0, 0], [4, 0, 3], [0, 0, 3]]      # 12㎡
BIG = [[0, 0, 0], [5, 0, 0], [5, 0, 4], [0, 0, 4]]       # 20㎡


def _zone(zid="Z1", area=20.0):
    return {"id": zid, "area": area}


def _surf(sid="S1", zone="Z1", verts=None, openings=None):
    return {"id": sid, "zone": zone, "vertices": verts or WALL,
            "openings": openings or []}


def test_clean_payload_passes():
    blocking, warns = validate_simulation_payload([_zone()], [_surf()])
    assert blocking == [] and warns == []


def test_no_zones_blocks():
    blocking, _ = validate_simulation_payload([], [_surf()])
    assert any(b["issue"] == "no_zones" for b in blocking)


def test_duplicate_surface_id_blocks():
    """EnergyPlus 객체명이 충돌해 결과가 뒤섞인다."""
    blocking, _ = validate_simulation_payload(
        [_zone()], [_surf("dup"), _surf("dup")])
    assert any(b["issue"] == "duplicate_surface_id" for b in blocking)


def test_opening_exceeding_host_blocks():
    """업로드 검증을 우회해도 여기서 막혀야 한다."""
    s = _surf(openings=[{"vertices": BIG}])
    blocking, _ = validate_simulation_payload([_zone()], [s])
    assert any(b["issue"] == "opening_exceeds_host" for b in blocking)


def test_opening_within_tolerance_passes():
    """좌표 반올림 수준의 미세 초과는 통과해야 한다 (오탐 방지)."""
    almost = [[0, 0, 0], [4, 0, 0], [4, 0, 3.001], [0, 0, 3.001]]   # 12.004㎡
    s = _surf(openings=[{"vertices": almost}])
    blocking, _ = validate_simulation_payload([_zone()], [s])
    assert not any(b["issue"] == "opening_exceeds_host" for b in blocking)


def test_invalid_zone_area_blocks():
    """면적이 음수·NaN 이면 면적당 지표의 분모가 무너진다."""
    blocking, _ = validate_simulation_payload(
        [{"id": "Z1", "area": -5.0}], [_surf()])
    assert any(b["issue"] == "invalid_zone_area" for b in blocking)

    blocking, _ = validate_simulation_payload(
        [{"id": "Z1", "area": float("nan")}], [_surf()])
    assert any(b["issue"] == "invalid_zone_area" for b in blocking)


def test_orphan_surface_warns_not_blocks():
    """없는 존에 속한 면은 제외될 뿐이라 경고로 충분하다."""
    blocking, warns = validate_simulation_payload(
        [_zone("Z1")], [_surf("S1", zone="Z없음")])
    assert blocking == []
    assert any(w["issue"] == "orphan_surface" for w in warns)
