import React from 'react';
import { motion } from 'framer-motion';
import { BookOpen, AlertCircle, Building2, Layout, Sliders, BarChart3 } from 'lucide-react';

export default function Manual({ onStart }) {
  return (
    <section id="가이드" className="py-24 px-6 bg-white relative overflow-hidden">
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-col md:flex-row items-end justify-between mb-16 gap-6">
          <div className="max-w-2xl">
            <h2 className="text-4xl md:text-5xl font-display font-black mb-6 text-slate-900">
              ZeroBase <span className="text-brand-primary">사용자 매뉴얼</span>
            </h2>
            <p className="text-slate-500 text-lg">
              환영합니다! BIM 모델 데이터를 기반으로 클릭 몇 번만에 
              빠르고 직관적인 건물 에너지 성능 분석을 제공합니다.
            </p>
          </div>
          <div className="flex items-center gap-2 px-4 py-2 bg-brand-primary/10 border border-brand-primary/20 rounded-lg text-brand-primary font-bold text-sm">
            <BookOpen className="w-4 h-4" />
            Decision Solution Guide
          </div>
        </div>

        {/* Essential Check Section */}
        <div className="glass-panel p-8 md:p-12 mb-20 border-slate-100 bg-slate-50/50">
          <div className="flex items-center gap-4 mb-8">
            <div className="w-12 h-12 rounded-2xl bg-brand-primary/10 flex items-center justify-center">
              <AlertCircle className="w-6 h-6 text-brand-primary" />
            </div>
            <div>
              <h3 className="text-2xl font-display font-bold text-slate-900">시작 전 필수 확인 사항</h3>
              <p className="text-slate-500 text-sm">정확한 분석을 위해 gbXML 데이터를 준비해주세요.</p>
            </div>
          </div>

          <div className="grid md:grid-cols-2 gap-12">
            <div className="space-y-6">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-white flex items-center justify-center font-bold text-xs text-brand-primary border border-slate-200">A</div>
                <h4 className="font-bold text-lg text-slate-800">Autodesk Revit 추출 가이드</h4>
              </div>
              <ul className="space-y-4 text-sm text-slate-500">
                <li className="flex gap-3">
                  <span className="text-brand-primary font-bold">01</span>
                  <span>[해석] 탭에서 [에너지 모델 생성] 버튼으로 분석용 모델 작성</span>
                </li>
                <li className="flex gap-3">
                  <span className="text-brand-primary font-bold">02</span>
                  <span>[파일] {'>'} [내보내기] {'>'} [gbXML] 선택</span>
                </li>
                <li className="flex gap-3">
                  <span className="text-brand-primary font-bold">03</span>
                  <span className="text-slate-900 font-semibold">"에너지 설정 사용(Use Energy Settings)" 옵션 필수 선택</span>
                </li>
              </ul>
              
              <div className="mt-8 relative group">
                <div className="absolute -inset-1 bg-gradient-to-r from-brand-primary to-brand-secondary rounded-2xl blur opacity-25 group-hover:opacity-40 transition duration-1000 group-hover:duration-200"></div>
                <video 
                  src="/gbXML_manual.mp4" 
                  autoPlay 
                  loop 
                  muted 
                  playsInline 
                  className="relative w-full rounded-xl shadow-2xl border border-slate-200/50"
                />
              </div>
            </div>

            <div className="space-y-6">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-white flex items-center justify-center font-bold text-xs text-brand-secondary border border-slate-200">B</div>
                <h4 className="font-bold text-lg text-slate-800">Graphisoft ArchiCAD 추출 가이드</h4>
              </div>
              <ul className="space-y-4 text-sm text-slate-500">
                <li className="flex gap-3">
                  <span className="text-brand-secondary font-bold">01</span>
                  <span>[디자인] {'>'} [에너지 평가] 에서 열 블록(Thermal Blocks) 구성</span>
                </li>
                <li className="flex gap-3">
                  <span className="text-brand-secondary font-bold">02</span>
                  <span>내보내기 형식 중 "gbXML" 선택하여 저장</span>
                </li>
              </ul>
            </div>
          </div>
        </div>

        {/* 4 Steps Process */}
        <div className="mb-20 text-center">
          <h3 className="text-3xl font-display font-black mb-12 text-slate-900 italic">4단계 분석 프로세스</h3>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6 text-left">
            {[
              { 
                step: "01", 
                title: "프로젝트 업로드", 
                icon: Building2, 
                desc: "gbXML 파일을 드래그 앤 드롭하여 3D 형상을 구축합니다.",
                color: "brand-primary"
              },
              { 
                step: "02", 
                title: "3D 형상 상세편집", 
                icon: Layout, 
                desc: "층별로 구역(Zone) 및 외피(Surface) 스펙을 변경합니다.",
                color: "brand-secondary"
              },
              { 
                step: "03", 
                title: "환경 및 스케줄 설정", 
                icon: Sliders, 
                desc: "24시간 차트를 통해 정교하게 냉난방 스케줄을 커스텀합니다.",
                color: "slate-400"
              },
              { 
                step: "04", 
                title: "시뮬레이션 & 리포트", 
                icon: BarChart3, 
                desc: "EnergyPlus 엔진이 분석한 LCA & 경제성 결과를 확인합니다.",
                color: "brand-primary"
              }
            ].map((s, idx) => (
              <motion.div 
                key={idx}
                whileHover={{ y: -5 }}
                className="glass-card p-6 border-slate-100 flex flex-col gap-4 group"
              >
                <div className={`w-12 h-12 rounded-xl bg-slate-50 flex items-center justify-center transition-colors group-hover:bg-brand-primary/10`}>
                  <s.icon className={`w-6 h-6 text-slate-400 group-hover:text-brand-primary`} />
                </div>
                <div>
                  <span className="text-brand-primary text-[10px] font-black tracking-widest uppercase text-brand-primary">Step {s.step}</span>
                  <h4 className="font-bold mb-2 text-slate-800 group-hover:text-brand-primary transition-colors">{s.title}</h4>
                  <p className="text-xs text-slate-500 leading-relaxed">{s.desc}</p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>

        {/* CTA */}
        <div className="flex flex-col items-center justify-center p-12 bg-gradient-to-br from-brand-primary/5 to-brand-secondary/5 rounded-[3rem] border border-slate-100 shadow-sm">
          <p className="text-xl font-medium mb-8 text-slate-700">준비가 완료되었나요? 지금 분석을 시작하세요.</p>
          <button 
            onClick={onStart}
            className="px-10 py-5 bg-slate-900 text-white rounded-full font-black text-lg hover:bg-brand-primary transition-all shadow-lg shadow-slate-200"
          >
            시뮬레이션 시작하기
          </button>
        </div>
      </div>
    </section>
  );
}
