"""현금흐름·NPV·IRR — **순수 함수**.

`cost_analyzer.calculate()` 안의 중첩 함수로 있던 것을 꺼냈다.
중첩 함수는 밖에서 시험할 수 없어서, 시험 파일이 알고리즘을 **복제**해 검사하고
있었다. 그러면 실제 구현이 깨져도 복제본 시험은 통과한다 — 시험이 아니라
별개 구현을 검증하는 셈이다.
"""
from typing import List, Optional, Sequence

# IRR 탐색 구간. 건물 리트로핏에서 -99% 미만이나 +500% 초과는 의미가 없다.
IRR_SEARCH_LOW = -0.99
IRR_SEARCH_HIGH = 5.0
IRR_TOLERANCE = 1e-5
IRR_MAX_ITER = 200


def npv(cash_flows: Sequence[float], discount_rate: float) -> float:
    """순현재가치. `cash_flows[0]` 은 0년차(초기 투자)로 할인하지 않는다."""
    return sum(cf / ((1 + discount_rate) ** t) for t, cf in enumerate(cash_flows))


def irr(cash_flows: Sequence[float],
        low: float = IRR_SEARCH_LOW, high: float = IRR_SEARCH_HIGH,
        max_iter: int = IRR_MAX_ITER) -> Optional[float]:
    """내부수익률. **해가 없으면 None.**

    ⚠️ 예전 구현은 부호 변화를 확인하지 않고 항상 숫자를 반환했다. 그래서
    절대 회수되지 않는 흐름(전부 음수)에는 탐색 하한 −0.99 를, 투자가 없는
    흐름(전부 양수)에는 상한 5.0 을 **진짜 IRR 처럼** 내보냈다 —
    화면에는 "-99%" 나 "500%" 로 표시된다.

    ⚠️ 부호가 여러 번 바뀌는 흐름(교체비로 중간에 음수가 되는 경우)은 IRR 이
    여러 개일 수 있다. 이분법은 그중 하나만 찾는다 — 값 하나로 투자 판단을
    하면 안 된다는 뜻이다.
    """
    if not cash_flows or not any(cash_flows):
        return None                      # 흐름이 없다 — IRR 이 정의되지 않는다

    npv_low, npv_high = npv(cash_flows, low), npv(cash_flows, high)
    # ⚠️ `> 0` 만 보면 양끝이 **둘 다 0** 인 경우(전부 0 인 흐름)가 통과해
    # 구간 중점을 IRR 처럼 내보낸다. 0 인 쪽을 근으로 인정하고, 부호가 같으면 없다.
    if npv_low == 0:
        return low
    if npv_high == 0:
        return high
    if npv_low * npv_high > 0:
        return None                      # 구간 양 끝의 부호가 같다 → 근이 없다

    rate = (low + high) / 2
    for _ in range(max_iter):
        rate = (low + high) / 2
        value = npv(cash_flows, rate)
        if abs(value) < IRR_TOLERANCE:
            return rate
        if (value > 0) == (npv_low > 0):
            low, npv_low = rate, value
        else:
            high = rate
    return rate


def simple_payback_years(cash_flows: Sequence[float]) -> Optional[float]:
    """단순 회수기간(할인 없음). 회수되지 않으면 None.

    누적이 0 을 넘는 해에서 선형 보간한다.
    """
    if not cash_flows:
        return None
    cumulative = cash_flows[0]
    if cumulative >= 0:
        return 0.0
    for year, flow in enumerate(cash_flows[1:], start=1):
        previous = cumulative
        cumulative += flow
        if cumulative >= 0:
            if flow == 0:
                return float(year)
            return year - 1 + (-previous / flow)
    return None


def cumulative_present_value(capital_cost: float, yearly_costs: Sequence[float],
                             discount_rate: float) -> List[float]:
    """연차별 누적 현재가치. `[0]` 은 1년차 누적(초기투자 + 1년 할인비용)이다.

    ⚠️ 인덱스가 연차보다 1 작다. `series[i]` 는 **(i+1)년차** 누적이다 —
    소비자가 헷갈리기 쉬운 지점이라 여기 적어둔다.
    """
    out: List[float] = []
    running = capital_cost
    for year, cost in enumerate(yearly_costs, start=1):
        running += cost / ((1 + discount_rate) ** year)
        out.append(running)
    return out


# ── 생애주기 가정 ──
# ⚠️ 예전에는 유지비·교체 주기가 **두 곳에 복제**돼 있었다(누적 LCC 곡선과 순절감
# 현금흐름). 한쪽만 고치면 차트와 NPV/IRR 이 서로 다른 가정에서 나온 값이 된다.
HVAC_MAINTENANCE_RATE = 0.02     # 설비 공사비 대비 연간 유지비
LED_MAINTENANCE_RATE = 0.01
HVAC_REPLACEMENT_YEARS = 15      # 전면 교체가 아니라 핵심기기 부분 교체
HVAC_REPLACEMENT_RATIO = 0.5
LED_REPLACEMENT_YEARS = 10
LED_REPLACEMENT_RATIO = 0.4


def maintenance_cost(hvac_cost: float, led_cost: float,
                     inflation_rate: float, year: int) -> float:
    """해당 연도의 유지보수비(명목)."""
    base = hvac_cost * HVAC_MAINTENANCE_RATE + led_cost * LED_MAINTENANCE_RATE
    return base * ((1 + inflation_rate) ** year)


def replacement_cost(hvac_cost: float, led_cost: float,
                     inflation_rate: float, year: int) -> float:
    """해당 연도의 교체비(명목). 주기가 아닌 해는 0."""
    total = 0.0
    if year > 0 and year % HVAC_REPLACEMENT_YEARS == 0:
        total += hvac_cost * HVAC_REPLACEMENT_RATIO * ((1 + inflation_rate) ** year)
    if year > 0 and year % LED_REPLACEMENT_YEARS == 0:
        total += led_cost * LED_REPLACEMENT_RATIO * ((1 + inflation_rate) ** year)
    return total


def build_savings_cash_flows(*, capital_cost: float, baseline_running_cost: float,
                             retrofit_running_cost: float, hvac_cost: float,
                             led_cost: float, years: int,
                             utility_inflation: float, inflation_rate: float) -> List[float]:
    """연차별 **순절감액** 현금흐름. `[0]` 은 −초기투자비.

    절감액 = 기존 건물 운영비 − (개선 후 운영비 + 유지보수 + 교체비)
    """
    flows = [-capital_cost]
    for year in range(1, years + 1):
        escalation = (1 + utility_inflation) ** year
        saved = baseline_running_cost * escalation - retrofit_running_cost * escalation
        cost = (maintenance_cost(hvac_cost, led_cost, inflation_rate, year)
                + replacement_cost(hvac_cost, led_cost, inflation_rate, year))
        flows.append(saved - cost)
    return flows


def build_lifecycle_costs(*, retrofit_running_cost: float, hvac_cost: float,
                          led_cost: float, years: int,
                          utility_inflation: float, inflation_rate: float) -> List[float]:
    """연차별 **총 소유비용**(명목). 누적 LCC 곡선용 — 순절감액이 아니다."""
    return [
        retrofit_running_cost * ((1 + utility_inflation) ** year)
        + maintenance_cost(hvac_cost, led_cost, inflation_rate, year)
        + replacement_cost(hvac_cost, led_cost, inflation_rate, year)
        for year in range(1, years + 1)
    ]
