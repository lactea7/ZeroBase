import React, { useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
  LineChart,
  Line,
} from 'recharts';
import {
  Settings2,
  ArrowRight,
  ArrowLeft,
  FileText,
  Loader2,
  LayoutDashboard,
  FileSpreadsheet,
  Moon,
  Sun,
  Save,
  Box as BoxIcon,
  Info,
  Layers,
  X,
  UploadCloud,
  Building,
  CheckCircle2,
  SlidersHorizontal,
  ChevronLeft,
  HardHat,
  List,
  Wind,
  Users,
  ToggleLeft,
  ToggleRight,
  Flame,
  DollarSign,
  Thermometer,
  Lightbulb,
  Monitor,
  Zap,
  Compass,
  Activity,
  Calculator,
  MapPin,
  TrendingUp,
  PiggyBank,
  Coins,
  Wallet,
  Clock,
  Calendar,
  AlertTriangle,
  Check,
  Percent,
  LineChart as LineChartIcon
} from 'lucide-react';

// --- 분리된 모듈 import ---
import { uploadGbxml, runSimulation } from './api/client';
import { ACTIVITIES, GLAZING_TYPES, KOREA_REGIONS, OUTLET_W_PER_ACTIVITY } from './data/constants';
import { INSULATION_TYPES, INSULATION_CATEGORIES } from './data/insulation';
import { STRUCTURAL_MATERIALS } from './data/structuralMaterials';
import { HVAC_SYSTEMS, FUEL_TYPES, VENT_TYPES } from './data/hvac';
import { LOADING_MESSAGES, DIR_MAP } from './utils/format';
import { getPanesCategory, getCoatingType } from './utils/surface';
import ScheduleEditor from './components/ScheduleEditor';
import Navigation from './components/landing/Navigation';
import Hero from './components/landing/Hero';
import Manual from './components/landing/Manual';
import { REGION_LATITUDES } from './utils/solarHelper';
import * as THREE from 'three';

// --- 분리된 3D 뷰어 컴포넌트 ---
import BuildingViewer from './components/viewer/BuildingViewer';

// --- 분리된 결과 대시보드 (STEP 6) ---
import ResultDashboard from './components/steps/ResultDashboard';

// --- 분리된 평면도/속성 편집기 (STEP 3 & 4) ---
import FloorEditor from './components/steps/FloorEditor';


// --- 설정 위저드 공통 셸 (스텝별 페이지 래퍼: 헤더 + 이전/다음 네비게이션) ---
// 모듈 스코프에 정의해야 매 렌더마다 재생성되어 입력 포커스를 잃는 문제를 피할 수 있다.
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

// --- [메인 애플리케이션] ---
export default function App() {
  const [step, setStep] = useState('landing');
  const [selectedMetric, setSelectedMetric] = useState(null);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  
  const [showVideoTooltip, setShowVideoTooltip] = useState(false);
  const tooltipTimerRef = useRef(null);

  const handleMouseEnterTooltip = () => {
    tooltipTimerRef.current = setTimeout(() => {
      setShowVideoTooltip(true);
    }, 1000);
  };

  const handleMouseLeaveTooltip = () => {
    if (tooltipTimerRef.current) {
      clearTimeout(tooltipTimerRef.current);
    }
    setShowVideoTooltip(false);
  };

  const [projectData, setProjectData] = useState({
    name: '신규 프로젝트',
    activityId: 1105,
    location: 'KOR_SQ_Seoul',
    pvCapacity: 0,
    heatSource: 11, // 난방 열원: 2전기 11지역난방
    // 기존 건물 실측 운영비(선택). 비우면 1.6배 추정으로 계산됨을 결과에 명시 고지.
    //   mode 'bill'=연간 요금(원), 'usage'=연간 사용량(kWh). 빈칸은 백엔드에서 무시.
    baselineActual: { mode: 'bill', elecBill: '', heatBill: '', elecKwh: '', heatKwh: '' },
    geothermalApplied: false,
    hvacUpgradeActive: false,
    orientation: 0,
    targetBudget: 0,
    lccParameters: {
      discountRate: 5.0,
      inflationRate: 3.0,
      utilityInflation: 4.0,
      lifecycleYears: 20
    },
    ledFixtureCount: 0,
    customSchedule: {
      useCustom: false, // 기본=용도별 자동 스케줄, 켜면 전체 존에 커스텀 override
      mode: 'simplified', // 'simplified' | 'detailed'
      simplifiedParams: {
        weekday: { openTime: 8, closeTime: 18, heatOcc: 20, heatUnocc: 15, coolOcc: 26, coolUnocc: 30, opOcc: 1.0, opUnocc: 0.0 },
        weekend: { openTime: 0, closeTime: 0, heatOcc: 15, heatUnocc: 15, coolOcc: 30, coolUnocc: 30, opOcc: 0.0, opUnocc: 0.0 },
        holiday: { openTime: 0, closeTime: 0, heatOcc: 15, heatUnocc: 15, coolOcc: 30, coolUnocc: 30, opOcc: 0.0, opUnocc: 0.0 }
      },
      holidays: ["01/01", "03/01", "05/05", "06/06", "08/15", "10/03", "10/09", "12/25"],
      profiles: {
        weekday: {
          heating: Array(24).fill().map((_, i) => (i >= 8 && i < 18) ? 20 : 15),
          cooling: Array(24).fill().map((_, i) => (i >= 8 && i < 18) ? 26 : 30),
          operation: Array(24).fill().map((_, i) => (i >= 8 && i < 18) ? 1.0 : 0.0),
        },
        weekend: {
          heating: Array(24).fill(15),
          cooling: Array(24).fill(30),
          operation: Array(24).fill(0.0),
        },
        holiday: {
          heating: Array(24).fill(15),
          cooling: Array(24).fill(30),
          operation: Array(24).fill(0.0),
        }
      }
    }
  });

  const [surfaces, setSurfaces] = useState([]);
  const [zones, setZones] = useState([]);
  const [activeFloor, setActiveFloor] = useState(1);
  const [editMode, setEditMode] = useState('surface');
  const [selectedId, setSelectedId] = useState(null);
  const [hoveredId, setHoveredId] = useState(null);
  const [editState, setEditState] = useState({});
  const [loadingMsgIdx, setLoadingMsgIdx] = useState(0);
  const [res, setRes] = useState(null);
  
  // 💡 [수정] 결과를 볼 때 '에너지 성능(energy)' 탭이 무조건 먼저 나오도록 기본값 설정
  const [activeResultTab, setActiveResultTab] = useState('energy');

  const [viewMode, setViewMode] = useState('default'); // 'default' | 'sunpath' | 'thermal' | 'airflow'
  const [sunMonth, setSunMonth] = useState(6);
  const [sunHour, setSunHour] = useState(12);

  const fileInputRef = useRef(null);
  const [uploadedFile, setUploadedFile] = useState(null);
  const [uploadError, setUploadError] = useState(null);

  const [lightCalc, setLightCalc] = useState({ active: false, w: 32, qty: 10, area: 100 });
  const [equipCalc, setEquipCalc] = useState({ active: false, w: 150, qty: 5, area: 100 });
  const [gapWarnings, setGapWarnings] = useState([]);
  const [realFloorCount, setRealFloorCount] = useState(0); // 파서가 감지한 실제 층수 (가상 층 제외)
  
  // 💡 단열재 및 구조체 속성 튜닝을 위한 State
  const [materials, setMaterials] = useState(null);
  const [constructionOverrides, setConstructionOverrides] = useState({});

  const calculateUpdatedUValue = (constr, override) => {
    if (!constr || !constr.layers || constr.layers.length === 0) return null;
    const R_FILM = 0.17; // 실내외 표면열전달저항 (근사치)

    if (!override) {
      let r_other = 0;
      let original_insul_r = 0;
      constr.layers.forEach(l => {
        const thick = l.thickness || 0;
        const cond = l.conductivity || 1.0;
        const r = cond > 0 ? (thick / 1000.0) / cond : 0;
        if (l.isInsulation) {
          original_insul_r += r;
        } else {
          r_other += r;
        }
      });
      const r_total = R_FILM + r_other + original_insul_r;
      if (r_total <= 0) return null;
      return parseFloat((1.0 / r_total).toFixed(4));
    }

    if (override.isCustom) {
      // 4-layer custom override (외장재, 단열재, 구조체, 내장재)
      const getR = (id, thickRaw, db) => {
        const t = parseFloat(thickRaw) || 0;
        if (t <= 0) return 0;
        const mat = db.find(m => m.id === id);
        const cond = mat ? mat.conductivity : 0;
        return cond > 0 ? (t / 1000.0) / cond : 0;
      };
      
      const rOuter = getR(override.outerId, override.outerThick, STRUCTURAL_MATERIALS);
      const rInsul = getR(override.insulId, override.insulThick, INSULATION_TYPES);
      const rCore = getR(override.coreId, override.coreThick, STRUCTURAL_MATERIALS);
      const rInner = getR(override.innerId, override.innerThick, STRUCTURAL_MATERIALS);
      
      const r_total_new = R_FILM + rOuter + rInsul + rCore + rInner;
      if (r_total_new <= 0) return null;
      return parseFloat((1.0 / r_total_new).toFixed(4));
    } else {
      // Fallback for simple insulation override (backward compatibility)
      let r_other = 0;
      constr.layers.forEach(l => {
        if (!l.isInsulation) {
          const thick = l.thickness || 0;
          const cond = l.conductivity || 1.0;
          r_other += cond > 0 ? (thick / 1000.0) / cond : 0;
        }
      });

      let lambda_new = 0.04;
      if (override.insulationId) {
        const product = INSULATION_TYPES.find(p => p.id === override.insulationId);
        if (product) lambda_new = product.conductivity;
      } else if (override.tier) {
        lambda_new = { premium: 0.025, high: 0.035, standard: 0.055, basic: 0.085 }[override.tier] || 0.04;
      }
  
      const thick_new = parseFloat(override.thickness) || 0;
      const r_insul_new = lambda_new > 0 ? (thick_new / 1000.0) / lambda_new : 0;
  
      const r_total_new = R_FILM + r_other + r_insul_new;
      if (r_total_new <= 0) return null;
      return parseFloat((1.0 / r_total_new).toFixed(4));
    }
  };

  const handleConstructionOverrideChange = (surfaceId, constructionId, overrideUpdate) => {
    setConstructionOverrides(prev => {
      const current = prev[surfaceId] || {};
      const next = { ...current, ...overrideUpdate };

      // 제품 변경에 따른 기본 두께 적용 로직
      if (overrideUpdate.isCustom) {
        if (overrideUpdate.outerId && overrideUpdate.outerId !== current.outerId) {
          next.outerThick = STRUCTURAL_MATERIALS.find(m => m.id === overrideUpdate.outerId)?.defaultThickness || 10;
        }
        if (overrideUpdate.coreId && overrideUpdate.coreId !== current.coreId) {
          next.coreThick = STRUCTURAL_MATERIALS.find(m => m.id === overrideUpdate.coreId)?.defaultThickness || 150;
        }
        if (overrideUpdate.innerId && overrideUpdate.innerId !== current.innerId) {
          next.innerThick = STRUCTURAL_MATERIALS.find(m => m.id === overrideUpdate.innerId)?.defaultThickness || 10;
        }
        if (overrideUpdate.insulId && overrideUpdate.insulId !== current.insulId) {
          next.insulThick = INSULATION_TYPES.find(m => m.id === overrideUpdate.insulId)?.defaultThickness || 100;
        }
      } else if (overrideUpdate.insulationId && overrideUpdate.insulationId !== current.insulationId) {
        // 단열재 단독 교체 모드일 경우
        const product = INSULATION_TYPES.find(p => p.id === overrideUpdate.insulationId);
        next.tier = product ? product.tier : 'standard';
        if (overrideUpdate.thickness === undefined) {
          next.thickness = product?.defaultThickness || 100;
        }
      }

      // 선택한 개별 서피스(Surface)에만 U-value 동적 재계산 반영
      const constr = materials?.constructions?.find(c => c.id === constructionId);
      if (constr) {
        const newU = calculateUpdatedUValue(constr, next);
        next.uValue = newU; // 백엔드로 전달하기 위해 override 객체에 저장
        
        setSurfaces(prevSurfaces =>
          prevSurfaces.map(s =>
            (s.id === surfaceId) ? { ...s, uValue: newU } : s
          )
        );
        
        // 🔥 현재 편집 중인 서피스의 U-Value도 업데이트 (저장 시 덮어쓰기 방지 및 슬라이더 연동)
        setEditState(prevEdit => {
          if (selectedId === surfaceId) {
            return { ...prevEdit, uValue: newU };
          }
          return prevEdit;
        });
      }
      return { ...prev, [surfaceId]: next };
    });
  };

  const handleResetInsulationOverride = (surfaceId, constructionId) => {
    const newOverrides = { ...constructionOverrides };
    delete newOverrides[surfaceId];
    setConstructionOverrides(newOverrides);

    // 원본 U-value 복원
    const constr = materials?.constructions?.find(c => c.id === constructionId);
    if (constr) {
      const origU = constr.uValue;
      setSurfaces(prevSurfaces =>
        prevSurfaces.map(s =>
          (s.id === surfaceId) ? { ...s, uValue: origU } : s
        )
      );
      
      setEditState(prevEdit => {
        if (selectedId === surfaceId) {
          return { ...prevEdit, uValue: origU };
        }
        return prevEdit;
      });
    }
  };

  const availableFloors = Array.from(
    new Set([...surfaces.map((s) => s.floor || 1), ...zones.map((z) => z.floor || 1)])
  ).sort((a, b) => a - b);
  const displayFloors = availableFloors.length > 0 ? availableFloors : [1, 2, 3];

  const selectedRegion = KOREA_REGIONS.flatMap(g => g.options).find(opt => opt.id === projectData.location) || { name: '서울특별시 (Seoul)' };
  const latitude = REGION_LATITUDES[projectData.location] || 37.56;
  // 가상 층 판별: floor 번호가 실제 층 수보다 크면 특수 공간(창고, 샤프트 등)
  const isVirtualFloor = (f) => realFloorCount > 0 && f > realFloorCount;

  const getActivityCategory = (activityId) => {
    const id = Number(activityId);
    if ([1105,1106,1103,1113,1116,1119,1122].includes(id)) return 'office';
    if ([1440,1441,1442,1443,1444,1114,1115,1107,1112,1120,1121,1445].includes(id)) return 'residential';
    if ([1447,1448,1449,1104,1457,1458,1452].includes(id)) return 'lab';
    if ([1108,1109,1117,1118].includes(id)) return 'restaurant';
    return 'default';
  };

  const calculateSurfaceArea = (vertices) => {
    if (!vertices || vertices.length < 3) return 0;
    let area = 0;
    const v0 = vertices[0];
    for (let i = 1; i < vertices.length - 1; i++) {
      const v1 = vertices[i];
      const v2 = vertices[i + 1];
      const ux = v1[0] - v0[0];
      const uy = v1[1] - v0[1];
      const uz = v1[2] - v0[2];
      const vx = v2[0] - v0[0];
      const vy = v2[1] - v0[1];
      const vz = v2[2] - v0[2];
      const cx = uy * vz - uz * vy;
      const cy = uz * vx - ux * vz;
      const cz = ux * vy - uy * vx;
      area += 0.5 * Math.sqrt(cx * cx + cy * cy + cz * cz);
    }
    return area;
  };

  const getZoneFloorArea = (zoneId) => {
    const zoneSurfaces = surfaces.filter(
      (s) => s.zone === zoneId && s.type && (s.type.toLowerCase().includes('floor') || s.type.toLowerCase().includes('slab'))
    );
    const areaSum = zoneSurfaces.reduce((acc, s) => acc + calculateSurfaceArea(s.vertices), 0);
    return areaSum >= 1.0 ? areaSum : 100.0;
  };

  const calcOutletPower = (zone, floorArea) => {
    const count = Number(zone?.outletCount || 0);
    if (count <= 0) return 0;
    const category = getActivityCategory(zone?.activityId);
    const wPerOutlet = OUTLET_W_PER_ACTIVITY[category] ?? OUTLET_W_PER_ACTIVITY.default;
    const DIVERSITY = 0.5;    // NREL/TP-7A40-54466 권장
    const UTILIZATION = 0.7;  // IEC 60364-8-1 ku 평균
    const area = floorArea > 0 ? floorArea : 1;
    const density = (count * wPerOutlet * DIVERSITY * UTILIZATION) / area;
    return Math.min(parseFloat(density.toFixed(2)), 25); // ASHRAE 90.1 상한 25 W/m²
  };

  const getSampleVerts = (w, h, pos, rot) => {
    const pts = [
      new THREE.Vector3(-w / 2, -h / 2, 0),
      new THREE.Vector3(w / 2, -h / 2, 0),
      new THREE.Vector3(w / 2, h / 2, 0),
      new THREE.Vector3(-w / 2, h / 2, 0),
    ];
    const euler = new THREE.Euler(rot.x, rot.y, rot.z);
    return pts.map((p) => {
      p.applyEuler(euler);
      p.add(new THREE.Vector3(pos.x, pos.y, pos.z));
      return [p.x, -p.z, p.y];
    });
  };

  const populateBuildingData = () => {
    const floors = 3;
    const w = 10;
    const d = 10;
    const h = 3;
    let newSurfaces = [];
    let newZones = [];
    let surfId = 1;

    for (let f = 1; f <= floors; f++) {
      const y = (f - 1) * h;
      const positions = [
        { x: -w / 2, z: -d / 2 },
        { x: w / 2, z: -d / 2 },
        { x: -w / 2, z: d / 2 },
        { x: w / 2, z: d / 2 },
      ];

      positions.forEach((pos, zIdx) => {
        const zoneName = `Z${f}-${zIdx + 1}`;
        const cx = pos.x;
        const cy = y + h / 2;
        const cz = pos.z;

        newZones.push({
          id: zoneName,
          floor: f,
          activityId: 1105,
          isConditioned: true,
          hvacSystemId: 2,
          heatingFuelId: 2,
          ventilationId: 2,
          heatingSetpoint: 20,
          coolingSetpoint: 26,
          peopleDensity: 0.1,
          lightingPower: 10.0,
          equipmentPower: 15.0,
          outletCount: 0,
          outletLoadType: 'sum',
        });

        const faces = [
          { dir: 'South', type: 'Wall', width: w, height: h, pos: { x: cx, y: cy, z: cz + d / 2 }, rot: { x: 0, y: 0, z: 0 } },
          { dir: 'North', type: 'Wall', width: w, height: h, pos: { x: cx, y: cy, z: cz - d / 2 }, rot: { x: 0, y: Math.PI, z: 0 } },
          { dir: 'East', type: 'Wall', width: d, height: h, pos: { x: cx + w / 2, y: cy, z: cz }, rot: { x: 0, y: Math.PI / 2, z: 0 } },
          { dir: 'West', type: 'Wall', width: d, height: h, pos: { x: cx - w / 2, y: cy, z: cz }, rot: { x: 0, y: -Math.PI / 2, z: 0 } },
          { dir: 'Roof', type: 'Roof', width: w, height: d, pos: { x: cx, y: cy + h / 2, z: cz }, rot: { x: -Math.PI / 2, y: 0, z: 0 } },
          { dir: 'Floor', type: 'Floor', width: w, height: d, pos: { x: cx, y: cy - h / 2, z: cz }, rot: { x: Math.PI / 2, y: 0, z: 0 } },
        ];

        faces.forEach((face) => {
          let isExteriorWall = false;
          if (face.dir === 'South' && cz > 0) isExteriorWall = true;
          if (face.dir === 'North' && cz < 0) isExteriorWall = true;
          if (face.dir === 'East' && cx > 0) isExteriorWall = true;
          if (face.dir === 'West' && cx < 0) isExteriorWall = true;

          let isRoof = face.dir === 'Roof' && f === floors;
          let isGroundFloor = face.dir === 'Floor' && f === 1;
          let isInternalSlab = face.dir === 'Floor' && f > 1;

          if (isExteriorWall || isRoof || isGroundFloor || isInternalSlab) {
            let finalType = face.type;
            if (isGroundFloor) finalType = 'GroundFloor';
            if (isInternalSlab) finalType = 'InternalSlab';

            newSurfaces.push({
              id: `S-${surfId++}`,
              zone: zoneName,
              adjacentZone: null,
              floor: f,
              type: finalType,
              direction: face.dir,
              width: face.width,
              height: face.height,
              pos: face.pos,
              rot: face.rot,
              vertices: getSampleVerts(face.width, face.height, face.pos, face.rot),
              uValue:
                finalType.includes('Floor') || finalType === 'InternalSlab'
                  ? 0.4
                  : finalType === 'Roof'
                  ? 0.2
                  : 0.8,
              wwr: finalType === 'Wall' ? 25 : 0,
              glazingId: 42,
              constructionId: finalType === 'Wall' ? 'C-Sample-Wall' : (finalType === 'Roof' ? 'C-Sample-Roof' : null),
            });
          }
        });
      });
    }
    setSurfaces(newSurfaces);
    setZones(newZones);
    
    // 샘플용 가상 단열재 데이터 주입 (DB 연동/단열재 표시 기능 활성화용)
    setMaterials({
      summary: { premium: 0, high: 2, standard: 0, basic: 0 },
      constructions: [
        {
          id: 'C-Sample-Wall',
          name: '외벽 (샘플)',
          totalArea: 1600, // 20x4x4면x5층 = 1600
          layers: [
            {
              isInsulation: true,
              materialName: '중성능 단열 보드 (샘플)',
              thickness: 100,
              conductivity: 0.040
            }
          ]
        },
        {
          id: 'C-Sample-Roof',
          name: '지붕 (샘플)',
          totalArea: 400, // 20x20
          layers: [
            {
              isInsulation: true,
              materialName: '중성능 단열 보드 (샘플)',
              thickness: 150,
              conductivity: 0.040
            }
          ]
        }
      ]
    });

    // 샘플도 업로드와 동일하게 설정 위저드 첫 페이지로 진입
    setStep('projectInfo');
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setUploadedFile(file);
    setUploadError(null);
    setStep('parsing');

    setMaterials(null);
    setConstructionOverrides({});
    try {
      const response = await uploadGbxml(file);
      if (response && response.data) {
        setSurfaces(response.data.surfaces || []);
        if (response.data.materials) {
          setMaterials(response.data.materials);
        }
        const mappedZones = (response.data.zones || []).map((z) => ({
          ...z,
          peopleDensity: z.peopleDensity || 0.1,
          lightingPower: z.lightingPower || 10.0,
          equipmentPower: z.equipmentPower || 15.0,
          outletCount: z.outletCount || 0,
          outletLoadType: z.outletLoadType || 'sum',
        }));
        setZones(mappedZones);
        
        // 💡 면 갭 경고 처리
        const warnings = response.data.warnings || [];
        if (warnings.length > 0) {
          setGapWarnings(warnings);
        }
        // 💡 실제 층수 저장 (가상 층 구분용)
        if (response.data.floorLevels) {
          setRealFloorCount(response.data.floorLevels);
        }
      }
      setStep('upload');
    } catch (error) {
      console.error('파싱 에러:', error);
      setUploadError('백엔드 서버(Python) 응답이 없거나 gbXML 파일 해석에 실패했습니다.');
      setStep('upload');
    }
  };

  const handleStartWithSample = () => {
    setUploadError(null);
    setUploadedFile({ name: 'Sample_Building_V1.xml' });
    populateBuildingData();
  };

  const handleModeSwitch = (mode) => {
    if (editMode !== mode) {
      handleSaveClose();
      setEditMode(mode);
      setSelectedId(null);
      setHoveredId(null);
    }
  };

  const handleSurfaceClick = (data) => {
    if (editMode !== 'surface') return;
    if (selectedId && selectedId !== data?.id) handleSaveClose();

    setSelectedId(data ? data.id : null);
    if (data) {
      setEditState({ wwr: data.wwr, uValue: data.uValue, glazingId: data.glazingId || 42 });
    }
  };

  const handleZoneClick = (zoneId) => {
    if (editMode !== 'zone') return;
    if (selectedId && selectedId !== zoneId) handleSaveClose();

    setSelectedId(zoneId ? zoneId : null);
    const zData = zones.find((z) => z.id === zoneId);
    if (zData) {
      setEditState({ ...zData });
    }
  };

  const handleSaveClose = () => {
    if (!selectedId) return;
    if (editMode === 'surface') {
      setSurfaces((prev) =>
        prev.map((s) => (s.id === selectedId ? { ...s, ...editState } : s))
      );
    } else if (editMode === 'zone') {
      setZones((prev) =>
        prev.map((z) => (z.id === selectedId ? { ...z, ...editState } : z))
      );
    }

    setSelectedId(null);
    setLightCalc((p) => ({ ...p, active: false }));
    setEquipCalc((p) => ({ ...p, active: false }));
  };

  // 제안 1건의 상태 변경만 수행하고, 무엇을 바꿨는지 요약 문자열을 반환한다.
  // (alert/화면이동은 호출하는 쪽에서 일괄 처리 → 여러 제안을 한 번에 적용 가능)
  const applyRecommendationChanges = (type) => {
    if (type === 'window') {
      setSurfaces((prev) =>
        prev.map((s) => {
          if (s.type === 'Window' || s.type === 'Skylight') {
            return { ...s, glazingId: 42 }; // 일반 복층 유리(ID 42)로 하향
          }
          return s;
        })
      );
      return '창호를 일반 복층유리로 하향';
    } else if (type === 'insulation') {
      // 모든 구조체의 단열재를 일반 등급 제품(비드법 1종 1호, ID 1)으로 일괄 교체
      const stdProduct = INSULATION_TYPES.find(p => p.tier === 'standard') || INSULATION_TYPES[0];
      
      const newOverrides = { ...constructionOverrides };
      const updatedUValues = {};

      let changedCount = 0;

      // 1. 기존 오버라이드 중 고성능 다운그레이드
      Object.keys(newOverrides).forEach((id) => {
        if (newOverrides[id].tier === 'premium' || newOverrides[id].tier === 'high') {
          changedCount++;
          const newOverride = { insulationId: stdProduct.id, tier: 'standard', thickness: newOverrides[id].thickness || 100 };
          
          const s = surfaces.find(surf => surf.id === id);
          if (s && materials?.constructions) {
            const c_ref = s.constructionRef || s.constructionId;
            const c = materials.constructions.find(con => con.id === c_ref);
            if (c) {
              const newU = calculateUpdatedUValue(c, newOverride);
              newOverride.uValue = newU;
              updatedUValues[id] = newU;
            }
          }
          newOverrides[id] = newOverride;
        }
      });

      // 2. 오버라이드가 없는 원본 고성능 벽체 추가
      if (materials?.constructions) {
        surfaces.forEach((s) => {
          if (!newOverrides[s.id]) {
            const c_ref = s.constructionRef || s.constructionId;
            const c = materials.constructions.find(con => con.id === c_ref);
            if (c) {
              const insul = c.layers?.find(l => l.isInsulation);
              if (insul && insul.conductivity <= 0.045) {
                changedCount++;
                const newOverride = { insulationId: stdProduct.id, tier: 'standard', thickness: insul.thickness || 100 };
                const newU = calculateUpdatedUValue(c, newOverride);
                newOverride.uValue = newU;
                updatedUValues[s.id] = newU;
                newOverrides[s.id] = newOverride;
              }
            }
          }
        });
      }

      setConstructionOverrides(newOverrides);
      if (Object.keys(updatedUValues).length > 0) {
        setSurfaces(prevSurfaces => prevSurfaces.map(s => 
          updatedUValues[s.id] !== undefined ? { ...s, uValue: updatedUValues[s.id] } : s
        ));
      }
      
      return `단열재 ${changedCount}개 외벽을 일반 등급(EPS/미네랄울)으로 하향`;
    } else if (type === 'hvac') {
      setProjectData((prev) => ({ ...prev, geothermalApplied: false }));
      return '지열(Geothermal) 시스템 도입 취소';
    } else if (type === 'led') {
      const manualZones = zones.filter((z) => z.ledFixtureCount > 0);
      if (manualZones.length > 0) {
        const reducedCount = manualZones.reduce(
          (acc, z) => acc + (z.ledFixtureCount - Math.floor(z.ledFixtureCount * 0.5)),
          0
        );
        setZones((prev) =>
          prev.map((z) =>
            z.ledFixtureCount > 0 ? { ...z, ledFixtureCount: Math.floor(z.ledFixtureCount * 0.5) } : z
          )
        );
        return `LED 교체 수량 ${reducedCount}개 축소`;
      }
      setProjectData((prev) => ({ ...prev, ledReductionActive: true }));
      return '비필수 구역 LED 교체 제외';
    }
    return null;
  };

  // 선택한 여러 제안을 한 번에 적용 → 안내 1회 + 화면 이동 1회
  const handleApplyRecommendations = (types) => {
    if (!types || types.length === 0) return;
    const summaries = types.map(applyRecommendationChanges).filter(Boolean);
    alert(
      `✅ ${summaries.length}개 제안을 적용했습니다.\n\n` +
      summaries.map((s) => `· ${s}`).join('\n') +
      `\n\n하단의 [시뮬레이션 가동] 버튼을 눌러 낮아진 예산을 확인해 주세요.`
    );
    setStep('floorView');
  };

  const handleSimulation = async () => {
    setStep('loading');
    setLoadingMsgIdx(0);

    const interval = setInterval(() => {
      setLoadingMsgIdx((prev) => Math.min(prev + 1, LOADING_MESSAGES.length - 1));
    }, 1500);
    try {
      // 선택된 모드의 실측 필드만 전송 (다른 모드의 잔여값이 우선순위를 뒤집지 않도록)
      const _ba = projectData.baselineActual || {};
      const baselineActual =
        _ba.mode === 'usage'
          ? { mode: 'usage', elecKwh: _ba.elecKwh, heatKwh: _ba.heatKwh }
          : { mode: 'bill', elecBill: _ba.elecBill, heatBill: _ba.heatBill };
      const payload = {
        projectData: { ...projectData, baselineActual },
        zones: zones,
        surfaces: surfaces,
        materials: materials,
        constructionOverrides: constructionOverrides,
        // lccParameters / hvacUpgradeActive는 projectData 안에 포함되어 함께 전송됨
        // (백엔드는 projectData에서 읽음 — 최상위로 보내면 SimulationPayload에서 누락됨)
      };
      const response = await runSimulation(payload);

      clearInterval(interval);
      setRes(response.result);
      setStep('result');
      // 💡 [수정] 시뮬레이션 완료 시 에너지 탭이 먼저 보이도록 강제
      setActiveResultTab('energy'); 
    } catch (error) {
      clearInterval(interval);
      alert('백엔드 시뮬레이션 연동에 실패했습니다. 파이썬 서버가 정상 동작하는지 확인하세요.');
      setStep('floorView');
    }
  };

  const getZebGradeInfo = (rate) => {
    const r = Number(rate) || 0;
    if (r >= 100) return '1등급';
    if (r >= 80) return '2등급';
    if (r >= 60) return '3등급';
    if (r >= 40) return '4등급';
    if (r >= 20) return '5등급';
    return '등급 외';
  };

  const getAnnualChartData = () => {
    if (!res || !res.matrix) return [];
    const m = res.matrix;
    const categoriesList = [
      { id: 'heating', name: '난방', color: '#F87171' },
      { id: 'cooling', name: '냉방', color: '#60A5FA' },
      { id: 'hotwater', name: '급탕', color: '#FB923C' },
      { id: 'lighting', name: '조명', color: '#FACC15' },
      { id: 'ventilation', name: '환기', color: '#4ADE80' },
      { id: 'equipment', name: '기기', color: '#A78BFA' },
      { id: 'renewable', name: '신재생', color: '#2DD4BF' },
    ];

    return [
      {
        name: '요구량',
        ...categoriesList.reduce((acc, c) => ({ ...acc, [c.name]: Number(m[c.id]?.req || 0) }), {}),
      },
      {
        name: '소요량',
        ...categoriesList.reduce((acc, c) => ({ ...acc, [c.name]: Number(m[c.id]?.con || 0) }), {}),
      },
      {
        name: '1차 소요량',
        ...categoriesList.reduce((acc, c) => ({ ...acc, [c.name]: Number(m[c.id]?.con || 0) * 2.75 }), {}),
      },
      {
        name: '등급용 1차',
        ...categoriesList.reduce((acc, c) => ({
          ...acc,
          [c.name]: c.id === 'equipment' ? 0 : Number(m[c.id]?.con || 0) * 2.1
        }), {}),
      },
    ];
  };

  const theme = {
    bg: isDarkMode ? 'bg-[#0B0F19] text-slate-200' : 'bg-[#DFDCD5] text-slate-800',
    card: isDarkMode ? 'bg-[#151B2B] border-slate-800' : 'bg-[#EAE8E3] border-[#D5D2C9]',
    panel: isDarkMode ? 'bg-slate-900/80 border-slate-700' : 'bg-white/80 border-slate-300',
    textMain: isDarkMode ? 'text-white' : 'text-slate-900',
    textSub: isDarkMode ? 'text-slate-400' : 'text-slate-600',
    input: isDarkMode ? 'bg-slate-800 border-slate-700 text-white' : 'bg-white border-slate-300 text-slate-800',
    tableHeader: isDarkMode ? 'bg-white/5 text-emerald-400 border-slate-700' : 'bg-[#DFDCD5] text-slate-800 border-[#C4C1B6]',
    tableBorder: isDarkMode ? 'border-slate-700' : 'border-[#D5D2C9]',
    chartText: isDarkMode ? '#94a3b8' : '#475569',
    chartGrid: isDarkMode ? 'rgba(255,255,255,0.05)' : '#C4C1B6',
    pieBg: isDarkMode ? 'rgba(255,255,255,0.05)' : '#DFDCD5',
  };

  const selectedSurfaceData = editMode === 'surface' ? surfaces.find((s) => s.id === selectedId) : null;

  // 동적 창호 드롭다운 처리 로직
  const currentGlazing =
    GLAZING_TYPES.find((g) => g.id === (editState.glazingId || 42)) ||
    GLAZING_TYPES.find((g) => g.id === 42);
  const currentPanes = getPanesCategory(currentGlazing?.name);
  const currentType = getCoatingType(currentGlazing?.name);
  const availableTypes = Array.from(
    new Set(GLAZING_TYPES.filter((g) => getPanesCategory(g.name) === currentPanes).map((g) => getCoatingType(g.name)))
  );
  const filteredGlazingList = GLAZING_TYPES.filter(
    (g) => getPanesCategory(g.name) === currentPanes && getCoatingType(g.name) === currentType
  );

  const handlePanesChange = (newPanes) => {
    let match = GLAZING_TYPES.find(
      (g) => getPanesCategory(g.name) === newPanes && getCoatingType(g.name) === currentType
    );
    if (!match) match = GLAZING_TYPES.find((g) => getPanesCategory(g.name) === newPanes);
    if (match) setEditState((prev) => ({ ...prev, glazingId: match.id }));
  };

  const handleTypeChange = (newType) => {
    let match = GLAZING_TYPES.find(
      (g) => getPanesCategory(g.name) === currentPanes && getCoatingType(g.name) === newType
    );
    if (match) setEditState((prev) => ({ ...prev, glazingId: match.id }));
  };

  // 💡 LCC(현금흐름) 차트 데이터 계산 로직
  const getCashFlowData = () => {
    if (!res || !res.financial) return [];

    // 백엔드에서 계산된 값이 넘어오면 그것을 우선 사용
    const f = res.financial;
    const retrofitRunningCost = f.total_energy_bill;
    const capitalCost = f.capital_cost;
    // 기준 건물 운영비: 백엔드 baseline_assumptions와 단일 소스로 공유 → 차트/NPV/IRR 일관.
    //   실측 입력 시 base_running_cost가 내려오고, 없으면 1.6배 추정으로 환산.
    const ba = f.baseline_assumptions || {};
    const baseMultiplier = ba.running_cost_multiplier || 1.6;
    const baseRunningCost = ba.base_running_cost > 0 ? ba.base_running_cost : retrofitRunningCost * baseMultiplier;
    const annualSavings = baseRunningCost - retrofitRunningCost;
    
    const params = f.lcc_parameters || { inflation_rate: 2, lifecycle_years: 15 };
    const inflationRate = params.inflation_rate / 100;
    const years = params.lifecycle_years || 20;

    const data = [];
    let cumulativeBase = 0;
    let cumulativeRetrofit = -capitalCost; 

    for (let year = 0; year <= years; year++) {
      if (year > 0) {
        cumulativeBase -= baseRunningCost * Math.pow(1 + inflationRate, year - 1);
        cumulativeRetrofit -= retrofitRunningCost * Math.pow(1 + inflationRate, year - 1);
      }

      data.push({
        year: `${year}년차`,
        '기존 노후건물 유지': Math.round(cumulativeBase),
        '친환경 리모델링 (투자+운영)': Math.round(cumulativeRetrofit),
        '누적 순이익 (ROI)': Math.round(cumulativeRetrofit - cumulativeBase),
      });
    }
    
    // 고급 재무 지표
    const npv = f.npv || 0;
    const irr = f.irr || 0;
    
    // payback 추산 (수익이 0을 돌파하는 시점)
    let paybackYears = capitalCost / annualSavings; 
    let exactPayback = data.findIndex(d => d['누적 순이익 (ROI)'] >= 0);
    if(exactPayback > 0) {
        // 선형 보간으로 소수점 연도 추정
        const prev = data[exactPayback - 1]['누적 순이익 (ROI)'];
        const curr = data[exactPayback]['누적 순이익 (ROI)'];
        paybackYears = (exactPayback - 1) + Math.abs(prev) / (curr - prev);
    } else {
        paybackYears = 0;
    }

    return { data, annualSavings, paybackYears, npv, irr, params, baselineAssumptions: f.baseline_assumptions };
  };

  const lccAnalysis = getCashFlowData();
  const inactiveBtnClass = isDarkMode
    ? 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
    : 'text-slate-500 hover:text-slate-700 hover:bg-slate-300';

  return (
    <>
      <style>{`
        #root { max-width: none !important; width: 100% !important; margin: 0 !important; padding: 0 !important; text-align: left !important; } 
        body { margin: 0 !important; display: block !important; min-width: 100vw !important; min-height: 100vh !important; ${step === 'landing' ? '' : 'overflow: hidden !important;'} }

        /* Custom Toggle Switch CSS */
        .toggle-switch {
          position: relative;
          width: 100px;
          height: 50px;
          --light: #d8dbe0;
          --dark: #28292c;
          --link: rgb(27, 129, 112);
          --link-hover: rgb(24, 94, 82);
        }
        .switch-label {
          position: absolute;
          width: 100%;
          height: 100%;
          background-color: var(--dark);
          border-radius: 25px;
          cursor: pointer;
          border: 3px solid var(--dark);
          margin: 0;
        }
        .checkbox-input {
          position: absolute;
          display: none;
        }
        .slider {
          position: absolute;
          width: 100%;
          height: 100%;
          border-radius: 25px;
          -webkit-transition: 0.3s;
          transition: 0.3s;
          pointer-events: none;
        }
        .checkbox-input:checked ~ .slider {
          background-color: var(--light);
        }
        .slider::before {
          content: "";
          position: absolute;
          top: 10px;
          left: 10px;
          width: 25px;
          height: 25px;
          border-radius: 50%;
          -webkit-box-shadow: inset 10px -3px 0px 0px var(--light);
          box-shadow: inset 10px -3px 0px 0px var(--light);
          background-color: var(--dark);
          -webkit-transition: 0.3s;
          transition: 0.3s;
        }
        .checkbox-input:checked ~ .slider::before {
          -webkit-transform: translateX(49px);
          -ms-transform: translateX(49px);
          transform: translateX(49px);
          background-color: var(--dark);
          -webkit-box-shadow: none;
          box-shadow: none;
        }

        /* Custom Bouncy Loading CSS */
        .loading-wrapper {
          width: 200px;
          height: 60px;
          position: relative;
          z-index: 1;
        }
        .loading-circle {
          width: 20px;
          height: 20px;
          position: absolute;
          border-radius: 50%;
          background-color: #10b981; /* Emerald 500 */
          left: 15%;
          transform-origin: 50%;
          animation: circle7124 .5s alternate infinite ease;
        }
        @keyframes circle7124 {
          0% {
            top: 60px;
            height: 5px;
            border-radius: 50px 50px 25px 25px;
            transform: scaleX(1.7);
          }
          40% {
            height: 20px;
            border-radius: 50%;
            transform: scaleX(1);
          }
          100% {
            top: 0%;
          }
        }
        .loading-circle:nth-child(2) {
          left: 45%;
          animation-delay: .2s;
        }
        .loading-circle:nth-child(3) {
          left: auto;
          right: 15%;
          animation-delay: .3s;
        }
        .loading-shadow {
          width: 20px;
          height: 4px;
          border-radius: 50%;
          background-color: rgba(0,0,0,0.5);
          position: absolute;
          top: 62px;
          transform-origin: 50%;
          z-index: -1;
          left: 15%;
          filter: blur(1px);
          animation: shadow046 .5s alternate infinite ease;
        }
        @keyframes shadow046 {
          0% {
            transform: scaleX(1.5);
          }
          40% {
            transform: scaleX(1);
            opacity: .7;
          }
          100% {
            transform: scaleX(.2);
            opacity: .4;
          }
        }
        .loading-shadow:nth-child(4) {
          left: 45%;
          animation-delay: .2s
        }
        .loading-shadow:nth-child(5) {
          left: auto;
          right: 15%;
          animation-delay: .3s;
        }
      `}</style>

      {/* 💡 면 갭(Gap) 경고 모달 */}
      {gapWarnings.length > 0 && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className={`w-full max-w-lg mx-4 rounded-3xl shadow-2xl border p-8 ${isDarkMode ? 'bg-[#151B2B] border-slate-700' : 'bg-white border-slate-200'}`}>
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-2xl bg-amber-500/20 flex items-center justify-center">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                  <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
                </svg>
              </div>
              <div>
                <h3 className={`text-lg font-black ${isDarkMode ? 'text-white' : 'text-slate-900'}`}>건물 모델 검증 경고</h3>
                <p className={`text-xs ${isDarkMode ? 'text-slate-400' : 'text-slate-500'}`}>gbXML 기하학 분석 결과</p>
              </div>
            </div>

            <p className={`text-sm mb-4 ${isDarkMode ? 'text-slate-300' : 'text-slate-600'}`}>
              다음 Zone에서 면과 면이 완전히 맞닿지 않는 부분이 감지되었습니다.
              이는 CAD 모델링 시 발생하는 미세한 틈(Gap)일 수 있습니다.
            </p>

            <div className={`rounded-2xl border p-4 mb-6 max-h-48 overflow-y-auto ${isDarkMode ? 'bg-slate-900/50 border-slate-700' : 'bg-slate-50 border-slate-200'}`}>
              {gapWarnings.map((w, i) => (
                <div key={i} className={`flex justify-between items-center py-2 ${i > 0 ? (isDarkMode ? 'border-t border-slate-700' : 'border-t border-slate-200') : ''}`}>
                  <span className={`text-sm font-mono font-bold ${isDarkMode ? 'text-slate-200' : 'text-slate-700'}`}>{w.zone}</span>
                  <span className={`text-xs font-bold px-3 py-1 rounded-full ${
                    w.deviation > 20 ? 'bg-red-500/20 text-red-400' : 'bg-amber-500/20 text-amber-500'
                  }`}>
                    오차: {w.deviation}%
                  </span>
                </div>
              ))}
            </div>

            <p className={`text-xs mb-6 ${isDarkMode ? 'text-slate-500' : 'text-slate-400'}`}>
              이 상태로 시뮬레이션을 진행할 수 있지만, 해당 Zone의 냉난방 부하 결과 정확도가 떨어질 수 있습니다.
            </p>

            <div className="flex gap-3">
              <button
                onClick={() => {
                  setGapWarnings([]);
                  setSurfaces([]);
                  setZones([]);
                  setMaterials(null);
                  setConstructionOverrides({});
                  setUploadedFile(null);
                  if (fileInputRef.current) fileInputRef.current.value = '';
                }}
                className={`flex-1 py-3 rounded-2xl text-sm font-bold border transition-all ${
                  isDarkMode ? 'border-slate-600 text-slate-300 hover:bg-slate-800' : 'border-slate-300 text-slate-600 hover:bg-slate-100'
                }`}
              >
                수정하고 재업로드
              </button>
              <button
                onClick={() => setGapWarnings([])}
                className="flex-1 py-3 rounded-2xl text-sm font-bold bg-amber-500 hover:bg-amber-400 text-black transition-all shadow-lg shadow-amber-500/25"
              >
                그대로 진행
              </button>
            </div>
          </div>
        </div>
      )}

      {step === 'landing' ? (
        <div className="min-h-screen selection:bg-brand-primary/30 bg-white overflow-y-auto pb-24">
          <Navigation onStart={() => setStep('upload')} />
          <main>
            <Hero />
            <Manual onStart={() => setStep('upload')} />
          </main>
        </div>
      ) : (
      <div className={`h-screen w-full transition-colors duration-300 ${theme.bg} font-sans flex flex-col overflow-hidden`}>
        <header className={`flex-shrink-0 px-8 py-4 border-b ${isDarkMode ? 'border-slate-800 bg-[#0B0F19]' : 'border-[#D5D2C9] bg-[#DFDCD5]'} flex justify-between items-center z-10 shadow-sm`}>
          <div 
            className="flex items-center gap-3 cursor-pointer hover:opacity-80 transition-opacity" 
            onClick={() => setStep('landing')}
          >
            <div className="w-8 h-8 bg-emerald-500 rounded-lg flex items-center justify-center shadow-lg">
              <Layers className="text-white" size={18} />
            </div>
            <h1 className="text-lg font-black tracking-tighter uppercase">ZeroBase</h1>
          </div>
          <div className="hidden md:flex items-center gap-4 text-[10px] font-black tracking-widest uppercase opacity-60">
            <span className={step === 'upload' ? 'text-emerald-500' : ''}>1. 업로드</span> <ArrowRight size={10} />
            <span className={['projectInfo','renewable','budget','financial'].includes(step) ? 'text-emerald-500' : ''}>2. 설정</span> <ArrowRight size={10} />
            <span className={step === 'buildingView' || step === 'floorView' ? 'text-emerald-500' : ''}>3. 3D 모델</span> <ArrowRight size={10} />
            <span className={step === 'result' ? 'text-emerald-500' : ''}>4. 분석</span>
          </div>
          <div className="toggle-switch" style={{ transform: 'scale(0.6)', transformOrigin: 'right center' }}>
            <label className="switch-label">
              <input 
                type="checkbox" 
                className="checkbox-input" 
                checked={!isDarkMode}
                onChange={() => setIsDarkMode(!isDarkMode)}
              />
              <span className="slider"></span>
            </label>
          </div>
        </header>

        <main className="flex-1 flex overflow-hidden relative w-full h-full">
          {/* STEP 1: Upload & Project Setup */}
          {step === 'upload' && (
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
                        <p className={`text-sm text-center ${theme.textSub}`}>클릭하여 파일을 선택하세요 (.xml)</p>
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
                        onClick={() => {
                          setUploadedFile(null);
                          setSurfaces([]);
                          setZones([]);
                          setMaterials(null);
                          setConstructionOverrides({});
                        }}
                        className={`mt-8 text-xs font-bold transition-colors underline ${isDarkMode ? 'text-slate-500 hover:text-red-400' : 'text-slate-400 hover:text-red-500'}`}
                      >
                        다른 파일 다시 업로드하기
                      </button>
                    </div>
                  )}
                </div>
            </WizardShell>
          )}

          {/* STEP: 프로젝트 기본 정보 */}
          {step === 'projectInfo' && (
            <WizardShell
              theme={theme} isDarkMode={isDarkMode} setStep={setStep}
              icon={<Building size={32} />}
              title="프로젝트 기본 정보"
              subtitle="건물 이름·용도·기상 지역·정북 방향을 설정하세요."
              back="upload" next="renewable"
            >
              <div className={`p-8 rounded-[2rem] border ${theme.card}`}>
                    <div className="space-y-4">
                      <div>
                        <label className={`block text-[10px] font-black uppercase tracking-widest mb-2 ${theme.textSub}`}>Project Name</label>
                        <input
                          type="text"
                          value={projectData.name}
                          onChange={(e) => setProjectData({ ...projectData, name: e.target.value })}
                          className={`w-full p-4 rounded-2xl outline-none border ${theme.input} focus:border-emerald-500`}
                        />
                      </div>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className={`block text-[10px] font-black uppercase tracking-widest mb-2 ${theme.textSub}`}>건물 기본 용도</label>
                          <select
                            value={projectData.activityId}
                            onChange={(e) => setProjectData({ ...projectData, activityId: parseInt(e.target.value) })}
                            className={`w-full p-4 rounded-2xl outline-none border appearance-none ${theme.input} focus:border-emerald-500`}
                          >
                            {ACTIVITIES.map((act) => (
                              <option key={act.id} value={act.id}>
                                {act.name}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label className={`block text-[10px] font-black uppercase tracking-widest mb-2 ${theme.textSub}`}>기상 데이터 지역 (Location)</label>
                          <div className="relative">
                            <select
                              value={projectData.location}
                              onChange={(e) => setProjectData({ ...projectData, location: e.target.value })}
                              className={`w-full p-4 pl-10 rounded-2xl outline-none border appearance-none ${theme.input} focus:border-emerald-500`}
                            >
                              {KOREA_REGIONS.map((group) => (
                                <optgroup key={group.group} label={group.group}>
                                  {group.options.map((opt) => (
                                    <option key={opt.id} value={opt.id}>
                                      {opt.name}
                                    </option>
                                  ))}
                                </optgroup>
                              ))}
                            </select>
                            <MapPin size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-emerald-500" />
                          </div>
                        </div>
                      </div>
                      <div>
                        <label className={`block text-[10px] font-black uppercase tracking-widest mb-2 mt-2 ${theme.textSub}`}>건물 정북방향 회전각(°)</label>
                        <div className="relative">
                          <input
                            type="number"
                            value={projectData.orientation}
                            onChange={(e) => setProjectData({ ...projectData, orientation: parseInt(e.target.value) || 0 })}
                            className={`w-full p-4 pl-10 rounded-2xl outline-none border ${theme.input} focus:border-emerald-500`}
                          />
                          <Compass size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" />
                        </div>
                      </div>

                      <div
                        className={`mt-4 p-4 rounded-xl flex items-center justify-between cursor-pointer border-2 transition-all ${projectData.customSchedule.useCustom ? 'border-indigo-500 bg-indigo-500/10' : 'border-slate-500/30 bg-black/5'}`}
                        onClick={() => setProjectData((prev) => ({ ...prev, customSchedule: { ...prev.customSchedule, useCustom: !prev.customSchedule.useCustom } }))}
                      >
                        <div className="flex items-center gap-3">
                          <div className={`p-2 rounded-lg ${projectData.customSchedule.useCustom ? 'bg-indigo-500 text-white' : 'bg-slate-600 text-slate-300'}`}>
                            <Clock size={18} />
                          </div>
                          <div>
                            <span className={`block font-black text-sm ${projectData.customSchedule.useCustom ? 'text-indigo-500' : theme.textSub}`}>
                              사용자 스케줄 적용
                            </span>
                            <span className="text-[10px] opacity-60">용도별 스케줄 대신 직접 수정합니다.</span>
                          </div>
                        </div>
                        <div className="flex items-center gap-3">
                          {projectData.customSchedule.useCustom && (
                            <button
                              onClick={(e) => { e.stopPropagation(); setShowScheduleModal(true); }}
                              className="px-3 py-1.5 bg-indigo-500 hover:bg-indigo-600 text-white text-xs font-bold rounded-lg shadow-sm transition-colors"
                            >
                              스케줄 수정
                            </button>
                          )}
                          {projectData.customSchedule.useCustom ? (
                            <ToggleRight size={32} className="text-indigo-500" />
                          ) : (
                            <ToggleLeft size={32} className="text-slate-500" />
                          )}
                        </div>
                      </div>
                    </div>
              </div>
            </WizardShell>
          )}

          {/* STEP: 신재생 & 에너지 설비 */}
          {step === 'renewable' && (
            <WizardShell
              theme={theme} isDarkMode={isDarkMode} setStep={setStep}
              icon={<Sun size={32} />}
              title="신재생 에너지 & 설비"
              subtitle="태양광·지열·난방 열원·설비 교체 여부를 설정하세요."
              back="projectInfo" next="budget"
            >
              <div className={`p-8 rounded-[2rem] border ${theme.card} border-blue-500/20`}>
                    <div className="space-y-6">
                      <div>
                        <label className={`flex justify-between items-center text-sm font-black mb-3 ${theme.textMain}`}>
                          <span className="flex items-center gap-2">
                            <Sun className="text-yellow-500" size={16} /> 태양광(PV) 패널 설치 용량
                          </span>
                          <span className="text-blue-500 bg-blue-500/10 px-3 py-1 rounded-lg text-[11px] uppercase tracking-widest">
                            {projectData.pvCapacity} kW
                          </span>
                        </label>
                        <input
                          type="range"
                          min="0"
                          max="100"
                          step="5"
                          value={projectData.pvCapacity}
                          onChange={(e) => setProjectData({ ...projectData, pvCapacity: parseInt(e.target.value) })}
                          className="w-full h-3 rounded-full appearance-none accent-blue-500 bg-slate-700 cursor-pointer"
                        />
                      </div>

                      {/* 난방 열원 선택 — 요금·1차에너지·CO2가 열원별로 달라짐 */}
                      <div>
                        <label className={`flex items-center gap-2 text-sm font-black mb-3 ${theme.textMain}`}>
                          <Flame className="text-orange-500" size={16} /> 난방 열원 (Heating Source)
                        </label>
                        <select
                          value={projectData.heatSource}
                          onChange={(e) => setProjectData({ ...projectData, heatSource: parseInt(e.target.value) })}
                          disabled={projectData.geothermalApplied}
                          className={`w-full p-3 text-sm font-bold rounded-xl border outline-none ${theme.input} focus:border-orange-500 ${projectData.geothermalApplied ? 'opacity-40 cursor-not-allowed' : ''}`}
                        >
                          {FUEL_TYPES.map((f) => (
                            <option key={f.id} value={f.id}>{f.name}</option>
                          ))}
                        </select>
                        <p className="text-[10px] opacity-60 mt-1">
                          {projectData.geothermalApplied
                            ? '지열 적용 시 난방은 전기(히트펌프)로 계산됩니다.'
                            : '열원에 따라 난방 요금·1차에너지·CO2 계수가 달라집니다.'}
                        </p>
                      </div>

                      <div
                        className={`p-4 rounded-xl flex items-center justify-between cursor-pointer border-2 transition-all ${projectData.geothermalApplied ? 'border-emerald-500 bg-emerald-500/10' : 'border-slate-500/30 bg-black/5'}`}
                        onClick={() => setProjectData((prev) => ({ ...prev, geothermalApplied: !prev.geothermalApplied }))}
                      >
                        <div className="flex items-center gap-3">
                          <div className={`p-2 rounded-lg ${projectData.geothermalApplied ? 'bg-emerald-500 text-white' : 'bg-slate-600 text-slate-300'}`}>
                            <Zap size={18} />
                          </div>
                          <div>
                            <span className={`block font-black text-sm ${projectData.geothermalApplied ? 'text-emerald-500' : theme.textSub}`}>
                              지열(Geothermal) 히트펌프 적용
                            </span>
                            <span className="text-[10px] opacity-60">냉난방 기기의 효율(COP)을 극대화합니다.</span>
                          </div>
                        </div>
                        {projectData.geothermalApplied ? (
                          <ToggleRight size={32} className="text-emerald-500" />
                        ) : (
                          <ToggleLeft size={32} className="text-slate-500" />
                        )}
                      </div>
                      
                      <div
                        className={`mt-4 p-4 rounded-xl flex items-center justify-between cursor-pointer border-2 transition-all ${projectData.hvacUpgradeActive ? 'border-orange-500 bg-orange-500/10' : 'border-slate-500/30 bg-black/5'}`}
                        onClick={() => setProjectData((prev) => ({ ...prev, hvacUpgradeActive: !prev.hvacUpgradeActive }))}
                      >
                        <div className="flex items-center gap-3">
                          <div className={`p-2 rounded-lg ${projectData.hvacUpgradeActive ? 'bg-orange-500 text-white' : 'bg-slate-600 text-slate-300'}`}>
                            <Thermometer size={18} />
                          </div>
                          <div>
                            <span className={`block font-black text-sm ${projectData.hvacUpgradeActive ? 'text-orange-500' : theme.textSub}`}>
                              설비 시스템 전면 교체 (HVAC Upgrade)
                            </span>
                            <span className="text-[10px] opacity-60">기존 냉난방 설비의 노후화로 인해 기기를 완전히 교체할 경우 체크하세요. (공사비 증가)</span>
                          </div>
                        </div>
                        {projectData.hvacUpgradeActive ? (
                          <ToggleRight size={32} className="text-orange-500" />
                        ) : (
                          <ToggleLeft size={32} className="text-slate-500" />
                        )}
                      </div>
                    </div>
              </div>
            </WizardShell>
          )}

          {/* STEP: 목표 예산 & 기존 건물 사용량 */}
          {step === 'budget' && (
            <WizardShell
              theme={theme} isDarkMode={isDarkMode} setStep={setStep}
              icon={<PiggyBank size={32} />}
              title="목표 예산 & 기존 건물 사용량"
              subtitle="목표 공사비와, 리모델링 전 실제 사용량을 입력하세요."
              back="renewable" next="financial"
            >
              <div className={`p-8 rounded-[2rem] border ${theme.card}`}>
                <div className="space-y-6">
                      <div className="p-4 rounded-xl border-2 border-slate-500/30 bg-black/5">
                        <label className="flex items-center justify-between mb-2">
                          <span className={`font-black flex items-center gap-2 ${theme.textMain}`}>
                            <PiggyBank className="text-pink-500" size={18} /> 목표 공사 예산 (단위: 만 원)
                          </span>
                          <span className="text-pink-500 bg-pink-500/10 px-3 py-1 rounded-lg text-[11px] font-black uppercase tracking-widest">
                            {projectData.targetBudget === 0 ? '미설정 (제한없음)' : `${projectData.targetBudget.toLocaleString()} 만 원`}
                          </span>
                        </label>
                        <input
                          type="number"
                          min="0"
                          step="100"
                          value={projectData.targetBudget || ''}
                          placeholder="예: 5000 (5천만 원)"
                          onChange={(e) => setProjectData({ ...projectData, targetBudget: parseInt(e.target.value) || 0 })}
                          className={`w-full p-3 rounded-lg focus:ring-2 focus:ring-pink-500 outline-none transition-all font-mono font-bold ${theme.input}`}
                        />
                        <p className="text-[11px] opacity-60 mt-2">
                          목표 예산을 설정하면, 시뮬레이션 결과에서 예산 초과 여부를 분석하고 비용 절감을 위한 대안(창호 등급 하향 등)을 추천해 드립니다.
                        </p>
                      </div>

                      {/* 기존 건물 실측 운영비(선택) — 비우면 1.6배 추정으로 계산됨을 결과에 고지 */}
                      <div>
                        <label className={`flex items-center gap-2 text-sm font-black mb-2 ${theme.textMain}`}>
                          <DollarSign className="text-emerald-500" size={16} /> 기존 건물 실제 사용량 (선택)
                        </label>
                        <p className="text-[10px] opacity-60 mb-3">
                          리모델링 전 건물의 작년 값을 입력하면 절감액·NPV·IRR을 실측 기준으로 계산합니다.
                          비워두면 <b>리모델링 후 운영비의 1.6배</b>로 추정합니다.
                        </p>
                        <div className="flex gap-2 mb-3">
                          {[{ k: 'bill', t: '연간 요금(원)' }, { k: 'usage', t: '연간 사용량(kWh)' }].map((m) => (
                            <button
                              key={m.k}
                              type="button"
                              onClick={() => setProjectData((p) => ({ ...p, baselineActual: { ...p.baselineActual, mode: m.k } }))}
                              className={`flex-1 py-2 text-xs font-black rounded-lg border-2 transition-all ${projectData.baselineActual.mode === m.k ? 'border-emerald-500 bg-emerald-500/10 text-emerald-500' : 'border-slate-500/30 opacity-60'}`}
                            >
                              {m.t}
                            </button>
                          ))}
                        </div>
                        <div className="grid grid-cols-2 gap-2">
                          {(projectData.baselineActual.mode === 'bill'
                            ? [{ f: 'elecBill', t: '전기요금 (원/년)' }, { f: 'heatBill', t: '난방요금 (원/년)' }]
                            : [{ f: 'elecKwh', t: '전기 (kWh/년)' }, { f: 'heatKwh', t: '난방 (kWh/년)' }]
                          ).map((x) => (
                            <div key={x.f}>
                              <span className="text-[10px] opacity-70 block mb-1">{x.t}</span>
                              <input
                                type="number"
                                min="0"
                                placeholder="미입력 시 추정"
                                value={projectData.baselineActual[x.f]}
                                onChange={(e) => setProjectData((p) => ({ ...p, baselineActual: { ...p.baselineActual, [x.f]: e.target.value } }))}
                                className={`w-full p-2.5 text-sm font-bold rounded-lg border outline-none ${theme.input} focus:border-emerald-500`}
                              />
                            </div>
                          ))}
                        </div>
                      </div>
                </div>
              </div>
            </WizardShell>
          )}

          {/* STEP: 재무 분석 설정 (LCC) */}
          {step === 'financial' && (
            <WizardShell
              theme={theme} isDarkMode={isDarkMode} setStep={setStep}
              icon={<Calculator size={32} />}
              title="재무 분석 설정 (LCC)"
              subtitle="할인율·물가상승률·수명주기 기간을 설정합니다. (기본값 권장)"
              back="budget" next="buildingView" nextLabel="3D 모델 렌더링"
            >
              <div className={`p-8 rounded-[2rem] border ${theme.card}`}>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <div>
                            <label className={`block text-xs font-bold mb-1 opacity-70 ${theme.textMain}`}>인플레이션율 (%)</label>
                            <input
                              type="number" step="0.1"
                              value={projectData.lccParameters.inflationRate}
                              onChange={(e) => setProjectData({ ...projectData, lccParameters: { ...projectData.lccParameters, inflationRate: parseFloat(e.target.value) || 0 } })}
                              className={`w-full p-2 rounded-lg outline-none font-mono font-bold ${theme.input}`}
                            />
                          </div>
                          <div>
                            <label className={`block text-xs font-bold mb-1 opacity-70 ${theme.textMain}`}>에너지 요금 상승률 (%)</label>
                            <input
                              type="number" step="0.1"
                              value={projectData.lccParameters.utilityInflation}
                              onChange={(e) => setProjectData({ ...projectData, lccParameters: { ...projectData.lccParameters, utilityInflation: parseFloat(e.target.value) || 0 } })}
                              className={`w-full p-2 rounded-lg outline-none font-mono font-bold ${theme.input}`}
                            />
                          </div>
                          <div>
                            <label className={`block text-xs font-bold mb-1 opacity-70 ${theme.textMain}`}>할인율 (기대수익률, %)</label>
                            <input
                              type="number" step="0.1"
                              value={projectData.lccParameters.discountRate}
                              onChange={(e) => setProjectData({ ...projectData, lccParameters: { ...projectData.lccParameters, discountRate: parseFloat(e.target.value) || 0 } })}
                              className={`w-full p-2 rounded-lg outline-none font-mono font-bold ${theme.input}`}
                            />
                          </div>
                          <div>
                            <label className={`block text-xs font-bold mb-1 opacity-70 ${theme.textMain}`}>수명주기 분석 기간 (년)</label>
                            <input
                              type="number" step="1" min="5" max="50"
                              value={projectData.lccParameters.lifecycleYears}
                              onChange={(e) => setProjectData({ ...projectData, lccParameters: { ...projectData.lccParameters, lifecycleYears: parseInt(e.target.value) || 20 } })}
                              className={`w-full p-2 rounded-lg outline-none font-mono font-bold ${theme.input}`}
                            />
                          </div>
                          <p className="col-span-1 md:col-span-2 text-[10px] opacity-60 mt-1">
                            수명주기비용(LCC) 분석 모형에 따라 각 항목별 물가상승률을 복리로 적용하여 순현재가치(NPV) 및 내부수익률(IRR)을 계산합니다.
                          </p>
                        </div>
              </div>
            </WizardShell>
          )}

          {/* STEP 1.5: Parsing gbXML */}
          {step === 'parsing' && (
            <div className="flex-1 flex flex-col items-center justify-center animate-in fade-in h-full bg-black/10 backdrop-blur-sm z-50">
              {!uploadError ? (
                <>
                  <div className="relative mb-12">
                    <Loader2 size={120} className="text-blue-500 animate-spin" />
                    <div className="absolute inset-0 flex items-center justify-center">
                      <FileText size={40} className="text-blue-500/50 animate-pulse" />
                    </div>
                  </div>
                  <h2 className="text-4xl font-black mb-4 tracking-tighter uppercase text-center text-blue-400">
                    gbXML 파일 형상 데이터 파싱 중...
                  </h2>
                  <p className="text-blue-500 font-mono font-bold tracking-[0.2em] uppercase">
                    Extracting Thermal Zones & Surfaces from "{uploadedFile?.name}"
                  </p>
                  <div className="w-[600px] h-3 bg-slate-800 rounded-full mt-12 overflow-hidden border border-white/5">
                    <div className="h-full bg-blue-500 animate-pulse shadow-[0_0_20px_rgba(59,130,246,0.5)]" style={{ width: `100%` }}></div>
                  </div>
                </>
              ) : (
                <>
                  <div className="relative mb-8">
                    <X size={80} className="text-red-500 drop-shadow-lg" />
                  </div>
                  <h2 className="text-3xl font-black mb-4 tracking-tighter uppercase text-center text-red-500">파이썬 백엔드 연결 실패</h2>
                  <p className="text-red-400/80 font-bold mb-8 text-center max-w-lg leading-relaxed">{uploadError}</p>
                  <div className="flex gap-4">
                    <button
                      onClick={() => setStep('upload')}
                      className="px-6 py-3 rounded-2xl font-bold border-2 border-slate-500 hover:bg-slate-800 transition-colors"
                    >
                      다시 업로드 시도
                    </button>
                    <button
                      onClick={handleStartWithSample}
                      className="px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-2xl font-bold shadow-lg shadow-blue-500/30 transition-colors"
                    >
                      안전장치(샘플 모델)로 계속하기
                    </button>
                  </div>
                </>
              )}
            </div>
          )}

          {/* STEP 2: Building View */}
          {step === 'buildingView' && (
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
          )}

          {/* STEP 3 & 4: Floor View + Side Editor Panel */}
          {step === 'floorView' && (
            <FloorEditor
              theme={theme}
              isDarkMode={isDarkMode}
              projectData={projectData}
              res={res}
              surfaces={surfaces}
              zones={zones}
              materials={materials}
              constructionOverrides={constructionOverrides}
              editState={editState}
              setEditState={setEditState}
              editMode={editMode}
              selectedId={selectedId}
              setSelectedId={setSelectedId}
              hoveredId={hoveredId}
              setHoveredId={setHoveredId}
              activeFloor={activeFloor}
              setActiveFloor={setActiveFloor}
              viewMode={viewMode}
              setViewMode={setViewMode}
              sunMonth={sunMonth}
              setSunMonth={setSunMonth}
              sunHour={sunHour}
              setSunHour={setSunHour}
              latitude={latitude}
              selectedRegion={selectedRegion}
              lightCalc={lightCalc}
              setLightCalc={setLightCalc}
              equipCalc={equipCalc}
              setEquipCalc={setEquipCalc}
              setStep={setStep}
              displayFloors={displayFloors}
              selectedSurfaceData={selectedSurfaceData}
              currentPanes={currentPanes}
              currentType={currentType}
              currentGlazing={currentGlazing}
              availableTypes={availableTypes}
              filteredGlazingList={filteredGlazingList}
              inactiveBtnClass={inactiveBtnClass}
              handleConstructionOverrideChange={handleConstructionOverrideChange}
              handleResetInsulationOverride={handleResetInsulationOverride}
              handleZoneClick={handleZoneClick}
              handleSurfaceClick={handleSurfaceClick}
              handleSaveClose={handleSaveClose}
              handleModeSwitch={handleModeSwitch}
              handleTypeChange={handleTypeChange}
              handlePanesChange={handlePanesChange}
              handleSimulation={handleSimulation}
              getZoneFloorArea={getZoneFloorArea}
              calcOutletPower={calcOutletPower}
              isVirtualFloor={isVirtualFloor}
              getActivityCategory={getActivityCategory}
              calculateUpdatedUValue={calculateUpdatedUValue}
            />
          )}

          {/* STEP 5: Loading */}
          {step === 'loading' && (
            <div className="flex-1 flex flex-col items-center justify-center animate-in fade-in h-full">
              <h2 className={`text-4xl font-black mb-12 tracking-tighter uppercase text-center ${theme.textMain}`}>
                {LOADING_MESSAGES[loadingMsgIdx]}
              </h2>
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
          )}

          {/* STEP 6: Result */}
          {step === 'result' && (
            <ResultDashboard
              theme={theme}
              res={res}
              isDarkMode={isDarkMode}
              lccAnalysis={lccAnalysis}
              activeResultTab={activeResultTab}
              setActiveResultTab={setActiveResultTab}
              setSelectedMetric={setSelectedMetric}
              zones={zones}
              surfaces={surfaces}
              setStep={setStep}
              handleApplyRecommendations={handleApplyRecommendations}
              getZebGradeInfo={getZebGradeInfo}
              getAnnualChartData={getAnnualChartData}
              viewMode={viewMode}
              setViewMode={setViewMode}
              sunMonth={sunMonth}
              setSunMonth={setSunMonth}
              sunHour={sunHour}
              setSunHour={setSunHour}
              latitude={latitude}
              selectedRegion={selectedRegion}
            />
          )}

          {/* 팝업 모달 공간 (전역으로 위치 조정됨) */}
          <AnimatePresence>
            {selectedMetric && (
              <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="absolute inset-0 bg-black/60 backdrop-blur-sm"
                  onClick={() => setSelectedMetric(null)}
                />
                <motion.div
                  layoutId={selectedMetric.layoutId}
                  className={`relative w-full max-w-2xl p-10 rounded-[3rem] shadow-[0_30px_60px_-15px_rgba(0,0,0,0.5)] ${isDarkMode ? 'bg-[#0f172a] border border-slate-700/50' : 'bg-white border border-[#D5D2C9]'} z-10 overflow-hidden flex flex-col`}
                >
                  <button
                    onClick={() => setSelectedMetric(null)}
                    className="absolute top-6 right-6 p-2 rounded-full hover:bg-slate-500/20 transition-colors"
                  >
                    ✖
                  </button>
                  
                  <motion.p layoutId={`${selectedMetric.layoutId}-label`} className={`text-sm font-black uppercase tracking-widest mb-4 opacity-60 ${theme.textSub}`}>
                    {selectedMetric.label}
                  </motion.p>
                  <motion.div layoutId={`${selectedMetric.layoutId}-val`} className="flex items-baseline gap-2 mb-8 border-b border-slate-500/20 pb-8">
                    <span className={`text-6xl font-black tracking-tighter ${selectedMetric.colorClass || 'text-emerald-400'}`}>
                      {selectedMetric.isRawString ? selectedMetric.val : Number(selectedMetric.val).toFixed(1)}
                    </span>
                    <span className="text-lg font-bold opacity-50">{selectedMetric.unit}</span>
                  </motion.div>
                  
                  <motion.p
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ delay: 0.1 }}
                    className={`text-base font-medium leading-relaxed ${theme.textMain} whitespace-pre-wrap`}
                  >
                    {selectedMetric.desc}
                  </motion.p>
                </motion.div>
              </div>
            )}
          </AnimatePresence>

          {/* 스케줄 수정 모달 */}
          <AnimatePresence>
            {showScheduleModal && (
              <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
                <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setShowScheduleModal(false)}></div>
                <motion.div
                  initial={{ opacity: 0, scale: 0.95, y: 20 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95, y: 20 }}
                  className={`relative w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-[2rem] shadow-2xl ${isDarkMode ? 'bg-slate-900' : 'bg-white'} border border-slate-700/50 p-6`}
                >
                  <button
                    onClick={() => setShowScheduleModal(false)}
                    className="absolute top-6 right-6 p-2 rounded-full bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 transition-colors z-50"
                  >
                    <X size={20} className="text-slate-500" />
                  </button>
                  <ScheduleEditor 
                    value={projectData.customSchedule}
                    onChange={(newSchedule) => setProjectData({...projectData, customSchedule: newSchedule})}
                  />
                </motion.div>
              </div>
            )}
          </AnimatePresence>
        </main>
      </div>
      )}
    </>
  );
}
