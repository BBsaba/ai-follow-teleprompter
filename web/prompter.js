/* 提词窗渲染器：固定红线 + 逐行跳变 + 行级/字级双染色 */
(() => {
  const stage = document.getElementById('stage');
  const textEl = document.getElementById('text');
  const cueEl = document.getElementById('cue');
  const hintEl = document.getElementById('hint');
  const root = document.documentElement;

  let UI = null;
  let lineEls = [];
  let cur = { line: -1, readIdx: 0, state: 'IDLE' };
  let ws = null;

  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  function effFont() {
    if (!UI) return 64;
    const byWidth = Math.floor((stage.clientWidth * 0.96) / (UI.per_line + 1.2));
    return clamp(
      Math.min(UI.font_px, UI.font_max, byWidth),
      UI.font_min,
      UI.font_max
    );
  }

  function lineH() {
    return effFont() * (UI ? UI.line_height : 1.9);
  }

  /* 红线 y 坐标：按比例给，但不许把「当前行」挤出上边缘 */
  function cueY() {
    if (!UI) return 0;
    const H = stage.clientHeight;
    const want = H * UI.cue_ratio;
    const hi = Math.max(1, H - UI.cue_gap_px);
    const lo = Math.min(lineH() + UI.cue_gap_px, hi);
    return clamp(want, lo, hi);
  }

  function setVars() {
    if (!UI) return;
    const s = root.style;
    s.setProperty('--fs', effFont() + 'px');
    s.setProperty('--lh', String(UI.line_height));
    s.setProperty('--per', String(UI.per_line));
    s.setProperty('--cue', String(UI.cue_ratio));
    s.setProperty('--gap', UI.cue_gap_px + 'px');
    s.setProperty('--thick', UI.cue_thickness + 'px');
    s.setProperty('--bg', UI.bg);
    s.setProperty('--fg', UI.fg);
    s.setProperty('--read', UI.read_color);
    s.setProperty('--red', UI.cue_color);
    s.setProperty('--red2', UI.cue_paused_color);
    document.body.classList.toggle('mirror', !!UI.mirror);
  }

  function build(lines) {
    textEl.innerHTML = '';
    lineEls = (lines || []).map((s) => {
      const row = document.createElement('div');
      row.className = 'line';
      for (const ch of s) {
        const span = document.createElement('span');
        span.className = 'ch';
        span.textContent = ch;
        row.appendChild(span);
      }
      textEl.appendChild(row);
      return row;
    });
  }

  /* 上下渐隐区：只盖住「被屏边切了一半」的那一行，完整行一个字都不碰。
     渐变"实色"分界要落在被切那行的字形边缘上——行盒上下各有半行行距是空的，
     若按行盒算，渐变会有一大半浪费在空白处，字形仍然露出来。 */
  function setFades(idx, curTop, curBot) {
    const H = stage.clientHeight;
    const lh = lineH();
    const half = Math.max(0, (lh - effFont()) / 2);   // 行盒单侧留白
    const mod = (a, b) => ((a % b) + b) % b;
    const solid = (span) => (span > 0 ? clamp((span - half) / span, 0, 1) : 1);

    let fadeT = 0;
    if (curTop >= 0) {
      const top0 = curTop - idx * lh;                 // 第 0 行的顶
      if (top0 < 0) fadeT = mod(top0, lh);            // 被上边切掉那一行的余量
    }
    let fadeB = 0;
    const rest = H - curBot;
    if (rest > 0) fadeB = mod(rest, lh);

    const s = root.style;
    s.setProperty('--fadeT', Math.round(fadeT) + 'px');
    s.setProperty('--fadeB', Math.round(fadeB) + 'px');
    s.setProperty('--fadeTSolid', (solid(fadeT) * 100).toFixed(1) + '%');
    s.setProperty('--fadeBSolid', (solid(fadeB) * 100).toFixed(1) + '%');
  }

  function relayout() {
    const cy = cueY();
    if (UI) cueEl.style.top = cy + 'px';
    if (!UI || !lineEls.length) {
      textEl.style.transform = 'translateX(-50%) translateY(0px)';
      root.style.setProperty('--fadeT', '0px');
      root.style.setProperty('--fadeB', '0px');
      return;
    }
    const i = clamp(cur.line, 0, lineEls.length - 1);
    const el = lineEls[i];
    const lh = lineH();
    const ty = cy - UI.cue_gap_px - (el.offsetTop + lh);
    textEl.style.transform = `translateX(-50%) translateY(${ty}px)`;
    setFades(i, cy - UI.cue_gap_px - lh, cy - UI.cue_gap_px);
  }

  function paint() {
    for (let i = 0; i < lineEls.length; i++) {
      const isCur = i === cur.line;
      lineEls[i].classList.toggle('read', i < cur.line);
      const chars = lineEls[i].children;
      const limit = isCur ? cur.readIdx : 0;
      for (let k = 0; k < chars.length; k++) {
        chars[k].classList.toggle('read', k < limit);
      }
    }
    const paused = cur.state === 'PAUSED';
    cueEl.classList.toggle('paused', paused);
    hintEl.classList.toggle('show', paused);
  }

  function applyPos(p) {
    const lineChanged = p.line !== cur.line;
    cur = p;
    paint();
    if (lineChanged) relayout();
  }

  /* ---------- 尺寸自适应 ---------- */
  let rafId = 0;
  function onResize() {
    if (rafId) return;
    rafId = requestAnimationFrame(() => {
      rafId = 0;
      textEl.classList.add('no-anim');
      setVars();
      relayout();
      requestAnimationFrame(() =>
        requestAnimationFrame(() => textEl.classList.remove('no-anim'))
      );
    });
  }

  new ResizeObserver(onResize).observe(stage);
  window.addEventListener('resize', onResize);
  document.addEventListener('fullscreenchange', () => setTimeout(onResize, 60));

  /* ---------- 通信 ---------- */
  function send(obj) {
    if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj));
  }

  function connect() {
    ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
    ws.onmessage = (ev) => {
      let m;
      try { m = JSON.parse(ev.data); } catch { return; }
      if (m.type === 'init') {
        UI = m.ui;
        setVars();
        build(m.script.lines);
        applyPos(m.pos);
      } else if (m.type === 'script') {
        build(m.script.lines);
        applyPos(cur);
      } else if (m.type === 'ui') {
        UI = m.ui;
        setVars();
        relayout();
      } else if (m.type === 'pos') {
        applyPos(m.pos);
      }
    };
    ws.onclose = () => setTimeout(connect, 400);
  }

  /* ---------- 录制态输入：空格 / Esc / 滚轮 ---------- */
  window.addEventListener('keydown', (e) => {
    if (e.code === 'Space') {
      e.preventDefault();
      if (cur.state === 'IDLE') send({ type: 'start' });
      else send({ type: 'pause' });
    } else if (e.code === 'Escape') {
      e.preventDefault();
      send({ type: 'stop' });
    } else if (e.ctrlKey || e.metaKey || e.altKey) {
      e.preventDefault();
    }
  });

  let acc = 0;
  let lockUntil = 0;
  window.addEventListener('wheel', (e) => {
    if (cur.state === 'IDLE') return;
    e.preventDefault();
    const now = performance.now();
    if (now < lockUntil) return;
    acc += e.deltaY;
    if (Math.abs(acc) >= 40) {
      const dir = acc > 0 ? 1 : -1;   // 向下滚 = 下一行
      acc = 0;
      lockUntil = now + 50;
      send({ type: 'wheel', delta: dir });
    }
  }, { passive: false });

  connect();
})();
