// utils/pdfReport.js - 결과 리포트 PDF 생성 (인쇄 최적화 A4 2페이지)
// 1페이지: 요약 / 2페이지: 섹션별 선택 사항·자재 상세
// 브라우저 인쇄(PDF 저장)를 사용 — 벡터 텍스트·한글 폰트·CSS 완전 재현, 외부 라이브러리 불필요
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
    <div class="kpi">
      <div class="kpi-label">${esc(labelTxt)}</div>
      <div class="kpi-value">${esc(value)}<span class="kpi-unit">${esc(unit)}</span></div>
      ${note ? `<div class="kpi-note">${esc(note)}</div>` : ''}
    </div>`;

  const row = (k, v) => `<div class="row"><div class="row-k">${esc(k)}</div><div class="row-v">${v}</div></div>`;

  const html = `<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>ZeroBase 리포트 — ${esc(projectData.name || '건물 분석')}</title>
<style>
  :root {
    --ink: #1D1712; --sub: #6B5D50; --parchment: #F3ECE1; --parchment-80: rgba(243,236,225,.8);
    --hair: #E3D9C8; --accent: #C2734A; --good: #3D7A5C;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { background: #fff; color: var(--ink);
    font-family: "Apple SD Gothic Neo", Pretendard, "Noto Sans KR", -apple-system, sans-serif;
    -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  @page { size: A4; margin: 0; }
  .sheet { width: 210mm; height: 297mm; padding: 16mm 15mm 12mm; page-break-after: always;
    display: flex; flex-direction: column; overflow: hidden; position: relative; }
  .sheet:last-child { page-break-after: auto; }

  /* ── 마스트헤드: 여백이 받침대 (헤드라인 위 64px 급 여백) ── */
  .mast { text-align: center; padding: 34px 0 30px; }
  .wordmark { font-size: 11px; font-weight: 800; letter-spacing: .34em; color: var(--accent);
    text-transform: uppercase; margin-bottom: 18px; }
  .mast h1 { font-size: 26px; font-weight: 800; letter-spacing: -.02em; line-height: 1.3; }
  .mast .meta { margin-top: 10px; font-size: 11px; color: var(--sub); font-weight: 600; }
  .mast .meta span + span::before { content: "·"; margin: 0 8px; color: var(--hair); }

  /* ── 히어로 수치 (단일 컬럼 센터 스택) ── */
  .hero { text-align: center; padding: 6px 0 30px; }
  .hero-label { font-size: 11px; font-weight: 800; letter-spacing: .12em; color: var(--sub); text-transform: uppercase; }
  .hero-value { font-size: 44px; font-weight: 800; letter-spacing: -.03em; margin-top: 6px; }
  .hero-value .u { font-size: 16px; font-weight: 700; color: var(--sub); margin-left: 6px; letter-spacing: 0; }
  .hero-sub { margin-top: 8px; font-size: 12px; color: var(--sub); font-weight: 600; }
  .hero-sub b { color: var(--good); }

  /* ── 유틸리티 카드 그리드 (3열, 거터 22px, 플랫) ── */
  .grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 22px; }
  .grid2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 22px; }
  .kpi { background: var(--parchment-80); border-radius: 10px; padding: 18px 18px 16px; text-align: center; }
  .kpi-label { font-size: 10px; font-weight: 800; letter-spacing: .1em; color: var(--sub); text-transform: uppercase; }
  .kpi-value { font-size: 23px; font-weight: 800; letter-spacing: -.02em; margin-top: 8px;
    font-variant-numeric: tabular-nums; }
  .kpi-unit { font-size: 11px; font-weight: 700; color: var(--sub); margin-left: 3px; }
  .kpi-note { margin-top: 5px; font-size: 10px; color: var(--sub); font-weight: 600; }

  /* ── 밴드(전/후 비교) : 2열 사이드-바이-사이드 타일 ── */
  .band { margin-top: 26px; background: var(--parchment); border-radius: 12px; padding: 20px 24px; }
  .band-title { font-size: 10.5px; font-weight: 800; letter-spacing: .12em; color: var(--sub);
    text-transform: uppercase; text-align: center; margin-bottom: 14px; }
  .ba { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 18px; }
  .ba-col { text-align: center; }
  .ba-k { font-size: 10px; font-weight: 800; color: var(--sub); letter-spacing: .08em; text-transform: uppercase; }
  .ba-v { font-size: 20px; font-weight: 800; margin-top: 5px; font-variant-numeric: tabular-nums; }
  .ba-arrow { font-size: 18px; color: var(--accent); font-weight: 800; }

  /* ── 섹션 (헤드라인 위 넉넉한 여백, 플랫·헤어라인) ── */
  .section { margin-top: 30px; }
  .section-h { display: flex; align-items: baseline; gap: 10px; padding-bottom: 8px;
    border-bottom: 1px solid var(--ink); margin-bottom: 12px; }
  .section-no { font-size: 10px; font-weight: 800; color: var(--accent); letter-spacing: .1em; }
  .section-h h2 { font-size: 14px; font-weight: 800; letter-spacing: -.01em; }
  .section-h .cost { margin-left: auto; font-size: 12px; font-weight: 800; color: var(--accent);
    font-variant-numeric: tabular-nums; }
  .row { display: grid; grid-template-columns: 34% 1fr; padding: 6px 0; border-bottom: 1px solid var(--hair);
    font-size: 11px; }
  .row:last-child { border-bottom: none; }
  .row-k { color: var(--sub); font-weight: 700; }
  .row-v { font-weight: 600; }

  table { width: 100%; border-collapse: collapse; font-size: 10.5px; margin-top: 2px; }
  th { text-align: left; font-size: 9px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase;
    color: var(--sub); padding: 5px 8px; border-bottom: 1px solid var(--ink); }
  td { padding: 6px 8px; border-bottom: 1px solid var(--hair); font-weight: 600; vertical-align: top; }
  tr:last-child td { border-bottom: none; }
  td.n { font-variant-numeric: tabular-nums; white-space: nowrap; }
  .tag { display: inline-block; font-size: 8.5px; font-weight: 800; padding: 1px 7px; border-radius: 99px;
    background: var(--parchment); color: var(--sub); }
  .tag.user { background: #E3EFE8; color: var(--good); }

  .note-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 24px; font-size: 9.5px; color: var(--sub); }
  .note-grid b { color: var(--ink); font-weight: 800; }
  .note-item { padding: 4px 0; line-height: 1.55; }
  .warn-item { font-size: 9.5px; color: #8A5A2B; padding: 3px 0; line-height: 1.5; }

  /* ── 밀도 높은 푸터 ── */
  .foot { margin-top: auto; padding-top: 12px; border-top: 1px solid var(--hair);
    display: flex; justify-content: space-between; gap: 16px;
    font-size: 8.5px; color: var(--sub); line-height: 1.6; }
  .pageno { font-weight: 800; white-space: nowrap; }
</style></head><body>

<!-- ═══════════ PAGE 1 · 요약 ═══════════ -->
<section class="sheet">
  <div class="mast">
    <div class="wordmark">ZeroBase</div>
    <h1>${esc(projectData.name || '건물 그린 리트로핏')} 분석 리포트</h1>
    <div class="meta">
      <span>${esc(regionName || projectData.location || '')}</span>
      <span>존 ${zones.length || (eq?.zones?.length ?? '—')}개</span>
      <span>난방 열원 · ${esc(heatLabel)}</span>
      <span>${today}</span>
    </div>
  </div>

  <div class="hero">
    <div class="hero-label">연간 에너지 소요량</div>
    <div class="hero-value">${num(sum.consume_per_m2)}<span class="u">kWh/㎡·년</span></div>
    <div class="hero-sub">
      기준 건물(${esc(baselineLabel)}) 대비 절감률 <b>${esc(savingsPct)}%</b>
      · 연간 절감액 <b>${won(lccAnalysis.annualSavings)}</b>
    </div>
  </div>

  <div class="grid3">
    ${kpi('1차에너지 소요량', num(sum.primary_per_m2), 'kWh/㎡·년')}
    ${kpi('CO2 배출량', num(sum.co2_per_m2, 2), 'kg/㎡·년')}
    ${kpi('에너지 자립률', `${zebRate}`, '%', `ZEB ${zebGrade}`)}
    ${kpi('총 공사비', won(fin.capital_cost), '')}
    ${kpi('연간 에너지 요금', won(fin.total_energy_bill ?? ((fin.annual_elec_bill || 0) + (fin.annual_heat_bill || 0))), '', `전기 ${won(fin.annual_elec_bill)} · 열 ${won(fin.annual_heat_bill)}`)}
    ${kpi('투자 회수기간', lccAnalysis.paybackYears ? num(lccAnalysis.paybackYears) : '—', '년', `NPV ${won(fin.npv)} · IRR ${num(fin.irr)}%`)}
  </div>

  ${base ? `
  <div class="band">
    <div class="band-title">개선 전 · 후 비교 — 동일 물리 엔진(EnergyPlus) 산출</div>
    <div class="ba">
      <div class="ba-col">
        <div class="ba-k">개선 전 (원본 건물)</div>
        <div class="ba-v">${num(base.summary?.consume_per_m2)} kWh/㎡</div>
        <div class="ba-k" style="margin-top:8px">연간 운영비 ${won((base.annual_elec_bill || 0) + (base.annual_heat_bill || 0))}</div>
      </div>
      <div class="ba-arrow">→</div>
      <div class="ba-col">
        <div class="ba-k">개선 후 (리모델링안)</div>
        <div class="ba-v">${num(sum.consume_per_m2)} kWh/㎡</div>
        <div class="ba-k" style="margin-top:8px">연간 운영비 ${won((fin.annual_elec_bill || 0) + (fin.annual_heat_bill || 0))}</div>
      </div>
    </div>
  </div>` : ''}

  ${recs.length ? `
  <div class="band" style="background:#EDF3EE">
    <div class="band-title" style="color:var(--good)">추가 절감 대안 ${recs.length}건 — 모두 적용 시 −${won(recTotal)}</div>
    <div class="note-grid">
      ${recs.map((r) => `<div class="note-item"><b>${esc(r.title)}</b> — 절감 ${won(r.saved_cost)}</div>`).join('')}
    </div>
  </div>` : ''}

  <div class="foot">
    <div>
      기준 건물: ${esc(baselineLabel)} · 시뮬레이션: EnergyPlus 25.2 연간 8,760시간 · 기상: 한국 TMYx(2009–2023)
      · 요금: KEPCO(2026)·KDHC(2024) · 단가: 친환경건설자재 DB 중앙값 — 결과는 추정치이며 실제 견적·요금과 차이가 날 수 있습니다.
    </div>
    <div class="pageno">1 / 2</div>
  </div>
</section>

<!-- ═══════════ PAGE 2 · 섹션별 선택 사항 · 자재 상세 ═══════════ -->
<section class="sheet">
  <div class="mast" style="padding:10px 0 6px">
    <div class="wordmark">ZeroBase</div>
    <h1 style="font-size:19px">적용 사양 및 자재 상세</h1>
  </div>

  <div class="section">
    <div class="section-h"><span class="section-no">01</span><h2>프로젝트 설정</h2></div>
    <div class="grid2" style="gap:0 40px">
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
        <td><span class="tag ${g.source === 'user' ? 'user' : ''}">${g.source === 'user' ? '입력값' : '자동'}</span></td>
      </tr>`).join('')}
      ${eqGroups.length > 6 ? `<tr><td colspan="4" style="color:var(--sub)">…외 구성 ${eqGroups.length - 6}종</td></tr>` : ''}
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

  <div class="section">
    <div class="section-h"><span class="section-no">06</span><h2>산정 가정 및 유의사항</h2></div>
    <div class="note-grid">
      ${notes.map((n) => `<div class="note-item"><b>${esc(n.label)}</b> — ${esc(n.note)}</div>`).join('')}
    </div>
    ${warns.length ? `<div style="margin-top:8px">${warns.map((w) => `<div class="warn-item">⚠ ${esc(w)}</div>`).join('')}</div>` : ''}
  </div>

  <div class="foot">
    <div>ZeroBase — gbXML 기반 그린 리트로핏 시뮬레이션 · 생성일 ${today} · 본 리포트의 수치는 물리 시뮬레이션 기반 추정치입니다.</div>
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
