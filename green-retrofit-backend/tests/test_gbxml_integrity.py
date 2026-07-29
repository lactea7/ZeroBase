# gbXML 무결성(P0) 검증.
#
# 참조가 모호하거나 기하가 성립하지 않으면 이후 계산 전체가 무의미하다.
# 이런 입력은 '경고 후 진행'이 아니라 차단해야 한다.
import os
import tempfile

from src.gbxml_parser import parse_gbxml_to_json

HEAD = """<?xml version="1.0" encoding="UTF-8"?>
<gbXML xmlns="http://www.gbxml.org/schema" lengthUnit="Meters" areaUnit="SquareMeters">
  <Campus id="c1">
    <Building buildingType="Office" id="b1">
      <Name>t</Name>
{spaces}
    </Building>
{surfaces}
  </Campus>
</gbXML>
"""

SPACE = """      <Space id="{sid}" zoneIdRef="z-{sid}">
        <Name>{name}</Name>
        <Area>20</Area>
        <Volume>60</Volume>
      </Space>"""


def _poly(pts):
    return "<PolyLoop>" + "".join(
        f"<CartesianPoint><Coordinate>{x}</Coordinate>"
        f"<Coordinate>{y}</Coordinate><Coordinate>{z}</Coordinate></CartesianPoint>"
        for x, y, z in pts) + "</PolyLoop>"


def _surface(sid, adj, pts, stype="ExteriorWall", openings=""):
    adj_xml = "".join(f'<AdjacentSpaceId spaceIdRef="{a}"/>' for a in adj)
    return f"""    <Surface id="{sid}" surfaceType="{stype}">
      <Name>{sid}</Name>
      {adj_xml}
      <PlanarGeometry>{_poly(pts)}</PlanarGeometry>
      {openings}
    </Surface>"""


WALL = [(0, 0, 0), (4, 0, 0), (4, 0, 3), (0, 0, 3)]      # 12㎡


def _parse(spaces_xml, surfaces_xml):
    xml = HEAD.format(spaces=spaces_xml, surfaces=surfaces_xml)
    with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False, encoding="utf-8") as f:
        f.write(xml)
        path = f.name
    try:
        return parse_gbxml_to_json(path)
    finally:
        os.unlink(path)


def _issues(result, issue):
    return [w for w in result.get("warnings", []) if w.get("issue") == issue]


def test_duplicate_surface_id_blocks():
    """같은 id 를 가진 Surface 가 있으면 참조가 모호해 차단해야 한다."""
    r = _parse(SPACE.format(sid="sp-a", name="A"),
               _surface("dup", ["sp-a"], WALL) + "\n" + _surface("dup", ["sp-a"], WALL))
    w = _issues(r, "duplicate_id")
    assert len(w) == 1 and w[0]["severity"] == "block"


def test_opening_larger_than_host_blocks():
    """창 면적이 벽 면적을 넘으면 기하가 성립하지 않는다.

    예전에는 WWR 을 90% 로 조용히 잘라내 오류를 감췄다.
    """
    big = [(0, 0, 0), (5, 0, 0), (5, 0, 4), (0, 0, 4)]   # 20㎡ > 벽 12㎡
    op = f'<Opening id="op1" openingType="FixedWindow"><PlanarGeometry>{_poly(big)}</PlanarGeometry></Opening>'
    r = _parse(SPACE.format(sid="sp-a", name="A"),
               _surface("su1", ["sp-a"], WALL, openings=op))
    w = _issues(r, "opening_exceeds_host")
    assert len(w) == 1 and w[0]["severity"] == "block"


def test_dangling_adjacent_reference_warns():
    """두 번째 참조만 끊기면 인접관계만 사라진다 → warn."""
    r = _parse(SPACE.format(sid="sp-a", name="A"),
               _surface("su1", ["sp-a", "sp-없음"], WALL, stype="InteriorWall"))
    w = _issues(r, "dangling_adjacent_space_reference")
    assert len(w) == 1 and w[0]["severity"] == "warn"


def test_dangling_primary_reference_blocks():
    """첫 번째 참조가 끊기면 zone 이 Unknown 이 되어 면이 통째로 제외된다 → block.

    외피가 사라지므로 경고만 하고 진행시키면 안 된다.
    """
    r = _parse(SPACE.format(sid="sp-a", name="A"),
               _surface("su1", ["sp-없음"], WALL))
    w = _issues(r, "dangling_primary_space_reference")
    assert len(w) == 1 and w[0]["severity"] == "block"


def test_too_few_vertices_is_detected():
    """꼭짓점 2개 면도 감지돼야 한다.

    파서가 len(vertices) < 3 에서 continue 하므로 그 이후에 수집하면 영원히 도달하지
    못한다 — 실제로 그 버그가 있었다.
    """
    line = [(0, 0, 0), (4, 0, 0)]
    r = _parse(SPACE.format(sid="sp-a", name="A"), _surface("su1", ["sp-a"], line))
    w = _issues(r, "degenerate_polygon")
    assert len(w) == 1
    assert "꼭짓점 부족" in w[0]["action"]


def test_duplicate_material_id_blocks():
    """Material/Construction/WindowType 중복도 잡아야 한다.

    이들은 dict 에 조용히 덮어써지며 U-value·재료비·창 성능을 바꾼다.
    Surface/Space 만 검사하면 놓친다.
    """
    mats = ('<Material id="m-dup"><Name>a</Name></Material>'
            '<Material id="m-dup"><Name>b</Name></Material>')
    r = _parse(SPACE.format(sid="sp-a", name="A"),
               _surface("su1", ["sp-a"], WALL) + mats)
    w = _issues(r, "duplicate_id")
    assert len(w) == 1 and w[0]["severity"] == "block"


def test_degenerate_polygon_warns():
    """꼭짓점이 부족하거나 면적이 0인 면은 외피·비용에서 빠지므로 알린다."""
    flat = [(0, 0, 0), (4, 0, 0), (8, 0, 0)]   # 일직선 → 면적 0
    r = _parse(SPACE.format(sid="sp-a", name="A"),
               _surface("su1", ["sp-a"], flat))
    w = _issues(r, "degenerate_polygon")
    assert len(w) == 1 and w[0]["severity"] == "warn"


def test_clean_file_has_no_integrity_warnings():
    """정상 파일에서는 무결성 경고가 뜨지 않는다 (오탐 방지)."""
    r = _parse(SPACE.format(sid="sp-a", name="A"),
               _surface("su1", ["sp-a"], WALL))
    for issue in ("duplicate_id", "opening_exceeds_host",
                  "dangling_primary_space_reference",
                  "dangling_adjacent_space_reference", "degenerate_polygon"):
        assert _issues(r, issue) == [], f"{issue} 오탐"


def test_real_file_passes_integrity():
    """실제 업무 파일에는 P0 무결성 문제가 없어야 한다."""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sample = os.path.join(repo_root, "용호동 파일 2.xml")
    if not os.path.exists(sample):
        import pytest
        pytest.skip("용호동 파일 2.xml 없음")

    r = parse_gbxml_to_json(sample)
    blocking = [w for w in r.get("warnings", []) if w.get("severity") == "block"]
    assert blocking == [], f"차단 경고 발생: {[w['issue'] for w in blocking]}"
