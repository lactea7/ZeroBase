# src/idf_builder.py
# imugi.py의 IDF 객체 패턴을 참고한 IDF 빌더 클래스
# - EnergyPlus IDF 파일을 객체 지향적으로 생성
# - 필드 검증 및 에러 방지 내장

import os
import math


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
