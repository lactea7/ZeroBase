"""ASHRAE 140 5.2절 케이스를 **우리 payload 형식**으로 표현한다 (Tier B).

수치는 전부 `stock_idf/case*.idf`(정식 생성본)에서 옮겼다.
값을 고칠 일이 생기면 stock IDF 를 먼저 확인할 것 — 이 파일이 아니라 그쪽이 정본이다.

공통 형상: 단일 존 8 m × 6 m × 2.7 m (바닥 48 ㎡, 체적 129.6 ㎥)
공통 조건: 내부발열 순수 현열 200 W(잠열 0 / 복사 0.6), 침기 0.5 ACH 상시,
          설정온도 20/27℃ 상시, 이상부하(용량 무제한·외기 0),
          바닥은 Outdoors + NoSun/NoWind (R-25 단열로 지면 결합 무시)

케이스별 차이 — **이 차이 하나만 격리해서 보는 것이 델타 검사의 핵심이다.**
  600  경량 기준
  620  창을 남향 12 ㎡ → 동·서 각 6 ㎡ (방위)
  900  경량 → 중량 구조 (열용량)
  610  600 + 남벽 1 m 돌출 차양
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
EPW = HERE.parent / "weather" / "725650TYCST.epw"

_OPT = {"thermalAbsorptance": 0.9, "solarAbsorptance": 0.6, "visibleAbsorptance": 0.6}


def _mat(name, thickness, conductivity, density, specific_heat, roughness="Rough"):
    return {"name": name, "roughness": roughness, "thickness": thickness,
            "conductivity": conductivity, "density": density,
            "specificHeat": specific_heat, **_OPT}


# ── 재료 (stock IDF 의 Material / Material:NoMass 와 1:1) ──
WOOD_SIDING = _mat("WoodSiding", 0.009, 0.14, 530, 900)
FIBERGLASS_WALL = _mat("FiberglassQuilt", 0.066, 0.04, 12, 840)
PLASTERBOARD_WALL = _mat("Plasterboard", 0.012, 0.16, 950, 840)
ROOF_DECK = _mat("RoofDeck", 0.019, 0.14, 530, 900)
FIBERGLASS_ROOF = _mat("FiberglassQuiltRoof", 0.1118, 0.04, 12, 840)
PLASTERBOARD_ROOF = _mat("PlasterboardRoof", 0.010, 0.16, 950, 840)
TIMBER_FLOORING = _mat("TimberFlooring", 0.025, 0.14, 650, 1200)
CONCRETE_BLOCK = _mat("ConcreteBlock", 0.100, 0.51, 1400, 1000)
CONCRETE_SLAB = _mat("ConcreteSlab", 0.080, 1.13, 1400, 1000)
FOAM_INSULATION = _mat("FoamInsulation", 0.0615, 0.04, 10, 1400)
R25_LT = {"name": "R25InsulationLt", "roughness": "Rough", "thermalResistance": 25.075, **_OPT}
R25_HW = {"name": "R25InsulationHw", "roughness": "Rough", "thermalResistance": 25.175, **_OPT}

# 층 순서는 **바깥 → 안**
LTWALL = [WOOD_SIDING, FIBERGLASS_WALL, PLASTERBOARD_WALL]
LTROOF = [ROOF_DECK, FIBERGLASS_ROOF, PLASTERBOARD_ROOF]
LTFLOOR = [R25_LT, TIMBER_FLOORING]
HWWALL = [WOOD_SIDING, FOAM_INSULATION, CONCRETE_BLOCK]
HWFLOOR = [R25_HW, CONCRETE_SLAB]

# ── 유리 (Double Pane Window: Glass Type 1 / Air 12 mm / Glass Type 1) ──
GLASS = {"name": "GlassType1", "thickness": 0.003048,
         "solarTransmittance": 0.834, "solarReflectance": 0.075,
         "visibleTransmittance": 0.91325, "visibleReflectance": 0.082,
         "infraredTransmittance": 0.0, "emissivityFront": 0.84, "emissivityBack": 0.84,
         "conductivity": 1.0}
AIR_GAP = {"name": "AirGap", "gasType": "AIR", "thickness": 0.012}
DOUBLE_PANE = [GLASS, AIR_GAP, GLASS]

ZONE_ID = "ZONE ONE"
H = 2.7
U_PLACEHOLDER = 0.5      # layers 가 있으면 쓰이지 않는다(U-value 합성 경로 비활성)

# 벽 좌표 (바깥에서 본 반시계). stock IDF 와 동일.
WALL_VERTS = {
    "SOUTH": [[0, 0, H], [0, 0, 0], [8, 0, 0], [8, 0, H]],
    "EAST": [[8, 0, H], [8, 0, 0], [8, 6, 0], [8, 6, H]],
    "NORTH": [[8, 6, H], [8, 6, 0], [0, 6, 0], [0, 6, H]],
    "WEST": [[0, 6, H], [0, 6, 0], [0, 0, 0], [0, 0, H]],
}
WALL_META = {"SOUTH": ("South", 180.0), "EAST": ("East", 90.0),
             "NORTH": ("North", 0.0), "WEST": ("West", 270.0)}

# 창 (stock IDF 좌표 그대로)
SOUTH_WINDOWS = [
    [[0.5, 0, 2.2], [0.5, 0, 0.2], [3.5, 0, 0.2], [3.5, 0, 2.2]],
    [[4.5, 0, 2.2], [4.5, 0, 0.2], [7.5, 0, 0.2], [7.5, 0, 2.2]],
]
EAST_WINDOW = [[[8, 1.5, 2.2], [8, 1.5, 0.2], [8, 4.5, 0.2], [8, 4.5, 2.2]]]
WEST_WINDOW = [[[0, 4.5, 2.2], [0, 4.5, 0.2], [0, 1.5, 0.2], [0, 1.5, 2.2]]]

# 케이스 정의 — 기준(600)에서 무엇만 바꾸는지가 한눈에 보이게 둔다
CASE_SPECS = {
    "600": {"wall": LTWALL, "floor": LTFLOOR, "windows": {"SOUTH": SOUTH_WINDOWS}},
    "620": {"wall": LTWALL, "floor": LTFLOOR,
            "windows": {"EAST": EAST_WINDOW, "WEST": WEST_WINDOW}},
    "900": {"wall": HWWALL, "floor": HWFLOOR, "windows": {"SOUTH": SOUTH_WINDOWS}},
    "610": {"wall": LTWALL, "floor": LTFLOOR, "windows": {"SOUTH": SOUTH_WINDOWS},
            # 남벽 상단에서 1 m 돌출, 폭 8 m
            "shading": [{"id": "SouthOverhang",
                         "vertices": [[8, 0, H], [8, -1, H], [0, -1, H], [0, 0, H]]}]},
}


def _polygon_area_xz(verts):
    """직사각형 창 면적. 벽면 위 4점이므로 인접 두 변의 길이를 곱한다."""
    import math

    def d(a, b):
        return math.dist(a, b)
    return d(verts[0], verts[1]) * d(verts[1], verts[2])


def build_payload(case: str) -> dict:
    """케이스 payload. `generate_idf_and_simulate(payload, tmp)` 에 그대로 넣는다."""
    spec = CASE_SPECS[case]
    wall_layers, floor_layers = spec["wall"], spec["floor"]

    surfaces = []
    for name, verts in WALL_VERTS.items():
        direction, azimuth = WALL_META[name]
        wins = spec["windows"].get(name)
        s = {
            "id": name, "type": "ExteriorWall", "zone": ZONE_ID, "adjacentZone": None,
            "floor": 1, "direction": direction, "azimuth": azimuth,
            "vertices": verts, "uValue": U_PLACEHOLDER, "constructionRef": None,
            "wwr": 0, "openings": [], "layers": wall_layers,
        }
        if wins:
            wall_area = 8 * H if name in ("SOUTH", "NORTH") else 6 * H
            win_area = sum(_polygon_area_xz(w) for w in wins)
            # build_window_geometries 의 규칙 1(실좌표 보존)에 걸리려면
            # wwr 이 원본 비율과 1.5%p 이내여야 한다.
            s["wwr"] = round(win_area / wall_area * 100, 2)
            s["openings"] = [{"id": f"{name}_Win{i}", "type": "FixedWindow", "vertices": w}
                             for i, w in enumerate(wins)]
            s["glazingLayers"] = DOUBLE_PANE
        surfaces.append(s)

    surfaces.append({
        "id": "ROOF", "type": "Roof", "zone": ZONE_ID, "adjacentZone": None, "floor": 1,
        "direction": "Roof", "azimuth": 0.0,
        "vertices": [[8, 0, H], [8, 6, H], [0, 6, H], [0, 0, H]],
        "uValue": U_PLACEHOLDER, "wwr": 0, "openings": [], "layers": LTROOF,
    })
    surfaces.append({
        "id": "FLOOR", "type": "Floor", "zone": ZONE_ID, "adjacentZone": None, "floor": 1,
        "direction": "Floor", "azimuth": 0.0,
        "vertices": [[8, 6, 0], [8, 0, 0], [0, 0, 0], [0, 6, 0]],
        "uValue": U_PLACEHOLDER, "wwr": 0, "openings": [], "layers": floor_layers,
        # 지면 결합을 무시하는 5.2절 관례 — 자동 추정으로는 나올 수 없는 조합이다
        "boundaryCondition": "Outdoors", "sunExposure": "NoSun", "windExposure": "NoWind",
    })

    payload = {
        "projectData": {
            "name": f"ASHRAE140_Case{case}", "orientation": 0,
            "heatSource": 11,            # forceIdealLoads 로 덮인다
            "location": "ASHRAE140",
        },
        "zones": [{
            "id": ZONE_ID, "floor": 1, "height": H, "area": 48.0,
            "activityId": None, "isConditioned": True,
            "heatingSetpoint": 20.0, "coolingSetpoint": 27.0,
            "peopleDensity": 0.0, "lightingPower": 0.0, "equipmentPower": 0.0,
        }],
        "surfaces": surfaces,
        "benchmark": {
            "label": f"ASHRAE 140 Case {case}",
            "weatherFile": str(EPW),
            "timestep": 6,                                  # stock IDF 와 동일
            "solarDistribution": "FullInteriorAndExterior",
            "terrain": "Country",
            "minWarmupDays": 6,
            "infiltrationAch": 0.5,
            "disableAirflowNetwork": True,
            "suppressAutoLoads": True,
            "constantSetpoints": True,
            "forceIdealLoads": True,
            # ⚠️ ASHRAE 140 은 **차양 없음**을 사양으로 못 박는다. 600 vs 610 의
            # 유일한 차이가 외부 차양이므로, 내부 블라인드가 붙으면 그 델타가
            # 오염되고 참조값과 비교 자체가 성립하지 않는다.
            "noInteriorBlind": True,
            "idealNoOutdoorAir": True,
            "idealNoHumidityControl": True,
            "otherEquipment": [
                {"designLevelW": 200.0, "fractionLatent": 0.0, "fractionRadiant": 0.6},
            ],
        },
    }
    if spec.get("shading"):
        payload["shadingSurfaces"] = spec["shading"]
    return payload
