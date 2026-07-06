// utils/pdfReport.js - 결과 리포트 PDF 생성 (인쇄 최적화 A4 2페이지)
// 1페이지: 요약 / 2페이지: 섹션별 선택 사항·자재 상세
// 디자인: DESIGN-apple.md — 화이트/파치먼트(#f5f5f7)/니어블랙 타일 교차, 단일 Action Blue(#0066cc),
// SF Pro 네거티브 트래킹 600 헤드라인, 그림자 0(표면색 전환이 구분선), 밀도 높은 파치먼트 푸터
import { COOLING_GRADES, HEATING_AGES, FUEL_TYPES } from '../data/hvac';
import { formatWon } from './format';

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const num = (v, d = 1) => (Number.isFinite(Number(v)) ? Number(v).toFixed(d) : '—');
const won = (v) => (v || v === 0 ? formatWon(v) : '—');
const label = (list, id, fallback = '—') => list.find((x) => String(x.id) === String(id))?.name || fallback;

// 존별 설비 내역을 '고유 구성'으로 그룹핑 (82존을 표로 나열하지 않기 위함)
function groupEquipment(zonesLog = []) {
  const map = new Map();
  for (const z of zonesLog) {
    const key = `${z.heating}|${z.cooling}|${z.source}`;
    if (!map.has(key)) map.set(key, { ...z, count: 0, examples: [] });
    const g = map.get(key);
    g.count += 1;
    if (g.examples.length < 3) g.examples.push(z.zone);
  }
  return [...map.values()].sort((a, b) => b.count - a.count);
}

// 단열 상세를 등급별로 집계
function groupInsulation(details = []) {
  const map = new Map();
  for (const d of details) {
    if (!map.has(d.tier)) map.set(d.tier, { tier: d.tier, area: 0, cost: 0, price: d.price, count: 0 });
    const g = map.get(d.tier);
    g.area += d.area || 0;
    g.cost += d.cost || 0;
    g.count += 1;
  }
  return [...map.values()].sort((a, b) => b.cost - a.cost);
}

export function openPdfReport({ res, projectData = {}, lccAnalysis = {}, zones = [], regionName }) {
  const fin = res?.financial || {};
  const sum = res?.summary || {};
  const ba = fin.baseline_assumptions || {};
  const base = res?.baseline;
  const eq = res?.hvacEquipment;
  const recs = fin.recommendations || [];
  const notes = fin.estimate_notes || [];
  const warns = fin.cost_warnings || [];
  const cd = fin.cost_details || {};
  const lcc = fin.lcc_parameters || {};
  const today = new Date().toISOString().slice(0, 10);

  const zebRate = Math.round(Number(sum.independence) || 0);
  const zebGrade = zebRate >= 100 ? '1등급' : zebRate >= 80 ? '2등급' : zebRate >= 60 ? '3등급'
    : zebRate >= 40 ? '4등급' : zebRate >= 20 ? '5등급' : '등급 외';

  const baselineLabel = ba.source === 'actual_bill' ? '실측 요금 입력'
    : ba.source === 'actual_usage' ? '실측 사용량 입력'
    : ba.source === 'simulated' ? '개선 전 건물 물리 시뮬레이션' : '추정 (개선 후 × 1.6)';

  const heatLabel = fin.heat_source || label(FUEL_TYPES, projectData.heatSource, '지역난방');
  const coolGrade = label(COOLING_GRADES, projectData.hvacEquipment?.coolingGrade || 'grade3');
  const heatAge = label(HEATING_AGES, projectData.hvacEquipment?.heatingAge || 'new');

  const eqGroups = groupEquipment(eq?.zones);
  const insGroups = groupInsulation(fin.insulation_details);
  const recTotal = recs.reduce((a, r) => a + (r.saved_cost || 0), 0);
  const savingsPct = ba.savings_pct ?? '—';

  const kpi = (labelTxt, value, unit, note = '') => `
    <div class="card">
      <div class="card-label">${esc(labelTxt)}</div>
      <div class="card-value">${esc(value)}<span class="card-unit">${esc(unit)}</span></div>
      ${note ? `<div class="card-note">${esc(note)}</div>` : ''}
    </div>`;

  const row = (k, v) => `<div class="row"><div class="row-k">${esc(k)}</div><div class="row-v">${v}</div></div>`;

  const html = `<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>ZeroBase 리포트 — ${esc(projectData.name || '건물 분석')}</title>
<style>
  /* ── DESIGN-apple.md 토큰 ── */
  :root {
    --primary: #0066cc;           /* Action Blue — 유일한 액센트 */
    --primary-on-dark: #2997ff;   /* Sky Link Blue — 다크 타일 전용 */
    --ink: #1d1d1f;
    --ink-80: #333333;
    --ink-48: #7a7a7a;
    --body-muted: #cccccc;        /* 다크 타일 보조 카피 */
    --divider-soft: #f0f0f0;
    --hairline: #e0e0e0;
    --canvas: #ffffff;
    --parchment: #f5f5f7;
    --tile-dark: #272729;
    --black: #000000;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { background: #fff; color: var(--ink);
    /* SF Pro Display/Text — macOS에서 system-ui가 실제 SF Pro로 해석됨 */
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text",
      "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
    -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  @page { size: A4; margin: 0; }
  /* 297mm 정확값은 인쇄 px 반올림으로 하단이 잘림 → 296mm로 안전 확보 */
  .sheet { width: 210mm; height: 296mm; page-break-after: always;
    display: flex; flex-direction: column; overflow: hidden; background: var(--canvas); }
  .sheet:last-child { page-break-after: auto; }

  /* ── global-nav: 순수 블랙은 나브에만 (spec: surface-black) ── */
  .gnav { background: var(--black); color: #fff; height: 34px; padding: 0 15mm;
    display: flex; align-items: center; justify-content: space-between; }
  .gnav .brand { font-size: 11px; font-weight: 600; letter-spacing: -0.01em; }
  .gnav .meta { font-size: 9px; font-weight: 400; letter-spacing: -0.01em; color: rgba(255,255,255,.8); }
  .gnav .meta span + span::before { content: "·"; margin: 0 7px; color: rgba(255,255,255,.35); }

  /* ── sub-nav: 파치먼트 스트립 (frosted 대응 — 인쇄에선 불투명) ── */
  .subnav { background: var(--parchment); height: 30px; padding: 0 15mm;
    display: flex; align-items: center; justify-content: space-between;
    border-bottom: 1px solid rgba(0,0,0,.08); }
  .subnav .cat { font-size: 12px; font-weight: 600; letter-spacing: 0.011em; }
  .subnav .aux { font-size: 9px; color: var(--ink-48); letter-spacing: -0.01em; }

  /* ── 히어로 타일 (화이트, 센터 스택 — 헤드라인 위 64px급 여백) ── */
  .hero { text-align: center; padding: 46px 15mm 40px; background: var(--canvas); }
  .hero .eyebrow { font-size: 12.5px; font-weight: 600; letter-spacing: 0.011em; color: var(--ink); }
  .hero .display { font-size: 38px; font-weight: 600; line-height: 1.07; letter-spacing: -0.005em;
    margin-top: 10px; font-variant-numeric: tabular-nums; }
  .hero .display .u { font-size: 14px; font-weight: 400; color: var(--ink-48); margin-left: 6px; letter-spacing: 0; }
  .hero .lead { margin-top: 10px; font-size: 12px; font-weight: 400; line-height: 1.47;
    letter-spacing: -0.022em; color: var(--ink-80); }
  /* 두 개의 필 CTA 문법: 채운 블루 / 고스트 블루 */
  .hero .pills { margin-top: 16px; display: flex; justify-content: center; gap: 10px; }
  .pill { display: inline-block; border-radius: 9999px; padding: 6px 15px;
    font-size: 10.5px; font-weight: 400; letter-spacing: -0.01em; }
  .pill.fill { background: var(--primary); color: #fff; }
  .pill.ghost { color: var(--primary); border: 1px solid var(--primary); }

  /* ── 유틸리티 카드 그리드: 파치먼트 캔버스 위 화이트 카드(18px·헤어라인·그림자 없음) ── */
  .util { background: var(--parchment); padding: 22px 15mm 26px; }
  .grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }
  .card { background: var(--canvas); border: 1px solid var(--hairline); border-radius: 18px;
    padding: 16px 14px 14px; text-align: center; }
  .card-label { font-size: 9px; font-weight: 600; letter-spacing: -0.016em; color: var(--ink-48); }
  .card-value { font-size: 17px; font-weight: 600; letter-spacing: -0.022em; margin-top: 7px;
    font-variant-numeric: tabular-nums; }
  .card-unit { font-size: 9.5px; font-weight: 400; color: var(--ink-48); margin-left: 3px; }
  .card-note { margin-top: 5px; font-size: 8.5px; font-weight: 400; color: var(--ink-48);
    letter-spacing: -0.016em; }

  /* ── 다크 타일: 표면색 전환이 곧 구분선 (rounded.none, 풀블리드) ── */
  .dark-tile { background: var(--tile-dark); color: #fff; padding: 26px 15mm; text-align: center; }
  .dark-tile .t { font-size: 13px; font-weight: 600; letter-spacing: 0.011em; }
  .dark-tile .s { margin-top: 4px; font-size: 9px; font-weight: 400; color: var(--body-muted);
    letter-spacing: -0.016em; }
  .ba { margin-top: 16px; display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 16px; }
  .ba-k { font-size: 9px; font-weight: 400; color: var(--body-muted); letter-spacing: -0.016em; }
  .ba-v { font-size: 21px; font-weight: 600; letter-spacing: -0.01em; margin-top: 5px;
    font-variant-numeric: tabular-nums; }
  .ba-cost { margin-top: 7px; font-size: 9.5px; font-weight: 400; color: var(--primary-on-dark); }
  .ba-arrow { font-size: 17px; color: var(--primary-on-dark); font-weight: 400; }

  /* ── 추천 타일 (화이트) — 인라인 블루 텍스트 링크 문법 ── */
  .recs { background: var(--canvas); padding: 22px 15mm; text-align: center; }
  .recs .t { font-size: 13px; font-weight: 600; letter-spacing: 0.011em; }
  .recs .list { margin-top: 10px; display: grid; grid-template-columns: 1fr 1fr; gap: 3px 26px;
    text-align: left; }
  .recs .item { font-size: 9.5px; font-weight: 400; letter-spacing: -0.016em; line-height: 1.47;
    padding: 3px 0; color: var(--ink-80); }
  .recs .item b { font-weight: 600; color: var(--ink); }
  .recs .item .amt { color: var(--primary); }

  /* ── 섹션 (2페이지, 화이트 캔버스·헤어라인 룰) ── */
  .content { padding: 4px 15mm 0; }
  .section { margin-top: 22px; }
  .section-h { display: flex; align-items: baseline; gap: 9px; padding-bottom: 7px;
    border-bottom: 1px solid var(--hairline); margin-bottom: 9px; }
  .section-no { font-size: 9px; font-weight: 600; color: var(--ink-48); letter-spacing: -0.016em;
    font-variant-numeric: tabular-nums; }
  .section-h h2 { font-size: 14px; font-weight: 600; letter-spacing: -0.011em; }
  .section-h .cost { margin-left: auto; font-size: 11.5px; font-weight: 600; color: var(--primary);
    font-variant-numeric: tabular-nums; letter-spacing: -0.022em; }
  .row { display: grid; grid-template-columns: 34% 1fr; padding: 5.5px 0;
    border-bottom: 1px solid var(--divider-soft); font-size: 10.5px; letter-spacing: -0.022em; }
  .row:last-child { border-bottom: none; }
  .row-k { color: var(--ink-48); font-weight: 400; }
  .row-v { font-weight: 600; color: var(--ink); }
  .grid2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0 40px; }

  table { width: 100%; border-collapse: collapse; font-size: 10px; margin-top: 2px;
    letter-spacing: -0.016em; }
  th { text-align: left; font-size: 8.5px; font-weight: 600; letter-spacing: -0.016em;
    color: var(--ink-48); padding: 4px 8px; border-bottom: 1px solid var(--hairline); }
  td { padding: 5.5px 8px; border-bottom: 1px solid var(--divider-soft); font-weight: 400;
    vertical-align: top; color: var(--ink); }
  tr:last-child td { border-bottom: none; }
  td.n { font-variant-numeric: tabular-nums; white-space: nowrap; }
  /* configurator-option-chip 문법: 화이트+헤어라인 필 / 선택(입력값) = 블루 보더 */
  .chip { display: inline-block; font-size: 8px; font-weight: 400; padding: 2px 9px;
    border-radius: 9999px; background: var(--canvas); border: 1px solid var(--hairline);
    color: var(--ink); }
  .chip.user { border: 1.5px solid var(--primary); color: var(--primary); font-weight: 600; }

  /* ── 가정·유의 파치먼트 타일 ── */
  .assump { background: var(--parchment); padding: 18px 15mm 16px; margin-top: 22px; }
  .assump .t { font-size: 12px; font-weight: 600; letter-spacing: -0.011em; margin-bottom: 9px; }
  .note-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 3px 26px; font-size: 8.8px;
    color: var(--ink-80); letter-spacing: -0.016em; }
  .note-grid b { color: var(--ink); font-weight: 600; }
  .note-item { padding: 3px 0; line-height: 1.47; }
  .warn-item { font-size: 8.8px; color: var(--ink-80); padding: 2.5px 0; line-height: 1.47; }
  .warn-item::before { content: "◦ "; color: var(--ink-48); }

  /* ── 밀도 높은 파치먼트 푸터 (fine-print 문법) ── */
  .foot { margin-top: auto; background: var(--parchment); padding: 12px 15mm 13px;
    display: flex; justify-content: space-between; align-items: flex-start; gap: 16px;
    font-size: 8px; color: var(--ink-48); line-height: 1.5; letter-spacing: -0.01em; }
  .foot b { color: var(--ink-80); font-weight: 600; }
  .pageno { font-weight: 600; white-space: nowrap; color: var(--ink-80);
    font-variant-numeric: tabular-nums; }
</style></head><body>

<!-- ═══════════ PAGE 1 · 요약 ═══════════ -->
<section class="sheet">
  <div class="gnav">
    <div class="brand">ZeroBase</div>
    <div class="meta">
      <span>${esc(projectData.name || '건물 그린 리트로핏')}</span>
      <span>${esc(regionName || projectData.location || '')}</span>
      <span>존 ${zones.length || (eq?.zones?.length ?? '—')}개</span>
      <span>${today}</span>
    </div>
  </div>

  <div class="hero">
    <div class="eyebrow">연간 에너지 소요량</div>
    <div class="display">${num(sum.consume_per_m2)}<span class="u">kWh/㎡·년</span></div>
    <div class="lead">기준 건물(${esc(baselineLabel)}) 대비 — 난방 열원 ${esc(heatLabel)}</div>
    <div class="pills">
      <span class="pill fill">절감률 ${esc(savingsPct)}%</span>
      <span class="pill ghost">연간 절감액 ${won(lccAnalysis.annualSavings)}</span>
    </div>
  </div>

  <div class="util">
    <div class="grid3">
      ${kpi('1차에너지 소요량', num(sum.primary_per_m2), 'kWh/㎡·년')}
      ${kpi('CO2 배출량', num(sum.co2_per_m2, 2), 'kg/㎡·년')}
      ${kpi('에너지 자립률', `${zebRate}`, '%', `ZEB ${zebGrade}`)}
      ${kpi('총 공사비', won(fin.capital_cost), '')}
      ${kpi('연간 에너지 요금', won(fin.total_energy_bill ?? ((fin.annual_elec_bill || 0) + (fin.annual_heat_bill || 0))), '', `전기 ${won(fin.annual_elec_bill)} · 열 ${won(fin.annual_heat_bill)}`)}
      ${kpi('투자 회수기간', lccAnalysis.paybackYears ? num(lccAnalysis.paybackYears) : '—', '년', `NPV ${won(fin.npv)} · IRR ${num(fin.irr)}%`)}
    </div>
  </div>

  ${base ? `
  <div class="dark-tile">
    <div class="t">개선 전 · 후 비교</div>
    <div class="s">동일 물리 엔진(EnergyPlus) 산출</div>
    <div class="ba">
      <div>
        <div class="ba-k">개선 전 (원본 건물)</div>
        <div class="ba-v">${num(base.summary?.consume_per_m2)} kWh/㎡</div>
        <div class="ba-cost">연간 운영비 ${won((base.annual_elec_bill || 0) + (base.annual_heat_bill || 0))}</div>
      </div>
      <div class="ba-arrow">→</div>
      <div>
        <div class="ba-k">개선 후 (리모델링안)</div>
        <div class="ba-v">${num(sum.consume_per_m2)} kWh/㎡</div>
        <div class="ba-cost">연간 운영비 ${won((fin.annual_elec_bill || 0) + (fin.annual_heat_bill || 0))}</div>
      </div>
    </div>
  </div>` : ''}

  ${recs.length ? `
  <div class="recs">
    <div class="t">추가 절감 대안 ${recs.length}건 — 모두 적용 시 −${won(recTotal)}</div>
    <div class="list">
      ${recs.map((r) => `<div class="item"><b>${esc(r.title)}</b> — 절감 <span class="amt">${won(r.saved_cost)}</span></div>`).join('')}
    </div>
  </div>` : ''}

  <div class="foot">
    <div>
      <b>기준 건물</b> ${esc(baselineLabel)} · <b>시뮬레이션</b> EnergyPlus 25.2 연간 8,760시간 ·
      <b>기상</b> 한국 TMYx(2009–2023) · <b>요금</b> KEPCO(2026)·KDHC(2024) ·
      <b>단가</b> 친환경건설자재 DB 중앙값 — 결과는 추정치이며 실제 견적·요금과 차이가 날 수 있습니다.
    </div>
    <div class="pageno">1 / 2</div>
  </div>
</section>

<!-- ═══════════ PAGE 2 · 섹션별 선택 사항 · 자재 상세 ═══════════ -->
<section class="sheet">
  <div class="gnav">
    <div class="brand">ZeroBase</div>
    <div class="meta"><span>${esc(projectData.name || '건물 그린 리트로핏')}</span><span>${today}</span></div>
  </div>
  <div class="subnav">
    <div class="cat">적용 사양 및 자재 상세</div>
    <div class="aux">${esc(regionName || projectData.location || '')}</div>
  </div>

  <div class="content">
    <div class="section">
      <div class="section-h"><span class="section-no">01</span><h2>프로젝트 설정</h2></div>
      <div class="grid2">
        <div>
          ${row('지역 (기상데이터)', esc(regionName || projectData.location || '—'))}
          ${row('난방 열원', esc(heatLabel))}
          ${row('지열 히트펌프', projectData.geothermalApplied ? '적용 (COP 5.0/4.5)' : '미적용')}
          ${row('태양광(PV)', projectData.pvCapacity ? `${esc(projectData.pvCapacity)} kW (연 ${(projectData.pvCapacity * 1300).toLocaleString()} kWh 자가소비)` : '미설치')}
        </div>
        <div>
          ${row('목표 예산', projectData.targetBudget ? `${Number(projectData.targetBudget).toLocaleString()} 만원` : '미설정')}
          ${row('LCC 분석 기간', `${lcc.lifecycle_years ?? 20}년`)}
          ${row('할인율 / 물가 / 요금상승', `${num(lcc.discount_rate)}% / ${num(lcc.inflation_rate)}% / ${num(lcc.utility_inflation)}%`)}
          ${row('기준 건물 산정', esc(baselineLabel))}
        </div>
      </div>
    </div>

    <div class="section">
      <div class="section-h"><span class="section-no">02</span><h2>냉난방 설비</h2>
        <span class="cost">${won(cd.hvac)}</span></div>
      ${row('냉방기 등급·연식 (건물 기본)', esc(coolGrade))}
      ${row('난방기 연식 (건물 기본)', esc(heatAge))}
      ${eqGroups.length ? `
      <table>
        <tr><th>구성 (난방 / 냉방)</th><th style="text-align:right">존 수</th><th>적용 예</th><th>출처</th></tr>
        ${eqGroups.slice(0, 6).map((g) => `
        <tr>
          <td>${esc(g.heating)}<br>${esc(g.cooling)}</td>
          <td class="n" style="text-align:right">${g.count}</td>
          <td>${esc(g.examples.join(', '))}${g.count > g.examples.length ? ' 외' : ''}</td>
          <td><span class="chip ${g.source === 'user' ? 'user' : ''}">${g.source === 'user' ? '입력값' : '자동'}</span></td>
        </tr>`).join('')}
        ${eqGroups.length > 6 ? `<tr><td colspan="4" style="color:var(--ink-48)">…외 구성 ${eqGroups.length - 6}종</td></tr>` : ''}
      </table>` : ''}
    </div>

    <div class="section">
      <div class="section-h"><span class="section-no">03</span><h2>창호</h2>
        <span class="cost">${won(cd.window)}</span></div>
      ${row('적용 등급 (U값 기반 매칭)', esc(fin.mapped_window_name || '—'))}
      ${row('산정 방식', '창 면적가중 실측 U/SHGC → 친환경건설자재 DB 창세트 중앙값 단가')}
    </div>

    <div class="section">
      <div class="section-h"><span class="section-no">04</span><h2>단열재</h2>
        <span class="cost">${won(cd.insulation)}</span></div>
      ${insGroups.length ? `
      <table>
        <tr><th>등급</th><th style="text-align:right">시공 면적</th><th style="text-align:right">단가</th><th style="text-align:right">비용</th><th style="text-align:right">부위 수</th></tr>
        ${insGroups.map((g) => `
        <tr>
          <td>${esc(g.tier)}</td>
          <td class="n" style="text-align:right">${g.area.toFixed(1)} ㎡</td>
          <td class="n" style="text-align:right">₩${(g.price || 0).toLocaleString()}/㎡</td>
          <td class="n" style="text-align:right">${won(g.cost)}</td>
          <td class="n" style="text-align:right">${g.count}</td>
        </tr>`).join('')}
      </table>` : row('산정 방식', '단열층 미검출 — 벽면적 × DB 폴백 단가 적용')}
    </div>

    <div class="section">
      <div class="section-h"><span class="section-no">05</span><h2>LED 조명</h2>
        <span class="cost">${won(cd.led)}</span></div>
      ${row('산정 방식', '거주면적 10㎡당 등기구 1개 환산 × 개당 중앙값 단가 (비거주 구역 30% 반영)')}
    </div>
  </div>

  <div class="assump">
    <div class="t">산정 가정 및 유의사항</div>
    <div class="note-grid">
      ${notes.map((n) => `<div class="note-item"><b>${esc(n.label)}</b> — ${esc(n.note)}</div>`).join('')}
    </div>
    ${warns.length ? `<div style="margin-top:7px">${warns.map((w) => `<div class="warn-item">${esc(w)}</div>`).join('')}</div>` : ''}
  </div>

  <div class="foot">
    <div><b>ZeroBase</b> — gbXML 기반 그린 리트로핏 시뮬레이션 · 생성일 ${today} · 본 리포트의 수치는 물리 시뮬레이션 기반 추정치입니다.</div>
    <div class="pageno">2 / 2</div>
  </div>
</section>

<script>
  // 렌더 완료 후 인쇄 다이얼로그 자동 호출 (PDF로 저장)
  window.addEventListener('load', () => setTimeout(() => window.print(), 400));
</script>
</body></html>`;

  const win = window.open('', '_blank');
  if (!win) {
    alert('팝업이 차단되어 리포트를 열 수 없습니다. 팝업을 허용해 주세요.');
    return;
  }
  win.document.write(html);
  win.document.close();
}
