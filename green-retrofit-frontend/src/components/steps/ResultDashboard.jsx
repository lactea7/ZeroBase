import React, { useState } from 'react';
import { motion } from 'framer-motion';
import {
  BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine, LineChart, Line,
} from 'recharts';
import {
  TrendingUp, PiggyBank, Coins, Wallet, Percent, Check, Calculator,
  AlertTriangle, Lightbulb, LineChart as LineChartIcon,
  Box as BoxIcon, FileSpreadsheet, LayoutDashboard, Info,
} from 'lucide-react';
import { formatWon } from '../../utils/format';
import BuildingViewer from '../viewer/BuildingViewer';

// App.jsx에서 분리된 STEP 6: 분석 결과 대시보드 (에너지 성능 / LCC 경제성 탭)
export default function ResultDashboard({
  theme,
  res,
  isDarkMode,
  lccAnalysis,
  activeResultTab,
  setActiveResultTab,
  setSelectedMetric,
  zones,
  surfaces,
  setStep,
  handleApplyRecommendations,
  getZebGradeInfo,
  getAnnualChartData,
  viewMode,
  setViewMode,
  sunMonth,
  setSunMonth,
  sunHour,
  setSunHour,
  latitude,
  selectedRegion,
}) {
  // 에너지 항목 분류 및 차트 색상 (App.jsx에서 함께 이동)
  const categories = ['신재생', '난방', '냉방', '급탕', '조명', '환기', '기기'];
  const colors = ['#2DD4BF', '#F87171', '#60A5FA', '#FB923C', '#FACC15', '#4ADE80', '#A78BFA'];

  // 비용 절감 제안: 즉시 적용이 아니라 다중 선택 후 일괄 적용
  const [selectedRecTypes, setSelectedRecTypes] = useState([]);
  const toggleRecType = (type) =>
    setSelectedRecTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    );

  return (
            <div className="w-full h-full max-w-[1400px] mx-auto p-8 overflow-y-auto animate-in zoom-in duration-500 custom-scrollbar flex flex-col">
              <div className="flex flex-col md:flex-row md:items-end justify-between mb-8 gap-4 flex-shrink-0">
                <div>
                  <h2 className="text-5xl font-black text-emerald-500 mb-2 tracking-tighter">Analysis Complete</h2>
                  <p className={`${theme.textSub} text-lg font-medium`}>
                    사용자 맞춤 설정이 반영된 최종 건물 성능 및 경제성 리포트입니다.
                  </p>
                </div>
                <div className="flex flex-col md:flex-row items-stretch md:items-center gap-3">
                  <div
                    className={`p-1 flex flex-col sm:flex-row rounded-2xl border shadow-inner ${
                      isDarkMode ? 'bg-black/30 border-slate-800' : 'bg-slate-200 border-slate-300'
                    }`}
                  >
                    <button
                      onClick={() => setActiveResultTab('energy')}
                      className={`px-6 py-3 font-black rounded-xl text-sm transition-all ${
                        activeResultTab === 'energy'
                          ? 'bg-emerald-500 text-white shadow-lg'
                          : 'text-slate-500 hover:text-emerald-400 hover:bg-white/5'
                      }`}
                    >
                      ⚡ 에너지 성능
                    </button>
                    <button
                      onClick={() => setActiveResultTab('lcc')}
                      className={`px-6 py-3 font-black rounded-xl text-sm transition-all flex items-center gap-2 ${
                        activeResultTab === 'lcc'
                          ? 'bg-amber-500 text-white shadow-lg'
                          : 'text-slate-500 hover:text-amber-400 hover:bg-white/5'
                      }`}
                    >
                      💰 경제성(LCC) 분석{' '}
                      <span className="flex h-2 w-2 relative">
                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                        <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span>
                      </span>
                    </button>
                  </div>
                  <button
                    onClick={() => setStep('buildingView')}
                    className="px-6 py-3 rounded-2xl border-2 border-slate-500 font-black text-sm hover:bg-slate-500/10 transition-all active:scale-95 text-slate-400"
                  >
                    모델 재수정
                  </button>
                </div>
              </div>

              {/* 탭: ⚡ 에너지 성능 (기존) */}
              {activeResultTab === 'energy' && (
                <div className="animate-in fade-in slide-in-from-bottom-4">
                  <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6 mb-6">
                    {[
                      {
                        label: '요구량',
                        val: res?.summary?.demand_per_m2 || 0,
                        unit: 'kWh/m²a',
                        layoutId: 'metric-demand',
                        desc: '건축물 자체가 요구하는 순수 에너지의 양입니다. 단열재, 창호 성능, 일사량, 외풍 등 건물의 물리적 특성만으로 결정되며, 전기/설비 기기의 효율은 반영되지 않은 이상적인 필요량입니다. 이 수치를 낮추려면 패시브(Passive) 건축 기법(고성능 단열, 로이유리 등)을 적용해야 합니다.'
                      },
                      {
                        label: '소요량',
                        val: res?.summary?.consume_per_m2 || 0,
                        unit: 'kWh/m²a',
                        layoutId: 'metric-consume',
                        desc: '요구량 에너지를 실제로 공급하기 위해 보일러, 에어컨, 조명 등 냉난방 설비가 기구적으로 소비하는 실제 에너지양입니다. 물리적 한계(요구량)에 설비 기기의 효율(COP)이 결합된 결과이며, 실질적인 에너지 비용/관리비 청구서에 직접적으로 영향을 미칩니다.'
                      },
                      {
                        label: '1차 소요량',
                        val: res?.summary?.primary_per_m2 || 0,
                        unit: 'kWh/m²a',
                        layoutId: 'metric-primary',
                        desc: '건물까지 에너지를 배달하기 위해 화력, 원자력 발전소 등에서 채굴, 발전, 송전하는 과정에서 발생한 에너지 손실까지 모두 합산한 국가/에너지원 관점의 환산(원시) 소요량입니다. 건축물 에너지 효율 등급 평가의 절대적 기준이 됩니다.'
                      },
                      {
                        label: 'CO2 배출량',
                        val: res?.summary?.co2_per_m2 || 0,
                        unit: 'kg/m²a',
                        layoutId: 'metric-co2',
                        desc: '해당 시뮬레이션의 에너지 사용에 따라 발생하는 연간 온실가스 평균 배출량입니다. 에너지 사용량에 각 에너지원별(전기 0.466, 가스 2.1 등) 환산 배출 계수를 곱하여 산출합니다. 탄소 중립 및 관련 건축 인증에 가장 비중 있게 활용됩니다.'
                      },
                    ].map((stat, i) => (
                      <motion.div
                        key={i}
                        layoutId={stat.layoutId}
                        onClick={() => setSelectedMetric(stat)}
                        className={`p-8 rounded-[2rem] ${theme.card} border flex flex-col justify-center items-center text-center shadow-lg cursor-pointer hover:border-emerald-500/50 transition-colors z-10`}
                      >
                        <motion.p layoutId={`${stat.layoutId}-label`} className={`text-xs font-bold uppercase tracking-widest mb-3 opacity-60 ${theme.textSub}`}>
                          {stat.label}
                        </motion.p>
                        <motion.div layoutId={`${stat.layoutId}-val`} className="flex items-baseline gap-2">
                          <span className="text-4xl font-black text-emerald-400">{Number(stat.val).toFixed(1)}</span>
                          <span className="text-xs font-bold opacity-50">{stat.unit}</span>
                        </motion.div>
                      </motion.div>
                    ))}
                  </div>

                  <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 mb-6">
                    <div
                      className={`xl:col-span-4 p-8 rounded-[2.5rem] ${theme.card} border flex flex-col items-center justify-center relative overflow-hidden shadow-lg`}
                    >
                      <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/10 rounded-full blur-3xl -mr-10 -mt-10"></div>
                      <h3 className={`text-sm font-black uppercase tracking-widest mb-8 ${theme.textSub}`}>
                        에너지 자립률
                      </h3>
                      <div className="relative w-full aspect-square flex items-center justify-center">
                        <PieChart width={250} height={250}>
                          <Pie
                            data={[
                              { v: Number(res?.summary?.independence || 0) },
                              { v: 100 - Number(res?.summary?.independence || 0) },
                            ]}
                            innerRadius={85}
                            outerRadius={110}
                            startAngle={225}
                            endAngle={-45}
                            paddingAngle={0}
                            dataKey="v"
                            stroke="none"
                          >
                            <Cell fill="#10B981" />
                            <Cell fill={theme.pieBg} />
                          </Pie>
                        </PieChart>
                        <div
                          className={`absolute inset-0 flex flex-col items-center justify-center ${theme.textMain}`}
                        >
                          <span className="text-6xl font-black tracking-tighter">
                            {Number(res?.summary?.independence || 0).toFixed(1)}
                          </span>
                          <span className={`text-sm font-bold ${theme.textSub}`}>%</span>
                        </div>
                      </div>
                      <div
                        className={`mt-6 px-6 py-2.5 rounded-full text-xs font-black border transition-colors ${
                          Number(res?.summary?.independence || 0) >= 20
                            ? isDarkMode
                              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                              : 'bg-emerald-100 text-emerald-700 border-emerald-300'
                            : isDarkMode
                            ? 'bg-slate-500/10 text-slate-400 border-slate-500/20'
                            : 'bg-slate-200 text-slate-600 border-slate-300'
                        }`}
                      >
                        {Number(res?.summary?.independence || 0) >= 20
                          ? `ZEB 인증 완료 (${getZebGradeInfo(res?.summary?.independence)})`
                          : `ZEB 인증 미달 (등급 외)`}
                      </div>
                    </div>

                    <div className={`xl:col-span-8 p-8 rounded-[2.5rem] ${theme.card} border flex flex-col shadow-lg`}>
                      <div className="flex justify-between items-center mb-6">
                        <h3 className={`text-lg font-black flex items-center gap-2 ${theme.textMain}`}>
                          <BoxIcon size={20} className="text-emerald-500" /> 최종 적용된 3D 모델 형상
                        </h3>
                      </div>
                      <div
                        className={`flex-1 w-full rounded-2xl overflow-hidden relative min-h-[300px] ${
                          isDarkMode ? 'bg-slate-900/50 border border-white/5' : 'bg-slate-100 border border-slate-200'
                        }`}
                      >
                        <BuildingViewer
                          surfaces={surfaces}
                          zones={zones}
                          activeFloor="all"
                          editMode="surface"
                          readOnly={true}
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
                      <p className={`mt-4 text-[11px] text-center font-bold ${theme.textSub}`}>
                        적용된 창면적비(WWR)와 단열재가 반영된 형상입니다. 마우스로 드래그하여 확인할 수 있습니다.
                      </p>
                    </div>
                  </div>

                  <div className={`p-8 rounded-[2.5rem] ${theme.card} border shadow-lg mb-6`}>
                    <div className="flex justify-between items-center mb-8">
                      <h3 className={`text-lg font-black flex items-center gap-2 ${theme.textMain}`}>
                        <LayoutDashboard size={20} className="text-emerald-500" /> 월별 냉난방 에너지 요구량
                        [kWh/m²a]
                      </h3>
                      <div className={`flex gap-4 text-xs font-bold ${theme.textSub}`}>
                        <span className="flex items-center gap-2">
                          <div className="w-3 h-3 rounded-full bg-red-400"></div> 난방
                        </span>
                        <span className="flex items-center gap-2">
                          <div className="w-3 h-3 rounded-full bg-blue-400"></div> 냉방
                        </span>
                      </div>
                    </div>
                    <div className="h-[280px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={res?.monthly || []} barGap={4}>
                          <CartesianGrid vertical={false} stroke={theme.chartGrid} />
                          <XAxis
                            dataKey="name"
                            axisLine={false}
                            tickLine={false}
                            tick={{ fill: theme.chartText, fontSize: 12, fontWeight: 'bold' }}
                            dy={10}
                          />
                          <YAxis
                            axisLine={false}
                            tickLine={false}
                            tick={{ fill: theme.chartText, fontSize: 12, fontWeight: 'bold' }}
                          />
                          <Tooltip
                            cursor={{ fill: isDarkMode ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)' }}
                            formatter={(value) => Number(value).toFixed(1)}
                            contentStyle={{
                              borderRadius: '16px',
                              border: isDarkMode ? 'none' : '1px solid #e2e8f0',
                              backgroundColor: isDarkMode ? '#1e293b' : '#fff',
                              boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1)',
                            }}
                          />
                          <Bar dataKey="heating" fill="#F87171" radius={[8, 8, 0, 0]} barSize={16} />
                          <Bar dataKey="cooling" fill="#60A5FA" radius={[8, 8, 0, 0]} barSize={16} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                    <div className={`mt-8 overflow-x-auto rounded-2xl border ${theme.tableBorder}`}>
                      <table className="w-full text-[12px] text-center border-collapse">
                        <thead className={`${theme.tableHeader} border-b ${theme.tableBorder}`}>
                          <tr>
                            <th className="p-3 font-bold">비주거</th>
                            {(res?.monthly || []).map((d) => (
                              <th key={d.name} className="p-3 font-bold">
                                {d.name}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className={`font-bold ${theme.textMain}`}>
                          <tr className={`border-b ${theme.tableBorder}`}>
                            <td className="p-3 text-red-500">난방</td>
                            {(res?.monthly || []).map((d) => (
                              <td key={d.name}>{Number(d.heating || 0).toFixed(1)}</td>
                            ))}
                          </tr>
                          <tr>
                            <td className="p-3 text-blue-500">냉방</td>
                            {(res?.monthly || []).map((d) => (
                              <td key={d.name}>{Number(d.cooling || 0).toFixed(1)}</td>
                            ))}
                          </tr>
                        </tbody>
                      </table>
                    </div>
                  </div>

                  <div className={`p-10 rounded-[2.5rem] ${theme.card} border shadow-lg`}>
                    <h3 className={`text-xl font-black mb-8 flex items-center gap-3 ${theme.textMain}`}>
                      <FileSpreadsheet className="text-emerald-500" /> 연간 에너지 요구량 및 소요량 [kWh/m²a]
                    </h3>
                    <div className="h-[300px] mb-12">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart
                          data={getAnnualChartData()}
                          layout="vertical"
                          margin={{ left: 40, right: 40 }}
                          stackOffset="sign"
                        >
                          <CartesianGrid horizontal={false} stroke={theme.chartGrid} />
                          <XAxis type="number" hide />
                          <YAxis
                            dataKey="name"
                            type="category"
                            axisLine={false}
                            tickLine={false}
                            tick={{ fill: theme.chartText, fontSize: 13, fontWeight: 'bold' }}
                          />
                          <Tooltip
                            cursor={{ fill: 'transparent' }}
                            formatter={(value) => Number(value).toFixed(1)}
                            contentStyle={{
                              borderRadius: '12px',
                              border: isDarkMode ? 'none' : `1px solid ${theme.tableBorder}`,
                              backgroundColor: isDarkMode ? '#1e293b' : '#fff',
                            }}
                          />
                          <Legend
                            iconType="circle"
                            wrapperStyle={{ color: theme.chartText, fontWeight: 'bold', paddingTop: '20px' }}
                          />
                          <ReferenceLine
                            x={0}
                            stroke={isDarkMode ? '#fff' : '#475569'}
                            opacity={isDarkMode ? 0.2 : 0.4}
                            strokeDasharray="3 3"
                          />
                          {categories.map((c, i) => (
                            <Bar
                              key={c}
                              dataKey={c}
                              stackId="a"
                              fill={colors[i]}
                              barSize={32}
                              radius={i === 0 ? [6, 0, 0, 6] : i === categories.length - 1 ? [0, 6, 6, 0] : 0}
                            />
                          ))}
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                    <div className={`overflow-hidden rounded-3xl border ${theme.tableBorder}`}>
                      <table className="w-full text-sm text-center border-collapse">
                        <thead className={`${theme.tableHeader} border-b ${theme.tableBorder}`}>
                          <tr>
                            <th className={`p-4 border-r ${theme.tableBorder} font-bold`}>구분</th>
                            {categories.map((c) => (
                              <th key={c} className={`p-4 border-r ${theme.tableBorder} font-bold`}>
                                {c}
                              </th>
                            ))}
                            <th className="p-4 font-black">합계</th>
                          </tr>
                        </thead>
                        <tbody className={`font-semibold ${theme.textMain}`}>
                          {[
                            { id: 'req', name: '요구량' },
                            { id: 'con', name: '소요량' },
                            { id: 'pri', name: '1차 소요량' },
                            { id: 'co2', name: 'CO2 발생량' },
                            { id: 'grd', name: '등급용 1차' },
                          ].map((row, idx) => {
                            const m = res?.matrix;
                            if (!m) return null;
                            const getVal = (catId) => {
                              const base = m[catId];
                              if (row.id === 'req') return Number(base?.req || 0);
                              if (row.id === 'con') return Number(base?.con || 0);
                              if (row.id === 'pri') return Number(base?.con || 0) * 2.75;
                              if (row.id === 'co2') return Number(base?.con || 0) * 0.466;
                              if (row.id === 'grd') {
                                if (catId === 'equipment') return 0;
                                return Number(base?.con || 0) * 2.1;
                              }
                              return 0;
                            };
                            const rowDataValues = ['renewable', 'heating', 'cooling', 'hotwater', 'lighting', 'ventilation', 'equipment'].map((id) =>
                              getVal(id)
                            );
                            const totalValue = rowDataValues.reduce((a, b) => a + b, 0);
                            return (
                              <tr
                                key={row.id}
                                className={`${
                                  idx % 2 === 0 ? (isDarkMode ? 'bg-white/5' : 'bg-white/40') : 'bg-transparent'
                                } border-b ${theme.tableBorder}`}
                              >
                                <td
                                  className={`p-4 border-r ${theme.tableBorder} font-bold ${
                                    isDarkMode ? 'text-emerald-400' : 'text-emerald-700'
                                  }`}
                                >
                                  {row.name}
                                </td>
                                {rowDataValues.map((v, i) => (
                                  <td
                                    key={i}
                                    className={`p-4 border-r ${theme.tableBorder} ${
                                      v < 0 ? (isDarkMode ? 'text-cyan-400' : 'text-cyan-600 font-bold') : ''
                                    }`}
                                  >
                                    {v.toFixed(1)}
                                  </td>
                                ))}
                                <td
                                  className={`p-4 font-black ${isDarkMode ? 'text-emerald-400' : 'text-emerald-700'}`}
                                >
                                  {totalValue.toFixed(1)}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}

              {/* 탭: 💰 LCC (경제성) 분석 */}
              {activeResultTab === 'lcc' && res?.financial && (
                <div className="animate-in fade-in slide-in-from-bottom-4 flex flex-col gap-6">
                  {/* 예산 초과 알림 및 절감 추천 */}
                  {res.financial.target_budget > 0 && res.financial.capital_cost > res.financial.target_budget && (
                    <div className={`border-2 rounded-3xl p-7 shadow-sm ${isDarkMode ? 'bg-rose-500/5 border-rose-500/30' : 'bg-rose-50 border-rose-200'}`}>
                      <div className="flex items-center gap-3 text-rose-500 mb-4">
                        <AlertTriangle size={24} />
                        <h3 className="text-lg font-black tracking-tight">목표 예산 초과 안내 및 비용 절감 제안</h3>
                      </div>
                      <p className={`mb-6 text-sm font-medium leading-relaxed ${theme.textMain}`}>
                        입력하신 목표 예산({formatWon(res.financial.target_budget)})을
                        <span className="font-black text-rose-500 mx-1.5 underline decoration-rose-500/30 underline-offset-4">
                          {formatWon(res.financial.capital_cost - res.financial.target_budget)}
                        </span>
                        초과했습니다. 적용할 제안을 <span className="font-bold">여러 개 선택</span>한 뒤 아래 <span className="font-bold">[선택 적용]</span> 버튼으로 한 번에 반영하세요.
                      </p>
                      
                      {res.financial.recommendations && res.financial.recommendations.length > 0 && (
                        <div className="space-y-4">
                          {(() => {
                            const totalSavedCost = res.financial.recommendations.reduce((acc, curr) => acc + curr.saved_cost, 0);
                            return (
                              <div className={`flex flex-col sm:flex-row sm:items-center justify-between p-4 rounded-xl border ${isDarkMode ? 'bg-black/20 border-emerald-500/20' : 'bg-white border-emerald-500/20 shadow-sm'}`}>
                                <span className={`text-sm font-bold flex items-center gap-2 ${isDarkMode ? 'text-emerald-400' : 'text-emerald-600'}`}>
                                  <PiggyBank size={18} /> 모든 제안 적용 시 예상 총 절감액
                                </span>
                                <span className={`text-2xl font-black tracking-tighter mt-1 sm:mt-0 ${isDarkMode ? 'text-emerald-400' : 'text-emerald-600'}`}>
                                  -{formatWon(totalSavedCost)}
                                </span>
                              </div>
                            );
                          })()}

                          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                            {res.financial.recommendations.map((rec, idx) => {
                              const isSelected = selectedRecTypes.includes(rec.type);
                              return (
                              <button
                                key={idx}
                                type="button"
                                onClick={() => toggleRecType(rec.type)}
                                aria-pressed={isSelected}
                                className={`relative overflow-hidden p-5 rounded-2xl border flex flex-col gap-3 text-left transition-all duration-300 hover:-translate-y-1 hover:shadow-lg cursor-pointer ${
                                  isSelected
                                    ? 'border-emerald-500 ring-2 ring-emerald-500/40 bg-emerald-500/10'
                                    : isDarkMode
                                    ? 'bg-gradient-to-br from-white/5 to-white/0 border-white/10 hover:border-emerald-500/50'
                                    : 'bg-gradient-to-br from-slate-50 to-white border-slate-200 shadow-sm hover:border-emerald-500/50'
                                }`}
                              >
                                {/* Glassmorphism accent */}
                                <div className="absolute -top-12 -right-12 w-32 h-32 bg-emerald-500/10 rounded-full blur-2xl pointer-events-none"></div>

                                <div className="flex justify-between items-start gap-2 z-10">
                                  <span className={`font-black flex items-center gap-2 text-[13px] ${isDarkMode ? 'text-white' : 'text-slate-800'}`}>
                                    <Lightbulb size={16} className="shrink-0 text-emerald-500" /> {rec.title}
                                  </span>
                                  {/* 선택 표시 체크박스 */}
                                  <span className={`shrink-0 w-5 h-5 rounded-md border flex items-center justify-center transition-colors ${isSelected ? 'bg-emerald-500 border-emerald-500 text-white' : 'border-slate-400/50 text-transparent'}`}>
                                    <Check size={14} />
                                  </span>
                                </div>
                                <p className={`text-xs leading-relaxed z-10 opacity-80 ${theme.textSub}`}>{rec.description}</p>

                                <div className="mt-auto pt-4 flex flex-wrap items-center justify-between gap-2 z-10 border-t border-slate-500/10">
                                  <span className="text-[11px] font-black bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 px-2.5 py-1.5 rounded-lg border border-emerald-500/20">
                                    예상 절감: -{formatWon(rec.saved_cost).replace(' 만 원', '만원')}
                                  </span>
                                  <span className={`text-[11px] font-bold ${isSelected ? 'text-emerald-500' : 'opacity-50'}`}>
                                    {isSelected ? '✓ 선택됨' : '선택하기'}
                                  </span>
                                </div>
                              </button>
                              );
                            })}
                          </div>

                          {/* 선택 일괄 적용 바 */}
                          {(() => {
                            const selectedSaved = res.financial.recommendations
                              .filter((r) => selectedRecTypes.includes(r.type))
                              .reduce((acc, r) => acc + r.saved_cost, 0);
                            return (
                              <div className={`flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-2xl border ${isDarkMode ? 'bg-black/20 border-emerald-500/20' : 'bg-white border-emerald-500/20 shadow-sm'}`}>
                                <span className={`text-sm font-bold ${theme.textSub}`}>
                                  {selectedRecTypes.length > 0
                                    ? <>선택한 <span className="text-emerald-500 font-black">{selectedRecTypes.length}</span>개 제안 · 예상 절감 <span className="text-emerald-500 font-black">-{formatWon(selectedSaved)}</span></>
                                    : '적용할 제안을 선택하세요'}
                                </span>
                                <button
                                  type="button"
                                  disabled={selectedRecTypes.length === 0}
                                  onClick={() => handleApplyRecommendations(selectedRecTypes)}
                                  className={`px-6 py-2.5 rounded-xl font-black text-sm flex items-center justify-center gap-2 transition-all ${
                                    selectedRecTypes.length === 0
                                      ? 'bg-slate-400/30 text-slate-400 cursor-not-allowed'
                                      : 'bg-blue-500 hover:bg-blue-600 text-white shadow-md hover:shadow-lg active:scale-95'
                                  }`}
                                >
                                  <Check size={16} /> 선택 적용{selectedRecTypes.length > 0 ? ` (${selectedRecTypes.length})` : ''}
                                </button>
                              </div>
                            );
                          })()}
                        </div>
                      )}
                    </div>
                  )}

                  {/* 핵심 재무/LCC 지표 요약 */}
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
                    {[
                      {
                        label: '초기 총 공사비',
                        val: formatWon(res.financial.capital_cost).replace(' 만 원', ''),
                        unit: '만 원',
                        isRawString: true, // Prevents formatting as number
                        layoutId: 'lcc-capital',
                        colorClass: 'text-amber-500',
                        bgClass: 'bg-amber-500/10',
                        borderClass: 'border-amber-500/20',
                        hoverClass: 'hover:border-amber-500/50',
                        icon: <Wallet className="text-amber-500" size={24} />,
                        desc: '에너지 성능 개선(창호, 단열, 조명 등)을 위해 투입되는 1회성 공사비입니다.'
                      },
                      {
                        label: '순현재가치 (NPV)',
                        val: formatWon(lccAnalysis.npv).replace(' 만 원', ''),
                        unit: '만 원',
                        isRawString: true,
                        layoutId: 'lcc-npv',
                        colorClass: 'text-indigo-400',
                        bgClass: 'bg-indigo-500/10',
                        borderClass: 'border-indigo-500/20',
                        hoverClass: 'hover:border-indigo-500/50',
                        icon: <LineChartIcon className="text-indigo-500" size={24} />,
                        desc: '미래의 잉여 현금흐름(에너지 요금 절감액)을 현재 가치로 할인하여 초기 공사비를 뺀 20년 생애 순수익입니다. (0 이상이면 투자 타당성 있음)'
                      },
                      {
                        label: '내부수익률 (IRR)',
                        val: lccAnalysis.irr.toFixed(1),
                        unit: '%',
                        isRawString: true,
                        layoutId: 'lcc-irr',
                        colorClass: 'text-rose-400',
                        bgClass: 'bg-rose-500/10',
                        borderClass: 'border-rose-500/20',
                        hoverClass: 'hover:border-rose-500/50',
                        icon: <Percent className="text-rose-500" size={24} />,
                        desc: '이 프로젝트에 투자했을 때 예상되는 연평균 복리 수익률입니다. 은행 이자율이나 기대 수익률(할인율)보다 높다면 성공적인 리모델링입니다.'
                      },
                      {
                        label: '투자 회수 기간',
                        val: lccAnalysis.paybackYears > 0 ? lccAnalysis.paybackYears.toFixed(1) : '-',
                        unit: '년',
                        isRawString: true,
                        layoutId: 'lcc-payback',
                        colorClass: 'text-blue-400',
                        bgClass: 'bg-blue-500/10',
                        borderClass: 'border-blue-500/20',
                        hoverClass: 'hover:border-blue-500/50',
                        icon: <TrendingUp className="text-blue-500" size={24} />,
                        glow: true,
                        desc: '초기 지출한 공사비를 매년 아껴지는 에너지 요금으로 전액 회수하는 데 걸리는 기간(할인율 미적용 기준)입니다.'
                      },
                      {
                        label: '연간 에너지운영비',
                        val: formatWon(res.financial.total_energy_bill).replace(' 만 원', ''),
                        unit: '만 원/년',
                        isRawString: true,
                        layoutId: 'lcc-running',
                        colorClass: 'text-emerald-400',
                        bgClass: 'bg-emerald-500/10',
                        borderClass: 'border-emerald-500/20',
                        hoverClass: 'hover:border-emerald-500/50',
                        icon: <PiggyBank className="text-emerald-500" size={24} />,
                        desc: '리모델링 후 발생하는 연간 실제 에너지 요금입니다.'
                      }
                    ].map((stat, i) => (
                      <motion.div
                        key={i}
                        layoutId={stat.layoutId}
                        onClick={() => setSelectedMetric(stat)}
                        className={`p-8 rounded-[2rem] ${theme.card} border ${stat.borderClass} ${stat.hoverClass} shadow-lg flex items-center gap-6 cursor-pointer transition-colors relative overflow-hidden z-10`}
                      >
                        {stat.glow && (
                          <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/10 rounded-full blur-3xl -mr-10 -mt-10"></div>
                        )}
                        <motion.div layoutId={`${stat.layoutId}-icon`} className={`w-16 h-16 rounded-2xl ${stat.bgClass} flex items-center justify-center shrink-0 border ${stat.borderClass} z-10`}>
                          {stat.icon}
                        </motion.div>
                        <div className="z-10">
                          <motion.p layoutId={`${stat.layoutId}-label`} className={`text-xs font-bold uppercase tracking-widest mb-1 opacity-60 ${theme.textSub}`}>
                            {stat.label}
                          </motion.p>
                          <motion.div layoutId={`${stat.layoutId}-val`} className={`text-3xl font-black ${stat.colorClass} tracking-tighter flex items-end gap-1`}>
                            {stat.val} <span className="text-sm font-bold opacity-50 mb-1">{stat.unit}</span>
                          </motion.div>
                        </div>
                      </motion.div>
                    ))}
                  </div>

                  {/* NPV/IRR/회수기간 산정 기준 안내 (실측 vs 추정 명시 고지) */}
                  {lccAnalysis.baselineAssumptions && (() => {
                    const ba = lccAnalysis.baselineAssumptions;
                    const isActual = ba.source === 'actual_bill' || ba.source === 'actual_usage';
                    const srcLabel = ba.source === 'actual_bill' ? '실측(요금 입력)'
                      : ba.source === 'actual_usage' ? '실측(사용량 입력)' : '추정';
                    return (
                      <div className={`text-[11px] leading-relaxed px-1 ${theme.textSub} opacity-80`}>
                        <span className={`inline-block px-2 py-0.5 mb-1.5 rounded-full text-[10px] font-black ${isActual ? 'bg-emerald-500/15 text-emerald-500' : 'bg-amber-500/15 text-amber-500'}`}>
                          기준 건물: {srcLabel}
                        </span>
                        <p className="flex items-start gap-1.5">
                          <Info size={13} className="shrink-0 mt-0.5 text-indigo-400" />
                          {isActual ? (
                            <span>
                              NPV·IRR·회수기간은 입력하신 <b>실제 기존 건물 운영비</b>
                              (연 {Math.round((ba.base_running_cost || 0) / 10000).toLocaleString()}만원,
                              절감률 {ba.savings_pct}%) 대비 절감액으로 산출되었습니다.
                            </span>
                          ) : (
                            <span>
                              실측값 미입력 — <b>추정 기준 건물</b>(기존 운영비를 리모델링 후의{' '}
                              {ba.running_cost_multiplier}배 ≈ 절감률 {ba.savings_pct}%로 가정) 대비 산출된
                              값입니다. 정확한 분석을 원하면 설정에서 기존 건물 실제 사용량을 입력하세요.
                            </span>
                          )}
                        </p>
                      </div>
                    );
                  })()}

                  {/* 세부 내역 2분할 */}
                  <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                    {/* 공사비 브레이크다운 */}
                    <div className={`p-8 rounded-[2.5rem] ${theme.card} border shadow-lg flex flex-col`}>
                      <h3 className={`text-lg font-black flex items-center gap-2 mb-6 ${theme.textMain}`}>
                        <Calculator size={20} className="text-amber-500" /> 공종별 내역서 (조달청/친환경 DB)
                      </h3>

                      <p className={`text-[11px] mb-5 -mt-3 flex items-start gap-1.5 ${theme.textSub} opacity-70`}>
                        <Info size={13} className="shrink-0 mt-0.5 text-amber-400" />
                        <span>자재비 단가 기준 <b>상대 비교용 추정치</b>입니다(노무·철거·가설비 미포함). 절대 금액보다 공종 간 비중·대안 비교에 활용하세요.</span>
                      </p>

                      {res.financial.cost_warnings?.length > 0 && (
                        <div className="mb-5 p-3 rounded-xl border border-rose-500/30 bg-rose-500/10 flex flex-col gap-1">
                          {res.financial.cost_warnings.map((w, i) => (
                            <span key={i} className="text-[11px] font-bold text-rose-500 flex items-start gap-1.5">
                              <AlertTriangle size={12} className="shrink-0 mt-0.5" /> {w}
                            </span>
                          ))}
                        </div>
                      )}

                      <div className="flex-1 flex flex-col justify-center gap-4">
                        {[
                          { key: 'window', label: '창호 공사 (Glazing)', color: 'bg-blue-500' },
                          { key: 'insulation', label: '단열 공사 (Insulation)', color: 'bg-orange-500' },
                          { key: 'led', label: '전기 공사 (LED 등기구)', color: 'bg-yellow-400' },
                          { key: 'hvac', label: '설비 공사 (HVAC 시스템)', color: 'bg-emerald-500' },
                        ].map((item) => {
                          const cost = res.financial.cost_details[item.key] || 0;
                          const pct = (cost / res.financial.capital_cost) * 100 || 0;
                          return (
                            <div key={item.key} className="flex flex-col gap-2">
                              <div className="flex justify-between items-end">
                                <span className={`text-sm font-bold ${theme.textMain} flex items-center gap-2`}>
                                  <div className={`w-3 h-3 rounded-full ${item.color}`}></div>
                                  {item.label}
                                </span>
                                <span className="text-sm font-black tracking-tight">
                                  {formatWon(cost)} <span className="text-[10px] opacity-40 ml-1">({pct.toFixed(1)}%)</span>
                                </span>
                              </div>
                              <div className="w-full h-2.5 bg-black/10 rounded-full overflow-hidden border border-white/5">
                                <div className={`h-full ${item.color} rounded-full`} style={{ width: `${pct}%` }}></div>
                              </div>
                            </div>
                          );
                        })}
                      </div>

                      <div className="mt-8 p-4 bg-black/10 rounded-2xl border border-white/5 flex flex-col gap-2">
                        <div className="flex items-center justify-between">
                          <span className={`text-xs font-bold opacity-60 ${theme.textMain}`}>적용된 DB 데이터베이스 건수</span>
                          <span className="text-xs font-black text-emerald-400">
                            {res.financial.csv_db_loaded?.items?.toLocaleString() || 0} 건의 실견적 단가 로드됨
                          </span>
                        </div>
                        {/* 💡 [신규] 백엔드에서 매칭된 창호 실제 제품명 표시 */}
                        <div className="flex items-center justify-between border-t border-white/5 pt-2 mt-1">
                          <span className={`text-xs font-bold opacity-60 ${theme.textMain}`}>적용된 창호 단가 제품명 (U-Value 연동)</span>
                          <span className="text-xs font-black text-blue-400 max-w-[200px] truncate" title={res.financial.mapped_window_name}>
                            {res.financial.mapped_window_name}
                          </span>
                        </div>
                        {/* 💡 [신규] 백엔드에서 매칭된 단열재 실제 등급 및 U-Value 연동 단가 표시 */}
                        {res.financial.insulation_details && res.financial.insulation_details.length > 0 && (
                          <div className="flex flex-col border-t border-white/5 pt-2 mt-1 gap-1.5">
                            <span className={`text-xs font-bold opacity-60 ${theme.textMain}`}>적용된 구조체별 단열 공사비 상세 (친환경DB 연동)</span>
                            <div className="space-y-1 max-h-[120px] overflow-y-auto custom-scrollbar pr-1">
                              {res.financial.insulation_details.map((d, idx) => (
                                <div key={idx} className="flex justify-between items-center text-[10px] font-bold">
                                  <span className="text-slate-400 truncate max-w-[180px]">{d.constructionName} ({d.area.toFixed(1)}㎡)</span>
                                  <span className="text-orange-400">{d.tier.split(' ')[0]} (₩{d.price.toLocaleString()}/㎡)</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* 공과금 브레이크다운 */}
                    <div className={`p-8 rounded-[2.5rem] ${theme.card} border shadow-lg flex flex-col`}>
                      <h3 className={`text-lg font-black flex items-center gap-2 mb-6 ${theme.textMain}`}>
                        <Coins size={20} className="text-emerald-500" /> 연간 예상 공과금 내역 (KEPCO/지역난방)
                      </h3>

                      <div className="flex-1 flex items-center justify-center relative">
                        <PieChart width={300} height={300}>
                          <Pie
                            data={[
                              { name: '전기요금 (조명/기기/냉방)', value: res.financial.annual_elec_bill, fill: '#3B82F6' },
                              { name: '열요금 (지역난방/급탕)', value: res.financial.annual_heat_bill, fill: '#EF4444' },
                            ]}
                            cx="50%"
                            cy="50%"
                            innerRadius={80}
                            outerRadius={110}
                            paddingAngle={2}
                            dataKey="value"
                            stroke="none"
                          />
                          <Tooltip
                            formatter={(val) => formatWon(val)}
                            contentStyle={{
                              borderRadius: '12px',
                              border: isDarkMode ? 'none' : `1px solid ${theme.tableBorder}`,
                              backgroundColor: isDarkMode ? '#1e293b' : '#fff',
                              fontWeight: 'bold',
                            }}
                          />
                        </PieChart>
                        <div
                          className={`absolute inset-0 flex flex-col items-center justify-center ${theme.textMain} pointer-events-none`}
                        >
                          <span className="text-xs font-bold opacity-50 uppercase tracking-widest mb-1">TOTAL</span>
                          <span className="text-2xl font-black">{formatWon(res.financial.total_energy_bill)}</span>
                        </div>
                      </div>

                      <div className="flex justify-center gap-6 mt-4">
                        <div className="text-center">
                          <span className="flex items-center justify-center gap-1 text-[10px] font-bold opacity-60 mb-1">
                            <div className="w-2 h-2 rounded-full bg-blue-500"></div>전기요금
                          </span>
                          <span className={`text-sm font-black ${theme.textMain}`}>
                            {formatWon(res.financial.annual_elec_bill)}
                          </span>
                        </div>
                        <div className="text-center">
                          <span className="flex items-center justify-center gap-1 text-[10px] font-bold opacity-60 mb-1">
                            <div className="w-2 h-2 rounded-full bg-red-500"></div>지역난방비
                          </span>
                          <span className={`text-sm font-black ${theme.textMain}`}>
                            {formatWon(res.financial.annual_heat_bill)}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* 💰 하이라이트: ROI Cash Flow 차트 */}
                  <motion.div 
                    layoutId="lcc-graph"
                    onClick={() => setSelectedMetric({
                      layoutId: 'lcc-graph',
                      label: '생애주기비용 (LCC) 누적 현금 흐름도',
                      val: `+${formatWon(lccAnalysis.annualSavings).replace(' 만 원', '')}`,
                      unit: '만 원 / 년 순절감액',
                      isRawString: true,
                      colorClass: 'text-emerald-400',
                      desc: '리모델링 공사비(초기 투자금)를 비용으로 지출한 뒤, 향상된 에너지 효율을 통해 매달 절감하는 운영비가 기존 노후 건물을 방치했을 때의 낭비보다 장기적으로 얼마나 더 이득인지 15년간 추적한 차트입니다. 빨간선(기존 상태 유지)과 파란선(리모델링 진행)이 교차하는 지점이 바로 초기 투자금을 100% 회수하고 누적 순이익(초록선)이 플러스가 되는 ‘손익분기점’입니다. 시간이 갈수록 초록선이 우상향하며 친환경 리모델링의 압도적인 경제적 가치를 증명합니다.'
                    })}
                    className={`p-10 rounded-[2.5rem] ${theme.card} border shadow-xl flex flex-col cursor-pointer hover:border-emerald-500/50 transition-colors z-10 relative overflow-hidden`}
                  >
                    <div className="flex justify-between items-end mb-8">
                      <div>
                        <h3 className={`text-xl font-black flex items-center gap-3 ${theme.textMain}`}>
                          <TrendingUp className="text-amber-400" size={24} /> 생애주기비용 (LCC) 누적 현금 흐름도
                        </h3>
                        <p className={`text-sm font-medium mt-2 ${theme.textSub}`}>
                          친환경 리모델링 시뮬레이션에 따른 15년간의 투자/수익(절감액) 분석표입니다.
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-xs font-bold opacity-50 uppercase tracking-widest mb-1">연간 순 절감액</p>
                        <p className="text-2xl font-black text-emerald-400">+{formatWon(lccAnalysis.annualSavings)}</p>
                      </div>
                    </div>

                    <div className="h-[400px] w-full">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={lccAnalysis.data} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke={theme.chartGrid} />
                          <XAxis
                            dataKey="year"
                            tick={{ fill: theme.chartText, fontSize: 12, fontWeight: 'bold' }}
                            axisLine={false}
                            tickLine={false}
                            dy={10}
                          />
                          <YAxis
                            tickFormatter={(val) => `${Math.round(val / 10000000)}천만`}
                            tick={{ fill: theme.chartText, fontSize: 12, fontWeight: 'bold' }}
                            axisLine={false}
                            tickLine={false}
                            domain={['auto', 'auto']}
                          />
                          <Tooltip
                            formatter={(val) => formatWon(val)}
                            contentStyle={{
                              borderRadius: '16px',
                              border: isDarkMode ? 'none' : '1px solid #e2e8f0',
                              backgroundColor: isDarkMode ? '#0F172A' : '#fff',
                              fontWeight: 'bold',
                              boxShadow: '0 10px 25px -5px rgb(0 0 0 / 0.3)',
                            }}
                          />
                          <Legend wrapperStyle={{ paddingTop: '20px', fontWeight: 'bold', color: theme.chartText }} />

                          {/* 0원 선 (손익분기점 기준선) */}
                          <ReferenceLine
                            y={0}
                            stroke={isDarkMode ? '#ffffff' : '#000'}
                            strokeOpacity={0.3}
                            strokeWidth={2}
                            strokeDasharray="3 3"
                          />

                          {/* 투자 회수 기점 라인 표시 */}
                          <ReferenceLine
                            x={`${Math.ceil(lccAnalysis.paybackYears)}년차`}
                            stroke="#F59E0B"
                            strokeOpacity={0.8}
                            strokeDasharray="3 3"
                            label={{
                              position: 'top',
                              value: '손익분기 돌파',
                              fill: '#F59E0B',
                              fontSize: 12,
                              fontWeight: 'black',
                            }}
                          />

                          <Line
                            type="monotone"
                            dataKey="기존 노후건물 유지"
                            stroke="#EF4444"
                            strokeWidth={3}
                            dot={{ r: 4, strokeWidth: 2 }}
                            activeDot={{ r: 6 }}
                          />
                          <Line
                            type="monotone"
                            dataKey="친환경 리모델링 (투자+운영)"
                            stroke="#3B82F6"
                            strokeWidth={3}
                            dot={{ r: 4, strokeWidth: 2 }}
                            activeDot={{ r: 6 }}
                          />
                          <Line
                            type="monotone"
                            dataKey="누적 순이익 (ROI)"
                            stroke="#10B981"
                            strokeWidth={4}
                            dot={{ r: 6, fill: '#10B981', strokeWidth: 2, stroke: '#fff' }}
                            activeDot={{ r: 8, stroke: '#fff', strokeWidth: 3 }}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </motion.div>
                </div>
              )}
            </div>
  );
}
