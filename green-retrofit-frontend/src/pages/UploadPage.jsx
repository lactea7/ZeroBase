import React from 'react';
// ⚠️ 블록을 옮길 때 **아이콘 import 를 빠뜨리기 쉽다.** 빌드는 통과하고
// 런타임에만 죽어 화면이 백지가 된다 — 예전에 실제로 그렇게 됐다.
import { AnimatePresence, motion } from 'framer-motion';
import { CheckCircle2, PlayCircle, UploadCloud, X } from 'lucide-react';
import WizardShell from '../components/layout/WizardShell';

/**
 * gbXML 업로드 화면.
 *
 * ⚠️ 재업로드는 `onResetModel` **하나**로 처리한다. 예전엔 setter 5개를 나열해서
 * `originalModel`(절감액의 기준선)·`gapWarnings`·`realFloorCount` 를 빠뜨렸다.
 *
 * ⚠️ 여기서 막히면 사용자는 **아무것도 시작할 수 없다.** 파일 입력·샘플 시작·
 * 재업로드 세 경로가 모두 살아 있어야 한다.
 * 화면 간 계약은 `src/__tests__/App.upload.test.jsx` 가 지킨다.
 */
export default function UploadPage({
  theme, isDarkMode, setStep,
  surfaces, zones, uploadedFile, fileInputRef,
  handleFileUpload, handleStartWithSample,
  onResetModel,
}) {
  // ⚠️ **이 화면만 여는 모달이다.** App 에 두면 다른 화면이 소유하지도 않는
  // 상태를 들고 다닌다(여는 곳도 여기, 닫는 곳도 여기).
  const [showGuide, setShowGuide] = React.useState(false);

  return (
    <>
            <WizardShell
              theme={theme} isDarkMode={isDarkMode} setStep={setStep}
              icon={<UploadCloud size={32} />}
              title="gbXML 모델 업로드"
              subtitle="분석할 BIM 모델 파일을 올리거나, 샘플 건물로 바로 시작하세요."
              next="projectInfo"
              nextDisabled={surfaces.length === 0}
            >
                <div className="flex flex-col gap-4">
                  {!uploadedFile || surfaces.length === 0 ? (
                    <>
                      <div
                        onClick={() => fileInputRef.current?.click()}
                        className={`flex-1 min-h-[300px] p-12 rounded-[2rem] border-2 border-dashed ${isDarkMode ? 'border-slate-700 hover:border-emerald-500' : 'border-slate-300 hover:border-emerald-500'} flex flex-col items-center justify-center cursor-pointer transition-all hover:bg-emerald-500/5 group ${theme.card}`}
                      >
                        <UploadCloud size={60} className="text-emerald-500 mb-6 group-hover:scale-110 transition-transform" />
                        <h3 className="text-2xl font-black mb-2">gbXML 모델 업로드</h3>
                        <p className={`text-sm text-center ${theme.textSub}`}>클릭하여 파일을 선택하세요 (.xml / .gbxml)</p>
                        <input
                          type="file"
                          accept=".xml,.gbxml"
                          ref={fileInputRef}
                          className="hidden"
                          onChange={handleFileUpload}
                        />
                      </div>
                      <div className="flex items-center gap-4 my-1">
                        <div className="flex-1 h-px bg-current opacity-10"></div>
                        <span className="text-[10px] font-bold opacity-50 uppercase tracking-widest">OR</span>
                        <div className="flex-1 h-px bg-current opacity-10"></div>
                      </div>
                      <button
                        onClick={handleStartWithSample}
                        className={`w-full py-5 rounded-[1.5rem] font-black text-sm border-2 transition-all active:scale-95 ${isDarkMode ? 'border-slate-700 hover:bg-slate-800 text-slate-300' : 'border-slate-300 hover:bg-slate-200 text-slate-600'}`}
                      >
                        샘플 3층 상업용 건물로 바로 시작하기
                      </button>
                      <button
                        onClick={() => setShowGuide(true)}
                        className="mt-1 inline-flex items-center justify-center gap-2 self-center text-sm font-bold text-emerald-600 hover:text-emerald-500 transition-colors"
                      >
                        <PlayCircle size={18} /> Revit에서 gbXML 추출하는 법 보기
                      </button>
                    </>
                  ) : (
                    <div className={`flex-1 min-h-[300px] p-12 rounded-[2rem] border-2 border-emerald-500 ${isDarkMode ? 'bg-emerald-500/10' : 'bg-emerald-50'} flex flex-col items-center justify-center transition-all animate-in zoom-in-95`}>
                      <CheckCircle2 size={60} className="text-emerald-500 mb-6 animate-pulse" />
                      <h3 className="text-2xl font-black mb-2 text-emerald-500">모델 파싱 완료!</h3>
                      <p className={`text-sm text-center font-bold ${theme.textMain} max-w-[250px] truncate`}>
                        {uploadedFile.name}
                      </p>
                      <div className="flex gap-4 mt-6 text-sm">
                        <span className={`px-4 py-2 rounded-xl ${isDarkMode ? 'bg-black/20' : 'bg-white/50'} text-emerald-500 font-bold border border-emerald-500/20`}>
                          면(Surface): {surfaces.length}개
                        </span>
                        <span className={`px-4 py-2 rounded-xl ${isDarkMode ? 'bg-black/20' : 'bg-white/50'} text-blue-500 font-bold border border-blue-500/20`}>
                          존(Zone): {zones.length}개
                        </span>
                      </div>
                      <button
                        onClick={onResetModel}
                        className={`mt-8 text-xs font-bold transition-colors underline ${isDarkMode ? 'text-slate-500 hover:text-red-400' : 'text-slate-400 hover:text-red-500'}`}
                      >
                        다른 파일 다시 업로드하기
                      </button>
                    </div>
                  )}
                </div>
            </WizardShell>

      {/* Revit gbXML 추출 가이드 영상 모달 */}
      <AnimatePresence>
        {showGuide && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setShowGuide(false)}></div>
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 20 }}
              className={`relative w-full max-w-3xl rounded-[2rem] shadow-2xl overflow-hidden border ${isDarkMode ? 'bg-[#241a13] border-[#3a2c20]' : 'bg-[#fbf7f0] border-[#d8cbb5]'}`}
            >
              <div className="flex items-center justify-between px-6 py-4">
                <h3 className={`text-base font-black flex items-center gap-2 ${theme.textMain}`}>
                  <PlayCircle size={18} className="text-emerald-600" /> Revit에서 gbXML 추출하기
                </h3>
                <button
                  onClick={() => setShowGuide(false)}
                  className={`p-2 rounded-full transition-colors ${isDarkMode ? 'hover:bg-white/10' : 'hover:bg-black/5'}`}
                >
                  <X size={20} className={theme.textSub} />
                </button>
              </div>
              <video
                src="/gbXML_manual.mp4"
                controls
                autoPlay
                playsInline
                className="w-full max-h-[70vh] bg-black"
              />
              <p className={`px-6 py-4 text-xs leading-relaxed ${theme.textSub}`}>
                Revit · File → Export → gbXML 로 내보낸 .xml 파일을 업로드 화면에 올리면 됩니다.
              </p>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
}
