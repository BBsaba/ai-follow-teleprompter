/* 设置页。只用原生 JS，和 console.js 一个路子：不引框架、不打包。 */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);

  const S = {
    asr: { mic_index: null, model_dir: null, device: 'auto', dtype: 'auto' },
    devices: [],
    models: [],
    busy: false,
  };

  const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // ---------- 请求 ----------
  async function req(url, opt) {
    const r = await fetch(url, opt);
    let data = null;
    try { data = await r.json(); } catch (e) { /* 空响应 */ }
    if (!r.ok) {
      const msg = (data && data.error) || `请求失败（HTTP ${r.status}）`;
      const err = new Error(msg);
      err.status = r.status;
      throw err;
    }
    return data;
  }

  const get = (u) => req(u);
  const put = (u, body) => req(u, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const post = (u, body) => req(u, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });

  // ---------- 提示 ----------
  let toastTimer = 0;
  function toast(text, kind) {
    const el = $('toast');
    el.textContent = text;
    el.className = 'toast' + (kind ? ' ' + kind : '');
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 3600);
  }

  function setMsg(id, text, kind) {
    const el = $(id);
    el.textContent = text || '';
    el.className = 'msg' + (kind ? ' ' + kind : '');
  }

  // ---------- 填充：麦克风 ----------
  function fillDevices() {
    const sel = $('micSel');
    const want = S.asr.mic_index;
    const opts = ['<option value="">系统默认输入</option>'];
    for (const d of S.devices) {
      const tag = d.default ? '（系统默认）' : '';
      opts.push(`<option value="${d.id}">#${d.id} · ${esc(d.name)}${tag}</option>`);
    }
    sel.innerHTML = opts.join('');
    sel.value = want === null || want === undefined ? '' : String(want);
    // 保存过的设备现在拔了：别装作选中了默认，明确告诉用户
    if (sel.value === '' && want !== null && want !== undefined) {
      setMsg('micTestMsg', `上次选的 #${want} 现在不在了（麦克风拔了？），已回到系统默认。`, 'warn');
      sel.value = '';
    }
  }

  function updateMicChip() {
    const v = $('micSel').value;
    const chip = $('micChip');
    if (v === '') {
      chip.textContent = '系统默认';
      chip.className = 'chip';
    } else {
      // 别把设备名硬截断——「麦克风 (fifine Microp」看着像渲染坏了。
      // 完整名字就在下面的下拉里，这里只表明"用的是哪一个"。
      chip.textContent = `已选 #${v}`;
      chip.className = 'chip on';
    }
  }

  // ---------- 填充：模型 ----------
  const CUSTOM = '__custom__';

  function fillModels() {
    const sel = $('modelSel');
    const cur = S.asr.model_dir || '';
    const opts = ['<option value="">自动（在 models/ 里找）</option>'];
    for (const m of S.models) {
      const size = m.gb ? ` · ${m.gb} GB` : '';
      opts.push(`<option value="${esc(m.path)}">${esc(m.name)}${size}</option>`);
    }
    opts.push(`<option value="${CUSTOM}">手动指定路径…</option>`);
    sel.innerHTML = opts.join('');

    if (!cur) {
      sel.value = '';
      $('pathRow').hidden = true;
    } else if (S.models.some((m) => m.path === cur)) {
      sel.value = cur;
      $('pathRow').hidden = true;
    } else {
      sel.value = CUSTOM;
      $('pathRow').hidden = false;
      $('modelPath').value = cur;
    }
    updateModelChip();
  }

  function updateModelChip() {
    const v = $('modelSel').value;
    const chip = $('modelChip');
    if (v === '') {
      chip.textContent = '自动';
      chip.className = 'chip';
    } else if (v === CUSTOM) {
      chip.textContent = '手动路径';
      chip.className = 'chip warn';
    } else {
      const m = S.models.find((x) => x.path === v);
      chip.textContent = m ? m.name : '已指定';
      chip.className = 'chip on';
    }
  }

  function renderEngine() {
    const e = S.engine || {};
    const el = $('engineMsg');
    if (!e.ready) {
      el.textContent = '当前没有加载模型（点控制台的「开始」才会加载）。';
      return;
    }
    const parts = [e.device, e.dtype].filter(Boolean).join(' · ');
    el.textContent = `已加载：${parts}` +
      (e.load_ms ? ` · 加载 ${(e.load_ms / 1000).toFixed(1)} s` : '') +
      (e.rtf ? ` · RTF ${e.rtf}` : '');
  }

  // ---------- 锁定 ----------
  function setBusy(busy) {
    S.busy = busy;
    $('busyBar').hidden = !busy;
    for (const id of ['micSel', 'modelSel', 'devSel', 'dtypeSel', 'modelPath',
                      'btnMicRefresh', 'btnMicTest', 'btnModelScan',
                      'btnPathCheck', 'btnSave']) {
      const el = $(id);
      if (el) el.disabled = busy;
    }
  }

  // ---------- 载入 ----------
  function apply(payload) {
    S.asr = payload.asr || S.asr;
    S.devices = payload.devices || [];
    S.models = payload.models || [];
    S.engine = payload.engine || {};
    fillDevices();
    fillModels();
    $('devSel').value = S.asr.device || 'auto';
    $('dtypeSel').value = S.asr.dtype || 'auto';
    updateMicChip();
    renderEngine();
    setBusy(!!payload.busy);
  }

  async function load() {
    loadStorage();          // 统计要遍历文件系统，别让它挡住设置先显示
    try {
      apply(await get('/api/settings'));
    } catch (e) {
      toast('读取设置失败：' + e.message, 'err');
    }
  }

  // ---------- 保存 ----------
  async function save() {
    const sel = $('modelSel').value;
    const patch = {
      mic_index: $('micSel').value === '' ? null : Number($('micSel').value),
      model_dir: sel === CUSTOM ? ($('modelPath').value || '').trim() : sel,
      device: $('devSel').value,
      dtype: $('dtypeSel').value,
    };
    $('btnSave').disabled = true;
    try {
      const res = await put('/api/settings', patch);
      apply(res);
      const ch = res.changed || {};
      const bits = [];
      if (ch.mic_changed) bits.push('麦克风');
      if (ch.model_changed) bits.push('模型/推理');
      toast(bits.length
        ? `已保存（${bits.join('、')}）。下次「开始」生效。`
        : '已保存。设置没有变化。', 'ok');
    } catch (e) {
      toast(e.message, 'err');
      if (e.status === 409) setBusy(true);
    } finally {
      $('btnSave').disabled = S.busy;
    }
  }

  // ---------- 试音 ----------
  let vuTimer = 0;
  async function micTest() {
    const v = $('micSel').value;
    const body = { index: v === '' ? null : Number(v), ms: 1200 };
    $('btnMicTest').disabled = true;
    setMsg('micTestMsg', '正在录音……请对着麦克风说话', '');
    const bar = $('micVu');
    bar.style.width = '0%';
    clearInterval(vuTimer);
    vuTimer = setInterval(() => {           // 等待期间让条子脉动一下，别像卡死
      bar.style.width = (12 + Math.random() * 26) + '%';
    }, 120);

    try {
      const r = await post('/api/mic/test', body);
      clearInterval(vuTimer);
      if (!r.ok) {
        bar.style.width = '0%';
        setMsg('micTestMsg', '这个设备打不开：' + (r.error || '未知错误'), 'err');
        return;
      }
      bar.style.width = Math.min(100, r.level * 320) + '%';
      if (r.level < 0.002) {
        setMsg('micTestMsg',
          `几乎没声音（电平 ${r.level}）。检查：系统里是不是选错了输入、麦克风是不是静音、或者换一个设备试试。`,
          'err');
      } else if (r.level < 0.02) {
        setMsg('micTestMsg', `有声音但偏小（电平 ${r.level}），录的时候可以离近一点。`, 'warn');
      } else {
        setMsg('micTestMsg', `正常（电平 ${r.level}，${r.sr} Hz）。这个设备可以用。`, 'ok');
      }
    } catch (e) {
      clearInterval(vuTimer);
      bar.style.width = '0%';
      setMsg('micTestMsg', e.message, 'err');
    } finally {
      $('btnMicTest').disabled = S.busy;
    }
  }

  // ---------- 刷新设备 ----------
  async function refreshDevices() {
    $('btnMicRefresh').disabled = true;
    try {
      const r = await get('/api/devices');
      S.devices = r.devices || [];
      fillDevices();
      updateMicChip();
      toast(`读到 ${S.devices.length} 个输入设备`, 'ok');
    } catch (e) {
      toast('刷新失败：' + e.message, 'err');
    } finally {
      $('btnMicRefresh').disabled = S.busy;
    }
  }

  // ---------- 重新扫描模型 ----------
  async function rescanModels() {
    $('btnModelScan').disabled = true;
    try {
      const r = await get('/api/models');
      S.models = r.models || [];
      fillModels();
      setMsg('modelMsg', S.models.length
        ? `在 models/ 里找到 ${S.models.length} 个模型。`
        : 'models/ 里没有找到模型。先运行 python tools/download_model.py，或者把模型文件夹放进去。',
        S.models.length ? 'ok' : 'warn');
    } catch (e) {
      setMsg('modelMsg', e.message, 'err');
    } finally {
      $('btnModelScan').disabled = S.busy;
    }
  }

  // ---------- 校验手填路径 ----------
  async function checkPath() {
    const p = ($('modelPath').value || '').trim();
    if (!p) { setMsg('modelMsg', '路径是空的。', 'err'); return; }
    $('btnPathCheck').disabled = true;
    try {
      // 借保存接口做校验：先写一份当前值 + 这个路径，失败会 400 且错误文案就是原因。
      // 但那样会真的改掉设置，所以这里改用一个"只读"的办法：直接扫一遍父目录。
      const r = await get('/api/models');
      const hit = (r.models || []).find(
        (m) => m.path.toLowerCase() === p.replace(/\//g, '\\').toLowerCase());
      if (hit) {
        setMsg('modelMsg', `✓ 认定成功：${hit.name}（${hit.gb} GB）`, 'ok');
        if (!S.models.some((m) => m.path === hit.path)) {
          S.models = r.models;
          fillModels();
        }
      } else {
        setMsg('modelMsg',
          '没认出来。这个目录必须同时有 config.json 和 model.safetensors\n' +
          '（或者 pytorch_model.bin）。也可能它不在 models/ 下——那就需要点保存让程序记住它。',
          'warn');
      }
    } catch (e) {
      setMsg('modelMsg', e.message, 'err');
    } finally {
      $('btnPathCheck').disabled = S.busy;
    }
  }

  // ---------- 数据占用 ----------
  /* 只统计、只显示；唯一的删除入口就是这张表里的「清理」按钮，
     而且后端只认白名单里的名字（logs / install_cache）—— 稿件永远不在里面。 */
  function fmtBytes(n) {
    n = Number(n) || 0;
    if (n < 1024) return n + ' B';
    const unit = ['KB', 'MB', 'GB', 'TB'];
    let v = n / 1024;
    let i = 0;
    while (v >= 1024 && i < unit.length - 1) { v /= 1024; i += 1; }
    return (v >= 100 ? v.toFixed(0) : v.toFixed(1)) + ' ' + unit[i];
  }

  function renderStorage(st) {
    const body = $('storBody');
    if (!st || !st.rows) return;
    body.innerHTML = st.rows.map((r) => {
      const cnt = (r.count === null || r.count === undefined) ? '—' : `${r.count} ${r.unit}`;
      const btn = r.cleanable
        ? `<button class="ghost" data-clean="${esc(r.key)}" data-label="${esc(r.label)}">清理</button>`
        : '';
      return `<tr>
        <td>${esc(r.label)}<span class="note">${esc(r.note || '')}</span></td>
        <td>${esc(cnt)}</td>
        <td>${fmtBytes(r.bytes)}</td>
        <td>${btn}</td>
      </tr>`;
    }).join('');
    $('storTotal').textContent = fmtBytes(st.total);
    $('storChip').textContent = '合计 ' + fmtBytes(st.total);
  }

  async function loadStorage() {
    try {
      renderStorage(await get('/api/storage'));
    } catch (e) {
      setMsg('storMsg', '统计失败：' + e.message, 'err');
    }
  }

  async function cleanStorage(what, label, btn) {
    if (!confirm(`清理${label}？\n\n只删${label}，稿件和设置一个字都不会动。`)) return;
    btn.disabled = true;
    setMsg('storMsg', `正在清理${label}…`, '');
    try {
      const r = await post('/api/storage/clean', { what });
      renderStorage(r.storage);
      const d = r.did || {};
      const bits = [];
      if ((d.deleted || []).length) bits.push('删掉 ' + d.deleted.join('、'));
      // 被占用删不掉的，退一步清空 —— 得说清楚，否则用户看到文件还在会以为没生效
      if ((d.truncated || []).length) bits.push('清空 ' + d.truncated.join('、') + '（正被占用）');
      if ((d.failed || []).length) bits.push('没清掉 ' + d.failed.join('、'));
      setMsg('storMsg', bits.length ? bits.join('；') : '没有可清理的文件。',
        (d.failed || []).length ? 'warn' : 'ok');
    } catch (e) {
      setMsg('storMsg', '清理失败：' + e.message, 'err');
    } finally {
      btn.disabled = false;
    }
  }

  // ---------- 绑定 ----------
  $('btnSave').addEventListener('click', save);
  $('btnMicTest').addEventListener('click', micTest);
  $('btnMicRefresh').addEventListener('click', refreshDevices);
  $('btnModelScan').addEventListener('click', rescanModels);
  $('btnPathCheck').addEventListener('click', checkPath);
  $('micSel').addEventListener('change', () => {
    updateMicChip();
    setMsg('micTestMsg', '', '');
    $('micVu').style.width = '0%';
  });
  $('modelSel').addEventListener('change', () => {
    const custom = $('modelSel').value === CUSTOM;
    $('pathRow').hidden = !custom;
    if (custom) $('modelPath').focus();
    updateModelChip();
    setMsg('modelMsg', '', '');
  });
  $('modelPath').addEventListener('input', () => setMsg('modelMsg', '', ''));
  // 清理按钮是渲染出来的（行数不固定），所以绑在容器上做事件委托
  $('storBody').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-clean]');
    if (b) cleanStorage(b.dataset.clean, b.dataset.label, b);
  });
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); save(); }
  });

  load();
})();
