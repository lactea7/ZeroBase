# src/gbxml_parser.py
import xml.etree.ElementTree as ET
import re

def strip_ns_and_lower(tag):
    """XML 태그에서 네임스페이스와 접두사를 모두 제거하고 소문자로 변환합니다."""
    tag = re.sub(r'\{.*\}', '', tag)
    if ':' in tag:
        tag = tag.split(':')[-1]
    return tag.lower()

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
    for surf in root.findall('.//surface'):
        surf_id = get_attr(surf, 'id')
        surf_type = get_attr(surf, 'surfacetype') or "Unknown"
            
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

        u_value = 0.8
        surf_type_lower = surf_type.lower()
        if "exteriorwall" in surf_type_lower: u_value = 0.43
        elif "roof" in surf_type_lower: u_value = 0.25
        elif "floor" in surf_type_lower or "slab" in surf_type_lower: u_value = 0.50
        elif "interiorwall" in surf_type_lower or "internal" in surf_type_lower: u_value = 1.25

        mapped_type = surf_type
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
        surface_data = {
            "id": surf_id,
            "type": mapped_type,
            "zone": zone_name,
            "adjacentZone": adj_zone_name,
            "floor": assigned_floor, # 프론트엔드로 층수 전달!
            "vertices": vertices,
            "uValue": u_value,
            "wwr": 0,
            "openings": []
        }

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
            
            surface_data["openings"].append({
                "id": op_id,
                "type": op_type or "Unknown",
                "vertices": op_verts,
                "uValue": 2.5,
                "shgc": 0.7
            })

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

    return {
        "zones": zones_list,
        "surfaces": surfaces_list
    }