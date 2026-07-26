# gbXML 경계조건 변환 규칙 — 특히 익스포터 결함(자기참조 인접)에 대한 방어.
#
# 일부 익스포터는 최하층 바닥을 SlabOnGrade 대신 같은 Space를 AdjacentSpaceId로
# 두 번 적은 InteriorFloor 로 내보낸다. 이를 그대로 인접관계로 받으면 시뮬레이터가
# 같은 Zone 안에 원본+미러 쌍을 만들어 '자기 자신과 맞닿은 내부면'이 생긴다.
import os
import tempfile

from src.gbxml_parser import parse_gbxml_to_json

GBXML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<gbXML xmlns="http://www.gbxml.org/schema" lengthUnit="Meters" areaUnit="SquareMeters">
  <Campus id="cmps-1">
    <Building buildingType="Office" id="bldg-1">
      <Name>테스트</Name>
      <Space id="sp-a" zoneIdRef="zone-a">
        <Name>A실</Name>
        <Area>20.0</Area>
        <Volume>60.0</Volume>
      </Space>
      <Space id="sp-b" zoneIdRef="zone-b">
        <Name>B실</Name>
        <Area>20.0</Area>
        <Volume>60.0</Volume>
      </Space>
    </Building>
    {surfaces}
  </Campus>
</gbXML>
"""

SURFACE = """
    <Surface id="{sid}" surfaceType="{stype}">
      <Name>{sid}</Name>
      {adj}
      <PlanarGeometry>
        <PolyLoop>
          <CartesianPoint><Coordinate>0</Coordinate><Coordinate>0</Coordinate><Coordinate>{z}</Coordinate></CartesianPoint>
          <CartesianPoint><Coordinate>4</Coordinate><Coordinate>0</Coordinate><Coordinate>{z}</Coordinate></CartesianPoint>
          <CartesianPoint><Coordinate>4</Coordinate><Coordinate>5</Coordinate><Coordinate>{z}</Coordinate></CartesianPoint>
          <CartesianPoint><Coordinate>0</Coordinate><Coordinate>5</Coordinate><Coordinate>{z}</Coordinate></CartesianPoint>
        </PolyLoop>
      </PlanarGeometry>
    </Surface>
"""


def _adj(*space_ids):
    return "\n      ".join(f'<AdjacentSpaceId spaceIdRef="{s}"/>' for s in space_ids)


def _parse(surfaces_xml):
    xml = GBXML_TEMPLATE.format(surfaces=surfaces_xml)
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-8") as f:
        f.write(xml)
        path = f.name
    try:
        return parse_gbxml_to_json(path)
    finally:
        os.unlink(path)


def _by_id(result, sid):
    return next(s for s in result["surfaces"] if s["id"] == sid)


def test_self_adjacent_surface_loses_adjacency():
    """같은 Space가 AdjacentSpaceId에 두 번 → 인접관계를 버린다.

    남겨두면 ep_simulator가 같은 Zone 안에 원본+미러 쌍을 만든다.
    """
    result = _parse(SURFACE.format(sid="su-self", stype="InteriorFloor",
                                   adj=_adj("sp-a", "sp-a"), z=0))
    surf = _by_id(result, "su-self")
    assert surf["adjacentZone"] is None, "자기참조 인접은 제거되어야 한다"
    assert surf["zone"] is not None, "소속 Zone 자체는 유지되어야 한다"


def test_genuine_adjacency_is_preserved():
    """서로 다른 Space 간의 정상 인접관계는 그대로 둔다 (과잉 방어 금지)."""
    result = _parse(SURFACE.format(sid="su-ab", stype="InteriorWall",
                                   adj=_adj("sp-a", "sp-b"), z=0))
    surf = _by_id(result, "su-ab")
    assert surf["adjacentZone"] is not None
    assert surf["adjacentZone"] != surf["zone"]


def test_single_adjacency_untouched():
    """AdjacentSpaceId가 하나뿐인 외벽은 영향받지 않는다."""
    result = _parse(SURFACE.format(sid="su-ext", stype="ExteriorWall",
                                   adj=_adj("sp-a"), z=0))
    surf = _by_id(result, "su-ext")
    assert surf["adjacentZone"] is None


def test_self_adjacent_warning_reaches_api_result():
    """경고가 warnings 에 실려 나가야 한다 — 표준출력만으로는 사용자가 볼 수 없다."""
    result = _parse(SURFACE.format(sid="su-self", stype="InteriorFloor",
                                   adj=_adj("sp-a", "sp-a"), z=0))
    warns = [w for w in result.get("warnings", [])
             if w.get("issue") == "self_adjacent_surface"]
    assert len(warns) == 1, "자기참조 면 경고가 warnings 에 없다"

    w = warns[0]
    assert w["count"] == 1
    assert "su-self" in w["surfaces"]
    assert w["message"], "사용자에게 보여줄 message 가 비어 있다"
    # 지면 열손실 누락이라는 핵심 정보가 문구에 남아 있어야 한다
    assert "지면" in w["message"]


def test_warning_schema_matches_frontend_branch():
    """프론트(App.jsx)는 w.issue === 'not_enclosed' 로 분기한다.

    갭 경고에 issue 가 없거나 자기참조 경고에 message 가 없으면 모달이 빈 칸이 된다.
    """
    result = _parse(SURFACE.format(sid="su-self", stype="InteriorFloor",
                                   adj=_adj("sp-a", "sp-a"), z=0))
    for w in result.get("warnings", []):
        assert "issue" in w, f"issue 필드 없음: {w}"
        if w["issue"] == "not_enclosed":
            assert "zone" in w and "deviation" in w
        else:
            assert w.get("message"), f"message 없는 비-갭 경고: {w}"


def test_no_warning_when_adjacency_is_clean():
    """정상 인접만 있으면 자기참조 경고가 뜨지 않는다 (오탐 방지)."""
    result = _parse(SURFACE.format(sid="su-ab", stype="InteriorWall",
                                   adj=_adj("sp-a", "sp-b"), z=0))
    warns = [w for w in result.get("warnings", [])
             if w.get("issue") == "self_adjacent_surface"]
    assert warns == []


def test_self_adjacent_air_surface_is_not_exposed_outdoors():
    """타입에 'interior'가 없는 Air 면도 외기 노출로 빠지면 안 된다.

    ep_simulator는 `"interior" in t or adj_zone_raw or selfAdjacent` 로 Adiabatic을
    판정한다. adjacentZone을 비운 뒤 selfAdjacent 플래그가 없으면 Air 면은
    Outdoors/SunExposed가 되어 없던 외피와 일사 취득이 생긴다.
    """
    result = _parse(SURFACE.format(sid="su-air", stype="Air",
                                   adj=_adj("sp-a", "sp-a"), z=0))
    surf = _by_id(result, "su-air")
    assert surf["adjacentZone"] is None
    assert surf.get("selfAdjacent") is True, "Air 면에 selfAdjacent 플래그가 없다"

    # ep_simulator 의 경계조건 판정과 동일한 식으로 확인
    t = surf.get("type", "").lower()
    assert "interior" not in t, "이 테스트는 타입에 interior가 없는 면을 전제로 한다"
    is_adiabatic = bool("interior" in t or surf.get("adjacentZone") or surf.get("selfAdjacent"))
    assert is_adiabatic, "자기참조 Air 면이 외기 노출로 처리된다"


def test_normal_surface_has_no_self_adjacent_flag():
    """정상 면에는 플래그가 서지 않아야 한다 (과잉 방어 금지)."""
    result = _parse(SURFACE.format(sid="su-ab", stype="InteriorWall",
                                   adj=_adj("sp-a", "sp-b"), z=0))
    assert _by_id(result, "su-ab").get("selfAdjacent") is False


def test_real_file_self_adjacent_types():
    """실제 파일의 자기참조 면에는 타입과 무관하게 전부 플래그가 서야 한다."""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sample = os.path.join(repo_root, "용호동 파일 2.xml")
    if not os.path.exists(sample):
        import pytest
        pytest.skip("용호동 파일 2.xml 없음 (저장소 미추가 상태)")

    result = parse_gbxml_to_json(sample)
    flagged = [s for s in result["surfaces"] if s.get("selfAdjacent")]
    assert len(flagged) == 19, f"자기참조 면 19개를 기대했으나 {len(flagged)}개"
    # InteriorFloor 9 / InteriorWall 7 / Air 3 — Air 가 섞여 있는 것이 이 방어의 요점
    assert any("air" in s.get("type", "").lower() for s in flagged), \
        "Air 자기참조 면이 감지되지 않았다 (이 케이스가 외기 노출 회귀의 원인)"


def test_real_file_self_adjacent_count():
    """실제 업무 파일(용호동)에 자기참조 면이 있고 전부 걸러지는지 확인."""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sample = os.path.join(repo_root, "용호동 파일 2.xml")
    if not os.path.exists(sample):
        import pytest
        pytest.skip("용호동 파일 2.xml 없음 (저장소 미추가 상태)")

    result = parse_gbxml_to_json(sample)
    bad = [s for s in result["surfaces"]
           if s.get("adjacentZone") and s.get("adjacentZone") == s.get("zone")]
    assert bad == [], f"자기 자신과 인접한 면이 남아있다: {[s['id'] for s in bad][:5]}"
