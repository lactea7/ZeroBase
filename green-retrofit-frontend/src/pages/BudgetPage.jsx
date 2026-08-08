import React from 'react';
// ⚠️ 아이콘 import 를 빠뜨리면 빌드는 통과하고 **런타임에 백지 화면**이 된다.
import { DollarSign, PiggyBank } from 'lucide-react';
import WizardShell from '../components/layout/WizardShell';

/**
 * 예산 설정.
 *
 * ⚠️ 예산을 넘으면 백엔드가 경고를 붙여 내려준다 — 여기 값이 그 판정 기준이다.
 */
export default function BudgetPage({
  theme, isDarkMode, setStep, projectData, setProjectData,
}) {
  return (
            <WizardShell
              theme={theme} isDarkMode={isDarkMode} setStep={setStep}
              icon={<PiggyBank size={32} />}
              title="목표 예산 & 기존 건물 사용량"
              subtitle="목표 공사비와, 리모델링 전 실제 사용량을 입력하세요."
              back="renewable" next="financial"
            >
              <div className={`p-8 rounded-[2rem] border ${theme.card}`}>
                <div className="space-y-6">
                      <div className="p-4 rounded-xl border-2 border-slate-500/30 bg-black/5">
                        <label className="flex items-center justify-between mb-2">
                          <span className={`font-black flex items-center gap-2 ${theme.textMain}`}>
                            <PiggyBank className="text-pink-500" size={18} /> 목표 공사 예산 (단위: 만 원)
                          </span>
                          <span className="text-pink-500 bg-pink-500/10 px-3 py-1 rounded-lg text-[11px] font-black uppercase tracking-widest">
                            {projectData.targetBudget === 0 ? '미설정 (제한없음)' : `${projectData.targetBudget.toLocaleString()} 만 원`}
                          </span>
                        </label>
                        <input
                          type="number"
                          min="0"
                          step="100"
                          value={projectData.targetBudget || ''}
                          placeholder="예: 5000 (5천만 원)"
                          onChange={(e) => setProjectData({ ...projectData, targetBudget: parseInt(e.target.value) || 0 })}
                          className={`w-full p-3 rounded-lg focus:ring-2 focus:ring-pink-500 outline-none transition-all font-mono font-bold ${theme.input}`}
                        />
                        <p className="text-[11px] opacity-60 mt-2">
                          목표 예산을 설정하면, 시뮬레이션 결과에서 예산 초과 여부를 분석하고 비용 절감을 위한 대안(창호 등급 하향 등)을 추천해 드립니다.
                        </p>
                      </div>

                      {/* 기존 건물 실측 운영비(선택) — 비우면 1.6배 추정으로 계산됨을 결과에 고지 */}
                      <div>
                        <label className={`flex items-center gap-2 text-sm font-black mb-2 ${theme.textMain}`}>
                          <DollarSign className="text-emerald-500" size={16} /> 기존 건물 실제 사용량 (선택)
                        </label>
                        <p className="text-[10px] opacity-60 mb-3">
                          리모델링 전 건물의 작년 값을 입력하면 절감액·NPV·IRR을 실측 기준으로 계산합니다.
                          비워두면 <b>리모델링 후 운영비의 1.6배</b>로 추정합니다.
                        </p>
                        <div className="flex gap-2 mb-3">
                          {[{ k: 'bill', t: '연간 요금(원)' }, { k: 'usage', t: '연간 사용량(kWh)' }].map((m) => (
                            <button
                              key={m.k}
                              type="button"
                              onClick={() => setProjectData((p) => ({ ...p, baselineActual: { ...p.baselineActual, mode: m.k } }))}
                              className={`flex-1 py-2 text-xs font-black rounded-lg border-2 transition-all ${projectData.baselineActual.mode === m.k ? 'border-emerald-500 bg-emerald-500/10 text-emerald-500' : 'border-slate-500/30 opacity-60'}`}
                            >
                              {m.t}
                            </button>
                          ))}
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          {(projectData.baselineActual.mode === 'bill'
                            ? [{ f: 'elecBill', t: '전기요금 (원/년)' }, { f: 'heatBill', t: '난방요금 (원/년)' }]
                            : [{ f: 'elecKwh', t: '전기 (kWh/년)' }, { f: 'heatKwh', t: '난방 (kWh/년)' }]
                          ).map((x) => (
                            <div key={x.f}>
                              <span className="text-[10px] opacity-70 block mb-1">{x.t}</span>
                              <input
                                type="number"
                                min="0"
                                placeholder="미입력 시 추정"
                                value={projectData.baselineActual[x.f]}
                                onChange={(e) => setProjectData((p) => ({ ...p, baselineActual: { ...p.baselineActual, [x.f]: e.target.value } }))}
                                className={`w-full p-2.5 text-sm font-bold rounded-lg border outline-none ${theme.input} focus:border-emerald-500`}
                              />
                            </div>
                          ))}
                        </div>
                      </div>
                </div>
              </div>
            </WizardShell>
  );
}
