import React from 'react';
// ⚠️ 아이콘 import 를 빠뜨리면 빌드는 통과하고 **런타임에 백지 화면**이 된다.
import { Building } from 'lucide-react';
import BuildingViewer from '../components/viewer/BuildingViewer';

/**
 * 전체 건물 3D 화면 + 층 선택.
 *
 * ⚠️ **3D 뷰어만 있는 화면이 아니다.** 층 버튼이 유일한 상세 편집 진입점이라,
 * 여기가 깨지면 사용자는 평면도 편집으로 갈 수 없다.
 * 시험에서는 `BuildingViewer` 를 mock 하고 **네비게이션과 배선**을 지킨다 —
 * 실제 WebGL 렌더는 브라우저에서 확인할 몫이다.
 */
export default function BuildingViewPage({
  isDarkMode, setStep, surfaces, zones, displayFloors, isVirtualFloor, setActiveFloor, setSelectedId, viewMode, setViewMode, sunMonth, setSunMonth, sunHour, setSunHour, res, latitude, selectedRegion,
}) {
  return (
            <div className="flex-1 flex flex-col animate-in fade-in min-h-0 w-full h-full">
              <div className="p-6 border-b flex-shrink-0 flex flex-col md:flex-row md:justify-between items-start md:items-center bg-black/5 z-10 shadow-sm gap-4">
                <div className="flex-shrink-0">
                  <h2 className="text-xl font-black flex items-center gap-2">
                    <Building className="text-emerald-500" /> 전체 건물 형상 시각화
                  </h2>
                  <p className="text-xs opacity-60 mt-1">층별 버튼을 눌러 상세 편집 모드로 진입하세요.</p>
                </div>
                <div className="flex flex-wrap gap-2 justify-start md:justify-end w-full md:max-w-[70%] max-h-[120px] overflow-y-auto custom-scrollbar pr-2">
                  {displayFloors.map((f) => (
                    <button
                      key={f}
                      onClick={() => {
                        setActiveFloor(f);
                        setStep('floorView');
                        setSelectedId(null);
                      }}
                      className={`px-4 py-2 rounded-xl text-white font-black hover:opacity-90 transition-all shadow-md min-w-[3.5rem] flex flex-col items-center gap-0.5 ${
                        isVirtualFloor(f)
                          ? 'bg-amber-600 hover:bg-amber-500'
                          : 'bg-emerald-600 hover:bg-emerald-500'
                      }`}
                    >
                      <span>{isVirtualFloor(f) ? '⚡' : ''}{f}F</span>
                      {isVirtualFloor(f) && <span className="text-[9px] font-medium opacity-80 leading-none">특수공간</span>}
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex-1 relative flex flex-col md:flex-row overflow-hidden w-full h-full gap-4 p-4">
                {/* 3D 모델 시각화 영역 */}
                <div className="flex-1 relative min-h-[400px]">
                  <BuildingViewer
                    surfaces={surfaces}
                    zones={zones}
                    activeFloor="all"
                    editMode="surface"
                    onSurfaceClick={() => {}}
                    onZoneClick={() => {}}
                    isDarkMode={isDarkMode}
                    viewMode={viewMode}
                    setViewMode={setViewMode}
                    sunMonth={sunMonth}
                    setSunMonth={setSunMonth}
                    sunHour={sunHour}
                    setSunHour={setSunHour}
                    res={res}
                    latitude={latitude}
                    locationName={selectedRegion.name}
                  />
                </div>


              </div>
            </div>
  );
}
