# mcp_server.py — ZeroBase 그린 리트로핏 MCP 서버 (stdio)
# gbXML 파싱 → EnergyPlus 시뮬레이션(비동기 잡) → 비용/LCC 결과 조회를 MCP 도구로 노출한다.
# 시뮬레이션 1회가 ~2.5분 걸리므로 실행은 start → status 폴링 → result 조회의 잡 패턴.
# 실행: python3 mcp_server.py  (Claude Code .mcp.json / Claude Desktop 설정에서 호출)
import json
import os
import sys
import threading
import time
import uuid

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
# ep_simulator가 _data/temp_workspace를 상대경로로 참조하므로 cwd를 백엔드로 고정
# (Claude Desktop은 cwd=/ 로 서버를 띄운다)
os.chdir(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

from mcp.server.fastmcp import FastMCP

from src.gbxml_parser import parse_gbxml_to_json
from src.ep_simulator import calculate_surface_area, generate_idf_and_simulate
from src.task_store import TaskStore

WEATHER_DIR = os.path.join(os.path.dirname(BACKEND_DIR), "_data", "weather")
WORKSPACE_ROOT = os.path.join(BACKEND_DIR, "temp_workspace")

mcp = FastMCP("green-retrofit")
# FastAPI 서버의 tasks.db와 분리 — 두 프로세스가 같은 큐를 prune하지 않도록
task_store = TaskStore(os.path.join(BACKEND_DIR, "mcp_tasks.db"))
task_store.recover_orphans()

HEAT_SOURCES = {1: "가스보일러", 2: "전기(히트펌프)", 4: "등유보일러", 11: "지역난방"}


def _zone_floor_area(zone_id, surfaces):
    return sum(
        calculate_surface_area(s.get("vertices", []))
        for s in surfaces
        if s.get("zone") == zone_id
        and ("floor" in s.get("type", "").lower() or "slab" in s.get("type", "").lower())
    )


@mcp.tool()
def parse_gbxml(gbxml_path: str) -> dict:
    """gbXML 건물 모델 파일을 파싱해 존/표면/면적 요약과 모델 품질 경고를 반환한다.

    시뮬레이션 전에 모델이 정상인지 확인할 때 사용. gbxml_path는 절대경로.
    """
    if not os.path.isfile(gbxml_path):
        return {"error": f"파일이 없습니다: {gbxml_path}"}
    parsed = parse_gbxml_to_json(gbxml_path)
    zones, surfaces = parsed["zones"], parsed["surfaces"]

    total_floor = total_wall = total_window = 0.0
    type_counts = {}
    for s in surfaces:
        t = s.get("type", "Unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
        a = calculate_surface_area(s.get("vertices", []))
        tl = t.lower()
        if "floor" in tl or "slab" in tl:
            total_floor += a
        if "wall" in tl:
            total_wall += a
            total_window += a * (s.get("wwr", 0) / 100.0)

    # 모델 품질: 바닥 폴리곤이 없거나 1㎡ 미만인 존 (천장/지붕 면적 폴백이 적용됨)
    degenerate = []
    for z in zones:
        fa = _zone_floor_area(z["id"], surfaces)
        if fa < 1.0:
            degenerate.append({"zone": z["id"], "floor_area_m2": round(fa, 2)})

    return {
        "zones": len(zones),
        "surfaces": len(surfaces),
        "surface_types": type_counts,
        "total_floor_area_m2": round(total_floor, 1),
        "total_wall_area_m2": round(total_wall, 1),
        "total_window_area_m2": round(total_window, 1),
        "zone_names_sample": [z["id"] for z in zones[:10]],
        "warnings": (
            [f"바닥 폴리곤 누락/퇴화 존 {len(degenerate)}개 — 천장/지붕 면적 폴백 적용됨"]
            if degenerate else []
        ),
        "degenerate_zones": degenerate,
    }


@mcp.tool()
def list_weather_locations() -> dict:
    """시뮬레이션에 사용 가능한 한국 기상데이터(TMYx) 지역 키 목록을 반환한다."""
    if not os.path.isdir(WEATHER_DIR):
        return {"error": f"기상데이터 디렉토리가 없습니다: {WEATHER_DIR}"}
    keys = sorted({f.split(".")[0] for f in os.listdir(WEATHER_DIR) if f.lower().endswith(".epw")})
    return {"count": len(keys), "locations": keys}


def _run_task(task_id: str, payload: dict, workdir: str):
    try:
        task_store.mark_running(task_id)
        result = generate_idf_and_simulate(
            payload, workdir, on_stage=lambda s: task_store.set_stage(task_id, s)
        )
        task_store.finish(task_id, result=result)
    except Exception as e:  # noqa: BLE001 — 잡 실패는 상태로 전달
        task_store.finish(task_id, error=str(e))


@mcp.tool()
def start_simulation(
    gbxml_path: str,
    location: str = "KOR_SO_Seoul",
    heat_source: int = 11,
    pv_capacity_kw: float = 0,
    geothermal: bool = False,
    target_budget_manwon: float = 0,
    project_name: str = "MCP 시뮬레이션",
) -> dict:
    """gbXML 건물의 EnergyPlus 연간(8760h) 시뮬레이션 + 비용/LCC 분석을 시작한다.

    ~2.5분 소요되는 비동기 잡. 반환된 task_id로 get_simulation_status를 폴링하고,
    완료되면 get_simulation_result로 결과를 조회한다.

    Args:
        gbxml_path: gbXML 파일 절대경로.
        location: 기상데이터 지역 키 (list_weather_locations 참조). 기본 서울.
        heat_source: 난방 열원 — 1 가스보일러, 2 전기(히트펌프), 4 등유보일러, 11 지역난방(기본).
        pv_capacity_kw: 태양광 설치 용량(kW). 0이면 미설치.
        geothermal: 지열 히트펌프 적용 여부.
        target_budget_manwon: 목표 공사 예산(만원). 0이면 미설정.
    """
    if not os.path.isfile(gbxml_path):
        return {"error": f"파일이 없습니다: {gbxml_path}"}
    if heat_source not in HEAT_SOURCES:
        return {"error": f"heat_source는 {list(HEAT_SOURCES)} 중 하나여야 합니다"}
    if task_store.count_pending() >= 1:
        return {"error": "이미 실행 중인 시뮬레이션이 있습니다. 완료 후 다시 시작하세요."}

    parsed = parse_gbxml_to_json(gbxml_path)
    payload = {
        "projectData": {
            "name": project_name,
            "location": location,
            "heatSource": heat_source,
            "pvCapacity": pv_capacity_kw or 0,
            "geothermalApplied": bool(geothermal),
            "targetBudget": target_budget_manwon or 0,
        },
        "zones": parsed["zones"],
        "surfaces": parsed["surfaces"],
        "materials": parsed.get("materials", {}),
        "constructionOverrides": {},
    }

    task_id = uuid.uuid4().hex[:12]
    workdir = os.path.join(WORKSPACE_ROOT, f"mcp_{task_id}")
    task_store.create(task_id)
    threading.Thread(target=_run_task, args=(task_id, payload, workdir), daemon=True).start()
    return {
        "task_id": task_id,
        "status": "queued",
        "note": "약 2~3분 소요. get_simulation_status(task_id)로 진행 상태를 확인하세요.",
        "heat_source": HEAT_SOURCES[heat_source],
        "zones": len(parsed["zones"]),
    }


@mcp.tool()
def get_simulation_status(task_id: str) -> dict:
    """시뮬레이션 잡의 상태(queued/running/success/failed)와 진행 단계를 반환한다."""
    task = task_store.get(task_id)
    if task is None:
        return {"error": f"task_id를 찾을 수 없습니다: {task_id}"}
    out = {"task_id": task_id, "status": task["status"]}
    if task.get("stage"):
        out["stage"] = task["stage"]
    if task.get("started_at"):
        out["elapsed_sec"] = round((task.get("finished_at") or time.time()) - task["started_at"])
    if task["status"] == "failed":
        out["error"] = task.get("error")
    if task["status"] == "success":
        out["note"] = "get_simulation_result(task_id, section)로 결과를 조회하세요."
    return out


@mcp.tool()
def get_simulation_result(task_id: str, section: str = "summary") -> dict:
    """완료된 시뮬레이션의 결과를 섹션별로 조회한다.

    section:
        summary          — 연간 에너지 소요량/1차에너지/CO2/자립률 + 요금/공사비/절감 핵심 지표
        monthly          — 월별 난방/냉방/조명/기기/급탕 (kWh/㎡)
        financial        — 공사비 내역, 요금, NPV/IRR, LCC 파라미터, 산정 유의사항
        recommendations  — 추가 절감 대안 목록
        baseline         — 개선 전(원본 건물) 대비 비교
    """
    task = task_store.get(task_id)
    if task is None:
        return {"error": f"task_id를 찾을 수 없습니다: {task_id}"}
    if task["status"] != "success":
        return {"error": f"결과가 아직 없습니다 (status={task['status']})"}
    r = task["result"]
    fin = r.get("financial", {})

    if section == "summary":
        ba = fin.get("baseline_assumptions", {})
        return {
            "summary": r.get("summary"),
            "annual_elec_bill": fin.get("annual_elec_bill"),
            "annual_heat_bill": fin.get("annual_heat_bill"),
            "capital_cost": fin.get("capital_cost"),
            "npv": fin.get("npv"),
            "irr": fin.get("irr"),
            "savings_pct_vs_baseline": ba.get("savings_pct"),
            "baseline_source": ba.get("source"),
            "heat_source": fin.get("heat_source"),
        }
    if section == "monthly":
        return {"unit": "kWh/㎡·월", "monthly": r.get("monthly")}
    if section == "financial":
        return {
            "capital_cost": fin.get("capital_cost"),
            "cost_details": fin.get("cost_details"),
            "annual_elec_bill": fin.get("annual_elec_bill"),
            "annual_heat_bill": fin.get("annual_heat_bill"),
            "npv": fin.get("npv"),
            "irr": fin.get("irr"),
            "lcc_parameters": fin.get("lcc_parameters"),
            "mapped_window_name": fin.get("mapped_window_name"),
            "estimate_notes": fin.get("estimate_notes"),
            "cost_warnings": fin.get("cost_warnings"),
        }
    if section == "recommendations":
        return {"recommendations": fin.get("recommendations", [])}
    if section == "baseline":
        base = r.get("baseline")
        if not base:
            return {"error": "이 실행에는 개선 전(baseline) 비교가 없습니다"}
        return {
            "before": {
                "consume_per_m2": (base.get("summary") or {}).get("consume_per_m2"),
                "annual_elec_bill": base.get("annual_elec_bill"),
                "annual_heat_bill": base.get("annual_heat_bill"),
            },
            "after": {
                "consume_per_m2": (r.get("summary") or {}).get("consume_per_m2"),
                "annual_elec_bill": fin.get("annual_elec_bill"),
                "annual_heat_bill": fin.get("annual_heat_bill"),
            },
        }
    return {"error": f"알 수 없는 section: {section}",
            "sections": ["summary", "monthly", "financial", "recommendations", "baseline"]}


async def _amain():
    # stdio MCP는 stdout이 JSON-RPC 프로토콜 채널이다. 파서/시뮬레이터의 print()와
    # EnergyPlus 출력 에코(sys.stdout.write)가 채널을 오염시키면 클라이언트가 죽는다.
    # → 프로토콜 스트림을 먼저 확보(stdio_server가 이 시점의 sys.stdout.buffer를 캡처)한 뒤
    #   sys.stdout을 stderr로 돌려 이후의 모든 텍스트 출력을 로그로 보낸다.
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        sys.stdout = sys.stderr
        srv = mcp._mcp_server
        await srv.run(read_stream, write_stream, srv.create_initialization_options())


if __name__ == "__main__":
    if "--http" in sys.argv:
        # HTTP 모드: Claude 커스텀 커넥터 등에 URL로 연결할 때 사용.
        # 접속 주소 → http://127.0.0.1:8765/mcp  (백엔드 FastAPI의 8000번과 분리)
        # 터널(trycloudflare 등) 뒤에서 서빙하면 Host가 외부 도메인이 되므로
        # SDK 기본 DNS 리바인딩 보호(localhost만 허용)를 끈다 — 터널 도메인이 매번 바뀜.
        # HTTP 모드는 stdout이 프로토콜 채널이 아니므로 print 오염 걱정 없음.
        from mcp.server.transport_security import TransportSecuritySettings

        mcp.settings.transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        )
        mcp.settings.host = "127.0.0.1"
        mcp.settings.port = 8765
        mcp.run(transport="streamable-http")
    else:
        import anyio

        anyio.run(_amain)
