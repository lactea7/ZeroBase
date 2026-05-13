import React, { useState, useEffect, useRef } from 'react';
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
  Calendar
} from 'lucide-react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

// --- 분리된 모듈 import ---
import { uploadGbxml, runSimulation } from './api/client';
import { ACTIVITIES, GLAZING_TYPES, KOREA_REGIONS } from './data/constants';
import { HVAC_SYSTEMS, FUEL_TYPES, VENT_TYPES } from './data/hvac';
import { LOADING_MESSAGES, DIR_MAP, groupBy, formatWon } from './utils/format';
import { getSurfaceGroupName, getZoneGroupName, getPanesCategory, getCoatingType } from './utils/surface';
import ScheduleEditor from './components/ScheduleEditor';
import Navigation from './components/landing/Navigation';
import Hero from './components/landing/Hero';
import Manual from './components/landing/Manual';
import SimulationEngine from './components/landing/SimulationEngine';

// --- [3D 뷰어 컴포넌트] ---
const BuildingViewer = ({
  surfaces,
  zones,
  activeFloor,
  editMode,
  onSurfaceClick,
  onZoneClick,
  selectedId,
  hoveredId,
  draftState,
  readOnly = false,
  isDarkMode = true,
}) => {
  const mountRef = useRef(null);
  const ctx = useRef({});

  useEffect(() => {
    if (!mountRef.current) return;

    while (mountRef.current.firstChild) {
      mountRef.current.removeChild(mountRef.current.firstChild);
    }

    const width = mountRef.current.clientWidth || 500;
    const height = mountRef.current.clientHeight || 500;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 20000);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });

    renderer.setSize(width, height);
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.domElement.style.width = '100%';
    renderer.domElement.style.height = '100%';
    renderer.domElement.style.display = 'block';

    mountRef.current.appendChild(renderer.domElement);

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.8);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(20, 50, 30);
    scene.add(dirLight);

    const group = new THREE.Group();
    scene.add(group);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.autoRotate = readOnly;
    controls.autoRotateSpeed = 1.0;

    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    ctx.current = { scene, camera, renderer, group, controls, raycaster, mouse, reqId: null, ro: null };

    const animate = () => {
      ctx.current.reqId = requestAnimationFrame(animate);
      if (ctx.current.controls) {
        ctx.current.controls.update();
      }
      if (ctx.current.renderer && ctx.current.scene && ctx.current.camera) {
        ctx.current.renderer.render(ctx.current.scene, ctx.current.camera);
      }
    };
    animate();

    const ro = new ResizeObserver(() => {
      if (!mountRef.current || !ctx.current.camera || !ctx.current.renderer) return;
      const w = mountRef.current.clientWidth;
      const h = mountRef.current.clientHeight;
      if (w === 0 || h === 0) return;
      ctx.current.camera.aspect = w / h;
      ctx.current.camera.updateProjectionMatrix();
      ctx.current.renderer.setSize(w, h);
    });
    ro.observe(mountRef.current);
    ctx.current.ro = ro;

    return () => {
      if (ctx.current.reqId) cancelAnimationFrame(ctx.current.reqId);
      if (ctx.current.ro) ctx.current.ro.disconnect();
      if (ctx.current.controls) ctx.current.controls.dispose();
      if (ctx.current.renderer) {
        ctx.current.renderer.dispose();
        if (mountRef.current && ctx.current.renderer.domElement) {
          try {
            mountRef.current.removeChild(ctx.current.renderer.domElement);
          } catch (e) {}
        }
      }
      ctx.current = {};
    };
  }, []);

  useEffect(() => {
    ctx.current.onSurfaceClick = onSurfaceClick;
    ctx.current.onZoneClick = onZoneClick;
    ctx.current.editMode = editMode;
  }, [onSurfaceClick, onZoneClick, editMode]);

  useEffect(() => {
    if (readOnly || !ctx.current.camera) return;
    const onClick = (e) => {
      if (!mountRef.current || !ctx.current.camera || !ctx.current.group) return;
      const rect = mountRef.current.getBoundingClientRect();
      ctx.current.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      ctx.current.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      ctx.current.raycaster.setFromCamera(ctx.current.mouse, ctx.current.camera);

      const meshes = ctx.current.group.children.filter((c) => c.type === 'Mesh' && c.userData?.id);
      const intersects = ctx.current.raycaster.intersectObjects(meshes);

      if (intersects.length > 0) {
        const clickedData = intersects[0].object.userData;
        if (ctx.current.editMode === 'surface' && ctx.current.onSurfaceClick) {
          ctx.current.onSurfaceClick(clickedData);
        } else if (ctx.current.editMode === 'zone' && ctx.current.onZoneClick) {
          ctx.current.onZoneClick(clickedData.zone);
        }
      }
    };
    const el = mountRef.current;
    if (el) el.addEventListener('click', onClick);
    return () => {
      if (el) el.removeEventListener('click', onClick);
    };
  }, [readOnly]);

  useEffect(() => {
    const { scene, group, camera, controls } = ctx.current;
    if (!scene || !group || !camera || !controls) return;

    scene.background = new THREE.Color(isDarkMode ? '#0f172a' : '#e2e8f0');

    while (group.children.length > 0) {
      const obj = group.children[0];
      if (obj.geometry) obj.geometry.dispose();
      if (obj.material) {
        if (Array.isArray(obj.material)) {
          obj.material.forEach((m) => m.dispose());
        } else {
          obj.material.dispose();
        }
      }
      group.remove(obj);
    }

    const visibleSurfaces =
      activeFloor === 'all' ? surfaces : surfaces.filter((s) => s.floor === parseInt(activeFloor));
    let minX = Infinity,
      maxX = -Infinity,
      minY = Infinity,
      maxY = -Infinity,
      minZ = Infinity,
      maxZ = -Infinity;

    visibleSurfaces.forEach((surf) => {
      const isHovered =
        (editMode === 'surface' && surf.id === hoveredId) || (editMode === 'zone' && surf.zone === hoveredId);
      const isSelected =
        (editMode === 'surface' && surf.id === selectedId) || (editMode === 'zone' && surf.zone === selectedId);

      if (surf.width && surf.height && surf.pos && surf.rot) {
        const geometry = new THREE.PlaneGeometry(surf.width, surf.height);
        let baseColor = 0x3b82f6;

        if (editMode === 'zone' && !readOnly) {
          const liveZoneData =
            selectedId === surf.zone && draftState ? draftState : zones.find((z) => z.id === surf.zone);
          if (liveZoneData) {
            if (!liveZoneData.isConditioned) {
              baseColor = 0x475569;
            } else {
              const act = ACTIVITIES.find((a) => a.id === liveZoneData.activityId);
              baseColor = act ? act.color : 0x3b82f6;
            }
          }
        } else {
          if (surf.type === 'Roof') {
            baseColor = 0xef4444;
          } else if (surf.type === 'InternalSlab' || surf.type === 'SlabOnGrade' || surf.type === 'UndergroundSlab' || surf.type === 'InteriorFloor' || surf.type === 'Ceiling' || surf.type === 'Floor' || surf.type === 'ExteriorFloor') {
            baseColor = 0x8b5cf6;
          } else if (surf.type === 'GroundFloor') {
            baseColor = 0x78716c;
          } else if (surf.type === 'InternalWall' || surf.type === 'InteriorWall') {
            baseColor = 0xf59e0b;
          } else {
            baseColor = 0x3b82f6;
          }
        }

        let finalOpacity = 0.15;
        let finalEmissive = 0x000000;
        let finalEmissiveIntensity = 0;
        let lineColor = baseColor;
        let isXRayMode = false;

        if (isSelected) {
          finalOpacity = 0.95;
          finalEmissive = baseColor;
          finalEmissiveIntensity = 0.6;
          lineColor = 0xffffff;
          isXRayMode = true;
        } else if (isHovered) {
          finalOpacity = 0.85;
          finalEmissive = 0xfacc15;
          finalEmissiveIntensity = 0.6;
          lineColor = 0xfacc15;
          isXRayMode = true;
        } else if (!selectedId && !hoveredId) {
          finalOpacity =
            editMode === 'zone' && !readOnly
              ? 0.6
              : surf.type === 'InternalWall' || surf.type === 'InteriorWall'
              ? 0.25
              : 0.4;
        } else {
          finalOpacity = 0.05;
        }

        const material = new THREE.MeshStandardMaterial({
          color: baseColor,
          transparent: true,
          opacity: finalOpacity,
          emissive: finalEmissive,
          emissiveIntensity: finalEmissiveIntensity,
          side: THREE.DoubleSide,
          depthWrite: true,
        });

        const mesh = new THREE.Mesh(geometry, material);
        mesh.position.set(surf.pos.x, surf.pos.y, surf.pos.z);
        mesh.rotation.set(surf.rot.x, surf.rot.y, surf.rot.z);

        if (surf.pos.x < minX) minX = surf.pos.x;
        if (surf.pos.x > maxX) maxX = surf.pos.x;
        if (surf.pos.y < minY) minY = surf.pos.y;
        if (surf.pos.y > maxY) maxY = surf.pos.y;
        if (surf.pos.z < minZ) minZ = surf.pos.z;
        if (surf.pos.z > maxZ) maxZ = surf.pos.z;

        surf.baseColor = baseColor;
        mesh.userData = surf;

        const edges = new THREE.EdgesGeometry(geometry);
        const lineMat = new THREE.LineBasicMaterial({
          color: lineColor,
          linewidth: isXRayMode ? 2 : 1,
          depthTest: !isXRayMode,
        });
        const line = new THREE.LineSegments(edges, lineMat);

        if (isXRayMode) {
          line.renderOrder = 999;
        }
        mesh.add(line);

        const liveWwr = editMode === 'surface' && selectedId === surf.id && draftState ? draftState.wwr : surf.wwr;
        const safeWwr = isNaN(liveWwr) ? 0 : Math.max(0, Math.min(90, liveWwr));

        if ((surf.type === 'Wall' || surf.type === 'ExteriorWall') && safeWwr > 0) {
          const winRatio = Math.sqrt(safeWwr / 100);
          const winGeom = new THREE.PlaneGeometry(surf.width * winRatio, surf.height * winRatio);
          const winMat = new THREE.MeshStandardMaterial({
            color: 0x06b6d4,
            transparent: true,
            opacity: editMode === 'zone' && !readOnly ? 0.4 : 0.8,
            side: THREE.DoubleSide,
            polygonOffset: true,
            polygonOffsetFactor: -1,
            polygonOffsetUnits: -1,
          });
          const winMesh = new THREE.Mesh(winGeom, winMat);
          winMesh.position.z = 0.01;
          mesh.add(winMesh);
        }
        group.add(mesh);
      } else if (surf.vertices && surf.vertices.length >= 3) {
        const geometry = new THREE.BufferGeometry();
        const verticesArray = [];
        const v0 = surf.vertices[0];

        for (let i = 1; i < surf.vertices.length - 1; i++) {
          const v1 = surf.vertices[i];
          const v2 = surf.vertices[i + 1];
          verticesArray.push(v0[0], v0[2], -v0[1]);
          verticesArray.push(v1[0], v1[2], -v1[1]);
          verticesArray.push(v2[0], v2[2], -v2[1]);
        }

        geometry.setAttribute('position', new THREE.Float32BufferAttribute(verticesArray, 3));
        geometry.computeVertexNormals();

        let baseColor = 0x3b82f6;
        if (editMode === 'zone' && !readOnly) {
          const liveZoneData =
            selectedId === surf.zone && draftState ? draftState : zones.find((z) => z.id === surf.zone);
          if (liveZoneData) {
            if (!liveZoneData.isConditioned) {
              baseColor = 0x475569;
            } else {
              const act = ACTIVITIES.find((a) => a.id === liveZoneData.activityId);
              baseColor = act ? act.color : 0x3b82f6;
            }
          }
        } else {
          if (surf.type === 'Roof') {
            baseColor = 0xef4444;
          } else if (surf.type === 'InternalSlab' || surf.type === 'SlabOnGrade' || surf.type === 'UndergroundSlab' || surf.type === 'InteriorFloor' || surf.type === 'Ceiling' || surf.type === 'Floor' || surf.type === 'ExteriorFloor') {
            baseColor = 0x8b5cf6;
          } else if (surf.type === 'GroundFloor') {
            baseColor = 0x78716c;
          } else if (surf.type === 'InternalWall' || surf.type === 'InteriorWall') {
            baseColor = 0xf59e0b;
          } else {
            baseColor = 0x3b82f6;
          }
        }

        let finalOpacity = 0.15;
        let finalEmissive = 0x000000;
        let finalEmissiveIntensity = 0;
        let lineColor = baseColor;
        let isXRayMode = false;

        if (isSelected) {
          finalOpacity = 0.95;
          finalEmissive = baseColor;
          finalEmissiveIntensity = 0.6;
          lineColor = 0xffffff;
          isXRayMode = true;
        } else if (isHovered) {
          finalOpacity = 0.85;
          finalEmissive = 0xfacc15;
          finalEmissiveIntensity = 0.6;
          lineColor = 0xfacc15;
          isXRayMode = true;
        } else if (!selectedId && !hoveredId) {
          finalOpacity =
            editMode === 'zone' && !readOnly
              ? 0.6
              : surf.type === 'InternalWall' || surf.type === 'InteriorWall'
              ? 0.25
              : 0.4;
        } else {
          finalOpacity = 0.05;
        }

        const material = new THREE.MeshStandardMaterial({
          color: baseColor,
          transparent: true,
          opacity: finalOpacity,
          emissive: finalEmissive,
          emissiveIntensity: finalEmissiveIntensity,
          side: THREE.DoubleSide,
          depthWrite: true,
        });

        const mesh = new THREE.Mesh(geometry, material);

        surf.vertices.forEach((v) => {
          const vx = v[0],
            vy = v[2],
            vz = -v[1];
          if (vx < minX) minX = vx;
          if (vx > maxX) maxX = vx;
          if (vy < minY) minY = vy;
          if (vy > maxY) maxY = vy;
          if (vz < minZ) minZ = vz;
          if (vz > maxZ) maxZ = vz;
        });

        surf.baseColor = baseColor;
        mesh.userData = surf;

        const lineGeom = new THREE.BufferGeometry();
        const lineVerts = [];

        surf.vertices.forEach((v) => {
          lineVerts.push(v[0], v[2], -v[1]);
        });

        if (surf.vertices.length > 0) {
          lineVerts.push(surf.vertices[0][0], surf.vertices[0][2], -surf.vertices[0][1]);
        }

        lineGeom.setAttribute('position', new THREE.Float32BufferAttribute(lineVerts, 3));
        const lineMat = new THREE.LineBasicMaterial({
          color: lineColor,
          linewidth: isXRayMode ? 2 : 1,
          depthTest: !isXRayMode,
        });

        const line = new THREE.Line(lineGeom, lineMat);
        if (isXRayMode) {
          line.renderOrder = 999;
        }
        mesh.add(line);

        if (surf.openings && surf.openings.length > 0) {
          surf.openings.forEach((op) => {
            if (op.vertices && op.vertices.length >= 3) {
              const opGeom = new THREE.BufferGeometry();
              const opVerts = [];
              const ov0 = op.vertices[0];

              for (let i = 1; i < op.vertices.length - 1; i++) {
                const ov1 = op.vertices[i];
                const ov2 = op.vertices[i + 1];
                opVerts.push(ov0[0], ov0[2], -ov0[1]);
                opVerts.push(ov1[0], ov1[2], -ov1[1]);
                opVerts.push(ov2[0], ov2[2], -ov2[1]);
              }

              opGeom.setAttribute('position', new THREE.Float32BufferAttribute(opVerts, 3));
              opGeom.computeVertexNormals();

              const opMat = new THREE.MeshStandardMaterial({
                color: 0x06b6d4,
                transparent: true,
                opacity: 0.8,
                side: THREE.DoubleSide,
                polygonOffset: true,
                polygonOffsetFactor: -1,
                polygonOffsetUnits: -1,
              });

              const opMesh = new THREE.Mesh(opGeom, opMat);
              mesh.add(opMesh);
            }
          });
        }
        group.add(mesh);
      }
    });

    let camDistance = 50;
    if (
      visibleSurfaces.length > 0 &&
      Number.isFinite(minX) &&
      Number.isFinite(maxX) &&
      Number.isFinite(minY) &&
      Number.isFinite(maxY) &&
      Number.isFinite(minZ) &&
      Number.isFinite(maxZ)
    ) {
      const centerX = (maxX + minX) / 2;
      const centerY = (maxY + minY) / 2;
      const centerZ = (maxZ + minZ) / 2;

      group.position.set(-centerX, -centerY, -centerZ);
      const maxDim = Math.max(maxX - minX, maxY - minY, maxZ - minZ);

      camera.far = Math.max(10000, maxDim * 20);
      camera.updateProjectionMatrix();

      camDistance = maxDim === 0 ? 50 : maxDim * 1.5;
    } else {
      group.position.set(0, 0, 0);
    }

    if (!Number.isFinite(camDistance) || camDistance === 0) camDistance = 50;

    if (camera.position.x === 0 && camera.position.y === 0 && camera.position.z === 0) {
      camera.position.set(camDistance, camDistance * 0.8, camDistance);
      camera.lookAt(0, 0, 0);
      controls.target.set(0, 0, 0);
      controls.update();
    }
  }, [surfaces, zones, activeFloor, editMode, selectedId, hoveredId, draftState, readOnly, isDarkMode]);

  return (
    <div className="relative w-full h-full min-h-[500px] overflow-hidden rounded-xl bg-slate-900 shadow-inner border border-slate-700">
      <div
        ref={mountRef}
        className="absolute inset-0 z-10 w-full h-full cursor-pointer"
        style={{ mixBlendMode: 'normal' }}
      />
    </div>
  );
};

// --- [메인 애플리케이션] ---
export default function App() {
  const [step, setStep] = useState('landing');
  const [selectedMetric, setSelectedMetric] = useState(null);
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [showScheduleModal, setShowScheduleModal] = useState(false);

  const [projectData, setProjectData] = useState({
    name: '신규 프로젝트',
    activityId: 1105,
    location: 'KOR_SQ_Seoul',
    pvCapacity: 0,
    geothermalApplied: false,
    orientation: 0,
    customSchedule: {
      useCustom: true,
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

  const fileInputRef = useRef(null);
  const [uploadedFile, setUploadedFile] = useState(null);
  const [uploadError, setUploadError] = useState(null);

  const [lightCalc, setLightCalc] = useState({ active: false, w: 32, qty: 10, area: 100 });
  const [equipCalc, setEquipCalc] = useState({ active: false, w: 150, qty: 5, area: 100 });
  const [gapWarnings, setGapWarnings] = useState([]);

  const availableFloors = Array.from(
    new Set([...surfaces.map((s) => s.floor || 1), ...zones.map((z) => z.floor || 1)])
  ).sort((a, b) => a - b);
  const displayFloors = availableFloors.length > 0 ? availableFloors : [1, 2, 3];

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
            });
          }
        });
      });
    }
    setSurfaces(newSurfaces);
    setZones(newZones);
    setStep('buildingView');
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setUploadedFile(file);
    setUploadError(null);
    setStep('parsing');

    try {
      const response = await uploadGbxml(file);
      if (response && response.data) {
        setSurfaces(response.data.surfaces || []);
        const mappedZones = (response.data.zones || []).map((z) => ({
          ...z,
          peopleDensity: z.peopleDensity || 0.1,
          lightingPower: z.lightingPower || 10.0,
          equipmentPower: z.equipmentPower || 15.0,
        }));
        setZones(mappedZones);
        
        // 💡 면 갭 경고 처리
        const warnings = response.data.warnings || [];
        if (warnings.length > 0) {
          setGapWarnings(warnings);
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

  const handleSimulation = async () => {
    setStep('loading');
    setLoadingMsgIdx(0);

    const interval = setInterval(() => {
      setLoadingMsgIdx((prev) => Math.min(prev + 1, LOADING_MESSAGES.length - 1));
    }, 1500);

    try {
      const payload = { projectData: projectData, zones: zones, surfaces: surfaces };
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
        ...categoriesList.reduce((acc, c) => ({ ...acc, [c.name]: Number(m[c.id]?.con || 0) * 2.1 }), {}),
      },
    ];
  };

  const categories = ['신재생', '난방', '냉방', '급탕', '조명', '환기'];
  const colors = ['#2DD4BF', '#F87171', '#60A5FA', '#FB923C', '#FACC15', '#4ADE80'];

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

    // 리모델링 적용 후 에너지 운영비 (1년)
    const retrofitRunningCost = res.financial.total_energy_bill;
    // 초기 투자 비용
    const capitalCost = res.financial.capital_cost;

    // 기준 건물(기존 노후 건물)의 에너지 운영비 추정 (약 60% 더 발생한다고 가정 - U-value 1.5, 싱글창호 기준 추산)
    const baseRunningCost = retrofitRunningCost * 1.6;

    // 연간 에너지 절감액
    const annualSavings = baseRunningCost - retrofitRunningCost;

    // 15년간의 현금흐름 추적 (인플레이션 2% 가정)
    const inflationRate = 0.02;
    const data = [];

    let cumulativeBase = 0;
    let cumulativeRetrofit = -capitalCost; // Year 0 투자

    for (let year = 0; year <= 15; year++) {
      if (year > 0) {
        cumulativeBase -= baseRunningCost * Math.pow(1 + inflationRate, year - 1);
        cumulativeRetrofit -= retrofitRunningCost * Math.pow(1 + inflationRate, year - 1);
      }

      data.push({
        year: `${year}년차`,
        '기존 노후건물 유지': cumulativeBase,
        '친환경 리모델링 (투자+운영)': cumulativeRetrofit,
        '누적 순이익 (ROI)': cumulativeRetrofit - cumulativeBase, // 0을 돌파하면 손익분기점!
      });
    }
    return { data, annualSavings, paybackYears: capitalCost / annualSavings };
  };

  const lccAnalysis = getCashFlowData();
  const inactiveBtnClass = isDarkMode
    ? 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
    : 'text-slate-500 hover:text-slate-700 hover:bg-slate-300';

  return (
    <>
      <style>{`
        #root { max-width: none !important; width: 100% !important; margin: 0 !important; padding: 0 !important; text-align: left !important; } 
        body { margin: 0 !important; display: block !important; min-width: 100vw !important; min-height: 100vh !important; overflow: hidden !important; }

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
            <SimulationEngine onStart={() => setStep('upload')} />
          </main>
        </div>
      ) : (
      <div className={`h-screen w-full transition-colors duration-300 ${theme.bg} font-sans flex flex-col overflow-hidden`}>
        <header className={`flex-shrink-0 px-8 py-4 border-b ${isDarkMode ? 'border-slate-800 bg-[#0B0F19]' : 'border-[#D5D2C9] bg-[#DFDCD5]'} flex justify-between items-center z-10 shadow-sm`}>
          <div 
            className="flex items-center gap-3 cursor-pointer hover:opacity-80 transition-opacity" 
            onClick={() => setStep('upload')}
          >
            <div className="w-8 h-8 bg-emerald-500 rounded-lg flex items-center justify-center shadow-lg">
              <Layers className="text-white" size={18} />
            </div>
            <h1 className="text-lg font-black tracking-tighter uppercase">ZeroBase</h1>
          </div>
          <div className="hidden md:flex items-center gap-4 text-[10px] font-black tracking-widest uppercase opacity-60">
            <span className={step === 'upload' ? 'text-emerald-500' : ''}>1. Project Setup</span> <ArrowRight size={10} />
            <span className={step === 'buildingView' || step === 'floorView' ? 'text-emerald-500' : ''}>2. 3D Model</span> <ArrowRight size={10} />
            <span className={step === 'floorView' && selectedId ? 'text-emerald-500' : ''}>3. Property Editor</span> <ArrowRight size={10} />
            <span className={step === 'result' ? 'text-emerald-500' : ''}>4. Analysis</span>
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
            <div className="w-full h-full mx-auto px-6 pt-8 animate-in fade-in slide-in-from-bottom-4 overflow-y-auto custom-scrollbar">
              <div className="text-center mb-12">
                <h2 className={`text-5xl font-black mb-6 tracking-tight ${theme.textMain}`}>BEM 에너지 시뮬레이션</h2>
                <p className={`text-lg ${theme.textSub}`}>BIM 형상 데이터를 분석하고 각 객체의 열역학적 속성과 신재생 설비를 튜닝하세요.</p>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                {/* 왼쪽: 파일 업로드 */}
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
                        }}
                        className={`mt-8 text-xs font-bold transition-colors underline ${isDarkMode ? 'text-slate-500 hover:text-red-400' : 'text-slate-400 hover:text-red-500'}`}
                      >
                        다른 파일 다시 업로드하기
                      </button>
                    </div>
                  )}
                </div>

                {/* 오른쪽: 프로젝트 및 신재생 환경 설정 */}
                <div className="flex flex-col gap-6">
                  {/* 프로젝트 기본 설정 */}
                  <div className={`p-8 rounded-[2rem] border ${theme.card}`}>
                    <h3 className="text-lg font-bold mb-6 flex items-center gap-2 border-b border-emerald-500/20 pb-3 text-emerald-500">
                      <Building size={20} /> 프로젝트 기본 정보
                    </h3>
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

                  <div className={`p-8 rounded-[2rem] border ${theme.card} shadow-lg shadow-blue-500/5 border-blue-500/20`}>
                    <h3 className="text-lg font-bold mb-6 flex items-center gap-2 border-b border-blue-500/20 pb-3 text-blue-500">
                      <Sun size={20} /> 신재생 에너지 시스템 (Renewable)
                    </h3>
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
                    </div>
                  </div>
                </div>
              </div>

              {uploadedFile && surfaces.length > 0 && (
                <div className="mt-8 flex justify-end animate-in fade-in slide-in-from-bottom-4">
                  <button
                    onClick={() => setStep('buildingView')}
                    className="px-10 py-5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-[1.5rem] font-black text-lg shadow-xl shadow-emerald-500/30 flex items-center gap-3 transition-transform hover:scale-105"
                  >
                    <CheckCircle2 size={24} /> 프로젝트 설정 완료 및 3D 모델 렌더링 <ArrowRight size={24} />
                  </button>
                </div>
              )}
            </div>
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
                      className="px-5 py-2 rounded-xl bg-emerald-600 text-white font-black hover:bg-emerald-500 transition-colors shadow-md min-w-[3.5rem]"
                    >
                      {f}F
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex-1 relative w-full h-full p-4 flex flex-col">
                <div className="flex-1 relative min-h-[400px]">
                  <BuildingViewer
                    surfaces={surfaces}
                    zones={zones}
                    activeFloor="all"
                    editMode="surface"
                    onSurfaceClick={() => {}}
                    onZoneClick={() => {}}
                    isDarkMode={isDarkMode}
                  />
                </div>
              </div>
            </div>
          )}

          {/* STEP 3 & 4: Floor View + Side Editor Panel */}
          {step === 'floorView' && (
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
                    <div className="flex bg-black/20 p-1.5 rounded-xl border border-white/5 shadow-inner">
                      {displayFloors.map((f) => (
                        <button
                          key={f}
                          onClick={() => {
                            setActiveFloor(f);
                            handleSaveClose();
                            setSelectedId(null);
                            setHoveredId(null);
                          }}
                          className={`px-5 py-2 text-sm font-black rounded-lg transition-all ${
                            activeFloor === f
                              ? 'bg-emerald-500 text-white shadow-[0_0_15px_rgba(16,185,129,0.5)]'
                              : 'text-slate-400 hover:text-white hover:bg-white/10'
                          }`}
                        >
                          {f}F
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
                      className={`p-6 border-b sticky top-0 backdrop-blur-xl z-10 flex justify-between items-center ${
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
                              {ACTIVITIES.map((a) => (
                                <option key={a.id} value={a.id}>
                                  {a.name}
                                </option>
                              ))}
                            </select>
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
                              radius={i === 0 ? [6, 0, 0, 6] : i === 5 ? [0, 6, 6, 0] : 0}
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
                              if (row.id === 'grd') return Number(base?.con || 0) * 2.1;
                              return 0;
                            };
                            const rowDataValues = ['renewable', 'heating', 'cooling', 'hotwater', 'lighting', 'ventilation'].map((id) =>
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
                  {/* 핵심 3대 지표 요약 */}
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    {[
                      {
                        label: '초기 총 공사비 (Capital Cost)',
                        val: formatWon(res.financial.capital_cost).replace(' 만 원', ''),
                        unit: '만 원',
                        isRawString: true, // Prevents formatting as number
                        layoutId: 'lcc-capital',
                        colorClass: 'text-amber-500',
                        bgClass: 'bg-amber-500/10',
                        borderClass: 'border-amber-500/20',
                        hoverClass: 'hover:border-amber-500/50',
                        icon: <Wallet className="text-amber-500" size={32} />,
                        desc: '기존 건물의 에너지 성능을 개선하기 위해 투입되는 1회성 공사비입니다. 고효율 창호, 단열재 보강, 고효율 조명 등 적용된 친환경 자재 스펙과 조달청 단가를 기반으로 자동 산출되며, LCC(생애주기비용) 모의 분석의 출발점이 되는 핵심 투자금입니다.'
                      },
                      {
                        label: '연간 운영비 (Running Cost)',
                        val: formatWon(res.financial.total_energy_bill).replace(' 만 원', ''),
                        unit: '만 원 / 년',
                        isRawString: true,
                        layoutId: 'lcc-running',
                        colorClass: 'text-emerald-400',
                        bgClass: 'bg-emerald-500/10',
                        borderClass: 'border-emerald-500/20',
                        hoverClass: 'hover:border-emerald-500/50',
                        icon: <PiggyBank className="text-emerald-500" size={32} />,
                        desc: '친환경 건물로 변신한 뒤, 향상된 단열성능과 설비효율 덕분에 실제로 매년 납부하게 될 평균 에너지 요금입니다. 현재 노후 상태일 때 납부하는 예상 관리비와 비교 시 연간 수익(절감액)을 직관적으로 보여주는 지표입니다.'
                      },
                      {
                        label: '투자비 회수 기간 (Payback)',
                        val: lccAnalysis.paybackYears.toFixed(1),
                        unit: '년',
                        isRawString: true,
                        layoutId: 'lcc-payback',
                        colorClass: 'text-blue-400',
                        bgClass: 'bg-blue-500/10',
                        borderClass: 'border-blue-500/20',
                        hoverClass: 'hover:border-blue-500/50',
                        icon: <TrendingUp className="text-blue-500" size={32} />,
                        glow: true,
                        desc: '초기 지출한 "총 공사비"를 매 등 매년 아껴지는 "에너지 요금 절감액"으로 100% 되돌려 받는 데 걸리는 기간입니다. 이 기간이 짧을수록 경제적 타당성이 높은 리모델링이며, 이 기간이 끝나는 시점부터는 오롯이 흑자를 보게 됩니다.'
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

                  {/* 세부 내역 2분할 */}
                  <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                    {/* 공사비 브레이크다운 */}
                    <div className={`p-8 rounded-[2.5rem] ${theme.card} border shadow-lg flex flex-col`}>
                      <h3 className={`text-lg font-black flex items-center gap-2 mb-6 ${theme.textMain}`}>
                        <Calculator size={20} className="text-amber-500" /> 공종별 내역서 (조달청/친환경 DB)
                      </h3>

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