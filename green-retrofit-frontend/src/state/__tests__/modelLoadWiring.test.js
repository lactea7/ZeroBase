/**
 * 모델 교체 배선 — **소스 수준 계약**.
 *
 * ⚠️ 모델을 갈아끼울 때 편집 세션(`selectedId`·`activeFloor`·초안)도 함께
 * 초기화해야 한다. 안 하면 새 건물에 **이전 건물의 선택이 남는다**(codex 지적).
 *
 * 이 회귀는 렌더 시험으로 잡기 어렵다 — 관측하려면 업로드→설정→3D→평면도까지
 * 들어가 면을 고른 뒤 재업로드해야 해서 시험이 길고 취약해진다. 실제로 화면만
 * 보는 시험을 써 봤더니 배선을 통째로 제거해도 **하나도 안 깨졌다.**
 *
 * 그래서 구조를 직접 검사한다: 모델을 **교체**하는 action 은 반드시
 * `loadModel()` 을 통해야 하고, `loadModel()` 은 세션 초기화를 함께 보낸다.
 */
import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const APP = fs.readFileSync(
  path.join(import.meta.dirname, '..', '..', 'App.jsx'), 'utf8');

/** 모델을 통째로 갈아끼우는 action 들. 편집 세션이 이전 건물을 가리키게 된다. */
const MODEL_REPLACING = ['PARSE_SUCCEEDED', 'SAMPLE_LOADED', 'MODEL_RESET'];

describe('loadModel 배선', () => {
  it('세션 초기화를 함께 보낸다', () => {
    const body = APP.slice(APP.indexOf('const loadModel ='), APP.indexOf('const resetModel ='));
    expect(body).toContain('dispatchModel(action)');
    expect(body).toContain('EditAction.SESSION_RESET');
  });

  it.each(MODEL_REPLACING)(
    '⚠️ %s 는 dispatchModel 로 직접 보내지 않는다', (action) => {
      // 직접 보내면 편집 세션이 이전 건물을 가리킨 채 남는다
      const direct = new RegExp(`dispatchModel\\(\\{[^}]*ModelAction\\.${action}`);
      expect(APP).not.toMatch(direct);
    });

  it.each(MODEL_REPLACING)('%s 가 loadModel 을 거친다', (action) => {
    expect(APP).toMatch(new RegExp(`loadModel\\(\\{[\\s\\S]{0,80}ModelAction\\.${action}`));
  });
});
