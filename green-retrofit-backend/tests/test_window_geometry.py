# 창 형상 생성 규칙: 실측 opening 보존 / 축소 스케일 / 확대·부재 시 합성 폴백
import pytest

from src.ep_simulator import build_window_geometries, calculate_surface_area

WALL = [[0, 0, 0], [10, 0, 0], [10, 0, 3], [0, 0, 3]]          # 30㎡ 남향 벽
OP1 = [[1, 0, 1], [4, 0, 1], [4, 0, 2], [1, 0, 2]]             # 3㎡ (좌측 창)
OP2 = [[6, 0, 1], [9, 0, 1], [9, 0, 2], [6, 0, 2]]             # 3㎡ (우측 창)


def _surf(wwr, openings=None):
    return {"wwr": wwr, "openings": openings or []}


def test_real_openings_preserved_when_wwr_unchanged():
    """WWR 미수정(=파싱값 int(20%)) → 실좌표 그대로, 창 2개 유지."""
    wins = build_window_geometries(_surf(20, [{"type": "Window", "vertices": OP1},
                                              {"type": "Window", "vertices": OP2}]), WALL)
    assert len(wins) == 2
    assert wins[0] == OP1 and wins[1] == OP2


def test_openings_scaled_down_when_wwr_reduced():
    """WWR 20%→10% 축소 → 각 창이 중심 축소, 총면적 비율 유지."""
    wins = build_window_geometries(_surf(10, [{"type": "Window", "vertices": OP1},
                                              {"type": "Window", "vertices": OP2}]), WALL)
    assert len(wins) == 2
    total = sum(calculate_surface_area(w) for w in wins)
    assert total == pytest.approx(30 * 0.10, rel=0.02)   # 벽 30㎡의 10%
    # 중심 보존 (좌측 창은 여전히 좌측에)
    cx = sum(v[0] for v in wins[0]) / 4
    assert cx == pytest.approx(2.5, abs=0.01)


def test_fallback_to_synthetic_when_wwr_increased():
    """WWR 확대(20%→40%) → 실형상 확대는 벽 이탈 위험 → 합성 창 1개 폴백."""
    wins = build_window_geometries(_surf(40, [{"type": "Window", "vertices": OP1},
                                              {"type": "Window", "vertices": OP2}]), WALL)
    assert len(wins) == 1
    assert calculate_surface_area(wins[0]) == pytest.approx(30 * 0.40, rel=0.02)


def test_fallback_when_no_openings():
    wins = build_window_geometries(_surf(25), WALL)
    assert len(wins) == 1
    assert calculate_surface_area(wins[0]) == pytest.approx(30 * 0.25, rel=0.02)


def test_air_openings_excluded():
    """Air(개방경계)는 창이 아님 — 합성 폴백으로 처리."""
    wins = build_window_geometries(_surf(20, [{"type": "Air", "vertices": OP1}]), WALL)
    assert len(wins) == 1                      # 합성 1개
    assert calculate_surface_area(wins[0]) == pytest.approx(30 * 0.20, rel=0.02)


def test_no_window_when_wwr_zero():
    assert build_window_geometries(_surf(0, [{"type": "Window", "vertices": OP1}]), WALL) == []
