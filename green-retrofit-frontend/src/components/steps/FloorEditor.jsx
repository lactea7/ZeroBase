import React from 'react';
import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import {
  Activity, Box as BoxIcon, Calculator, ChevronLeft, Clock, FileText, Flame,
  HardHat, Info, Layers, Lightbulb, List, Monitor, Save, Settings2,
  SlidersHorizontal, Thermometer, ToggleLeft, ToggleRight, Users, Wind, X,
} from 'lucide-react';

import { ACTIVITIES, ACTIVITIES_UNIQUE, OUTLET_W_PER_ACTIVITY } from '../../data/constants';
import { INSULATION_TYPES, INSULATION_CATEGORIES, getLayerColor } from '../../data/insulation';
import { STRUCTURAL_MATERIALS, getMaterialsByCategory } from '../../data/structuralMaterials';
import { HVAC_SYSTEMS, FUEL_TYPES, VENT_TYPES } from '../../data/hvac';
import { DIR_MAP, groupBy } from '../../utils/format';
import { getSurfaceGroupName, getZoneGroupName } from '../../utils/surface';
import BuildingViewer from '../viewer/BuildingViewer';

// App.jsx에서 분리된 STEP 3 & 4: 평면도 뷰 + 우측 속성 편집 패널 (존/표면/단열 튜닝)
export default function FloorEditor(props) {
  const {
    // 상태
    theme, isDarkMode, projectData, res, surfaces, zones, materials,
    constructionOverrides, editState, setEditState, editMode, selectedId,
    setSelectedId, hoveredId, setHoveredId, activeFloor, setActiveFloor,
    viewMode, setViewMode, sunMonth, setSunMonth, sunHour, setSunHour,
    latitude, selectedRegion, lightCalc, setLightCalc, equipCalc, setEquipCalc,
    setStep,
    // 계산된 파생값 (App에서 전달)
    displayFloors, selectedSurfaceData, currentPanes, currentType, currentGlazing,
    availableTypes, filteredGlazingList, inactiveBtnClass,
    // 핸들러 / 헬퍼
    handleConstructionOverrideChange, handleResetInsulationOverride,
    handleZoneClick, handleSurfaceClick, handleSaveClose, handleModeSwitch,
    handleTypeChange, handlePanesChange, handleSimulation,
    getZoneFloorArea, calcOutletPower, isVirtualFloor, getActivityCategory,
    calculateUpdatedUValue, applyToSimilarZones, setApplyToSimilarZones,
  } = props;

  // 편집 중인 존과 같은 용도(activityId)의 다른 존 — 화장실·계단실처럼 여러 존이
  // 거의 동일한 설정을 갖는 경우, 하나씩 편집하지 않도록 일괄 적용을 제안한다.
  const similarZoneCount = editMode === 'zone' && editState.activityId != null
    ? zones.filter((z) => z.activityId === editState.activityId && z.id !== selectedId).length
    : 0;
  const activityLabel = ACTIVITIES.find((a) => a.id === editState.activityId)?.name || '이 용도';
  // 드롭다운은 이름 중복 제거본을 쓰되, 이전에 저장된 존이 제거된 쪽 id(예: 1121)를
  // 이미 갖고 있으면 선택값이 빈칸처럼 보이지 않도록 그 항목만 예외로 포함시킨다.
  const activityOptions = ACTIVITIES_UNIQUE.some((a) => a.id === editState.activityId)
    ? ACTIVITIES_UNIQUE
    : [...ACTIVITIES_UNIQUE, ACTIVITIES.find((a) => a.id === editState.activityId)].filter(Boolean);

  return (
            <div className="flex-1 flex flex-col animate-in fade-in min-h-0 w-full h-full">
              <div className="flex-shrink-0 p-4 border-b flex flex-col md:flex-row justify-between items-start md:items-center gap-4 bg-black/5 z-10 shadow-sm">
                <div className="flex items-center gap-4">
                  <button
                    onClick={() => {
                      setStep('buildingView');
                      handleSaveClose();
                    }}
                    className="p-2 rounded-full hover:bg-slate-500/10 transition-colors"
                  >
                    <ChevronLeft />
                  </button>
                  <div className="flex items-center gap-4">
                    <h2 className="text-xl font-black flex items-center gap-2">
                      <HardHat className="text-emerald-500" /> 층간 빠른 이동
                    </h2>
                    <div className={`flex p-1.5 rounded-xl border shadow-inner ${isDarkMode ? 'bg-black/20 border-white/5' : 'bg-slate-300/60 border-slate-400/30'}`}>
                      {displayFloors.map((f) => (
                        <button
                          key={f}
                          onClick={() => {
                            setActiveFloor(f);
                            handleSaveClose();
                            setSelectedId(null);
                            setHoveredId(null);
                          }}
                          className={`px-4 py-1.5 text-sm font-black rounded-lg transition-all flex flex-col items-center ${
                            activeFloor === f
                              ? isVirtualFloor(f)
                                ? 'bg-amber-500 text-white shadow-[0_0_15px_rgba(245,158,11,0.5)]'
                                : 'bg-emerald-500 text-white shadow-[0_0_15px_rgba(16,185,129,0.5)]'
                              : isDarkMode
                                ? 'text-slate-400 hover:text-white hover:bg-white/10'
                                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/80'
                          }`}
                        >
                          <span>{isVirtualFloor(f) ? '⚡' : ''}{f}F</span>
                          {isVirtualFloor(f) && <span className="text-[8px] font-medium opacity-75 leading-none">특수</span>}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
                <div className={`flex w-full md:w-auto p-1 rounded-xl border ${isDarkMode ? 'bg-slate-900 border-slate-700' : 'bg-slate-200 border-slate-300'}`}>
                  <button
                    onClick={() => handleModeSwitch('zone')}
                    className={`flex-1 md:flex-none px-4 md:px-6 py-2 rounded-lg font-black text-xs md:text-sm flex items-center justify-center gap-2 transition-all ${
                      editMode === 'zone' ? 'bg-emerald-500 text-white shadow-md' : 'text-slate-500 hover:text-slate-300'
                    }`}
                  >
                    <BoxIcon size={16} /> 구역(Zone)
                  </button>
                  <button
                    onClick={() => handleModeSwitch('surface')}
                    className={`flex-1 md:flex-none px-4 md:px-6 py-2 rounded-lg font-black text-xs md:text-sm flex items-center justify-center gap-2 transition-all ${
                      editMode === 'surface' ? 'bg-blue-500 text-white shadow-md' : 'text-slate-500 hover:text-slate-300'
                    }`}
                  >
                    <Layers size={16} /> 외피(Surface)
                  </button>
                </div>
                <button
                  onClick={handleSimulation}
                  className="w-full md:w-auto px-8 py-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-full font-black shadow-xl shadow-emerald-500/30 flex justify-center items-center gap-2 transition-transform hover:scale-105"
                >
                  <Settings2 size={20} /> 시뮬레이션 가동
                </button>
              </div>

              <div className="flex-1 relative flex flex-col-reverse md:flex-row overflow-hidden w-full h-full">
                <div
                  className={`w-full md:w-[320px] flex-shrink-0 h-1/2 md:h-full overflow-y-auto border-t md:border-t-0 md:border-r z-20 shadow-[0_-5px_20px_rgba(0,0,0,0.05)] md:shadow-[10px_0_30px_rgba(0,0,0,0.05)] flex flex-col ${
                    isDarkMode ? 'bg-[#0F172A]/95 border-slate-700' : 'bg-[#F8FAFC]/95 border-slate-300'
                  }`}
                >
                  <div
                    className={`p-6 border-b sticky top-0 backdrop-blur-xl z-10 flex justify-between items-center ${
                      isDarkMode ? 'border-slate-700 bg-[#0F172A]/90' : 'border-slate-300 bg-[#F8FAFC]/90'
                    }`}
                  >
                    <div>
                      <h2 className="text-xl font-black flex items-center gap-2">
                        {editMode === 'zone' ? (
                          <>
                            <Users size={22} className="text-emerald-500" /> 공간 용도 현황
                          </>
                        ) : (
                          <>
                            <List size={22} className="text-blue-500" /> 외피 단열 현황
                          </>
                        )}
                      </h2>
                      <p
                        className={`text-[10px] opacity-60 mt-1 uppercase tracking-widest ${
                          editMode === 'zone' ? 'text-emerald-500' : 'text-blue-500'
                        }`}
                      >
                        {editMode === 'zone' ? 'Thermal Zone Inventory' : 'Surface Inventory'}
                      </p>
                    </div>
                  </div>
                  <div className="p-4 pb-32 custom-scrollbar">
                    {editMode === 'zone' &&
                      Object.entries(
                        groupBy(
                          zones.filter((z) => (z.floor || 1) === parseInt(activeFloor)),
                          getZoneGroupName
                        )
                      ).map(([groupName, groupZones]) => (
                        <div key={groupName} className="mb-6">
                          <h3 className="text-[11px] font-black text-emerald-500 uppercase tracking-widest mb-3 flex items-center gap-2 border-b border-emerald-500/20 pb-2">
                            <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>
                            {groupName} <span className="opacity-50 text-slate-400">({groupZones.length})</span>
                          </h3>
                          <div className="space-y-3">
                            {groupZones.map((zone) => (
                              <div
                                key={zone.id}
                                onMouseEnter={() => setHoveredId(zone.id)}
                                onMouseLeave={() => setHoveredId(null)}
                                onClick={() => handleZoneClick(zone.id)}
                                className={`p-4 rounded-2xl border transition-all cursor-pointer flex flex-col gap-2 group ${
                                  selectedId === zone.id
                                    ? 'border-emerald-500 bg-emerald-500/10 scale-[1.02] shadow-md'
                                    : hoveredId === zone.id
                                    ? 'border-emerald-500/50 bg-slate-500/10'
                                    : `border-current/10 bg-black/5 hover:bg-black/10`
                                }`}
                              >
                                <div className="flex justify-between items-center">
                                  <span className="font-bold font-mono text-sm">{zone.id}</span>
                                  <span
                                    className={`text-[10px] font-black px-2 py-1 rounded uppercase ${
                                      zone.isConditioned
                                        ? 'bg-emerald-500/20 text-emerald-400'
                                        : 'bg-slate-500/20 text-slate-400'
                                    }`}
                                  >
                                    {zone.isConditioned ? '공조' : '비공조'}
                                  </span>
                                </div>
                                <div className="text-xs font-bold opacity-80 mt-1 flex justify-between items-end">
                                  <span className="truncate pr-2">
                                    {ACTIVITIES.find((a) => a.id === zone.activityId)?.name || '알 수 없음'}
                                  </span>
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleZoneClick(zone.id);
                                    }}
                                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-[10px] font-black uppercase tracking-widest transition-transform shadow-lg group-hover:scale-105 shrink-0"
                                  >
                                    설정
                                  </button>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}



                    {editMode === 'surface' &&
                      Object.entries(
                        groupBy(
                          surfaces.filter((s) => (s.floor || 1) === parseInt(activeFloor)),
                          (s) => getSurfaceGroupName(s.type)
                        )
                      ).map(([groupName, groupSurfs]) => (
                        <div key={groupName} className="mb-6">
                          <h3 className="text-[11px] font-black text-blue-500 uppercase tracking-widest mb-3 flex items-center gap-2 border-b border-blue-500/20 pb-2">
                            <div className="w-1.5 h-1.5 rounded-full bg-blue-500"></div>
                            {groupName} <span className="opacity-50 text-slate-400">({groupSurfs.length})</span>
                          </h3>
                          <div className="space-y-3">
                            {groupSurfs.map((surf) => (
                              <div
                                key={surf.id}
                                onMouseEnter={() => setHoveredId(surf.id)}
                                onMouseLeave={() => setHoveredId(null)}
                                onClick={() => handleSurfaceClick(surf)}
                                className={`p-4 rounded-2xl border transition-all cursor-pointer flex flex-col gap-3 group ${
                                  selectedId === surf.id
                                    ? 'border-blue-500 bg-blue-500/10 scale-[1.02] shadow-md'
                                    : hoveredId === surf.id
                                    ? 'border-blue-500/50 bg-slate-500/10'
                                    : `border-current/10 bg-black/5 hover:bg-black/10`
                                }`}
                              >
                                <div className="flex justify-between items-center">
                                  <span className="font-bold font-mono text-sm">{surf.id}</span>
                                </div>
                                <div className="flex justify-between items-end">
                                  <span className="text-xs opacity-70 font-medium">
                                    {DIR_MAP[surf.direction] || surf.direction || surf.zone}
                                  </span>
                                  <div className="flex items-center gap-3">
                                    <div className="text-right">
                                      <span className="text-[10px] opacity-50 uppercase mb-0.5 block">U-Value</span>
                                      <span
                                        className={`text-sm font-black ${
                                          (surf.uValue || 0) > 0.6 ? 'text-orange-500' : 'text-blue-500'
                                        }`}
                                      >
                                        {(surf.uValue || 0).toFixed(2)}
                                      </span>
                                    </div>
                                    <button
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        handleSurfaceClick(surf);
                                      }}
                                      className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-[10px] font-black uppercase tracking-widest transition-transform shadow-lg group-hover:scale-105"
                                    >
                                      수정
                                    </button>
                                  </div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                  </div>
                </div>

                <div className="flex-1 relative transition-all duration-300 w-full h-full flex flex-col bg-black/5 p-4">
                  <div className="flex-1 relative min-h-[300px] md:min-h-[400px]">
                    <BuildingViewer
                      surfaces={surfaces}
                      zones={zones}
                      activeFloor={activeFloor}
                      editMode={editMode}
                      onSurfaceClick={handleSurfaceClick}
                      onZoneClick={handleZoneClick}
                      selectedId={selectedId}
                      hoveredId={hoveredId}
                      draftState={editState}
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
                  <div className="absolute bottom-10 left-1/2 -translate-x-1/2 px-6 py-3 rounded-full bg-black/80 backdrop-blur-md text-white text-xs font-bold pointer-events-none shadow-lg z-20">
                    💡{' '}
                    {editMode === 'zone'
                      ? '공간 덩어리(Zone)를 클릭하여 용도와 공조(HVAC)를 세팅하세요.'
                      : '외피(Surface)를 클릭하여 단열과 창호 속성을 수정하세요.'}
                  </div>
                </div>

                {/* --- 우측 패널: 에디터 --- */}
                {selectedId && (
                  <div
                    className={`absolute right-0 top-0 w-[480px] h-full shadow-[-30px_0_60px_rgba(0,0,0,0.4)] z-50 overflow-y-auto flex flex-col animate-in slide-in-from-right-8 duration-300 custom-scrollbar ${
                      isDarkMode ? 'bg-[#0F172A] border-l border-slate-700' : 'bg-[#F8FAFC] border-l border-slate-300'
                    }`}
                  >
                    <div
                      className={`p-6 border-b sticky top-0 backdrop-blur-xl z-50 flex justify-between items-center ${
                        isDarkMode ? 'border-slate-700 bg-[#0F172A]/90' : 'border-slate-300 bg-[#F8FAFC]/90'
                      }`}
                    >
                      <div>
                        <h2 className="text-xl font-black flex items-center gap-2">
                          {editMode === 'zone' ? (
                            <Info className="text-emerald-500" size={24} />
                          ) : (
                            <Info className="text-blue-500" size={24} />
                          )}{' '}
                          {editMode === 'zone' ? '구역 용도/공조 설정' : '외피 속성 상세 수정'}
                        </h2>
                      </div>
                      <button
                        onClick={() => setSelectedId(null)}
                        className="p-2 rounded-xl hover:bg-red-500/10 text-red-500 transition-colors"
                      >
                        <X size={20} />
                      </button>
                    </div>

                    <div className="p-6 space-y-6 pb-32">
                      <div className={`p-4 rounded-2xl border ${theme.card} shadow-sm text-center`}>
                        <p className="text-[10px] font-black uppercase tracking-widest opacity-50 mb-1">
                          {editMode === 'zone' ? 'Target Zone ID' : 'Target Element ID'}
                        </p>
                        <p
                          className={`text-2xl font-black font-mono ${
                            editMode === 'zone' ? 'text-emerald-400' : 'text-blue-400'
                          }`}
                        >
                          {selectedId}
                        </p>
                        {editMode === 'surface' &&
                          (selectedSurfaceData?.type === 'InternalWall' ||
                            selectedSurfaceData?.type === 'InteriorWall') &&
                          selectedSurfaceData.adjacentZone && (
                            <p className="text-xs font-bold text-orange-500 mt-2 bg-orange-500/10 py-1.5 rounded-lg inline-block px-3 border border-orange-500/20">
                              연결된 구역: {selectedSurfaceData.zone} ↔ {selectedSurfaceData.adjacentZone}
                            </p>
                          )}
                      </div>

                      {/* ZONE EDITOR */}
                      {editMode === 'zone' && (
                        <div className="space-y-6 animate-in fade-in zoom-in-95">
                          <div className={`p-6 rounded-[1.5rem] border ${theme.card} shadow-sm`}>
                            <label className="text-sm font-black block mb-4 flex items-center gap-2">
                              <Users size={18} className="text-emerald-500" /> 공간 용도 할당 (Activity)
                            </label>
                            <select
                              value={editState.activityId}
                              onChange={(e) =>
                                setEditState((prev) => ({ ...prev, activityId: parseInt(e.target.value) }))
                              }
                              className={`w-full p-4 text-[12px] font-bold rounded-xl border outline-none ${theme.input} focus:border-emerald-500`}
                            >
                              {activityOptions.map((a) => (
                                <option key={a.id} value={a.id}>
                                  {a.name}
                                </option>
                              ))}
                            </select>

                            {similarZoneCount > 0 && (
                              <label
                                className={`mt-4 flex items-start gap-3 p-4 rounded-xl border cursor-pointer transition-all ${
                                  applyToSimilarZones
                                    ? 'border-emerald-500 bg-emerald-500/10'
                                    : isDarkMode ? 'border-white/10 bg-white/5' : 'border-slate-300/60 bg-slate-500/5'
                                }`}
                              >
                                <input
                                  type="checkbox"
                                  className="mt-0.5 shrink-0 accent-emerald-500"
                                  checked={applyToSimilarZones}
                                  onChange={(e) => setApplyToSimilarZones(e.target.checked)}
                                />
                                <span className={`text-xs font-bold leading-relaxed ${theme.textMain}`}>
                                  같은 용도(&apos;{activityLabel}&apos;)로 분류된 존이 {similarZoneCount}개 더 있습니다.
                                  저장 시 이 설정(용도·부하·냉난방)을 전부 동일하게 적용할까요?
                                  <span className={`block mt-1 font-normal ${theme.textSub}`}>
                                    체크 후 저장하면 {similarZoneCount}개 존에 하나하나 반복 입력할 필요 없이 한 번에 반영됩니다.
                                  </span>
                                </span>
                              </label>
                            )}
                          </div>

                          <div
                            className={`p-6 rounded-[1.5rem] border ${theme.card} shadow-sm space-y-6 border-emerald-500/10 bg-emerald-500/5`}
                          >
                            <h3 className="text-sm font-black flex items-center gap-2 text-emerald-500 border-b border-emerald-500/20 pb-3 mb-2">
                              <Activity size={16} /> 내부 발열 부하 (Internal Loads)
                            </h3>
                            <div className="flex items-center justify-between gap-4">
                              <label className={`text-xs font-bold flex items-center gap-2 w-1/3 ${theme.textMain}`}>
                                <Users size={14} className="text-emerald-400" /> 재실 밀도
                              </label>
                              <div className="flex-1 flex items-center gap-2">
                                <input
                                  type="number"
                                  min="0"
                                  step="0.01"
                                  value={editState.peopleDensity || 0}
                                  onChange={(e) =>
                                    setEditState((prev) => ({ ...prev, peopleDensity: parseFloat(e.target.value) }))
                                  }
                                  className={`w-full p-2 rounded-lg font-black text-right outline-none border ${theme.input} focus:border-emerald-500`}
                                />
                                <span className={`text-[10px] font-bold w-12 ${theme.textSub}`}>명/m²</span>
                              </div>
                            </div>

                            <div className="flex flex-col gap-2 border-t border-emerald-500/10 pt-4">
                              <div className="flex items-center justify-between gap-4">
                                <label className={`text-xs font-bold flex items-center gap-2 w-1/3 ${theme.textMain}`}>
                                  <Lightbulb size={14} className="text-yellow-400" /> 조명 부하
                                </label>
                                <div className="flex-1 flex flex-col items-end gap-1">
                                  <div className="flex items-center gap-2 w-full">
                                    <input
                                      type="number"
                                      min="0"
                                      step="0.5"
                                      value={editState.lightingPower || 0}
                                      onChange={(e) =>
                                        setEditState((prev) => ({
                                          ...prev,
                                          lightingPower: parseFloat(e.target.value),
                                        }))
                                      }
                                      className={`w-full p-2 rounded-lg font-black text-right outline-none border ${theme.input} focus:border-emerald-500`}
                                    />
                                    <span className={`text-[10px] font-bold w-12 ${theme.textSub}`}>W/m²</span>
                                  </div>
                                  <button
                                    onClick={() => setLightCalc((p) => ({ ...p, active: !p.active }))}
                                    className="text-[10px] text-emerald-500 hover:text-emerald-400 font-bold flex items-center gap-1 mt-1 transition-colors"
                                  >
                                    <Calculator size={12} /> {lightCalc.active ? '계산기 닫기' : '🧮 개수로 계산하기'}
                                  </button>
                                </div>
                              </div>
                              {lightCalc.active && (
                                <div className="p-3 rounded-xl bg-black/20 border border-emerald-500/20 flex flex-col gap-3 animate-in fade-in zoom-in-95">
                                  <div className="flex items-center justify-between gap-1 text-[10px] font-bold text-slate-400">
                                    <div className="flex flex-col gap-1 items-center">
                                      <span className="opacity-70">1대 전력</span>
                                      <div className="flex items-center gap-1">
                                        <input
                                          type="number"
                                          value={lightCalc.w}
                                          onChange={(e) => setLightCalc((p) => ({ ...p, w: Number(e.target.value) }))}
                                          className={`w-14 p-1.5 rounded-lg font-bold text-center outline-none border ${theme.input} focus:border-emerald-500`}
                                        />{' '}
                                        W
                                      </div>
                                    </div>
                                    <span className="mt-4">×</span>
                                    <div className="flex flex-col gap-1 items-center">
                                      <span className="opacity-70">설치 개수</span>
                                      <div className="flex items-center gap-1">
                                        <input
                                          type="number"
                                          value={lightCalc.qty}
                                          onChange={(e) => setLightCalc((p) => ({ ...p, qty: Number(e.target.value) }))}
                                          className={`w-12 p-1.5 rounded-lg font-bold text-center outline-none border ${theme.input} focus:border-emerald-500`}
                                        />{' '}
                                        개
                                      </div>
                                    </div>
                                    <span className="mt-4">÷</span>
                                    <div className="flex flex-col gap-1 items-center">
                                      <span className="opacity-70">구역 면적</span>
                                      <div className="flex items-center gap-1">
                                        <input
                                          type="number"
                                          value={lightCalc.area}
                                          onChange={(e) =>
                                            setLightCalc((p) => ({ ...p, area: Number(e.target.value) }))
                                          }
                                          className={`w-14 p-1.5 rounded-lg font-bold text-center outline-none border ${theme.input} focus:border-emerald-500`}
                                        />{' '}
                                        m²
                                      </div>
                                    </div>
                                  </div>
                                  <div className="flex justify-between items-center border-t border-white/5 pt-2 mt-1">
                                    <span className="text-[11px] text-emerald-400 font-black">
                                      결과: {((lightCalc.w * lightCalc.qty) / (lightCalc.area || 1)).toFixed(1)} W/m²
                                    </span>
                                    <button
                                      onClick={() => {
                                        setEditState((prev) => ({
                                          ...prev,
                                          lightingPower: parseFloat(
                                            ((lightCalc.w * lightCalc.qty) / (lightCalc.area || 1)).toFixed(1)
                                          ),
                                        }));
                                        setLightCalc((p) => ({ ...p, active: false }));
                                      }}
                                      className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-[10px] rounded-lg font-black shadow-lg"
                                    >
                                      적용하기
                                    </button>
                                  </div>
                                </div>
                              )}
                            </div>

                            <div className="flex flex-col gap-2 border-t border-emerald-500/10 pt-4">
                              <div className="flex items-center justify-between gap-4">
                                <label className={`text-xs font-bold flex items-center gap-2 w-1/3 ${theme.textMain}`}>
                                  <Monitor size={14} className="text-blue-400" /> 기기 부하
                                </label>
                                <div className="flex-1 flex flex-col items-end gap-1">
                                  <div className="flex items-center gap-2 w-full">
                                    <input
                                      type="number"
                                      min="0"
                                      step="0.5"
                                      value={editState.equipmentPower || 0}
                                      onChange={(e) =>
                                        setEditState((prev) => ({
                                          ...prev,
                                          equipmentPower: parseFloat(e.target.value),
                                        }))
                                      }
                                      className={`w-full p-2 rounded-lg font-black text-right outline-none border ${theme.input} focus:border-emerald-500`}
                                    />
                                    <span className={`text-[10px] font-bold w-12 ${theme.textSub}`}>W/m²</span>
                                  </div>
                                  <button
                                    onClick={() => setEquipCalc((p) => ({ ...p, active: !p.active }))}
                                    className="text-[10px] text-emerald-500 hover:text-emerald-400 font-bold flex items-center gap-1 mt-1 transition-colors"
                                  >
                                    <Calculator size={12} /> {equipCalc.active ? '계산기 닫기' : '🧮 개수로 계산하기'}
                                  </button>
                                </div>
                              </div>
                              {equipCalc.active && (
                                <div className="p-3 rounded-xl bg-black/20 border border-emerald-500/20 flex flex-col gap-3 animate-in fade-in zoom-in-95">
                                  <div className="flex items-center justify-between gap-1 text-[10px] font-bold text-slate-400">
                                    <div className="flex flex-col gap-1 items-center">
                                      <span className="opacity-70">1대 전력</span>
                                      <div className="flex items-center gap-1">
                                        <input
                                          type="number"
                                          value={equipCalc.w}
                                          onChange={(e) => setEquipCalc((p) => ({ ...p, w: Number(e.target.value) }))}
                                          className={`w-14 p-1.5 rounded-lg font-bold text-center outline-none border ${theme.input} focus:border-emerald-500`}
                                        />{' '}
                                        W
                                      </div>
                                    </div>
                                    <span className="mt-4">×</span>
                                    <div className="flex flex-col gap-1 items-center">
                                      <span className="opacity-70">설치 개수</span>
                                      <div className="flex items-center gap-1">
                                        <input
                                          type="number"
                                          value={equipCalc.qty}
                                          onChange={(e) =>
                                            setEquipCalc((p) => ({ ...p, qty: Number(e.target.value) }))
                                          }
                                          className={`w-12 p-1.5 rounded-lg font-bold text-center outline-none border ${theme.input} focus:border-emerald-500`}
                                        />{' '}
                                        개
                                      </div>
                                    </div>
                                    <span className="mt-4">÷</span>
                                    <div className="flex flex-col gap-1 items-center">
                                      <span className="opacity-70">구역 면적</span>
                                      <div className="flex items-center gap-1">
                                        <input
                                          type="number"
                                          value={equipCalc.area}
                                          onChange={(e) =>
                                            setEquipCalc((p) => ({ ...p, area: Number(e.target.value) }))
                                          }
                                          className={`w-14 p-1.5 rounded-lg font-bold text-center outline-none border ${theme.input} focus:border-emerald-500`}
                                        />{' '}
                                        m²
                                      </div>
                                    </div>
                                  </div>
                                  <div className="flex justify-between items-center border-t border-white/5 pt-2 mt-1">
                                    <span className="text-[11px] text-emerald-400 font-black">
                                      결과: {((equipCalc.w * equipCalc.qty) / (equipCalc.area || 1)).toFixed(1)} W/m²
                                    </span>
                                    <button
                                      onClick={() => {
                                        setEditState((prev) => ({
                                          ...prev,
                                          equipmentPower: parseFloat(
                                            ((equipCalc.w * equipCalc.qty) / (equipCalc.area || 1)).toFixed(1)
                                          ),
                                        }));
                                        setEquipCalc((p) => ({ ...p, active: false }));
                                      }}
                                      className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-[10px] rounded-lg font-black shadow-lg"
                                    >
                                      적용하기
                                    </button>
                                  </div>
                                </div>
                              )}

                              <div className={`border-t ${isDarkMode ? 'border-white/5' : 'border-slate-300/60'} pt-4 mt-4 space-y-4 text-left`}>
                                <div className="flex items-center justify-between">
                                  <label className={`text-xs font-black flex items-center gap-2 ${isDarkMode ? 'text-slate-400' : 'text-slate-600'}`}>
                                    🔌 콘센트 (소켓) 수
                                  </label>
                                  <div className="flex items-center gap-2">
                                    <input
                                      type="number"
                                      min="0"
                                      value={editState.outletCount || 0}
                                      onChange={(e) =>
                                        setEditState((prev) => ({
                                          ...prev,
                                          outletCount: parseInt(e.target.value) || 0,
                                        }))
                                      }
                                      className={`w-24 p-2 rounded-lg font-black text-right outline-none border ${theme.input} focus:border-emerald-500`}
                                      placeholder="개수 입력"
                                    />
                                    <span className={`text-[10px] font-bold w-12 ${theme.textSub}`}>개</span>
                                  </div>
                                </div>

                                {(editState.outletCount || 0) > 0 && (
                                  <div className={`space-y-3 p-3 rounded-xl border ${isDarkMode ? 'bg-black/20 border-white/5' : 'bg-slate-300/40 border-slate-300/80'} animate-in fade-in duration-200`}>
                                    <div className="flex items-center justify-between text-[11px] font-bold">
                                      <span className={isDarkMode ? 'text-slate-400' : 'text-slate-600'}>구역 면적:</span>
                                      <span className={isDarkMode ? 'text-slate-200' : 'text-slate-800'}>{getZoneFloorArea(editState.id).toFixed(1)} m²</span>
                                    </div>
                                    <div className="flex items-center justify-between text-[11px] font-bold">
                                      <span className={isDarkMode ? 'text-slate-400' : 'text-slate-600'}>용도별 콘센트당 정격:</span>
                                      <span className={isDarkMode ? 'text-slate-200' : 'text-slate-800'}>
                                        {OUTLET_W_PER_ACTIVITY[getActivityCategory(editState.activityId)] || OUTLET_W_PER_ACTIVITY.default} W
                                      </span>
                                    </div>
                                    <div className="flex items-center justify-between text-[11px] font-bold">
                                      <span className={isDarkMode ? 'text-slate-400' : 'text-slate-600'}>산정 방식 (NREL 2012 / IEC):</span>
                                      <span className={`text-right ${isDarkMode ? 'text-slate-200' : 'text-slate-800'}`}>
                                        개수({editState.outletCount}) × 정격 × 0.5(다양성) × 0.7(사용률)
                                      </span>
                                    </div>
                                    <div className={`flex items-center justify-between text-[11px] font-black border-t pt-2 ${isDarkMode ? 'text-emerald-400 border-white/5' : 'text-emerald-700 border-slate-300/60'}`}>
                                      <span>🔌 예상 콘센트 부하:</span>
                                      <span className={isDarkMode ? 'text-emerald-400' : 'text-emerald-700'}>
                                        {calcOutletPower(editState, getZoneFloorArea(editState.id)).toFixed(2)} W/m²
                                      </span>
                                    </div>

                                    <div className="flex items-center justify-between pt-1">
                                      <span className={`text-[10px] font-bold ${isDarkMode ? 'text-slate-400' : 'text-slate-600'}`} title="기기부하와 콘센트 추정값은 같은 부하를 두 방식으로 잰 값입니다. 기본은 큰 쪽만 씁니다.">콘센트 부하 반영:</span>
                                      <div className={`flex ${isDarkMode ? 'bg-black/30 border-white/5' : 'bg-slate-300/60 border-slate-300/80'} p-0.5 rounded-lg border`}>
                                        <button
                                          onClick={() =>
                                            setEditState((prev) => ({
                                              ...prev,
                                              outletLoadType: 'sum',
                                            }))
                                          }
                                          className={`px-2 py-1 text-[9px] font-bold rounded-md transition-all ${
                                            (editState.outletLoadType || 'max') === 'sum'
                                              ? 'bg-emerald-600 text-white shadow-sm'
                                              : `${isDarkMode ? 'text-slate-400 hover:text-slate-200' : 'text-slate-600 hover:text-slate-800'}`
                                          }`}
                                        >
                                          합산 (별도 공정부하)
                                        </button>
                                        <button
                                          onClick={() =>
                                            setEditState((prev) => ({
                                              ...prev,
                                              outletLoadType: 'max',
                                            }))
                                          }
                                          className={`px-2 py-1 text-[9px] font-bold rounded-md transition-all ${
                                            (editState.outletLoadType || 'max') === 'max'
                                              ? 'bg-emerald-600 text-white shadow-sm'
                                              : `${isDarkMode ? 'text-slate-400 hover:text-slate-200' : 'text-slate-600 hover:text-slate-800'}`
                                          }`}
                                        >
                                          큰 쪽만 (기본)
                                        </button>
                                      </div>
                                    </div>

                                    {/* 기기부하 기본값(ASHRAE/DOE 통상값)의 정의가 곧 콘센트 부하다.
                                        두 값을 더하면 같은 부하를 두 번 세는 것이라 기본은 '큰 쪽만'이다. */}
                                    <p className={`text-[9px] leading-relaxed ${isDarkMode ? 'text-slate-500' : 'text-slate-500'}`}>
                                      {(editState.outletLoadType || 'max') === 'sum'
                                        ? '기기 부하가 콘센트를 제외한 공정·특수기기만일 때 고르세요. 아니면 같은 부하를 두 번 세게 됩니다.'
                                        : '기기 부하와 콘센트 추정값은 같은 부하를 두 방식으로 잰 값이라, 큰 쪽만 씁니다.'}
                                    </p>
                                    <div className={`text-[11px] font-bold flex justify-between items-center bg-emerald-500/10 p-2 rounded-lg border border-emerald-500/20 mt-1 ${isDarkMode ? 'text-slate-300' : 'text-emerald-950'}`}>
                                      <span>⚡ 시뮬레이션 반영 기기 부하:</span>
                                      <span className={`font-black ${isDarkMode ? 'text-emerald-400' : 'text-emerald-700'}`}>
                                        {((editState.outletLoadType || 'max') === 'sum'
                                          ? (editState.equipmentPower || 0) + calcOutletPower(editState, getZoneFloorArea(editState.id))
                                          : Math.max(editState.equipmentPower || 0, calcOutletPower(editState, getZoneFloorArea(editState.id)))
                                        ).toFixed(2)}{' '}
                                        W/m²
                                      </span>
                                    </div>
                                  </div>
                                )}
                              </div>
                              <div className={`border-t ${isDarkMode ? 'border-white/5' : 'border-slate-300/60'} pt-4 mt-4 space-y-4 text-left`}>
                                <div className="flex items-center justify-between">
                                  <label className={`text-xs font-black flex items-center gap-2 ${isDarkMode ? 'text-slate-400' : 'text-slate-600'}`}>
                                    <Lightbulb className="text-yellow-500" size={16} /> 교체할 LED 등기구 수량
                                  </label>
                                  <div className="flex items-center gap-2">
                                    <input
                                      type="number"
                                      min="0"
                                      value={editState.ledFixtureCount || ''}
                                      onChange={(e) =>
                                        setEditState((prev) => ({
                                          ...prev,
                                          ledFixtureCount: parseInt(e.target.value) || 0,
                                        }))
                                      }
                                      className={`w-24 p-2 rounded-lg font-black text-right outline-none border ${theme.input} focus:border-yellow-500`}
                                      placeholder="자동 추정"
                                    />
                                    <span className={`text-[10px] font-bold w-12 ${theme.textSub}`}>개</span>
                                  </div>
                                </div>
                                <p className={`text-[10px] mt-1 ${isDarkMode ? 'text-slate-500' : 'text-slate-500'}`}>
                                  값을 입력하면 구역 면적 기반 추정 방식 대신, '입력한 갯수 × 단가(30,000원)'로 이 구역의 전기 공사비를 정밀하게 직접 산출합니다.
                                </p>
                              </div>

                            </div>
                          </div>

                          <div className={`p-6 rounded-[1.5rem] border ${theme.card} shadow-sm`}>
                            <label className="text-sm font-black flex items-center justify-between mb-4">
                              <div className="flex items-center gap-2">
                                <Wind size={18} className="text-blue-500" /> 냉난방 공조(HVAC) 가동 여부
                              </div>
                            </label>
                            <div
                              className={`p-4 rounded-xl flex items-center justify-between cursor-pointer border-2 transition-all ${
                                editState.isConditioned ? 'border-blue-500 bg-blue-500/10' : 'border-slate-500 bg-slate-500/10'
                              }`}
                              onClick={() => setEditState((prev) => ({ ...prev, isConditioned: !prev.isConditioned }))}
                            >
                              <span className={`font-black ${editState.isConditioned ? 'text-blue-400' : 'text-slate-400'}`}>
                                {editState.isConditioned ? '냉난방기 가동 (Conditioned)' : '비공조 구역 (Unconditioned)'}
                              </span>
                              {editState.isConditioned ? (
                                <ToggleRight size={32} className="text-blue-500" />
                              ) : (
                                <ToggleLeft size={32} className="text-slate-500" />
                              )}
                            </div>
                          </div>

                          {editState.isConditioned && (
                            <div className={`p-6 rounded-[1.5rem] border ${theme.card} shadow-sm animate-in slide-in-from-top-4 space-y-6 border-blue-500/30 bg-blue-500/5`}>
                              <h3 className="text-sm font-black flex items-center gap-2 text-blue-500 border-b border-blue-500/20 pb-3 mb-4">
                                <Settings2 size={16} /> 상세 공조 세팅 (HVAC Setup)
                              </h3>
                              <div>
                                <label className="text-xs font-black block mb-2 opacity-70">
                                  공조 시스템 종류 (System Type)
                                </label>
                                <select
                                  value={editState.hvacSystemId}
                                  onChange={(e) =>
                                    setEditState((prev) => ({ ...prev, hvacSystemId: parseInt(e.target.value) }))
                                  }
                                  className={`w-full p-3 text-xs font-bold rounded-lg border outline-none ${theme.input} focus:border-blue-500`}
                                >
                                  {HVAC_SYSTEMS.map((sys) => (
                                    <option key={sys.id} value={sys.id}>
                                      {sys.name}
                                    </option>
                                  ))}
                                </select>
                              </div>
                              {/* 존별 냉방기 오버라이드 — 시뮬레이션 실기기(설치/용량)에 직접 반영 */}
                              <div className="grid grid-cols-2 gap-3">
                                <div>
                                  <label className="text-xs font-black block mb-2 opacity-70">
                                    냉방기(에어컨) 설치
                                  </label>
                                  <select
                                    value={editState.coolingInstalled || 'auto'}
                                    onChange={(e) =>
                                      setEditState((prev) => ({ ...prev, coolingInstalled: e.target.value }))
                                    }
                                    className={`w-full p-3 text-xs font-bold rounded-lg border outline-none ${theme.input} focus:border-cyan-500`}
                                  >
                                    <option value="auto">자동 (거주 구역만 설치)</option>
                                    <option value="yes">설치</option>
                                    <option value="no">미설치</option>
                                  </select>
                                </div>
                                <div>
                                  <label className="text-xs font-black block mb-2 opacity-70">
                                    냉방 용량 (평형, 비우면 자동)
                                  </label>
                                  <input
                                    type="number" min="0" step="1"
                                    placeholder="예: 6 (≈2.3kW)"
                                    value={editState.coolingCapacityPyeong ?? ''}
                                    onChange={(e) =>
                                      setEditState((prev) => ({
                                        ...prev,
                                        coolingCapacityPyeong: e.target.value === '' ? null : parseFloat(e.target.value),
                                      }))
                                    }
                                    className={`w-full p-3 text-xs font-bold rounded-lg border outline-none ${theme.input} focus:border-cyan-500`}
                                  />
                                </div>
                              </div>
                              <div>
                                <label className="text-xs font-black block mb-2 opacity-70">
                                  난방 열원 (Heating Fuel)
                                </label>
                                <select
                                  value={editState.heatingFuelId}
                                  onChange={(e) =>
                                    setEditState((prev) => ({ ...prev, heatingFuelId: parseInt(e.target.value) }))
                                  }
                                  className={`w-full p-3 text-xs font-bold rounded-lg border outline-none ${theme.input} focus:border-blue-500`}
                                >
                                  {FUEL_TYPES.map((fuel) => (
                                    <option key={fuel.id} value={fuel.id}>
                                      {fuel.name}
                                    </option>
                                  ))}
                                </select>
                              </div>
                              <div>
                                <label className="text-xs font-black block mb-2 opacity-70">
                                  환기/급배기 방식 (Ventilation)
                                </label>
                                <select
                                  value={editState.ventilationId}
                                  onChange={(e) =>
                                    setEditState((prev) => ({ ...prev, ventilationId: parseInt(e.target.value) }))
                                  }
                                  className={`w-full p-3 text-xs font-bold rounded-lg border outline-none ${theme.input} focus:border-blue-500`}
                                >
                                  {VENT_TYPES.map((vt) => (
                                    <option key={vt.id} value={vt.id}>
                                      {vt.name}
                                    </option>
                                  ))}
                                </select>
                              </div>
                              <div className="grid grid-cols-2 gap-4 pt-2">
                                {projectData.customSchedule.useCustom ? (
                                  <div className="col-span-2 p-4 rounded-xl border border-indigo-500/30 bg-indigo-500/10 flex items-center gap-3">
                                    <Clock size={20} className="text-indigo-500 shrink-0" />
                                    <div>
                                      <p className="text-sm font-bold text-indigo-500">24시간 스케줄 온도 제어 중</p>
                                      <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">이전 단계의 스케줄 에디터에서 설정한 상세 온도 곡선이 최우선으로 적용됩니다.</p>
                                    </div>
                                  </div>
                                ) : (
                                  <>
                                    <div
                                      className={`p-3 rounded-xl border ${
                                        isDarkMode ? 'bg-slate-900 border-slate-700' : 'bg-white border-slate-200'
                                      }`}
                                    >
                                      <label className="text-[10px] font-black uppercase text-red-500 flex items-center gap-1 mb-2">
                                        <Flame size={12} /> 난방 설정온도
                                      </label>
                                      <div className="flex items-center gap-1 text-red-500">
                                        <input
                                          type="number"
                                          min="16"
                                          max="30"
                                          value={editState.heatingSetpoint}
                                          onChange={(e) =>
                                            setEditState((prev) => ({
                                              ...prev,
                                              heatingSetpoint: parseFloat(e.target.value),
                                            }))
                                          }
                                          className="w-12 bg-transparent font-black text-xl outline-none"
                                        />
                                        <span className="font-bold text-xs opacity-50">°C</span>
                                      </div>
                                    </div>
                                    <div
                                      className={`p-3 rounded-xl border ${
                                        isDarkMode ? 'bg-slate-900 border-slate-700' : 'bg-white border-slate-200'
                                      }`}
                                    >
                                      <label className="text-[10px] font-black uppercase text-cyan-500 flex items-center gap-1 mb-2">
                                        <Thermometer size={12} /> 냉방 설정온도
                                      </label>
                                      <div className="flex items-center gap-1 text-cyan-500">
                                        <input
                                          type="number"
                                          min="18"
                                          max="32"
                                          value={editState.coolingSetpoint}
                                          onChange={(e) =>
                                            setEditState((prev) => ({
                                              ...prev,
                                              coolingSetpoint: parseFloat(e.target.value),
                                            }))
                                          }
                                          className="w-12 bg-transparent font-black text-xl outline-none"
                                        />
                                        <span className="font-bold text-xs opacity-50">°C</span>
                                      </div>
                                    </div>
                                  </>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {/* SURFACE EDITOR */}
                      {editMode === 'surface' && selectedSurfaceData && (
                        <div className="space-y-8 animate-in fade-in zoom-in-95">
                          <div className={`p-4 rounded-2xl border ${theme.card} shadow-sm text-center mb-6`}>
                            <p className="text-[10px] font-black uppercase tracking-widest opacity-50 mb-1">
                              Surface Type
                            </p>
                            <p className="text-lg font-bold text-blue-500 uppercase">
                              {selectedSurfaceData.type === 'InternalWall' ||
                              selectedSurfaceData.type === 'InteriorWall'
                                ? '내벽 (Internal Wall)'
                                : selectedSurfaceData.type}{' '}
                              {selectedSurfaceData.direction
                                ? ` (${DIR_MAP[selectedSurfaceData.direction] || selectedSurfaceData.direction})`
                                : ''}
                            </p>
                          </div>

                          {/* 시뮬레이션 표면 열해석 결과 오버레이 */}
                          {res && (res.surfaceThermal || res.result?.surfaceThermal) && (
                            <div className="p-4 rounded-2xl border border-emerald-500/30 bg-emerald-500/5 shadow-sm space-y-2">
                              <h4 className="text-xs font-black uppercase text-emerald-500 tracking-wider flex items-center gap-1.5 justify-center">
                                🌡️ EnergyPlus 표면 열해석 ({sunMonth}월)
                              </h4>
                              <div className="grid grid-cols-2 gap-3 text-left">
                                <div className="text-center">
                                  <span className="text-[10px] text-slate-500 font-bold block">외피 표면 온도</span>
                                  <span className="text-sm font-black text-emerald-400">
                                    {(res.surfaceThermal?.[selectedSurfaceData.id]?.temperature?.[sunMonth - 1] ?? 
                                      res.result?.surfaceThermal?.[selectedSurfaceData.id]?.temperature?.[sunMonth - 1] ?? 20.0).toFixed(1)} °C
                                  </span>
                                </div>
                                <div className="text-center">
                                  <span className="text-[10px] text-slate-500 font-bold block">일사 도달량</span>
                                  <span className="text-sm font-black text-emerald-400">
                                    {(res.surfaceThermal?.[selectedSurfaceData.id]?.radiation?.[sunMonth - 1] ?? 
                                      res.result?.surfaceThermal?.[selectedSurfaceData.id]?.radiation?.[sunMonth - 1] ?? 0.0).toFixed(1)} W/㎡
                                  </span>
                                </div>
                              </div>
                            </div>
                          )}

                          {/* 시뮬레이션 표면 환기량 결과 오버레이 */}
                          {res && (res.surfaceAirflow || res.result?.surfaceAirflow) && (
                            <div className="p-4 rounded-2xl border border-sky-500/30 bg-sky-500/5 shadow-sm space-y-2">
                              <h4 className="text-xs font-black uppercase text-sky-500 tracking-wider flex items-center gap-1.5 justify-center">
                                💨 EnergyPlus 개구부 환기/풍량 ({sunMonth}월)
                              </h4>
                              {(() => {
                                const afData = res.surfaceAirflow?.[selectedSurfaceData.id] || res.result?.surfaceAirflow?.[selectedSurfaceData.id];
                                if (afData && (afData.inflow || afData.outflow)) {
                                  const inf = afData.inflow?.[sunMonth - 1] ?? 0.0;
                                  const outf = afData.outflow?.[sunMonth - 1] ?? 0.0;
                                  const chartData = Array.from({ length: 12 }, (_, i) => ({
                                    name: `${i + 1}월`,
                                    inflow: afData.inflow?.[i] ?? 0,
                                    outflow: afData.outflow?.[i] ?? 0,
                                  }));

                                  return (
                                    <div className="space-y-3">
                                      <div className="grid grid-cols-2 gap-3 text-left">
                                        <div className="text-center">
                                          <span className="text-[10px] text-slate-500 font-bold block">유입량 (Inflow)</span>
                                          <span className="text-sm font-black text-sky-400">
                                            {inf.toFixed(2)} L/s
                                          </span>
                                        </div>
                                        <div className="text-center">
                                          <span className="text-[10px] text-slate-500 font-bold block">유출량 (Outflow)</span>
                                          <span className="text-sm font-black text-orange-400">
                                            {outf.toFixed(2)} L/s
                                          </span>
                                        </div>
                                      </div>
                                      <div className="h-24 w-full mt-2">
                                        <ResponsiveContainer width="100%" height="100%">
                                          <BarChart data={chartData} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
                                            <CartesianGrid strokeDasharray="3 3" stroke="#334155" opacity={0.3} />
                                            <XAxis dataKey="name" stroke="#64748b" fontSize={9} tickLine={false} />
                                            <YAxis stroke="#64748b" fontSize={9} tickLine={false} axisLine={false} unit="L" />
                                            <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: 10 }} />
                                            <Bar dataKey="inflow" fill="#0ea5e9" radius={[2, 2, 0, 0]} name="유입" />
                                            <Bar dataKey="outflow" fill="#f97316" radius={[2, 2, 0, 0]} name="유출" />
                                          </BarChart>
                                        </ResponsiveContainer>
                                      </div>
                                    </div>
                                  );
                                } else {
                                  return (
                                    <p className="text-[10px] text-center text-slate-500 font-bold py-2">
                                      이 벽면에는 개구부가 없거나 환기량이 발생하지 않았습니다.
                                    </p>
                                  );
                                }
                              })()}
                            </div>
                          )}

                          {(selectedSurfaceData.type === 'InternalWall' ||
                            selectedSurfaceData.type === 'InteriorWall') && (
                            <div className={`p-6 rounded-[1.5rem] border border-orange-500/30 bg-orange-500/5 shadow-sm`}>
                              <h3 className="text-sm font-black flex items-center gap-2 text-orange-500 mb-2">
                                <Info size={16} /> 내벽 안내
                              </h3>
                              <p className="text-xs font-medium opacity-80 leading-relaxed text-orange-400/80">
                                이 내벽은 양쪽 공간과 열을 교환하며, <b>창문(WWR)을 설치할 수 없습니다.</b>
                              </p>
                            </div>
                          )}

                          {(selectedSurfaceData.type === 'Wall' || selectedSurfaceData.type === 'ExteriorWall') && (
                            <>
                              <div className={`p-6 rounded-[1.5rem] border ${theme.card} shadow-sm`}>
                                <div className="flex justify-between items-end mb-4">
                                  <label className="text-sm font-black flex items-center gap-2">
                                    <Layers size={16} className="text-blue-500" /> 창면적비 (WWR)
                                  </label>
                                </div>
                                <div className="flex items-center gap-4 mb-3">
                                  <input
                                    type="range"
                                    min="0"
                                    max="90"
                                    step="1"
                                    value={editState.wwr || 0}
                                    onChange={(e) =>
                                      setEditState((prev) => ({ ...prev, wwr: parseInt(e.target.value) || 0 }))
                                    }
                                    className="flex-1 h-3 rounded-full appearance-none accent-blue-500 bg-slate-700 cursor-pointer"
                                  />
                                  <input
                                    type="number"
                                    min="0"
                                    max="90"
                                    step="1"
                                    value={editState.wwr || 0}
                                    onChange={(e) =>
                                      setEditState((prev) => ({ ...prev, wwr: parseInt(e.target.value) || 0 }))
                                    }
                                    className={`w-20 p-2 rounded-lg font-black text-center text-blue-500 border outline-none focus:border-blue-500 ${theme.input}`}
                                  />
                                  <span className="text-xs font-bold opacity-50">%</span>
                                </div>
                              </div>

                              <div
                                className={`p-6 rounded-[1.5rem] border ${theme.card} shadow-sm transition-opacity ${
                                  (editState.wwr || 0) === 0 ? 'opacity-30 pointer-events-none' : ''
                                }`}
                              >
                                <label className="text-sm font-black block mb-4 flex items-center gap-2">
                                  <FileText size={16} className="text-blue-500" /> 창호 시스템 사양
                                </label>
                                <div className="space-y-4">
                                  <div>
                                    <label className="text-[10px] font-black uppercase opacity-60 mb-2 flex items-center gap-1">
                                      <span className="bg-blue-500 text-white w-4 h-4 rounded-full flex items-center justify-center text-[8px]">
                                        1
                                      </span>{' '}
                                      창호 겹수 형태 (Window Panes)
                                    </label>
                                    <div className="flex gap-2 p-1 bg-black/10 rounded-xl">
                                      {['Single', 'Double', 'Triple', 'Quadruple'].map((p) => {
                                        const pLabel =
                                          p === 'Single'
                                            ? '단창'
                                            : p === 'Double'
                                            ? '복층창'
                                            : p === 'Triple'
                                            ? '삼중창'
                                            : '사중/특수';
                                        return (
                                          <button
                                            key={p}
                                            onClick={() => handlePanesChange(p)}
                                            className={`flex-1 py-2 text-[11px] font-black rounded-lg transition-all ${
                                              currentPanes === p ? 'bg-blue-500 text-white shadow-md' : inactiveBtnClass
                                            }`}
                                          >
                                            {pLabel}
                                          </button>
                                        );
                                      })}
                                    </div>
                                  </div>

                                  <div className="animate-in fade-in slide-in-from-top-2 pt-2 border-t border-blue-500/10">
                                    <label className="text-[10px] font-black uppercase opacity-60 mb-2 flex items-center gap-1">
                                      <span className="bg-blue-500 text-white w-4 h-4 rounded-full flex items-center justify-center text-[8px]">
                                        2
                                      </span>{' '}
                                      유리 코팅 및 특성 (Glass Type)
                                    </label>
                                    <div className="flex gap-2 p-1 bg-black/10 rounded-xl">
                                      {['Clear/Tinted', 'Low-E', 'Smart'].map((t) => {
                                        const tLabel =
                                          t === 'Clear/Tinted'
                                            ? '일반/칼라'
                                            : t === 'Low-E'
                                            ? '로이(Low-E)'
                                            : '스마트/가변';
                                        const isAvailable = availableTypes.includes(t);
                                        return (
                                          <button
                                            key={t}
                                            onClick={() => isAvailable && handleTypeChange(t)}
                                            disabled={!isAvailable}
                                            className={`flex-1 py-2 text-[11px] font-black rounded-lg transition-all ${
                                              !isAvailable
                                                ? 'opacity-20 cursor-not-allowed'
                                                : currentType === t
                                                ? 'bg-blue-500 text-white shadow-md'
                                                : inactiveBtnClass
                                            }`}
                                          >
                                            {tLabel}
                                          </button>
                                        );
                                      })}
                                    </div>
                                  </div>

                                  <div className="animate-in fade-in slide-in-from-top-2 pt-2 border-t border-blue-500/10">
                                    <label className="text-[10px] font-black uppercase opacity-60 mb-2 flex items-center gap-1">
                                      <span className="bg-blue-500 text-white w-4 h-4 rounded-full flex items-center justify-center text-[8px]">
                                        3
                                      </span>{' '}
                                      최종 상세 모델 (Specific Spec)
                                    </label>
                                    <select
                                      value={editState.glazingId || 42}
                                      onChange={(e) =>
                                        setEditState((prev) => ({ ...prev, glazingId: parseInt(e.target.value) }))
                                      }
                                      className={`w-full p-3 text-[11px] font-bold rounded-xl border outline-none ${theme.input} focus:border-blue-500 custom-scrollbar`}
                                    >
                                      {filteredGlazingList.map((g) => (
                                        <option key={g.id} value={g.id}>
                                          {g.name.split(': ')[1] || g.name} (U: {g.u.toFixed(2)}, SHGC: {g.shgc.toFixed(2)})
                                        </option>
                                      ))}
                                    </select>
                                  </div>

                                  {/* 4. 유리 단면 시각화 (단열재 단면과 동일 컨셉, 수평형) */}
                                  <div className="animate-in fade-in slide-in-from-top-2 pt-2 border-t border-blue-500/10">
                                    <label className="text-[10px] font-black uppercase opacity-60 mb-2 flex items-center gap-1">
                                      <span className="bg-blue-500 text-white w-4 h-4 rounded-full flex items-center justify-center text-[8px]">4</span>{' '}
                                      유리 단면 (Glazing Section)
                                    </label>
                                    {(() => {
                                      const g = currentGlazing || {};
                                      const paneCount = currentPanes === 'Single' ? 1 : currentPanes === 'Triple' ? 3 : currentPanes === 'Quadruple' ? 4 : 2;
                                      const lowE = currentType === 'Low-E';
                                      const smart = currentType === 'Smart';
                                      const coated = lowE || smart;
                                      const isArgon = /arg/i.test(g.name || '');
                                      const gasLabel = isArgon ? '아르곤' : '공기';
                                      const coatLabel = smart ? '스마트' : 'Low-E';

                                      // ── 아이소메트릭 단면 지오메트리 (사진 스타일: 비스듬한 유리 + PVC 프레임 코너) ──
                                      const baseY = 176, topY = 40;     // 유리 하단/상단 y
                                      const SH = 58;                     // 상단이 우측으로 기우는 양(입체감)
                                      const pw = 8;                      // 유리 한 장 두께
                                      const gap = Math.max(14, Math.min(26, 150 / (paneCount + 1)));
                                      const startX = 78;                 // 첫(바깥) 유리 하단 x
                                      const dep = 9, depY = -6;          // 유리 상단 두께(입체)

                                      const panes = [];
                                      for (let i = 0; i < paneCount; i++) {
                                        const x = startX + i * (pw + gap);
                                        let isLowEpane = false;
                                        if (coated) isLowEpane = paneCount >= 3 ? (i === 0 || i === paneCount - 1) : (i === paneCount - 1);
                                        panes.push({ x, isLowEpane, label: isLowEpane ? coatLabel + '유리' : '일반유리' });
                                      }
                                      const front = (x) => `${x},${baseY} ${x + pw},${baseY} ${x + pw + SH},${topY} ${x + SH},${topY}`;
                                      const cap = (x) => `${x + SH},${topY} ${x + pw + SH},${topY} ${x + pw + SH + dep},${topY + depY} ${x + SH + dep},${topY + depY}`;
                                      const gasPoly = (x) => { const a = x + pw, b = x + pw + gap; return `${a},${baseY} ${b},${baseY} ${b + SH},${topY} ${a + SH},${topY}`; };
                                      const unitR = startX + (paneCount - 1) * (pw + gap) + pw; // 안쪽 유리 하단 우측 x

                                      // 라벨 타겟(유리 표면 중앙 부근)
                                      const mid = (x) => ({ x: x + pw / 2 + SH * 0.45, y: (baseY + topY) / 2 + 6 });
                                      const labelRows = [];
                                      const pushPane = (p) => labelRows.push({ t: p.label, ...mid(p.x), c: p.isLowEpane ? '#d97706' : '#3b82f6' });
                                      pushPane(panes[0]);                                            // 바깥 유리
                                      if (paneCount >= 3) pushPane(panes[Math.floor((paneCount - 1) / 2)]); // 가운데 유리
                                      if (paneCount >= 2) pushPane(panes[paneCount - 1]);            // 실내 유리
                                      if (paneCount > 1) { const gx = panes[0].x; const a = gx + pw + gap / 2 + SH * 0.5; labelRows.push({ t: gasLabel + '가스', x: a, y: topY + 18, c: '#0ea5e9' }); }
                                      if (paneCount > 1) labelRows.push({ t: '단열간봉', x: panes[0].x + pw + gap / 2 + 4, y: baseY - 8, c: '#64748b' });

                                      return (
                                        <>
                                          <div className="rounded-xl overflow-hidden border border-slate-500/15 bg-gradient-to-b from-sky-50/40 to-transparent text-slate-600 dark:text-slate-300">
                                            <svg viewBox="0 0 340 210" className="w-full h-auto" style={{ display: 'block' }}>
                                              <defs>
                                                <linearGradient id="glz-glass" x1="0" y1="0" x2="1" y2="1">
                                                  <stop offset="0%" stopColor="#dcefff" stopOpacity="0.95" />
                                                  <stop offset="45%" stopColor="#9fd4f0" stopOpacity="0.85" />
                                                  <stop offset="100%" stopColor="#7cc3e8" stopOpacity="0.9" />
                                                </linearGradient>
                                                <linearGradient id="glz-frame" x1="0" y1="0" x2="0" y2="1">
                                                  <stop offset="0%" stopColor="#f3efe1" />
                                                  <stop offset="100%" stopColor="#ddd5bd" />
                                                </linearGradient>
                                              </defs>

                                              {/* 하단 프레임(sill) — 3D 비드 */}
                                              <polygon points={`44,${baseY + 2} ${unitR + SH + 26},${baseY + 2} ${unitR + SH + 40},${baseY - 8} 58,${baseY - 8}`} fill="#eee8d6" stroke="#c9c0a3" strokeWidth="1" />
                                              <rect x="44" y={baseY + 2} width={unitR + SH - 18} height="26" rx="3" fill="url(#glz-frame)" stroke="#c9c0a3" strokeWidth="1" />
                                              <rect x="64" y={baseY + 9} width="120" height="6" rx="3" fill="#cfc6a8" opacity="0.7" />
                                              <circle cx={unitR + SH - 2} cy={baseY + 16} r="7" fill="#e7e0cb" stroke="#bfb595" strokeWidth="1" />
                                              <circle cx={unitR + SH - 2} cy={baseY + 16} r="2.5" fill="#bfb595" />

                                              {/* 좌측 프레임(jamb) */}
                                              <polygon points={`52,${baseY} 66,${baseY} ${66 + SH},${topY} ${52 + SH},${topY}`} fill="url(#glz-frame)" stroke="#c9c0a3" strokeWidth="1" />

                                              {/* 가스 충전층 */}
                                              {panes.slice(0, -1).map((p, i) => (
                                                <polygon key={'g' + i} points={gasPoly(p.x)} fill="#eaf7ff" stroke="#bcdcef" strokeWidth="0.6" opacity="0.55" />
                                              ))}
                                              {/* 단열간봉(스페이서) — 각 가스층 하단 */}
                                              {panes.slice(0, -1).map((p, i) => (
                                                <polygon key={'s' + i} points={`${p.x + pw},${baseY} ${p.x + pw + gap},${baseY} ${p.x + pw + gap - 2},${baseY - 11} ${p.x + pw + 2},${baseY - 11}`} fill="#3f3f46" stroke="#27272a" strokeWidth="0.6" rx="2" />
                                              ))}

                                              {/* 유리판 (바깥→실내) */}
                                              {panes.map((p, i) => (
                                                <g key={'p' + i}>
                                                  <polygon points={cap(p.x)} fill="#cfe9fb" stroke="#8fb9d6" strokeWidth="0.6" />
                                                  <polygon points={front(p.x)} fill="url(#glz-glass)" stroke="#6fb0d6" strokeWidth="0.8" />
                                                  {/* 유리 반사 하이라이트 */}
                                                  <polygon points={`${p.x},${baseY} ${p.x + 2.5},${baseY} ${p.x + 2.5 + SH},${topY} ${p.x + SH},${topY}`} fill="#ffffff" opacity="0.35" />
                                                  {/* Low-E 코팅면(실내측 표면) */}
                                                  {p.isLowEpane && <polygon points={`${p.x + pw - 1.4},${baseY} ${p.x + pw},${baseY} ${p.x + pw + SH},${topY} ${p.x + pw - 1.4 + SH},${topY}`} fill="#f5b942" opacity="0.85" />}
                                                </g>
                                              ))}

                                              {/* 라벨 + 리더선 (오른쪽 정렬) */}
                                              {labelRows.map((r, i) => {
                                                const lx = 250, ly = 30 + i * 23;
                                                return (
                                                  <g key={'l' + i} fontSize="10" fontWeight="700">
                                                    <path d={`M${r.x},${r.y} L${lx - 6},${ly}`} stroke={r.c} strokeWidth="1" fill="none" opacity="0.55" />
                                                    <circle cx={r.x} cy={r.y} r="1.8" fill={r.c} />
                                                    <text x={lx} y={ly + 3} fill="currentColor">{r.t}{/^아|^공/.test(r.t) ? '' : ''}</text>
                                                  </g>
                                                );
                                              })}
                                              {/* 방향 표기 */}
                                              <text x="40" y="24" fontSize="9" fontWeight="800" fill="#3b82f6" opacity="0.7">바깥</text>
                                              <text x={unitR + SH - 6} y="24" fontSize="9" fontWeight="800" fill="#ef4444" opacity="0.7">실내</text>
                                            </svg>
                                          </div>
                                          {/* 사양 칩 */}
                                          <div className="flex flex-wrap gap-1.5 mt-2 justify-center">
                                            <span className="text-[9px] font-bold px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-500 border border-blue-500/20">{paneCount}중 유리</span>
                                            {coated && <span className="text-[9px] font-bold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-600 border border-amber-500/20">{coatLabel} 코팅</span>}
                                            {paneCount > 1 && <span className="text-[9px] font-bold px-2 py-0.5 rounded-full bg-slate-500/10 text-slate-500 border border-slate-500/20">{gasLabel} 충전</span>}
                                            {g.u != null && <span className="text-[9px] font-black px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-600 border border-emerald-500/20">U {Number(g.u).toFixed(2)}</span>}
                                            {g.shgc != null && <span className="text-[9px] font-black px-2 py-0.5 rounded-full bg-orange-500/10 text-orange-600 border border-orange-500/20">SHGC {Number(g.shgc).toFixed(2)}</span>}
                                          </div>
                                        </>
                                      );
                                    })()}
                                  </div>
                                </div>
                              </div>
                            </>
                          )}

                          <div className={`p-6 rounded-[1.5rem] border ${theme.card} shadow-sm`}>
                            <div className="flex justify-between items-end mb-4">
                              <label className="text-sm font-black flex items-center gap-2">
                                <SlidersHorizontal size={16} className="text-orange-500" /> 외피 단열 성능 (U-Value)
                              </label>
                            </div>
                            <div className="flex items-center gap-4">
                              <input
                                type="range"
                                min="0.1"
                                max="3.0"
                                step="0.05"
                                value={editState.uValue || 0}
                                onChange={(e) =>
                                  setEditState((prev) => ({ ...prev, uValue: parseFloat(e.target.value) }))
                                }
                                className="flex-1 h-3 rounded-full appearance-none accent-orange-500 bg-slate-700 cursor-pointer"
                              />
                              <input
                                type="number"
                                min="0.1"
                                max="3.0"
                                step="0.01"
                                value={editState.uValue || 0}
                                onChange={(e) =>
                                  setEditState((prev) => ({ ...prev, uValue: parseFloat(e.target.value) || 0.1 }))
                                }
                                className={`w-24 p-2 rounded-lg font-black text-center text-orange-500 border outline-none focus:border-orange-500 ${theme.input}`}
                              />
                            </div>
                          </div>

                          {/* 💡 단열재 및 레이어 상세 정보 · 튜닝 편집기 */}
                          {materials && (selectedSurfaceData?.constructionRef || selectedSurfaceData?.constructionId) && (() => {
                            const refId = selectedSurfaceData.constructionRef || selectedSurfaceData.constructionId;
                            const construction = materials.constructions?.find(c => c.id === refId);
                            if (!construction) return null;

                            const originalInsul = construction.layers?.find(l => l.isInsulation);
                            const activeOverride = constructionOverrides[selectedSurfaceData.id];
                            
                            // 현재 선택된 제품 ID 결정
                            const activeInsulationId = activeOverride?.insulationId || (() => {
                              if (!originalInsul) return 1;
                              // 원본 conductivity에 가장 가까운 제품 자동 매칭
                              const cond = originalInsul.conductivity || 0.04;
                              const closest = INSULATION_TYPES.reduce((prev, curr) =>
                                Math.abs(curr.conductivity - cond) < Math.abs(prev.conductivity - cond) ? curr : prev
                              );
                              return closest.id;
                            })();
                            const activeProduct = INSULATION_TYPES.find(p => p.id === activeInsulationId) || INSULATION_TYPES[0];
                            const activeThickness = activeOverride ? activeOverride.thickness : (originalInsul ? originalInsul.thickness : activeProduct.defaultThickness);
                            const activeCategory = activeProduct.category;

                            // 레이어 시각화를 위한 병합 (오버라이드 값 반영)
                            let displayLayers = [];
                            if (activeOverride && activeOverride.isCustom) {
                              const getMat = (id, db) => db.find(m => m.id === id);
                              const outerM = getMat(activeOverride.outerId, STRUCTURAL_MATERIALS);
                              const insulM = getMat(activeOverride.insulId, INSULATION_TYPES);
                              const coreM = getMat(activeOverride.coreId, STRUCTURAL_MATERIALS);
                              const innerM = getMat(activeOverride.innerId, STRUCTURAL_MATERIALS);
                              
                              if (outerM) displayLayers.push({ name: outerM.name, thickness: parseFloat(activeOverride.outerThick)||0, conductivity: outerM.conductivity, isInsulation: false, category: outerM.category });
                              if (insulM) displayLayers.push({ name: insulM.name, thickness: parseFloat(activeOverride.insulThick)||0, conductivity: insulM.conductivity, isInsulation: true, category: insulM.category });
                              if (coreM) displayLayers.push({ name: coreM.name, thickness: parseFloat(activeOverride.coreThick)||0, conductivity: coreM.conductivity, isInsulation: false, category: coreM.category });
                              if (innerM) displayLayers.push({ name: innerM.name, thickness: parseFloat(activeOverride.innerThick)||0, conductivity: innerM.conductivity, isInsulation: false, category: innerM.category });
                            } else {
                              displayLayers = (construction.layers || []).map(l => {
                                if (l.isInsulation && activeOverride && activeOverride.insulationId) {
                                  return {
                                    ...l,
                                    name: activeProduct.name,
                                    thickness: activeThickness !== '' ? parseFloat(activeThickness) : 0,
                                    conductivity: activeProduct.conductivity,
                                    category: activeCategory
                                  };
                                }
                                return l;
                              });
                            }
                            const displayTotalThickness = displayLayers.reduce((sum, l) => sum + (l.thickness || 10), 0) || 100;

                            return (
                              <div className={`p-6 rounded-[1.5rem] border ${theme.card} shadow-sm space-y-4`}>
                                <div className="flex justify-between items-center border-b pb-2 mb-2 opacity-90 border-slate-700/30">
                                  <label className="text-sm font-black flex items-center gap-2">
                                    <Layers size={16} className="text-orange-500" /> 구조체 단면도 · 단열재 교체
                                  </label>
                                  <span className="text-[10px] font-mono opacity-50">{construction.id}</span>
                                </div>
                                
                                <div className="space-y-2">
                                  <p className="text-xs font-bold">구조체명: <span className="text-blue-500">{construction.name}</span></p>
                                  
                                  {/* 🧱 벽체 단면 시각화 (수직형, 그림 스타일) */}
                                  {displayLayers.length > 0 ? (
                                    <div className="rounded-xl overflow-hidden border-2 border-slate-500/30 shadow-inner bg-black/5">
                                      {/* 방향 라벨: Outer Surface */}
                                      <div className="text-center py-2 text-[10px] font-black tracking-widest text-blue-500/70 border-b-2 border-slate-500/30 bg-white/5">
                                        OUTER SURFACE (바깥쪽)
                                      </div>
                                      
                                      {/* 수직 단면 스택 */}
                                      <div className="flex flex-col w-full">
                                        {displayLayers.map((l, idx) => {
                                          const t = l.thickness || 10;
                                          // 최소 40px, 비례에 따라 높이 결정
                                          const heightPx = Math.max(45, (t / displayTotalThickness) * 200);
                                          const color = getLayerColor(l.name, l.isInsulation, l.category);
                                          const isInsulLayer = l.isInsulation;
                                          
                                          return (
                                            <div
                                              key={idx}
                                              className={`relative flex flex-col items-center justify-center border-b border-slate-500/30 transition-all duration-300 ${isInsulLayer ? 'ring-2 ring-orange-400/80 ring-inset z-10' : ''}`}
                                              style={{
                                                height: `${heightPx}px`,
                                                backgroundColor: color.bg,
                                              }}
                                              title={`${l.name || '레이어'} — ${t}mm${l.conductivity ? `, λ=${l.conductivity}` : ''}`}
                                            >
                                              {/* 텍스처 오버레이 */}
                                              {isInsulLayer ? (
                                                <div className="absolute inset-0 opacity-20 pointer-events-none" style={{
                                                  backgroundImage: 'repeating-linear-gradient(45deg, transparent, transparent 5px, rgba(0,0,0,0.3) 5px, rgba(0,0,0,0.3) 10px)'
                                                }}></div>
                                              ) : (
                                                <div className="absolute inset-0 opacity-10 pointer-events-none" style={{
                                                  backgroundImage: 'radial-gradient(circle, #000 1px, transparent 1px)',
                                                  backgroundSize: '8px 8px'
                                                }}></div>
                                              )}
                                              
                                              {/* 레이어 텍스트 */}
                                              <div className="z-10 flex flex-col items-center justify-center text-center px-4 w-full" style={{ color: color.text || '#111' }}>
                                                <span className="text-[11px] font-black drop-shadow-sm truncate w-full">
                                                  {t}mm {l.name || 'Unknown Layer'}
                                                </span>
                                                {isInsulLayer && (
                                                  <span className="text-[9px] font-bold opacity-90 mt-1 bg-white/40 px-2 py-0.5 rounded-full border border-black/10">
                                                    λ={l.conductivity || '?'} W/m·K
                                                  </span>
                                                )}
                                              </div>
                                            </div>
                                          );
                                        })}
                                      </div>

                                      {/* 방향 라벨: Inner Surface */}
                                      <div className="text-center py-2 text-[10px] font-black tracking-widest text-red-500/70 border-t-2 border-slate-500/30 bg-white/5">
                                        INNER SURFACE (안쪽)
                                      </div>
                                    </div>
                                  ) : (
                                    <p className="opacity-50 text-xs text-center py-4">레이어 정보가 없습니다.</p>
                                  )}
                                </div>

                                {/* 🔧 구조체 전면 튜닝 (4-Layer) & 단열재 교체 */}
                                <div className="p-4 rounded-xl border border-orange-500/15 bg-gradient-to-br from-orange-500/5 to-amber-500/5 space-y-3">
                                  <div className="flex justify-between items-center mb-2">
                                    <span className="text-xs font-black text-orange-500 flex items-center gap-1.5">
                                      <SlidersHorizontal size={13} /> {activeOverride?.isCustom ? '구조체 전면 튜닝' : '단열재 교체'}
                                    </span>
                                    <div className="flex items-center gap-3">
                                      {/* 커스텀 토글 스위치 */}
                                      <label className="flex items-center cursor-pointer gap-1.5">
                                        <div className="relative">
                                          <input 
                                            type="checkbox" 
                                            className="sr-only" 
                                            checked={activeOverride?.isCustom || false}
                                            onChange={(e) => {
                                              const isCustom = e.target.checked;
                                              if (isCustom) {
                                                handleConstructionOverrideChange(selectedSurfaceData.id, construction.id, {
                                                  isCustom: true,
                                                  outerId: 'O1', outerThick: 90,
                                                  insulId: activeInsulationId || 1, insulThick: activeThickness || 100,
                                                  coreId: 'C1', coreThick: 200,
                                                  innerId: 'I1', innerThick: 9.5
                                                });
                                              } else {
                                                // 커스텀 해제 시 기존 단열재 값만 유지
                                                handleConstructionOverrideChange(selectedSurfaceData.id, construction.id, {
                                                  isCustom: false,
                                                  insulationId: activeInsulationId || 1, 
                                                  thickness: activeThickness || 100
                                                });
                                              }
                                            }}
                                          />
                                          <div className={`block w-8 h-4.5 rounded-full ${activeOverride?.isCustom ? 'bg-orange-500' : 'bg-slate-600'}`}></div>
                                          <div className={`dot absolute left-0.5 top-0.5 bg-white w-3.5 h-3.5 rounded-full transition-transform ${activeOverride?.isCustom ? 'transform translate-x-3.5' : ''}`}></div>
                                        </div>
                                        <span className="text-[10px] font-bold opacity-80">전면 커스텀</span>
                                      </label>
                                      
                                      {activeOverride && (
                                        <button 
                                          onClick={() => handleResetInsulationOverride(selectedSurfaceData.id, construction.id)}
                                          className="text-[10px] text-red-400 hover:text-red-300 underline font-bold ml-2"
                                        >
                                          초기화
                                        </button>
                                      )}
                                    </div>
                                  </div>
                                  
                                  {/* 4중 레이어 커스텀 모드 UI */}
                                  {activeOverride?.isCustom ? (
                                    <div className="space-y-3">
                                      {/* 1. 외장재 */}
                                      <div className="flex gap-2">
                                        <div className="flex-1">
                                          <label className="text-[9px] font-black opacity-60 block mb-1 text-blue-400">1. 외장재</label>
                                          <select
                                            value={activeOverride.outerId}
                                            onChange={(e) => handleConstructionOverrideChange(selectedSurfaceData.id, construction.id, { outerId: e.target.value })}
                                            className={`w-full p-2 text-[10px] font-bold rounded border outline-none ${theme.input} focus:border-blue-500`}
                                          >
                                            {getMaterialsByCategory('OUTER').map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
                                          </select>
                                        </div>
                                        <div className="w-20">
                                          <label className="text-[9px] font-black opacity-60 block mb-1">두께(mm)</label>
                                          <input type="number" min="0" value={activeOverride.outerThick} onChange={(e) => handleConstructionOverrideChange(selectedSurfaceData.id, construction.id, { outerThick: parseFloat(e.target.value)||0 })} className={`w-full p-2 text-[10px] font-bold rounded border outline-none ${theme.input}`} />
                                        </div>
                                      </div>
                                      
                                      {/* 2. 단열재 (기존 로직 재사용) */}
                                      <div className="flex gap-2">
                                        <div className="flex-1">
                                          <label className="text-[9px] font-black opacity-60 block mb-1 text-orange-400">2. 단열재</label>
                                          <select
                                            value={activeOverride.insulId}
                                            onChange={(e) => handleConstructionOverrideChange(selectedSurfaceData.id, construction.id, { insulId: parseInt(e.target.value) })}
                                            className={`w-full p-2 text-[10px] font-bold rounded border outline-none ${theme.input} focus:border-orange-500`}
                                          >
                                            {INSULATION_TYPES.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
                                          </select>
                                        </div>
                                        <div className="w-20">
                                          <label className="text-[9px] font-black opacity-60 block mb-1">두께(mm)</label>
                                          <input type="number" min="0" value={activeOverride.insulThick} onChange={(e) => handleConstructionOverrideChange(selectedSurfaceData.id, construction.id, { insulThick: parseFloat(e.target.value)||0 })} className={`w-full p-2 text-[10px] font-bold rounded border outline-none ${theme.input}`} />
                                        </div>
                                      </div>
                                      
                                      {/* 3. 구조체 */}
                                      <div className="flex gap-2">
                                        <div className="flex-1">
                                          <label className="text-[9px] font-black opacity-60 block mb-1 text-slate-400">3. 구조체 (Core)</label>
                                          <select
                                            value={activeOverride.coreId}
                                            onChange={(e) => handleConstructionOverrideChange(selectedSurfaceData.id, construction.id, { coreId: e.target.value })}
                                            className={`w-full p-2 text-[10px] font-bold rounded border outline-none ${theme.input} focus:border-slate-500`}
                                          >
                                            {getMaterialsByCategory('CORE').map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
                                          </select>
                                        </div>
                                        <div className="w-20">
                                          <label className="text-[9px] font-black opacity-60 block mb-1">두께(mm)</label>
                                          <input type="number" min="0" value={activeOverride.coreThick} onChange={(e) => handleConstructionOverrideChange(selectedSurfaceData.id, construction.id, { coreThick: parseFloat(e.target.value)||0 })} className={`w-full p-2 text-[10px] font-bold rounded border outline-none ${theme.input}`} />
                                        </div>
                                      </div>

                                      {/* 4. 내장재 */}
                                      <div className="flex gap-2">
                                        <div className="flex-1">
                                          <label className="text-[9px] font-black opacity-60 block mb-1 text-red-400">4. 내장재</label>
                                          <select
                                            value={activeOverride.innerId}
                                            onChange={(e) => handleConstructionOverrideChange(selectedSurfaceData.id, construction.id, { innerId: e.target.value })}
                                            className={`w-full p-2 text-[10px] font-bold rounded border outline-none ${theme.input} focus:border-red-500`}
                                          >
                                            {getMaterialsByCategory('INNER').map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
                                          </select>
                                        </div>
                                        <div className="w-20">
                                          <label className="text-[9px] font-black opacity-60 block mb-1">두께(mm)</label>
                                          <input type="number" min="0" value={activeOverride.innerThick} onChange={(e) => handleConstructionOverrideChange(selectedSurfaceData.id, construction.id, { innerThick: parseFloat(e.target.value)||0 })} className={`w-full p-2 text-[10px] font-bold rounded border outline-none ${theme.input}`} />
                                        </div>
                                      </div>
                                    </div>
                                  ) : (
                                    /* 기본 단열재 단독 교체 UI */
                                    <div className="space-y-2.5">
                                      <div>
                                        <label className="text-[9px] font-black opacity-60 block mb-1">① 단열재 종류</label>
                                        <select
                                          value={activeCategory}
                                          onChange={(e) => {
                                            const catProducts = INSULATION_TYPES.filter(p => p.category === e.target.value);
                                            if (catProducts.length > 0) {
                                              handleConstructionOverrideChange(selectedSurfaceData.id, construction.id, { insulationId: catProducts[0].id, thickness: activeThickness });
                                            }
                                          }}
                                          className={`w-full p-2.5 text-[11px] font-bold rounded-lg border outline-none ${theme.input} focus:border-orange-500`}
                                        >
                                          {Object.entries(INSULATION_CATEGORIES).map(([key, label]) => (
                                            <option key={key} value={key}>{label}</option>
                                          ))}
                                        </select>
                                      </div>
                                      
                                      <div>
                                        <label className="text-[9px] font-black opacity-60 block mb-1">② 세부 제품</label>
                                        <select
                                          value={activeInsulationId}
                                          onChange={(e) => {
                                            const prodId = parseInt(e.target.value);
                                            const prod = INSULATION_TYPES.find(p => p.id === prodId);
                                            handleConstructionOverrideChange(construction.id, { insulationId: prodId, thickness: activeThickness || prod?.defaultThickness || 100 });
                                          }}
                                          className={`w-full p-2.5 text-[11px] font-bold rounded-lg border outline-none ${theme.input} focus:border-orange-500`}
                                        >
                                          {INSULATION_TYPES.filter(p => p.category === activeCategory).map((p) => (
                                            <option key={p.id} value={p.id}>
                                              {p.name} (λ={p.conductivity}, {p.density}kg/m³)
                                            </option>
                                          ))}
                                        </select>
                                      </div>

                                      <div>
                                        <label className="text-[9px] font-black opacity-60 block mb-1">③ 두께 (mm)</label>
                                        <div className="relative">
                                          <input
                                            type="number"
                                            min="10"
                                            max="500"
                                            step="5"
                                            value={activeThickness}
                                            onChange={(e) => handleConstructionOverrideChange(selectedSurfaceData.id, construction.id, { insulationId: activeInsulationId, thickness: parseFloat(e.target.value) || 0 })}
                                            className={`w-full p-2.5 pl-3 pr-10 text-[11px] font-bold rounded-lg border outline-none ${theme.input} focus:border-orange-500 text-center`}
                                          />
                                          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[9px] opacity-40">mm</span>
                                        </div>
                                      </div>
                                    </div>
                                  )}

                                  {/* 결과 표시 */}
                                  <div className={`p-3 rounded-lg text-center space-y-1 ${activeOverride ? 'bg-emerald-500/10 border border-emerald-500/20' : 'bg-black/5 border border-white/5'}`}>
                                    {activeOverride?.isCustom ? (
                                      <p className="text-[10px] font-bold opacity-80">
                                        구조체 4중 레이어 커스텀 모드 활성화 됨
                                      </p>
                                    ) : (
                                      <p className="text-[10px] font-bold opacity-60">
                                        단열재 단독: <span className="text-orange-500">{activeProduct.name}</span> · {activeThickness}mm · λ={activeProduct.conductivity}
                                      </p>
                                    )}
                                    {activeOverride ? (
                                      <p className="text-[11px] text-emerald-400 font-black mt-1">
                                        ✓ U-value: {calculateUpdatedUValue(construction, null) || '?'} → {calculateUpdatedUValue(construction, activeOverride) || '?'} W/m²K
                                      </p>
                                    ) : (
                                      <p className="text-[10px] opacity-50 mt-1">값을 변경하면 U-Value가 자동 재계산됩니다.</p>
                                    )}
                                  </div>
                                </div>
                              </div>
                            );
                          })()}
                        </div>
                      )}

                      <button
                        onClick={handleSaveClose}
                        className={`w-full py-5 text-white rounded-[1.5rem] font-black text-lg shadow-xl flex items-center justify-center gap-3 transition-transform hover:scale-105 mt-8 ${
                          editMode === 'zone'
                            ? 'bg-emerald-600 hover:bg-emerald-500 shadow-emerald-500/30'
                            : 'bg-blue-600 hover:bg-blue-500 shadow-blue-500/30'
                        }`}
                      >
                        <Save size={24} /> 설정 사항 저장 및 닫기
                      </button>
                      <p className="text-center text-[10px] text-slate-500 font-bold">
                        * 저장을 누르셔야 시뮬레이션 엔진에 최종 반영됩니다.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </div>
  );
}
