"""파싱 결과(zones/surfaces)에 대한 무결성 검증.

업로드 모달의 차단은 클라이언트 UX 일 뿐이다. 다른 클라이언트나 변조된 요청은
그 화면을 거치지 않고 `/api/simulate` 로 직접 들어올 수 있으므로, 시뮬레이션
진입점에서도 같은 기준으로 막아야 한다.

파서(gbxml_parser)는 XML 원문에서만 알 수 있는 것(중복 id, 단위, 선언 면적)을 검사하고,
여기서는 **payload 로 전달된 zones/surfaces 만으로 판정 가능한 것**을 다시 본다.
따라서 두 검사는 겹치지만 목적이 다르다 — 파서는 진단, 이쪽은 신뢰 경계다.
"""
import math


def _area(vertices):
    if not vertices or len(vertices) < 3:
        return 0.0
    nx = ny = nz = 0.0
    for i in range(len(vertices)):
        a, b = vertices[i], vertices[(i + 1) % len(vertices)]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    return math.sqrt(nx * nx + ny * ny + nz * nz) / 2.0


def validate_simulation_payload(zones, surfaces):
    """시뮬레이션을 진행해도 되는지 판정한다.

    반환: (blocking, warnings) — blocking 이 비어 있지 않으면 진행 불가.
    """
    blocking = []
    warnings = []

    # set 으로 바로 만들면 중복을 잃는다. 파서가 Space.Name 을 zone id 로 쓰기 때문에
    # XML 의 Space id 가 고유해도 Name 이 겹치면 여기서 zone id 가 충돌한다 —
    # 이 검사는 payload 단계에만 존재할 수 있다.
    _zid_list = [z.get("id") for z in (zones or []) if z.get("id")]
    zone_ids = set(_zid_list)
    _dup_zone = sorted({z for z in _zid_list if _zid_list.count(z) > 1})
    if _dup_zone:
        blocking.append({
            "issue": "duplicate_zone_id",
            "count": len(_dup_zone),
            "message": f"같은 이름을 가진 존이 {len(_dup_zone)}건 있습니다 "
                       f"({', '.join(_dup_zone[:3])}). 존이 하나로 합쳐져 면적·부하가 "
                       f"뒤섞이므로 이름을 구분해 주세요.",
        })

    # 빈 id 를 가진 존·면은 EnergyPlus 객체명을 만들 수 없다.
    if any(not z.get("id") for z in (zones or [])):
        blocking.append({
            "issue": "empty_zone_id",
            "message": "이름이 없는 존이 있습니다.",
        })
    if any(not s.get("id") for s in (surfaces or [])):
        blocking.append({
            "issue": "empty_surface_id",
            "message": "id 가 없는 면이 있습니다.",
        })

    if not zone_ids:
        blocking.append({
            "issue": "no_zones",
            "message": "존이 하나도 없습니다. 시뮬레이션할 대상이 없습니다.",
        })

    # 중복 면 id — EnergyPlus 객체명이 충돌해 결과가 뒤섞인다.
    seen = set()
    dup = []
    for s in (surfaces or []):
        sid = s.get("id")
        if not sid:
            continue
        if sid in seen:
            dup.append(sid)
        seen.add(sid)
    if dup:
        blocking.append({
            "issue": "duplicate_surface_id",
            "count": len(dup),
            "message": f"같은 id 를 가진 면이 {len(dup)}건 있습니다 ({', '.join(dup[:3])}). "
                       f"EnergyPlus 객체명이 충돌해 결과를 신뢰할 수 없습니다.",
        })

    # 존재하지 않는 존에 속한 면 — 그 면은 모델에서 사라진다.
    orphan = [s.get("id") for s in (surfaces or [])
              if s.get("zone") and s.get("zone") not in zone_ids]
    if orphan:
        warnings.append({
            "issue": "orphan_surface",
            "count": len(orphan),
            "message": f"어느 존에도 속하지 않는 면이 {len(orphan)}개 있습니다 — 모델에서 제외됩니다.",
        })

    # 개구부가 호스트 면을 초과 — 창면적비가 성립하지 않는다.
    overflow = []
    for s in (surfaces or []):
        host = _area(s.get("vertices"))
        if host <= 0:
            continue
        op_total = sum(_area(o.get("vertices")) for o in (s.get("openings") or []))
        if op_total > host + max(host * 0.005, 0.01):
            overflow.append(s.get("id"))
    if overflow:
        blocking.append({
            "issue": "opening_exceeds_host",
            "count": len(overflow),
            "message": f"창·문 면적이 벽 면적을 넘는 면이 {len(overflow)}개 있습니다 "
                       f"({', '.join(str(x) for x in overflow[:3])}).",
        })

    # 면적 필드가 비정상인 존 — 면적당 지표의 분모가 무너진다.
    # area 뿐 아니라 declaredArea·geometricArea 도 봐야 한다. 시뮬레이터가
    # declaredArea → geometricArea 순으로 신뢰하므로, 이 값이 오염되면 그대로 쓰인다.
    bad_area = []
    for z in (zones or []):
        for field in ("area", "declaredArea", "geometricArea"):
            v = z.get(field)
            if v is None:
                continue
            try:
                fv = float(v)
            except (TypeError, ValueError):
                bad_area.append(f"{z.get('id')}.{field}")
                continue
            if not math.isfinite(fv) or fv < 0:
                bad_area.append(f"{z.get('id')}.{field}")
    if bad_area:
        blocking.append({
            "issue": "invalid_zone_area",
            "count": len(bad_area),
            "message": f"면적이 음수이거나 숫자가 아닌 항목이 {len(bad_area)}개 있습니다 "
                       f"({', '.join(bad_area[:3])}).",
        })

    # 클라이언트가 보낸 geometricArea 를 그대로 믿지 않는다. 서버가 surfaces 로
    # 다시 계산해 크게 어긋나면 조용히 쓰지 않고 막는다 (변조·버전 불일치 방어).
    try:
        from src.gbxml_parser import compute_zone_floor_geometry
        recomputed = compute_zone_floor_geometry(surfaces or [])
    except Exception:
        recomputed = {}
    drifted = []
    for z in (zones or []):
        claimed = z.get("geometricArea")
        if claimed is None:
            continue
        try:
            claimed = float(claimed)
        except (TypeError, ValueError):
            continue
        if claimed <= 0:
            continue
        server = (recomputed.get(z.get("id")) or (0.0, 0.0, ""))[0]
        if server <= 0:
            continue
        if abs(claimed - server) > max(server * 0.05, 0.5):
            drifted.append(f"{z.get('id')}({claimed:.1f}≠{server:.1f}㎡)")
    if drifted:
        blocking.append({
            "issue": "geometric_area_drift",
            "count": len(drifted),
            "message": f"전달된 도형 면적이 서버 재계산값과 다른 존이 {len(drifted)}개 있습니다 "
                       f"({', '.join(drifted[:3])}). 파일을 다시 올려 주세요.",
        })

    return blocking, warnings
