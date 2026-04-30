import React, { useState, useRef } from 'react';
import { Calendar, Clock, Plus, X, AlertCircle, ChevronLeft, ChevronRight } from 'lucide-react';

const KOREAN_HOLIDAYS = [
  { date: "01/01", name: "신정" },
  { date: "03/01", name: "삼일절" },
  { date: "05/05", name: "어린이날" },
  { date: "06/06", name: "현충일" },
  { date: "08/15", name: "광복절" },
  { date: "10/03", name: "개천절" },
  { date: "10/09", name: "한글날" },
  { date: "12/25", name: "기독탄신일" }
];

// 24시간 드래그 가능한 막대 차트 컴포넌트
const InteractiveHourlyChart = ({ title, data, onChange, min, max, unit, colorClass }) => {
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef(null);

  const updateValue = (e, index) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const y = e.clientY - rect.top;
    const percentage = Math.max(0, Math.min(1, 1 - (y / rect.height)));
    
    // 값 보정
    let newValue = min + (max - min) * percentage;
    
    // 소수점 1자리로 반올림
    if (unit !== "%") {
      newValue = Math.round(newValue * 2) / 2; // 0.5도 단위
    } else {
      newValue = Math.round(newValue * 100) / 100; // 0.01 단위
    }

    const newData = [...data];
    newData[index] = newValue;
    onChange(newData);
  };

  const handleMouseDown = (e, index) => {
    setIsDragging(true);
    updateValue(e, index);
  };

  const handleMouseEnter = (e, index) => {
    if (isDragging) {
      updateValue(e, index);
    }
  };

  const handleMouseUp = () => {
    setIsDragging(false);
  };

  return (
    <div className="mb-8" onMouseUp={handleMouseUp} onMouseLeave={handleMouseUp}>
      <div className="flex justify-between items-center mb-2">
        <h4 className="text-sm font-semibold text-slate-700 dark:text-slate-200">{title}</h4>
        <span className="text-xs text-slate-500">마우스로 막대를 드래그하세요</span>
      </div>
      <div 
        ref={containerRef}
        className="relative h-32 w-full bg-slate-100 dark:bg-slate-800 rounded-lg flex items-end overflow-hidden p-1 select-none border border-slate-200 dark:border-slate-700"
      >
        {/* Y-axis guidelines */}
        <div className="absolute inset-0 flex flex-col justify-between pointer-events-none opacity-20 py-1">
          <div className="w-full border-t border-slate-400"></div>
          <div className="w-full border-t border-slate-400"></div>
          <div className="w-full border-t border-slate-400"></div>
          <div className="w-full border-t border-slate-400"></div>
        </div>

        {/* Y-axis labels */}
        <div className="absolute left-2 top-0 h-full flex flex-col justify-between py-1 text-[10px] text-slate-400 pointer-events-none">
          <span>{unit === "%" ? "100%" : `${max}${unit}`}</span>
          <span>{unit === "%" ? "0%" : `${min}${unit}`}</span>
        </div>

        {/* Bars */}
        <div className="w-full h-full flex items-end gap-[2px] ml-8 z-10">
          {data.map((val, i) => {
            const heightPercent = Math.max(0, Math.min(100, ((val - min) / (max - min)) * 100));
            return (
              <div 
                key={i}
                className="flex-1 flex flex-col items-center justify-end h-full group"
                onMouseDown={(e) => handleMouseDown(e, i)}
                onMouseEnter={(e) => handleMouseEnter(e, i)}
              >
                {/* Tooltip on hover */}
                <div className="opacity-0 group-hover:opacity-100 absolute top-[-25px] bg-slate-800 text-white text-[10px] py-0.5 px-1.5 rounded z-20 pointer-events-none whitespace-nowrap transition-opacity">
                  {i}시: {unit === "%" ? `${Math.round(val * 100)}%` : `${val}${unit}`}
                </div>
                
                {/* Bar */}
                <div 
                  className={`w-full rounded-t-sm cursor-ns-resize transition-all duration-75 ${colorClass}`}
                  style={{ height: `${heightPercent}%` }}
                ></div>
                
                {/* X-axis label (only every 3 hours) */}
                {(i % 3 === 0) && (
                  <span className="absolute -bottom-5 text-[10px] text-slate-400 pointer-events-none">{i}h</span>
                )}
              </div>
            );
          })}
        </div>
      </div>
      <div className="h-5"></div> {/* Spacer for x-axis labels */}
    </div>
  );
};

export default function ScheduleEditor({ value, onChange }) {
  const [activeTab, setActiveTab] = useState('weekday');
  const [currentDate, setCurrentDate] = useState(new Date(new Date().getFullYear(), 0, 1));

  const handleProfileChange = (metric, newData) => {
    onChange({
      ...value,
      profiles: {
        ...value.profiles,
        [activeTab]: {
          ...value.profiles[activeTab],
          [metric]: newData
        }
      }
    });
  };

  const updateProfileFromSimplified = (tab, params) => {
    const { openTime, closeTime, heatOcc, heatUnocc, coolOcc, coolUnocc, opOcc, opUnocc } = params;
    const newHeating = Array(24).fill(heatUnocc);
    const newCooling = Array(24).fill(coolUnocc);
    const newOp = Array(24).fill(opUnocc);

    for (let i = 0; i < 24; i++) {
      if (openTime < closeTime) {
        if (i >= openTime && i < closeTime) {
          newHeating[i] = heatOcc;
          newCooling[i] = coolOcc;
          newOp[i] = opOcc;
        }
      } else if (openTime > closeTime) { 
        if (i >= openTime || i < closeTime) {
          newHeating[i] = heatOcc;
          newCooling[i] = coolOcc;
          newOp[i] = opOcc;
        }
      }
    }
    
    return { heating: newHeating, cooling: newCooling, operation: newOp };
  };

  const handleSimplifiedChange = (tab, field, val) => {
    const parsedVal = isNaN(val) ? 0 : val;
    const newParams = { ...value.simplifiedParams[tab], [field]: parsedVal };
    const newProfiles = updateProfileFromSimplified(tab, newParams);
    
    onChange({
      ...value,
      simplifiedParams: {
        ...value.simplifiedParams,
        [tab]: newParams
      },
      profiles: {
        ...value.profiles,
        [tab]: newProfiles
      }
    });
  };

  const renderSimplifiedUI = () => {
    const p = value.simplifiedParams[activeTab];
    return (
      <div className="space-y-6">
        <div className="p-5 bg-slate-50 dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700">
          <h4 className="text-sm font-bold text-slate-700 dark:text-slate-200 flex items-center gap-2 mb-4">
            <Clock size={16} className="text-indigo-500" />
            운영 시간 (Operating Hours)
          </h4>
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-2">시작 시간 (Opens at)</label>
              <select value={p.openTime} onChange={e => handleSimplifiedChange(activeTab, 'openTime', parseInt(e.target.value))} className="w-full p-2.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 text-sm font-medium outline-none focus:border-indigo-500">
                {Array(24).fill().map((_, i) => <option key={i} value={i}>{i.toString().padStart(2, '0')}:00</option>)}
              </select>
            </div>
            <span className="text-slate-400 mt-6 font-bold">~</span>
            <div className="flex-1">
              <label className="block text-xs font-semibold text-slate-500 dark:text-slate-400 mb-2">종료 시간 (Closes at)</label>
              <select value={p.closeTime} onChange={e => handleSimplifiedChange(activeTab, 'closeTime', parseInt(e.target.value))} className="w-full p-2.5 rounded-lg bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 text-sm font-medium outline-none focus:border-indigo-500">
                {Array(25).fill().map((_, i) => <option key={i} value={i}>{i.toString().padStart(2, '0')}:00</option>)}
              </select>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="p-5 bg-red-50 dark:bg-red-900/10 rounded-xl border border-red-200 dark:border-red-900/30">
            <h4 className="text-sm font-bold text-red-600 dark:text-red-400 mb-4">🔥 난방 온도 설정 (℃)</h4>
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">운영 중 (Occupied)</span>
                <input type="number" value={p.heatOcc} onChange={e => handleSimplifiedChange(activeTab, 'heatOcc', parseFloat(e.target.value))} className="w-24 p-2 text-right rounded-lg bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 font-bold outline-none focus:border-red-400" />
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">비운영 중 (Unoccupied)</span>
                <input type="number" value={p.heatUnocc} onChange={e => handleSimplifiedChange(activeTab, 'heatUnocc', parseFloat(e.target.value))} className="w-24 p-2 text-right rounded-lg bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 font-bold outline-none focus:border-red-400" />
              </div>
            </div>
          </div>

          <div className="p-5 bg-blue-50 dark:bg-blue-900/10 rounded-xl border border-blue-200 dark:border-blue-900/30">
            <h4 className="text-sm font-bold text-blue-600 dark:text-blue-400 mb-4">❄️ 냉방 온도 설정 (℃)</h4>
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">운영 중 (Occupied)</span>
                <input type="number" value={p.coolOcc} onChange={e => handleSimplifiedChange(activeTab, 'coolOcc', parseFloat(e.target.value))} className="w-24 p-2 text-right rounded-lg bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 font-bold outline-none focus:border-blue-400" />
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">비운영 중 (Unoccupied)</span>
                <input type="number" value={p.coolUnocc} onChange={e => handleSimplifiedChange(activeTab, 'coolUnocc', parseFloat(e.target.value))} className="w-24 p-2 text-right rounded-lg bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 font-bold outline-none focus:border-blue-400" />
              </div>
            </div>
          </div>

          <div className="p-5 md:col-span-2 bg-emerald-50 dark:bg-emerald-900/10 rounded-xl border border-emerald-200 dark:border-emerald-900/30">
            <h4 className="text-sm font-bold text-emerald-600 dark:text-emerald-400 mb-4">💡 내부 부하 운영률 (조명/기기)</h4>
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">운영 중 (Occupied) <span className="text-xs font-normal text-slate-500 ml-1">[0~1.0]</span></span>
                <input type="number" step="0.1" min="0" max="1" value={p.opOcc} onChange={e => handleSimplifiedChange(activeTab, 'opOcc', parseFloat(e.target.value))} className="w-24 p-2 text-right rounded-lg bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 font-bold outline-none focus:border-emerald-400" />
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">비운영 중 (Unoccupied) <span className="text-xs font-normal text-slate-500 ml-1">[0~1.0]</span></span>
                <input type="number" step="0.1" min="0" max="1" value={p.opUnocc} onChange={e => handleSimplifiedChange(activeTab, 'opUnocc', parseFloat(e.target.value))} className="w-24 p-2 text-right rounded-lg bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 font-bold outline-none focus:border-emerald-400" />
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const prevMonth = () => {
    setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() - 1, 1));
  };
  const nextMonth = () => {
    setCurrentDate(new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 1));
  };

  const toggleHoliday = (dateStr) => {
    if (value.holidays.includes(dateStr)) {
      onChange({ ...value, holidays: value.holidays.filter(h => h !== dateStr) });
    } else {
      onChange({ ...value, holidays: [...value.holidays, dateStr].sort() });
    }
  };

  const addKoreanHolidays = () => {
    const newHolidays = [...value.holidays];
    let added = false;
    KOREAN_HOLIDAYS.forEach(h => {
      if (!newHolidays.includes(h.date)) {
        newHolidays.push(h.date);
        added = true;
      }
    });
    if (added) {
      onChange({
        ...value,
        holidays: newHolidays.sort()
      });
    }
  };

  const renderCalendar = () => {
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();
    
    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    
    const days = [];
    for (let i = 0; i < firstDay; i++) days.push(null);
    for (let i = 1; i <= daysInMonth; i++) days.push(i);

    const monthStr = (month + 1).toString().padStart(2, '0');

    return (
      <div className="mt-8 border-t border-slate-200 dark:border-slate-700 pt-6 animate-in fade-in slide-in-from-bottom-2">
        <div className="flex flex-col md:flex-row gap-6">
          {/* Calendar Left */}
          <div className="flex-1 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5 shadow-sm">
            <div className="flex justify-between items-center mb-6">
              <button onClick={prevMonth} className="p-2 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg text-slate-500 transition-colors">
                <ChevronLeft size={20} />
              </button>
              <h4 className="text-lg font-black text-slate-800 dark:text-slate-100">
                {month + 1}월
              </h4>
              <button onClick={nextMonth} className="p-2 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg text-slate-500 transition-colors">
                <ChevronRight size={20} />
              </button>
            </div>

            <div className="grid grid-cols-7 gap-2 text-center mb-2">
              {['일', '월', '화', '수', '목', '금', '토'].map((day, i) => (
                <div key={day} className={`text-xs font-bold ${i === 0 ? 'text-red-500' : i === 6 ? 'text-blue-500' : 'text-slate-400'}`}>
                  {day}
                </div>
              ))}
            </div>
            
            <div className="grid grid-cols-7 gap-2">
              {days.map((day, idx) => {
                if (!day) return <div key={`empty-${idx}`} className="h-10" />;
                
                const dayStr = day.toString().padStart(2, '0');
                const dateStr = `${monthStr}/${dayStr}`;
                const isHoliday = value.holidays.includes(dateStr);
                const isKoreanHoliday = KOREAN_HOLIDAYS.find(h => h.date === dateStr);

                return (
                  <button
                    key={dateStr}
                    onClick={() => toggleHoliday(dateStr)}
                    className={`relative h-10 rounded-lg flex items-center justify-center text-sm font-medium transition-all group
                      ${isHoliday 
                        ? 'bg-red-500 hover:bg-red-600 text-white shadow-md shadow-red-500/30' 
                        : 'bg-slate-50 dark:bg-slate-900 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-800'
                      }`}
                  >
                    {day}
                    {isKoreanHoliday && !isHoliday && (
                      <span className="absolute bottom-1 w-1 h-1 rounded-full bg-red-400"></span>
                    )}
                    {isKoreanHoliday && (
                      <div className="absolute opacity-0 group-hover:opacity-100 -top-8 left-1/2 -translate-x-1/2 bg-slate-800 text-white text-[10px] py-1 px-2 rounded whitespace-nowrap z-10 pointer-events-none transition-opacity">
                        {isKoreanHoliday.name}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Right Info Panel */}
          <div className="w-full md:w-72 flex flex-col gap-4">
            <div className="bg-slate-50 dark:bg-slate-800/50 rounded-xl p-5 border border-slate-200 dark:border-slate-700">
              <h4 className="text-sm font-bold text-slate-700 dark:text-slate-200 flex items-center gap-2 mb-4">
                <Calendar size={18} className="text-red-500" />
                지정된 특별 휴일 ({value.holidays.length}일)
              </h4>
              <button 
                onClick={addKoreanHolidays}
                className="w-full py-2.5 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-200 rounded-lg text-xs font-bold mb-4 hover:bg-slate-100 dark:hover:bg-slate-600 shadow-sm transition-all flex items-center justify-center gap-2"
              >
                🇰🇷 대한민국 기본 공휴일 일괄 추가
              </button>
              
              <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 h-48 overflow-y-auto p-2">
                {value.holidays.length === 0 ? (
                  <div className="h-full flex items-center justify-center text-sm text-slate-400">
                    지정된 휴일이 없습니다.
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {value.holidays.map(date => {
                      const kHoliday = KOREAN_HOLIDAYS.find(h => h.date === date);
                      return (
                        <div key={date} className="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/20 text-red-600 dark:text-red-400 px-2.5 py-1 rounded-md text-xs font-bold flex items-center gap-1.5">
                          {date}
                          {kHoliday && <span className="opacity-60 font-normal">({kHoliday.name})</span>}
                          <button onClick={() => toggleHoliday(date)} className="hover:text-red-800 dark:hover:text-red-300 ml-1">
                            <X size={12} />
                          </button>
                        </div>
                      )
                    })}
                  </div>
                )}
              </div>
            </div>
            
            <div className="p-4 bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 rounded-xl text-xs flex gap-3 items-start border border-blue-100 dark:border-blue-900/30">
              <AlertCircle size={16} className="shrink-0 mt-0.5" />
              <p className="leading-relaxed">달력에서 지정된 날짜에는 일반 스케줄을 무시하고, 현재 설정된 <strong>[공휴일]</strong> 스케줄이 최우선으로 적용됩니다.</p>
            </div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden shadow-sm">
      <div className="p-4 bg-slate-50 dark:bg-slate-800/50 border-b border-slate-200 dark:border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h3 className="text-lg font-bold text-slate-800 dark:text-white flex items-center gap-2">
            <Clock className="text-indigo-500" />
            프리미엄 스케줄 에디터
          </h3>
          <p className="text-sm text-slate-500 mt-1">
            24시간 운영 스케줄을 간편하게 설정하거나 상세 차트로 커스텀합니다.
          </p>
        </div>
        
        <div className="flex bg-slate-200 dark:bg-slate-800 p-1 rounded-lg w-fit">
          <button 
            onClick={() => onChange({ ...value, mode: 'simplified' })}
            className={`px-4 py-1.5 text-sm font-bold rounded-md transition-all ${value.mode === 'simplified' ? 'bg-white dark:bg-slate-700 text-indigo-600 dark:text-indigo-400 shadow-sm' : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'}`}
          >
            간편 설정 (Simplified)
          </button>
          <button 
            onClick={() => onChange({ ...value, mode: 'detailed' })}
            className={`px-4 py-1.5 text-sm font-bold rounded-md transition-all ${value.mode === 'detailed' ? 'bg-white dark:bg-slate-700 text-indigo-600 dark:text-indigo-400 shadow-sm' : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'}`}
          >
            상세 설정 (Hourly)
          </button>
        </div>
      </div>

      <div className="p-5 flex flex-col lg:flex-row gap-6">
        
        {/* 24시간 프로필 에디터 */}
        <div className="flex-1">
          {/* Tabs */}
          <div className="flex p-1 bg-slate-100 dark:bg-slate-800 rounded-lg mb-6">
            {[
              { id: 'weekday', label: '평일 (Weekday)' },
              { id: 'weekend', label: '주말 (Weekend)' },
              { id: 'holiday', label: '공휴일 (Holiday)' }
            ].map(tab => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex-1 py-2 text-sm font-medium rounded-md transition-all ${
                  activeTab === tab.id 
                    ? 'bg-white dark:bg-slate-700 text-indigo-600 dark:text-indigo-400 shadow-sm' 
                    : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {value.mode === 'simplified' ? (
            renderSimplifiedUI()
          ) : (
            <div className="animate-in fade-in slide-in-from-bottom-2">
              <InteractiveHourlyChart 
                title="🔥 난방 설정 온도 (Heating Setpoint)" 
                data={value.profiles[activeTab].heating} 
                onChange={(d) => handleProfileChange('heating', d)} 
                min={10} max={30} unit="℃" 
                colorClass="bg-red-400 hover:bg-red-500" 
              />
              
              <InteractiveHourlyChart 
                title="❄️ 냉방 설정 온도 (Cooling Setpoint)" 
                data={value.profiles[activeTab].cooling} 
                onChange={(d) => handleProfileChange('cooling', d)} 
                min={15} max={35} unit="℃" 
                colorClass="bg-blue-400 hover:bg-blue-500" 
              />

              <InteractiveHourlyChart 
                title="💡 내부 부하 운영률 (Lighting/Equipment/People)" 
                data={value.profiles[activeTab].operation} 
                onChange={(d) => handleProfileChange('operation', d)} 
                min={0} max={1} unit="%" 
                colorClass="bg-emerald-400 hover:bg-emerald-500" 
              />
            </div>
          )}

          {activeTab === 'holiday' && renderCalendar()}
        </div>
      </div>
    </div>
  );
}
