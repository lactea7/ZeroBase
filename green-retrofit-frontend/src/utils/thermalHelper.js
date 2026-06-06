import * as THREE from 'three';

export const getRadiationColor = (dotValue, isDarkMode) => {
  if (dotValue <= 0) {
    return isDarkMode ? 0x1e293b : 0x94a3b8; // Shadowed
  }
  if (dotValue < 0.5) {
    const t = dotValue / 0.5;
    const r = Math.round(0x3b + (0xea - 0x3b) * t);
    const g = Math.round(0x82 + (0xb3 - 0x82) * t);
    const b = Math.round(0xf6 + (0x08 - 0xf6) * t);
    return (r << 16) | (g << 8) | b;
  } else {
    const t = (dotValue - 0.5) / 0.5;
    const r = Math.round(0xea + (0xef - 0xea) * t);
    const g = Math.round(0xb3 + (0x44 - 0xb3) * t);
    const b = Math.round(0x08 + (0x44 - 0x08) * t);
    return (r << 16) | (g << 8) | b;
  }
};

export const getTemperatureColor = (temp, isDarkMode) => {
  const minT = -5;
  const maxT = 45;
  const t = Math.max(0, Math.min(1, (temp - minT) / (maxT - minT)));
  
  if (t < 0.5) {
    const factor = t / 0.5;
    const r = Math.round(0x3b + (0xea - 0x3b) * factor);
    const g = Math.round(0x82 + (0xb3 - 0x82) * factor);
    const b = Math.round(0xf6 + (0x08 - 0xf6) * factor);
    return (r << 16) | (g << 8) | b;
  } else {
    const factor = (t - 0.5) / 0.5;
    const r = Math.round(0xea + (0xef - 0xea) * factor);
    const g = Math.round(0xb3 + (0x44 - 0xb3) * factor);
    const b = Math.round(0x08 + (0x44 - 0x08) * factor);
    return (r << 16) | (g << 8) | b;
  }
};

/**
 * 3D 뷰어 표면에 표면 온도 텍스트 라벨 추가
 */
export const drawThermalLabel = (group, surf, {
  sunMonth,
  res,
  effectiveDarkMode,
  size,
  createTextSprite
}) => {
  const thermalData = res?.surfaceThermal?.[surf.id] || res?.result?.surfaceThermal?.[surf.id];
  const tempVal = thermalData?.temperature?.[sunMonth - 1];
  if (tempVal !== undefined && (surf.type === 'Wall' || surf.type === 'ExteriorWall' || surf.type === 'Roof')) {
    const labelText = `${tempVal.toFixed(1)}°C`;
    const sprite = createTextSprite(labelText, effectiveDarkMode);
    
    // Calculate center of surface
    let cx = 0, cy = 0, cz = 0;
    if (surf.width && surf.height && surf.pos) {
      cx = surf.pos.x;
      cy = surf.pos.y;
      cz = surf.pos.z;
    } else if (surf.vertices && surf.vertices.length >= 3) {
      surf.vertices.forEach((v) => {
        cx += v[0];
        cy += v[2];
        cz += -v[1];
      });
      cx /= surf.vertices.length;
      cy /= surf.vertices.length;
      cz /= surf.vertices.length;
    }
    
    // Offset slightly in the direction of the normal vector to avoid overlapping/z-fighting
    let normal = new THREE.Vector3(0, 0, 1);
    if (surf.width && surf.height && surf.rot) {
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
    
    // Move 0.3m outwards
    sprite.position.set(cx + normal.x * 0.3, cy + normal.y * 0.3, cz + normal.z * 0.3);
    
    // Scale dynamically
    const labelWidth = Math.max(1.2, size * 0.14);
    sprite.scale.set(labelWidth, labelWidth * 0.5, 1);
    
    group.add(sprite);
  }
};
