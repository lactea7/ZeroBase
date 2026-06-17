# src/gbxml_parser.py
import defusedxml.ElementTree as ET
import re
import math

def strip_ns_and_lower(tag):
    """XML 태그에서 네임스페이스와 접두사를 모두 제거하고 소문자로 변환합니다."""
    tag = re.sub(r'\{.*\}', '', tag)
    if ':' in tag:
        tag = tag.split(':')[-1]
    return tag.lower()

def calculate_surface_area(vertices):
    if len(vertices) < 3: 
        return 0.0
    nx, ny, nz = 0.0, 0.0, 0.0
    for i in range(len(vertices)):
        v1 = vertices[i]
        v2 = vertices[(i + 1) % len(vertices)]
        nx += (v1[1] - v2[1]) * (v1[2] + v2[2])
        ny += (v1[2] - v2[2]) * (v1[0] + v2[0])
        nz += (v1[0] - v2[0]) * (v1[1] + v2[1])
    return math.sqrt(nx*nx + ny*ny + nz*nz) / 2.0

def calculate_surface_normal(vertices):
    """면의 법선벡터(면적 가중)를 계산합니다. 반환값은 (nx, ny, nz)."""
    if len(vertices) < 3:
        return (0.0, 0.0, 0.0)
    nx, ny, nz = 0.0, 0.0, 0.0
    for i in range(len(vertices)):
        v1 = vertices[i]
        v2 = vertices[(i + 1) % len(vertices)]
        nx += (v1[1] - v2[1]) * (v1[2] + v2[2])
        ny += (v1[2] - v2[2]) * (v1[0] + v2[0])
        nz += (v1[0] - v2[0]) * (v1[1] + v2[1])
    return (nx / 2.0, ny / 2.0, nz / 2.0)

def get_attr(elem, attr_name):
    """대소문자 및 네임스페이스 구분 없이 속성 값을 안전하게 가져옵니다."""
    if elem is None: return None
    attr_lower = attr_name.lower()
    for k, v in elem.attrib.items():
        k_clean = re.sub(r'\{.*\}', '', k)
        if ':' in k_clean:
            k_clean = k_clean.split(':')[-1]
        if k_clean.lower() == attr_lower:
            return v
    return None

def azimuth_to_direction(azimuth):
    """방위각(Azimuth, 0~360°)을 방향 문자열로 변환합니다.
    gbXML 기준: 0°=북, 90°=동, 180°=남, 270°=서
    """
    if azimuth is None:
        return None
    try:
        az = float(azimuth) % 360
    except (ValueError, TypeError):
        return None
    
    if 315 <= az or az < 45:
        return "North"
    elif 45 <= az < 135:
        return "East"
    elif 135 <= az < 225:
        return "South"
    elif 225 <= az < 315:
        return "West"
    return None


def cluster_floor_levels(z_values, min_gap=1.5):
    """Z좌표 리스트를 클러스터링하여 층 레벨을 자동 감지합니다.
    
    인접한 Z좌표의 차이가 min_gap 미만이면 같은 층으로 간주합니다.
    반환값: 정렬된 층 레벨 리스트 (각 층의 바닥 Z좌표)
    """
    if not z_values:
        return [0.0]
    
    sorted_z = sorted(set(round(z, 2) for z in z_values))
    
    levels = [sorted_z[0]]
    for z in sorted_z[1:]:
        if z - levels[-1] >= min_gap:
            levels.append(z)
    
    return levels


def assign_floor_by_levels(z_value, floor_levels):
    """주어진 Z좌표가 어느 층에 속하는지 반환합니다 (1-indexed).
    
    각 층의 바닥 레벨에 가장 가까운 층을 찾습니다.
    """
    if not floor_levels:
        return 1
    
    best_floor = 1
    min_dist = float('inf')
    
    for i, level in enumerate(floor_levels):
        # 다음 층 레벨이 있으면 그 사이의 중간점을 경계로 사용
        if i + 1 < len(floor_levels):
            upper_bound = (level + floor_levels[i + 1]) / 2
        else:
            upper_bound = level + 100  # 마지막 층은 위쪽으로 넓게
        
        if level - 0.5 <= z_value < upper_bound:
            return i + 1
    
    # fallback: 가장 가까운 레벨
    for i, level in enumerate(floor_levels):
        dist = abs(z_value - level)
        if dist < min_dist:
            min_dist = dist
            best_floor = i + 1
    
    return best_floor


def detect_zone_gaps(surfaces_list):
    """Zone별 면 폐합(closure) 검증 — 법선벡터 합 방식.
    
    닫힌 볼륨(closed volume)이면 모든 면의 법선벡터 합이 영벡터에 근접합니다.
    법선벡터 합의 크기가 전체 면적 대비 임계값을 초과하면 경고를 생성합니다.
    
    반환값: warnings 리스트
    """
    DEVIATION_THRESHOLD = 0.05  # 5% 이상이면 경고
    
    zone_normals = {}  # zone_name -> [nx_sum, ny_sum, nz_sum]
    zone_areas = {}    # zone_name -> total_area
    
    for s in surfaces_list:
        zone = s.get("zone", "Unknown")
        if zone == "Unknown":
            continue
        
        verts = s.get("vertices", [])
        if len(verts) < 3:
            continue
        
        normal = calculate_surface_normal(verts)
        area = calculate_surface_area(verts)
        
        if zone not in zone_normals:
            zone_normals[zone] = [0.0, 0.0, 0.0]
            zone_areas[zone] = 0.0
        
        zone_normals[zone][0] += normal[0]
        zone_normals[zone][1] += normal[1]
        zone_normals[zone][2] += normal[2]
        zone_areas[zone] += area
    
    warnings = []
    for zone, normal_sum in zone_normals.items():
        total_area = zone_areas.get(zone, 0)
        if total_area <= 0:
            continue
        
        # 법선벡터 합의 크기
        residual = math.sqrt(
            normal_sum[0]**2 + normal_sum[1]**2 + normal_sum[2]**2
        )
        
        # 전체 면적 대비 잔차 비율
        deviation = residual / total_area
        
        if deviation > DEVIATION_THRESHOLD:
            warnings.append({
                "zone": zone,
                "issue": "not_enclosed",
                "deviation": round(deviation * 100, 1),  # 퍼센트
                "message": f"Zone \"{zone}\"의 면이 완전히 닫혀있지 않습니다 (오차: {round(deviation * 100, 1)}%)"
            })
    
    return warnings


def parse_gbxml_to_json(filepath: str):
    tree = ET.parse(filepath)
    root = tree.getroot()

    for elem in root.iter():
        if isinstance(elem.tag, str):
            elem.tag = strip_ns_and_lower(elem.tag)

    # 1. 도면 단위(Unit) 자동 감지 (Meters 기준 정규화)
    unit_scale = 1.0
    length_unit = get_attr(root, 'lengthunit')
    if length_unit:
        lu = length_unit.lower()
        if lu == 'millimeters': unit_scale = 0.001
        elif lu == 'centimeters': unit_scale = 0.01
        elif lu == 'feet': unit_scale = 0.3048
        elif lu == 'inches': unit_scale = 0.0254

    spaces = {}
    zones_list = []
    surfaces_list = []
    
    # 2. 건물 3D 중심점 및 최하단 Z축 계산
    all_x, all_y, all_z = [], [], []
    for pt in root.findall('.//cartesianpoint'):
        coords = pt.findall('.//coordinate')
        if len(coords) >= 3:
            try:
                all_x.append(float(coords[0].text) * unit_scale)
                all_y.append(float(coords[1].text) * unit_scale)
                all_z.append(float(coords[2].text) * unit_scale)
            except (ValueError, TypeError):
                pass
            
    offset_x = (min(all_x) + max(all_x)) / 2 if all_x else 0
    offset_y = (min(all_y) + max(all_y)) / 2 if all_y else 0
    offset_z = min(all_z) if all_z else 0

    # =====================================================
    # 💡 Material 데이터베이스 파싱
    # gbXML의 <Material> 요소에서 두께/열전도율/밀도/비열 추출
    # =====================================================
    INSULATION_CONDUCTIVITY_THRESHOLD = 0.1  # W/m·K 이하 → 단열재로 분류
    
    material_db = {}  # mat_id → {name, thickness, conductivity, density, specificHeat, isInsulation}
    for mat_elem in root.findall('.//material'):
        mat_id = get_attr(mat_elem, 'id')
        if not mat_id:
            continue
        
        mat_name_node = mat_elem.find('.//name')
        mat_name = mat_name_node.text if mat_name_node is not None and mat_name_node.text else mat_id
        # id에서 "mat-" 접두사 제거하여 가독성 향상
        if mat_name == mat_id and mat_id.startswith('mat-'):
            mat_name = mat_id[4:]
        
        thickness = 0.0
        conductivity = None
        density = None
        specific_heat = None
        
        t_elem = mat_elem.find('.//thickness')
        if t_elem is not None and t_elem.text:
            try:
                thickness = float(t_elem.text)
                # Meters → mm 변환 (gbXML 표준 단위는 Meters)
                t_unit = get_attr(t_elem, 'unit')
                if t_unit and 'meter' in t_unit.lower():
                    thickness = thickness * 1000  # m → mm
                elif thickness < 1.0 and thickness > 0:
                    # 단위 명시 없지만 값이 매우 작으면 m 단위로 추정
                    thickness = thickness * 1000
            except (ValueError, TypeError):
                pass
        
        c_elem = mat_elem.find('.//conductivity')
        if c_elem is not None and c_elem.text:
            try:
                conductivity = float(c_elem.text)
            except (ValueError, TypeError):
                pass
        
        d_elem = mat_elem.find('.//density')
        if d_elem is not None and d_elem.text:
            try:
                density = float(d_elem.text)
            except (ValueError, TypeError):
                pass
        
        sh_elem = mat_elem.find('.//specificheat')
        if sh_elem is not None and sh_elem.text:
            try:
                specific_heat = float(sh_elem.text)
            except (ValueError, TypeError):
                pass
        
        is_insulation = False
        if conductivity is not None and conductivity > 0 and thickness >= 20:
            # 열전도율이 낮고 두께가 20mm 이상인 경우 단열재 후보
            is_insulation = conductivity <= INSULATION_CONDUCTIVITY_THRESHOLD
            # 이름 기반 제외 (카펫, 마감재 등은 단열재가 아님)
            NON_INSULATION_NAMES = ['카펫', 'carpet', '마감', '타일', '석고', 'gypsum']
            if is_insulation and any(kw in mat_name.lower() for kw in NON_INSULATION_NAMES):
                is_insulation = False
        
        material_db[mat_id] = {
            "name": mat_name,
            "thickness": round(thickness, 1),       # mm
            "conductivity": conductivity,            # W/m·K
            "density": density,                      # kg/m³
            "specificHeat": specific_heat,            # J/kg·K
            "isInsulation": is_insulation
        }
    
    insul_count = sum(1 for m in material_db.values() if m["isInsulation"])
    if material_db:
        print(f"🧱 Material DB 파싱 완료: {len(material_db)}개 (단열재 {insul_count}개)")
    
    # =====================================================
    # 💡 Layer 데이터베이스 파싱
    # gbXML의 <Layer> 요소에서 MaterialId 참조 목록 추출
    # =====================================================
    layer_db = {}  # layer_id → [material_id_1, material_id_2, ...]
    for layer_elem in root.findall('.//layer'):
        lay_id = get_attr(layer_elem, 'id')
        if not lay_id:
            continue
        mat_refs = []
        for mat_id_elem in layer_elem.findall('.//materialid'):
            mat_ref = get_attr(mat_id_elem, 'materialidref')
            if mat_ref:
                mat_refs.append(mat_ref)
        layer_db[lay_id] = mat_refs

    # =====================================================
    # 💡 Construction 데이터베이스 파싱
    # gbXML의 <Construction> 요소에서 U-value/R-value 및 레이어 구성 추출
    # =====================================================
    construction_db = {}
    for constr in root.findall('.//construction'):
        c_id = get_attr(constr, 'id')
        if not c_id:
            continue
        
        c_name_node = constr.find('.//name')
        c_name = c_name_node.text if c_name_node is not None and c_name_node.text else c_id
        # id에서 "con-" 접두사 제거
        if c_name == c_id and c_id.startswith('con-'):
            c_name = c_id[4:]
        
        c_uvalue = None
        c_rvalue = None
        
        # U-value 직접 탐색 (다양한 태그명 대응)
        for tag_name in ['uvalue', 'u-value', 'ufactor', 'u-factor']:
            uval_elem = constr.find(f'.//{tag_name}')
            if uval_elem is not None and uval_elem.text:
                try:
                    c_uvalue = float(uval_elem.text)
                except (ValueError, TypeError):
                    pass
                break
        
        # R-value 탐색 (U-value가 없는 경우 R-value → U-value 변환)
        if c_uvalue is None:
            for tag_name in ['rvalue', 'r-value']:
                rval_elem = constr.find(f'.//{tag_name}')
                if rval_elem is not None and rval_elem.text:
                    try:
                        c_rvalue = float(rval_elem.text)
                        if c_rvalue > 0:
                            c_uvalue = 1.0 / c_rvalue
                    except (ValueError, TypeError):
                        pass
                    break
        
        # 단위 속성 확인 (IP 단위계일 경우 SI로 변환)
        uval_unit = get_attr(constr, 'unit')
        if c_uvalue and uval_unit and 'btu' in (uval_unit or '').lower():
            c_uvalue = c_uvalue * 5.678  # BTU/(hr·ft²·°F) → W/(m²·K)
        
        # Layer → Material 연결
        layers_info = []
        layer_id_elem = constr.find('.//layerid')
        if layer_id_elem is not None:
            lay_ref = get_attr(layer_id_elem, 'layeridref')
            if lay_ref and lay_ref in layer_db:
                for mat_ref in layer_db[lay_ref]:
                    if mat_ref in material_db:
                        layers_info.append(material_db[mat_ref])
        
        construction_db[c_id] = {
            "name": c_name,
            "uValue": c_uvalue,  # None이면 gbXML에 U-value 정보가 없음
            "layers": layers_info
        }
    
    if construction_db:
        found_count = sum(1 for v in construction_db.values() if v["uValue"] is not None)
        print(f"📐 Construction DB 파싱 완료: {len(construction_db)}개 중 U-value 보유 {found_count}개")
    
    # 타입별 기본 U-value (gbXML에 정보가 없을 때 fallback)
    DEFAULT_U_VALUES = {
        "exteriorwall": 0.43,
        "roof": 0.25,
        "floor": 0.50,
        "slab": 0.50,
        "slabongrade": 0.50,
        "undergroundslab": 0.50,
        "undergroundwall": 0.70,
        "interiorwall": 1.25,
        "internalwall": 1.25,
        "ceiling": 0.50,
        "interiorfloor": 0.50,
        "exteriorfloor": 0.50,
    }

    # 3. 공간(Space) 임시 저장
    space_elements = root.findall('.//space')
    for space in space_elements:
        sp_id = get_attr(space, 'id')
        if not sp_id: continue
        
        name_node = space.find('.//name')
        sp_name = name_node.text if name_node is not None and name_node.text else sp_id
        
        spaces[sp_id] = {
            "id": sp_id,
            "name": sp_name,
            "floor": 1,
            "isConditioned": True
        }
        
    # =====================================================
    # 💡 [1차 패스] Surface 파싱 및 Zone별 Z좌표 수집
    # =====================================================
    zone_z_coords = {}  # space_id -> [z1, z2, z3, ...]  (모든 꼭짓점의 Z좌표)
    
    all_surfaces = root.findall('.//surface')
    for surf in all_surfaces:
        surf_id = get_attr(surf, 'id')
        surf_type = get_attr(surf, 'surfacetype') or "Unknown"
        construction_ref = get_attr(surf, 'constructionidref')
        adj_spaces = surf.findall('.//adjacentspaceid')
        space_1 = get_attr(adj_spaces[0], 'spaceidref') if len(adj_spaces) > 0 else None
        space_2 = get_attr(adj_spaces[1], 'spaceidref') if len(adj_spaces) > 1 else None

        zone_name = spaces.get(space_1, {}).get('name', "Unknown") if space_1 else "Unknown"
        adj_zone_name = spaces.get(space_2, {}).get('name') if space_2 else None

        poly_loop = surf.find('.//planargeometry//polyloop')
        if poly_loop is None:
            poly_loop = surf.find('.//polyloop')

        vertices = []
        if poly_loop is not None:
            for pt in poly_loop.findall('.//cartesianpoint'):
                coords = pt.findall('.//coordinate')
                if len(coords) >= 3:
                    try:
                        vx = (float(coords[0].text) * unit_scale) - offset_x
                        vy = (float(coords[1].text) * unit_scale) - offset_y
                        vz = (float(coords[2].text) * unit_scale) - offset_z
                        vertices.append([vx, vy, vz])
                    except (ValueError, TypeError):
                        pass

        if len(vertices) < 3:
            continue

        # Zone별 Z좌표 수집 (높이 역산 및 층수 클러스터링용)
        if space_1 and space_1 in spaces:
            if space_1 not in zone_z_coords:
                zone_z_coords[space_1] = []
            for v in vertices:
                zone_z_coords[space_1].append(v[2])
        
        # U-value 결정 (1순위: gbXML Construction, 2순위: 타입별 기본값)
        u_value = None
        u_source = "default"
        
        if construction_ref and construction_ref in construction_db:
            constr_data = construction_db[construction_ref]
            if constr_data["uValue"] is not None:
                u_value = constr_data["uValue"]
                u_source = "gbxml"
        
        if u_value is None:
            surf_type_lower = surf_type.lower().replace(" ", "")
            for key, default_u in DEFAULT_U_VALUES.items():
                if key in surf_type_lower:
                    u_value = default_u
                    break
            if u_value is None:
                u_value = 0.8

        # 방향(Azimuth) 파싱
        direction = None
        azimuth_value = None
        
        rect_geom = surf.find('.//rectangulargeometry')
        if rect_geom is not None:
            az_elem = rect_geom.find('.//azimuth')
            if az_elem is not None and az_elem.text:
                try:
                    azimuth_value = float(az_elem.text)
                    direction = azimuth_to_direction(azimuth_value)
                except (ValueError, TypeError):
                    pass

        mapped_type = surf_type
        surf_type_lower = surf_type.lower()
        if "exteriorwall" in surf_type_lower: mapped_type = "ExteriorWall"
        elif "interiorwall" in surf_type_lower or "internalwall" in surf_type_lower: mapped_type = "InteriorWall"
        elif "roof" in surf_type_lower: mapped_type = "Roof"
        elif "ceiling" in surf_type_lower: mapped_type = "Ceiling"
        elif "interiorfloor" in surf_type_lower or "internalfloor" in surf_type_lower: mapped_type = "InteriorFloor"
        elif "exteriorfloor" in surf_type_lower: mapped_type = "ExteriorFloor"
        elif "slabongrade" in surf_type_lower: mapped_type = "SlabOnGrade"
        elif "undergroundslab" in surf_type_lower: mapped_type = "UndergroundSlab"
        elif "undergroundwall" in surf_type_lower: mapped_type = "UndergroundWall"
        elif "slab" in surf_type_lower: mapped_type = "SlabOnGrade"
        elif "floor" in surf_type_lower: mapped_type = "Floor"
        elif "exterior" in surf_type_lower: mapped_type = "ExteriorWall"
        elif "interior" in surf_type_lower or "internal" in surf_type_lower: mapped_type = "InteriorWall"
        
        # Roof/Floor 타입에 방향 자동 배정
        if mapped_type == "Roof":
            direction = "Roof"
        elif mapped_type in ("Floor", "SlabOnGrade", "UndergroundSlab", "ExteriorFloor", "InteriorFloor", "Ceiling"):
            direction = "Floor"
        
        surface_data = {
            "id": surf_id,
            "type": mapped_type,
            "zone": zone_name,
            "adjacentZone": adj_zone_name,
            "floor": 1,  # 임시값, 아래에서 클러스터링 후 재배정
            "direction": direction,
            "azimuth": azimuth_value,
            "vertices": vertices,
            "uValue": round(u_value, 4),
            "uSource": u_source,
            "constructionRef": construction_ref,
            "wwr": 0,
            "openings": [],
            "_space_id": space_1,  # 내부용: 층수 계산에 사용 후 삭제
        }

        surf_area = calculate_surface_area(vertices)
        surface_data["area"] = round(surf_area, 2)
        total_op_area = 0.0

        # 5. 창문/문(Opening) 파싱
        for opening in surf.findall('.//opening'):
            op_id = get_attr(opening, 'id')
            op_type = get_attr(opening, 'openingtype')
            
            op_poly = opening.find('.//planargeometry//polyloop')
            if op_poly is None:
                op_poly = opening.find('.//polyloop')
            
            op_verts = []
            if op_poly is not None:
                for pt in op_poly.findall('.//cartesianpoint'):
                    c = pt.findall('.//coordinate')
                    if len(c) >= 3:
                        try:
                            vx = (float(c[0].text) * unit_scale) - offset_x
                            vy = (float(c[1].text) * unit_scale) - offset_y
                            vz = (float(c[2].text) * unit_scale) - offset_z
                            op_verts.append([vx, vy, vz])
                        except:
                            pass
            
            if len(op_verts) >= 3:
                total_op_area += calculate_surface_area(op_verts)
                
            surface_data["openings"].append({
                "id": op_id,
                "type": op_type or "Unknown",
                "vertices": op_verts,
                "uValue": 2.5,
                "shgc": 0.7
            })

        # WWR 계산 반영
        if surf_area > 0 and total_op_area > 0:
            calc_wwr = int((total_op_area / surf_area) * 100)
            surface_data["wwr"] = min(calc_wwr, 90)

        surfaces_list.append(surface_data)

    # =====================================================
    # 💡 [2차 패스] Zone별 높이 자동역산 + Z클러스터링 층 배정
    # =====================================================
    
    # Zone별 높이 계산: Z좌표 min/max 차이
    zone_heights = {}  # space_id -> height (m)
    zone_min_z = {}    # space_id -> min_z (바닥 Z좌표)
    
    for sp_id, z_coords in zone_z_coords.items():
        if z_coords:
            z_min = min(z_coords)
            z_max = max(z_coords)
            height = z_max - z_min
            # 최소 2.0m, 비정상적이면 기본 3.0m
            if height < 2.0:
                height = 3.0
            zone_heights[sp_id] = round(height, 2)
            zone_min_z[sp_id] = z_min
        else:
            zone_heights[sp_id] = 3.0
            zone_min_z[sp_id] = 0.0
    
    # Z클러스터링: Zone 바닥 Z좌표를 기반으로 층 레벨 자동 감지
    all_floor_z = list(zone_min_z.values())
    floor_levels = cluster_floor_levels(all_floor_z, min_gap=1.5)
    
    print(f"🏗️ 층 레벨 자동 감지: {len(floor_levels)}개 층 → {[round(z, 2) for z in floor_levels]}")
    for sp_id, z_coords in zone_z_coords.items():
        sp_name = spaces.get(sp_id, {}).get("name", sp_id)
        h = zone_heights.get(sp_id, 3.0)
        print(f"   Zone \"{sp_name}\": 높이={h}m, 바닥Z={round(zone_min_z.get(sp_id, 0), 2)}m")
    
    # Zone별 층 배정
    zone_floor_map = {}  # space_id -> floor_number
    for sp_id, min_z in zone_min_z.items():
        zone_floor_map[sp_id] = assign_floor_by_levels(min_z, floor_levels)
    
    # =====================================================
    # 💡 [신규] 높이 이상치 감지 → 별도 가상 층으로 분리
    # 같은 층에 배정된 Zone들 중 높이가 현저히 다른 Zone을
    # 자동으로 별도 층(max_floor + 1, +2, ...)으로 올려줍니다.
    # 이를 통해 엘리베이터 샤프트, 창고, 다층 공간 등을 분리합니다.
    # =====================================================
    
    # 각 floor_level 그룹별로 Zone 높이 목록 수집
    floor_height_groups = {}  # floor_number -> [(sp_id, height)]
    for sp_id, floor_num in zone_floor_map.items():
        h = zone_heights.get(sp_id, 3.0)
        if floor_num not in floor_height_groups:
            floor_height_groups[floor_num] = []
        floor_height_groups[floor_num].append((sp_id, h))
    
    HEIGHT_OUTLIER_RATIO = 1.5  # 중앙값의 1.5배 초과 시 아웃라이어로 판단
    
    virtual_floor_counter = max(floor_height_groups.keys()) if floor_height_groups else 1
    virtual_floor_map = {}  # 아웃라이어 sp_id -> 새 가상 층 번호
    
    for floor_num, sp_heights in floor_height_groups.items():
        if len(sp_heights) < 2:
            # 그 층에 Zone이 하나뿐이면 비교 불가, 건너뜀
            continue
        
        heights = [h for _, h in sp_heights]
        # 중앙값 계산
        sorted_h = sorted(heights)
        n = len(sorted_h)
        median_h = (sorted_h[n // 2] + sorted_h[(n - 1) // 2]) / 2
        
        for sp_id, h in sp_heights:
            if median_h > 0 and h / median_h > HEIGHT_OUTLIER_RATIO:
                # 아웃라이어: 이미 같은 높이로 분리된 가상 층이 있으면 재사용
                matched_virtual = None
                for v_sp_id, v_floor in virtual_floor_map.items():
                    if abs(zone_heights.get(v_sp_id, 0) - h) < 0.5:
                        matched_virtual = v_floor
                        break
                
                if matched_virtual is None:
                    virtual_floor_counter += 1
                    matched_virtual = virtual_floor_counter
                
                virtual_floor_map[sp_id] = matched_virtual
                sp_name = spaces.get(sp_id, {}).get("name", sp_id)
                print(f"   ⚡ Zone \"{sp_name}\" 높이 이상치 감지 (높이={h}m, 중앙값={median_h:.1f}m) → 가상 {matched_virtual}층으로 분리")
    
    # 가상 층 배정 적용
    for sp_id, v_floor in virtual_floor_map.items():
        zone_floor_map[sp_id] = v_floor
    
    if virtual_floor_map:
        print(f"   ✅ 높이 이상치 {len(virtual_floor_map)}개 Zone 가상 층 분리 완료")

    # spaces 딕셔너리에 높이와 층수 업데이트
    for sp_id in spaces:
        spaces[sp_id]["floor"] = zone_floor_map.get(sp_id, 1)
        spaces[sp_id]["height"] = zone_heights.get(sp_id, 3.0)
    
    # Surface의 층수를 Zone 기반으로 재배정
    for s in surfaces_list:
        sp_id = s.pop("_space_id", None)  # 내부용 필드 제거
        if sp_id and sp_id in zone_floor_map:
            s["floor"] = zone_floor_map[sp_id]
        else:
            # Zone에 속하지 않는 Surface는 Z좌표로 직접 배정
            center_z = sum(v[2] for v in s["vertices"]) / len(s["vertices"])
            s["floor"] = assign_floor_by_levels(center_z, floor_levels)

    # =====================================================
    # 💡 면 갭(Gap) 검증 — 법선벡터 합 방식
    # =====================================================
    gap_warnings = detect_zone_gaps(surfaces_list)
    
    if gap_warnings:
        print(f"⚠️ 면 폐합 검증 경고: {len(gap_warnings)}개 Zone에서 갭 감지됨")
        for w in gap_warnings:
            print(f"   {w['message']}")

    # 6. 존(Zone) 리스트 완성
    for sp_id, sp_data in spaces.items():
        zones_list.append({
            "id": sp_data["name"],
            "floor": sp_data["floor"],
            "height": sp_data.get("height", 3.0),  # 💡 [신규] 역산된 높이
            "activityId": 1105,
            "isConditioned": True,
            "heatingSetpoint": 20.0,
            "coolingSetpoint": 26.0
        })

    # 7. 파싱 요약 출력
    u_from_gbxml = sum(1 for s in surfaces_list if s.get("uSource") == "gbxml")
    u_from_default = sum(1 for s in surfaces_list if s.get("uSource") == "default")
    dir_count = sum(1 for s in surfaces_list if s.get("direction") is not None)
    print(f"📊 파싱 완료 → Zone {len(zones_list)}개, Surface {len(surfaces_list)}개")
    print(f"   U-value: gbXML 원본 {u_from_gbxml}개 / 기본값 {u_from_default}개")
    print(f"   방향(Direction) 매핑: {dir_count}개")
    print(f"   층 수: {len(floor_levels)}개 층")

    # =====================================================
    # 💡 Construction별 사용 면적 · 단열재 요약 정보 생성
    # =====================================================
    # Construction별 적용 Surface 수 및 면적 합산
    constr_usage = {}  # c_id → {"count": int, "area": float, "types": set()}
    for s in surfaces_list:
        c_ref = s.get("constructionRef")
        if c_ref:
            if c_ref not in constr_usage:
                constr_usage[c_ref] = {"count": 0, "area": 0.0, "types": set()}
            constr_usage[c_ref]["count"] += 1
            constr_usage[c_ref]["area"] += calculate_surface_area(s.get("vertices", []))
            constr_usage[c_ref]["types"].add(s.get("type", "Unknown"))
    
    # Construction 목록 (레이어 구성 + 사용 현황)
    constructions_info = []
    for c_id, c_data in construction_db.items():
        usage = constr_usage.get(c_id, {"count": 0, "area": 0.0, "types": set()})
        if usage["count"] == 0:
            continue  # 사용되지 않는 Construction은 제외
        constructions_info.append({
            "id": c_id,
            "name": c_data["name"],
            "uValue": c_data.get("uValue"),
            "layers": c_data.get("layers", []),
            "surfaceCount": usage["count"],
            "totalArea": round(usage["area"], 1),
            "surfaceTypes": list(usage["types"])
        })
    
    # 단열재 요약 (중복 제거)
    insulation_summary = []
    seen_insulation = set()
    for c_info in constructions_info:
        for layer in c_info.get("layers", []):
            if layer.get("isInsulation") and layer["name"] not in seen_insulation:
                seen_insulation.add(layer["name"])
                # 이 단열재가 사용된 Construction 목록
                used_in = [ci["name"] for ci in constructions_info 
                          if any(l.get("name") == layer["name"] and l.get("isInsulation") 
                                for l in ci.get("layers", []))]
                total_area = sum(ci["totalArea"] for ci in constructions_info 
                               if any(l.get("name") == layer["name"] and l.get("isInsulation") 
                                     for l in ci.get("layers", [])))
                insulation_summary.append({
                    "name": layer["name"],
                    "conductivity": layer.get("conductivity"),
                    "thickness": layer.get("thickness"),
                    "density": layer.get("density"),
                    "usedIn": used_in,
                    "totalArea": round(total_area, 1)
                })
    
    if insulation_summary:
        print(f"   🧊 단열재 {len(insulation_summary)}종 감지:")
        for ins in insulation_summary:
            print(f"      - {ins['name']}: λ={ins['conductivity']} W/m·K, 두께={ins['thickness']}mm, 면적={ins['totalArea']}㎡")

    return {
        "zones": zones_list,
        "surfaces": surfaces_list,
        "warnings": gap_warnings,
        "floorLevels": len(floor_levels),
        "materials": {
            "constructions": constructions_info,
            "insulationSummary": insulation_summary
        }
    }