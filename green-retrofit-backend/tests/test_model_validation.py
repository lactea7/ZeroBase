# 시뮬레이션 진입점의 무결성 검증 (신뢰 경계).
#
# 업로드 모달의 '그대로 진행' 차단은 클라이언트 UX 일 뿐이다. 다른 클라이언트나
# 변조된 요청은 그 화면을 거치지 않고 /api/simulate 로 직접 들어올 수 있다.
import pytest
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


def test_duplicate_zone_id_blocks():
    """파서가 Space.Name 을 zone id 로 쓰므로 Name 이 겹치면 payload 에서 충돌한다.

    XML 의 Space id 가 고유해도 잡히지 않는다 — 이 검사는 payload 단계에만 있을 수 있다.
    zone_ids 를 바로 set 으로 만들면 중복을 잃어 이 케이스를 놓친다.
    """
    blocking, _ = validate_simulation_payload(
        [_zone("같은이름"), _zone("같은이름")], [_surf(zone="같은이름")])
    assert any(b["issue"] == "duplicate_zone_id" for b in blocking)


def test_empty_ids_block():
    blocking, _ = validate_simulation_payload([{"id": "", "area": 20.0}], [_surf()])
    assert any(b["issue"] == "empty_zone_id" for b in blocking)

    blocking, _ = validate_simulation_payload(
        [_zone()], [{"id": "", "zone": "Z1", "vertices": WALL, "openings": []}])
    assert any(b["issue"] == "empty_surface_id" for b in blocking)


def test_invalid_declared_and_geometric_area_block():
    """area 뿐 아니라 declaredArea·geometricArea 도 검사해야 한다.

    시뮬레이터가 declaredArea → geometricArea 순으로 신뢰하므로
    이 값이 오염되면 그대로 부하·분모에 쓰인다.
    """
    for field in ("declaredArea", "geometricArea"):
        blocking, _ = validate_simulation_payload(
            [{"id": "Z1", "area": 20.0, field: -5.0}], [_surf()])
        assert any(b["issue"] == "invalid_zone_area" for b in blocking), field

        blocking, _ = validate_simulation_payload(
            [{"id": "Z1", "area": 20.0, field: float("inf")}], [_surf()])
        assert any(b["issue"] == "invalid_zone_area" for b in blocking), field


def test_geometric_area_drift_blocks():
    """클라이언트가 보낸 도형 면적을 그대로 믿지 않는다.

    서버가 surfaces 로 재계산해 크게 어긋나면 막는다 (변조·버전 불일치 방어).
    """
    # 실제 바닥 4×5=20㎡ 인데 200㎡ 라고 주장
    floor = {"id": "F1", "zone": "Z1", "type": "InteriorFloor", "openings": [],
             "vertices": [[0, 0, 0], [4, 0, 0], [4, 5, 0], [0, 5, 0]]}
    blocking, _ = validate_simulation_payload(
        [{"id": "Z1", "geometricArea": 200.0}], [floor])
    assert any(b["issue"] == "geometric_area_drift" for b in blocking)


def test_geometric_area_within_tolerance_passes():
    """허용오차 안이면 통과한다 (반올림·버전차 오탐 방지)."""
    floor = {"id": "F1", "zone": "Z1", "type": "InteriorFloor", "openings": [],
             "vertices": [[0, 0, 0], [4, 0, 0], [4, 5, 0], [0, 5, 0]]}
    blocking, _ = validate_simulation_payload(
        [{"id": "Z1", "geometricArea": 20.3}], [floor])
    assert not any(b["issue"] == "geometric_area_drift" for b in blocking)


# ── 좌표 유한성 (신뢰 경계) ───────────────────────────────────────────────────
#
# ⚠️ 파서는 이걸 `non_finite_geometry`(severity block)로 잡지만 그 검사는 **XML
# 경로에만** 있다. `/api/simulate` 는 payload 를 직접 받으므로 그 관문을 지나지 않는다.
# 실측: NaN·Inf 좌표가 blocking 0 으로 통과했고, 실제 요청은 422 가 아니라
# **500 Internal Server Error** 로 안쪽에서 터졌다.

NAN = float("nan")
INF = float("inf")
_OK = [(0, 0, 0), (4, 0, 0), (4, 0, 3), (0, 0, 3)]
_ZONES = [{"id": "Z1", "area": 20.0, "height": 3.0, "floor": 1}]


def _payload_with(verts, openings=None):
    return _ZONES, [{"id": "S1", "type": "ExteriorWall", "zone": "Z1",
                     "vertices": verts, "area": 12.0, "uValue": 0.5,
                     "openings": openings or []}]


def _issues(verts, openings=None):
    from src.model_validation import validate_simulation_payload
    z, s = _payload_with(verts, openings)
    blocking, _w = validate_simulation_payload(z, s)
    return [b["issue"] for b in blocking]


def test_finite_geometry_passes():
    assert "non_finite_geometry" not in _issues(_OK)


@pytest.mark.parametrize("label,verts", [
    ("NaN",      [(0, 0, 0), (NAN, 0, 0), (4, 0, 3), (0, 0, 3)]),
    ("Inf",      [(0, 0, 0), (INF, 0, 0), (4, 0, 3), (0, 0, 3)]),
    ("-Inf",     [(0, 0, 0), (-INF, 0, 0), (4, 0, 3), (0, 0, 3)]),
    ("None",     [(0, 0, 0), (None, 0, 0), (4, 0, 3), (0, 0, 3)]),
    ("문자열",    [(0, 0, 0), ("x", 0, 0), (4, 0, 3), (0, 0, 3)]),
    ("2차원 점",  [(0, 0), (4, 0), (4, 3), (0, 3)]),
    ("점이 아님", [0, 1, 2, 3]),
])
def test_non_finite_geometry_is_blocked(label, verts):
    """⚠️ NaN 은 **비교가 전부 False** 라 면적·초과 검사를 조용히 지나간다.
    다른 검사에 기대면 안 되고 명시적으로 잡아야 한다."""
    assert "non_finite_geometry" in _issues(verts), f"{label} 이 통과했다"


def test_non_finite_opening_is_blocked():
    """개구부 좌표만 망가져도 막아야 한다 — 벽은 멀쩡해 보인다."""
    assert "non_finite_geometry" in _issues(
        _OK, [{"vertices": [(0, 0, 0), (NAN, 0, 0), (1, 0, 1)]}])


def test_validator_never_raises_on_malformed_geometry():
    """⚠️ **이게 500 의 원인이었다.** 검증기가 예외를 던지면 신뢰 경계가 무너지고
    FastAPI 가 422 대신 500 을 낸다."""
    from src.model_validation import validate_simulation_payload
    for verts in ([(0, 0, 0), (None, 0, 0), (4, 0, 3), (0, 0, 3)],
                  [(0, 0, 0), ("x", 0, 0), (4, 0, 3), (0, 0, 3)],
                  [(0, 0), (4, 0), (4, 3)], None, "쓰레기", 42):
        z, s = _payload_with(verts)
        validate_simulation_payload(z, s)   # 예외가 나면 실패


def test_area_helper_is_defensive():
    """공용 헬퍼가 방어적이어야 모든 호출부가 함께 보호된다."""
    from src.model_validation import _area
    assert _area([(0, 0, 0), (None, 0, 0), (4, 0, 3)]) == 0.0
    assert _area([(0, 0, 0), (NAN, 0, 0), (4, 0, 3)]) == 0.0
    assert _area(None) == 0.0
    assert _area(_OK) > 0.0
