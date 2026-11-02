/* Venue map viewer. Reads data/overlay.json (the only data contract, see README)
   and the background files it names. No framework, no external requests. */
'use strict';
(() => {
  const NS = 'http://www.w3.org/2000/svg';
  const DATA_URL = 'data/overlay.json';

  // ---------------------------------------------------------------- icons
  // Built-in icon set, chosen by name in overlay.json. Unknown names -> dot.
  const ICONS = {
    toilet: { text: 'WC' },
    food: 'M7 2h1.5v6h1V2H11v6h1V2h1.5v7a2.5 2.5 0 0 1-2 2.45V22h-2V11.45A2.5 2.5 0 0 1 7 9zM17.5 2c1 0 1.5 1 1.5 2.5V22h-2v-7h-2.5V7c0-3 1.5-5 3-5z',
    pin: 'M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z',
    stairs: 'M3 21v-4.5h4.5V12H12V7.5h4.5V3H21v3h-1.5v4.5H15V15h-4.5v4.5H6V21z',
    bolt: 'M13.5 2 4 13.5h6.5L9.5 22 20 9.5h-6.5z',
    booth: 'M3 9.5 5 4h14l2 5.5v1a2.5 2.5 0 0 1-4.5 1.5 2.5 2.5 0 0 1-4.5 0 2.5 2.5 0 0 1-4.5 0A2.5 2.5 0 0 1 3 10.5zM5 14h2v5h10v-5h2v7H5z',
    flask: 'M9 2h6v2h-1v4.5l5.6 10A2.3 2.3 0 0 1 17.6 22H6.4a2.3 2.3 0 0 1-2-3.5L10 8.5V4H9zm-.6 13h7.2L12.4 9.6h-.8z',
    door: 'M4 20h2V3h12v17h2v2H4zm4 0h8V5H8zm5-9h2v2h-2z',
    lift: 'M5 2h14v20H5zm2 2v16h10V4zm5 1.5 3.5 4.5h-7zm0 13L8.5 14h7z',
    stage: 'M2 18h20v4H2zM3 3h18v2.5h-1.5V16h-2V5.5h-11V16h-2V5.5H3z',
    info: 'M12 2a10 10 0 1 1 0 20 10 10 0 0 1 0-20zm-1 8v7h2v-7zm0-4v2h2V6z',
    coat: 'M12 3a2.5 2.5 0 0 1 1 4.8V9l8 6.5V18H3v-2.5L11 9V7h2v.2A.5.5 0 1 0 12 5a.5.5 0 0 0-.5.5h-2A2.5 2.5 0 0 1 12 3zm0 7.6L5.4 16h13.2z',
    firstaid: 'M10 3h4v7h7v4h-7v7h-4v-7H3v-4h7z',
    quiet: 'M20 15.5A8.5 8.5 0 1 1 8.5 4a7 7 0 0 0 11.5 11.5z',
    registration: 'M4 4h16v16H4zm2 2v12h12V6zm2 2h8v2H8zm0 4h8v2H8z',
    dot: 'M12 6a6 6 0 1 1 0 12 6 6 0 0 1 0-12z',
  };
  function iconMarkup(name) {
    const ic = ICONS[name] || ICONS.dot;
    if (typeof ic === 'object') {
      return `<text x="12" y="12.5" text-anchor="middle" dominant-baseline="central" font-size="9.5" font-weight="700">${ic.text}</text>`;
    }
    return `<path d="${ic}"/>`;
  }
  function catDot(cat, size = 30) {
    return `<span class="cat-dot" style="background:${cat.color || '#555'};width:${size}px;height:${size}px" aria-hidden="true"><svg viewBox="0 0 24 24">${iconMarkup(cat.icon)}</svg></span>`;
  }

  // ---------------------------------------------------------------- helpers
  const $ = (id) => document.getElementById(id);
  const el = (tag, attrs = {}, parent) => {
    const n = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (parent) parent.appendChild(n);
    return n;
  };
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const norm = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
    .toLowerCase().replace(/ß/g, 'ss').replace(/[^a-z0-9]+/g, ' ').trim();
  const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

  function shapePoints(it) {
    const s = it.shape;
    if (!s) return null;
    if (s.type === 'polygon' && Array.isArray(s.points) && s.points.length >= 3) return s.points;
    if (s.type === 'rect') return [[s.x, s.y], [s.x + s.width, s.y], [s.x + s.width, s.y + s.height], [s.x, s.y + s.height]];
    return null; // unknown shape types are ignored (pin still works)
  }
  function inPoly(x, y, pts) {
    let inside = false;
    for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
      const [xi, yi] = pts[i], [xj, yj] = pts[j];
      if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }
  function polyArea(pts) {
    let a = 0;
    for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) a += (pts[j][0] + pts[i][0]) * (pts[j][1] - pts[i][1]);
    return Math.abs(a / 2);
  }

  // ---------------------------------------------------------------- state
  const S = {
    data: null, floors: [], floorById: {}, cats: [], catById: {}, items: [], itemById: {},
    floor: null, cat: null, item: null, allFloors: false,
    view: { k: 1, x: 0, y: 0 }, fitK: 1, pulseAt: 0, ready: false,
    allLabels: false,
  };
  try { S.allLabels = localStorage.getItem('venueMap.allLabels') === '1'; } catch (e) { /* private mode */ }
  const svg = $('svg'), mapEl = $('map');
  let vp, bgLayer, fullLayer, dimRect, maskG, hlLayer, labelLayer, clipG, labMaskG, markerLayer;
  const bgs = {};

  // ---------------------------------------------------------------- load
  fetch(DATA_URL, { cache: 'no-cache' })
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(init)
    .catch((e) => { $('loading').textContent = 'Could not load the map. Check your connection and reload.'; console.error(e); });

  function init(data) {
    S.data = data;
    S.floors = (data.floors || []).filter((f) => f && f.id && f.width > 0 && f.height > 0)
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
    S.floors.forEach((f) => (S.floorById[f.id] = f));
    S.cats = (data.categories || []).filter((c) => c && c.id);
    S.cats.forEach((c) => (S.catById[c.id] = c));
    S.items = (data.items || []).filter((it) => it && it.id && S.floorById[it.floor] && S.catById[it.category] && Array.isArray(it.pin));
    S.items.forEach((it) => {
      S.itemById[it.id] = it;
      it._pts = shapePoints(it);
      it._area = it._pts ? polyArea(it._pts) : 0;
      const cat = S.catById[it.category];
      it._name = norm(it.name);
      it._hay = norm([it.name, ...(it.aliases || []), it.description, cat.label].join(' '));
      it._compact = it._hay.replace(/ /g, '');
    });
    if (!S.floors.length) { $('loading').textContent = 'The map has no floors yet.'; return; }

    buildSvg();
    buildFloorTabs();
    buildChips();
    showUpdated(data.updated);
    bindMap();
    bindSearch();

    // deep links: ?item=  or  ?floor= & cat=
    const q = new URLSearchParams(location.search);
    const item = S.itemById[q.get('item')];
    const floor = S.floorById[q.get('floor')];
    const cat = S.catById[q.get('cat')];
    setFloor((item && item.floor) || (floor && floor.id) || S.floors[0].id, { noUrl: true });
    if (item) selectItem(item.id, { noUrl: true, instant: true });
    else if (cat) selectCat(cat.id, { noUrl: true, keepFloor: !!floor });
    S.ready = true;
  }

  function showUpdated(iso) {
    const d = new Date(iso);
    if (!iso || isNaN(d)) return;
    const fmt = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
    $('updated').textContent = 'Map updated ' + fmt.format(d);
  }

  // ---------------------------------------------------------------- svg setup
  // Layers, bottom to top: background (muted when a full-colour copy exists),
  // full-colour copy clipped to the selection, light veil, outlines, printed
  // labels (masked per label), then screen-space markers.
  function buildSvg() {
    const defs = el('defs', {}, svg);
    const mask = el('mask', { id: 'hole', maskUnits: 'userSpaceOnUse' }, defs);
    maskG = el('g', {}, mask);
    clipG = el('clipPath', { id: 'sel', clipPathUnits: 'userSpaceOnUse' }, defs);
    const lm = el('mask', { id: 'lab', maskUnits: 'userSpaceOnUse' }, defs);
    labMaskG = el('g', {}, lm);
    vp = el('g', {}, svg);
    bgLayer = el('g', {}, vp);
    fullLayer = el('g', { 'clip-path': 'url(#sel)' }, vp);
    dimRect = el('rect', { class: 'dim', mask: 'url(#hole)' }, vp);
    hlLayer = el('g', {}, vp);
    labelLayer = el('g', { mask: 'url(#lab)' }, vp);
    markerLayer = el('g', {}, svg); // screen space: markers keep their size when zooming
  }

  const fulls = {}, labs = {};
  const layerImg = (f, href, parent) => el('image', { x: 0, y: 0, width: f.width, height: f.height, preserveAspectRatio: 'none', href }, parent);
  function showOnly(store, id) { for (const [fid, im] of Object.entries(store)) im.style.display = fid === id ? '' : 'none'; }
  function ensureLayers(f) {
    if (f.labels && !labs[f.id]) labs[f.id] = layerImg(f, f.labels, labelLayer);
    showOnly(labs, f.id);
    showOnly(fulls, f.id);
  }
  // the full-colour copy is only fetched once something on that floor is highlighted
  function ensureFull(f) {
    if (f.backgroundHighlight && !fulls[f.id]) fulls[f.id] = layerImg(f, f.backgroundHighlight, fullLayer);
    showOnly(fulls, f.id);
  }
  function ensureBg(f) {
    if (bgs[f.id]) return bgs[f.id];
    const img = layerImg(f, f.background, bgLayer);
    img.addEventListener('load', () => { if (f.id === S.floor) $('loading').hidden = true; });
    img.addEventListener('error', () => { if (f.id === S.floor) $('loading').textContent = 'Could not load this floor plan.'; });
    bgs[f.id] = img;
    return img;
  }

  // ---------------------------------------------------------------- floors
  function buildFloorTabs() {
    const nav = $('floors');
    nav.innerHTML = '';
    for (const f of S.floors) {
      const b = document.createElement('button');
      b.setAttribute('role', 'tab');
      b.dataset.floor = f.id;
      b.title = f.name;
      b.innerHTML = `<span>${esc(f.shortName || f.name)}</span>`;
      b.addEventListener('click', () => setFloor(f.id));
      nav.appendChild(b);
    }
  }

  function setFloor(id, opts = {}) {
    const f = S.floorById[id];
    if (!f) return;
    const changed = S.floor !== id;
    S.floor = id;
    for (const [fid, img] of Object.entries(bgs)) img.style.display = fid === id ? '' : 'none';
    const img = ensureBg(f);
    img.style.display = '';
    ensureLayers(f);
    if (img.getBBox && img.dataset.loaded !== '1') $('loading').hidden = false;
    img.addEventListener('load', () => (img.dataset.loaded = '1'), { once: true });
    if (S.item && S.itemById[S.item].floor !== id) S.item = null;
    dimRect.setAttribute('width', f.width); dimRect.setAttribute('height', f.height);
    for (const sel of ['#hole', '#lab']) {
      const m = svg.querySelector(sel);
      m.setAttribute('x', 0); m.setAttribute('y', 0); m.setAttribute('width', f.width); m.setAttribute('height', f.height);
    }
    if (changed || opts.refit) fit(true);
    render(opts);
  }

  // default view: the area that has items (or floor.view), not the whole page
  function homeBox(f) {
    if (Array.isArray(f.view) && f.view.length === 4) return f.view;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const it of S.items) {
      if (it.floor !== f.id) continue;
      for (const [x, y] of it._pts || [it.pin]) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
    }
    if (!isFinite(x0)) return [0, 0, f.width, f.height];
    const pad = 0.08 * Math.max(x1 - x0, y1 - y0);
    x0 = Math.max(0, x0 - pad); y0 = Math.max(0, y0 - pad); x1 = Math.min(f.width, x1 + pad); y1 = Math.min(f.height, y1 + pad);
    // never zoom in further than half the floor
    const w = Math.max(x1 - x0, f.width * 0.5), h = Math.max(y1 - y0, f.height * 0.5);
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    return [cx - w / 2, cy - h / 2, w, h];
  }
  function size() { return [mapEl.clientWidth || 1, mapEl.clientHeight || 1]; }
  function fit(instant) {
    const f = S.floorById[S.floor];
    const [bx, by, bw, bh] = homeBox(f);
    const [cw, ch] = size();
    const k = Math.min(cw / bw, ch / bh) * 0.96;
    S.fitK = k;
    setView({ k, x: cw / 2 - k * (bx + bw / 2), y: ch / 2 - k * (by + bh / 2) }, instant);
  }

  // ---------------------------------------------------------------- view / zoom
  let anim = 0, animState = null;
  function clampView(v) {
    const f = S.floorById[S.floor];
    const [cw, ch] = size();
    const k = Math.min(Math.max(v.k, S.fitK * 0.6), S.fitK * 12);
    const m = 60; // keep at least this many px of the floor on screen
    const x = Math.min(Math.max(v.x, m - k * f.width), cw - m);
    const y = Math.min(Math.max(v.y, m - k * f.height), ch - m);
    return { k, x, y };
  }
  function setView(v, instant) {
    v = clampView(v);
    cancelAnimationFrame(anim);
    animState = null;
    if (instant || reduceMotion) { S.view = v; applyView(); return; }
    animState = { from: { ...S.view }, to: v, t0: performance.now(), dur: 320 };
    const step = (t) => {
      if (!animState) return;
      const { from, to, t0, dur } = animState;
      const p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
      S.view = { k: from.k + (to.k - from.k) * e, x: from.x + (to.x - from.x) * e, y: from.y + (to.y - from.y) * e };
      applyView();
      if (p < 1) anim = requestAnimationFrame(step); else animState = null;
    };
    anim = requestAnimationFrame(step);
  }
  // the map area changed size (rotation, search panel, info card): keep the
  // same point in the middle, and let a running animation finish.
  function shiftView(dx, dy) {
    if (animState) {
      animState.from.x += dx; animState.from.y += dy;
      animState.to.x += dx; animState.to.y += dy;
    }
    S.view = { ...S.view, x: S.view.x + dx, y: S.view.y + dy };
    applyView();
  }
  function applyView() {
    const { k, x, y } = S.view;
    vp.setAttribute('transform', `translate(${x} ${y}) scale(${k})`);
    placeMarkers();
    // mask holes for pin-only items keep a constant on-screen size
    maskG.querySelectorAll('circle').forEach((c) => c.setAttribute('r', 40 / k));
  }
  function zoomAt(px, py, factor) {
    const { k, x, y } = S.view;
    const nk = Math.min(Math.max(k * factor, S.fitK * 0.6), S.fitK * 12);
    const wx = (px - x) / k, wy = (py - y) / k;
    setView({ k: nk, x: px - nk * wx, y: py - nk * wy }, true);
  }
  function centreOn(it) {
    const [cw, ch] = size();
    const k = Math.max(S.view.k, S.fitK * 2.2);
    setView({ k, x: cw / 2 - k * it.pin[0], y: ch / 2 - k * it.pin[1] });
  }

  // ---------------------------------------------------------------- render
  function render(opts = {}) {
    const f = S.floorById[S.floor];
    const cat = S.cat && S.catById[S.cat];
    // floor tabs
    const floorsWithCat = new Set(cat ? S.items.filter((i) => i.category === cat.id).map((i) => i.floor) : []);
    document.querySelectorAll('#floors button').forEach((b) => {
      const on = b.dataset.floor === S.floor;
      b.setAttribute('aria-selected', on);
      b.tabIndex = on ? 0 : -1;
      const dot = floorsWithCat.has(b.dataset.floor) && !on;
      b.innerHTML = `<span>${esc(S.floorById[b.dataset.floor].shortName || S.floorById[b.dataset.floor].name)}</span>` +
        (dot ? `<span class="has" style="background:${cat.color || 'currentColor'}" title="Has ${esc(cat.label)}"></span>` : '');
    });
    // chips
    document.querySelectorAll('.chip').forEach((b) => b.setAttribute('aria-pressed', b.dataset.cat === S.cat));

    // which items are emphasised
    let hl = [];
    if (S.item) hl = [S.itemById[S.item]];
    else if (cat) hl = S.items.filter((i) => i.category === cat.id && i.floor === f.id);
    const dimOn = !!(S.item || cat);
    const layered = !!f.backgroundHighlight;
    dimRect.style.opacity = dimOn ? 1 : 0;
    dimRect.classList.toggle('light', layered);

    maskG.innerHTML = '';
    hlLayer.innerHTML = '';
    clipG.innerHTML = '';
    el('rect', { x: 0, y: 0, width: f.width, height: f.height, fill: '#fff' }, maskG);
    if (layered && hl.some((i) => i._pts)) ensureFull(f);
    for (const it of hl) {
      const c = S.catById[it.category].color || '#e33';
      if (it._pts) {
        const d = it._pts.map((p) => p.join(',')).join(' ');
        el('polygon', { points: d, fill: '#000' }, maskG);
        el('polygon', { points: d }, clipG);
        el('polygon', { points: d, class: 'hl-halo' }, hlLayer);
        el('polygon', { points: d, class: 'hl' + (layered ? ' over-full' : ''), fill: c, stroke: c }, hlLayer);
      } else if (!f.labels) {
        // no separate label layer: reveal the printed pin through the veil
        el('circle', { cx: it.pin[0], cy: it.pin[1], r: 40 / S.view.k, fill: '#000' }, maskG);
      }
    }
    S.hl = hl;
    renderLabelMask(f, hl, dimOn);
    $('labelsBtn').setAttribute('aria-pressed', S.allLabels);
    $('labelsBtn').hidden = !f.labels;
    applyView();
    renderSheet(hl, cat, floorsWithCat);
    if (!opts.noUrl && S.ready) updateUrl();
  }

  // Which printed labels stay crisp. Mask luminance = opacity.
  const FADED = '#4d4d4d'; // ~30 %
  const CHROME = '#333'; // ~20 %: title, legend
  function renderLabelMask(f, hl, selecting) {
    labMaskG.innerHTML = '';
    const box = (b, fill) => el('rect', { x: b[0], y: b[1], width: b[2], height: b[3], fill }, labMaskG);
    if (S.allLabels) { box([0, 0, f.width, f.height], '#fff'); return; }
    box([0, 0, f.width, f.height], selecting ? FADED : '#fff');
    for (const b of f.chromeBoxes || []) box(b, CHROME);
    if (selecting) for (const it of hl) for (const b of it.labelBoxes || []) box(b, '#fff');
    for (const b of f.fixedBoxes || []) box(b, '#fff');
  }

  function placeMarkers() {
    markerLayer.innerHTML = '';
    if (!S.hl) return;
    const { k, x, y } = S.view;
    for (const it of S.hl) {
      // printed pins/labels already show where things are; a marker only for
      // the searched/tapped item, or things with nothing printed on the plan
      if (S.item !== it.id && (it.labelBoxes?.length || it._pts)) continue;
      const cat = S.catById[it.category];
      const sx = x + k * it.pin[0], sy = y + k * it.pin[1];
      if (S.item === it.id && performance.now() - S.pulseAt < 3500) {
        el('circle', { class: 'pulse', cx: sx, cy: sy, r: 14 }, markerLayer);
      }
      // teardrop: the tip is exactly on the spot, the head floats above it
      const g = el('g', { class: 'marker', transform: `translate(${sx} ${sy})` }, markerLayer);
      el('path', { class: 'bg', d: 'M0 0C-3-7-14-13-14-24a14 14 0 1 1 28 0C14-13 3-7 0 0z', fill: cat.color || '#555' }, g);
      const ig = el('g', { class: 'glyph', transform: 'translate(-9 -33) scale(0.75)' }, g);
      ig.innerHTML = iconMarkup(cat.icon);
    }
  }

  // bottom sheet: selected item, or category summary / empty state
  function renderSheet(hl, cat, floorsWithCat) {
    const sh = $('sheet');
    const close = `<button class="icon-btn close" aria-label="Clear"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6.4 5 5.6 5.6L17.6 5 19 6.4 13.4 12l5.6 5.6-1.4 1.4-5.6-5.6L6.4 19 5 17.6l5.6-5.6L5 6.4z"/></svg></button>`;
    const floorLinks = (ids) => S.floors.filter((f) => ids.has(f.id) && f.id !== S.floor)
      .map((f) => `<button data-goto="${esc(f.id)}">${esc(f.name)}</button>`).join('');
    if (S.item) {
      const it = S.itemById[S.item], c = S.catById[it.category];
      sh.innerHTML = `${catDot(c)}<div class="grow"><div class="name">${esc(it.name)}</div>` +
        `<div class="sub">${esc([it.description, c.label, S.floorById[it.floor].name].filter(Boolean).join(' · '))}</div></div>${close}`;
    } else if (cat) {
      const n = hl.length;
      const others = floorLinks(floorsWithCat);
      let txt;
      if (!floorsWithCat.size) txt = `${esc(cat.label)}: not on the map yet.`;
      else if (!n) txt = `No ${esc(cat.label)} on ${esc(S.floorById[S.floor].name)}. On:`;
      else txt = `${esc(cat.label)}: ${n} on this floor.` + (others ? ' Also on:' : '');
      sh.innerHTML = `${catDot(cat)}<div class="grow"><div class="name">${txt}</div>` +
        (others ? `<div class="links">${others}</div>` : '') + `</div>${close}`;
    } else {
      sh.hidden = true;
      return;
    }
    sh.hidden = false;
    sh.querySelector('.close').onclick = () => { S.item = null; S.cat = null; render(); };
    sh.querySelectorAll('[data-goto]').forEach((b) => (b.onclick = () => setFloor(b.dataset.goto)));
  }

  // ---------------------------------------------------------------- categories
  function buildChips() {
    const box = $('chips');
    box.innerHTML = '';
    for (const c of S.cats) {
      if (c.chip === false) continue;
      const b = document.createElement('button');
      b.className = 'chip';
      b.dataset.cat = c.id;
      b.innerHTML = `${catDot(c, 32)}<span>${esc(c.label)}</span>`;
      b.addEventListener('click', () => selectCat(c.id));
      box.appendChild(b);
    }
  }

  function selectCat(id, opts = {}) {
    if (S.cat === id && !opts.force) { S.cat = null; render(opts); return; }
    S.cat = id;
    S.item = null;
    const c = S.catById[id];
    const floors = [...new Set(S.items.filter((i) => i.category === id).map((i) => i.floor))];
    // "lives on one floor": explicit category.floor, or all its items are on one floor
    const target = (c.floor && S.floorById[c.floor]) ? c.floor : (floors.length === 1 ? floors[0] : null);
    if (target && target !== S.floor && !opts.keepFloor) setFloor(target, opts);
    else render(opts);
    const chip = document.querySelector(`.chip[data-cat="${CSS.escape(id)}"]`);
    if (chip) chip.scrollIntoView({ inline: 'nearest', block: 'nearest', behavior: reduceMotion ? 'auto' : 'smooth' });
  }

  function selectItem(id, opts = {}) {
    const it = S.itemById[id];
    if (!it) return;
    S.cat = null;
    S.item = id;
    S.pulseAt = performance.now();
    if (it.floor !== S.floor) setFloor(it.floor, { noUrl: true });
    render(opts);
    if (opts.instant) {
      const [cw, ch] = size();
      const k = S.fitK * 2.2;
      setView({ k, x: cw / 2 - k * it.pin[0], y: ch / 2 - k * it.pin[1] }, true);
    } else centreOn(it);
    setTimeout(placeMarkers, 3600); // drop the pulse ring after it finishes
  }

  function updateUrl() {
    const p = new URLSearchParams();
    if (S.item) p.set('item', S.item);
    else {
      if (S.floor !== S.floors[0].id) p.set('floor', S.floor);
      if (S.cat) p.set('cat', S.cat);
    }
    const qs = p.toString();
    history.replaceState(null, '', qs ? `?${qs}` : location.pathname);
  }

  // ---------------------------------------------------------------- gestures
  function bindMap() {
    const pts = new Map();
    let start = null, lastTap = null, moved = false, downAt = 0;
    const pos = (e) => { const r = svg.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
    const begin = () => {
      const arr = [...pts.values()];
      if (arr.length === 1) start = { mode: 'pan', p: arr[0], v: { ...S.view } };
      else if (arr.length >= 2) {
        const [a, b] = arr;
        start = { mode: 'pinch', d: Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, m: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], v: { ...S.view } };
      }
    };
    svg.addEventListener('pointerdown', (e) => {
      svg.setPointerCapture(e.pointerId);
      pts.set(e.pointerId, pos(e));
      cancelAnimationFrame(anim);
      if (pts.size === 1) { moved = false; downAt = performance.now(); }
      else moved = true;
      begin();
    });
    svg.addEventListener('pointermove', (e) => {
      if (!pts.has(e.pointerId)) return;
      pts.set(e.pointerId, pos(e));
      const arr = [...pts.values()];
      if (start.mode === 'pan' && arr.length === 1) {
        const dx = arr[0][0] - start.p[0], dy = arr[0][1] - start.p[1];
        if (Math.hypot(dx, dy) > 6) moved = true;
        if (moved) setView({ k: start.v.k, x: start.v.x + dx, y: start.v.y + dy }, true);
      } else if (start.mode === 'pinch' && arr.length >= 2) {
        const [a, b] = arr;
        const d = Math.hypot(a[0] - b[0], a[1] - b[1]);
        const m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
        const k = Math.min(Math.max(start.v.k * (d / start.d), S.fitK * 0.6), S.fitK * 12);
        const wx = (start.m[0] - start.v.x) / start.v.k, wy = (start.m[1] - start.v.y) / start.v.k;
        setView({ k, x: m[0] - k * wx, y: m[1] - k * wy }, true);
      }
    });
    const end = (e) => {
      if (!pts.has(e.pointerId)) return;
      const p = pts.get(e.pointerId);
      pts.delete(e.pointerId);
      if (pts.size) { begin(); return; }
      if (!moved && performance.now() - downAt < 400) {
        const now = performance.now();
        if (lastTap && now - lastTap.t < 320 && Math.hypot(p[0] - lastTap.p[0], p[1] - lastTap.p[1]) < 30) {
          lastTap = null;
          zoomAtAnimated(p[0], p[1], 2);
        } else {
          lastTap = { t: now, p };
          tap(p[0], p[1]);
        }
      }
    };
    svg.addEventListener('pointerup', end);
    svg.addEventListener('pointercancel', end);
    svg.addEventListener('wheel', (e) => {
      e.preventDefault();
      const [px, py] = pos(e);
      zoomAt(px, py, Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015)));
    }, { passive: false });
    $('reset').addEventListener('click', () => fit(false));
    $('labelsBtn').addEventListener('click', () => {
      S.allLabels = !S.allLabels;
      try { localStorage.setItem('venueMap.allLabels', S.allLabels ? '1' : '0'); } catch (e) { /* ignore */ }
      render();
    });
    let last = size();
    new ResizeObserver(() => {
      const now = size();
      if (now[0] === last[0] && now[1] === last[1]) return;
      const dx = (now[0] - last[0]) / 2, dy = (now[1] - last[1]) / 2;
      last = now;
      const f = S.floorById[S.floor];
      if (f) {
        const [, , bw, bh] = homeBox(f);
        S.fitK = Math.min(now[0] / bw, now[1] / bh) * 0.96;
      }
      shiftView(dx, dy);
    }).observe(mapEl);
  }
  function zoomAtAnimated(px, py, factor) {
    const { k, x, y } = S.view;
    const nk = Math.min(k * factor, S.fitK * 12);
    const wx = (px - x) / k, wy = (py - y) / k;
    setView({ k: nk, x: px - nk * wx, y: py - nk * wy });
  }

  // tap on the map: show what is there
  function tap(px, py) {
    const { k, x, y } = S.view;
    const wx = (px - x) / k, wy = (py - y) / k;
    const here = S.items.filter((i) => i.floor === S.floor);
    // prefer pins within 22px, then the smallest shape containing the point
    let best = null, bd = 22;
    for (const it of here) {
      const d = Math.hypot(it.pin[0] - wx, it.pin[1] - wy) * k;
      if (d < bd && (!S.cat || it.category === S.cat)) { bd = d; best = it; }
    }
    if (!best) {
      const inside = here.filter((i) => i._pts && inPoly(wx, wy, i._pts) && (!S.cat || i.category === S.cat))
        .sort((a, b) => a._area - b._area);
      best = inside[0] || null;
    }
    if (best) {
      S.item = best.id; S.pulseAt = 0; render();
    } else if (S.item) {
      S.item = null; render();
    }
  }

  // ---------------------------------------------------------------- search
  function bindSearch() {
    const panel = $('search'), btn = $('searchBtn'), input = $('q');
    const open = () => { panel.hidden = false; btn.setAttribute('aria-expanded', 'true'); input.focus(); runSearch(); };
    const close = () => { panel.hidden = true; btn.setAttribute('aria-expanded', 'false'); };
    btn.addEventListener('click', () => (panel.hidden ? open() : close()));
    $('searchClose').addEventListener('click', close);
    input.addEventListener('input', runSearch);
    $('allFloors').addEventListener('change', (e) => { S.allFloors = e.target.checked; runSearch(); });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') { if (!panel.hidden) close(); else if (S.item || S.cat) { S.item = null; S.cat = null; render(); } }
      if (e.key === '/' && panel.hidden && document.activeElement.tagName !== 'INPUT') { e.preventDefault(); open(); }
    });
    $('results').addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b) return;
      if (b.dataset.all) { $('allFloors').checked = true; S.allFloors = true; runSearch(); return; }
      if (b.dataset.item) {
        close(); input.blur();
        // let the map take its new size before jumping, or the resize cancels the animation
        requestAnimationFrame(() => requestAnimationFrame(() => selectItem(b.dataset.item)));
      }
    });
    S.closeSearch = close;
  }

  function search(q) {
    const nq = norm(q);
    if (!nq) return [];
    const toks = nq.split(' '), compact = nq.replace(/ /g, '');
    return S.items.filter((it) => toks.every((t) => it._hay.includes(t)) || it._compact.includes(compact))
      .map((it) => {
        let score = it._name.startsWith(nq) ? 0 : it._name.includes(nq) ? 1 : 2;
        if (it.category === 'rooms' || it._pts == null) score -= 0.1; // named places first
        return { it, score };
      })
      .sort((a, b) => a.score - b.score || (S.floorById[a.it.floor].order ?? 0) - (S.floorById[b.it.floor].order ?? 0) || a.it.name.localeCompare(b.it.name))
      .map((r) => r.it);
  }

  function runSearch() {
    const q = $('q').value, ul = $('results');
    const all = search(q);
    const list = S.allFloors ? all : all.filter((i) => i.floor === S.floor);
    if (!norm(q)) { ul.innerHTML = `<li class="hint">Type a room name or a meeting point like “C3”.</li>`; return; }
    let html = list.slice(0, 40).map((it) => {
      const c = S.catById[it.category];
      const sub = [it.description, S.allFloors ? S.floorById[it.floor].name : ''].filter(Boolean).join(' · ');
      return `<li><button data-item="${esc(it.id)}">${catDot(c)}<span><span class="name">${esc(it.name)}</span>` +
        (sub ? `<br><span class="sub">${esc(sub)}</span>` : '') + `</span></button></li>`;
    }).join('');
    const elsewhere = all.length - list.length;
    if (!S.allFloors && elsewhere > 0) {
      html += `<li class="hint">${list.length ? '' : 'Nothing on this floor. '}${elsewhere} more on other floors – <button data-all="1">search all floors</button></li>`;
    } else if (!all.length) {
      html = `<li class="hint">No matches for “${esc(q)}”.</li>`;
    }
    ul.innerHTML = html;
  }
})();
