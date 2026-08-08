import React from 'react';
// ⚠️ 아이콘 import 를 빠뜨리면 빌드는 통과하고 **런타임에 백지 화면**이 된다.
import { Building, Clock, MapPin, ToggleLeft, ToggleRight } from 'lucide-react';
import WizardShell from '../components/layout/WizardShell';
import ScheduleEditor from '../components/ScheduleEditor';
import { ACTIVITIES, KOREA_REGIONS } from '../data/constants';

/**
 * 프로젝트 기본 정보 — 용도·지역·연면적 등.
 *
 * ⚠️ 여기 입력이 **용도별 아키타입과 기상 파일을 정한다.** 지역이 틀리면 결과가
 * 통째로 달라진다(기상 파일이 바뀐다).
 */
export default function ProjectInfoPage({
  theme, isDarkMode, setStep, projectData, setProjectData, scheduleEditorRef,
}) {
  return (
            <WizardShell
              theme={theme} isDarkMode={isDarkMode} setStep={setStep}
              icon={<Building size={32} />}
              title="프로젝트 기본 정보"
              subtitle="건물 이름·용도·기상 지역·정북 방향을 설정하세요."
              back="upload" next="renewable"
            >
              <div className={`p-8 rounded-[2rem] border ${theme.card}`}>
                    <div className="space-y-4">
                      <div>
                        <label className={`block text-[10px] font-black uppercase tracking-widest mb-2 ${theme.textSub}`}>Project Name</label>
                        <input
                          type="text"
                          value={projectData.name}
                          onChange={(e) => setProjectData({ ...projectData, name: e.target.value })}
                          className={`w-full p-4 rounded-2xl outline-none border ${theme.input} focus:border-emerald-500`}
                        />
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className={`block text-[10px] font-black uppercase tracking-widest mb-2 ${theme.textSub}`}>건물 기본 용도</label>
                          <select
                            value={projectData.activityId}
                            onChange={(e) => setProjectData({ ...projectData, activityId: parseInt(e.target.value) })}
                            className={`w-full p-4 rounded-2xl outline-none border appearance-none ${theme.input} focus:border-emerald-500`}
                          >
                            {ACTIVITIES.map((act) => (
                              <option key={act.id} value={act.id}>
                                {act.name}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className={`block text-[10px] font-black uppercase tracking-widest mb-2 ${theme.textSub}`}>기상 데이터 지역 (Location)</label>
                          <div className="relative">
                            <select
                              value={projectData.location}
                              onChange={(e) => setProjectData({ ...projectData, location: e.target.value })}
                              className={`w-full p-4 pl-10 rounded-2xl outline-none border appearance-none ${theme.input} focus:border-emerald-500`}
                            >
                              {KOREA_REGIONS.map((group) => (
                                <optgroup key={group.group} label={group.group}>
                                  {group.options.map((opt) => (
                                    <option key={opt.id} value={opt.id}>
                                      {opt.name}
                                    </option>
                                  ))}
                                </optgroup>
                              ))}
                            </select>
                            <MapPin size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-emerald-500" />
                          </div>
                        </div>
                      </div>
                      <div
                        className={`mt-4 p-4 rounded-xl flex items-center justify-between cursor-pointer border-2 transition-all ${projectData.customSchedule.useCustom ? 'border-indigo-500 bg-indigo-500/10' : 'border-slate-500/30 bg-black/5'}`}
                        onClick={() => {
                          const turningOn = !projectData.customSchedule.useCustom;
                          setProjectData((prev) => ({ ...prev, customSchedule: { ...prev.customSchedule, useCustom: turningOn } }));
                          // 켜질 때 인라인 편집기로 부드럽게 스크롤
                          if (turningOn) {
                            setTimeout(() => scheduleEditorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 120);
                          }
                        }}
                      >
                        <div className="flex items-center gap-3">
                          <div className={`p-2 rounded-lg ${projectData.customSchedule.useCustom ? 'bg-indigo-500 text-white' : 'bg-slate-600 text-slate-300'}`}>
                            <Clock size={18} />
                          </div>
                          <div>
                            <span className={`block font-black text-sm ${projectData.customSchedule.useCustom ? 'text-indigo-500' : theme.textSub}`}>
                              사용자 스케줄 적용
                            </span>
                            <span className="text-[10px] opacity-60">용도별 스케줄 대신 직접 수정합니다. (켜면 아래에서 바로 편집)</span>
                          </div>
                        </div>
                        {projectData.customSchedule.useCustom ? (
                          <ToggleRight size={32} className="text-indigo-500" />
                        ) : (
                          <ToggleLeft size={32} className="text-slate-500" />
                        )}
                      </div>

                      {/* 사용자 스케줄 인라인 편집기 — 토글 ON 시 펼쳐지며 스크롤 */}
                      {projectData.customSchedule.useCustom && (
                        <div
                          ref={scheduleEditorRef}
                          className="mt-2 p-5 rounded-2xl border-2 border-indigo-500/30 bg-indigo-500/5 animate-in fade-in slide-in-from-top-2 duration-300"
                        >
                          <ScheduleEditor
                            value={projectData.customSchedule}
                            onChange={(newSchedule) => setProjectData({ ...projectData, customSchedule: newSchedule })}
                          />
                        </div>
                      )}
                    </div>
              </div>
            </WizardShell>
  );
}
