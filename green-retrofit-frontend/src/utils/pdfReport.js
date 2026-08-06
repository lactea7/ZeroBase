// utils/pdfReport.js - 결과 리포트 PDF 생성 (인쇄 최적화 A4 2페이지)
// 1페이지: 요약 + 월별 에너지 그래프 / 2페이지: 섹션별 선택 사항·자재 상세
// 디자인: 에디토리얼 리포트 스타일 — 화이트 캔버스, 잉크 룰(2px)로 위계 구분,
// 단일 에메랄드 액센트, 업퍼케이스 마이크로 라벨, 차트는 인라인 SVG(검증 팔레트)
import { COOLING_GRADES, HEATING_AGES, FUEL_TYPES } from '../data/hvac';
import { formatWon } from './format';

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const num = (v, d = 1) => (Number.isFinite(Number(v)) ? Number(v).toFixed(d) : '—');
const won = (v) => (v || v === 0 ? formatWon(v) : '—');
const label = (list, id, fallback = '—') => list.find((x) => String(x.id) === String(id))?.name || fallback;

// ── 차트 시리즈 정의 (dataviz 검증 팔레트: 흰 배경 대비·CVD 분리 통과) ──
const SERIES_HVAC = [
  { key: 'heating', name: '난방', color: '#e34948' },
  { key: 'cooling', name: '냉방', color: '#2a78d6' },
];
const SERIES_INTERNAL = [
  { key: 'lighting', name: '조명', color: '#c98500' },
  { key: 'equipment', name: '기기', color: '#4a3aa7' },
  { key: 'hotwater', name: '급탕', color: '#eb6834' },
];

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

// ── 인라인 SVG 그룹 막대차트 (Recharts 없이 인쇄용으로 직접 렌더) ──
function niceCeil(v) {
  if (!(v > 0)) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  const m = v / p;
  const s = m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10;
  return s * p;
}

function fmtTick(v) {
  if (v === 0) return '0';
  return v >= 10 ? String(Math.round(v)) : String(Math.round(v * 10) / 10);
}

// 데이터 끝(윗변)만 둥근 막대 — 베이스라인에 붙는 아랫변은 직각 유지
function barPath(x, y, w, h, r) {
  const rr = Math.min(r, w / 2, h);
  const x2 = x + w;
  return `M${x},${(y + h).toFixed(1)} L${x},${(y + rr).toFixed(1)} Q${x},${y.toFixed(1)} ${(x + rr).toFixed(1)},${y.toFixed(1)} L${(x2 - rr).toFixed(1)},${y.toFixed(1)} Q${x2},${y.toFixed(1)} ${x2},${(y + rr).toFixed(1)} L${x2},${(y + h).toFixed(1)} Z`;
}

function monthlyChartSvg(data, series, { w = 356, h = 196 } = {}) {
  const padL = 26, padR = 2, padT = 8, padB = 16;
  const pw = w - padL - padR, ph = h - padT - padB;
  const rawMax = Math.max(0, ...data.flatMap((d) => series.map((s) => Number(d[s.key]) || 0)));
  const yMax = niceCeil(rawMax || 1);
  // 눈금 간격이 0.5/1/2 같은 깔끔한 값이 되도록 눈금 수를 최대값 유효숫자에 맞춤
  const mant = yMax / 10 ** Math.floor(Math.log10(yMax));
  const ticks = mant === 2 ? 4 : 5;
  let el = '';
  for (let i = 0; i <= ticks; i++) {
    const v = (yMax / ticks) * i;
    const y = padT + ph - (v / yMax) * ph;
    el += `<line x1="${padL}" x2="${w - padR}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}" stroke="${i === 0 ? '#c9ccd2' : '#eef0f3'}" stroke-width="1"/>`;
    el += `<text x="${padL - 5}" y="${(y + 2.4).toFixed(1)}" text-anchor="end" font-size="6.8" fill="#9095a0">${fmtTick(v)}</text>`;
  }
  const n = series.length;
  const gap = 2;                              // 인접 막대 사이 2px 표면 간격
  const gw = pw / data.length;
  const bw = Math.max(2.5, Math.min(9, (gw - 7 - gap * (n - 1)) / n));
  const inner = n * bw + (n - 1) * gap;
  data.forEach((d, i) => {
    const gx = padL + gw * i + (gw - inner) / 2;
    series.forEach((s, j) => {
      const v = Number(d[s.key]) || 0;
      const bh = (v / yMax) * ph;
      if (bh > 0.4) {
        el += `<path d="${barPath(gx + j * (bw + gap), padT + ph - bh, bw, bh, 1.6)}" fill="${s.color}"/>`;
      }
    });
    el += `<text x="${(gx + inner / 2).toFixed(1)}" y="${h - 4}" text-anchor="middle" font-size="6.8" fill="#9095a0">${esc(String(d.name).replace('월', ''))}</text>`;
  });
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" style="display:block" xmlns="http://www.w3.org/2000/svg" role="img">${el}</svg>`;
}

const legendHtml = (series) => series.map((s) =>
  `<span class="lg"><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join('');

export function buildReportHtml({ res, projectData = {}, lccAnalysis = {}, zones = [], regionName }) {
  const fin = res?.financial || {};
  const sum = res?.summary || {};
  const ba = fin.baseline_assumptions || {};
  const base = res?.baseline;
  const eq = res?.hvacEquipment;
  const recs = fin.recommendations || [];
  // ⚠️ 지면 상한. 넘치면 **조용히 버리지 않고** '외 N건'으로 알린다 —
  // 예전엔 .sheet 의 overflow:hidden 이 넘친 내용을 소리 없이 잘라냈다.
  const MAX_INS_ROWS = 8;
  const MAX_WARN_ROWS = 6;
  const notes = fin.estimate_notes || [];
  const warns = fin.cost_warnings || [];
  const cd = fin.cost_details || {};
  const lcc = fin.lcc_parameters || {};
  const monthly = Array.isArray(res?.monthly) ? res.monthly : [];
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
  const savingsPct = ba.savings_pct ?? '—'; // 운영비 기준 절감률 (에너지 아님)

  // 목표 예산 초과 판단 — 대시보드(ResultDashboard)와 동일 기준 (둘 다 원 단위)
  const targetBudget = Number(fin.target_budget) || 0;
  const overAmt = targetBudget > 0 ? (Number(fin.capital_cost) || 0) - targetBudget : 0;
  const overBudget = overAmt > 0;
  const overPct = overBudget ? Math.round((overAmt / targetBudget) * 100) : 0;

  // 개선 후 소요량이 개선 전보다 큰 경우 — PV 자가소비는 kWh에 미반영(요금에만 차감)이라
  // "소요량 증가 + 운영비 감소"가 동시에 성립할 수 있음을 리포트에서 설명해야 함
  const pvKw = Number(projectData.pvCapacity) || 0;
  const energyUp = base && Number(sum.consume_per_m2) > Number(base.summary?.consume_per_m2);
  const sens = Array.isArray(fin.npv_sensitivity) ? fin.npv_sensitivity : [];

  const stat = (labelTxt, value, unit, note = '', noteWarn = false) => `
    <div class="stat">
      <div class="stat-label">${esc(labelTxt)}</div>
      <div class="stat-value">${esc(value)}${unit ? `<span class="stat-unit">${esc(unit)}</span>` : ''}</div>
      ${note ? `<div class="stat-note${noteWarn ? ' warn' : ''}">${esc(note)}</div>` : ''}
    </div>`;

  const row = (k, v) => `<div class="row"><div class="row-k">${esc(k)}</div><div class="row-v">${v}</div></div>`;

  const masthead = (aux) => `
  <div class="band"></div>
  <header class="mast">
    <div>
      <div class="brand">ZeroBase</div>
      <div class="brand-sub">GREEN RETROFIT REPORT</div>
    </div>
    <div class="mast-meta">
      <div class="mm-title">${esc(projectData.name || '건물 그린 리트로핏')}</div>
      <div class="mm-sub">${[regionName || projectData.location, aux, today].filter(Boolean).map(esc).join(' · ')}</div>
    </div>
  </header>`;

  const html = `<!doctype html><html lang="ko"><head><meta charset="utf-8">
<title>ZeroBase 리포트 — ${esc(projectData.name || '건물 분석')}</title>
<style>
  :root {
    --ink: #16181d;
    --ink-2: #565b64;
    --ink-3: #9095a0;
    --hairline: #e4e6ea;
    --soft: #f5f6f8;
    --accent: #047857;        /* 유일한 액센트 — 에메랄드 (본문·수치용 700) */
    --accent-bright: #059669; /* 대형 숫자·밴드용 600 */
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { background: #fff; color: var(--ink);
    font-family: system-ui, -apple-system, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
    -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  @page { size: A4; margin: 0; }
  /* 297mm 정확값은 인쇄 px 반올림으로 하단이 잘림 → 296mm로 안전 확보.
     ⚠️ height + overflow:hidden 이면 내용이 넘칠 때 **조용히 잘린다**(하단 유실).
     min-height 로 바꿔 넘치면 다음 장으로 흘려보낸다 — 잘리는 것보다 낫다. */
  .sheet { width: 210mm; min-height: 296mm; page-break-after: always;
    display: flex; flex-direction: column; background: #fff;
    padding: 0 15mm; }
  .sheet:last-child { page-break-after: auto; }

  /* ── 마스트헤드: 액센트 밴드 + 브랜드 / 2px 잉크 룰 ── */
  .band { height: 5px; background: var(--accent-bright); margin: 0 -15mm; }
  .mast { display: flex; justify-content: space-between; align-items: flex-end;
    padding: 16px 0 12px; border-bottom: 2px solid var(--ink); }
  .brand { font-size: 17px; font-weight: 800; letter-spacing: -0.02em; }
  .brand-sub { font-size: 7px; font-weight: 700; letter-spacing: 0.22em; color: var(--accent);
    margin-top: 2px; }
  .mast-meta { text-align: right; }
  .mm-title { font-size: 11px; font-weight: 700; }
  .mm-sub { font-size: 8.5px; color: var(--ink-3); margin-top: 2px; }

  /* ── 히어로: 좌 핵심 수치 / 우 개선 전후 비교 ── */
  .hero { display: grid; grid-template-columns: 1.1fr 1fr; gap: 28px; align-items: center;
    padding: 30px 0 26px; border-bottom: 1px solid var(--hairline); }
  .kicker { font-size: 8px; font-weight: 700; letter-spacing: 0.18em; color: var(--ink-3); }
  .hero .display { font-size: 48px; font-weight: 800; letter-spacing: -0.03em; line-height: 1.05;
    margin-top: 8px; font-variant-numeric: tabular-nums; }
  .hero .display .u { font-size: 13px; font-weight: 500; color: var(--ink-3); margin-left: 6px;
    letter-spacing: 0; }
  .hero .lead { margin-top: 8px; font-size: 9.5px; line-height: 1.5; color: var(--ink-2); }
  .hero .save { margin-top: 10px; font-size: 11px; font-weight: 700; }
  .hero .save b { color: var(--accent); font-variant-numeric: tabular-nums; }
  .hero .save span + span { margin-left: 14px; }

  .ba { background: var(--soft); border-radius: 12px; padding: 16px 18px; }
  .ba-t { font-size: 8px; font-weight: 700; letter-spacing: 0.14em; color: var(--ink-3); }
  .ba-grid { margin-top: 10px; display: grid; grid-template-columns: 1fr auto 1fr;
    align-items: center; gap: 12px; }
  .ba-k { font-size: 8px; color: var(--ink-3); font-weight: 600; }
  .ba-v { font-size: 17px; font-weight: 800; letter-spacing: -0.02em; margin-top: 3px;
    font-variant-numeric: tabular-nums; }
  .ba-v .u { font-size: 8.5px; font-weight: 500; color: var(--ink-3); }
  .ba-cost { margin-top: 4px; font-size: 8.5px; color: var(--ink-2); }
  .ba-arrow { font-size: 15px; color: var(--accent); font-weight: 700; }
  .ba-note { margin-top: 9px; font-size: 7.5px; color: var(--ink-3); }

  /* ── KPI: 카드 없이 2px 톱룰 스탯 (에디토리얼) ── */
  .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px 22px;
    padding: 22px 0 24px; border-bottom: 1px solid var(--hairline); }
  .stat { border-top: 2px solid var(--ink); padding-top: 8px; }
  .stat-label { font-size: 7.5px; font-weight: 700; letter-spacing: 0.1em; color: var(--ink-3); }
  .stat-value { font-size: 17px; font-weight: 800; letter-spacing: -0.02em; margin-top: 5px;
    font-variant-numeric: tabular-nums; }
  .stat-unit { font-size: 8.5px; font-weight: 500; color: var(--ink-3); margin-left: 3px; }
  .stat-note { margin-top: 3px; font-size: 7.8px; color: var(--ink-2); }
  .stat-note.warn { color: #b91c1c; font-weight: 700; }

  /* ── 월별 차트 2분할: 냉난방 / 조명·기기·급탕 ── */
  .charts { padding: 24px 0 6px; }
  .charts-h { display: flex; align-items: baseline; gap: 10px; }
  .charts-h h2 { font-size: 12.5px; font-weight: 800; letter-spacing: -0.01em; }
  .charts-h .unit { font-size: 8px; color: var(--ink-3); }
  .chart-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 22px; margin-top: 10px; }
  .chart-box .ch-h { display: flex; justify-content: space-between; align-items: baseline;
    margin-bottom: 6px; }
  .chart-box .ch-t { font-size: 9.5px; font-weight: 700; }
  .legend { display: flex; gap: 9px; }
  .lg { display: inline-flex; align-items: center; gap: 4px; font-size: 7.8px; font-weight: 600;
    color: var(--ink-2); }
  .lg i { width: 7px; height: 7px; border-radius: 2px; display: inline-block; }

  /* ── 추천 대안 ── */
  .recs { padding: 22px 0 0; border-top: 1px solid var(--hairline); margin-top: 18px; }
  .recs .t { font-size: 11.5px; font-weight: 800; }
  .recs .t b { color: var(--accent); font-variant-numeric: tabular-nums; }
  .recs .list { margin-top: 9px; display: grid; grid-template-columns: 1fr 1fr; gap: 3px 26px; }
  .recs .item { font-size: 9.2px; line-height: 1.55; padding: 3.5px 0; color: var(--ink-2);
    border-bottom: 1px solid var(--soft); }
  .recs .item b { font-weight: 700; color: var(--ink); }
  .recs .item .amt { color: var(--accent); font-weight: 700; font-variant-numeric: tabular-nums; }

  /* ── 2페이지 섹션 ── */
  .section { margin-top: 18px; break-inside: avoid; page-break-inside: avoid; }
  .section-h { display: flex; align-items: baseline; gap: 9px; padding-bottom: 6px;
    border-bottom: 2px solid var(--ink); margin-bottom: 8px; }
  .section-no { font-size: 9px; font-weight: 800; color: var(--accent);
    font-variant-numeric: tabular-nums; }
  .section-h h2 { font-size: 12.5px; font-weight: 800; letter-spacing: -0.01em; }
  .section-h .cost { margin-left: auto; font-size: 11px; font-weight: 800;
    font-variant-numeric: tabular-nums; }
  .section-h .cost::before { content: "공사비 "; font-size: 7.5px; font-weight: 600;
    color: var(--ink-3); letter-spacing: 0.08em; margin-right: 3px; }
  .row { display: grid; grid-template-columns: 34% 1fr; padding: 5px 0;
    border-bottom: 1px solid var(--soft); font-size: 9.8px; }
  .row:last-child { border-bottom: none; }
  .row-k { color: var(--ink-3); font-weight: 500; }
  .row-v { font-weight: 700; color: var(--ink); }
  .grid2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0 36px; }

  table { width: 100%; border-collapse: collapse; font-size: 9.3px; margin-top: 4px; }
  th { text-align: left; font-size: 7.2px; font-weight: 700; letter-spacing: 0.08em;
    color: var(--ink-3); padding: 4px 8px; border-bottom: 1px solid var(--ink); }
  td { padding: 5px 8px; border-bottom: 1px solid var(--soft); font-weight: 500;
    vertical-align: top; color: var(--ink); }
  tr:last-child td { border-bottom: none; }
  td.n { font-variant-numeric: tabular-nums; white-space: nowrap; }
  .chip { display: inline-block; font-size: 7.5px; font-weight: 600; padding: 2px 8px;
    border-radius: 9999px; background: var(--soft); color: var(--ink-2); }
  .chip.user { background: #fff; border: 1px solid var(--accent); color: var(--accent); }

  /* ── 가정·유의 ── */
  .assump { break-inside: avoid; page-break-inside: avoid;
    background: var(--soft); border-radius: 12px; padding: 14px 16px 12px;
    margin-top: 18px; }
  .assump .t { font-size: 10.5px; font-weight: 800; margin-bottom: 7px; }
  .note-item { break-inside: avoid; }
  .note-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 2px 22px; font-size: 8.2px;
    color: var(--ink-2); }
  .note-grid b { color: var(--ink); font-weight: 700; }
  .note-item { padding: 2.5px 0; line-height: 1.5; }
  .warn-item { font-size: 8.2px; color: var(--ink-2); padding: 2px 0; line-height: 1.5; }
  .warn-item::before { content: "◦ "; color: var(--ink-3); }

  /* ── 푸터 ── */
  table { break-inside: auto; }
  tr { break-inside: avoid; page-break-inside: avoid; }
  .foot { margin-top: auto; break-inside: avoid; border-top: 1px solid var(--hairline); padding: 10px 0 14px;
    display: flex; justify-content: space-between; align-items: flex-start; gap: 16px;
    font-size: 7.5px; color: var(--ink-3); line-height: 1.55; }
  .foot b { color: var(--ink-2); font-weight: 700; }
  .pageno { font-weight: 800; white-space: nowrap; color: var(--ink);
    font-variant-numeric: tabular-nums; }
</style></head><body>

<!-- ═══════════ PAGE 1 · 요약 + 월별 그래프 ═══════════ -->
<section class="sheet">
  ${masthead(`존 ${zones.length || (eq?.zones?.length ?? '—')}개`)}

  <div class="hero">
    <div>
      <div class="kicker">연간 에너지 소요량</div>
      <div class="display">${num(sum.consume_per_m2)}<span class="u">kWh/㎡·년</span></div>
      <div class="lead">기준 건물(${esc(baselineLabel)}) 대비 · 난방 열원 ${esc(heatLabel)}</div>
      <div class="save">
        <span>운영비 절감률 <b>${esc(savingsPct)}%</b></span>
        <span>연간 운영비 절감액 <b>${won(lccAnalysis.annualSavings)}</b></span>
      </div>
    </div>
    ${base ? `
    <div class="ba">
      <div class="ba-t">개선 전 · 후 비교</div>
      <div class="ba-grid">
        <div>
          <div class="ba-k">개선 전 (원본 건물)</div>
          <div class="ba-v">${num(base.summary?.consume_per_m2)}<span class="u"> kWh/㎡</span></div>
          <div class="ba-cost">연간 운영비 ${won((base.annual_elec_bill || 0) + (base.annual_heat_bill || 0))}</div>
        </div>
        <div class="ba-arrow">→</div>
        <div>
          <div class="ba-k">개선 후 (리모델링안)</div>
          <div class="ba-v">${num(sum.consume_per_m2)}<span class="u"> kWh/㎡</span></div>
          <div class="ba-cost">연간 운영비 ${won((fin.annual_elec_bill || 0) + (fin.annual_heat_bill || 0))}</div>
        </div>
      </div>
      <div class="ba-note">${[
        'kWh 수치는 동일 물리 엔진(EnergyPlus) 산출',
        energyUp ? (pvKw > 0
          ? `소요량에는 PV 자가소비(연 ${(pvKw * 1300).toLocaleString()} kWh)가 차감되지 않고 요금에서만 상쇄되어, 소요량이 늘어도 운영비는 감소할 수 있습니다`
          : '열원·요금 구조에 따라 소요량이 늘어도 운영비는 감소할 수 있습니다') : '',
        ba.source && ba.source !== 'simulated' ? `절감액 산정 기준: ${esc(baselineLabel)}` : '',
      ].filter(Boolean).join(' · ')}</div>
    </div>` : ''}
  </div>

  <div class="stats">
    ${stat('1차에너지 소요량', num(sum.primary_per_m2), 'kWh/㎡·년')}
    ${stat('CO2 배출량', num(sum.co2_per_m2, 2), 'kg/㎡·년')}
    ${stat('에너지 자립률', `${zebRate}`, '%', `ZEB ${zebGrade}`)}
    ${stat('총 공사비', won(fin.capital_cost), '',
      targetBudget > 0
        ? (overBudget ? `목표 예산 ${won(overAmt)} (${overPct}%) 초과` : '목표 예산 이내')
        : '', overBudget)}
    ${stat('연간 에너지 요금', won(fin.total_energy_bill ?? ((fin.annual_elec_bill || 0) + (fin.annual_heat_bill || 0))), '', `전기 ${won(fin.annual_elec_bill)} · 열 ${won(fin.annual_heat_bill)}`)}
    ${stat('투자 회수기간', lccAnalysis.paybackYears ? num(lccAnalysis.paybackYears) : '분석기간 내 미회수', '년', `NPV ${won(fin.npv)} · IRR ${fin.irr == null ? '—' : num(fin.irr) + '%'}`)}
  </div>

  ${monthly.length ? `
  <div class="charts">
    <div class="charts-h">
      <h2>월별 에너지 요구량</h2>
      <span class="unit">단위: kWh/㎡ · 가로축: 월</span>
    </div>
    <div class="chart-grid">
      <div class="chart-box">
        <div class="ch-h">
          <div class="ch-t">냉난방</div>
          <div class="legend">${legendHtml(SERIES_HVAC)}</div>
        </div>
        ${monthlyChartSvg(monthly, SERIES_HVAC)}
      </div>
      <div class="chart-box">
        <div class="ch-h">
          <div class="ch-t">조명 · 기기 · 급탕</div>
          <div class="legend">${legendHtml(SERIES_INTERNAL)}</div>
        </div>
        ${monthlyChartSvg(monthly, SERIES_INTERNAL)}
      </div>
    </div>
  </div>` : ''}

  ${recs.length ? `
  <div class="recs">
    <div class="t">개선 대안 ${recs.length}건${recTotal > 0 ? ` — 비용 절감안 모두 적용 시 <b>−${won(recTotal)}</b>` : ''}</div>
    <div class="list">
      ${recs.map((r) => {
        const imp = r.impact;
        // 재시뮬레이션 산출 정량 영향이 있으면 수치를, 없으면 정성 주석을 병기
        const isUp = r.direction === 'upgrade';
        // 정량 평가가 없는 이유는 두 가지고 뜻이 다르다 — 실패를 "영향 없음"으로
        // 적으면 보고서가 거짓 근거를 싣게 된다.
        const noImpactNote = r.impact_status === 'failed'
          ? '↳ 정량 영향 산출 실패(재시뮬레이션 오류) — 에너지·운영비 변화 미확인'
          : (imp ? '↳ 에너지 영향 없음(열모델 불변)' : '');
        const sub = imp?.simulated
          ? `↳ 에너지 ${imp.delta_kwh_m2 > 0 ? '+' : ''}${imp.delta_kwh_m2} kWh/㎡·년 · 운영비 ${imp.annual_bill_delta > 0 ? '+' : ''}${won(imp.annual_bill_delta)}/년 · 실공사비 ${imp.capital_delta > 0 ? '+' : ''}${won(imp.capital_delta)}${imp.payback_years ? ` · 회수 ${imp.payback_years}년` : ''} · ${imp.lifecycle_years}년 순효과 <b style="color:${imp.net_effect >= 0 ? 'var(--accent)' : '#b91c1c'}">${imp.net_effect >= 0 ? '+' : ''}${won(imp.net_effect)}</b> (EnergyPlus 재시뮬레이션 산출)`
          : [noImpactNote, r.performance_note ? esc(r.performance_note) : '']
              .filter(Boolean).join(' · ');
        const advise = r.advisable === false ? ` <span style="color:#b91c1c; font-weight:700">(비권장 — 장기 손해, 예산 제약 시에만)</span>` : '';
        const head = (isUp
          ? `<b>[상향] ${esc(r.title)}</b> — 공사비 <span class="amt">${(imp?.simulated ? imp.capital_delta : (r.added_cost || 0)) > 0 ? '+' : ''}${won(imp?.simulated ? imp.capital_delta : (r.added_cost || 0))}</span>`
          : `<b>${esc(r.title)}</b> — 절감 <span class="amt">${won(r.saved_cost)}</span>`) + advise;
        return `<div class="item">${head}${sub ? `<br><span style="color:var(--ink-3); font-size:8px">${sub}</span>` : ''}</div>`;
      }).join('')}
    </div>
  </div>` : ''}

  <div class="foot">
    <div>
      <b>기준 건물</b> ${esc(baselineLabel)} · <b>시뮬레이션</b> EnergyPlus 25.2 연간 8,760시간 ·
      <b>기상</b> 한국 TMYx(2009–2023) · <b>요금</b> KEPCO(2026)·KDHC(2024) ·
      <b>단가</b> 친환경건설자재 DB 중앙값 — 결과는 추정치이며 실제 견적·요금과 차이가 날 수 있습니다.
    </div>
    <div class="pageno">요약</div>
  </div>
</section>

<!-- ═══════════ PAGE 2 · 섹션별 선택 사항 · 자재 상세 ═══════════ -->
<section class="sheet">
  ${masthead('적용 사양 및 자재 상세')}

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
        ${row('목표 예산', targetBudget > 0
          ? `${won(targetBudget)}${overBudget
              ? ` <span style="color:#b91c1c">— 공사비가 ${won(overAmt)} (${overPct}%) 초과</span>`
              : ' — 공사비 예산 이내'}`
          : '미설정')}
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
    ${fin.hvac_capacity_kw ? row('공사비 산정 용량', `건물 전체 피크부하 기준 ${num(fin.hvac_capacity_kw, 0)} kW × kW당 시스템 단가 — 아래 표의 기기 용량은 존 1개당 모델 값이며, '존 수'만큼 설치를 가정한 것으로 두 수치는 산정 목적이 다릅니다`) : ''}
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
      ${eqGroups.length > 6 ? `<tr><td colspan="4" style="color:var(--ink-3)">…외 구성 ${eqGroups.length - 6}종</td></tr>` : ''}
    </table>` : ''}
  </div>

  <div class="section">
    <div class="section-h"><span class="section-no">03</span><h2>창호</h2>
      <span class="cost">${won(cd.window)}</span></div>
    ${fin.window_details ? `
    ${row('적용 창호', `${esc(fin.mapped_window_name || '—')} — 대표 U값 <b>${num(fin.window_details.u_value, 2)} W/㎡K</b> · SHGC ${num(fin.window_details.shgc, 2)}`)}
    ${row('산정 단가', `친환경건설자재 DB 창세트 중앙값 <b>₩${(fin.window_details.unit_price || 0).toLocaleString()}/㎡</b> × 창 면적 ${num(fin.window_details.area_m2)}㎡`)}
    ${row('산정 방식', '창 면적가중 실측 U/SHGC로 성능 등급을 매칭한 뒤 해당 등급 중앙값 단가 적용')}` : `
    ${row('적용 등급 (U값 기반 매칭)', esc(fin.mapped_window_name || '—'))}
    ${row('산정 방식', '창 면적가중 실측 U/SHGC → 친환경건설자재 DB 창세트 중앙값 단가')}`}
  </div>

  <div class="section">
    <div class="section-h"><span class="section-no">04</span><h2>단열재</h2>
      <span class="cost">${won(cd.insulation)}</span></div>
    ${insGroups.length ? `
    <table>
      <tr><th>등급</th><th style="text-align:right">시공 면적</th><th style="text-align:right">단가</th><th style="text-align:right">비용</th><th style="text-align:right">부위 수</th></tr>
      ${insGroups.slice(0, MAX_INS_ROWS).map((g) => `
      <tr>
        <td>${esc(g.tier)}</td>
        <td class="n" style="text-align:right">${g.area.toFixed(1)} ㎡</td>
        <td class="n" style="text-align:right">₩${(g.price || 0).toLocaleString()}/㎡</td>
        <td class="n" style="text-align:right">${won(g.cost)}</td>
        <td class="n" style="text-align:right">${g.count}</td>
      </tr>`).join('')}
      ${insGroups.length > MAX_INS_ROWS ? `<tr><td colspan="5" style="color:var(--ink-3)">
        · 외 ${insGroups.length - MAX_INS_ROWS}개 등급은 지면 관계로 생략했습니다 (합계에는 포함)</td></tr>` : ''}
    </table>` : row('산정 방식', '단열층 미검출 — 벽면적 × DB 폴백 단가 적용')}
  </div>

  <div class="section">
    <div class="section-h"><span class="section-no">05</span><h2>LED 조명</h2>
      <span class="cost">${won(cd.led)}</span></div>
    ${row('산정 방식', '거주면적 10㎡당 등기구 1개 환산 × 개당 중앙값 단가 (비거주 구역 30% 반영)')}
  </div>

  <div class="assump">
    <div class="t">산정 가정 및 유의사항</div>
    <div class="note-grid">
      ${notes.map((n) => `<div class="note-item"><b>${esc(n.label)}</b> — ${esc(n.note)}</div>`).join('')}
    </div>
    ${warns.length ? `<div style="margin-top:6px">${warns.slice(0, MAX_WARN_ROWS).map((w) => `<div class="warn-item">${esc(w)}</div>`).join('')}${warns.length > MAX_WARN_ROWS ? `<div class="warn-item">· 외 ${warns.length - MAX_WARN_ROWS}건 — 화면의 경고 목록에서 전체를 확인하세요</div>` : ''}</div>` : ''}
    ${sens.length ? `
    <div style="margin-top:8px; border-top:1px solid var(--hairline); padding-top:7px">
      <div style="font-size:8.2px; font-weight:700; margin-bottom:2px">NPV 민감도 — 기본 ${won(fin.npv)} (${lcc.lifecycle_years ?? 20}년, 재시뮬레이션 없이 가정만 변경)</div>
      ${sens.map((s) => `<div class="note-item">${esc(s.param)} ${esc(s.low_label)} → <b>${won(s.low)}</b> · ${esc(s.high_label)} → <b>${won(s.high)}</b></div>`).join('')}
    </div>` : ''}
  </div>

  <div class="foot">
    <div><b>ZeroBase</b> — gbXML 기반 그린 리트로핏 시뮬레이션 · 생성일 ${today} · 본 리포트의 수치는 물리 시뮬레이션 기반 추정치입니다.</div>
    <div class="pageno">산정 근거</div>
  </div>
</section>

<script>
  // 렌더 완료 후 인쇄 다이얼로그 자동 호출 (PDF로 저장)
  window.addEventListener('load', () => setTimeout(() => window.print(), 400));
</script>
</body></html>`;

  return html;
}

export function openPdfReport(params) {
  const html = buildReportHtml(params);
  const win = window.open('', '_blank');
  if (!win) {
    alert('팝업이 차단되어 리포트를 열 수 없습니다. 팝업을 허용해 주세요.');
    return;
  }
  win.document.write(html);
  win.document.close();
}
