"""생성 IDF golden — **리팩터링 안전망**.

구조 분리는 "순수 이동"이어야 한다. 파일을 옮기다 동작이 바뀌면 즉시 잡혀야 하는데,
기존 시험은 대부분 결과 숫자만 보므로 **IDF 조립 과정의 미세한 변화**(객체 순서,
빠진 필드, 스케줄 이름, 기본값)는 통과해 버린다.

이 시험은 조립된 IDF 전체를 문자열로 고정한다. EnergyPlus 를 돌리지 않아 1초 이내다.

golden 이 바뀌면:
  - **의도한 변경**이면 `UPDATE_GOLDEN=1 pytest ...` 로 갱신하고 diff 를 커밋에 남긴다.
  - **의도하지 않았다면 순수 이동이 아니다.** 중단하고 원인을 찾을 것.
"""
import difflib
import os
import re
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(BACKEND, "src"))

GOLDEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")
H = 3.0


def _wall(sid, verts, direction, azimuth, zone, wwr=0):
    return {"id": sid, "type": "ExteriorWall", "zone": zone, "adjacentZone": None,
            "floor": 1, "direction": direction, "azimuth": azimuth, "vertices": verts,
            "uValue": 0.47, "constructionRef": None, "wwr": wwr, "openings": []}


def representative_payload() -> dict:
    """여러 경로를 한 번에 지나가는 대표 payload.

    - 공조 존 + 비공조 존 (아키타입이 다르다: office / auxiliary)
    - 창 있는 벽 / 없는 벽
    - 존 간 인접면 (Surface 경계)
    - 지붕·바닥
    - 연료 HVAC 경로(heatSource=11 → UnitHeater + WindowAC)
    """
    zones = [
        {"id": "OFFICE", "floor": 1, "height": H, "area": 48.0, "activityId": 1105,
         "isConditioned": True, "heatingSetpoint": 20.0, "coolingSetpoint": 26.0},
        {"id": "STAIR", "floor": 1, "height": H, "area": 12.0, "activityId": 1101,
         "isConditioned": False, "heatingSetpoint": 18.0, "coolingSetpoint": 28.0},
    ]
    surfaces = [
        _wall("S_SOUTH", [[0, 0, H], [0, 0, 0], [8, 0, 0], [8, 0, H]], "South", 180.0,
              "OFFICE", wwr=30),
        _wall("S_EAST", [[8, 0, H], [8, 0, 0], [8, 6, 0], [8, 6, H]], "East", 90.0, "OFFICE"),
        _wall("S_WEST", [[0, 6, H], [0, 6, 0], [0, 0, 0], [0, 0, H]], "West", 270.0, "OFFICE"),
        # 존 간 경계 — Surface 경계조건으로 나가야 한다
        {"id": "S_PARTY", "type": "InteriorWall", "zone": "OFFICE", "adjacentZone": "STAIR",
         "floor": 1, "direction": "North", "azimuth": 0.0,
         "vertices": [[8, 6, H], [8, 6, 0], [0, 6, 0], [0, 6, H]],
         "uValue": 1.2, "wwr": 0, "openings": []},
        _wall("S_STAIR_N", [[8, 8, H], [8, 8, 0], [0, 8, 0], [0, 8, H]], "North", 0.0, "STAIR"),
        {"id": "S_ROOF", "type": "Roof", "zone": "OFFICE", "adjacentZone": None, "floor": 1,
         "direction": "Roof", "azimuth": 0.0,
         "vertices": [[8, 0, H], [8, 6, H], [0, 6, H], [0, 0, H]],
         "uValue": 0.29, "wwr": 0, "openings": []},
        {"id": "S_FLOOR", "type": "Floor", "zone": "OFFICE", "adjacentZone": None, "floor": 1,
         "direction": "Floor", "azimuth": 0.0,
         "vertices": [[8, 6, 0], [8, 0, 0], [0, 0, 0], [0, 6, 0]],
         "uValue": 0.41, "wwr": 0, "openings": []},
    ]
    return {
        "projectData": {"name": "GoldenFixture", "location": "KOR_Seoul",
                        "heatSource": 11, "orientation": 0},
        "zones": zones, "surfaces": surfaces, "materials": {},
    }


# 실행마다 달라지는 것은 비교에서 뺀다 — 경로·시각은 동작 변화가 아니다.
_VOLATILE = [
    (re.compile(r"^! EnergyPlus Version:.*$", re.M), "! EnergyPlus Version: <PINNED>"),
    (re.compile(r"/private/tmp/[^\s,;]*"), "<TMP>"),
    (re.compile(r"/var/folders/[^\s,;]*"), "<TMP>"),
]


def _normalize(text: str) -> str:
    for pattern, repl in _VOLATILE:
        text = pattern.sub(repl, text)
    return text.strip() + "\n"


@pytest.fixture(scope="module")
def assembled_idf(tmp_path_factory) -> str:
    """IDF 조립 직후 가로채 문자열로 받는다 — EnergyPlus 는 돌리지 않는다."""
    import ep_simulator

    tmp = tmp_path_factory.mktemp("golden")
    captured = {}

    def fake_run(self, weather_file, out_dir):
        captured["idf"] = "\n".join(o.to_idf() for o in self.objects)
        raise RuntimeError("stop-after-assembly")

    original = ep_simulator.IdfBuilder.run
    ep_simulator.IdfBuilder.run = fake_run
    try:
        try:
            ep_simulator.generate_idf_and_simulate(representative_payload(), str(tmp))
        except Exception:
            pass
    finally:
        ep_simulator.IdfBuilder.run = original

    assert "idf" in captured, "IDF 조립 전에 실패했다"
    return _normalize(captured["idf"])


def test_generated_idf_matches_golden(assembled_idf):
    """조립된 IDF 가 golden 과 한 글자도 다르지 않아야 한다."""
    os.makedirs(GOLDEN_DIR, exist_ok=True)
    path = os.path.join(GOLDEN_DIR, "representative.idf")

    if os.environ.get("UPDATE_GOLDEN") == "1" or not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(assembled_idf)
        pytest.skip(f"golden 갱신: {path} — diff 를 커밋에 남길 것")

    with open(path, encoding="utf-8") as fh:
        expected = fh.read()

    if assembled_idf != expected:
        diff = "\n".join(difflib.unified_diff(
            expected.splitlines(), assembled_idf.splitlines(),
            fromfile="golden", tofile="현재", lineterm="", n=2))
        pytest.fail(
            "생성 IDF 가 golden 과 다르다 — **순수 이동이 아니다.**\n"
            "의도한 변경이면 UPDATE_GOLDEN=1 로 갱신하고 diff 를 커밋에 남길 것.\n\n"
            + diff[:6000]
        )


def test_golden_covers_key_paths(assembled_idf):
    """golden 이 실제로 여러 경로를 지나가는지 — 빈 껍데기를 고정하면 의미가 없다."""
    for token, why in [
        ("ZoneInfiltration:DesignFlowRate", "고정 침기"),
        ("ZoneHVAC:UnitHeater", "연료 난방 실기기"),
        ("FenestrationSurface:Detailed", "창 생성"),
        ("Lights,", "용도별 자동 조명"),
        ("ElectricEquipment,", "용도별 자동 기기"),
        ("Schedule:Compact", "아키타입 스케줄"),
        ("Site:GroundTemperature:BuildingSurface", "지중온도"),
        ("Construction,", "구성체 합성"),
    ]:
        assert token in assembled_idf, f"golden 이 {why} 경로를 안 지난다 ({token})"
    # 존 간 경계가 Surface 로 나갔는지 (Outdoors 로 새면 없던 외피가 생긴다)
    assert "S_PARTY" in assembled_idf
