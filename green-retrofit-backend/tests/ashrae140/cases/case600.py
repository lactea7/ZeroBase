"""ASHRAE 140 케이스 600 을 **우리 payload 형식**으로 표현한다 (Tier B).

수치는 전부 `stock_idf/case600.idf`(정식 생성본)에서 그대로 옮겼다.
값을 바꿀 일이 생기면 stock IDF 를 먼저 확인할 것 — 이 파일이 아니라 그쪽이 정본이다.

케이스 600 사양 요약:
  - 단일 존 8 m × 6 m × 2.7 m (바닥 48 ㎡, 체적 129.6 ㎥)
  - 경량 구조(LTWALL/LTROOF/LTFLOOR) — 900 시리즈와의 차이가 바로 이 열용량이다
  - 남향 창 3 m × 2 m 두 짝 = 12 ㎡ (남벽 21.6 ㎡ 의 55.56%)
  - 내부발열 순수 현열 200 W (잠열 0 / 복사 0.6)
  - 침기 0.5 ACH 상시
  - 설정온도 난방 20℃ / 냉방 27℃ 상시, 이상부하(용량 무제한·외기 0)
  - 바닥은 Outdoors + NoSun/NoWind (R-25 단열로 지면 결합 무시)
"""
from pathlib import Path

HERE = Path(__file__).resolve().parent
EPW = HERE.parent / "weather" / "725650TYCST.epw"

# ── 재료 (stock IDF 의 Material / Material:NoMass 와 1:1) ──
WOOD_SIDING = {"name": "WoodSiding", "roughness": "Rough", "thickness": 0.009,
               "conductivity": 0.14, "density": 530, "specificHeat": 900,
               "thermalAbsorptance": 0.9, "solarAbsorptance": 0.6, "visibleAbsorptance": 0.6}
FIBERGLASS_WALL = {"name": "FiberglassQuilt", "roughness": "Rough", "thickness": 0.066,
                   "conductivity": 0.04, "density": 12, "specificHeat": 840,
                   "thermalAbsorptance": 0.9, "solarAbsorptance": 0.6, "visibleAbsorptance": 0.6}
PLASTERBOARD_WALL = {"name": "Plasterboard", "roughness": "Rough", "thickness": 0.012,
                     "conductivity": 0.16, "density": 950, "specificHeat": 840,
                     "thermalAbsorptance": 0.9, "solarAbsorptance": 0.6, "visibleAbsorptance": 0.6}
ROOF_DECK = {"name": "RoofDeck", "roughness": "Rough", "thickness": 0.019,
             "conductivity": 0.14, "density": 530, "specificHeat": 900,
             "thermalAbsorptance": 0.9, "solarAbsorptance": 0.6, "visibleAbsorptance": 0.6}
FIBERGLASS_ROOF = {"name": "FiberglassQuiltRoof", "roughness": "Rough", "thickness": 0.1118,
                   "conductivity": 0.04, "density": 12, "specificHeat": 840,
                   "thermalAbsorptance": 0.9, "solarAbsorptance": 0.6, "visibleAbsorptance": 0.6}
PLASTERBOARD_ROOF = {"name": "PlasterboardRoof", "roughness": "Rough", "thickness": 0.010,
                     "conductivity": 0.16, "density": 950, "specificHeat": 840,
                     "thermalAbsorptance": 0.9, "solarAbsorptance": 0.6, "visibleAbsorptance": 0.6}
R25_INSULATION = {"name": "R25Insulation", "roughness": "Rough", "thermalResistance": 25.075,
                  "thermalAbsorptance": 0.9, "solarAbsorptance": 0.6, "visibleAbsorptance": 0.6}
TIMBER_FLOORING = {"name": "TimberFlooring", "roughness": "Rough", "thickness": 0.025,
                   "conductivity": 0.14, "density": 650, "specificHeat": 1200,
                   "thermalAbsorptance": 0.9, "solarAbsorptance": 0.6, "visibleAbsorptance": 0.6}

# 층 순서는 **바깥 → 안**
LTWALL = [WOOD_SIDING, FIBERGLASS_WALL, PLASTERBOARD_WALL]
LTROOF = [ROOF_DECK, FIBERGLASS_ROOF, PLASTERBOARD_ROOF]
LTFLOOR = [R25_INSULATION, TIMBER_FLOORING]

# ── 유리 (Double Pane Window: Glass Type 1 / Air 12mm / Glass Type 1) ──
GLASS = {"name": "GlassType1", "thickness": 0.003048,
         "solarTransmittance": 0.834, "solarReflectance": 0.075,
         "visibleTransmittance": 0.91325, "visibleReflectance": 0.082,
         "infraredTransmittance": 0.0, "emissivityFront": 0.84, "emissivityBack": 0.84,
         "conductivity": 1.0}
AIR_GAP = {"name": "AirGap", "gasType": "AIR", "thickness": 0.012}
DOUBLE_PANE = [GLASS, AIR_GAP, GLASS]

ZONE_ID = "ZONE ONE"
H = 2.7            # 층고
WALL_U_PLACEHOLDER = 0.5   # layers 가 있으면 쓰이지 않는다(합성 경로 비활성)


def _wall(sid, verts, direction, azimuth, wwr=0, openings=None):
    s = {
        "id": sid, "type": "ExteriorWall", "zone": ZONE_ID, "adjacentZone": None,
        "floor": 1, "direction": direction, "azimuth": azimuth,
        "vertices": verts, "uValue": WALL_U_PLACEHOLDER, "constructionRef": None,
        "wwr": wwr, "openings": openings or [], "layers": LTWALL,
    }
    if wwr:
        s["glazingLayers"] = DOUBLE_PANE
    return s


def build_payload() -> dict:
    """케이스 600 payload. `generate_idf_and_simulate(payload, tmp)` 에 그대로 넣는다."""
    # 남벽 21.6 ㎡ 중 창 12 ㎡ → 55.56%. build_window_geometries 의 규칙 1
    # (실좌표 보존)에 걸리려면 wwr 이 원본 비율과 1.5%p 이내여야 한다.
    south_openings = [
        {"id": "Win1", "type": "FixedWindow",
         "vertices": [[0.5, 0, 2.2], [0.5, 0, 0.2], [3.5, 0, 0.2], [3.5, 0, 2.2]]},
        {"id": "Win2", "type": "FixedWindow",
         "vertices": [[4.5, 0, 2.2], [4.5, 0, 0.2], [7.5, 0, 0.2], [7.5, 0, 2.2]]},
    ]

    surfaces = [
        _wall("SOUTH", [[0, 0, H], [0, 0, 0], [8, 0, 0], [8, 0, H]], "South", 180.0,
              wwr=round(12.0 / 21.6 * 100, 2), openings=south_openings),
        _wall("EAST", [[8, 0, H], [8, 0, 0], [8, 6, 0], [8, 6, H]], "East", 90.0),
        _wall("NORTH", [[8, 6, H], [8, 6, 0], [0, 6, 0], [0, 6, H]], "North", 0.0),
        _wall("WEST", [[0, 6, H], [0, 6, 0], [0, 0, 0], [0, 0, H]], "West", 270.0),
        {"id": "ROOF", "type": "Roof", "zone": ZONE_ID, "adjacentZone": None, "floor": 1,
         "direction": "Roof", "azimuth": 0.0,
         "vertices": [[8, 0, H], [8, 6, H], [0, 6, H], [0, 0, H]],
         "uValue": WALL_U_PLACEHOLDER, "wwr": 0, "openings": [], "layers": LTROOF},
        {"id": "FLOOR", "type": "Floor", "zone": ZONE_ID, "adjacentZone": None, "floor": 1,
         "direction": "Floor", "azimuth": 0.0,
         "vertices": [[8, 6, 0], [8, 0, 0], [0, 0, 0], [0, 6, 0]],
         "uValue": WALL_U_PLACEHOLDER, "wwr": 0, "openings": [], "layers": LTFLOOR,
         # 지면 결합을 무시하는 5.2절 관례 — 자동 추정으로는 나올 수 없는 조합이다
         "boundaryCondition": "Outdoors", "sunExposure": "NoSun", "windExposure": "NoWind"},
    ]

    zones = [{
        "id": ZONE_ID, "floor": 1, "height": H, "area": 48.0,
        "activityId": None, "isConditioned": True,
        "heatingSetpoint": 20.0, "coolingSetpoint": 27.0,
        # 자동 추정을 끄더라도 명시적으로 0 을 박아 의도를 남긴다
        "peopleDensity": 0.0, "lightingPower": 0.0, "equipmentPower": 0.0,
    }]

    return {
        "projectData": {
            "name": "ASHRAE140_Case600",
            "orientation": 0,
            "heatSource": 11,          # forceIdealLoads 로 덮인다
            "location": "ASHRAE140",
        },
        "zones": zones,
        "surfaces": surfaces,
        "benchmark": {
            "label": "ASHRAE 140 Case 600",
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
            "idealNoOutdoorAir": True,
            "idealNoHumidityControl": True,
            "otherEquipment": [
                {"designLevelW": 200.0, "fractionLatent": 0.0, "fractionRadiant": 0.6},
            ],
        },
    }
