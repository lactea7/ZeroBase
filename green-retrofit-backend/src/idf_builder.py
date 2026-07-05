# src/idf_builder.py
# imugi.py의 IDF 객체 패턴을 참고한 IDF 빌더 클래스
# - EnergyPlus IDF 파일을 객체 지향적으로 생성
# - 필드 검증 및 에러 방지 내장

import os
import math
import re

# ---------------------------------------------------------------------------- #
#                    IDD 필드 순서 인덱스 (dict→positional 평탄화)               #
# ---------------------------------------------------------------------------- #
# idragon 등은 객체를 {필드명: 값} dict로 작성하지만 우리 빌더는 위치(positional)
# 리스트로 emit한다. 실기기 HVAC(VRF/보일러/지역난방 등)는 필드가 수십 개라
# 위치를 손으로 맞추면 한 칸만 밀려도 물리 오류/Fatal이 난다. → EnergyPlus IDD를
# 파싱해 객체별 '필드명 순서'를 얻고, dict를 그 순서대로 평탄화한다.

_IDD_PATHS = [
    "/Applications/EnergyPlus-25-2-0/Energy+.idd",
    "/usr/local/EnergyPlus-25-2-0/Energy+.idd",
    "/usr/local/bin/Energy+.idd",
]
_IDD_INDEX_CACHE = None  # {obj_type_lower: {"fields": [names...], "min": int}}


def _get_idd_index():
    """Energy+.idd를 1회 파싱해 {객체타입(소문자): {fields:[필드명...], min:최소필드수}} 반환."""
    global _IDD_INDEX_CACHE
    if _IDD_INDEX_CACHE is not None:
        return _IDD_INDEX_CACHE
    idd_path = next((p for p in _IDD_PATHS if os.path.exists(p)), None)
    if idd_path is None:
        # 환경변수 폴백
        env = os.environ.get("ENERGYPLUS_IDD")
        if env and os.path.exists(env):
            idd_path = env
    index = {}
    if idd_path is None:
        _IDD_INDEX_CACHE = index
        return index

    obj_header = re.compile(r"^([A-Za-z][A-Za-z0-9:_]*)\s*,\s*$")
    field_line = re.compile(r"^\s+[AN]\d+\s*[,;]\s*\\field\s+(.+?)\s*$")
    minf_line = re.compile(r"^\s+\\min-fields\s+(\d+)")

    cur = None
    with open(idd_path, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.rstrip("\n")
            m = obj_header.match(line)
            if m:
                cur = {"fields": [], "min": 0}
                index[m.group(1).lower()] = cur
                continue
            if cur is None:
                continue
            fm = field_line.match(line)
            if fm:
                cur["fields"].append(fm.group(1).strip())
                continue
            mm = minf_line.match(line)
            if mm:
                cur["min"] = int(mm.group(1))
    _IDD_INDEX_CACHE = index
    return index


class IdfObject:
    """EnergyPlus IDF 단일 객체 (imugi의 IdfObject 패턴 차용)"""

    def __init__(self, obj_type: str, fields: list):
        self.obj_type = obj_type
        self.fields = fields

    def to_idf(self) -> str:
        """IDF 텍스트로 변환"""
        if not self.fields:
            return f"{self.obj_type};\n"
        
        lines = [f"{self.obj_type},"]
        for i, field in enumerate(self.fields):
            terminator = ";" if i == len(self.fields) - 1 else ","
            val = "" if field is None else str(field)
            lines.append(f"  {val}{terminator}")
        
        return "\n".join(lines) + "\n"


class IdfBuilder:
    """EnergyPlus IDF 빌더 (imugi의 IDF 클래스 패턴 차용)
    
    사용 예시:
        idf = IdfBuilder(version="25.2")
        idf.add("Building", ["MyBuilding", 0, "Suburbs", 0.04, 0.4, "FullExterior", 25, 6])
        idf.add("Zone", ["Zone1", 0, 0, 0, 0, 1, 1, 3.0])
        idf.write("output.idf")
        idf.run(weather_file, output_dir)
    """

    def __init__(self, version: str = "25.2"):
        self.version = version
        self.objects: list[IdfObject] = []
        # 실기기 HVAC 누적 상태 (idragon의 postprocessor 대체: 누적→finalize_hvac에서 일괄 emit)
        self._vrf_sources: dict = {}   # source_name -> {"terminals": [term_name,...]}
        # zone_id -> [(obj_type, name, cool_seq, heat_seq), ...] — 존당 여러 기기 지원
        self._zone_equip: dict = {}
        # zone_id -> {"inlets": [node,...], "exhausts": [node,...]} (2개 이상이면 NodeList로 emit)
        self._zone_nodes: dict = {}
        self._add_header()

    def _add_header(self):
        """필수 헤더 객체 추가"""
        self.add("Version", [self.version])
        self.add("SimulationControl", ["No", "No", "No", "No", "Yes"])
        self.add("SurfaceConvectionAlgorithm:Inside", ["TARP"])
        self.add("SurfaceConvectionAlgorithm:Outside", ["DOE-2"])
        self.add("HeatBalanceAlgorithm", ["ConductionTransferFunction"])
        self.add("Timestep", [4])
        self.add("GlobalGeometryRules", ["UpperLeftCorner", "CounterClockwise", "World"])

    def add(self, obj_type: str, fields: list = None) -> "IdfBuilder":
        """IDF 객체 추가 (체이닝 지원)"""
        self.objects.append(IdfObject(obj_type, fields or []))
        return self

    def _emit_by_idd(self, obj_type: str, field_dict: dict) -> "IdfBuilder":
        """{필드명: 값} dict를 IDD 필드 순서대로 위치 리스트로 평탄화해 추가.

        - 미설정 필드는 "" 로 채움(마지막 설정 필드 또는 \\min-fields 까지).
        - field_dict 키가 IDD에 없으면 ValueError(오타·버전 불일치 조기 발견).
        - IDD를 못 찾으면 RuntimeError(이 경로는 IDD 기반 객체 emit을 요구).
        """
        idx = _get_idd_index().get(obj_type.lower())
        if idx is None or not idx["fields"]:
            raise RuntimeError(
                f"IDD에서 '{obj_type}' 필드 정의를 찾지 못했습니다 "
                f"(Energy+.idd 경로 확인 필요)."
            )
        names = idx["fields"]
        pos = {n: i for i, n in enumerate(names)}
        # 키 검증
        unknown = [k for k in field_dict if k not in pos]
        if unknown:
            raise ValueError(
                f"'{obj_type}' IDD에 없는 필드: {unknown}\n사용 가능 필드 일부: {names[:8]}..."
            )
        if not field_dict:
            last = 0
        else:
            last = max(pos[k] for k in field_dict) + 1
        length = max(last, idx.get("min", 0))
        fields = []
        for i in range(length):
            v = field_dict.get(names[i], "")
            fields.append("" if v is None else v)
        return self.add(obj_type, fields)

    # -------------------------------------------------------
    # 도메인 특화 메서드 (imugi의 set_wwr, rename 패턴 참고)
    # -------------------------------------------------------

    def add_building(self, name: str, orientation: float = 0):
        """Building 객체 추가"""
        return self.add("Building", [
            name, orientation, "Suburbs", 0.04, 0.4, "FullExterior", 25, 6
        ])

    def add_run_period(self, year: int = 2024):
        """연간 시뮬레이션 기간 설정"""
        return self.add("RunPeriod", [
            "AnnualRun", 1, 1, year, 12, 31, year,
            "Sunday", "Yes", "Yes", "No", "Yes", "Yes"
        ])

    def add_material(self, name: str, roughness: str, thickness: float,
                     conductivity: float, density: float, specific_heat: float,
                     absorptance_t: float = 0.9, absorptance_s: float = 0.7,
                     absorptance_v: float = 0.7):
        """Material 객체 추가 (두께/전도율 자동 검증)"""
        if thickness <= 0:
            raise ValueError(f"Material '{name}' 두께는 양수여야 합니다: {thickness}")
        if conductivity <= 0:
            raise ValueError(f"Material '{name}' 열전도율은 양수여야 합니다: {conductivity}")
        
        return self.add("Material", [
            name, roughness, f"{thickness:.4f}", conductivity, density, specific_heat,
            absorptance_t, absorptance_s, absorptance_v
        ])

    def add_construction(self, name: str, layers: list[str]):
        """Construction 객체 추가"""
        return self.add("Construction", [name] + layers)

    def add_air_boundary_construction(self, name: str, ach: float = 0.5,
                                      mixing_schedule: str = "AlwaysOn"):
        """Construction:AirBoundary — 물리적 벽이 없는 개방 경계(존간 공기혼합+복사교환).
        Air 표면(문없는 방↔복도 등)에 사용. 전도저항 0."""
        return self.add("Construction:AirBoundary", [
            name, "SimpleMixing", ach, mixing_schedule
        ])

    def add_glazing_simple(self, name: str, u_value: float, shgc: float, vt: float = 0.8):
        """SimpleGlazingSystem 유리 추가 (U값/SHGC 범위 검증)"""
        if u_value <= 0 or u_value > 10:
            raise ValueError(f"유리 '{name}' U값 범위 초과: {u_value} (0~10)")
        if shgc < 0 or shgc > 1:
            raise ValueError(f"유리 '{name}' SHGC 범위 초과: {shgc} (0~1)")
        
        return self.add("WindowMaterial:SimpleGlazingSystem", [
            name, f"{u_value:.2f}", f"{shgc:.2f}", vt
        ])

    def add_special_day(self, name: str, date: str):
        """특정 날짜를 공휴일로 강제 지정하는 RunPeriodControl:SpecialDays 객체 추가"""
        return self.add("RunPeriodControl:SpecialDays", [
            name, date, 1, "Holiday"
        ])

    def add_zone(self, name: str, floor_area: float, height: float = 3.0):
        """Zone 객체 추가"""
        volume = floor_area * height
        return self.add("Zone", [
            name, 0, 0, 0, 0, 1, 1, height, f"{volume:.2f}", f"{floor_area:.2f}"
        ])

    def add_surface(self, surface_id: str, ep_type: str, construction: str,
                    zone_id: str, boundary: str, sun: str, wind: str,
                    vertices: list, adj_surface_id: str = ""):
        """BuildingSurface:Detailed 객체 추가 (정점 자동 직렬화)
        
        adj_surface_id: Zone-to-Zone 경계 시 상대 Surface ID (Outside Boundary Condition Object)
                        Outdoors/Adiabatic 경계일 때는 빈 문자열.
        """
        fields = [
            surface_id, ep_type, construction, zone_id, "",
            boundary, adj_surface_id, sun, wind, "Autocalculate", len(vertices)
        ]
        # 정점 좌표를 필드에 풀어서 추가
        for v in vertices:
            fields.extend([f"{v[0]:.4f}", f"{v[1]:.4f}", f"{v[2]:.4f}"])
        
        return self.add("BuildingSurface:Detailed", fields)

    def add_window(self, window_id: str, construction: str, parent_surface: str,
                   vertices: list):
        """FenestrationSurface:Detailed 창호 추가"""
        fields = [
            window_id, "Window", construction, parent_surface, "",
            "Autocalculate", "", 1, len(vertices)
        ]
        for v in vertices:
            fields.extend([f"{v[0]:.4f}", f"{v[1]:.4f}", f"{v[2]:.4f}"])
        
        return self.add("FenestrationSurface:Detailed", fields)

    def add_people(self, name: str, zone: str, schedule: str, density: float):
        """People 객체 추가"""
        return self.add("People", [
            name, zone, schedule, "People/Area", "", density, "", "", "", "ActivitySch"
        ])

    def add_lights(self, name: str, zone: str, schedule: str, power_density: float):
        """Lights 객체 추가"""
        return self.add("Lights", [
            name, zone, schedule, "Watts/Area", "", power_density
        ])

    def add_equipment(self, name: str, zone: str, schedule: str, power_density: float):
        """ElectricEquipment 객체 추가"""
        return self.add("ElectricEquipment", [
            name, zone, schedule, "Watts/Area", "", power_density
        ])

    def add_infiltration(self, name: str, zone: str, ach: float = 0.5):
        """ZoneInfiltration 객체 추가"""
        return self.add("ZoneInfiltration:DesignFlowRate", [
            name, zone, "AlwaysOn", "AirChanges/Hour", "", "", "", ach,
            1.0, 0.0, 0.0, 0.0
        ])

    def add_dhw(self, name: str, zone: str, schedule: str, peak_flow_rate_m3_s: float):
        """WaterUse:Equipment 객체를 통해 동적 급탕(DHW) 추가 (온수 사용량)"""
        self.add("WaterUse:Equipment", [
            name, "DHW_Equip", peak_flow_rate_m3_s, schedule, "DHW_Target_Temp", "DHW_Hot_Temp", "DHW_Cold_Temp", zone
        ])
        return self

    def add_ideal_hvac(self, zone_id: str, oa_schedule: str = "AlwaysOn"):
        """IdealLoadsAirSystem + 연관 객체 일괄 추가"""
        self.add("ZoneHVAC:EquipmentConnections", [
            zone_id, f"{zone_id}_Equip", f"{zone_id}_Inlet", "",
            f"{zone_id}_Node", f"{zone_id}_Return"
        ])
        self.add("ZoneHVAC:EquipmentList", [
            f"{zone_id}_Equip", "SequentialLoad",
            "ZoneHVAC:IdealLoadsAirSystem", f"{zone_id}_Ideal", 1, 1
        ])
        self.add("DesignSpecification:OutdoorAir", [
            f"{zone_id}_OA", "Sum", 0.0025, 0.0008, "", "", oa_schedule
        ])
        self.add("ZoneHVAC:IdealLoadsAirSystem", [
            f"{zone_id}_Ideal", "", f"{zone_id}_Inlet", "", "",
            50, 13, 0.015, 0.008,
            "NoLimit", "", "", "NoLimit", "", "",
            "", "", "", "", "", f"{zone_id}_OA"
        ])
        return self

    # -------------------------------------------------------
    # 실기기 HVAC: VRF(가변냉매유량) 히트펌프 — idragon dragon/hvac.py 포팅
    #   이상부하(IdealLoads) 대신 실제 기기를 모델링해 EnergyPlus가
    #   실제 전력 소비/용량을 산출하도록 함. (전기 열원/지열 케이스)
    # -------------------------------------------------------

    def add_vrf_outdoor_unit(self, source_name: str, cooling_cop: float,
                             heating_cop: float, cooling_capacity_w: float,
                             heating_capacity_w: float):
        """VRF 실외기(AirConditioner:VariableRefrigerantFlow) + 성능곡선 ~20개.
        (idragon HeatPump.to_idf_object, hvac.py:147-302 포팅)
        용량은 고정값(W). 현재 파이프라인은 sizing 미수행이라 autosize 불가 →
        연면적 기반 추정 용량을 ep_simulator에서 계산해 전달."""
        s = source_name
        # (curve_type, suffix, [values...])  — idragon 계수 그대로
        curves = [
            ("Curve:Biquadratic", "CoolingCapaMF_LowTemp", [0.576882692, 0.017447952, 0.000583269, -1.76324E-06, -7.474E-09, -1.30413E-07, 15, 24, -5, 23, None, None, "Temperature", "Temperature", "Dimensionless"]),
            ("Curve:Cubic", "CoolingCapaBoundary", [25.73473775, -0.03150043, -0.01416595, 0, 11, 30, None, None, "Temperature"]),
            ("Curve:Biquadratic", "CoolingCapaMF_HighTemp", [0.6867358, 0.0207631, 0.0005447, -0.0016218, -4.259E-07, -0.0003392, 15, 24, 16, 43, None, None, "Temperature", "Temperature", "Dimensionless"]),
            ("Curve:Biquadratic", "CoolingEIRMF_LowTemp", [0.989010541, -0.02347967, 0.000199711, 0.005968336, -1.0289E-07, -0.00015686, 15, 24, -5, 23, None, None, "Temperature", "Temperature", "Dimensionless"]),
            ("Curve:Cubic", "CoolingEIRBoundary", [25.73473775, -0.03150043, -0.01416595, 0, 15, 24, None, None, "Temperature"]),
            ("Curve:Biquadratic", "CoolingEIRMF_HighTemp", [0.14351470, 0.01860035, -0.0003954, 0.02485219, 0.00016329, -0.0006244, 15, 24, 16, 43, None, None, "Temperature", "Temperature", "Dimensionless"]),
            ("Curve:Cubic", "CoolingEIRMF_LowPLR", [0.4628123, -1.0402406, 2.17490997, -0.5974817, 0, 1, None, None, "Temperature", "Capacity"]),
            ("Curve:Linear", "CoolingEIRMF_HighPLR", [1.0, 0.0, 1.0, 1.5]),
            ("Curve:Linear", "CoolingCombCorrection", [0.618055, 0.381945, 1.0, 1.5]),
            ("Curve:Linear", "CoolingPLRCorrelation", [0.85, 0.15, 0.0, 1.0]),
            ("Curve:Biquadratic", "HeatingCapaMF_LowTemp", [1.014599599, -0.002506703, -0.000141599, 0.026931595, 1.83538E-06, -0.000358147, 15, 27, -20, 15, None, None, "Temperature", "Temperature", "Dimensionless"]),
            ("Curve:Cubic", "HeatingCapaBoundary", [-7.6000882, 3.05090016, -0.1162844, 0.0, 15, 27, None, None, "Temperature"]),
            ("Curve:Biquadratic", "HeatingCapaMF_HighTemp", [1.161134821, 0.027478868, -0.00168795, 0.001783378, 2.03208E-06, -6.8969E-05, 15, 27, -10, 15, None, None, "Temperature", "Temperature", "Dimensionless"]),
            ("Curve:Biquadratic", "HeatingEIRMF_LowTemp", [0.87465501, -0.01319754, 0.00110307, -0.0133118, 0.00089017, -0.00012766, 15, 27, -20, 12, None, None, "Temperature", "Temperature", "Dimensionless"]),
            ("Curve:Cubic", "HeatingEIRBoundary", [-7.6000882, 3.05090016, -0.1162844, 0.0, 15, 27, -20, 15, "Temperature"]),
            ("Curve:Biquadratic", "HeatingEIRMF_HighTemp", [2.504005146, -0.05736767, 4.07336E-05, -0.12959669, 0.00135839, 0.00317047, 15, 27, -10, 15, None, None, "Temperature", "Temperature", "Dimensionless"]),
            ("Curve:Cubic", "HeatingEIRMF_LowPLR", [0.1400093, 0.6415002, 0.1339047, 0.0845859, 0, 1, None, None, "Dimensionless", "Dimensionless"]),
            ("Curve:Quadratic", "HeatingEIRMF_HighPLR", [2.4294355, -2.235887, 0.8064516, 1.0, 1.5]),
            ("Curve:Linear", "HeatingCombCorrection", [0.96034, 0.03966, 1.0, 1.5]),
            ("Curve:Linear", "HeatingPLRCorrelation", [0.85, 0.15, 0.0, 1.0]),
        ]
        for ctype, suffix, vals in curves:
            self.add(ctype, [f"Curve_for_{s}:{suffix}"] + vals)

        self._emit_by_idd("AirConditioner:VariableRefrigerantFlow", {
            "Heat Pump Name": s,
            "Availability Schedule Name": "AlwaysOn",
            "Gross Rated Total Cooling Capacity": round(cooling_capacity_w, 1),
            "Gross Rated Cooling COP": cooling_cop,
            "Cooling Capacity Ratio Modifier Function of Low Temperature Curve Name": f"Curve_for_{s}:CoolingCapaMF_LowTemp",
            "Cooling Capacity Ratio Boundary Curve Name": f"Curve_for_{s}:CoolingCapaBoundary",
            "Cooling Capacity Ratio Modifier Function of High Temperature Curve Name": f"Curve_for_{s}:CoolingCapaMF_HighTemp",
            "Cooling Energy Input Ratio Modifier Function of Low Temperature Curve Name": f"Curve_for_{s}:CoolingEIRMF_LowTemp",
            "Cooling Energy Input Ratio Boundary Curve Name": f"Curve_for_{s}:CoolingEIRBoundary",
            "Cooling Energy Input Ratio Modifier Function of High Temperature Curve Name": f"Curve_for_{s}:CoolingEIRMF_HighTemp",
            "Cooling Energy Input Ratio Modifier Function of Low Part-Load Ratio Curve Name": f"Curve_for_{s}:CoolingEIRMF_LowPLR",
            "Cooling Energy Input Ratio Modifier Function of High Part-Load Ratio Curve Name": f"Curve_for_{s}:CoolingEIRMF_HighPLR",
            "Cooling Combination Ratio Correction Factor Curve Name": f"Curve_for_{s}:CoolingCombCorrection",
            "Cooling Part-Load Fraction Correlation Curve Name": f"Curve_for_{s}:CoolingPLRCorrelation",
            "Gross Rated Heating Capacity": round(heating_capacity_w, 1),
            "Gross Rated Heating COP": heating_cop,
            "Heating Capacity Ratio Modifier Function of Low Temperature Curve Name": f"Curve_for_{s}:HeatingCapaMF_LowTemp",
            "Heating Capacity Ratio Boundary Curve Name": f"Curve_for_{s}:HeatingCapaBoundary",
            "Heating Capacity Ratio Modifier Function of High Temperature Curve Name": f"Curve_for_{s}:HeatingCapaMF_HighTemp",
            "Heating Energy Input Ratio Modifier Function of Low Temperature Curve Name": f"Curve_for_{s}:HeatingEIRMF_LowTemp",
            "Heating Energy Input Ratio Boundary Curve Name": f"Curve_for_{s}:HeatingEIRBoundary",
            "Heating Energy Input Ratio Modifier Function of High Temperature Curve Name": f"Curve_for_{s}:HeatingEIRMF_HighTemp",
            "Heating Energy Input Ratio Modifier Function of Low Part-Load Ratio Curve Name": f"Curve_for_{s}:HeatingEIRMF_LowPLR",
            "Heating Energy Input Ratio Modifier Function of High Part-Load Ratio Curve Name": f"Curve_for_{s}:HeatingEIRMF_HighPLR",
            "Heating Combination Ratio Correction Factor Curve Name": f"Curve_for_{s}:HeatingCombCorrection",
            "Heating Part-Load Fraction Correlation Curve Name": f"Curve_for_{s}:HeatingPLRCorrelation",
            "Master Thermostat Priority Control Type": "LoadPriority",
            "Zone Terminal Unit List Name": f"{s}_TUList",
            # EP25.2는 기본 ReverseCycle 제상에 EIR 곡선을 요구 → 저항식으로 설정(곡선 불요)
            "Defrost Strategy": "Resistive",
            "Defrost Control": "Timed",
            # 공랭식 응축기는 응축기 입구노드를 외기노드에 연결해야 함(없으면 미초기화 노드 접근→crash)
            "Condenser Type": "AirCooled",
            "Condenser Inlet Node Name": f"{s}_OANode",
        })
        # 응축기 외기 노드 등록(외기 조건을 노드에 채워줌)
        self.add("OutdoorAir:NodeList", [f"{s}_OANode"])
        self._vrf_sources.setdefault(s, {"terminals": []})
        return self

    def add_vrf_terminal(self, zone_id: str, source_name: str,
                         cooling_w: float, heating_w: float,
                         op_schedule: str = "AlwaysOn"):
        """VRF 실내기(ZoneHVAC:TerminalUnit:VRF) + DX 코일 2종 + 팬.
        (idragon AirHandlingUnit.to_idf_object, hvac.py:2010-2102 포팅)
        용량 고정(W). 송풍량은 용량 기반 추정(ΔT≈10K) — sizing 미수행 대응."""
        tu = f"{zone_id}_VRFterm"
        inlet = f"{zone_id}_VRF_SupplyOut"     # 터미널→존 (존 급기)
        exhaust = f"{zone_id}_VRF_ReturnIn"    # 존→터미널 (존 환기, OA믹서 환기측)
        mixed = f"{zone_id}_VRF_Mixed"         # OA믹서 혼합공기 = 냉방코일 입구
        oa_in = f"{tu}_OAIn"                    # 외기 도입 노드
        relief = f"{tu}_Relief"                # 배기 노드
        mid1 = f"{zone_id}_VRF_C2H"
        mid2 = f"{zone_id}_VRF_H2F"
        # 송풍량(m3/s) ≈ Q /(ρ·cp·ΔT), ρ1.2 cp1006 ΔT10 → ≈ Q/12000, 최소 0.05
        airflow = round(max(cooling_w, heating_w) / 12000.0, 4)
        if airflow < 0.05:
            airflow = 0.05
        oa_flow = round(airflow * 0.15, 4)     # 환기용 외기풍량(고정)

        # 외기 믹서(EP25.2 VRF 실내기는 OA 믹서 구성을 기대 — 없으면 본런 직후 crash)
        self._emit_by_idd("OutdoorAir:Mixer", {
            "Name": f"{tu}_OAMixer",
            "Mixed Air Node Name": mixed,
            "Outdoor Air Stream Node Name": oa_in,
            "Relief Air Stream Node Name": relief,
            "Return Air Stream Node Name": exhaust,
        })
        self.add("OutdoorAir:NodeList", [oa_in])

        # 실내기 용량곡선 4개
        self.add("Curve:Cubic", [f"Curve_for_{tu}:HeatingCapaTemp", -3.90708928E-01, 2.61815024E-01, -1.30431603E-02, 1.78131746E-04, 0.0, 50, 0.5, 1.5, "Temperature", "Dimensionless"])
        self.add("Curve:Linear", [f"Curve_for_{tu}:HeatingCapaFlow", 0.8, 0.2, 0.0, 1.5])
        self.add("Curve:Cubic", [f"Curve_for_{tu}:CoolingCapaTemp", 5.04547274E-01, 2.88891279E-02, -1.08194187E-05, 1.01359395E-05, 0.0, 50, 0.5, 1.5, "Temperature", "Dimensionless"])
        self.add("Curve:Linear", [f"Curve_for_{tu}:CoolingCapaFlow", 0.8, 0.2, 0.0, 1.5])

        self._emit_by_idd("Coil:Cooling:DX:VariableRefrigerantFlow", {
            "Name": f"CoolingCoil_for_{tu}",
            "Availability Schedule Name": op_schedule,
            "Gross Rated Total Cooling Capacity": round(cooling_w, 1),
            "Gross Rated Sensible Heat Ratio": 0.75,
            "Rated Air Flow Rate": airflow,
            "Cooling Capacity Ratio Modifier Function of Temperature Curve Name": f"Curve_for_{tu}:CoolingCapaTemp",
            "Cooling Capacity Modifier Curve Function of Flow Fraction Name": f"Curve_for_{tu}:CoolingCapaFlow",
            "Coil Air Inlet Node": mixed,
            "Coil Air Outlet Node": mid1,
        })
        self._emit_by_idd("Coil:Heating:DX:VariableRefrigerantFlow", {
            "Name": f"HeatingCoil_for_{tu}",
            "Availability Schedule": op_schedule,
            "Gross Rated Heating Capacity": round(heating_w, 1),
            "Rated Air Flow Rate": airflow,
            "Coil Air Inlet Node": mid1,
            "Coil Air Outlet Node": mid2,
            "Heating Capacity Ratio Modifier Function of Temperature Curve Name": f"Curve_for_{tu}:HeatingCapaTemp",
            "Heating Capacity Modifier Function of Flow Fraction Curve Name": f"Curve_for_{tu}:HeatingCapaFlow",
        })
        self._emit_by_idd("Fan:SystemModel", {
            "Name": f"Fan_for_{tu}",
            "Availability Schedule Name": op_schedule,
            "Air Inlet Node Name": mid2,
            "Air Outlet Node Name": inlet,
            "Design Maximum Air Flow Rate": airflow,
            "Speed Control Method": "Discrete",
            "Design Pressure Rise": 100,
            "Motor Efficiency": 0.9,
            "Motor In Air Stream Fraction": 1.0,
            "Design Power Sizing Method": "TotalEfficiencyAndPressure",
            "Fan Total Efficiency": 0.7,
        })
        self._emit_by_idd("ZoneHVAC:TerminalUnit:VariableRefrigerantFlow", {
            "Zone Terminal Unit Name": tu,
            "Terminal Unit Availability Schedule": op_schedule,
            "Terminal Unit Air Inlet Node Name": exhaust,
            "Terminal Unit Air Outlet Node Name": inlet,
            "Cooling Supply Air Flow Rate": airflow,
            "No Cooling Supply Air Flow Rate": round(airflow * 0.3, 4),
            "Heating Supply Air Flow Rate": airflow,
            "No Heating Supply Air Flow Rate": round(airflow * 0.3, 4),
            "Cooling Outdoor Air Flow Rate": oa_flow,
            "Heating Outdoor Air Flow Rate": oa_flow,
            "No Load Outdoor Air Flow Rate": oa_flow,
            "Supply Air Fan Operating Mode Schedule Name": "AlwaysOn",
            "Supply Air Fan Placement": "DrawThrough",
            "Supply Air Fan Object Type": "Fan:SystemModel",
            "Supply Air Fan Object Name": f"Fan_for_{tu}",
            "Outside Air Mixer Object Type": "OutdoorAir:Mixer",
            "Outside Air Mixer Object Name": f"{tu}_OAMixer",
            "Cooling Coil Object Type": "Coil:Cooling:DX:VariableRefrigerantFlow",
            "Cooling Coil Object Name": f"CoolingCoil_for_{tu}",
            "Heating Coil Object Type": "Coil:Heating:DX:VariableRefrigerantFlow",
            "Heating Coil Object Name": f"HeatingCoil_for_{tu}",
            "Zone Terminal Unit On Parasitic Electric Energy Use": 30,
            "Zone Terminal Unit Off Parasitic Electric Energy Use": 20,
        })
        # 누적(존 장비/노드 + 소스 터미널 목록) → finalize_hvac에서 일괄 emit
        self._vrf_sources.setdefault(source_name, {"terminals": []})["terminals"].append(tu)
        self._register_zone_equip(zone_id, "ZoneHVAC:TerminalUnit:VariableRefrigerantFlow", tu,
                                  cool_seq=1, heat_seq=1, inlet=inlet, exhaust=exhaust)
        return self

    def _register_zone_equip(self, zone_id: str, obj_type: str, name: str, *,
                             cool_seq: int, heat_seq: int, inlet: str, exhaust: str):
        """존 장비/노드 누적 — finalize_hvac에서 EquipmentConnections/List로 일괄 emit."""
        self._zone_equip.setdefault(zone_id, []).append((obj_type, name, cool_seq, heat_seq))
        nodes = self._zone_nodes.setdefault(zone_id, {"inlets": [], "exhausts": []})
        nodes["inlets"].append(inlet)
        nodes["exhausts"].append(exhaust)

    # -------------------------------------------------------
    # 실기기 HVAC: PTHP(패키지형 터미널 히트펌프) — 존 단위 자기완결 실기기.
    #   VRF가 EP25.2에서 불안정해 PTHP로 채택. 실제 전력소비+COP를 EnergyPlus가
    #   산출 → 비용(운영비)에 직접 연결. (전기 열원/지열=고COP 케이스)
    #   DX 곡선은 EnergyPlus 공식 PTHP 예제의 검증된 정규화 곡선 사용.
    # -------------------------------------------------------

    def _add_dx_curves_once(self):
        """PTHP DX 단속(single-speed) 성능곡선(공용, 1회만)."""
        if getattr(self, "_dx_curves_added", False):
            return
        self._dx_curves_added = True
        self.add("Curve:Biquadratic", ["HPACCoolCapFT", 0.942587793, 0.009543347, 0.000683770, -0.011042676, 0.000005249, -0.000009720, 12.77778, 23.88889, 18.0, 46.11111, None, None, "Temperature", "Temperature", "Dimensionless"])
        self.add("Curve:Quadratic", ["HPACCoolCapFFF", 0.8, 0.2, 0.0, 0.5, 1.5])
        self.add("Curve:Biquadratic", ["HPACEIRFT", 0.342414409, 0.034885008, -0.000623700, 0.004977216, 0.000437951, -0.000728028, 12.77778, 23.88889, 18.0, 46.11111, None, None, "Temperature", "Temperature", "Dimensionless"])
        self.add("Curve:Quadratic", ["HPACEIRFFF", 1.1552, -0.1808, 0.0256, 0.5, 1.5])
        self.add("Curve:Quadratic", ["HPACCOOLPLFFPLR", 0.75, 0.25, 0.0, 0.0, 1.0])
        self.add("Curve:Cubic", ["HPACHeatCapFT", 0.758746, 0.027626, 0.000148716, 0.0000034992, -20.0, 20.0, None, None, "Temperature", "Dimensionless"])
        self.add("Curve:Cubic", ["HPACHeatCapFFF", 0.84, 0.16, 0.0, 0.0, 0.5, 1.5])
        self.add("Curve:Cubic", ["HPACHeatEIRFT", 1.19248, -0.0300438, 0.00103745, -0.000023328, -20.0, 20.0, None, None, "Temperature", "Dimensionless"])
        self.add("Curve:Quadratic", ["HPACHeatEIRFFF", 1.3824, -0.4336, 0.0512, 0.0, 1.0])
        self.add("Curve:Quadratic", ["HPACPLFFPLR", 0.85, 0.15, 0.0, 0.0, 1.0])

    def add_pthp(self, zone_id: str, cooling_cop: float, heating_cop: float,
                 op_schedule: str = "AlwaysOn"):
        """ZoneHVAC:PackagedTerminalHeatPump(+OA믹서·팬·DX코일2·보조전기코일) 추가.
        용량/풍량은 autosize → enable_sizing()+add_zone_sizing() 필요(부하에 맞춰 적정 산정)."""
        self._add_dx_curves_once()
        u = f"{zone_id}_PTHP"
        inlet = f"{zone_id}_PTHP_SupplyOut"   # 유닛→존
        exhaust = f"{zone_id}_PTHP_ReturnIn"  # 존→유닛 (유닛 입구)
        oa_in = f"{u}_OAIn"; relief = f"{u}_Relief"; mixed = f"{u}_Mixed"
        fan_out = f"{u}_FanOut"; c2h = f"{u}_C2H"; h2s = f"{u}_H2S"
        A = "autosize"

        # OA 믹서
        self._emit_by_idd("OutdoorAir:Mixer", {
            "Name": f"{u}_OAMixer",
            "Mixed Air Node Name": mixed,
            "Outdoor Air Stream Node Name": oa_in,
            "Relief Air Stream Node Name": relief,
            "Return Air Stream Node Name": exhaust,
        })
        self.add("OutdoorAir:NodeList", [oa_in])
        # 팬(BlowThrough): mixed → fan_out
        self._emit_by_idd("Fan:SystemModel", {
            "Name": f"Fan_for_{u}",
            "Availability Schedule Name": op_schedule,
            "Air Inlet Node Name": mixed,
            "Air Outlet Node Name": fan_out,
            "Design Maximum Air Flow Rate": A,
            "Speed Control Method": "Discrete",
            "Design Pressure Rise": 100,
            "Motor Efficiency": 0.9,
            "Motor In Air Stream Fraction": 1.0,
            "Design Power Sizing Method": "TotalEfficiencyAndPressure",
            "Fan Total Efficiency": 0.7,
        })
        # DX 냉방코일: fan_out → c2h
        self._emit_by_idd("Coil:Cooling:DX:SingleSpeed", {
            "Name": f"CoolCoil_{u}",
            "Availability Schedule Name": op_schedule,
            "Gross Rated Total Cooling Capacity": A,
            "Gross Rated Sensible Heat Ratio": A,
            "Gross Rated Cooling COP": cooling_cop,
            "Rated Air Flow Rate": A,
            "Air Inlet Node Name": fan_out,
            "Air Outlet Node Name": c2h,
            "Total Cooling Capacity Function of Temperature Curve Name": "HPACCoolCapFT",
            "Total Cooling Capacity Function of Flow Fraction Curve Name": "HPACCoolCapFFF",
            "Energy Input Ratio Function of Temperature Curve Name": "HPACEIRFT",
            "Energy Input Ratio Function of Flow Fraction Curve Name": "HPACEIRFFF",
            "Part Load Fraction Correlation Curve Name": "HPACCOOLPLFFPLR",
        })
        # DX 난방코일: c2h → h2s (저항식 제상 → 제상 EIR 곡선 불요)
        self._emit_by_idd("Coil:Heating:DX:SingleSpeed", {
            "Name": f"HeatCoil_{u}",
            "Availability Schedule Name": op_schedule,
            "Gross Rated Heating Capacity": A,
            "Gross Rated Heating COP": heating_cop,
            "Rated Air Flow Rate": A,
            "Air Inlet Node Name": c2h,
            "Air Outlet Node Name": h2s,
            "Heating Capacity Function of Temperature Curve Name": "HPACHeatCapFT",
            "Heating Capacity Function of Flow Fraction Curve Name": "HPACHeatCapFFF",
            "Energy Input Ratio Function of Temperature Curve Name": "HPACHeatEIRFT",
            "Energy Input Ratio Function of Flow Fraction Curve Name": "HPACHeatEIRFFF",
            "Part Load Fraction Correlation Curve Name": "HPACPLFFPLR",
            # 한랭기에도 히트펌프 압축기가 계속 가동되도록(기본 컷오프가 높으면 보조히터가 과다)
            "Minimum Outdoor Dry-Bulb Temperature for Compressor Operation": -15.0,
            "Defrost Strategy": "Resistive",
            "Defrost Control": "Timed",
        })
        # 보조 전기 히터: h2s → inlet
        self._emit_by_idd("Coil:Heating:Electric", {
            "Name": f"SuppCoil_{u}",
            "Availability Schedule Name": op_schedule,
            "Efficiency": 1.0,
            "Nominal Capacity": A,
            "Air Inlet Node Name": h2s,
            "Air Outlet Node Name": inlet,
        })
        # PTHP 유닛
        self._emit_by_idd("ZoneHVAC:PackagedTerminalHeatPump", {
            "Name": u,
            "Availability Schedule Name": op_schedule,
            "Air Inlet Node Name": exhaust,
            "Air Outlet Node Name": inlet,
            "Outdoor Air Mixer Object Type": "OutdoorAir:Mixer",
            "Outdoor Air Mixer Name": f"{u}_OAMixer",
            "Cooling Supply Air Flow Rate": A,
            "Heating Supply Air Flow Rate": A,
            "No Load Supply Air Flow Rate": A,
            "Cooling Outdoor Air Flow Rate": A,
            "Heating Outdoor Air Flow Rate": A,
            "No Load Outdoor Air Flow Rate": A,
            "Supply Air Fan Object Type": "Fan:SystemModel",
            "Supply Air Fan Name": f"Fan_for_{u}",
            "Heating Coil Object Type": "Coil:Heating:DX:SingleSpeed",
            "Heating Coil Name": f"HeatCoil_{u}",
            "Cooling Coil Object Type": "Coil:Cooling:DX:SingleSpeed",
            "Cooling Coil Name": f"CoolCoil_{u}",
            "Supplemental Heating Coil Object Type": "Coil:Heating:Electric",
            "Supplemental Heating Coil Name": f"SuppCoil_{u}",
            "Maximum Supply Air Temperature from Supplemental Heater": 50,
            # 보조 전기히터는 한랭(-5℃ 미만)에서만 가동 → 그 외엔 히트펌프가 부하 담당(실효 COP↑)
            "Maximum Outdoor Dry-Bulb Temperature for Supplemental Heater Operation": -5.0,
            "Fan Placement": "BlowThrough",
        })
        self._register_zone_equip(zone_id, "ZoneHVAC:PackagedTerminalHeatPump", u,
                                  cool_seq=1, heat_seq=1, inlet=inlet, exhaust=exhaust)
        return self

    # -------------------------------------------------------
    # 실기기 HVAC: 비전기 열원(가스/등유/지역난방)용 존 자기완결 조합
    #   난방 = ZoneHVAC:UnitHeater + Coil:Heating:Fuel (연료·연소효율 실모델
    #          → Heating:<연료> 미터로 실소비 산출. 한국 개별 보일러 근사)
    #   냉방 = ZoneHVAC:WindowAirConditioner + DX 코일 (개별 에어컨 근사)
    #   지역난방은 Fuel Type=OtherFuel1, 효율≈0.95(열교환 손실)로 모델링.
    # -------------------------------------------------------

    def add_unit_heater(self, zone_id: str, fuel_type: str, efficiency: float,
                        op_schedule: str = "AlwaysOn"):
        """연료 난방기(UnitHeater+Coil:Heating:Fuel). autosize → 사이징 활성화 필요."""
        u = f"{zone_id}_UH"
        inlet = f"{zone_id}_UH_SupplyOut"   # 유닛→존
        exhaust = f"{zone_id}_UH_ReturnIn"  # 존→유닛
        fan_out = f"{u}_FanOut"
        A = "autosize"
        self._emit_by_idd("Fan:SystemModel", {
            "Name": f"Fan_for_{u}",
            "Availability Schedule Name": op_schedule,
            "Air Inlet Node Name": exhaust,
            "Air Outlet Node Name": fan_out,
            "Design Maximum Air Flow Rate": A,
            "Speed Control Method": "Discrete",
            "Design Pressure Rise": 75,
            "Motor Efficiency": 0.9,
            "Motor In Air Stream Fraction": 1.0,
            "Design Power Sizing Method": "TotalEfficiencyAndPressure",
            "Fan Total Efficiency": 0.7,
        })
        self._emit_by_idd("Coil:Heating:Fuel", {
            "Name": f"HeatCoil_{u}",
            "Availability Schedule Name": op_schedule,
            "Fuel Type": fuel_type,
            "Burner Efficiency": efficiency,
            "Nominal Capacity": A,
            "Air Inlet Node Name": fan_out,
            "Air Outlet Node Name": inlet,
        })
        self._emit_by_idd("ZoneHVAC:UnitHeater", {
            "Name": u,
            "Availability Schedule Name": op_schedule,
            "Air Inlet Node Name": exhaust,
            "Air Outlet Node Name": inlet,
            "Supply Air Fan Object Type": "Fan:SystemModel",
            "Supply Air Fan Name": f"Fan_for_{u}",
            "Maximum Supply Air Flow Rate": A,
            "Heating Coil Object Type": "Coil:Heating:Fuel",
            "Heating Coil Name": f"HeatCoil_{u}",
            "Supply Air Fan Operation During No Heating": "No",
        })
        # 난방 우선순위 1 / 냉방 2 (냉방은 WindowAC가 1순위로 담당)
        self._register_zone_equip(zone_id, "ZoneHVAC:UnitHeater", u,
                                  cool_seq=2, heat_seq=1, inlet=inlet, exhaust=exhaust)
        return self

    def add_window_ac(self, zone_id: str, cooling_cop: float,
                      cooling_capacity_w: float = None,
                      op_schedule: str = "AlwaysOn"):
        """개별 냉방기(WindowAC+DX 단속코일).

        cooling_capacity_w를 주면 명시 용량(정격 유량은 5e-5 m³/s·W로 유도) — 냉방부하가
        0인 존에서 autosize가 0이 되어 Fatal 나는 것을 원천 차단. 실제 에어컨도
        카탈로그 정격 용량으로 설치되므로 면적 기반 명시 용량이 현실과도 부합.
        미지정 시 autosize(사이징 활성화 필요)."""
        self._add_dx_curves_once()
        u = f"{zone_id}_WAC"
        inlet = f"{zone_id}_WAC_SupplyOut"
        exhaust = f"{zone_id}_WAC_ReturnIn"
        oa_in = f"{u}_OAIn"; relief = f"{u}_Relief"; mixed = f"{u}_Mixed"
        fan_out = f"{u}_FanOut"
        A = "autosize"
        if cooling_capacity_w:
            cap = round(float(cooling_capacity_w), 1)
            flow = round(cap * 5e-5, 5)   # 정격 유량 (E+ 허용범위 4.0e-5~6.0e-5 m³/s·W)
            shr = 0.75
        else:
            cap = flow = shr = A
        self._emit_by_idd("OutdoorAir:Mixer", {
            "Name": f"{u}_OAMixer",
            "Mixed Air Node Name": mixed,
            "Outdoor Air Stream Node Name": oa_in,
            "Relief Air Stream Node Name": relief,
            "Return Air Stream Node Name": exhaust,
        })
        self.add("OutdoorAir:NodeList", [oa_in])
        self._emit_by_idd("Fan:SystemModel", {
            "Name": f"Fan_for_{u}",
            "Availability Schedule Name": op_schedule,
            "Air Inlet Node Name": mixed,
            "Air Outlet Node Name": fan_out,
            "Design Maximum Air Flow Rate": flow,
            "Speed Control Method": "Discrete",
            "Design Pressure Rise": 75,
            "Motor Efficiency": 0.9,
            "Motor In Air Stream Fraction": 1.0,
            "Design Power Sizing Method": "TotalEfficiencyAndPressure",
            "Fan Total Efficiency": 0.7,
        })
        self._emit_by_idd("Coil:Cooling:DX:SingleSpeed", {
            "Name": f"CoolCoil_{u}",
            "Availability Schedule Name": op_schedule,
            "Gross Rated Total Cooling Capacity": cap,
            "Gross Rated Sensible Heat Ratio": shr,
            "Gross Rated Cooling COP": cooling_cop,
            "Rated Air Flow Rate": flow,
            "Air Inlet Node Name": fan_out,
            "Air Outlet Node Name": inlet,
            "Total Cooling Capacity Function of Temperature Curve Name": "HPACCoolCapFT",
            "Total Cooling Capacity Function of Flow Fraction Curve Name": "HPACCoolCapFFF",
            "Energy Input Ratio Function of Temperature Curve Name": "HPACEIRFT",
            "Energy Input Ratio Function of Flow Fraction Curve Name": "HPACEIRFFF",
            "Part Load Fraction Correlation Curve Name": "HPACCOOLPLFFPLR",
        })
        self._emit_by_idd("ZoneHVAC:WindowAirConditioner", {
            "Name": u,
            "Availability Schedule Name": op_schedule,
            "Maximum Supply Air Flow Rate": flow,
            "Maximum Outdoor Air Flow Rate": 0.0,
            "Air Inlet Node Name": exhaust,
            "Air Outlet Node Name": inlet,
            "Outdoor Air Mixer Object Type": "OutdoorAir:Mixer",
            "Outdoor Air Mixer Name": f"{u}_OAMixer",
            "Supply Air Fan Object Type": "Fan:SystemModel",
            "Supply Air Fan Name": f"Fan_for_{u}",
            "Cooling Coil Object Type": "Coil:Cooling:DX:SingleSpeed",
            "DX Cooling Coil Name": f"CoolCoil_{u}",
            "Fan Placement": "BlowThrough",
        })
        # 냉방 우선순위 1 / 난방 2 (난방은 UnitHeater가 1순위로 담당)
        self._register_zone_equip(zone_id, "ZoneHVAC:WindowAirConditioner", u,
                                  cool_seq=1, heat_seq=2, inlet=inlet, exhaust=exhaust)
        return self

    def enable_sizing(self):
        """존/시스템 사이징 활성화 + 외기 기반 사이징 기간 2종(여름/겨울 극한).
        autosize 기기(PTHP 등)가 부하에 맞춰 용량을 산정하도록. 1회만."""
        if getattr(self, "_sizing_enabled", False):
            return self
        self._sizing_enabled = True
        # SimulationControl(헤더의 objects[1]) → 존+시스템 사이징 ON
        for o in self.objects:
            if o.obj_type == "SimulationControl":
                o.fields = ["Yes", "Yes", "No", "No", "Yes"]
                break
        self.add("SizingPeriod:WeatherFileConditionType",
                 ["SummerSizing", "SummerExtreme", "SummerDesignDay", "No", "No"])
        self.add("SizingPeriod:WeatherFileConditionType",
                 ["WinterSizing", "WinterExtreme", "WinterDesignDay", "No", "No"])
        # 안전계수: 설계일 기준 자동산정에 여유를 둬 미달시간(unmet hours) 감소
        self._emit_by_idd("Sizing:Parameters", {
            "Heating Sizing Factor": 1.25,
            "Cooling Sizing Factor": 1.15,
        })
        return self

    def add_zone_sizing(self, zone_id: str):
        """Sizing:Zone — 존 냉난방 설계 급기 조건(autosize 기반)."""
        return self._emit_by_idd("Sizing:Zone", {
            "Zone or ZoneList Name": zone_id,
            "Zone Cooling Design Supply Air Temperature Input Method": "SupplyAirTemperature",
            "Zone Cooling Design Supply Air Temperature": 14,
            "Zone Heating Design Supply Air Temperature Input Method": "SupplyAirTemperature",
            "Zone Heating Design Supply Air Temperature": 40,
            "Zone Cooling Design Supply Air Humidity Ratio": 0.008,
            "Zone Heating Design Supply Air Humidity Ratio": 0.008,
        })

    def add_zone_hvac_connections(self, zone_id: str):
        """존 누적 장비로 EquipmentConnections + EquipmentList emit (실기기 존용).
        기기 2개 이상이면 인렛/배기 노드를 NodeList로 묶는다."""
        equip = self._zone_equip.get(zone_id, [])
        nodes = self._zone_nodes.get(zone_id, {"inlets": [], "exhausts": []})
        if not equip:
            return self

        inlets = nodes.get("inlets", [])
        exhausts = nodes.get("exhausts", [])
        if len(inlets) > 1:
            inlet_ref = f"{zone_id}_InletNodes"
            self.add("NodeList", [inlet_ref] + inlets)
        else:
            inlet_ref = inlets[0] if inlets else ""
        if len(exhausts) > 1:
            exhaust_ref = f"{zone_id}_ExhaustNodes"
            self.add("NodeList", [exhaust_ref] + exhausts)
        else:
            exhaust_ref = exhausts[0] if exhausts else ""

        self.add("ZoneHVAC:EquipmentConnections", [
            zone_id, f"{zone_id}_Equip", inlet_ref, exhaust_ref,
            f"{zone_id}_Node", f"{zone_id}_Return"
        ])
        fields = [f"{zone_id}_Equip", "SequentialLoad"]
        n = len(equip)  # 시퀀스는 1..기기수 범위여야 함 (기기 1개 존에 seq=2면 Severe)
        for (otype, oname, cool_seq, heat_seq) in equip:
            fields += [otype, oname, min(cool_seq, n), min(heat_seq, n), "", ""]
        self.add("ZoneHVAC:EquipmentList", fields)
        return self

    def finalize_hvac(self):
        """실기기 누적 상태를 마지막에 일괄 emit (idragon postprocessor 대체).
        - 소스별 ZoneTerminalUnitList(터미널 전체)
        - 실기기 존별 EquipmentConnections/List
        ep_simulator에서 존 루프 종료 후, write/run 전에 호출."""
        for src, info in self._vrf_sources.items():
            terms = info.get("terminals", [])
            if terms:
                self.add("ZoneTerminalUnitList", [f"{src}_TUList"] + terms)
        for zone_id in self._zone_equip:
            self.add_zone_hvac_connections(zone_id)
        return self

    def add_thermostat(self, zone_id: str, heat_schedule: str, cool_schedule: str):
        """온도 제어 세트 일괄 추가"""
        self.add("ThermostatSetpoint:DualSetpoint", [
            f"{zone_id}_DualSetp", heat_schedule, cool_schedule
        ])
        self.add("ZoneControl:Thermostat", [
            f"{zone_id}_Thermostat", zone_id, "DualZoneControlSch",
            "ThermostatSetpoint:DualSetpoint", f"{zone_id}_DualSetp"
        ])
        return self

    def add_output_variables(self):
        """표준 출력 변수 세트 추가"""
        self.add("Output:Variable", ["*", "Zone Ideal Loads Supply Air Total Heating Energy", "Hourly"])
        self.add("Output:Variable", ["*", "Zone Ideal Loads Supply Air Total Cooling Energy", "Hourly"])
        # HVAC 피크 산출용 Rate 출력 (W) -> Hourly 보고 시 정확한 Peak 탐지 가능
        self.add("Output:Variable", ["*", "Zone Ideal Loads Supply Air Total Heating Rate", "Hourly"])
        self.add("Output:Variable", ["*", "Zone Ideal Loads Supply Air Total Cooling Rate", "Hourly"])
        self.add("Output:Variable", ["*", "Facility Total Electric Demand Rate", "Hourly"])
        self.add("Output:Variable", ["*", "Lights Electricity Energy", "Hourly"])
        self.add("Output:Variable", ["*", "Electric Equipment Electricity Energy", "Hourly"])
        self.add("Output:Variable", ["*", "Surface Outside Face Temperature", "Hourly"])
        self.add("Output:Variable", ["*", "Surface Outside Face Incident Solar Radiation Rate per Area", "Hourly"])
        self.add("Output:Variable", ["*", "AFN Linkage Node 1 to Node 2 Volume Flow Rate", "Hourly"])
        self.add("Output:Variable", ["*", "AFN Linkage Node 2 to Node 1 Volume Flow Rate", "Hourly"])
        self.add("Output:Variable", ["*", "Water Use Equipment Heating Energy", "Hourly"])
        self.add("Output:Variable", ["*", "Zone Mechanical Ventilation Mass Flow Rate", "Hourly"])
        # 실기기(PTHP) 실제 소비/요구량 — 이상부하 존엔 0으로 나오므로 공존 가능
        self.add("Output:Variable", ["*", "Zone Air System Sensible Heating Energy", "Hourly"])
        self.add("Output:Variable", ["*", "Zone Air System Sensible Cooling Energy", "Hourly"])
        self.add("Output:Meter", ["Heating:Electricity", "Hourly"])
        self.add("Output:Meter", ["Cooling:Electricity", "Hourly"])
        self.add("Output:Meter", ["Fans:Electricity", "Hourly"])
        self.add("OutputControl:Table:Style", ["Comma"])
        self.add("Output:Table:SummaryReports", ["AllSummary"])
        return self

    def setup_airflow_network(self):
        """기본 자연환기 AirflowNetwork 컴포넌트 등록"""
        self.add("AirflowNetwork:SimulationControl", [
            "AFNControl", 
            "MultizoneWithoutDistribution",
            "SurfaceAverageCalculation",
            "OpeningHeight",
            "LowRise",
            500,
            "ZeroNodePressures",
            0.0001,
            1e-6,
            -0.5
        ])
        self.add("AirflowNetwork:MultiZone:ReferenceCrackConditions", [
            "RefCrackCond", 20.0, 101325, 0.0
        ])
        self.add("AirflowNetwork:MultiZone:Surface:Crack", [
            "WallCrack", 0.01, 0.65
        ])
        self.add("AirflowNetwork:MultiZone:Component:SimpleOpening", [
            "WindowOpening", 0.001, 0.65, 0.3, 0.6
        ])
        return self

    # -------------------------------------------------------
    # 스케줄 헬퍼
    # -------------------------------------------------------

    def add_schedule_compact(self, name: str, type_limits: str, schedule_text: str):
        """Schedule:Compact 추가 (텍스트 그대로)"""
        fields = [name, type_limits] + [s.strip() for s in schedule_text.split(",")]
        return self.add("Schedule:Compact", fields)

    def add_standard_schedules(self):
        """공통 스케줄 세트 일괄 추가"""
        self.add("ScheduleTypeLimits", ["AnyNumber"])
        self.add("ScheduleTypeLimits", ["Fraction", 0.0, 1.0, "Continuous"])
        self.add("ScheduleTypeLimits", ["ControlType", 0, 4, "Discrete"])
        
        self.add_schedule_compact("AlwaysOn", "Fraction",
            "Through: 12/31, For: AllDays, Until: 24:00, 1.0")
        self.add_schedule_compact("ActivitySch", "AnyNumber",
            "Through: 12/31, For: AllDays, Until: 24:00, 120.0")
        self.add_schedule_compact("DualZoneControlSch", "ControlType",
            "Through: 12/31, For: AllDays, Until: 24:00, 4")
        self.add_schedule_compact("DHW_Target_Temp", "AnyNumber",
            "Through: 12/31, For: AllDays, Until: 24:00, 40.0")
        self.add_schedule_compact("DHW_Hot_Temp", "AnyNumber",
            "Through: 12/31, For: AllDays, Until: 24:00, 45.0")
        self.add_schedule_compact("DHW_Cold_Temp", "AnyNumber",
            "Through: 12/31, For: AllDays, Until: 24:00, 15.0")
        self.add_schedule_compact("Sch_Office", "Fraction",
            "Through: 12/31, For: Weekdays, Until: 08:00, 0.0, Until: 18:00, 1.0, Until: 24:00, 0.0, For: AllOtherDays, Until: 24:00, 0.0")
        self.add_schedule_compact("Sch_Res", "Fraction",
            "Through: 12/31, For: Weekdays, Until: 08:00, 1.0, Until: 18:00, 0.0, Until: 24:00, 1.0, For: AllOtherDays, Until: 24:00, 1.0")
        self.add_schedule_compact("Sch_Rest", "Fraction",
            "Through: 12/31, For: AllDays, Until: 10:00, 0.0, Until: 14:00, 1.0, Until: 17:00, 0.2, Until: 21:00, 1.0, Until: 24:00, 0.0")
        self.add_schedule_compact("Sch_Lab", "Fraction",
            "Through: 12/31, For: AllDays, Until: 24:00, 1.0")
        return self

    # -------------------------------------------------------
    # 출력 (imugi의 write/run 패턴)
    # -------------------------------------------------------

    def write(self, filepath: str) -> str:
        """IDF 파일 쓰기"""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"! Generated by ZeroBase IdfBuilder (imugi pattern)\n")
            f.write(f"! EnergyPlus Version: {self.version}\n\n")
            for obj in self.objects:
                f.write(obj.to_idf())
                f.write("\n")
        
        print(f"📝 IDF 파일 생성 완료: {filepath} ({len(self.objects)}개 객체)")
        return filepath

    def run(self, weather_file: str, output_dir: str) -> bool:
        """EnergyPlus 시뮬레이션 실행 (imugi의 idf.run() 패턴)"""
        import subprocess
        import sys
        import shutil
        
        idf_path = os.path.join(output_dir, "generated_model.idf")
        self.write(idf_path)
        
        # EnergyPlus 실행 파일 탐색
        ep_cmd = "energyplus"
        if shutil.which(ep_cmd) is None:
            for p in ["/Applications/EnergyPlus-25-2-0/energyplus", "/usr/local/bin/energyplus"]:
                if os.path.exists(p):
                    ep_cmd = p
                    break

        cmd = [ep_cmd, "-w", weather_file, "-r", idf_path]
        process = subprocess.Popen(
            cmd, cwd=output_dir,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )
        
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
        
        process.wait()
        
        # Fatal 에러 확인
        err_path = os.path.join(output_dir, "eplusout.err")
        fatal_error = False
        if os.path.exists(err_path):
            with open(err_path, "r", encoding="utf-8", errors="ignore") as f_err:
                err_content = f_err.read()
                if "Fatal" in err_content:
                    fatal_error = True
                    print("\n" + "="*50)
                    print("🚨 EnergyPlus 상세 에러 로그 (eplusout.err):")
                    print("="*50)
                    print(err_content)
                    print("="*50 + "\n")

        success = process.returncode == 0 and not fatal_error
        
        if success:
            print(f"✅ EnergyPlus 시뮬레이션 성공!")
        else:
            print(f"❌ EnergyPlus 시뮬레이션 실패 (return code: {process.returncode})")
        
        return success

    def __len__(self) -> int:
        return len(self.objects)

    def __repr__(self) -> str:
        return f"<IdfBuilder V{self.version} with {len(self)} objects>"
