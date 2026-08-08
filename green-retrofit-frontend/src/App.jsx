import React, { useState, useRef, useReducer } from 'react';
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
  PlayCircle,
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
import { buildSimulationPayload } from './utils/simulationPayload';
import { runSimulationFlow } from './utils/simulationFlow';
import { ACTIVITIES, GLAZING_TYPES, KOREA_REGIONS } from './data/constants';
import { createInitialProjectData } from './data/initialProject';
import {
  AppAction, appReducer, initialAppState, toEdit, toExec, toModel,
} from './state/appReducer';
import { ModelAction } from './state/modelReducer';
import { ExecAction } from './state/execution';
import { EditAction } from './state/editSession';
// ⚠️ 콘센트 산식은 백엔드와 같은 값이어야 한다 — utils/zoneLoads.js 주석 참조.
import { calcOutletPower, getActivityCategory } from './utils/zoneLoads';
import { INSULATION_TYPES, INSULATION_CATEGORIES } from './data/insulation';
import { STRUCTURAL_MATERIALS } from './data/structuralMaterials';
import { HVAC_SYSTEMS, FUEL_TYPES, VENT_TYPES, COOLING_GRADES, HEATING_AGES } from './data/hvac';
import { LOADING_MESSAGES, DIR_MAP } from './utils/format';
import { getPanesCategory, getCoatingType } from './utils/surface';
import { getZebGradeInfo, buildAnnualChartData, buildCashFlowData } from './utils/resultData';
import { applyRecommendation } from './utils/recommendationActions';
import ZeroBaseLanding from './components/landing/ZeroBaseLanding';
import { REGION_LATITUDES } from './utils/solarHelper';
import * as THREE from 'three';

// --- 분리된 3D 뷰어 컴포넌트 ---
import BuildingViewer from './components/viewer/BuildingViewer';

// --- 분리된 결과 대시보드 (STEP 6) ---
import ResultDashboard from './components/steps/ResultDashboard';

// --- 분리된 평면도/속성 편집기 (STEP 3 & 4) ---
import FloorEditor from './components/steps/FloorEditor';
import WizardShell from './components/layout/WizardShell';
import LoadingPage from './pages/LoadingPage';
import UploadPage from './pages/UploadPage';
import BuildingViewPage from './pages/BuildingViewPage';
import FinancialPage from './pages/FinancialPage';
import BudgetPage from './pages/BudgetPage';
import RenewablePage from './pages/RenewablePage';
import ProjectInfoPage from './pages/ProjectInfoPage';



// --- [메인 애플리케이션] ---
export default function App() {
  const [isDarkMode, setIsDarkMode] = useState(false);
  

  // ── 업로드한 건물 모델 ──
  // ⚠️ 이 아홉 개는 **함께 바뀌어야 한다.** 흩어진 setter 로 두었더니 재업로드
  // 버튼 두 곳이 `originalModel`(절감액의 기준선)·`gapWarnings`·`realFloorCount`
  // 를 안 지우고 있었다. 상태 전이는 state/modelReducer.js 가 표로 고정한다.
  const [app, dispatch] = useReducer(appReducer, initialAppState);
  // 봉투를 매번 손으로 씌우면 읽기 어렵다 — 묶음별 dispatch 로 감싼다.
  const dispatchModel = (action) => dispatch(toModel(action));
  const dispatchEdit = (action) => dispatch(toEdit(action));
  const dispatchExec = (action) => dispatch(toExec(action));
  const { model, edit, exec } = app;
  const { step, loadingStage, loadingMsgIdx, res } = exec;

  const setStep = (v) => dispatchExec(({ type: ExecAction.NAVIGATED, step: v }));
  const {
    surfaces, zones, originalModel, uploadedFile, uploadError,
    gapWarnings, realFloorCount, materials, constructionOverrides,
  } = model;

  // 편집 경로용 호환 setter — `useState` 처럼 값/갱신함수를 받는다.
  const setSurfaces = (v) => dispatchModel(({ type: ModelAction.SURFACES_CHANGED, surfaces: v }));
  const setZones = (v) => dispatchModel(({ type: ModelAction.ZONES_CHANGED, zones: v }));
  const setConstructionOverrides = (v) =>
    dispatchModel(({ type: ModelAction.OVERRIDES_CHANGED, overrides: v }));
  // ⚠️ **모델을 갈아끼울 때는 편집 세션도 반드시 함께 초기화한다.** 모델만
  // 바꾸면 `selectedId`·`activeFloor`·초안이 **이전 건물을 가리킨다**(codex 지적).
  // 그래서 두 dispatch 를 한 함수로 묶어 빠뜨릴 수 없게 한다.
  // ⚠️ **한 전이**로 모델 교체 + 편집 세션 초기화를 한다. 예전에는 dispatch 두
  // 개를 나란히 불렀고, 그 연동은 정규식 소스 검사로만 지켜졌다(codex 지적).
  const loadModel = (modelAction) =>
    dispatch({ type: AppAction.MODEL_REPLACED, modelAction });
  const resetModel = () => loadModel({ type: ModelAction.MODEL_RESET });

  // ── 평면도 편집 세션 ──
  // ⚠️ `editState` 는 아직 커밋되지 않은 **초안**이다. 모델 반영은 model reducer 의
  // `*_EDIT_COMMITTED` 가 한다. 새 모델을 실을 때는 **반드시 SESSION_RESET** 을
  // 함께 보낸다 — 안 그러면 선택·층·초안이 이전 건물을 가리킨다.
  const {
    activeFloor, editMode, selectedId, hoveredId, editState,
    applyToSimilarZones, lightCalc, equipCalc,
  } = edit;

  const setActiveFloor = (f) => dispatchEdit(({ type: EditAction.FLOOR_CHANGED, floor: f }));
  // ⚠️ **선택 해제 전용**이다. 실제 선택은 `handleSurfaceClick(data)` /
  // `handleZoneClick(id)` 가 한다 — 그쪽은 대상 객체를 알고 초안을 제대로 만든다.
  // id 만으로 선택하면 초안이 `{wwr: undefined, ...}` 가 되어 저장하는 순간
  // 면의 실제 값을 지운다(codex 지적).
  const setSelectedId = (id) => {
    if (id != null) {
      // ⚠️ 사용자 앞에서 앱을 죽이지 않는다 — 개발 중에만 알리고 무시한다.
      if (import.meta.env?.DEV) {
        console.error(
          'setSelectedId 는 해제 전용입니다. 선택은 handleSurfaceClick/handleZoneClick 을 쓰세요.');
      }
      return;
    }
    dispatchEdit(({ type: EditAction.SELECTION_CLEARED }));
  };
  const setHoveredId = (id) => dispatchEdit(({ type: EditAction.HOVER_CHANGED, hoveredId: id }));
  const setEditState = (v) => dispatchEdit(({ type: EditAction.DRAFT_CHANGED, editState: v }));
  const setApplyToSimilarZones = (v) =>
    dispatchEdit(({ type: EditAction.APPLY_SIMILAR_CHANGED, value: v }));
  const setLightCalc = (v) => dispatchEdit(({ type: EditAction.LIGHT_CALC_CHANGED, lightCalc: v }));
  const setEquipCalc = (v) => dispatchEdit(({ type: EditAction.EQUIP_CALC_CHANGED, equipCalc: v }));

  const [projectData, setProjectData] = useState(createInitialProjectData);

  // 업로드 원본(개선 전) 스냅샷 — 백엔드가 전/후 비교 시뮬레이션의 기준선으로 사용
  // 화장실·계단실 등 동일 용도 존 일괄 적용 체크 — handleZoneClick에서 존 전환 시 리셋
  
  // 💡 [수정] 결과를 볼 때 '에너지 성능(energy)' 탭이 무조건 먼저 나오도록 기본값 설정

  const [viewMode, setViewMode] = useState('default'); // 'default' | 'sunpath' | 'thermal' | 'airflow'
  const [sunMonth, setSunMonth] = useState(6);
  const [sunHour, setSunHour] = useState(12);

  const fileInputRef = useRef(null);
  const scheduleEditorRef = useRef(null);

  
  // 💡 단열재 및 구조체 속성 튜닝을 위한 State

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
    // ⚠️ 예전에는 `setConstructionOverrides(prev => ...)` 의 **갱신함수 안에서**
    // `setSurfaces`·`setEditState` 를 불렀다. reducer 로 옮기면 그 함수가 reducer
    // 안에서 실행돼 **순수하지 않은 reducer** 가 된다(codex 지적).
    // 다음 override 를 먼저 계산한 뒤, 의미 있는 action 하나로 커밋한다.
    const current = constructionOverrides[surfaceId] || {};
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
    const newU = constr ? calculateUpdatedUValue(constr, next) : null;
    if (newU != null) {
      next.uValue = newU;   // 백엔드로 전달하기 위해 override 객체에 저장
    }

    dispatchModel(({
      type: ModelAction.CONSTRUCTION_OVERRIDE_APPLIED,
      surfaceId, override: next, uValue: newU,
    }));

    // 편집 중인 면의 슬라이더도 따라가야 한다(저장 시 덮어쓰기 방지).
    // ⚠️ 편집 상태는 **다른 상태 묶음**이라 여기서 따로 갱신한다.
    if (newU != null && selectedId === surfaceId) {
      setEditState(prevEdit => ({ ...prevEdit, uValue: newU }));
    }
  };

  const handleResetInsulationOverride = (surfaceId, constructionId) => {
    // 원본 U-value 복원까지 같은 전이에서 한다.
    const constr = materials?.constructions?.find(c => c.id === constructionId);
    dispatchModel(({
      type: ModelAction.CONSTRUCTION_OVERRIDE_RESET,
      surfaceId, uValue: constr ? constr.uValue : null,
    }));
    if (constr && selectedId === surfaceId) {
      setEditState(prevEdit => ({ ...prevEdit, uValue: constr.uValue }));
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

  // 지면 승격 대상 — 백엔드(ep_simulator)의 승격 조건과 **동일한 식**을 써야 한다.
  //   selfAdjacent && 타입에 'floor' && 모든 꼭짓점 Z ≈ 0
  // 조건이 어긋나면 "토글은 보이는데 켜도 0개가 바뀌는" 상황이 된다.
  const groundEligible = React.useMemo(() => {
    const targets = (surfaces || []).filter(
      (s) => s.selfAdjacent
        && (s.type || '').toLowerCase().includes('floor')
        && Array.isArray(s.vertices) && s.vertices.length >= 3
        && s.vertices.every((p) => Math.abs(p[2]) < 1e-6)
    );
    return {
      count: targets.length,
      area: targets.reduce((acc, s) => acc + calculateSurfaceArea(s.vertices), 0),
    };
  }, [surfaces]);

  const getZoneFloorArea = (zoneId) => {
    // 백엔드와 같은 기준을 써야 한다. 백엔드는 gbXML 선언 면적(declaredArea)을 우선하는데
    // 여기서 기하 합산을 쓰면 화면과 시뮬레이션이 갈린다 — 층간 슬래브가 아래층 존에
    // 바닥·천장으로 이중 계산돼 104 존이 프론트 223.22㎡ / 백엔드 107.22㎡ 로 2배 차이났다.
    // 유효성 기준을 백엔드(gbxml_parser: 유한한 양수)와 반드시 같게 둔다.
    // 임계값이 어긋나면 그 사이 면적의 존에서 화면과 시뮬레이션이 또 갈린다.
    const zone = zones.find((z) => z.id === zoneId);
    const declared = Number(zone?.declaredArea ?? zone?.area ?? 0);
    if (Number.isFinite(declared) && declared > 0) return declared;

    const zoneSurfaces = surfaces.filter(
      (s) => s.zone === zoneId && s.type && (s.type.toLowerCase().includes('floor') || s.type.toLowerCase().includes('slab'))
    );
    const areaSum = zoneSurfaces.reduce((acc, s) => acc + calculateSurfaceArea(s.vertices), 0);
    return areaSum >= 1.0 ? areaSum : 100.0;
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
          // ⚠️ 기본은 'max'. `equipmentPower` 와 콘센트 추정값은 같은 물리량의
          // 다른 추정치라(ASHRAE 기기부하 정의 = 콘센트 부하) 더하면 이중계산이다.
          outletLoadType: 'max',
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
    // 샘플도 모델·기준선을 한 번에 싣는다(재료는 아래에서 덧붙인다).
    // 샘플용 가상 단열재 데이터 (DB 연동/단열재 표시 기능 활성화용)
    const sampleMaterials = {
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
    };

    loadModel({
      type: ModelAction.SAMPLE_LOADED, surfaces: newSurfaces, zones: newZones,
      materials: sampleMaterials,
      // ⚠️ 층수를 안 넘기면 이전 건물의 층수로 가상층을 판정한다
      floorLevels: floors,
    });


    // 샘플도 업로드와 동일하게 설정 위저드 첫 페이지로 진입
    setStep('projectInfo');
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    dispatchModel(({ type: ModelAction.PARSE_STARTED, file }));
    dispatchExec(({ type: ExecAction.PARSE_STARTED }));
    try {
      const response = await uploadGbxml(file);
      if (response && response.data) {
        // ⚠️ 모델·기준선·경고·층수를 **한 번에** 싣는다. 예전엔 setter 를 따로
        // 불러서, 한 곳만 빠뜨려도 이전 모델의 잔여물이 섞였다.
        loadModel({
          type: ModelAction.PARSE_SUCCEEDED,
          surfaces: response.data.surfaces,
          zones: response.data.zones,
          materials: response.data.materials,
          warnings: response.data.warnings,
          floorLevels: response.data.floorLevels,
        });
      }
      dispatchExec(({ type: ExecAction.PARSE_SETTLED, ok: true }));
    } catch (error) {
      console.error('파싱 에러:', error);
      // 백엔드가 원인을 알려주면(400 detail 등) 그대로 보여준다 — "서버 응답 없음"으로 뭉개지 않기
      const detail = error?.response?.data?.detail;
      dispatchModel(({
        type: ModelAction.PARSE_FAILED,
        message: detail || '백엔드 서버(Python) 응답이 없거나 gbXML 파일 해석에 실패했습니다.',
      }));
      // ⚠️ 실패하면 `parsing` 에 **머문다.** 오류 화면이 그 단계 블록 **안에**
      // 있어서, upload 로 넘기면 사용자가 아무 안내도 못 받고 튕긴다.
      // 그 규칙은 `ExecAction.PARSE_SETTLED{ok:false}` 가 지킨다.
      dispatchExec(({ type: ExecAction.PARSE_SETTLED, ok: false }));
    }
  };

  const handleStartWithSample = () => {
    populateBuildingData();
  };

  const handleModeSwitch = (mode) => {
    if (editMode !== mode) {
      // ⚠️ 저장이 **먼저**다. 세션을 먼저 지우면 편집하던 초안이 사라진다.
      handleSaveClose();
      dispatchEdit(({ type: EditAction.MODE_SWITCHED, mode }));
    }
  };

  const handleSurfaceClick = (data) => {
    if (editMode !== 'surface') return;
    if (selectedId && selectedId !== data?.id) handleSaveClose();

    dispatchEdit(({ type: EditAction.SURFACE_SELECTED, surface: data }));
  };

  const handleZoneClick = (zoneId) => {
    if (editMode !== 'zone') return;
    if (selectedId && selectedId !== zoneId) handleSaveClose();

    // 존 전환 시 일괄적용 체크는 reducer 가 리셋한다(다음 존에 실수로 이어붙지 않게)
    dispatchEdit(({
      type: EditAction.ZONE_SELECTED,
      zone: zones.find((z) => z.id === zoneId) || null,
      zoneId,
    }));
  };

  // 화장실·계단실처럼 같은 용도(activityId)의 존이 여러 개일 때, 하나씩 편집하는
  // 수고를 덜기 위한 필드 화이트리스트 — 위치·면적 등 존 고유값은 절대 복제하지 않는다.
  const SIMILAR_ZONE_FIELDS = [
    'activityId', 'peopleDensity', 'lightingPower', 'equipmentPower',
    'outletCount', 'outletLoadType', 'ledFixtureCount', 'isConditioned',
    'hvacSystemId', 'coolingInstalled', 'coolingCapacityPyeong',
    'heatingFuelId', 'ventilationId', 'heatingSetpoint', 'coolingSetpoint',
  ];

  const handleSaveClose = () => {
    if (!selectedId) return;
    // ⚠️ **커밋과 닫기를 나눈다.** 초안을 모델에 반영하는 것(model reducer)과
    // 편집 세션을 닫는 것(edit reducer)은 다른 관심사다 — 한 곳에 두면
    // "저장했는데 화면만 바뀐" 상태가 생긴다.
    if (editMode === 'surface') {
      dispatchModel(({
        type: ModelAction.SURFACE_EDIT_COMMITTED,
        surfaceId: selectedId, patch: editState,
      }));
    } else if (editMode === 'zone') {
      dispatchModel(({
        type: ModelAction.ZONE_EDIT_COMMITTED,
        zoneId: selectedId, patch: editState,
        // ⚠️ 화이트리스트를 넘길 때만 일괄 적용된다. 존 전체를 복사하면
        // 위치·면적·id 까지 덮어써 다른 존이 통째로 망가진다.
        similarFields: applyToSimilarZones ? SIMILAR_ZONE_FIELDS : null,
      }));
    }
    dispatchEdit(({ type: EditAction.EDIT_CLOSED }));
  };

  // 제안 1건의 상태 변경만 수행하고, 무엇을 바꿨는지 요약 문자열을 반환한다.
  // (도메인 로직은 utils/recommendationActions.js — 여기선 상태/세터만 연결)
  const applyRecommendationChanges = (type) =>
    applyRecommendation(type, {
      surfaces, zones, projectData, constructionOverrides, materials,
      setSurfaces, setZones, setProjectData, setConstructionOverrides,
      calculateUpdatedUValue,
    });

  // 선택한 여러 제안을 한 번에 적용 → 안내 1회 + 화면 이동 1회
  const handleApplyRecommendations = (types) => {
    if (!types || types.length === 0) return;
    const summaries = types.map(applyRecommendationChanges).filter(Boolean);
    // 실제로 바뀐 항목이 하나도 없으면(이미 최소 사양 등) 안내만 하고 머무른다 — 재시뮬해도 동일하므로
    if (summaries.length === 0) {
      alert(
        '선택한 제안은 현재 모델에 적용할 변경 사항이 없습니다.\n' +
        '(이미 최저 사양이거나 해당 요소가 모델에 없어 비용이 더 줄지 않습니다.)'
      );
      return;
    }
    alert(
      `✅ ${summaries.length}개 제안을 적용했습니다.\n\n` +
      summaries.map((s) => `· ${s}`).join('\n') +
      `\n\n하단의 [시뮬레이션 가동] 버튼을 눌러 낮아진 예산을 확인해 주세요.`
    );
    setStep('floorView');
  };

  const handleSimulation = async () => {
    // 화면 전환 계약은 utils/simulationFlow.js — 긴 UI 경로 없이 시험한다.
    let interval = null;
    await runSimulationFlow(
      buildSimulationPayload({
        projectData, zones, surfaces, materials, constructionOverrides, originalModel,
      }),
      runSimulation,
      {
        onStarted: () => dispatchExec(({ type: ExecAction.SIMULATION_STARTED })),
        onStage: (stage) => dispatchExec(({ type: ExecAction.LOADING_STAGE_CHANGED, stage })),
        onSucceeded: (result) =>
          dispatchExec(({ type: ExecAction.SIMULATION_SUCCEEDED, result })),
        onFailed: () => dispatchExec(({ type: ExecAction.SIMULATION_FAILED })),
        startTicker: () => {
          interval = setInterval(() => dispatchExec(({
            type: ExecAction.LOADING_MESSAGE_TICKED, lastIndex: LOADING_MESSAGES.length - 1,
          })), 1500);
        },
        stopTicker: () => clearInterval(interval),
      },
    );
  };

  // 랜딩의 따뜻한 톤(브라운 #1a120d / 크림 #f3ece1 / 테라코타)을 앱 전역으로 이어감
  const theme = {
    bg: isDarkMode ? 'bg-[#1a120d] text-[#f3ece1]' : 'bg-[#f3ece1] text-[#2a211b]',
    card: isDarkMode ? 'bg-[#241a13] border-[#3a2c20]' : 'bg-[#eae1d3] border-[#d8cbb5]',
    panel: isDarkMode ? 'bg-[#1f160e]/85 border-[#3a2c20]' : 'bg-[#fbf7f0]/85 border-[#d8cbb5]',
    textMain: isDarkMode ? 'text-[#f7f1e8]' : 'text-[#2a211b]',
    textSub: isDarkMode ? 'text-[#b8a48f]' : 'text-[#6b5d50]',
    input: isDarkMode ? 'bg-[#241a13] border-[#3a2c20] text-[#f3ece1]' : 'bg-[#fbf7f0] border-[#d8cbb5] text-[#2a211b]',
    tableHeader: isDarkMode ? 'bg-white/5 text-[#e4b48f] border-[#3a2c20]' : 'bg-[#eae1d3] text-[#2a211b] border-[#d8cbb5]',
    tableBorder: isDarkMode ? 'border-[#3a2c20]' : 'border-[#d8cbb5]',
    chartText: isDarkMode ? '#b8a48f' : '#6b5d50',
    chartGrid: isDarkMode ? 'rgba(255,255,255,0.05)' : '#d8cbb5',
    pieBg: isDarkMode ? 'rgba(255,255,255,0.05)' : '#eae1d3',
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

  // 💡 LCC(현금흐름) 차트 데이터 (utils/resultData.js)
  const lccAnalysis = buildCashFlowData(res);
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
              gbXML 모델에서 시뮬레이션 결과에 영향을 줄 수 있는 항목이 감지되었습니다.
              내용을 확인한 뒤 진행해 주세요.
            </p>

            <div className={`rounded-2xl border p-4 mb-6 max-h-48 overflow-y-auto ${isDarkMode ? 'bg-slate-900/50 border-slate-700' : 'bg-slate-50 border-slate-200'}`}>
              {/* 경고 종류가 둘 이상이다. 갭 경고는 Zone·오차율 쌍으로, 그 외(자기참조 면 등)는
                  message 본문으로 표시한다. issue 분기 없이 zone/deviation만 읽으면 빈 칸이 된다. */}
              {gapWarnings.map((w, i) => (
                <div key={i} className={`py-2 ${i > 0 ? (isDarkMode ? 'border-t border-slate-700' : 'border-t border-slate-200') : ''}`}>
                  {w.issue === 'not_enclosed' ? (
                    <div className="flex justify-between items-center">
                      <span className={`text-sm font-mono font-bold ${isDarkMode ? 'text-slate-200' : 'text-slate-700'}`}>{w.zone}</span>
                      <span className={`text-xs font-bold px-3 py-1 rounded-full ${
                        w.deviation > 20 ? 'bg-red-500/20 text-red-400' : 'bg-amber-500/20 text-amber-500'
                      }`}>
                        오차: {w.deviation}%
                      </span>
                    </div>
                  ) : (
                    <div className="flex items-start gap-2">
                      {/* count 의 의미는 경고마다 다르다(실/면/존/항목). 백엔드가 준
                          countUnit 을 그대로 쓴다 — 예전엔 전부 '개 면'으로 찍혀 틀렸다. */}
                      <span className={`text-xs font-bold px-2 py-1 rounded-full shrink-0 ${
                        w.severity === 'block' ? 'bg-red-500/20 text-red-400'
                          : w.severity === 'choice' ? 'bg-sky-500/20 text-sky-500'
                          : w.severity === 'info' ? 'bg-slate-500/20 text-slate-400'
                          : 'bg-amber-500/20 text-amber-500'
                      }`}>
                        {w.count != null ? `${w.count}${w.countUnit || '개'}` : '확인 필요'}
                      </span>
                      <div className="min-w-0">
                        <div className={`text-xs leading-relaxed ${isDarkMode ? 'text-slate-300' : 'text-slate-600'}`}>{w.message}</div>
                        {w.action && (
                          <div className={`text-[11px] mt-1 ${isDarkMode ? 'text-slate-500' : 'text-slate-400'}`}>
                            → {w.action}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>

            <p className={`text-xs mb-6 ${
              gapWarnings.some((w) => w.severity === 'block')
                ? 'text-red-500 font-bold'
                : (isDarkMode ? 'text-slate-500' : 'text-slate-400')
            }`}>
              {gapWarnings.some((w) => w.severity === 'block')
                ? '해석할 수 없는 입력이 있어 이대로는 시뮬레이션을 진행할 수 없습니다. 위 항목을 수정한 뒤 다시 올려주세요.'
                : '이 상태로 시뮬레이션을 진행할 수 있지만, 해당 Zone의 냉난방 부하 결과 정확도가 떨어질 수 있습니다.'}
            </p>

            <div className="flex gap-3">
              <button
                onClick={() => {
                  // ⚠️ 예전엔 여기서 `originalModel`·`realFloorCount` 를 안 지웠다.
                  // `originalModel` 은 절감액의 기준선이라 남으면 엉뚱한 건물과 비교한다.
                  resetModel();
                  if (fileInputRef.current) fileInputRef.current.value = '';
                }}
                className={`flex-1 py-3 rounded-2xl text-sm font-bold border transition-all ${
                  isDarkMode ? 'border-slate-600 text-slate-300 hover:bg-slate-800' : 'border-slate-300 text-slate-600 hover:bg-slate-100'
                }`}
              >
                수정하고 재업로드
              </button>
              {/* severity=block 은 해석 자체가 불가능한 입력이다 —
                  '그대로 진행'을 허용하면 신뢰할 수 없는 결과를 만들게 된다. */}
              <button
                onClick={() => dispatchModel(({ type: ModelAction.WARNINGS_DISMISSED }))}
                disabled={gapWarnings.some((w) => w.severity === 'block')}
                className={`flex-1 py-3 rounded-2xl text-sm font-bold transition-all ${
                  gapWarnings.some((w) => w.severity === 'block')
                    ? 'bg-slate-400/30 text-slate-500 cursor-not-allowed'
                    : 'bg-amber-500 hover:bg-amber-400 text-black shadow-lg shadow-amber-500/25'
                }`}
              >
                그대로 진행
              </button>
            </div>
          </div>
        </div>
      )}

      {step === 'landing' ? (
        <div className="min-h-screen overflow-y-auto" style={{ background: '#1a120d' }}>
          <ZeroBaseLanding onStart={() => setStep('upload')} />
        </div>
      ) : (
      <div className={`h-screen w-full transition-colors duration-300 ${theme.bg} font-sans flex flex-col overflow-hidden`}>
        <header className={`flex-shrink-0 px-8 py-4 border-b ${isDarkMode ? 'border-[#3a2c20] bg-[#1a120d]' : 'border-[#d8cbb5] bg-[#f3ece1]'} flex justify-between items-center z-10 shadow-sm`}>
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
            <UploadPage
              theme={theme} isDarkMode={isDarkMode}
              setStep={setStep}
              surfaces={surfaces} zones={zones} uploadedFile={uploadedFile}
              fileInputRef={fileInputRef}
              handleFileUpload={handleFileUpload}
              handleStartWithSample={handleStartWithSample}
              onResetModel={resetModel}
            />
          )}

          {/* STEP: 프로젝트 기본 정보 */}
          {step === 'projectInfo' && (
            <ProjectInfoPage
              theme={theme}
              isDarkMode={isDarkMode}
              setStep={setStep}
              projectData={projectData}
              setProjectData={setProjectData}
              scheduleEditorRef={scheduleEditorRef}
            />
          )}

          {/* STEP: 신재생 & 에너지 설비 */}
          {step === 'renewable' && (
            <RenewablePage
              theme={theme}
              isDarkMode={isDarkMode}
              setStep={setStep}
              projectData={projectData}
              setProjectData={setProjectData}
              zones={zones}
              groundEligible={groundEligible}
            />
          )}

          {/* STEP: 목표 예산 & 기존 건물 사용량 */}
          {step === 'budget' && (
            <BudgetPage
              theme={theme}
              isDarkMode={isDarkMode}
              setStep={setStep}
              projectData={projectData}
              setProjectData={setProjectData}
            />
          )}

          {/* STEP: 재무 분석 설정 (LCC) */}
          {step === 'financial' && (
            <FinancialPage
              theme={theme}
              isDarkMode={isDarkMode}
              setStep={setStep}
              projectData={projectData}
              setProjectData={setProjectData}
            />
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
            <BuildingViewPage
              isDarkMode={isDarkMode}
              setStep={setStep}
              surfaces={surfaces}
              zones={zones}
              displayFloors={displayFloors}
              isVirtualFloor={isVirtualFloor}
              setActiveFloor={setActiveFloor}
              setSelectedId={setSelectedId}
              viewMode={viewMode}
              setViewMode={setViewMode}
              sunMonth={sunMonth}
              setSunMonth={setSunMonth}
              sunHour={sunHour}
              setSunHour={setSunHour}
              res={res}
              latitude={latitude}
              selectedRegion={selectedRegion}
            />
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
              applyToSimilarZones={applyToSimilarZones}
              setApplyToSimilarZones={setApplyToSimilarZones}
            />
          )}

          {/* STEP 5: Loading */}
          {step === 'loading' && (
            <LoadingPage
              theme={theme}
              loadingMsgIdx={loadingMsgIdx}
              loadingStage={loadingStage}
            />
          )}

          {/* STEP 6: Result */}
          {step === 'result' && (
            <ResultDashboard
              theme={theme}
              res={res}
              isDarkMode={isDarkMode}
              projectData={projectData}
              lccAnalysis={lccAnalysis}
              zones={zones}
              surfaces={surfaces}
              setStep={setStep}
              handleApplyRecommendations={handleApplyRecommendations}
              getZebGradeInfo={getZebGradeInfo}
              getAnnualChartData={() => buildAnnualChartData(res)}
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


          {/* 스케줄 수정 모달 */}

        </main>
      </div>
      )}
    </>
  );
}
