import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Upload, FileUp, Box, Layers, Play, CheckCircle2, ChevronRight, Eye, Calculator, ThermometerSun, Sun, Zap } from 'lucide-react';
import { cn } from '../../lib/utils';

export default function SimulationEngine({ onStart }) {
  const [currentStep, setCurrentStep] = useState('UPLOAD');
  const [isUploading, setIsUploading] = useState(false);
  const [uploadComplete, setUploadComplete] = useState(false);
  const [simulating, setSimulating] = useState(false);
  
  const handleUpload = () => {
    setIsUploading(true);
    setTimeout(() => {
      setIsUploading(false);
      setUploadComplete(true);
      setTimeout(() => setCurrentStep('VIEW'), 1000);
    }, 2000);
  };

  const startSimulation = () => {
    setSimulating(true);
    setTimeout(() => {
      setSimulating(false);
      setCurrentStep('REPORT');
    }, 3000);
  };

  return (
    <section id="시뮬레이션" className="py-24 px-6 bg-brand-deep/50 relative">
      <div className="max-w-6xl mx-auto">
        {/* Stepper Header */}
        <div className="flex items-center justify-between mb-12 glass-panel p-4 overflow-x-auto no-scrollbar">
          {[
            { id: 'UPLOAD', label: '업로드', icon: Upload },
            { id: 'VIEW', label: '3D 형상 확인', icon: Box },
            { id: 'SETTINGS', label: '환경 설정', icon: Layers },
            { id: 'REPORT', label: '분석 리포트', icon: CheckCircle2 },
          ].map((s, i, arr) => (
            <div key={s.id} className="flex items-center flex-shrink-0">
              <div 
                className={cn(
                  "flex items-center gap-3 px-6 py-3 rounded-2xl transition-all",
                  currentStep === s.id ? "bg-brand-primary/10 text-brand-primary" : "text-slate-400"
                )}
              >
                <s.icon className="w-5 h-5" />
                <span className="font-bold whitespace-nowrap">{s.label}</span>
              </div>
              {i < arr.length - 1 && <ChevronRight className="w-4 h-4 mx-2 text-slate-300" />}
            </div>
          ))}
        </div>

        {/* Step Contents */}
        <div className="min-h-[600px] flex items-center justify-center relative">
          <AnimatePresence mode="wait">
            {currentStep === 'UPLOAD' && (
              <motion.div 
                key="upload"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 1.05 }}
                className="w-full max-w-2xl px-6 py-12 md:py-24 glass-panel border-dashed border-2 border-slate-200 flex flex-col items-center justify-center gap-8 cursor-pointer hover:border-brand-primary/50 transition-colors group bg-slate-50/50"
                onClick={handleUpload}
              >
                <div className="relative">
                   <div className="absolute inset-0 bg-brand-primary/20 blur-2xl rounded-full scale-150 animate-pulse" />
                   <FileUp className="w-16 h-16 text-brand-primary relative z-10 group-hover:scale-110 transition-transform" />
                </div>
                <div className="text-center space-y-2">
                  <h3 className="text-2xl font-bold text-slate-800">gbXML 파일을 여기에 올려주세요</h3>
                  <p className="text-slate-500">Drag & Drop 또는 클릭하여 파일 선택 (Revit/ArchiCAD 추출본)</p>
                </div>
                
                {isUploading && (
                  <div className="w-full max-w-sm space-y-2">
                    <div className="h-1 bg-slate-200 rounded-full overflow-hidden">
                      <motion.div 
                        initial={{ width: 0 }}
                        animate={{ width: "100%" }}
                        transition={{ duration: 2 }}
                        className="h-full bg-brand-primary" 
                      />
                    </div>
                    <p className="text-center text-[10px] uppercase font-black tracking-widest text-brand-primary animate-pulse">Parsing geometry data...</p>
                  </div>
                )}
                
                {uploadComplete && !isUploading && (
                  <div className="flex items-center gap-2 text-brand-primary font-bold animate-bounce">
                    <CheckCircle2 className="w-5 h-5" />
                    업로드 완료! 3D 뷰로 이동합니다.
                  </div>
                )}
              </motion.div>
            )}

            {currentStep === 'VIEW' && (
              <motion.div 
                key="view"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                className="w-full grid lg:grid-cols-4 gap-8"
              >
                <div className="lg:col-span-3 glass-panel relative aspect-video flex items-center justify-center border-slate-200 overflow-hidden bg-slate-50">
                  <div className="absolute inset-0 bg-gradient-to-br from-brand-deep to-brand-primary/5" />
                  {/* Mock 3D Model visualization */}
                  <div className="relative z-10 w-full h-full flex items-center justify-center">
                    <div className="w-64 h-64 relative preserve-3d animate-[spin_20s_linear_infinite]">
                      <div className="absolute inset-0 border-2 border-brand-primary/20 bg-brand-primary/5 transform translate-z-32" />
                      <div className="absolute inset-0 border-2 border-brand-primary/20 bg-brand-primary/5 transform -translate-z-32" />
                      <div className="absolute inset-0 border-2 border-brand-primary/20 bg-brand-primary/5 transform rotate-x-90 translate-z-32" />
                      <div className="absolute inset-0 border-2 border-brand-primary/20 bg-brand-primary/5 transform rotate-x-90 -translate-z-32" />
                      <div className="absolute inset-0 border-2 border-brand-primary/20 bg-brand-primary/5 transform rotate-y-90 translate-z-32" />
                      <div className="absolute inset-0 border-2 border-brand-primary/20 bg-brand-primary/5 transform rotate-y-90 -translate-z-32" />
                    </div>
                    
                    <div className="absolute bottom-8 left-8 flex gap-4">
                      {['1F', '2F', '3F', 'ROOF'].map(f => (
                         <button key={f} className="px-4 py-2 glass-card hover:bg-brand-primary/20 transition-colors font-bold text-xs text-slate-700">{f}</button>
                      ))}
                    </div>
                    
                    <div className="absolute top-8 right-8 flex flex-col gap-2">
                       <button className="p-3 glass-card hover:bg-slate-100 text-slate-600"><Eye className="w-4 h-4" /></button>
                       <button className="p-3 glass-card hover:bg-slate-100 text-slate-600"><Layers className="w-4 h-4" /></button>
                    </div>
                  </div>
                </div>
                
                <div className="space-y-6">
                  <div className="glass-panel p-6 bg-slate-50">
                    <h4 className="font-bold mb-4 flex items-center gap-2 text-slate-800">
                       <Box className="w-4 h-4 text-brand-primary" />
                       요소 상세 데이터
                    </h4>
                    <div className="space-y-4">
                      {[
                        { label: 'Total Volume', value: '1,420 m³' },
                        { label: 'Surface Area', value: '850 m²' },
                        { label: 'Zones Found', value: '12 Spaces' },
                      ].map(item => (
                        <div key={item.label} className="flex justify-between text-sm py-2 border-b border-slate-200">
                          <span className="text-slate-500">{item.label}</span>
                          <span className="font-mono font-bold text-brand-secondary">{item.value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  
                  <button 
                    onClick={() => setCurrentStep('SETTINGS')}
                    className="w-full py-4 bg-brand-primary text-white rounded-2xl font-black flex items-center justify-center gap-2 shadow-lg shadow-brand-primary/20 hover:scale-[1.02] transition-transform"
                  >
                    다음 단계 <ChevronRight className="w-5 h-5" />
                  </button>
                </div>
              </motion.div>
            )}

            {currentStep === 'SETTINGS' && (
              <motion.div 
                key="settings"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="w-full"
              >
                <div className="grid lg:grid-cols-2 gap-8">
                  <div className="glass-panel p-8 space-y-8 bg-slate-50">
                    <h3 className="text-2xl font-bold flex items-center gap-3 text-slate-800">
                      <Layers className="w-6 h-6 text-brand-primary" />
                      스케줄 및 환경 변수
                    </h3>
                    
                    {/* Schedule Editor Mockup */}
                    <div className="space-y-6">
                      <div>
                        <div className="flex justify-between items-center mb-4">
                          <label className="text-sm font-bold text-slate-600">운영 스케줄 (24h)</label>
                          <span className="text-xs bg-brand-primary/10 text-brand-primary px-2 py-1 rounded font-bold">오피스 기본값</span>
                        </div>
                        <div className="h-32 flex items-end gap-1 px-2 border-b border-slate-200 pb-2">
                           {[...Array(24)].map((_, i) => (
                             <motion.div 
                              key={i} 
                              initial={{ height: 0 }}
                              animate={{ height: `${i > 8 && i < 18 ? 80 : 10}%` }}
                              className="flex-1 bg-gradient-to-t from-brand-primary to-brand-secondary rounded-t-sm" 
                             />
                           ))}
                        </div>
                        <div className="flex justify-between mt-2 text-[10px] text-slate-400 font-mono font-bold">
                           <span>00:00</span>
                           <span>12:00</span>
                           <span>23:59</span>
                        </div>
                      </div>
                      
                      <div className="grid grid-cols-2 gap-4">
                        <div className="p-4 bg-white rounded-xl border border-slate-200 shadow-sm">
                           <div className="flex items-center gap-2 mb-2 text-orange-500">
                             <ThermometerSun className="w-4 h-4" />
                             <span className="text-xs font-bold">난방 설정</span>
                           </div>
                           <div className="text-2xl font-mono font-bold text-slate-800">22.0°C</div>
                        </div>
                        <div className="p-4 bg-white rounded-xl border border-slate-200 shadow-sm">
                           <div className="flex items-center gap-2 mb-2 text-blue-500">
                             <Zap className="w-4 h-4" />
                             <span className="text-xs font-bold">냉방 설정</span>
                           </div>
                           <div className="text-2xl font-mono font-bold text-slate-800">26.0°C</div>
                        </div>
                      </div>
                    </div>
                  </div>

                  <div className="glass-panel p-8 flex flex-col justify-between bg-slate-50">
                    <div className="space-y-6">
                      <h4 className="font-bold flex items-center gap-2 text-slate-800">
                        <Zap className="w-4 h-4 text-brand-primary" />
                        지역 기후 데이터 매칭
                      </h4>
                      <p className="text-sm text-slate-500 leading-relaxed">
                        최적의 정밀도를 위해 대한민국 표준 기상 데이터(EPW) 중 
                        사용자 주변 관측소 데이터를 자동으로 매칭합니다.
                      </p>
                      <div className="flex items-center gap-4 p-4 bg-brand-primary/5 rounded-xl border border-brand-primary/10">
                        <div className="w-10 h-10 rounded-full bg-brand-primary/20 flex items-center justify-center text-brand-primary">
                           <Sun className="w-5 h-5" />
                        </div>
                        <div>
                          <p className="text-xs font-bold text-slate-400 uppercase">Detected Location</p>
                          <p className="font-bold text-slate-800">대한민국 세종특별자치시</p>
                        </div>
                      </div>
                    </div>
                    
                    <button 
                      onClick={startSimulation}
                      disabled={simulating}
                      className="mt-8 py-5 bg-gradient-to-r from-brand-primary to-brand-secondary text-white rounded-full font-black text-xl flex items-center justify-center gap-4 transition-all hover:scale-[1.02] disabled:opacity-50 shadow-lg shadow-brand-primary/20"
                    >
                      {simulating ? (
                        <>
                          <div className="w-6 h-6 border-4 border-white/30 border-t-white rounded-full animate-spin" />
                          Building LCA Report...
                        </>
                      ) : (
                        <>
                          시뮬레이션 가동 <Play className="w-6 h-6 fill-white" />
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </motion.div>
            )}

            {currentStep === 'REPORT' && (
              <motion.div 
                key="report"
                initial={{ opacity: 0, scale: 1.05 }}
                animate={{ opacity: 1, scale: 1 }}
                className="w-full space-y-8"
              >
                <div className="flex flex-col md:flex-row gap-6 items-start justify-between">
                  <h3 className="text-4xl font-display font-black leading-tight text-slate-900">
                    에너지 성능 및 <br />
                    <span className="text-brand-primary">LCC 경제성 분석 리포트</span>
                  </h3>
                </div>

                <div className="grid md:grid-cols-3 gap-6">
                  {[
                    { label: '연간 에너지 소요량', value: '142.5', unit: 'kWh/m²·y', icon: Zap, color: 'text-brand-primary' },
                    { label: 'CO₂ 배출량 절감', value: '28.4', unit: 'ton/y', icon: Sun, color: 'text-orange-400' },
                    { label: '예상 투자 회수 기간', value: '12.5', unit: 'Years', icon: Calculator, color: 'text-brand-secondary' },
                  ].map((stat, i) => (
                    <motion.div 
                      key={i}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.1 }}
                      className="glass-panel p-8 relative overflow-hidden group bg-white"
                    >
                      <stat.icon className={cn("absolute -right-4 -bottom-4 w-32 h-32 opacity-[0.03] transition-transform group-hover:scale-110", stat.color)} />
                      <p className="text-slate-500 text-sm font-bold mb-4">{stat.label}</p>
                      <div className="flex items-baseline gap-2">
                        <span className="text-5xl font-display font-black text-slate-800">{stat.value}</span>
                        <span className="text-xs text-slate-400 font-bold uppercase">{stat.unit}</span>
                      </div>
                    </motion.div>
                  ))}
                </div>

                <div className="grid lg:grid-cols-2 gap-6">
                  <div className="glass-panel p-8 bg-white">
                     <h4 className="font-bold mb-6 flex items-center gap-2 text-slate-800">월별 에너지 사용량 추이</h4>
                     <div className="h-64 flex items-end gap-3 px-4">
                        {[40, 35, 30, 22, 18, 15, 25, 28, 20, 24, 32, 45].map((val, i) => (
                          <div key={i} className="flex-1 flex flex-col items-center gap-2">
                            <motion.div 
                              initial={{ height: 0 }}
                              animate={{ height: `${val}%` }}
                              className="w-full bg-slate-200 hover:bg-brand-primary transition-colors rounded-t-sm"
                            />
                            <span className="text-[10px] text-slate-400 font-mono font-bold">{i+1}월</span>
                          </div>
                        ))}
                     </div>
                  </div>

                  <div className="glass-panel p-8 bg-white">
                    <h4 className="font-bold mb-6 flex items-center gap-2 text-slate-800">경제성 (LCC) 분석 상세</h4>
                    <div className="space-y-6">
                      <div className="flex justify-between items-center p-4 bg-slate-50 border border-slate-100 rounded-xl">
                        <div>
                          <p className="text-xs text-slate-500 mb-1">총 공사비 (자산 가치 증가분 포함)</p>
                          <p className="text-xl font-bold text-slate-800">₩ 2,450,000,000</p>
                        </div>
                        <div className="text-right">
                          <p className="text-xs text-brand-primary font-bold">+15% Efficiency</p>
                        </div>
                      </div>
                      
                      <div className="space-y-4">
                         {[
                           { label: '연간 에너지 요금 절감액', value: '₩ 14,200,000' },
                           { label: '정부 보조금 혜택 (그린리모델링)', value: '₩ 8,500,000' },
                           { label: '탄소 배출권 기대 수익', value: '₩ 2,100,000' },
                         ].map(item => (
                           <div key={item.label} className="flex justify-between text-sm py-2 border-b border-slate-100">
                             <span className="text-slate-500">{item.label}</span>
                             <span className="font-bold text-slate-700">{item.value}</span>
                           </div>
                         ))}
                      </div>
                    </div>
                  </div>
                </div>
                
                <div className="flex justify-center pt-8">
                   <button 
                    onClick={onStart}
                    className="px-12 py-5 bg-slate-900 text-white rounded-full font-black text-lg hover:bg-brand-primary transition-all shadow-xl shadow-slate-900/20"
                   >
                     실제 데이터로 분석 시작하기
                   </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </section>
  );
}
