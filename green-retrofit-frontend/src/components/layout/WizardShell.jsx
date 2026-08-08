import React from 'react';
import { ArrowLeft, ArrowRight } from 'lucide-react';

// --- 설정 위저드 공통 셸 (스텝별 페이지 래퍼: 헤더 + 이전/다음 네비게이션) ---
//
// ⚠️ **모듈 스코프에 있어야 한다.** 컴포넌트 안에 정의하면 매 렌더마다 새 함수가
// 되어 React 가 서브트리를 통째로 다시 마운트하고, 사용자가 입력 중이던 칸의
// 포커스가 날아간다.
function WizardShell({ theme, isDarkMode, setStep, icon, title, subtitle, back, next, nextLabel = '다음', nextDisabled = false, children }) {
  return (
    <div className="w-full h-full mx-auto px-6 pt-8 pb-28 animate-in fade-in slide-in-from-bottom-4 overflow-y-auto custom-scrollbar">
      <div className="max-w-3xl mx-auto">
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-emerald-500/10 text-emerald-500 mb-4">{icon}</div>
          <h2 className={`text-3xl font-black mb-2 tracking-tight ${theme.textMain}`}>{title}</h2>
          {subtitle && <p className={`text-sm ${theme.textSub}`}>{subtitle}</p>}
        </div>
        {children}
        <div className="mt-10 flex justify-between items-center gap-4">
          {back ? (
            <button
              onClick={() => setStep(back)}
              className={`px-6 py-3 rounded-2xl font-bold text-sm border-2 transition-all flex items-center gap-2 ${isDarkMode ? 'border-slate-700 hover:bg-slate-800 text-slate-300' : 'border-slate-300 hover:bg-slate-200 text-slate-600'}`}
            >
              <ArrowLeft size={18} /> 이전
            </button>
          ) : <span />}
          {next ? (
            <button
              onClick={() => { if (!nextDisabled) setStep(next); }}
              disabled={nextDisabled}
              className={`px-8 py-3 rounded-2xl font-black text-sm shadow-lg flex items-center gap-2 transition-all ${nextDisabled ? 'bg-slate-400/30 text-slate-500 cursor-not-allowed' : 'bg-emerald-600 hover:bg-emerald-500 text-white hover:scale-105 shadow-emerald-500/30'}`}
            >
              {nextLabel} <ArrowRight size={18} />
            </button>
          ) : <span />}
        </div>
      </div>
    </div>
  );
}

export default WizardShell;
