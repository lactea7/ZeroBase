"""응답 canonical snapshot — 계약 시험의 세 번째 층.

⚠️ **전체 응답을 snapshot 하지 않는다.** surface 데이터가 면 수 × 12개월이라
경고 문구 한 줄만 바뀌어도 diff 가 수천 줄이 되고, 그러면 아무도 안 읽는다.
**면 2개만 남긴 축소 응답**을 고정해 구조와 대표값을 함께 지킨다.

실행마다 달라지는 것(경고 순서 등)은 정규화한다.
값이 바뀌면 `UPDATE_SNAPSHOT=1` 로 갱신하고 **diff 를 커밋에 남긴다**.
"""
import difflib
import json
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

SNAPSHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "golden", "response.json")

# snapshot 에 남길 면 수. 구조를 보기엔 2개면 충분하다.
SURFACE_SAMPLE = 2


def _canonical(result):
    """비교 가능한 형태로 줄인다 — 면 표본만 남기고 키를 정렬한다."""
    def sample(mapping):
        return {k: mapping[k] for k in sorted(mapping)[:SURFACE_SAMPLE]}

    financial = dict(result["financial"])
    # 경고는 순서가 흔들릴 수 있다 — 정렬해 비교한다
    financial["cost_warnings"] = sorted(financial.get("cost_warnings", []))
    # 권고는 별도 시험이 덮는다. 여기선 개수와 타입만 남긴다.
    financial["recommendations"] = [
        {"type": r.get("type"), "direction": r.get("direction")}
        for r in financial.get("recommendations", [])
    ]
    # 단열 상세는 면 수만큼 길다 — 개수만 남긴다
    financial["insulation_details"] = len(financial.get("insulation_details", []))

    return {
        "summary": result["summary"],
        "monthly": result["monthly"],
        "matrix": result["matrix"],
        "financial": financial,
        "surfaceThermal": sample(result["surfaceThermal"]),
        "surfaceAirflow": sample(result["surfaceAirflow"]),
    }


@pytest.fixture(scope="module")
def canonical(analyzer, base_kwargs):
    return _canonical(analyzer.calculate(**base_kwargs))


def test_response_matches_snapshot(canonical):
    os.makedirs(os.path.dirname(SNAPSHOT), exist_ok=True)
    text = json.dumps(canonical, ensure_ascii=False, indent=1, sort_keys=True) + "\n"

    if os.environ.get("UPDATE_SNAPSHOT") == "1" or not os.path.exists(SNAPSHOT):
        with open(SNAPSHOT, "w", encoding="utf-8") as fh:
            fh.write(text)
        pytest.skip(f"snapshot 갱신: {SNAPSHOT} — diff 를 커밋에 남길 것")

    with open(SNAPSHOT, encoding="utf-8") as fh:
        expected = fh.read()

    if text != expected:
        diff = "\n".join(difflib.unified_diff(
            expected.splitlines(), text.splitlines(),
            fromfile="snapshot", tofile="현재", lineterm="", n=2))
        pytest.fail(
            "응답이 snapshot 과 다르다.\n"
            "의도한 변경이면 UPDATE_SNAPSHOT=1 로 갱신하고 diff 를 커밋에 남길 것.\n\n"
            + diff[:5000])


def test_snapshot_is_json_serialisable(canonical):
    """응답이 그대로 직렬화돼야 한다 — NaN·Infinity 는 JSON 이 아니다."""
    text = json.dumps(canonical, allow_nan=False)
    assert "NaN" not in text and "Infinity" not in text
