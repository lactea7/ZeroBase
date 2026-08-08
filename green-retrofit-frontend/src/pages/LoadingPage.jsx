import React from 'react';
import { LOADING_MESSAGES } from '../utils/format';
import { stageMessage } from '../utils/loadingStage';

/**
 * 시뮬레이션 진행 화면.
 *
 * ⚠️ 사용자가 여기서 **최대 30분**을 기다린다. 진행 단계 문구는
 * `utils/loadingStage.js` 가 만든다 — 그 규칙은 순수 함수라 따로 시험한다.
 */
export default function LoadingPage({ theme, loadingMsgIdx, loadingStage }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center animate-in fade-in h-full">
      <h2 className={`text-4xl font-black mb-4 tracking-tighter uppercase text-center ${theme.textMain}`}>
        {LOADING_MESSAGES[loadingMsgIdx]}
      </h2>
      {/* 백엔드가 알려주는 실제 진행 단계 */}
      <p className={`text-sm font-bold mb-10 ${theme.textSub}`}>
        {stageMessage(loadingStage)}
      </p>
      <div className="relative flex justify-center items-center h-24">
        <div className="loading-wrapper">
          <div className="loading-circle"></div>
          <div className="loading-circle"></div>
          <div className="loading-circle"></div>
          <div className="loading-shadow"></div>
          <div className="loading-shadow"></div>
          <div className="loading-shadow"></div>
        </div>
      </div>
    </div>
  );
}
