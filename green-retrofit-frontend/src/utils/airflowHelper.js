import * as THREE from 'three';

/**
 * 3D 자연환기 기류 화살표 및 풍량 배지 시뮬레이션 드로잉
 */
export const drawAirflowVisuals = (group, surf, {
  sunMonth,
  res,
  effectiveDarkMode,
  size,
  createTextSprite
}) => {
  const airflowData = res?.surfaceAirflow?.[surf.id] || res?.result?.surfaceAirflow?.[surf.id];
  if (airflowData && (airflowData.inflow || airflowData.outflow)) {
    const inflowVal = airflowData.inflow?.[sunMonth - 1] ?? 0.0;
    const outflowVal = airflowData.outflow?.[sunMonth - 1] ?? 0.0;
    
    if (inflowVal > 0.01 || outflowVal > 0.01) {
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
      
      // Normal vector
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

      const isInflow = inflowVal > outflowVal;
      const flowRate = isInflow ? inflowVal : outflowVal;
      const arrowColor = isInflow ? 0x0ea5e9 : 0xf97316;
      const textStroke = isInflow ? '#0ea5e9' : '#f97316';
      const textColor = isInflow ? '#38bdf8' : '#fb923c';
      const labelText = isInflow ? `IN: ${inflowVal.toFixed(1)}` : `OUT: ${outflowVal.toFixed(1)}`;
      
      // Arrow length proportional to flow rate, min 1.0, max 5.0
      const arrowLength = Math.max(1.0, Math.min(5.0, 1.0 + (flowRate / 15.0)));
      
      let arrowDir, arrowOrigin;
      if (isInflow) {
        // Inflow: points towards the window (inward)
        arrowDir = normal.clone().negate().normalize();
        // Starts outside
        arrowOrigin = new THREE.Vector3(
          cx + normal.x * (arrowLength + 0.1),
          cy + normal.y * (arrowLength + 0.1),
          cz + normal.z * (arrowLength + 0.1)
        );
      } else {
        // Outflow: points away from the window (outward)
        arrowDir = normal.clone().normalize();
        // Starts just outside the surface
        arrowOrigin = new THREE.Vector3(
          cx + normal.x * 0.1,
          cy + normal.y * 0.1,
          cz + normal.z * 0.1
        );
      }

      const arrowHelper = new THREE.ArrowHelper(
        arrowDir,
        arrowOrigin,
        arrowLength,
        arrowColor,
        arrowLength * 0.25,
        arrowLength * 0.15
      );
      group.add(arrowHelper);

      // Sprite label
      const sprite = createTextSprite(labelText, effectiveDarkMode, textStroke, textColor);
      const labelOffset = arrowLength + 0.5;
      sprite.position.set(
        cx + normal.x * labelOffset,
        cy + normal.y * labelOffset,
        cz + normal.z * labelOffset
      );
      
      const labelWidth = Math.max(1.4, size * 0.15);
      sprite.scale.set(labelWidth, labelWidth * 0.5, 1);
      group.add(sprite);
    }
  }
};
