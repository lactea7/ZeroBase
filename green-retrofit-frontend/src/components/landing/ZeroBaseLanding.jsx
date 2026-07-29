import React, { useEffect, useRef } from 'react';

// claude.ai/design 프로젝트 "zerobase 웹페이지" / ZeroBase.dc.html 구현.
// 스크롤 연동 히어로(인트로→개요/쾌적성/모델 블록 전환) + 갤러리 / 도면 / 시작 섹션.
// 기본 테마 '감성' (디자인의 CSS 변수 fallback 값이 곧 감성 팔레트라 별도 변수 주입 불필요).
// 원본 히어로의 스크롤 스크럽 영상은 MCP 256KiB 제한으로 가져올 수 없어 정적 배경 이미지로 대체했고,
// 텍스트 전환·스크럽바·진행 점 등 스크롤 연출은 그대로 포팅했다.

const HTML = `
  <div style="position:fixed;top:0;left:0;right:0;height:3px;z-index:300;background:rgba(0,0,0,.18);">
    <div id="zb-scrubbar" style="height:100%;background:var(--zb-accent,#c2734a);transform:scaleX(0);transform-origin:left center;will-change:transform;"></div>
  </div>

  <nav style="position:fixed;top:0;left:0;right:0;z-index:200;padding:18px 7vw;backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);background:linear-gradient(180deg,rgba(26,18,13,.42),rgba(26,18,13,.12));">
    <div style="max-width:1180px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;">
      <a href="#zb-track" style="display:flex;align-items:center;gap:10px;text-decoration:none;">
        <span style="width:9px;height:9px;background:var(--zb-accent,#c2734a);display:inline-block;border-radius:1px;"></span>
        <span style="font-family:'Gowun Batang',serif;font-size:21px;font-weight:700;letter-spacing:.01em;color:#f7f1e8;">Zero<span style="color:var(--zb-eyebrow-color,#e4b48f);">Base</span></span>
      </a>
      <div style="display:flex;align-items:center;gap:30px;">
        <a href="#zb-track" style="font-size:13.5px;letter-spacing:.04em;color:rgba(247,241,232,.82);text-decoration:none;">개요</a>
        <a href="#drawings" style="font-size:13.5px;letter-spacing:.04em;color:rgba(247,241,232,.82);text-decoration:none;">분석</a>
        <a id="zb-cta-start" href="#" style="display:inline-block;font-size:13px;letter-spacing:.05em;color:#1a120d;background:var(--zb-accent,#c2734a);padding:9px 18px;border-radius:2px;text-decoration:none;font-weight:600;cursor:pointer;">시뮬레이션 시작</a>
      </div>
    </div>
  </nav>

  <section id="zb-track" style="position:relative;height:480vh;background:#241a13;">
    <div id="zb-stage" style="position:fixed;top:0;left:0;width:100%;height:100vh;overflow:hidden;z-index:1;">

      <img src="/zerobase/assets/ext1.jpg" alt="" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;filter:contrast(1.06) saturate(1.06);" />
      <video id="zb-video" muted playsinline preload="auto" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;filter:contrast(1.04) saturate(1.04);opacity:0;transition:opacity .6s ease;"></video>

      <div style="position:absolute;inset:0;pointer-events:none;opacity:var(--zb-grid-op,0);background:repeating-linear-gradient(90deg,transparent 0 calc(16.666% - 1px),rgba(255,255,255,.45) calc(16.666% - 1px) 16.666%);"></div>
      <div style="position:absolute;inset:0;pointer-events:none;background:var(--zb-scrim,linear-gradient(180deg,rgba(20,14,10,.58) 0%,rgba(20,14,10,.12) 34%,rgba(20,14,10,.22) 68%,rgba(20,14,10,.62) 100%));"></div>

      <div id="zb-intro" style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:11vh 7vw;will-change:opacity,transform;">
        <div style="max-width:760px;">
          <div style="font-family:'IBM Plex Mono',monospace;font-size:13px;letter-spacing:.32em;text-transform:uppercase;color:var(--zb-eyebrow-color,#e4b48f);margin-bottom:24px;">Building Energy Simulation</div>
          <h1 style="font-family:'Gowun Batang',serif;font-weight:700;font-size:clamp(52px,8vw,120px);line-height:1.02;letter-spacing:-0.015em;color:#f7f1e8;margin:0;">ZeroBase</h1>
          <p style="font-family:'Pretendard',sans-serif;font-size:clamp(16px,1.4vw,21px);line-height:1.7;color:rgba(247,241,232,.86);margin:24px auto 0;max-width:36ch;">건물의 에너지를, 설계의 언어로.<br>gbXML 한 번으로 한 해의 에너지·비용·탄소를 시뮬레이션합니다.</p>
        </div>
      </div>

      <div id="zb-b1" style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:11vh 7vw;opacity:0;transform:translateY(24px);will-change:opacity,transform;">
        <div style="max-width:680px;">
          <div style="font-family:'IBM Plex Mono',monospace;font-size:13px;letter-spacing:.3em;text-transform:uppercase;color:var(--zb-eyebrow-color,#e4b48f);margin-bottom:20px;">01 — Model</div>
          <h2 style="font-family:'Gowun Batang',serif;font-weight:700;font-size:clamp(40px,6vw,92px);line-height:1.08;letter-spacing:-0.01em;color:#f7f1e8;margin:0;">gbXML 한 번이면<br>충분합니다</h2>
          <p style="font-family:'Pretendard',sans-serif;font-size:clamp(15px,1.25vw,19px);line-height:1.78;color:rgba(247,241,232,.82);margin:22px auto 0;max-width:44ch;">Revit·ArchiCAD에서 내보낸 gbXML을 올리면, 존과 외피를 자동으로 인식해 EnergyPlus 에너지 모델로 변환합니다.</p>
          <a href="/gbXML_manual.mp4" target="_blank" rel="noopener" style="display:inline-flex;align-items:center;gap:6px;margin-top:22px;font-family:'IBM Plex Mono',monospace;font-size:12.5px;letter-spacing:.04em;color:var(--zb-eyebrow-color,#e4b48f);text-decoration:none;border-bottom:1px solid rgba(228,180,143,.4);padding-bottom:3px;">▶ Revit 추출 방법 보기</a>
        </div>
      </div>

      <div id="zb-b2" style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:11vh 7vw;opacity:0;transform:translateY(24px);will-change:opacity,transform;">
        <div style="max-width:680px;">
          <div style="font-family:'IBM Plex Mono',monospace;font-size:13px;letter-spacing:.3em;text-transform:uppercase;color:var(--zb-eyebrow-color,#e4b48f);margin-bottom:20px;">02 — Simulation</div>
          <h2 style="font-family:'Gowun Batang',serif;font-weight:700;font-size:clamp(40px,6vw,92px);line-height:1.08;letter-spacing:-0.01em;color:#f7f1e8;margin:0;">한 해 8,760시간을<br>시뮬레이션</h2>
          <p style="font-family:'Pretendard',sans-serif;font-size:clamp(15px,1.25vw,19px);line-height:1.78;color:rgba(247,241,232,.82);margin:22px auto 0;max-width:44ch;">용도별 사용 스케줄을 반영해 냉방·난방·급탕·조명 에너지를 계산하고, 1차에너지와 탄소 배출까지 산출합니다.</p>
        </div>
      </div>

      <div id="zb-b3" style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:11vh 7vw;opacity:0;transform:translateY(24px);will-change:opacity,transform;">
        <div style="max-width:680px;">
          <div style="font-family:'IBM Plex Mono',monospace;font-size:13px;letter-spacing:.3em;text-transform:uppercase;color:var(--zb-eyebrow-color,#e4b48f);margin-bottom:20px;">03 — Economics</div>
          <h2 style="font-family:'Gowun Batang',serif;font-weight:700;font-size:clamp(40px,6vw,92px);line-height:1.08;letter-spacing:-0.01em;color:#f7f1e8;margin:0;">리모델링의 가치를<br>숫자로</h2>
          <p style="font-family:'Pretendard',sans-serif;font-size:clamp(15px,1.25vw,19px);line-height:1.78;color:rgba(247,241,232,.82);margin:22px auto 0;max-width:46ch;">창호·단열·태양광·지열·설비를 바꿔가며 공사비와 생애주기비용(LCC)·회수기간·NPV를, 예산 대비 절감까지 한 번에 비교합니다.</p>
        </div>
      </div>

      <div id="zb-cue" style="position:absolute;bottom:34px;left:50%;transform:translateX(-50%);display:flex;flex-direction:column;align-items:center;gap:10px;pointer-events:none;">
        <span style="font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.34em;color:rgba(247,241,232,.7);">SCROLL</span>
        <span style="display:block;width:1px;height:34px;background:linear-gradient(rgba(247,241,232,.7),rgba(247,241,232,0));animation:zbBounce 1.8s ease-in-out infinite;"></span>
      </div>

      <div style="position:absolute;right:max(7vw,(100vw - 1180px)/2);top:50%;transform:translateY(-50%);display:flex;flex-direction:column;gap:22px;align-items:flex-end;">
        <div style="display:flex;align-items:center;gap:12px;"><span style="font-family:'IBM Plex Mono',monospace;font-size:10.5px;letter-spacing:.18em;color:rgba(247,241,232,.7);">개요</span><span id="zb-dot0" style="width:8px;height:8px;border-radius:50%;background:rgba(255,255,255,.35);transition:transform .3s,background .3s;"></span></div>
        <div style="display:flex;align-items:center;gap:12px;"><span style="font-family:'IBM Plex Mono',monospace;font-size:10.5px;letter-spacing:.18em;color:rgba(247,241,232,.7);">쾌적성</span><span id="zb-dot1" style="width:8px;height:8px;border-radius:50%;background:rgba(255,255,255,.35);transition:transform .3s,background .3s;"></span></div>
        <div style="display:flex;align-items:center;gap:12px;"><span style="font-family:'IBM Plex Mono',monospace;font-size:10.5px;letter-spacing:.18em;color:rgba(247,241,232,.7);">모델</span><span id="zb-dot2" style="width:8px;height:8px;border-radius:50%;background:rgba(255,255,255,.35);transition:transform .3s,background .3s;"></span></div>
      </div>

    </div>
  </section>

  <section id="drawings" style="background:#241a13;padding:130px 7vw;color:#f3ece1;">
    <div style="max-width:1180px;margin:0 auto;">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:12.5px;letter-spacing:.3em;text-transform:uppercase;color:var(--zb-eyebrow-color,#e4b48f);margin-bottom:22px;">Analysis — 04</div>
      <h2 style="font-family:'Gowun Batang',serif;font-weight:700;font-size:clamp(34px,4.6vw,68px);line-height:1.12;letter-spacing:-0.01em;color:#f7f1e8;margin:0;max-width:20ch;">한 모델에서 읽는,<br>한 해의 에너지와 비용</h2>
      <p style="font-family:'Pretendard',sans-serif;font-size:clamp(15px,1.2vw,18px);line-height:1.8;color:rgba(243,236,225,.7);margin:26px 0 50px;max-width:56ch;">gbXML을 올리면 ZeroBase가 층·존·외피를 인식하고, 창호·단열 성능과 열 손실, 개선 효과를 모델 위에 그대로 보여줍니다.</p>

      <div style="position:relative;border-radius:3px;overflow:hidden;border:1px solid rgba(243,236,225,.14);">
        <img src="/zerobase/assets/drawing4.png" alt="건물 단면도" style="display:block;width:100%;object-fit:cover;" />
        <div style="position:absolute;left:50%;top:14%;transform:translate(-50%,0);display:flex;align-items:center;gap:8px;background:rgba(36,26,19,.82);backdrop-filter:blur(4px);padding:7px 12px;border-radius:2px;border:1px solid rgba(226,180,143,.4);">
          <span style="width:7px;height:7px;border-radius:50%;background:var(--zb-accent,#c2734a);"></span>
          <span style="font-family:'IBM Plex Mono',monospace;font-size:11.5px;letter-spacing:.04em;color:#f3ece1;">옥상 · 열 손실 집중 구간</span>
        </div>
        <div style="position:absolute;left:55%;top:46%;display:flex;align-items:center;gap:8px;background:rgba(36,26,19,.82);backdrop-filter:blur(4px);padding:7px 12px;border-radius:2px;border:1px solid rgba(226,180,143,.4);">
          <span style="width:7px;height:7px;border-radius:50%;background:var(--zb-accent,#c2734a);"></span>
          <span style="font-family:'IBM Plex Mono',monospace;font-size:11.5px;letter-spacing:.04em;color:#f3ece1;">공용부 · 비주거 존</span>
        </div>
        <div style="position:absolute;left:14%;top:62%;display:flex;align-items:center;gap:8px;background:rgba(36,26,19,.82);backdrop-filter:blur(4px);padding:7px 12px;border-radius:2px;border:1px solid rgba(226,180,143,.4);">
          <span style="width:7px;height:7px;border-radius:50%;background:var(--zb-accent,#c2734a);"></span>
          <span style="font-family:'IBM Plex Mono',monospace;font-size:11.5px;letter-spacing:.04em;color:#f3ece1;">남측 거실 · 일사 유입</span>
        </div>
      </div>

      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:32px;">
        <div style="border:1px solid rgba(243,236,225,.16);border-radius:3px;padding:24px;">
          <div style="font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:rgba(243,236,225,.55);">Primary Energy</div>
          <div style="font-family:'Gowun Batang',serif;font-size:34px;color:#f7f1e8;margin-top:12px;">132<span style="font-size:15px;color:rgba(243,236,225,.6);"> kWh/m²·yr</span></div>
        </div>
        <div style="border:1px solid rgba(243,236,225,.16);border-radius:3px;padding:24px;">
          <div style="font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:rgba(243,236,225,.55);">냉난방 부하</div>
          <div style="font-family:'Gowun Batang',serif;font-size:34px;color:var(--zb-accent,#c2734a);margin-top:12px;">−24<span style="font-size:15px;color:rgba(243,236,225,.6);"> % 절감</span></div>
        </div>
        <div style="border:1px solid rgba(243,236,225,.16);border-radius:3px;padding:24px;">
          <div style="font-family:'IBM Plex Mono',monospace;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:rgba(243,236,225,.55);">탄소 배출</div>
          <div style="font-family:'Gowun Batang',serif;font-size:34px;color:#f7f1e8;margin-top:12px;">18<span style="font-size:15px;color:rgba(243,236,225,.6);"> kgCO₂/m²</span></div>
        </div>
      </div>
    </div>
  </section>

  <section id="contact" style="background:#f3ece1;padding:150px 7vw;">
    <div style="max-width:760px;margin:0 auto;text-align:center;">
      <div style="font-family:'IBM Plex Mono',monospace;font-size:12.5px;letter-spacing:.3em;text-transform:uppercase;color:var(--zb-accent,#c2734a);margin-bottom:26px;">Get Started</div>
      <h2 style="font-family:'Gowun Batang',serif;font-weight:700;font-size:clamp(36px,5.2vw,76px);line-height:1.1;letter-spacing:-0.015em;color:#2a211b;margin:0;">넷제로를 향한<br>가장 빠른 시뮬레이션</h2>
      <p style="font-family:'Pretendard',sans-serif;font-size:clamp(15px,1.3vw,19px);line-height:1.75;color:#6b5d50;margin:28px auto 40px;max-width:44ch;">gbXML을 올리면 에너지·비용·탄소 분석이 바로 시작됩니다.</p>
      <a id="zb-cta-demo" href="#" style="display:inline-block;font-family:'Pretendard',sans-serif;font-size:15px;letter-spacing:.03em;font-weight:600;color:#1a120d;background:var(--zb-accent,#c2734a);padding:16px 38px;border-radius:2px;text-decoration:none;cursor:pointer;">시뮬레이션 시작</a>
    </div>
    <div style="max-width:1180px;margin:120px auto 0;padding-top:34px;border-top:1px solid rgba(42,33,27,.14);display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px;">
      <div style="display:flex;align-items:center;gap:9px;">
        <span style="width:8px;height:8px;background:var(--zb-accent,#c2734a);display:inline-block;border-radius:1px;"></span>
        <span style="font-family:'Gowun Batang',serif;font-size:18px;font-weight:700;color:#2a211b;">ZeroBase</span>
      </div>
      <span style="font-family:'IBM Plex Mono',monospace;font-size:12px;letter-spacing:.05em;color:#8a7a6b;">Building Energy Simulation · © 2026</span>
    </div>
  </section>
`;

export default function ZeroBaseLanding({ onStart }) {
  const rootRef = useRef(null);

  useEffect(() => {
    const track = document.getElementById('zb-track');
    if (!track) return;

    // ── 스크롤 연동 영상 스크럽 (원본 동작 복원) ──
    // upscaled-video.mp4는 moov atom이 끝에 있어 스트리밍이 멈추므로 blob으로 통째 받아 디코딩한다.
    const v = document.getElementById('zb-video');
    let target = 0, cur = 0, dur = 10, raf = 0;
    if (v) {
      const reveal = () => { v.style.opacity = '1'; };
      ['loadeddata', 'canplay', 'seeked', 'playing'].forEach((ev) => v.addEventListener(ev, reveal));
      v.addEventListener('loadedmetadata', () => { dur = v.duration || 10; });
      fetch('/zerobase/uploads/upscaled-video.mp4')
        .then((r) => r.blob())
        .then((b) => {
          v.src = URL.createObjectURL(b);
          v.load();
          v.play().then(() => { v.pause(); dur = v.duration || 10; reveal(); })
            .catch(() => { try { v.currentTime = 0.04; } catch { /* 시크 불가 상태는 무시 */ } });
        })
        .catch(() => {});
      const kick = () => { if (v.src) { v.play().then(() => { v.pause(); reveal(); }).catch(() => {}); reveal(); } };
      ['scroll', 'wheel', 'pointerdown', 'touchstart', 'keydown'].forEach((ev) =>
        window.addEventListener(ev, kick, { passive: true, once: true }));
    }

    const band = (p, a, b) => {
      const f = 0.06;
      if (p < a - f || p > b + f) return 0;
      if (p < a) return (p - (a - f)) / f;
      if (p > b) return Math.max(0, 1 - (p - b) / f);
      return 1;
    };
    const setP = (id, op, ty) => {
      const el = document.getElementById(id);
      if (el) { el.style.opacity = op; el.style.transform = 'translateY(' + ty + 'px)'; }
    };
    const compute = () => {
      const r = track.getBoundingClientRect();
      const total = track.offsetHeight - window.innerHeight;
      let p = total > 0 ? (-r.top) / total : 0;
      p = Math.max(0, Math.min(1, p));
      target = p;
      const stage = document.getElementById('zb-stage');
      if (stage) {
        const vh = window.innerHeight;
        // 트랙 끝자락에서 스테이지(영상)를 서서히 페이드아웃 → 어두운 배경을 거쳐 도면 섹션으로 부드럽게 연결
        const fade = Math.max(0, Math.min(1, (r.bottom - vh * 0.6) / (vh * 0.85)));
        stage.style.opacity = fade;
        stage.style.display = r.bottom > vh * 0.55 ? 'block' : 'none';
      }
      const introOp = p < 0.04 ? 1 : Math.max(0, 1 - (p - 0.04) / 0.06);
      setP('zb-intro', introOp, introOp < 1 ? -22 * (1 - introOp) : 0);
      const cue = document.getElementById('zb-cue'); if (cue) cue.style.opacity = introOp;
      const b1 = band(p, 0.12, 0.28); setP('zb-b1', b1, (1 - b1) * 26);
      const b2 = band(p, 0.42, 0.64); setP('zb-b2', b2, (1 - b2) * 26);
      const b3 = band(p, 0.78, 0.98); setP('zb-b3', b3, (1 - b3) * 26);
      const active = p < 0.34 ? 0 : (p < 0.74 ? 1 : 2);
      [0, 1, 2].forEach((i) => {
        const d = document.getElementById('zb-dot' + i);
        if (d) {
          d.style.background = i === active ? 'var(--zb-accent,#c2734a)' : 'rgba(255,255,255,.35)';
          d.style.transform = i === active ? 'scale(1.45)' : 'scale(1)';
        }
      });
      const bar = document.getElementById('zb-scrubbar');
      if (bar) bar.style.transform = 'scaleX(' + p + ')';
    };

    window.addEventListener('scroll', compute, { passive: true });
    window.addEventListener('resize', compute);
    compute();

    // 부드러운 추종 루프: 스크롤 진행도(target)로 영상 프레임을 스크럽한다.
    const loop = () => {
      cur += (target - cur) * 0.12;
      if (v && v.readyState >= 1 && !v.seeking) {
        const tt = cur * (dur || 10);
        if (Math.abs((v.currentTime || 0) - tt) > 0.03) { try { v.currentTime = tt; } catch { /* 시크 불가 상태는 무시 */ } }
        if (v.readyState >= 2 && v.style.opacity !== '1') v.style.opacity = '1';
      }
      raf = requestAnimationFrame(loop);
    };
    loop();

    const go = (e) => { e.preventDefault(); if (onStart) onStart(); };
    const c1 = document.getElementById('zb-cta-start');
    const c2 = document.getElementById('zb-cta-demo');
    c1 && c1.addEventListener('click', go);
    c2 && c2.addEventListener('click', go);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener('scroll', compute);
      window.removeEventListener('resize', compute);
      c1 && c1.removeEventListener('click', go);
      c2 && c2.removeEventListener('click', go);
    };
  }, [onStart]);

  return (
    <>
      <style>{`
        @keyframes zbBounce{0%,100%{transform:translateY(0);opacity:.55}50%{transform:translateY(7px);opacity:1}}
        #zb-root ::selection{background:#c2734a;color:#fff;}
        /* 한글이 글자 단위로 끊기지 않고 어절(띄어쓰기) 단위로만 줄바꿈되도록 */
        #zb-root, #zb-root *{word-break:keep-all;overflow-wrap:break-word;}
      `}</style>
      <div
        id="zb-root"
        ref={rootRef}
        style={{
          background: '#1a120d',
          color: '#2a211b',
          fontFamily: "'Pretendard', sans-serif",
          WebkitFontSmoothing: 'antialiased',
          overflowX: 'hidden',
          minHeight: '100vh',
        }}
        dangerouslySetInnerHTML={{ __html: HTML }}
      />
    </>
  );
}
