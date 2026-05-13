# src/gbxml_parser.py
import defusedxml.ElementTree as ET
import re

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
    import math
    return math.sqrt(nx*nx + ny*ny + nz*nz) / 2.0

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
    # 💡 [신규] Construction 데이터베이스 파싱
    # gbXML의 <Construction> 요소에서 U-value/R-value 추출
    # =====================================================
    construction_db = {}
    for constr in root.findall('.//construction'):
        c_id = get_attr(constr, 'id')
        if not c_id:
            continue
        
        c_name_node = constr.find('.//name')
        c_name = c_name_node.text if c_name_node is not None and c_name_node.text else c_id
        
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
        
        construction_db[c_id] = {
            "name": c_name,
            "uValue": c_uvalue  # None이면 gbXML에 U-value 정보가 없음
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
            "floor": 1, # 일단 1층으로 두고 Surface 높이로 자동 보정
            "isConditioned": True
        }
        
    # 4. 면(Surface) 추출 및 층(Floor) 동적 슬라이싱
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

        # 💡 핵심: 3D Z축(높이) 중심점을 기준으로 3m마다 1개 층으로 자동 계산
        center_z = sum([v[2] for v in vertices]) / len(vertices)
        assigned_floor = int(max(0, center_z) // 3.0) + 1

        # 공간(Space)의 층수도 맞게 업데이트
        if space_1 and spaces.get(space_1):
            spaces[space_1]["floor"] = max(spaces[space_1]["floor"], assigned_floor)

        # =====================================================
        # 💡 [신규] U-value 결정 우선순위:
        # 1순위: gbXML Construction에서 읽은 실제 U-value
        # 2순위: 면 타입별 기본값 (fallback)
        # =====================================================
        u_value = None
        u_source = "default"
        
        # 1순위: constructionIdRef → Construction DB 조회
        if construction_ref and construction_ref in construction_db:
            constr_data = construction_db[construction_ref]
            if constr_data["uValue"] is not None:
                u_value = constr_data["uValue"]
                u_source = "gbxml"
        
        # 2순위: 타입별 기본값 fallback
        if u_value is None:
            surf_type_lower = surf_type.lower().replace(" ", "")
            for key, default_u in DEFAULT_U_VALUES.items():
                if key in surf_type_lower:
                    u_value = default_u
                    break
            if u_value is None:
                u_value = 0.8  # 최종 fallback

        # =====================================================
        # 💡 [신규] 방향(Azimuth) 파싱 → direction 필드 생성
        # gbXML RectangularGeometry > Azimuth 태그에서 추출
        # =====================================================
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
        # 올바른 매핑 (포함 관계로 잘못 매핑되는 것 방지)
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
            "floor": assigned_floor,
            "direction": direction,        # 💡 [신규] 방향 (North/South/East/West/Roof/Floor)
            "azimuth": azimuth_value,       # 💡 [신규] 원본 방위각 (0~360°)
            "vertices": vertices,
            "uValue": round(u_value, 4),
            "uSource": u_source,            # 💡 [신규] U-value 출처 ("gbxml" 또는 "default")
            "constructionRef": construction_ref,  # 💡 [신규] Construction 참조 ID
            "wwr": 0,
            "openings": []
        }

        surf_area = calculate_surface_area(vertices)
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

    # 6. 존(Zone) 리스트 완성
    for sp_id, sp_data in spaces.items():
        zones_list.append({
            "id": sp_data["name"],
            "floor": sp_data["floor"],
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

    return {
        "zones": zones_list,
        "surfaces": surfaces_list
    }