import * as THREE from 'three';

/**
 * Canvas 기반 3D 텍스트 배지(Sprite) 생성 함수
 */
export const createTextSprite = (text, isDarkMode, strokeColor = '#10B981', textColor = '#34D399') => {
  const canvas = document.createElement('canvas');
  canvas.width = 128;
  canvas.height = 64;
  const ctx = canvas.getContext('2d');
  
  ctx.fillStyle = 'rgba(15, 23, 42, 0.9)';
  ctx.strokeStyle = strokeColor;
  ctx.lineWidth = 3;
  
  const x = 4;
  const y = 4;
  const w = canvas.width - 8;
  const h = canvas.height - 8;
  const r = 12;
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  
  ctx.fillStyle = textColor;
  ctx.font = 'bold 22px Inter, system-ui, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, canvas.width / 2, canvas.height / 2);
  
  const texture = new THREE.CanvasTexture(canvas);
  const spriteMaterial = new THREE.SpriteMaterial({ 
    map: texture,
    transparent: true,
    depthTest: true
  });
  const sprite = new THREE.Sprite(spriteMaterial);
  return sprite;
};

/**
 * Three.js 노드 리소스 해제 유틸
 */
export const disposeNode = (node) => {
  if (node.geometry) node.geometry.dispose();
  if (node.material) {
    if (Array.isArray(node.material)) {
      node.material.forEach((m) => {
        if (m.map) m.map.dispose();
        m.dispose();
      });
    } else {
      if (node.material.map) node.material.map.dispose();
      node.material.dispose();
    }
  }
};

/**
 * Group 안의 모든 자식을 순회하면서 리소스 메모리를 해제하고 비움
 */
export const clearGroup = (group) => {
  while (group.children.length > 0) {
    const obj = group.children[0];
    obj.traverse(disposeNode);
    group.remove(obj);
  }
};
