import React from 'react';
// ⚠️ 아이콘 import 를 빠뜨리면 빌드는 통과하고 **런타임에 백지 화면**이 된다.
import { Calculator } from 'lucide-react';
import WizardShell from '../components/layout/WizardShell';

/**
 * 경제성 분석 조건 — 할인율·물가상승률·분석기간.
 *
 * ⚠️ 이 값들은 `projectData.lccParameters` 안에 있어야 백엔드가 읽는다.
 * 최상위로 올리면 조용히 기본값으로 돌아간다(utils/simulationPayload.js 참조).
 * **0% 도 유효한 입력이다** — 빈 값과 구분해야 한다.
 */
export default function FinancialPage({
  theme, isDarkMode, setStep, projectData, setProjectData,
}) {
  return (
            <WizardShell
              theme={theme} isDarkMode={isDarkMode} setStep={setStep}
              icon={<Calculator size={32} />}
              title="재무 분석 설정 (LCC)"
              subtitle="할인율·물가상승률·수명주기 기간을 설정합니다. (기본값 권장)"
              back="budget" next="buildingView" nextLabel="3D 모델 렌더링"
            >
              <div className={`p-8 rounded-[2rem] border ${theme.card}`}>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <div>
                            <label className={`block text-xs font-bold mb-1 opacity-70 ${theme.textMain}`}>인플레이션율 (%)</label>
                            <input
                              type="number" step="0.1"
                              value={projectData.lccParameters.inflationRate}
                              onChange={(e) => setProjectData({ ...projectData, lccParameters: { ...projectData.lccParameters, inflationRate: parseFloat(e.target.value) || 0 } })}
                              className={`w-full p-2 rounded-lg outline-none font-mono font-bold ${theme.input}`}
                            />
                          </div>
                          <div>
                            <label className={`block text-xs font-bold mb-1 opacity-70 ${theme.textMain}`}>에너지 요금 상승률 (%)</label>
                            <input
                              type="number" step="0.1"
                              value={projectData.lccParameters.utilityInflation}
                              onChange={(e) => setProjectData({ ...projectData, lccParameters: { ...projectData.lccParameters, utilityInflation: parseFloat(e.target.value) || 0 } })}
                              className={`w-full p-2 rounded-lg outline-none font-mono font-bold ${theme.input}`}
                            />
                          </div>
                          <div>
                            <label className={`block text-xs font-bold mb-1 opacity-70 ${theme.textMain}`}>할인율 (기대수익률, %)</label>
                            <input
                              type="number" step="0.1"
                              value={projectData.lccParameters.discountRate}
                              onChange={(e) => setProjectData({ ...projectData, lccParameters: { ...projectData.lccParameters, discountRate: parseFloat(e.target.value) || 0 } })}
                              className={`w-full p-2 rounded-lg outline-none font-mono font-bold ${theme.input}`}
                            />
                          </div>
                          <div>
                            <label className={`block text-xs font-bold mb-1 opacity-70 ${theme.textMain}`}>수명주기 분석 기간 (년)</label>
                            <input
                              type="number" step="1" min="5" max="50"
                              value={projectData.lccParameters.lifecycleYears}
                              onChange={(e) => setProjectData({ ...projectData, lccParameters: { ...projectData.lccParameters, lifecycleYears: parseInt(e.target.value) || 20 } })}
                              className={`w-full p-2 rounded-lg outline-none font-mono font-bold ${theme.input}`}
                            />
                          </div>
                          <p className="col-span-1 md:col-span-2 text-[10px] opacity-60 mt-1">
                            수명주기비용(LCC) 분석 모형에 따라 각 항목별 물가상승률을 복리로 적용하여 순현재가치(NPV) 및 내부수익률(IRR)을 계산합니다.
                          </p>
                        </div>
              </div>
            </WizardShell>
  );
}
