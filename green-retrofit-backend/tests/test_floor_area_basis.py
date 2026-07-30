# 바닥면적 기준 — 내부발열 주입 기준과 면적당 지표 분모는 반드시 같은 값이어야 하고,
# gbXML이 선언한 <Space><Area>가 있으면 그것이 단일 기준이다.
#
# 기하 합산이 신뢰할 수 없는 이유: 층간 슬래브는 하나의 Surface 로 표현되고 그 면의
# space_1 존에만 귀속된다. 그래서 아래층 존은 바닥과 천장을 이중 계산하고(101 화장실
# 24.85 vs 선언 11.22) 최상층 존은 바닥을 아예 못 받는다.
import os
import tempfile

from src.ep_simulator import compute_zone_floor_areas
from src.gbxml_parser import parse_gbxml_to_json

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SAMPLE = os.path.join(REPO_ROOT, "용호동 파일 2.xml")

# 실제 파일 없이도 CI에서 회귀를 잡기 위한 인라인 픽스처.
# 바닥 4×5=20㎡ 인데 <Area>는 11.22 로 선언 — 선언값이 이기는지 본다.
GBXML = """<?xml version="1.0" encoding="UTF-8"?>
<gbXML xmlns="http://www.gbxml.org/schema" lengthUnit="{lu}" areaUnit="{au}">
  <Campus id="c1">
    <Building buildingType="Office" id="b1">
      <Name>t</Name>
      <Space id="sp-a" zoneIdRef="z-a">
        <Name>A실</Name>
        <Area>{area}</Area>
        <Volume>60</Volume>
      </Space>
    </Building>
    <Surface id="su-f" surfaceType="InteriorFloor">
      <Name>su-f</Name>
      <AdjacentSpaceId spaceIdRef="sp-a"/>
      <PlanarGeometry><PolyLoop>
        <CartesianPoint><Coordinate>0</Coordinate><Coordinate>0</Coordinate><Coordinate>0</Coordinate></CartesianPoint>
        <CartesianPoint><Coordinate>{w}</Coordinate><Coordinate>0</Coordinate><Coordinate>0</Coordinate></CartesianPoint>
        <CartesianPoint><Coordinate>{w}</Coordinate><Coordinate>{d}</Coordinate><Coordinate>0</Coordinate></CartesianPoint>
        <CartesianPoint><Coordinate>0</Coordinate><Coordinate>{d}</Coordinate><Coordinate>0</Coordinate></CartesianPoint>
      </PolyLoop></PlanarGeometry>
    </Surface>
  </Campus>
</gbXML>
"""


def _parse_inline(area="11.22", lu="Meters", au="SquareMeters", w=4, d=5):
    xml = GBXML.format(area=area, lu=lu, au=au, w=w, d=d)
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-8") as f:
        f.write(xml)
        path = f.name
    try:
        return parse_gbxml_to_json(path)
    finally:
        os.unlink(path)


def test_space_area_is_parsed_and_preferred():
    """<Space><Area>를 읽어 기하 면적(20㎡)보다 우선한다."""
    z = _parse_inline(area="11.22")["zones"][0]
    assert z["declaredArea"] == 11.22
    assert abs(z["geometricArea"] - 20.0) < 0.01
    assert z["area"] == 11.22


def test_area_unit_independent_of_length_unit():
    """areaUnit 이 lengthUnit 과 다른 파일에서 <Area>를 areaUnit 으로 환산한다.

    lengthUnit=Feet / areaUnit=SquareMeters 인 경우 11.22 는 이미 m² 이므로
    0.3048² 를 곱하면 안 된다 (약 90.7% 축소되는 버그).
    """
    z = _parse_inline(area="11.22", lu="Feet", au="SquareMeters")["zones"][0]
    assert abs(z["declaredArea"] - 11.22) < 0.01


def test_area_unit_squarefeet_converted():
    """areaUnit=SquareFeet 는 m² 로 환산한다 (100 sqft ≈ 9.29 m²)."""
    z = _parse_inline(area="100", lu="Feet", au="SquareFeet")["zones"][0]
    assert abs(z["declaredArea"] - 9.29) < 0.05


def test_nonfinite_declared_area_rejected():
    """NaN 등 유한하지 않은 선언값은 채택하지 않고 기하 면적으로 폴백한다."""
    z = _parse_inline(area="NaN")["zones"][0]
    assert z["declaredArea"] is None
    assert abs(z["area"] - 20.0) < 0.01


def test_tiny_declared_area_kept_but_warned():
    """0.5㎡ 미만이어도 버리지 않는다 — 샤프트·덕트 존이 실제로 존재한다.

    절대 하한으로 잘라내면 정상 소형 존을 부당하게 100㎡ 폴백으로 보낸다.
    대신 경고로 알린다.
    """
    r = _parse_inline(area="0.2")
    z = r["zones"][0]
    assert z["declaredArea"] == 0.2
    assert z["area"] == 0.2, "작아도 선언값을 그대로 쓴다"
    warns = [w for w in r.get("warnings", []) if w.get("issue") == "tiny_declared_area"]
    assert len(warns) == 1


def test_frontend_backend_share_validity_rule():
    """0.5~1.0㎡ 구간에서 백엔드가 선언값을 쓰면 프론트도 같은 값을 써야 한다.

    App.jsx getZoneFloorArea() 는 `Number.isFinite(declared) && declared > 0` 로
    판정한다. 백엔드도 같은 규칙이어야 화면과 시뮬레이션이 갈리지 않는다.
    (한쪽만 1.0㎡ 임계값을 쓰던 회귀를 잡는다)
    """
    for a in ("0.6", "0.9"):
        z = _parse_inline(area=a)["zones"][0]
        assert z["declaredArea"] == float(a)
        assert z["area"] == float(a), f"{a}㎡ 선언값이 백엔드에서 채택되지 않았다"


def test_unknown_area_unit_warns():
    """알 수 없는 areaUnit 은 조용히 넘기지 않고 경고한다."""
    r = _parse_inline(area="11.22", au="SquareCubits")
    warns = [w for w in r.get("warnings", []) if w.get("issue") == "unknown_area_unit"]
    assert len(warns) == 1
    assert "SquareCubits" in warns[0]["message"]


def test_mismatch_warning_from_inline_fixture():
    """선언 11.22 vs 기하 20.0 → 10% 초과 괴리이므로 경고가 나가야 한다."""
    warns = [w for w in _parse_inline(area="11.22").get("warnings", [])
             if w.get("issue") == "area_mismatch"]
    assert len(warns) == 1 and warns[0]["count"] == 1


def test_declared_area_wins_over_geometry():
    """선언 면적이 있으면 기하 면적 대신 그것을 쓴다."""
    zones = [{"id": "Z1", "declaredArea": 11.22, "geometricArea": 24.84}]
    surfaces = [{"zone": "Z1", "type": "InteriorFloor",
                 "vertices": [[0, 0, 0], [6, 0, 0], [6, 4, 0], [0, 4, 0]]}]  # 24㎡
    areas = compute_zone_floor_areas(zones, surfaces)
    assert areas["Z1"] == 11.22


def test_geometry_used_when_no_declared_area():
    """선언 면적이 없으면 기존대로 기하 합산으로 폴백한다."""
    zones = [{"id": "Z1"}]
    surfaces = [{"zone": "Z1", "type": "InteriorFloor",
                 "vertices": [[0, 0, 0], [6, 0, 0], [6, 4, 0], [0, 4, 0]]}]
    areas = compute_zone_floor_areas(zones, surfaces)
    assert abs(areas["Z1"] - 24.0) < 0.01


def test_ceiling_fallback_still_works():
    """바닥도 선언값도 없으면 천장/지붕으로 폴백 (EnergyPlus 객체 생성 실패 방지)."""
    zones = [{"id": "Z1"}]
    surfaces = [{"zone": "Z1", "type": "Roof",
                 "vertices": [[0, 0, 3], [5, 0, 3], [5, 4, 3], [0, 4, 3]]}]  # 20㎡
    areas = compute_zone_floor_areas(zones, surfaces)
    assert abs(areas["Z1"] - 20.0) < 0.01


def test_real_file_matches_declared_total():
    """실제 파일: 통일된 기준면적이 gbXML 선언 연면적과 일치해야 한다.

    이전에는 지표 분모 964.47㎡, 내부발열 기준 1,050.42㎡ 로 갈려 있었다.
    """
    if not os.path.exists(SAMPLE):
        import pytest
        pytest.skip("용호동 파일 2.xml 없음")

    result = parse_gbxml_to_json(SAMPLE)
    areas = compute_zone_floor_areas(result["zones"], result["surfaces"])
    total = sum(areas.values())
    assert abs(total - 864.37) < 1.0, f"선언 연면적 864.37㎡와 다름: {total:.2f}"


def test_real_file_has_no_area_mismatch_warning():
    """중심선 기준으로 정상 export 한 파일에는 면적 경고가 뜨지 않아야 한다.

    용호동 파일은 BIM에서 존 단위·중심선 기준으로 뽑은 정상 파일이다.
    함축 벽두께가 0.031~0.190m 로 전부 현실적 범위이므로 경고 대상이 아니다.
    예전에는 (1) 층간 슬래브 이중계산으로 도형 면적이 2배가 되고
    (2) 판정이 단순 10% 임계값이라 작은 실의 정상 편차(11%)까지 걸려
    10개 존이 오탐으로 걸렸다.
    """
    if not os.path.exists(SAMPLE):
        import pytest
        pytest.skip("용호동 파일 2.xml 없음")

    result = parse_gbxml_to_json(SAMPLE)
    warns = [w for w in result.get("warnings", []) if w.get("issue") == "area_mismatch"]
    assert warns == [], f"정상 파일에 면적 경고 오탐: {warns}"


def test_real_file_geometry_not_double_counted():
    """층간 슬래브 이중계산이 없어야 한다 — 1층 존의 도형 면적이 선언의 2배면 버그다."""
    if not os.path.exists(SAMPLE):
        import pytest
        pytest.skip("용호동 파일 2.xml 없음")

    result = parse_gbxml_to_json(SAMPLE)
    z = next(x for x in result["zones"] if x["id"] == "101 남자화장실")
    ratio = z["geometricArea"] / z["declaredArea"]
    assert ratio < 1.5, f"도형/선언 비율 {ratio:.2f} — 바닥과 천장을 함께 세고 있다"
    assert abs(z["geometricArea"] - 12.42) < 0.1


def test_implied_boundary_offset_explains_centerline_export():
    """중심선 편차는 둘레 × 경계 offset 으로 설명된다.

    이 관계가 성립하지 않으면 임계값의 근거가 무너진다.
    함수명이 implied_wall_thickness 였으나 실제 벽 두께가 아니라
    '모든 경계를 같은 거리만큼 평행이동한 유효 offset' 이므로 이름을 바꿨다.
    """
    from src.gbxml_parser import implied_boundary_offset
    # 선언 11.22㎡ / 도형 12.42㎡ / 둘레 17.0m → offset 14cm
    t = implied_boundary_offset(11.22, 12.42, 17.0)
    assert 0.10 < t < 0.20

    # 설명 불가한 차이(2배)는 비현실적 offset 으로 나온다
    t_bad = implied_boundary_offset(11.22, 24.84, 17.0)
    assert t_bad > 1.0


def test_zone_exposes_both_areas():
    """진단을 위해 선언·기하 면적을 모두 노출한다."""
    if not os.path.exists(SAMPLE):
        import pytest
        pytest.skip("용호동 파일 2.xml 없음")

    result = parse_gbxml_to_json(SAMPLE)
    z = next(x for x in result["zones"] if x["id"] == "101 남자화장실")
    assert z["declaredArea"] == 11.22
    assert z["geometricArea"] > z["declaredArea"], "이중 계산된 기하 면적이 더 커야 한다"
    assert z["area"] == z["declaredArea"], "사용 면적은 선언값이어야 한다"


def test_warnings_carry_severity_and_unit():
    """모든 경고에 severity/countUnit/action 이 있어야 프런트가 바르게 표시한다.

    예전에는 UI 가 count 를 무조건 '개 면'으로 찍어, 존 단위 경고(area_mismatch 10개 실)를
    '10개 면'으로 잘못 보여줬다.
    """
    r = _parse_inline(area="11.22")
    warns = r.get("warnings", [])
    assert warns
    for w in warns:
        assert w.get("severity") in ("info", "warn", "choice", "block"), w
        assert w.get("countUnit"), f"countUnit 없음: {w}"
        assert w.get("action"), f"action 없음: {w}"


def test_unknown_area_unit_is_blocking():
    """인식 못 한 areaUnit 은 추측으로 진행하면 안 된다 — 차단 등급이어야 한다."""
    r = _parse_inline(area="11.22", au="SquareCubits")
    w = next(x for x in r["warnings"] if x["issue"] == "unknown_area_unit")
    assert w["severity"] == "block"


def test_declared_area_wins_regardless_of_mismatch_flag():
    """선언 면적 채택은 10% 검사와 무관하다 — 불일치 경고는 진단일 뿐이다."""
    # 기하 20㎡ vs 선언 19.5㎡ → 10% 미만이라 경고는 없지만 선언값을 쓴다
    z = _parse_inline(area="19.5")["zones"][0]
    assert z["area"] == 19.5


def test_open_stairwell_footprint_from_air_boundary():
    """개방 계단실은 층간에 슬래브가 없고 수평 Air 경계로 표현된다.

    Floor/Slab 만 보면 이런 존의 평면 윤곽이 0㎡ 가 되어 교차검증에서 조용히 빠진다.
    용호동의 203/303/403/501 계단실이 실제로 그랬다.
    """
    from src.gbxml_parser import compute_zone_floor_geometry
    surfaces = [{
        "id": "air-boundary", "type": "Air",
        "zone": "아래층계단실", "adjacentZone": "위층계단실",
        "area": 16.2,
        "vertices": [[0, 0, 3.7], [4, 0, 3.7], [4, 4.05, 3.7], [0, 4.05, 3.7]],
    }]
    g = compute_zone_floor_geometry(surfaces, footprint=True)
    assert g["위층계단실"][0] > 0, "Air 경계가 윤곽 후보로 인정되지 않았다"

    # 열적 바닥면(Floor/Slab)으로는 여전히 잡히지 않아야 한다 — 실제로 슬래브가 없다
    g_thermal = compute_zone_floor_geometry(surfaces, footprint=False)
    assert "위층계단실" not in g_thermal or g_thermal["위층계단실"][0] == 0


def test_real_file_all_zones_have_footprint():
    """20개 존 전부 평면 윤곽이 계산돼야 한다.

    이전에는 개방 계단실 4개가 0㎡ 로 빠져 교차검증 대상이 16개뿐이었다.
    """
    if not os.path.exists(SAMPLE):
        import pytest
        pytest.skip("용호동 파일 2.xml 없음")

    from src.gbxml_parser import compute_zone_floor_geometry
    result = parse_gbxml_to_json(SAMPLE)
    g = compute_zone_floor_geometry(result["surfaces"])
    missing = [z["id"] for z in result["zones"] if g.get(z["id"], (0, 0))[0] <= 0]
    assert missing == [], f"윤곽 미계산 존: {missing}"


def test_simulator_reuses_parser_geometry():
    """선언 면적이 없으면 시뮬레이터가 파서 계산값을 써야 한다.

    각자 계산하면 파서는 보정값(12.42), 시뮬레이터는 이중계산(24.84)을 쓰게 된다.
    """
    zones = [{"id": "Z1", "geometricArea": 12.42}]
    surfaces = [
        {"zone": "Z1", "type": "InteriorFloor",
         "vertices": [[0, 0, 0], [4, 0, 0], [4, 3.1, 0], [0, 3.1, 0]]},
        {"zone": "Z1", "type": "InteriorFloor",   # 천장 역할 — 이중계산 유발원
         "vertices": [[0, 0, 3], [4, 0, 3], [4, 3.1, 3], [0, 3.1, 3]]},
    ]
    areas = compute_zone_floor_areas(zones, surfaces)
    assert areas["Z1"] == 12.42, f"파서 값을 쓰지 않고 재계산했다: {areas['Z1']}"
