// components/viewer/BuildingViewer.jsx
// 3D 건물 뷰어 컴포넌트 (Three.js + OrbitControls)
// 태양 궤적, 표면 열해석, 환기/풍량 시각화 모드 포함

import React, { useRef, useEffect } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

import { ACTIVITIES } from '../../data/constants';
import { createTextSprite, clearGroup } from '../../utils/threeHelper';
import { getSolarPosition, drawSunPathDome } from '../../utils/solarHelper';
import { getRadiationColor, getTemperatureColor, drawThermalLabel } from '../../utils/thermalHelper';
import { drawAirflowVisuals } from '../../utils/airflowHelper';

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
  viewMode = 'default',
  setViewMode,
  sunMonth = 6,
  setSunMonth,
  sunHour = 12,
  setSunHour,
  res = null,
  latitude = 37.56,
  locationName = '서울특별시 (Seoul)',
}) => {
  const mountRef = useRef(null);
  const ctx = useRef({});
  const effectiveViewMode = readOnly ? viewMode : 'default';
  const effectiveDarkMode = isDarkMode || (readOnly && (viewMode === 'sunpath' || viewMode === 'thermal' || viewMode === 'airflow'));

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
    
    // 그림자 섀도우맵 세팅
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;

    mountRef.current.appendChild(renderer.domElement);

    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(20, 50, 30);
    dirLight.castShadow = true;
    dirLight.shadow.mapSize.width = 2048;
    dirLight.shadow.mapSize.height = 2048;
    scene.add(dirLight);

    const group = new THREE.Group();
    scene.add(group);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.autoRotate = readOnly;
    controls.autoRotateSpeed = 1.0;

    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();
    ctx.current = { scene, camera, renderer, group, controls, raycaster, mouse, reqId: null, ro: null, dirLight, ambientLight };

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
    const { scene, group, camera, controls, renderer, dirLight, ambientLight } = ctx.current;
    if (!scene || !group || !camera || !controls || !renderer) return;

    scene.background = new THREE.Color(effectiveDarkMode ? '#0f172a' : '#e2e8f0');

    // 1. 기존 그룹 객체 비우기
    clearGroup(group);

    // 2. 프리패스: 바운딩 박스 크기 및 중점 연산
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity, minZ = Infinity, maxZ = -Infinity;
    const visibleSurfaces =
      activeFloor === 'all' ? surfaces : surfaces.filter((s) => s.floor === parseInt(activeFloor));

    visibleSurfaces.forEach((surf) => {
      if (surf.width && surf.height && surf.pos) {
        if (surf.pos.x < minX) minX = surf.pos.x;
        if (surf.pos.x > maxX) maxX = surf.pos.x;
        if (surf.pos.y < minY) minY = surf.pos.y;
        if (surf.pos.y > maxY) maxY = surf.pos.y;
        if (surf.pos.z < minZ) minZ = surf.pos.z;
        if (surf.pos.z > maxZ) maxZ = surf.pos.z;
      } else if (surf.vertices) {
        surf.vertices.forEach((v) => {
          const vx = v[0], vy = v[2], vz = -v[1];
          if (vx < minX) minX = vx;
          if (vx > maxX) maxX = vx;
          if (vy < minY) minY = vy;
          if (vy > maxY) maxY = vy;
          if (vz < minZ) minZ = vz;
          if (vz > maxZ) maxZ = vz;
        });
      }
    });

    const hasGeometry = visibleSurfaces.length > 0 && Number.isFinite(minX) && Number.isFinite(maxX);
    const centerX = hasGeometry ? (maxX + minX) / 2 : 0;
    const centerY = hasGeometry ? (maxY + minY) / 2 : 0;
    const centerZ = hasGeometry ? (maxZ + minZ) / 2 : 0;
    const maxDim = hasGeometry ? Math.max(maxX - minX, maxY - minY, maxZ - minZ) : 50;
    const size = maxDim / 2;

    // 3. 태양 위치 및 그림자 조명 연산
    const sunPos = getSolarPosition(latitude, sunMonth, sunHour);
    const R = Math.max(maxDim * 1.3, 30);
    
    // 월드 좌표계 태양 조명 위치
    const worldSunX = R * Math.cos(sunPos.altitude) * Math.sin(sunPos.azimuth);
    const worldSunY = (minY - centerY - 0.05) + R * Math.sin(sunPos.altitude);
    const worldSunZ = -R * Math.cos(sunPos.altitude) * Math.cos(sunPos.azimuth);

    // 로컬 그룹 내부 태양 구체 위치
    const localSunX = centerX + R * Math.cos(sunPos.altitude) * Math.sin(sunPos.azimuth);
    const localSunY = (minY - 0.05) + R * Math.sin(sunPos.altitude);
    const localSunZ = centerZ - R * Math.cos(sunPos.altitude) * Math.cos(sunPos.azimuth);

    // 실시간 태양 광선 벡터 (일사량 연산용)
    const sunDir = new THREE.Vector3(
      Math.cos(sunPos.altitude) * Math.sin(sunPos.azimuth),
      Math.sin(sunPos.altitude),
      -Math.cos(sunPos.altitude) * Math.cos(sunPos.azimuth)
    ).normalize();

    if (dirLight) {
      if (viewMode === 'sunpath' || viewMode === 'thermal') {
        if (sunPos.altitude >= -0.05) {
          dirLight.position.set(worldSunX, worldSunY, worldSunZ);
          dirLight.intensity = 0.9 * Math.sin(sunPos.altitude);
          dirLight.castShadow = true;
          
          // 동적 그림자 캡처 구역 설정
          const d = size * 1.5;
          dirLight.shadow.camera.left = -d;
          dirLight.shadow.camera.right = d;
          dirLight.shadow.camera.top = d;
          dirLight.shadow.camera.bottom = -d;
          dirLight.shadow.camera.near = 0.1;
          dirLight.shadow.camera.far = R * 2.5;
          dirLight.shadow.bias = -0.0005;
        } else {
          dirLight.intensity = 0.0;
          dirLight.castShadow = false;
        }
        
        if (ambientLight) {
          ambientLight.intensity = 0.2 + 0.3 * Math.max(0, Math.sin(sunPos.altitude));
        }
      } else {
        dirLight.position.set(20, 50, 30);
        dirLight.intensity = 0.8;
        dirLight.castShadow = false;
        if (ambientLight) {
          ambientLight.intensity = 0.6;
        }
      }
    }

    // 4. 바닥 그림자 수신 Plane 및 태양 궤적 돔 생성
    if (hasGeometry) {
      if (viewMode === 'sunpath' || viewMode === 'thermal') {
        drawSunPathDome(group, {
          R,
          minY,
          centerY,
          centerZ,
          centerX,
          latitude,
          sunMonth,
          sunHour,
          size,
          effectiveDarkMode,
          localSunX,
          localSunY,
          localSunZ,
          sunPos
        });
      }
    }

    // 5. 건물 외피 매쉬 생성 및 렌더링
    visibleSurfaces.forEach((surf) => {
      const isHovered =
        (editMode === 'surface' && surf.id === hoveredId) || (editMode === 'zone' && surf.zone === hoveredId);
      const isSelected =
        (editMode === 'surface' && surf.id === selectedId) || (editMode === 'zone' && surf.zone === selectedId);

      let baseColor = 0x3b82f6;

      if (viewMode === 'thermal') {
        const thermalData = res?.surfaceThermal?.[surf.id] || res?.result?.surfaceThermal?.[surf.id];
        
        if (thermalData && thermalData.temperature) {
          const tempVal = thermalData.temperature[sunMonth - 1] ?? 20.0;
          baseColor = getTemperatureColor(tempVal, effectiveDarkMode);
        } else {
          // 실시간 외벽 일사량 가상 매핑
          let normal = new THREE.Vector3(0, 0, 1);
          if (surf.width && surf.height && surf.pos && surf.rot) {
            normal.applyEuler(new THREE.Euler(surf.rot.x, surf.rot.y, surf.rot.z));
          } else if (surf.vertices && surf.vertices.length >= 3) {
            const v0 = new THREE.Vector3(surf.vertices[0][0], surf.vertices[0][2], -surf.vertices[0][1]);
            const v1 = new THREE.Vector3(surf.vertices[1][0], surf.vertices[1][2], -surf.vertices[1][1]);
            const v2 = new THREE.Vector3(surf.vertices[2][0], surf.vertices[2][2], -surf.vertices[2][1]);
            normal.crossVectors(
              new THREE.Vector3().subVectors(v1, v0),
              new THREE.Vector3().subVectors(v2, v0)
            ).normalize();
          }
          const dot = normal.dot(sunDir);
          
          if (surf.type === 'Roof' || surf.type === 'Wall' || surf.type === 'ExteriorWall') {
            baseColor = getRadiationColor(dot, effectiveDarkMode);
          } else {
            baseColor = effectiveDarkMode ? 0x1e293b : 0xe2e8f0; // 내부는 음영 처리
          }
        }
      } else if (viewMode === 'airflow') {
        baseColor = effectiveDarkMode ? 0x1e293b : 0xe2e8f0; // Neutral backdrop for airflow visualization
      } else {
        // 기존 테마별 색상 설정
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
          } else if (
            surf.type === 'InternalSlab' ||
            surf.type === 'SlabOnGrade' ||
            surf.type === 'UndergroundSlab' ||
            surf.type === 'InteriorFloor' ||
            surf.type === 'Ceiling' ||
            surf.type === 'Floor' ||
            surf.type === 'ExteriorFloor'
          ) {
            baseColor = 0x8b5cf6;
          } else if (surf.type === 'GroundFloor') {
            baseColor = 0x78716c;
          } else if (surf.type === 'InternalWall' || surf.type === 'InteriorWall') {
            baseColor = 0xf59e0b;
          } else {
            baseColor = 0x3b82f6;
          }
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
      } else if (viewMode === 'thermal') {
        finalOpacity = 0.85; // 일사 매핑 모드에서는 면을 뚜렷이 칠함
      } else if (viewMode === 'airflow') {
        finalOpacity = 0.45; // 환기 모드에서는 개구부 풍향 관찰을 위해 반투명하게 설정
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

      let geometry;
      let mesh;

      if (surf.width && surf.height && surf.pos && surf.rot) {
        geometry = new THREE.PlaneGeometry(surf.width, surf.height);
        mesh = new THREE.Mesh(geometry, material);
        mesh.position.set(surf.pos.x, surf.pos.y, surf.pos.z);
        mesh.rotation.set(surf.rot.x, surf.rot.y, surf.rot.z);
      } else if (surf.vertices && surf.vertices.length >= 3) {
        geometry = new THREE.BufferGeometry();
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
        mesh = new THREE.Mesh(geometry, material);
      }

      if (mesh) {
        mesh.castShadow = viewMode === 'sunpath' || viewMode === 'thermal';
        mesh.receiveShadow = viewMode === 'sunpath' || viewMode === 'thermal';

        surf.baseColor = baseColor;
        mesh.userData = surf;

        // 경계선 그리기
        const edges = new THREE.EdgesGeometry(geometry);
        const lineMat = new THREE.LineBasicMaterial({
          color: lineColor,
          linewidth: isXRayMode ? 2 : 1,
          depthTest: !isXRayMode,
        });
        const line = new THREE.LineSegments(edges, lineMat);
        if (isXRayMode) line.renderOrder = 999;
        mesh.add(line);

        // 창호 그리기
        const liveWwr = editMode === 'surface' && selectedId === surf.id && draftState ? draftState.wwr : surf.wwr;
        const safeWwr = isNaN(liveWwr) ? 0 : Math.max(0, Math.min(90, liveWwr));

        if ((surf.type === 'Wall' || surf.type === 'ExteriorWall') && safeWwr > 0 && surf.width && surf.height) {
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
          winMesh.castShadow = mesh.castShadow;
          winMesh.receiveShadow = mesh.receiveShadow;
          mesh.add(winMesh);
        } else if (surf.openings && surf.openings.length > 0) {
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
              opMesh.castShadow = mesh.castShadow;
              opMesh.receiveShadow = mesh.receiveShadow;
              mesh.add(opMesh);
            }
          });
        }
        group.add(mesh);

        // 표면 온도 텍스트 라벨 추가 (Add surface temperature text label)
        if (viewMode === 'thermal') {
          drawThermalLabel(group, surf, {
            sunMonth,
            res,
            effectiveDarkMode,
            size,
            createTextSprite
          });
        }

        // 개구부 풍량/환기 3D 화살표 및 텍스트 라벨 추가 (Add opening airflow 3D arrows and text labels)
        if (viewMode === 'airflow') {
          drawAirflowVisuals(group, surf, {
            sunMonth,
            res,
            effectiveDarkMode,
            size,
            createTextSprite
          });
        }
      }
    });

    // 6. 카메라 시점 초기화 및 핏 조절
    let camDistance = 50;
    if (hasGeometry) {
      group.position.set(-centerX, -centerY, -centerZ);
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
  }, [surfaces, zones, activeFloor, editMode, selectedId, hoveredId, draftState, readOnly, isDarkMode, viewMode, sunMonth, sunHour, res]);

  return (
    <div className="relative w-full h-full min-h-[500px] overflow-hidden rounded-xl bg-slate-900 shadow-inner border border-slate-700">
      <div
        ref={mountRef}
        className="absolute inset-0 z-10 w-full h-full cursor-pointer"
        style={{ mixBlendMode: 'normal' }}
      />
      
      {/* 뷰 모드 스위처 (Floating View Mode Switcher) */}
      <div className={`absolute top-4 left-4 z-20 flex gap-1 p-1 rounded-xl shadow-lg backdrop-blur-md border ${
        effectiveDarkMode ? 'bg-slate-950/80 border-slate-800' : 'bg-white/80 border-slate-200'
      }`}>
        {[
          { id: 'default', label: '👁️ 기본 뷰' },
          { id: 'sunpath', label: '☀️ 태양 궤적' },
          { id: 'thermal', label: '🌡️ 표면 일사량' },
          { id: 'airflow', label: '💨 환기/풍량' },
        ].map((mode) => (
          <button
            key={mode.id}
            onClick={() => setViewMode && setViewMode(mode.id)}
            className={`px-3 py-1.5 rounded-lg text-xs font-black transition-all duration-200 ${
              viewMode === mode.id
                ? 'bg-emerald-500 text-white shadow-sm'
                : effectiveDarkMode
                ? 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
            }`}
          >
            {mode.label}
          </button>
        ))}
      </div>

      {/* 태양/환기 시뮬레이션 설정 패널 (Floating Sun/Airflow Control Panel) */}
      {(viewMode === 'sunpath' || viewMode === 'thermal' || viewMode === 'airflow') && (
        <div className={`absolute bottom-4 right-4 z-20 p-4 rounded-2xl shadow-xl backdrop-blur-md border flex flex-col gap-3 min-w-[240px] ${
          effectiveDarkMode ? 'bg-slate-950/80 border-slate-800' : 'bg-white/80 border-slate-200'
        }`}>
          <div className="flex items-center justify-between border-b pb-2 mb-1 border-slate-500/20">
            <span className={`text-xs font-black flex items-center gap-1 ${effectiveDarkMode ? 'text-slate-200' : 'text-slate-800'}`}>
              {viewMode === 'airflow' ? '💨 자연환기/풍량 설정' : '☀️ 태양광 시뮬레이션 설정'}
            </span>
            <span className="text-[10px] bg-amber-500/20 text-amber-500 px-1.5 py-0.5 rounded font-bold">
              {locationName.split(' ')[0]} (위도 {latitude.toFixed(2)}°)
            </span>
          </div>
          
          {/* Month Slider */}
          <div className="flex flex-col gap-1">
            <div className="flex justify-between text-[11px] font-bold">
              <span className={effectiveDarkMode ? 'text-slate-400' : 'text-slate-600'}>월 (Month)</span>
              <span className="text-emerald-500">{sunMonth}월</span>
            </div>
            <input
              type="range"
              min="1"
              max="12"
              value={sunMonth}
              onChange={(e) => setSunMonth && setSunMonth(parseInt(e.target.value))}
              className={`w-full h-1.5 rounded-lg appearance-none cursor-pointer accent-emerald-500 ${effectiveDarkMode ? 'bg-slate-700' : 'bg-slate-200'}`}
            />
            <div className="flex justify-between text-[9px] text-slate-500 font-bold px-0.5">
              <span>1월</span>
              <span>6월</span>
              <span>12월</span>
            </div>
          </div>

          {/* Hour Slider (Only visible for solar/thermal modes) */}
          {viewMode !== 'airflow' && (
            <div className="flex flex-col gap-1">
              <div className="flex justify-between text-[11px] font-bold">
                <span className={effectiveDarkMode ? 'text-slate-400' : 'text-slate-600'}>시간 (Hour)</span>
                <span className="text-emerald-500">
                  {sunHour === 0 ? '자정 (00:00)' : sunHour === 12 ? '남중 (12:00)' : `${sunHour}:00`}
                </span>
              </div>
              <input
                type="range"
                min="0"
                max="24"
                step="0.5"
                value={sunHour}
                onChange={(e) => setSunHour && setSunHour(parseFloat(e.target.value))}
                className={`w-full h-1.5 rounded-lg appearance-none cursor-pointer accent-emerald-500 ${effectiveDarkMode ? 'bg-slate-700' : 'bg-slate-200'}`}
              />
              <div className="flex justify-between text-[9px] text-slate-500 font-bold px-0.5">
                <span>00시</span>
                <span>12시</span>
                <span>24시</span>
              </div>
            </div>
          )}

          {/* Heatmap Legend */}
          {viewMode === 'thermal' && (
            <div className="flex flex-col gap-1 border-t pt-2 mt-1 border-slate-500/20">
              <span className={`text-[10px] font-black ${effectiveDarkMode ? 'text-slate-400' : 'text-slate-600'}`}>
                {res && (res.surfaceThermal || res.result?.surfaceThermal) ? '🌡️ 표면 온도 범례 (EnergyPlus)' : '☀️ 가상 일사량 범례'}
              </span>
              <div className="h-2 w-full rounded bg-gradient-to-r from-blue-500 via-yellow-400 to-red-500" />
              <div className="flex justify-between text-[9px] text-slate-500 font-bold">
                {res && (res.surfaceThermal || res.result?.surfaceThermal) ? (
                  <>
                    <span>-5°C (저온)</span>
                    <span>20°C</span>
                    <span>45°C (고온)</span>
                  </>
                ) : (
                  <>
                    <span>음영 (북향)</span>
                    <span>중간</span>
                    <span>직사 (남향)</span>
                  </>
                )}
              </div>
            </div>
          )}

          {/* Airflow Legend */}
          {viewMode === 'airflow' && (
            <div className="flex flex-col gap-1.5 border-t pt-2 mt-1 border-slate-500/20">
              <span className={`text-[10px] font-black ${effectiveDarkMode ? 'text-slate-400' : 'text-slate-600'}`}>
                {res && (res.surfaceAirflow || res.result?.surfaceAirflow) ? '💨 자연환기 및 풍량 범례 (EnergyPlus AFN)' : '💨 환기 시뮬레이션 대기 중'}
              </span>
              {res && (res.surfaceAirflow || res.result?.surfaceAirflow) ? (
                <>
                  <div className="flex gap-4 items-center mt-1">
                    <div className="flex items-center gap-1.5">
                      <div className="w-3 h-3 bg-[#0ea5e9] rounded-full" />
                      <span className="text-[9px] text-slate-400 font-bold">실내 유입 (Inflow)</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <div className="w-3 h-3 bg-[#f97316] rounded-full" />
                      <span className="text-[9px] text-slate-400 font-bold">실외 유출 (Outflow)</span>
                    </div>
                  </div>
                  <span className="text-[8px] text-slate-500 font-medium mt-1 block">
                    * 화살표 크기는 풍량(L/s) 크기에 비례합니다.
                  </span>
                </>
              ) : (
                <span className="text-[8px] text-slate-500 font-medium leading-relaxed block mt-0.5">
                  상단 '시뮬레이션 실행' 버튼을 누르면 월별 자연환기 유량 분석 결과가 화살표와 텍스트로 표시됩니다.
                </span>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default BuildingViewer;
