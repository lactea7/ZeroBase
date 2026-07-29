import * as THREE from 'three';

export const REGION_LATITUDES = {
  // 특별시 및 광역시
  KOR_SO_Seoul: 37.56,
  KOR_PU_Busan: 35.18,
  KOR_TG_Daegu: 35.87,
  KOR_IN_Incheon: 37.45,
  KOR_KJ_Gwangju: 35.16,
  KOR_TJ_Daejeon: 36.35,
  KOR_UL_Ulsan: 35.54,
  // 경기도
  KOR_KG_Suwon: 37.26,
  KOR_KG_Paju: 37.76,
  KOR_KG_Pyeongtaek: 37.00,
  KOR_KG_Dongducheon: 37.90,
  KOR_KG_Icheon: 37.28,
  KOR_KG_Osan: 37.15,
  KOR_KG_Gapyeong: 37.83,
  KOR_KG_Yeoju: 37.30,
  // 강원도
  KOR_KW_Chuncheon: 37.88,
  KOR_KW_Wonju: 37.34,
  KOR_KW_Gangneung: 37.75,
  KOR_KW_Sokcho: 38.20,
  KOR_KW_Taebaek: 37.16,
  KOR_KW_Daegwallyeong: 37.67,
  // 충청도
  KOR_HB_Cheongju: 36.64,
  KOR_HN_Cheonan: 36.81,
  KOR_HN_Boryeong: 36.35,
  KOR_HN_Gongju: 36.45,
  KOR_HN_Seosan: 36.78,
  // 경상도
  KOR_KB_Pohang: 36.02,
  KOR_KB_Gumi: 36.12,
  KOR_KB_Andong: 36.56,
  KOR_KB_Ulleungdo: 37.48,
  KOR_KN_Changwon: 35.23,
  KOR_KN_Jinju: 35.18,
  KOR_KN_Tongyeong: 34.85,
  // 전라도 및 제주
  KOR_CB_Jeonju: 35.82,
  KOR_CB_Gunsan: 35.97,
  KOR_CN_Mokpo: 34.81,
  KOR_CN_Yeosu: 34.76,
  KOR_CN_Suncheon: 34.95,
  KOR_CJ_Jeju: 33.49,
  KOR_CJ_Seogwipo: 33.25,
};

export const getSolarPosition = (lat, month, hour) => {
  const latitudeRad = (lat * Math.PI) / 180;
  const day = (month - 1) * 30 + 15;
  const declination = 23.45 * Math.sin((2 * Math.PI * (284 + day)) / 365);
  const declinationRad = (declination * Math.PI) / 180;
  const hourAngle = (hour - 12) * 15;
  const hourAngleRad = (hourAngle * Math.PI) / 180;
  const sinAlt = Math.sin(latitudeRad) * Math.sin(declinationRad) +
                 Math.cos(latitudeRad) * Math.cos(declinationRad) * Math.cos(hourAngleRad);
  const altitudeRad = Math.asin(Math.max(-1, Math.min(1, sinAlt)));
  let azimuthRad = 0;
  if (Math.cos(altitudeRad) > 0.0001) {
    const cosAz = (Math.sin(declinationRad) - Math.sin(latitudeRad) * Math.sin(altitudeRad)) /
                  (Math.cos(latitudeRad) * Math.cos(altitudeRad));
    azimuthRad = Math.acos(Math.max(-1, Math.min(1, cosAz)));
    if (hour > 12) {
      azimuthRad = 2 * Math.PI - azimuthRad;
    }
  } else {
    azimuthRad = hour > 12 ? Math.PI * 1.5 : Math.PI * 0.5;
  }
  return { altitude: altitudeRad, azimuth: azimuthRad };
};

/**
 * 태양 궤적 돔을 렌더링하고 관련 요소를 group에 추가
 */
export const drawSunPathDome = (group, {
  R,
  minY,
  centerY,
  centerZ,
  centerX,
  latitude,
  sunMonth,
  size,
  effectiveDarkMode,
  localSunX,
  localSunY,
  localSunZ,
  sunPos
}) => {
  // 그림자 수수용 Ground Plane
  const groundGeom = new THREE.PlaneGeometry(R * 4, R * 4);
  const groundMat = new THREE.MeshStandardMaterial({
    color: effectiveDarkMode ? 0x1e293b : 0xf1f5f9,
    roughness: 0.9,
    metalness: 0.1,
  });
  const ground = new THREE.Mesh(groundGeom, groundMat);
  ground.rotation.x = -Math.PI / 2;
  ground.position.set(centerX, minY - 0.05, centerZ);
  ground.receiveShadow = true;
  group.add(ground);

  // 방위각 원판 (Compass)
  const compassGeom = new THREE.RingGeometry(R * 0.99, R * 1.01, 64);
  const compassMat = new THREE.MeshBasicMaterial({
    color: effectiveDarkMode ? 0x475569 : 0x94a3b8,
    side: THREE.DoubleSide
  });
  const compass = new THREE.Mesh(compassGeom, compassMat);
  compass.rotation.x = Math.PI / 2;
  compass.position.set(centerX, minY - 0.03, centerZ);
  group.add(compass);

  // 북향 화살표 가이드 (Red Arrow)
  const northArrowGeom = new THREE.BufferGeometry();
  const arrowPts = new Float32Array([
    centerX, minY - 0.02, centerZ - R * 1.06,
    centerX - size * 0.08, minY - 0.02, centerZ - R * 0.97,
    centerX + size * 0.08, minY - 0.02, centerZ - R * 0.97,
  ]);
  northArrowGeom.setAttribute('position', new THREE.BufferAttribute(arrowPts, 3));
  const northArrowMat = new THREE.MeshBasicMaterial({ color: 0xef4444, side: THREE.DoubleSide });
  const northArrow = new THREE.Mesh(northArrowGeom, northArrowMat);
  group.add(northArrow);

  // 월별 궤적 선분 그리기 (1, 3, 6, 9, 12월)
  const monthsToDraw = [1, 3, 6, 9, 12];
  monthsToDraw.forEach((m) => {
    const points = [];
    for (let h = 5.0; h <= 19.0; h += 0.25) {
      const pos = getSolarPosition(latitude, m, h);
      if (pos.altitude >= -0.05) {
        const sy = R * Math.sin(pos.altitude) + (minY - 0.03);
        const sz = -R * Math.cos(pos.altitude) * Math.cos(pos.azimuth) + centerZ;
        const sx = R * Math.cos(pos.altitude) * Math.sin(pos.azimuth) + centerX;
        points.push(new THREE.Vector3(sx, sy, sz));
      }
    }
    if (points.length >= 2) {
      const curve = new THREE.CatmullRomCurve3(points);
      const curvePoints = curve.getPoints(50);
      const pathGeom = new THREE.BufferGeometry().setFromPoints(curvePoints);
      const pathMat = new THREE.LineBasicMaterial({
        color: m === sunMonth ? 0xf59e0b : (effectiveDarkMode ? 0x334155 : 0xcbd5e1),
        linewidth: m === sunMonth ? 2 : 1,
        transparent: true,
        opacity: m === sunMonth ? 0.9 : 0.4
      });
      const pathLine = new THREE.Line(pathGeom, pathMat);
      group.add(pathLine);
    }
  });

  // 시간대별 점선 가이드 (8, 10, 12, 14, 16, 18시)
  const hoursToDraw = [8, 10, 12, 14, 16, 18];
  hoursToDraw.forEach((h) => {
    const points = [];
    for (let m = 1; m <= 12; m++) {
      const pos = getSolarPosition(latitude, m, h);
      if (pos.altitude >= -0.05) {
        const sy = R * Math.sin(pos.altitude) + (minY - 0.03);
        const sz = -R * Math.cos(pos.altitude) * Math.cos(pos.azimuth) + centerZ;
        const sx = R * Math.cos(pos.altitude) * Math.sin(pos.azimuth) + centerX;
        points.push(new THREE.Vector3(sx, sy, sz));
      }
    }
    if (points.length >= 2) {
      const curve = new THREE.CatmullRomCurve3(points);
      const curvePoints = curve.getPoints(30);
      const hourGeom = new THREE.BufferGeometry().setFromPoints(curvePoints);
      const hourMat = new THREE.LineDashedMaterial({
        color: effectiveDarkMode ? 0x334155 : 0xcbd5e1,
        dashSize: 0.5,
        gapSize: 0.5,
        transparent: true,
        opacity: 0.3
      });
      const hourLine = new THREE.Line(hourGeom, hourMat);
      hourLine.computeLineDistances();
      group.add(hourLine);
    }
  });

  // 현재 구체 태양 및 광선 표시
  if (sunPos && sunPos.altitude >= -0.05) {
    const sunGeom = new THREE.SphereGeometry(size * 0.06, 16, 16);
    const sunMat = new THREE.MeshBasicMaterial({ color: 0xfdb813 });
    const sunMesh = new THREE.Mesh(sunGeom, sunMat);
    sunMesh.position.set(localSunX, localSunY, localSunZ);
    group.add(sunMesh);

    const rayGeom = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(localSunX, localSunY, localSunZ),
      new THREE.Vector3(centerX, centerY, centerZ)
    ]);
    const rayMat = new THREE.LineBasicMaterial({
      color: 0xf59e0b,
      transparent: true,
      opacity: 0.4
    });
    const rayLine = new THREE.Line(rayGeom, rayMat);
    group.add(rayLine);
  }
};
