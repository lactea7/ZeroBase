import React from 'react';
// ⚠️ 아이콘 import 를 빠뜨리면 빌드는 통과하고 **런타임에 백지 화면**이 된다.
import { Flame, Layers, Sun, Thermometer, ToggleLeft, ToggleRight, Wind, Zap } from 'lucide-react';
import WizardShell from '../components/layout/WizardShell';
import { COOLING_GRADES, FUEL_TYPES, HEATING_AGES } from '../data/hvac';

/**
 * 신재생·설비 설정 — PV·지열·LED·설비 등급.
 *
 * ⚠️ 여기 선택이 **개선 후 모델을 정의한다.** 기준선(개선 전)에서는 백엔드가
 * 이 항목들을 전부 지우므로(`simulation/baseline.RETROFIT_KEYS`), 여기 추가되는
 * 항목은 그쪽에도 같이 등록해야 절감액이 맞는다.
 */
export default function RenewablePage({
  theme, isDarkMode, setStep, projectData, setProjectData, zones, groundEligible,
}) {
  return (
            <WizardShell
              theme={theme} isDarkMode={isDarkMode} setStep={setStep}
              icon={<Sun size={32} />}
              title="신재생 에너지 & 설비"
              subtitle="태양광·지열·난방 열원·설비 교체 여부를 설정하세요."
              back="projectInfo" next="budget"
            >
              <div className={`p-8 rounded-[2rem] border ${theme.card} border-blue-500/20`}>
                    <div className="space-y-6">
                      <div>
                        <label className={`flex justify-between items-center text-sm font-black mb-3 ${theme.textMain}`}>
                          <span className="flex items-center gap-2">
                            <Sun className="text-yellow-500" size={16} /> 태양광(PV) 패널 설치 용량
                          </span>
                          <span className="text-[#c2734a] bg-[#c2734a]/10 px-3 py-1 rounded-lg text-[11px] uppercase tracking-widest">
                            {projectData.pvCapacity} kW
                          </span>
                        </label>
                        <input
                          type="range"
                          min="0"
                          max="100"
                          step="5"
                          value={projectData.pvCapacity}
                          onChange={(e) => setProjectData({ ...projectData, pvCapacity: parseInt(e.target.value) })}
                          className="w-full h-3 rounded-full appearance-none accent-[#c2734a] bg-[#dccfbb] cursor-pointer"
                        />
                      </div>

                      {/* 난방 열원 선택 — 요금·1차에너지·CO2가 열원별로 달라짐 */}
                      <div>
                        <label className={`flex items-center gap-2 text-sm font-black mb-3 ${theme.textMain}`}>
                          <Flame className="text-orange-500" size={16} /> 난방 열원 (Heating Source)
                        </label>
                        <select
                          value={projectData.heatSource}
                          onChange={(e) => setProjectData({ ...projectData, heatSource: parseInt(e.target.value) })}
                          disabled={projectData.geothermalApplied}
                          className={`w-full p-3 text-sm font-bold rounded-xl border outline-none ${theme.input} focus:border-orange-500 ${projectData.geothermalApplied ? 'opacity-40 cursor-not-allowed' : ''}`}
                        >
                          {FUEL_TYPES.map((f) => (
                            <option key={f.id} value={f.id}>{f.name}</option>
                          ))}
                        </select>
                        <p className="text-[10px] opacity-60 mt-1">
                          {projectData.geothermalApplied
                            ? '지열 적용 시 난방은 전기(히트펌프)로 계산됩니다.'
                            : '열원에 따라 난방 요금·1차에너지·CO2 계수가 달라집니다.'}
                        </p>
                      </div>

                      {/* 냉난방 실기기 등급/연식 — 시뮬레이션 기기 효율(COP)에 직접 반영 */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                          <label className={`flex items-center gap-2 text-sm font-black mb-3 ${theme.textMain}`}>
                            <Wind className="text-cyan-500" size={16} /> 냉방기(에어컨) 등급·연식
                          </label>
                          <select
                            value={projectData.hvacEquipment?.coolingGrade || 'grade3'}
                            onChange={(e) => setProjectData((prev) => ({
                              ...prev,
                              hvacEquipment: { ...(prev.hvacEquipment || {}), coolingGrade: e.target.value },
                            }))}
                            className={`w-full p-3 text-sm font-bold rounded-xl border outline-none ${theme.input} focus:border-cyan-500`}
                          >
                            {COOLING_GRADES.map((g) => (
                              <option key={g.id} value={g.id}>{g.name}</option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className={`flex items-center gap-2 text-sm font-black mb-3 ${theme.textMain}`}>
                            <Flame className="text-rose-400" size={16} /> 난방기(보일러) 연식
                          </label>
                          <select
                            value={projectData.hvacEquipment?.heatingAge || 'new'}
                            onChange={(e) => setProjectData((prev) => ({
                              ...prev,
                              hvacEquipment: { ...(prev.hvacEquipment || {}), heatingAge: e.target.value },
                            }))}
                            className={`w-full p-3 text-sm font-bold rounded-xl border outline-none ${theme.input} focus:border-rose-400`}
                          >
                            {HEATING_AGES.map((a) => (
                              <option key={a.id} value={a.id}>{a.name}</option>
                            ))}
                          </select>
                        </div>
                        <p className="md:col-span-2 text-[10px] opacity-60 -mt-2">
                          입력한 등급·연식이 시뮬레이션 기기 효율(COP)에 직접 반영됩니다.
                          존별 냉방기 설치 여부·용량은 3D 편집 단계에서 조정할 수 있어요.
                        </p>
                      </div>

                      {/* 자기참조 최하층 바닥의 경계조건 선택.
                          익스포터가 지면 접촉 바닥을 SlabOnGrade 대신 자기참조 InteriorFloor 로
                          내보낸 경우가 있는데, 그것이 실제 지면 접촉인지 단열 경계인지는
                          파일만으로 판정할 수 없다. 해당 면이 있을 때만 노출한다. */}
                      {zones.length > 0 && groundEligible.count > 0 && (
                        <div
                          className={`mb-4 p-4 rounded-xl flex items-center justify-between cursor-pointer border-2 transition-all ${projectData.promoteGroundFloors ? 'border-sky-500 bg-sky-500/10' : 'border-slate-500/30 bg-black/5'}`}
                          onClick={() => setProjectData((prev) => ({ ...prev, promoteGroundFloors: !prev.promoteGroundFloors }))}
                        >
                          <div className="flex items-center gap-3">
                            <div className={`p-2 rounded-lg ${projectData.promoteGroundFloors ? 'bg-sky-500 text-white' : 'bg-slate-600 text-slate-300'}`}>
                              <Layers size={18} />
                            </div>
                            <div>
                              <span className={`block font-black text-sm ${projectData.promoteGroundFloors ? 'text-sky-500' : theme.textSub}`}>
                                최하층 바닥을 지면 접촉으로 처리
                              </span>
                              <span className="text-[10px] opacity-60">
                                대상 {groundEligible.count}개 면 · {groundEligible.area.toFixed(1)}㎡ ·
                                끄면 단열 경계(열 이동 없음). 켜면 지면 열손실을 반영합니다.
                                지하층·필로티·외기 노출 바닥이면 켜지 마세요.
                              </span>
                            </div>
                          </div>
                          {projectData.promoteGroundFloors ? (
                            <ToggleRight size={32} className="text-sky-500" />
                          ) : (
                            <ToggleLeft size={32} className="text-slate-500" />
                          )}
                        </div>
                      )}

                      <div
                        className={`p-4 rounded-xl flex items-center justify-between cursor-pointer border-2 transition-all ${projectData.geothermalApplied ? 'border-emerald-500 bg-emerald-500/10' : 'border-slate-500/30 bg-black/5'}`}
                        onClick={() => setProjectData((prev) => ({ ...prev, geothermalApplied: !prev.geothermalApplied }))}
                      >
                        <div className="flex items-center gap-3">
                          <div className={`p-2 rounded-lg ${projectData.geothermalApplied ? 'bg-emerald-500 text-white' : 'bg-slate-600 text-slate-300'}`}>
                            <Zap size={18} />
                          </div>
                          <div>
                            <span className={`block font-black text-sm ${projectData.geothermalApplied ? 'text-emerald-500' : theme.textSub}`}>
                              지열(Geothermal) 히트펌프 적용
                            </span>
                            <span className="text-[10px] opacity-60">냉난방 기기의 효율(COP)을 극대화합니다.</span>
                          </div>
                        </div>
                        {projectData.geothermalApplied ? (
                          <ToggleRight size={32} className="text-emerald-500" />
                        ) : (
                          <ToggleLeft size={32} className="text-slate-500" />
                        )}
                      </div>
                      
                      <div
                        className={`mt-4 p-4 rounded-xl flex items-center justify-between cursor-pointer border-2 transition-all ${projectData.hvacUpgradeActive ? 'border-orange-500 bg-orange-500/10' : 'border-slate-500/30 bg-black/5'}`}
                        onClick={() => setProjectData((prev) => ({ ...prev, hvacUpgradeActive: !prev.hvacUpgradeActive }))}
                      >
                        <div className="flex items-center gap-3">
                          <div className={`p-2 rounded-lg ${projectData.hvacUpgradeActive ? 'bg-orange-500 text-white' : 'bg-slate-600 text-slate-300'}`}>
                            <Thermometer size={18} />
                          </div>
                          <div>
                            <span className={`block font-black text-sm ${projectData.hvacUpgradeActive ? 'text-orange-500' : theme.textSub}`}>
                              설비 시스템 전면 교체 (HVAC Upgrade)
                            </span>
                            <span className="text-[10px] opacity-60">기존 냉난방 설비의 노후화로 인해 기기를 완전히 교체할 경우 체크하세요. (공사비 증가)</span>
                          </div>
                        </div>
                        {projectData.hvacUpgradeActive ? (
                          <ToggleRight size={32} className="text-orange-500" />
                        ) : (
                          <ToggleLeft size={32} className="text-slate-500" />
                        )}
                      </div>
                    </div>
              </div>
            </WizardShell>
  );
}
