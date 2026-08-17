// components/viewer/BuildingViewer.jsx
// 3D 건물 뷰어 컴포넌트 (Three.js + OrbitControls)
// 태양 궤적, 표면 열해석, 환기/풍량 시각화 모드 포함

import React, { useRef, useEffect, useState, useMemo } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

import { ACTIVITIES } from '../../data/constants';
import { createTextSprite, clearGroup } from '../../utils/threeHelper';
import { buildSurfaceGeometry, newellNormal } from '../../utils/polygonGeometry';

// ⚠️ 면적 계산을 여기서 다시 쓰지 않는다. `utils/geometry.js` 의
// `calculateSurfaceArea` 가 정본이고 백엔드와의 일치를 참조값 시험이 대조한다.
// 같은 산식을 세 군데 두면 갈라지는 건 시간문제다(codex 지적).
import { calculateSurfaceArea as polyArea3D } from '../../utils/geometry';
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
  // ⚠️ **초기값 전용**이다(비제어). 이름을 `showShades` 로 두면 부모가 바꿀 때
  // 반응할 것으로 오해한다 — `default...` 로 계약을 이름에 적는다(codex 지적).
  // 기본 false: 기본 뷰는 IDF 에 실제로 들어가는 면만 보여준다.
  defaultShowExcludedSurfaces = false,
}) => {
  const mountRef = useRef(null);
  const ctx = useRef({});
  // 시뮬레이션에서 제외된 면(차양·고아 surface 등)의 표시 여부.
  const [shownExcluded, setShownExcluded] = useState(defaultShowExcludedSurfaces);

  // ⚠️ 백엔드가 면을 버리는 기준을 **그대로** 옮긴다:
  //   `z_id = s['zone'].replace(" ", "_")`
  //   `if z_id == "Unknown" or z_id not in valid_zone_ids: skipped`
  // ⚠️ 파이썬 `str.replace` 는 **전부** 바꾸지만 JS `String.replace(" ", "_")` 는
  // **첫 하나만** 바꾼다. 공백이 둘 이상인 존 이름에서 갈린다 — `replaceAll` 이어야
  // 한다(codex 지적).
  const normZone = (v) => (v || '').replaceAll(' ', '_');
  const zoneIds = useMemo(
    () => new Set((zones || []).map((z) => normZone(z.id))),
    [zones]
  );
  const inSimulation = React.useCallback(
    (s) => {
      const z = normZone(s.zone);
      return z !== '' && z !== 'Unknown' && zoneIds.has(z);
    },
    [zoneIds]
  );
  // ⚠️ 파생값이다. effect 안에서 state 로 저장하면 토글이 한 렌더 늦게 뜨고
  // 불필요한 재렌더가 생긴다(codex 지적).
  const hiddenCount = useMemo(() => {
    const list =
      activeFloor === 'all' ? surfaces : (surfaces || []).filter((s) => s.floor === parseInt(activeFloor));
    return (list || []).filter((s) => !inSimulation(s)).length;
  }, [surfaces, activeFloor, inSimulation]);
  // NOTE: 한때 `readOnly ? viewMode : 'default'` 로 편집 화면의 특수 뷰를 막으려 했으나
  // 실제로는 어디서도 쓰이지 않았다. 편집 화면(App/FloorEditor)도 setViewMode 를 넘겨
  // 일조·열·기류 전환 UI를 제공하므로, 그 게이팅을 살리면 기능이 죽는다. 그래서 제거했다.
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

    // cleanup 시점의 mountRef.current 는 이미 바뀌었을 수 있다. effect 실행 시점의
    // 노드를 지역 변수로 붙잡아 두고 그것을 정리한다.
    const mountNode = mountRef.current;
    return () => {
      if (ctx.current.reqId) cancelAnimationFrame(ctx.current.reqId);
      if (ctx.current.ro) ctx.current.ro.disconnect();
      if (ctx.current.controls) ctx.current.controls.dispose();
      if (ctx.current.renderer) {
        ctx.current.renderer.dispose();
        if (mountNode && ctx.current.renderer.domElement) {
          try {
            mountNode.removeChild(ctx.current.renderer.domElement);
          } catch { /* 이미 제거된 노드 */ }
        }
      }
      ctx.current = {};
    };
    // readOnly 를 의존성에 넣으면 값이 바뀔 때마다 Three.js 씬을 통째로 재생성한다.
    // 초기화는 마운트 1회로 두고, readOnly 변화는 바로 아래 동기화 effect 가 반영한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    ctx.current.onSurfaceClick = onSurfaceClick;
    ctx.current.onZoneClick = onZoneClick;
    ctx.current.editMode = editMode;
  }, [onSurfaceClick, onZoneClick, editMode]);

  // 초기화 effect 는 []로 한 번만 돌기 때문에, 마운트 후 readOnly 가 바뀌면
  // 그때 설정한 autoRotate 가 낡은 값으로 남는다. readOnly 변화에 맞춰 동기화한다.
  useEffect(() => {
    if (ctx.current.controls) ctx.current.controls.autoRotate = readOnly;
  }, [readOnly]);

  useEffect(() => {
    if (readOnly || !ctx.current.camera) return;
    const onClick = (e) => {
      if (!mountRef.current || !ctx.current.camera || !ctx.current.group) return;
      const rect = mountRef.current.getBoundingClientRect();
      ctx.current.mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      ctx.current.mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      ctx.current.raycaster.setFromCamera(ctx.current.mouse, ctx.current.camera);

      // ⚠️ `Mesh` 만 고르면 **삼각분할에 실패해 윤곽선만 남은 면을 못 고른다.**
      // 그런 면일수록 사용자가 눌러서 확인해야 하는 대상이다(codex 지적).
      // 선은 두께가 없으므로 threshold 를 줘서 근처 클릭을 잡는다.
      const pickable = ctx.current.group.children.filter(
        (c) => (c.type === 'Mesh' || c.type === 'LineLoop') && c.userData?.id
      );
      ctx.current.raycaster.params.Line.threshold = 0.25;
      const intersects = ctx.current.raycaster.intersectObjects(pickable);

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
    // ⚠️ **차양·지형면(`Shade`)은 열적 표면이 아니다.** 시뮬레이터는 유효 존이
    // 없다는 이유로 이 면들을 버리는데(`geometry.py` 의 `skipped`), 뷰어는 타입을
    // 안 가려서 그대로 그렸다. 그래서 화면과 계산이 **다른 건물**을 보여줬다:
    // 용호동은 12면뿐이라 지붕 위 판 한 장으로 끝나지만(`su-x-s-235`, 지붕보다
    // 0.33m 위), 회의실은 675면 24,825㎡ 로 IDF 실제 표면적(10,514㎡)의 두 배가
    // 넘는 형상이 화면에만 존재했다.
    // 지우지는 않는다 — 차양은 일사에 실제로 영향을 주므로 **구분해서** 보여준다.
    //
    // ⚠️ 판정 기준을 `type === 'Shade'` 로 두면 안 된다(codex 지적). 백엔드가 면을
    // 버리는 기준은 **타입이 아니라 유효 존에 안 붙었는지**다:
    //   `if z_id == "Unknown" or z_id not in valid_zone_ids: result.skipped += 1`
    // 타입으로 거르면 ① 존이 없는 비-Shade 면은 화면에 남고 ② 존이 붙은 Shade 는
    // 계산에 들어가는데 화면에서 사라진다. 같은 기준을 그대로 쓴다.
    const floorFiltered =
      activeFloor === 'all' ? surfaces : surfaces.filter((s) => s.floor === parseInt(activeFloor));
    const visibleSurfaces = shownExcluded
      ? floorFiltered
      : floorFiltered.filter(inSimulation);

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
            // ⚠️ 첫 세 점의 외적으로 법선을 구하면 **그 셋이 한 직선 위일 때
            // 영벡터**가 되어 일사 방향 판정이 통째로 틀어진다(codex 지적).
            // 실제로 회의실·용호동에 공선 정점이 늘어선 면이 있다.
            // 모든 정점을 쓰는 뉴웰 법선은 그 함정이 없다.
            const n = newellNormal(surf.vertices);
            normal.set(n[0], n[2], -n[1]).normalize();
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
          } else if (!inSimulation(surf)) {
            // ⚠️ 시뮬레이션에 안 들어가는 면이다. 열적 표면과 같은 색으로 그리면
            // 사용자가 계산 대상으로 오해한다 — 중립 회색으로 뺀다.
            baseColor = 0x94a3b8;
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
        // ⚠️ 예전엔 정점 0에서 부채꼴(triangle fan)로 잘랐다. 부채꼴은 볼록
        // 다각형에만 유효해서, 오목한 면은 삼각형이 **바깥으로 삐져나갔다.**
        // 실측(용호동): 235면 중 17면이 어긋났고 최악은 27.8㎡ 가 133.9㎡ 로
        // 그려졌다(+382%). 화면을 가로지르던 긴 대각선이 그 삼각형의 바깥 변이다.
        const built = buildSurfaceGeometry(surf.vertices);
        if (built.triangles.length > 0) {
          geometry = new THREE.BufferGeometry();
          const verticesArray = [];
          for (let i = 0; i < built.triangles.length; i++) {
            const v = surf.vertices[built.triangles[i]];
            verticesArray.push(v[0], v[2], -v[1]);
          }
          geometry.setAttribute('position', new THREE.Float32BufferAttribute(verticesArray, 3));
          geometry.computeVertexNormals();
          mesh = new THREE.Mesh(geometry, material);
        } else {
          // 삼각분할을 **검증하지 못한** 다각형 — 면은 칠하지 않고 윤곽선만 남긴다.
          // ⚠️ 그룹의 직계 자식이어야 클릭 대상이 된다. 아래에서 윤곽선을 직접
          // 그룹에 붙이므로 여기서는 자리만 비운다.
          mesh = null;
        }
      }

      // 삼각분할을 검증하지 못한 면: 면은 없이 **빨간 윤곽선만** 그룹에 직접 붙인다.
      // ⚠️ `userData` 를 실어야 클릭으로 조사할 수 있다 — 문제가 있는 면일수록
      // 사용자가 눌러 봐야 한다.
      if (!mesh && surf.vertices && surf.vertices.length >= 3) {
        const loop = new THREE.BufferGeometry().setFromPoints(
          surf.vertices.map((v) => new THREE.Vector3(v[0], v[2], -v[1]))
        );
        const badLine = new THREE.LineLoop(
          loop, new THREE.LineBasicMaterial({ color: 0xef4444, linewidth: 2 })
        );
        surf.baseColor = 0xef4444;
        badLine.userData = surf;
        badLine.renderOrder = 999;
        group.add(badLine);
      }

      if (mesh) {
        mesh.castShadow = viewMode === 'sunpath' || viewMode === 'thermal';
        mesh.receiveShadow = viewMode === 'sunpath' || viewMode === 'thermal';

        surf.baseColor = baseColor;
        mesh.userData = surf;

        // 경계선 그리기
        //
        // ⚠️ **삼각분할 결과에서 선을 뽑지 않는다.** 예전엔 `EdgesGeometry(geometry)`
        // 였는데, 그러면 그리는 건 열적 표면의 경계가 아니라 mesh 의 삼각형 변이다.
        // 부채꼴이 만든 엉뚱한 삼각형의 바깥 변이 그대로 선으로 나왔다.
        // 우리가 보고 싶은 건 gbXML `PolyLoop` 그 자체이므로 원본 정점으로 그린다.
        const lineMat = new THREE.LineBasicMaterial({
          // ⚠️ 검증 실패 면은 여기 오지 않는다(mesh 가 없어 아래 분기로 빠진다).
          // 예전엔 `malformed ? red : lineColor` 였는데 **항상 false 인 조건**이었다.
          color: lineColor,
          linewidth: isXRayMode ? 2 : 1,
          depthTest: !isXRayMode,
        });
        let line;
        if (surf.vertices && surf.vertices.length >= 3) {
          const loop = new THREE.BufferGeometry().setFromPoints(
            surf.vertices.map((v) => new THREE.Vector3(v[0], v[2], -v[1]))
          );
          line = new THREE.LineLoop(loop, lineMat);
        } else {
          line = new THREE.LineSegments(new THREE.EdgesGeometry(geometry), lineMat);
        }
        if (isXRayMode) line.renderOrder = 999;
        mesh.add(line);

        // 창호 그리기
        const liveWwr = editMode === 'surface' && selectedId === surf.id && draftState ? draftState.wwr : surf.wwr;
        // ⚠️ 상한은 백엔드(`gbxml_parser.py`)와 **같은 값이어야 한다.** 한쪽만
        // 90 이면 화면이 계산과 다른 창을 그린다. 90 → 99 로 함께 올렸다.
        const safeWwr = isNaN(liveWwr) ? 0 : Math.max(0, Math.min(99, liveWwr));

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
          // 실측 창 형상 + WWR 편집 반영: 파싱 원본 비율과 다르게 수정하면
          // 각 창을 자기 중심으로 스케일 (시뮬레이션 build_window_geometries와 동일 규칙)
          const realOps = surf.openings.filter(
            (op) => (op.type || '').toLowerCase() !== 'air' && op.vertices && op.vertices.length >= 3
          );
          const origArea = realOps.reduce((acc, op) => acc + polyArea3D(op.vertices), 0);
          const origPct = surf.area > 0 ? (origArea / surf.area) * 100 : 0;
          let opScale = 1.0;
          if (origPct > 0 && Math.abs(safeWwr - origPct) > 1.5) {
            opScale = Math.sqrt(Math.max(safeWwr, 0.01) / origPct);
          }
          realOps.forEach((op) => {
            {
              // 중심 스케일된 꼭짓점
              const n = op.vertices.length;
              const c = op.vertices.reduce(
                (acc, v) => [acc[0] + v[0] / n, acc[1] + v[1] / n, acc[2] + v[2] / n], [0, 0, 0]);
              const sv = op.vertices.map((v) => [
                c[0] + (v[0] - c[0]) * opScale,
                c[1] + (v[1] - c[1]) * opScale,
                c[2] + (v[2] - c[2]) * opScale,
              ]);
              // ⚠️ 개구부도 같은 삼각분할을 쓴다. 창은 대개 사각형이지만 오목한
              // 개구부가 하나라도 있으면 벽면과 똑같이 삐져나간다(codex 지적).
              const opBuilt = buildSurfaceGeometry(sv);
              if (opBuilt.triangles.length === 0) return;   // 검증 실패한 개구부는 안 그린다
              const opGeom = new THREE.BufferGeometry();
              const opVerts = [];
              for (let i = 0; i < opBuilt.triangles.length; i++) {
                const ov = sv[opBuilt.triangles[i]];
                opVerts.push(ov[0], ov[2], -ov[1]);
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
    // latitude 는 위치 변경 시 태양궤적이 달라지므로 반드시 의존성에 있어야 한다.
    // effectiveDarkMode 는 isDarkMode·readOnly·viewMode 로부터 파생되지만, 린터가
    // 그 관계를 알 수 없으므로 명시한다.
  }, [surfaces, zones, activeFloor, editMode, selectedId, hoveredId, draftState, readOnly, isDarkMode, effectiveDarkMode, viewMode, sunMonth, sunHour, latitude, res, shownExcluded, inSimulation]);

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

      {/* 시뮬레이션 제외 면(차양·지형) 표시 토글 */}
      {(hiddenCount > 0 || shownExcluded) && (
        <div className={`absolute top-16 left-4 z-20 px-3 py-2 rounded-xl shadow-lg backdrop-blur-md border text-xs ${
          effectiveDarkMode ? 'bg-slate-950/80 border-slate-800 text-slate-300' : 'bg-white/80 border-slate-200 text-slate-700'
        }`}>
          <label className="flex items-center gap-2 font-bold cursor-pointer">
            <input
              type="checkbox"
              checked={shownExcluded}
              onChange={(e) => setShownExcluded(e.target.checked)}
            />
            시뮬레이션 제외 면 {hiddenCount}개 표시
          </label>
          <p className="mt-1 font-normal opacity-70">
            유효한 존에 붙지 않아 계산에서 빠진 면입니다 (회색). 차양·지형면이 대부분입니다.
          </p>
        </div>
      )}

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
