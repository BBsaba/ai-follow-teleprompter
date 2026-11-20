/* 控制台：稿件编辑 / 参数调节 / 提词窗联动 */
(() => {
  const $ = (id) => document.getElementById(id);
  const textEl = $('text');
  const selEl = $('scripts');
  const saveEl = $('saveState');
  const statEl = $('stats');
  const clampEl = $('clampHint');
  const modeEl = $('modeTag');
  const btnStart = $('btnStart');
  const btnMirror = $('btnMirror');

  let UI = null;
  let curId = null;
  let ws = null;
  let runState = 'IDLE';
  let asrOn = false;
  let asrState = null;        // 最近一次完整的状态对象（引擎/是否在听/最后识别时间）
  let quitting = false;       // 按过「退出程序」之后不再重连 WS
  let lastAlignAt = 0;        // 最后一次"对齐成功"的时间戳
  let lastConf = 0;           // 最后一次对齐的置信度
  let saveTimer = 0;
  let putTimer = 0;
  let pending = {};

  const api = async (path, opts) => {
    const r = await fetch(path, opts);
    return r.json();
  };
  const json = (body) => ({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  /* ---------- 统计 ---------- */
  function updateStats(chars, lines) {
    const sec = Math.round(chars / 4.2);
    const mm = Math.floor(sec / 60);
    const ss = String(sec % 60).padStart(2, '0');
    statEl.textContent = `${chars} 字 · ${lines} 行 · 约 ${mm} 分 ${ss} 秒`;
  }

  function updateClamp() {
    if (!UI) return;
    const byWidth = Math.floor((1920 * 0.96) / (UI.per_line + 1.2));
    clampEl.textContent = UI.font_px > byWidth ? `实际字号被预览宽度限制为 ${byWidth} px` : '';
  }

  /* ---------- 控件同步 ---------- */
  /* 0 是「不限」这一档，不是「0 行」—— 后者读不通，也是这个滑块唯一需要额外解释的取值 */
  const fmtJump = (v) => (Number(v) === 0 ? '不限' : v + ' 行');

  function syncControls() {
    if (!UI) return;
    $('rFont').min = UI.font_min;
    $('rFont').max = UI.font_max;
    $('rFont').value = UI.font_px;
    $('rPer').min = UI.per_line_min;
    $('rPer').max = UI.per_line_max;
    $('rPer').value = UI.per_line;
    $('rCue').min = Math.round(UI.cue_ratio_min * 100);
    $('rCue').max = Math.round(UI.cue_ratio_max * 100);
    $('rCue').value = Math.round(UI.cue_ratio * 100);
    $('rCps').min = 1;
    $('rCps').max = 10;
    $('rCps').value = UI.cps;
    $('rJump').min = UI.max_jump_lines_min;
    $('rJump').max = UI.max_jump_lines_max;
    $('rJump').value = UI.max_jump_lines;

    $('oFont').textContent = UI.font_px + ' px';
    $('oPer').textContent = UI.per_line + ' 字';
    $('oCue').textContent = Math.round(UI.cue_ratio * 100) + '%';
    $('oCps').textContent = Number(UI.cps).toFixed(1) + ' 字/秒';
    $('oJump').textContent = fmtJump(UI.max_jump_lines);
    btnMirror.textContent = UI.mirror ? '镜像 开' : '镜像 关';
    updateClamp();
    syncMode();
  }

  /* ---------- 推进方式：自动滚动 / AI 跟随 ----------
     两者互斥，同一个时刻只有一方能改位置（后端 session.mode 说了算）。
     速度滑块只在自动滚动下有意义，AI 模式下直接置灰，免得看着以为还在按速度走。 */
  function isAiMode() {
    return !!UI && UI.follow_mode === 'ai';
  }

  function syncMode() {
    if (!UI) return;
    const ai = isAiMode();
    $('btnModeAuto').classList.toggle('on', !ai);
    $('btnModeAi').classList.toggle('on', ai);

    const rCps = $('rCps');
    if (rCps) rCps.disabled = ai || runState !== 'IDLE';
    // AI 模式下这个数字没有意义，留着会让人以为还按速度走
    const oCps = $('oCps');
    if (oCps && UI) {
      oCps.textContent = ai ? '不用' : Number(UI.cps).toFixed(1) + ' 字/秒';
    }

    // 「最大跟进」正好反过来：只对 AI 跟随有意义，自动滚动下置灰。
    // 两个滑块永远是"一个亮一个灰"，本身就把"当前哪个模式在起作用"说清楚了。
    const rJump = $('rJump');
    if (rJump) rJump.disabled = !ai || runState !== 'IDLE';
    const oJump = $('oJump');
    if (oJump && UI) {
      oJump.textContent = ai ? fmtJump(UI.max_jump_lines) : '不用';
    }

    const note = $('modeNote');
    if (note) {
      // 这里只说"这个模式的规则"，"现在到底在不在听"交给下面的动态状态条。
      // 两处都写状态必然打架（加载中这里还写着"要先开麦克风"，实际已经在开了）。
      note.innerHTML = ai
        ? 'AI 跟随：<b>只在念到稿子时推进</b>，不说话就不动。'
        : '自动滚动：按「速度」匀速推进，不用麦克风。';
    }
    syncAiStatus();
  }

  /* ---------- AI 跟随运行状态 ----------
     用户从外面分不清「稿子不动」是因为没在念、没开麦、还是程序坏了。
     这一行把四种情况说开：没启动 / 加载中 / 在听但没听到 / 听到了但对不上稿子。 */
  const esc = (s) => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const shortText = (s) => {
    const t = String(s || '').replace(/\s+/g, '');
    return t.length > 18 ? '…' + t.slice(-18) : t;
  };

  function syncAiStatus() {
    const el = $('aiStatus');
    if (!el) return;
    if (!isAiMode()) { el.hidden = true; return; }
    el.hidden = false;

    const a = asrState || {};
    const eng = a.engine || {};
    const set = (cls, html) => {
      const k = cls + '|' + html;
      if (el.dataset.k === k) return;     // 内容没变就别动 DOM，500 ms 刷一次也不心疼
      el.dataset.k = k;
      el.className = 'ai-status ' + cls;
      el.innerHTML = html;
    };

    if (a.error) {
      set('err', `✕ <b>出错了</b>：${esc(a.error)}`);
      return;
    }
    if (a.loading && !eng.ready) {
      set('load', runState === 'RUNNING'
        ? '⏳ <b>正在加载语音引擎</b>（首次约 10–20 秒）… 加载完会自动跟上，<b>不用重新点开始</b>。'
        : '⏳ <b>正在加载语音引擎</b>（首次约 10–20 秒）…');
      return;
    }
    if (!a.on) {
      // 侧栏只有 380 px，这条要压到一行——「开启麦克风」按钮就在正下方，不用指路
      set('off', '⚠️ <b>麦克风没开</b> —— 点「开始」会自动开麦。');
      return;
    }
    if (!eng.ready) {
      set('load', '⏳ 麦克风已开，模型仍在加载…');
      return;
    }

    // 引擎就绪且在听 —— 再判断"到底收到声音没有"
    const lastAt = Number(a.last_at || 0);
    const quiet = lastAt ? (Date.now() / 1000 - lastAt) : 999;
    const level = Number(a.level || 0);
    const alignAgo = lastAlignAt ? (Date.now() - lastAlignAt) / 1000 : 999;

    if (!lastAt || quiet > 6) {
      set('warn', '🎤 <b>在听，但还没听到你说话</b> —— 看上面那条音量（VU）有没有在动；'
        + (level > 0.02 ? '有反应说明麦克风正常，直接念稿即可。'
                        : '一直不动就是麦克风没声、被静音或选错了设备。'));
      return;
    }
    if (alignAgo > 4) {
      set('warn', `🎧 <b>听到了，但对不上稿子</b>：「${esc(shortText(a.latest))}」`
        + '<br>多半是念的位置离当前行太远 —— 用滚轮把当前行拨到正在念的地方。');
      return;
    }
    set('live', `✅ <b>跟随中</b> · 置信度 ${Number(lastConf || 0).toFixed(2)}`
      + ` · 最近识别 ${quiet < 1 ? '刚刚' : quiet.toFixed(0) + ' 秒前'}`);
  }

  function setFollowMode(mode) {
    if (!UI) return;
    UI.follow_mode = mode;
    syncMode();
    pushPatch({ follow_mode: mode });
  }

  $('btnModeAuto').addEventListener('click', () => setFollowMode('auto'));
  $('btnModeAi').addEventListener('click', () => setFollowMode('ai'));

  function setControlsEnabled(on) {
    ['rFont', 'rPer', 'rCue', 'rJump', 'btnMirror', 'btnNew', 'btnImport', 'btnDel'].forEach((id) => {
      const el = $(id);
      if (el) el.disabled = !on;
    });
    selEl.disabled = !on;
    textEl.readOnly = !on;
    syncMode();          // 速度滑块由 syncMode 统一裁决（ai 模式下永远不可用）
  }

  function setMode(state) {
    runState = state;
    modeEl.textContent = state === 'RUNNING' ? '跟读中' : state === 'PAUSED' ? '已暂停' : '待机';
    modeEl.className = 'tag ' + (state === 'RUNNING' ? 'running' : state === 'PAUSED' ? 'paused' : '');
    btnStart.textContent = state === 'IDLE' ? '开始' : '停止';
    setControlsEnabled(state === 'IDLE');
  }

  /* ---------- 参数下发 ---------- */
  function pushPatch(patch) {
    Object.assign(pending, patch);
    clearTimeout(putTimer);
    putTimer = setTimeout(async () => {
      const body = pending;
      pending = {};
      await api('/api/state', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    }, 60);
  }

  function bindRange(id, key, out, fmt) {
    $(id).addEventListener('input', (e) => {
      const v = Number(e.target.value);
      UI[key] = key === 'cue_ratio' ? v / 100 : v;
      $(out).textContent = fmt(v);
      if (key === 'per_line') updateClamp();
      pushPatch({ [key]: UI[key] });
    });
  }

  bindRange('rFont', 'font_px', 'oFont', (v) => v + ' px');
  bindRange('rPer', 'per_line', 'oPer', (v) => v + ' 字');
  bindRange('rCue', 'cue_ratio', 'oCue', (v) => v + '%');
  bindRange('rCps', 'cps', 'oCps', (v) => Number(v).toFixed(1) + ' 字/秒');
  bindRange('rJump', 'max_jump_lines', 'oJump', fmtJump);

  /* ---------- 稿件 ---------- */
  async function loadScriptList() {
    const d = await api('/api/scripts');
    selEl.innerHTML = '';
    for (const it of d.items) {
      const o = document.createElement('option');
      o.value = it.id;
      o.textContent = it.title;
      selEl.appendChild(o);
    }
    if (!curId || !d.items.some((i) => i.id === curId)) curId = d.items[0]?.id;
    selEl.value = curId;
  }

  async function loadText(id) {
    const d = await api('/api/scripts/' + encodeURIComponent(id));
    textEl.value = d.text;
    curId = id;
  }

  async function saveScript() {
    if (!curId) return;
    saveEl.textContent = '保存中…';
    saveEl.className = 'save';
    const r = await api('/api/scripts', json({ id: curId, text: textEl.value }));
    saveEl.textContent = '已保存';
    saveEl.className = 'save ok';
    updateStats(r.chars, r.n_lines);
  }

  function onEdit() {
    saveEl.textContent = '编辑中…';
    saveEl.className = 'save';
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveScript, 800);
  }

  textEl.addEventListener('input', onEdit);
  textEl.addEventListener('blur', () => {
    clearTimeout(saveTimer);
    saveScript();
  });

  selEl.addEventListener('change', async () => {
    await saveScript();
    await loadText(selEl.value);
    await saveScript();
    saveEl.textContent = '已保存';
  });

  $('btnNew').addEventListener('click', async () => {
    const name = (prompt('新稿件名称：') || '').trim();
    if (!name) return;
    await api('/api/scripts', json({ id: name, text: '' }));
    await loadScriptList();
    await loadText(name);
    await saveScript();
  });

  $('btnImport').addEventListener('click', () => $('file').click());

  /* 删除当前稿件。删之前把字数和名字都摆出来——这个动作不可撤销，
     只弹一句"确定吗"不足以让人看清自己删的是哪一篇。 */
  $('btnDel').addEventListener('click', async () => {
    if (!curId) return;
    const chars = textEl.value.replace(/\s/g, '').length;
    if (!confirm(`删除稿件「${curId}」？\n\n共 ${chars} 字，删掉之后找不回来。`)) return;

    const btn = $('btnDel');
    btn.disabled = true;
    try {
      const r = await fetch('/api/scripts/' + encodeURIComponent(curId), { method: 'DELETE' });
      const d = await r.json();
      if (!r.ok || !d.ok) {
        alert(d.error || `删除失败（HTTP ${r.status}）`);
        return;
      }
      curId = d.current || (d.items[0] && d.items[0].id) || null;
      await loadScriptList();
      if (curId) {
        await loadText(curId);
        await saveScript();          // 顺带把字数/行数刷新掉
      } else {
        textEl.value = '';
        updateStats(0, 0);
      }
      saveEl.textContent = '已删除';
      saveEl.className = 'save ok';
    } catch (e) {
      alert('删除失败：' + e);
    } finally {
      btn.disabled = false;
    }
  });
  $('file').addEventListener('change', async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const text = await f.text();
    const name = f.name.replace(/\.[^.]+$/, '');
    await api('/api/scripts', json({ id: name, text }));
    await loadScriptList();
    await loadText(name);
    await saveScript();
    e.target.value = '';
  });

  /* ---------- 运行控制 ---------- */
  function send(obj) {
    if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj));
  }

  btnStart.addEventListener('click', () => {
    send({ type: runState === 'IDLE' ? 'start' : 'stop' });
  });

  btnMirror.addEventListener('click', () => {
    UI.mirror = !UI.mirror;
    btnMirror.textContent = UI.mirror ? '镜像 开' : '镜像 关';
    pushPatch({ mirror: UI.mirror });
  });

  /* ---------- 语音识别 ---------- */
  function renderAsr(a) {
    if (!a) return;
    asrState = a;
    const eng = a.engine || {};
    asrOn = !!a.on;
    const chip = $('asrChip');
    const btn = $('btnAsr');

    if (a.loading && !a.on) {
      // 加载模型这十几秒必须显式说出来，否则和"卡死"没区别
      chip.textContent = eng.ready ? '开麦中…' : '加载模型…';
      chip.className = 'chip load';
    } else if (a.on && eng.ready) {
      chip.textContent = '识别中';
      chip.className = 'chip on';
    } else if (a.on) {
      chip.textContent = '加载模型…';
      chip.className = 'chip load';
    } else {
      chip.textContent = '未开启';
      chip.className = 'chip';
    }

    btn.classList.toggle('on', a.on);
    btn.textContent = a.on ? '关闭麦克风' : '开启麦克风';
    btn.disabled = !!a.loading;

    if (eng.ready) {
      const rtf = eng.rtf ? `RTF ${eng.rtf}` : '—';
      $('asrDev').textContent = `${eng.device} · ${eng.dtype} · 加载 ${(eng.load_ms / 1000).toFixed(1)}s`;
      $('asrRtf').textContent = eng.last_ms
        ? `${eng.last_ms} ms / ${rtf}`
        : rtf;
    } else {
      $('asrDev').textContent = a.loading || a.on
        ? '正在加载模型（首次约 10–30 秒）…'
        : '—';
      $('asrRtf').textContent = '—';
    }
    if (a.latest) $('asrText').textContent = a.latest;
    $('asrErr').textContent = a.error || '';
    syncMode();
  }

  function renderVu(v) {
    const pct = Math.min(100, Math.round(Math.pow(v.level || 0, 0.5) * 100));
    $('vuBar').style.width = pct + '%';
  }

  /* 跟随状态：置信度 + 这一拍挪了几个字。
     低于门限的对齐器会自己丢掉，所以这里"没动静"通常不是故障，
     而是用户没在念稿（或念的内容和稿子对不上）。 */
  function renderAlign(al) {
    if (!al) return;
    const el = $('asrAlign');
    if (!el) return;
    lastAlignAt = Date.now();
    const conf = Number(al.conf || 0);
    lastConf = conf;
    const d = Number(al.delta || 0);
    const sign = d > 0 ? `+${d}` : String(d);
    el.textContent = `跟随中 · 置信度 ${conf.toFixed(2)} · ${sign} 字`;
    el.className = 'asr-align ' + (conf >= 0.70 ? 'ok' : 'warn');
    syncAiStatus();
  }

  function renderAlignIdle() {
    const el = $('asrAlign');
    if (!el) return;
    if (!asrOn) {
      el.textContent = '未跟随';
      el.className = 'asr-align';
    } else if (Date.now() - lastAlignAt > 2500) {
      el.textContent = '未跟上 —— 在等你念稿';
      el.className = 'asr-align';
    }
  }
  setInterval(() => {
    if (quitting) return;                 // 已经退出了，别再刷新一堆没人看的状态
    renderAlignIdle();
    syncAiStatus();       // "多久没听到"要随时间走，不能只在收到消息时才算
  }, 500);

  $('btnAsr').addEventListener('click', async () => {
    const btn = $('btnAsr');
    btn.disabled = true;
    btn.textContent = asrOn ? '正在关闭…' : '正在启动（首次要加载模型）…';
    try {
      const d = await api('/api/asr', { method: 'POST' });
      renderAsr(d);
    } catch (e) {
      $('asrErr').textContent = String(e);
      btn.disabled = false;
    }
  });

  $('btnAsrTest').addEventListener('click', async () => {
    const btn = $('btnAsrTest');
    btn.disabled = true;
    const old = btn.textContent;
    btn.textContent = '自检中…';
    $('asrErr').textContent = '';
    try {
      const r = await api('/api/asr/selftest', { method: 'POST' });
      if (r.ok) {
        $('asrText').textContent = r.text || '(空)';
        $('asrRtf').textContent = `${r.ms} ms · RTF ${r.rtf} · ${r.audio_sec}s 音频`;
        $('asrDev').textContent = `自检通过 · 模型加载 ${(r.load_ms / 1000).toFixed(1)}s`;
      } else {
        $('asrErr').textContent = r.error || '自检失败';
      }
    } catch (e) {
      $('asrErr').textContent = String(e);
    }
    btn.textContent = old;
    btn.disabled = false;
  });

  $('btnPrompter').addEventListener('click', () => {
    window.open('/prompter', 'prompter', 'width=1280,height=720');
  });

  // 设置页：麦克风 / 模型 / 推理后端。返回时如果换了麦克风，重新开麦即可生效。
  $('btnSettings').addEventListener('click', () => {
    window.location.href = '/settings';
  });

  /* ---------- 退出程序 ----------
     快捷方式走 pythonw，没有控制台窗口，关掉浏览器标签页服务照样在后台跑；
     以前想停只能去任务管理器结束 pythonw.exe —— 那不是正常用户该做的事。
     这个按钮替掉那一步：先存稿，再请服务自己退，然后盖一层"已退出"。 */
  $('btnQuit').addEventListener('click', async () => {
    const busy = runState !== 'IDLE' ? '\n\n⚠️ 现在正在跟读，退出会立刻中断。' : '';
    if (!confirm('退出提词器？' + busy
      + '\n\n服务会停止；下次要用，双击桌面上的「AI 提词器」。')) return;

    // 先把稿子落盘。退出会掐掉服务，还在等 800 ms 防抖的那次自动保存就没了。
    try { await saveScript(); } catch (e) { /* 存不上也得让人退 */ }

    quitting = true;
    const btn = $('btnQuit');
    btn.disabled = true;
    btn.textContent = '正在退出…';
    try {
      await api('/api/quit', { method: 'POST' });
    } catch (e) {
      // 服务退得太快，这个请求本身报错也正常；到底停没停看下面的复查
    }
    showQuitScreen();
    checkReallyQuit();
  });

  function showQuitScreen() {
    $('quitScreen').hidden = false;
    // 遮罩之外再把控件禁掉：万一哪天真被盖漏了，也别让人点到一排假按钮
    document.querySelectorAll('header button, header select, .controls button, .controls input')
      .forEach((el) => { el.disabled = true; });
  }

  /* 「已退出」这句话必须是真的。优雅退出要跑 lifespan 的 finally
     （里面在关音频流、等识别线程收尾），万一卡住，用户会看到"已退出"
     却还能刷新出界面 —— 那是最糟的一种谎话。4 秒后探一次，还活着就直说。 */
  function checkReallyQuit() {
    setTimeout(async () => {
      try {
        const r = await fetch('/api/state?probe=' + Date.now(), { cache: 'no-store' });
        if (!r.ok) return;
      } catch (e) {
        return;                       // 连不上 = 真的停了，正是要的结果
      }
      const el = $('quitWarn');
      el.hidden = false;
      el.textContent = '退出没有生效 —— 服务还在后台跑。\n'
        + '请到任务管理器里结束 pythonw.exe，或重启电脑。';
    }, 4000);
  }

  /* ---------- 快捷键（输入框内不拦截） ---------- */
  document.addEventListener('keydown', (e) => {
    const t = e.target;
    const typing = t && (t.tagName === 'TEXTAREA' || t.tagName === 'INPUT' || t.tagName === 'SELECT');
    if (typing) return;

    if (e.code === 'Space') {
      e.preventDefault();
      send({ type: runState === 'IDLE' ? 'start' : 'pause' });
    } else if (e.code === 'Escape') {
      e.preventDefault();
      send({ type: 'stop' });
    } else if ((e.ctrlKey || e.metaKey) && (e.key === '=' || e.key === '+' || e.key === '-')) {
      e.preventDefault();
      const step = e.key === '-' ? -UI.font_step : UI.font_step;
      UI.font_px = Math.max(UI.font_min, Math.min(UI.font_max, UI.font_px + step));
      $('rFont').value = UI.font_px;
      $('oFont').textContent = UI.font_px + ' px';
      pushPatch({ font_px: UI.font_px });
    }
  });

  /* ---------- 预览缩放 ---------- */
  function fitPreview() {
    const box = $('previewBox');
    const frame = $('preview');
    const s = Math.min(box.clientWidth / 1920, box.clientHeight / 1080);
    frame.style.transform = `scale(${s})`;
    frame.style.left = (box.clientWidth - 1920 * s) / 2 + 'px';
    frame.style.top = (box.clientHeight - 1080 * s) / 2 + 'px';
  }
  window.addEventListener('resize', fitPreview);

  /* ---------- WebSocket ---------- */
  function connect() {
    ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
    ws.onopen = () => send({ type: 'noop' });
    ws.onmessage = (ev) => {
      let m;
      try { m = JSON.parse(ev.data); } catch { return; }
      if (m.type === 'init') {
        setMode(m.pos.state);
        if (m.script) updateStats(m.script.chars, m.script.n_lines);
        if (m.asr) renderAsr(m.asr);
      } else if (m.type === 'pos') {
        setMode(m.pos.state);
        if (m.align) renderAlign(m.align);
      } else if (m.type === 'ui') {
        UI = m.ui;
        syncControls();
      } else if (m.type === 'script') {
        if (m.script) updateStats(m.script.chars, m.script.n_lines);
      } else if (m.type === 'asr') {
        renderAsr(m.asr);
        if (m.text) $('asrText').textContent = m.text;
      } else if (m.type === 'vu') {
        renderVu(m);
      }
    };
    // 退出时 WS 一定会断，这时候再重连就成了每 400 ms 一次的徒劳尝试
    ws.onclose = () => { if (!quitting) setTimeout(connect, 400); };
  }

  /* ---------- 启动 ---------- */
  (async () => {
    // 版本号由服务端读 VERSION.txt 给出，前端不认识任何具体数字
    try {
      const v = await api('/api/version');
      if (v && v.version && v.version !== 'dev') $('verTag').textContent = 'v' + v.version;
    } catch (e) { /* 拿不到就不显示，不影响用 */ }

    const d = await api('/api/state');
    UI = d.ui;
    curId = d.last_script_id;
    await loadScriptList();
    await loadText(curId);
    syncControls();
    setMode('IDLE');
    if (d.script) updateStats(d.script.chars, d.script.n_lines);
    fitPreview();
    connect();
    setTimeout(fitPreview, 60);
  })();
})();
