import React, { useState, useRef } from 'react';
import { Calendar, Clock, Plus, X, AlertCircle } from 'lucide-react';

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
  const [newHoliday, setNewHoliday] = useState("");

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

  const addHoliday = () => {
    if (!newHoliday) return;
    // Format check (MM/DD)
    if (!/^\d{2}\/\d{2}$/.test(newHoliday)) {
      alert("MM/DD 형식으로 입력해주세요 (예: 12/25)");
      return;
    }
    
    if (!value.holidays.includes(newHoliday)) {
      onChange({
        ...value,
        holidays: [...value.holidays, newHoliday].sort()
      });
    }
    setNewHoliday("");
  };

  const removeHoliday = (date) => {
    onChange({
      ...value,
      holidays: value.holidays.filter(h => h !== date)
    });
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

  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden shadow-sm">
      <div className="p-4 bg-slate-50 dark:bg-slate-800/50 border-b border-slate-200 dark:border-slate-800">
        <h3 className="text-lg font-bold text-slate-800 dark:text-white flex items-center gap-2">
          <Clock className="text-indigo-500" />
          프리미엄 스케줄 에디터
        </h3>
        <p className="text-sm text-slate-500 mt-1">
          24시간 운영 스케줄과 공휴일을 세밀하게 커스텀합니다. (eQUEST 인터랙티브 차트 방식)
        </p>
      </div>

      <div className="p-5 flex flex-col lg:flex-row gap-6">
        
        {/* 왼쪽: 24시간 프로필 에디터 */}
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

        {/* 오른쪽: 공휴일 지정기 */}
        <div className="w-full lg:w-72 bg-slate-50 dark:bg-slate-800/50 rounded-xl p-4 border border-slate-200 dark:border-slate-700 h-fit">
          <h4 className="text-sm font-bold text-slate-700 dark:text-slate-200 flex items-center gap-2 mb-4">
            <Calendar size={16} className="text-indigo-500" />
            특별 휴일 지정
          </h4>
          
          <div className="flex gap-2 mb-4">
            <input 
              type="text" 
              placeholder="MM/DD (예: 08/15)" 
              value={newHoliday}
              onChange={(e) => setNewHoliday(e.target.value)}
              className="flex-1 bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 rounded-lg px-3 py-1.5 text-sm outline-none focus:border-indigo-500"
              maxLength={5}
            />
            <button 
              onClick={addHoliday}
              className="bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg p-1.5 flex items-center justify-center transition-colors"
            >
              <Plus size={18} />
            </button>
          </div>

          <button 
            onClick={addKoreanHolidays}
            className="w-full py-2 bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-200 rounded-lg text-xs font-semibold mb-4 hover:bg-slate-50 dark:hover:bg-slate-600 transition-colors"
          >
            🇰🇷 대한민국 기본 공휴일 일괄 추가
          </button>

          <div className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 max-h-64 overflow-y-auto">
            {value.holidays.length === 0 ? (
              <div className="p-4 text-center text-sm text-slate-400">
                지정된 휴일이 없습니다.
              </div>
            ) : (
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {value.holidays.map(date => {
                  const koreanInfo = KOREAN_HOLIDAYS.find(h => h.date === date);
                  return (
                    <li key={date} className="flex justify-between items-center p-3 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors">
                      <div className="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-200">
                        <span className="text-indigo-500">{date}</span>
                        {koreanInfo && <span className="text-xs font-normal text-slate-400 bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded-full">{koreanInfo.name}</span>}
                      </div>
                      <button onClick={() => removeHoliday(date)} className="text-slate-400 hover:text-red-500 transition-colors">
                        <X size={16} />
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
          
          <div className="mt-4 p-3 bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 rounded-lg text-xs flex gap-2 items-start">
            <AlertCircle size={14} className="shrink-0 mt-0.5" />
            <p>지정된 휴일에는 시뮬레이션 시 <strong>[공휴일]</strong> 탭의 스케줄 프로필이 우선 적용됩니다.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
