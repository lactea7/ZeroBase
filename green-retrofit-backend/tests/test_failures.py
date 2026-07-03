# 실패 경로: 가짜 폴백 데이터 없이 명시적으로 실패해야 한다.
import pytest


def test_missing_csv_raises(analyzer, base_kwargs):
    with pytest.raises(RuntimeError, match="비용 분석 실패"):
        analyzer.calculate(**dict(base_kwargs, eplus_csv_path="/nonexistent/eplusout.csv"))


def test_fallback_data_removed(analyzer):
    assert not hasattr(analyzer, "_fallback_data")
