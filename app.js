/* Venue map viewer. Reads data/overlay.json (the only data contract, see README)
   and the background files it names. No framework, no external requests. */
'use strict';
(() => {
  const NS = 'http://www.w3.org/2000/svg';
  const DATA_URL = 'data/overlay.json';
  // links: an item has its own page at p/<id>/ (scripts/pages.py, for link previews); its
  // <base> points at the site root, so SITE is the root on every page
  const SITE = new URL('./', document.baseURI);
  // Pin it, on every page: relative addresses are read against the address
  // bar, which replaceState changes. Selecting an item makes it .../p/<id>/,
  // and on the main page (no <base>) every floor picture loaded afterwards
  // was looked for in p/<id>/maps/ (404: the map lost its background). On item
  // pages a relative <base> ("../../") had the same problem the other way round.
  const baseEl = document.querySelector('base') || document.head.appendChild(document.createElement('base'));
  baseEl.setAttribute('href', SITE.href);
  const itemPath = (id) => `p/${encodeURIComponent(id)}/`;
  const pathItem = () => { const m = location.pathname.match(/\/p\/([^/]+)\/?$/); return m ? decodeURIComponent(m[1]) : null; };

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
    museum: 'M12 2 2 7v2h20V7zM4 10.5h2.5V18H4zm4.75 0h2.5V18h-2.5zm4 0h2.5V18h-2.5zm4.75 0H20V18h-2.5zM2 19.5h20V22H2z',
    dot: 'M12 6a6 6 0 1 1 0 12 6 6 0 0 1 0-12z',
    laptop: 'M20 18c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2H4c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2H0v2h24v-2h-4zM4 6h16v10H4z', // silent working
    meditate: 'M12 2a2 2 0 1 1 0 4 2 2 0 0 1 0-4zm9 14v-2c-2.24 0-4.16-.96-5.6-2.68l-1.34-1.6A1.98 1.98 0 0 0 12.53 9h-1.05c-.59 0-1.15.26-1.53.72l-1.34 1.6C7.16 13.04 5.24 14 3 14v2c2.77 0 5.19-1.17 7-3.25V15l-3.88 1.55c-.67.27-1.12.93-1.12 1.66C5 19.2 5.8 20 6.79 20H9v-.5a2.5 2.5 0 0 1 2.5-2.5h3c.28 0 .5.22.5.5s-.22.5-.5.5h-3c-.83 0-1.5.67-1.5 1.5v.5h7.21c.99 0 1.79-.8 1.79-1.79 0-.73-.45-1.39-1.12-1.66L14 15v-2.25c1.81 2.08 4.23 3.25 7 3.25z', // prayer and meditation
    stroller: 'M13 2v8h8c0-4.42-3.58-8-8-8zm6.32 13.89C20.37 14.54 21 12.84 21 11H6.44l-.95-2H2v2h2.22s1.89 4.07 2.12 4.42c-1.1.59-1.84 1.75-1.84 3.08C4.5 20.43 6.07 22 8 22c1.76 0 3.22-1.3 3.46-3h2.08c.24 1.7 1.7 3 3.46 3 1.93 0 3.5-1.57 3.5-3.5 0-1.04-.46-1.97-1.18-2.61zM8 20c-.83 0-1.5-.67-1.5-1.5S7.17 17 8 17s1.5.67 1.5 1.5S8.83 20 8 20zm9 0c-.83 0-1.5-.67-1.5-1.5S16.17 17 17 17s1.5.67 1.5 1.5S17.83 20 17 20z', // parents
    kids: 'M9 11.75a1.25 1.25 0 1 0 0 2.5 1.25 1.25 0 0 0 0-2.5zm6 0a1.25 1.25 0 1 0 0 2.5 1.25 1.25 0 0 0 0-2.5zM12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8 0-.29.02-.58.05-.86 2.36-1.05 4.23-2.98 5.21-5.37A9.97 9.97 0 0 0 19.67 9.74c.21.71.33 1.47.33 2.26 0 4.41-3.59 8-8 8z', // childcare
    star: 'M12 17.27 18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z', // Extra
    chat: 'M21 6h-2v9H6v2c0 .55.45 1 1 1h11l4 4V7c0-.55-.45-1-1-1zm-4 6V3c0-.55-.45-1-1-1H3c-.55 0-1 .45-1 1v14l4-4h10c.55 0 1-.45 1-1z', // conversations
    diamond: { emoji: '🔶' }, // donations (Effektiv Spenden & GWWC)
  };
  function iconMarkup(name) {
    const ic = ICONS[name] || ICONS.dot;
    if (ic.emoji) return `<text class="emoji" x="12" y="11" text-anchor="middle" dominant-baseline="central" font-size="15">${ic.emoji}</text>`;
    if (typeof ic === 'object') {
      return `<text x="12" y="12.5" text-anchor="middle" dominant-baseline="central" font-size="9.5" font-weight="700">${ic.text}</text>`;
    }
    return `<path d="${ic}"/>`;
  }
  function catDot(cat, size = 30) {
    // an emoji icon has its own colours: white dot, ring in the item's colour
    const bg = ICONS[cat.icon]?.emoji ? `#fff;box-shadow:inset 0 0 0 2.5px ${cat.color || '#555'}` : cat.color || '#555';
    return `<span class="cat-dot" style="background:${bg};width:${size}px;height:${size}px" aria-hidden="true"><svg viewBox="0 0 24 24">${iconMarkup(cat.icon)}</svg></span>`;
  }
  // A chip for several things shows their icons stacked, the first in front:
  // Stairs & lifts (its categories), a cardList category (its items' own icons
  // in list order: Fairs & booths, Extras). The stack is as wide as two dots
  // however many there are (style.css, --n).
  function groupDot(cid, size = 30) {
    const c = S.catById[cid], m = members(cid);
    const seen = new Set();
    const looks = (m.length > 1 ? m : c.cardList ? listItems(cid).map(look) : [c])
      .filter((l) => { const k = l.icon + l.color; return !seen.has(k) && seen.add(k); });
    if (looks.length < 2) return catDot(c, size);
    return `<span class="dot-stack" style="--n:${looks.length}">` +
      looks.map((l, i) => catDot(l, size).replace('style="', `style="z-index:${looks.length - i};`)).join('') + '</span>';
  }
  // a cardList category's items in card order (item.order, then floor, then name)
  const listItems = (cid) => S.items.filter((i) => inCat(i, cid))
    .sort((x, y) => (x.order ?? 999) - (y.order ?? 999) || (S.floorById[x.floor].order ?? 0) - (S.floorById[y.floor].order ?? 0) || x.name.localeCompare(y.name));

  // Chip groups: a category with chipWith shows on that category's chip, so
  // selecting "Stairs & lifts" (S.cat = 'stairs') highlights the lifts too.
  const members = (cid) => [S.catById[cid], ...S.cats.filter((c) => c.chipWith === cid)].filter(Boolean);
  // an item's own colour/icon (item.color, item.icon) over its category's: the
  // fairs share a category but keep their printed colours
  const look = (it) => { const c = S.catById[it.category]; return { ...c, color: it.color || c.color, icon: it.icon || c.icon }; };
  const inCat = (it, cid) => it.category === cid || S.catById[it.category].chipWith === cid;
  const chipOf = (cid) => (S.catById[cid] && S.catById[S.catById[cid].chipWith] ? S.catById[cid].chipWith : cid);
  const catTitle = (c) => (members(c.id).length > 1 && c.chipLabel) || c.label;

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

  // all areas of an item: `shape` plus optional `shapes` (one item, several rooms)
  function itemPolys(it) {
    return [it.shape, ...(Array.isArray(it.shapes) ? it.shapes : [])].map(shapePoints).filter(Boolean);
  }
  function shapePoints(s) {
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
  function isDark(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
    if (!m) return false;
    const n = parseInt(m[1], 16);
    return (0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255 < 0.45;
  }
  function polyArea(pts) {
    let a = 0;
    for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) a += (pts[j][0] + pts[i][0]) * (pts[j][1] - pts[i][1]);
    return Math.abs(a / 2);
  }

  // ---------------------------------------------------------------- state
  const S = {
    data: null, floors: [], floorById: {}, cats: [], catById: {}, items: [], itemById: {},
    floor: null, cat: null, item: null, allFloors: true,
    view: { k: 1, x: 0, y: 0 }, fitK: 1, pulseAt: 0, ready: false,
    allLabels: false,
  };
  try { S.allLabels = localStorage.getItem('venueMap.allLabels') === '1'; } catch (e) { /* private mode */ }
  // First-time hint: the card's round icon pulses gently on every new
  // selection until it has been tapped once (remembered on this phone).
  let dotSeen = false, hintKey = '', hintAt = 0;
  const HINT_MS = 5000; // 0.5 s wait + 3 rings of 1.5 s
  try { dotSeen = localStorage.getItem('venueMap.dotSeen') === '1'; } catch (e) { /* private mode */ }
  const svg = $('svg'), mapEl = $('map');
  let vp, bgLayer, greyLayer, fullLayer, dimRect, maskG, hlLayer, labelLayer, traceLayer, clipG, markerLayer;
  // ?outline=1 draws the old outline around highlighted areas (for comparing)
  const OUTLINE = new URLSearchParams(location.search).get('outline') === '1';
  const bgs = {};

  // ---------------------------------------------------------------- theme
  // Auto (follow the phone) / Light / Dark. The choice is <html data-theme>,
  // set before the page draws by the line in index.html; the map uses the
  // floor's `dark` pictures while the page is dark.
  const THEMES = ['auto', 'light', 'dark'];
  const darkMq = matchMedia('(prefers-color-scheme: dark)');
  const themeChoice = () => document.documentElement.dataset.theme || 'auto';
  const pageIsDark = () => themeChoice() === 'dark' || (themeChoice() === 'auto' && darkMq.matches);
  let mapDark = pageIsDark();
  // the picture for a floor in the current theme (light one if there's no dark copy)
  const pic = (f, key) => (mapDark && f.dark && f.dark[key]) || f[key];

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
    // ?cat= takes a category's playful link word ("hungry") or, for old links, its id
    S.catByLink = {};
    S.cats.forEach((c) => (S.catByLink[c.id] = c));
    S.cats.forEach((c) => c.link && (S.catByLink[c.link] = c));
    // categories merged into this one (Org fair + Project fair -> fairs): their links still work
    S.cats.forEach((c) => (c.oldLinks || []).forEach((w) => (S.catByLink[w] = S.catByLink[w] || c)));
    S.items = (data.items || []).filter((it) => it && it.id && S.floorById[it.floor] && S.catById[it.category] && Array.isArray(it.pin));
    S.items.forEach((it) => {
      S.itemById[it.id] = it;
      it._polys = itemPolys(it);
      it._pts = it._polys.length ? it._polys.flat() : null; // all corner points (bounds, "has a shape")
      it._area = it._polys.reduce((a, p) => a + polyArea(p), 0);
      const cat = S.catById[it.category];
      it._name = norm(it.name);
      it._hay = norm([it.name, ...(it.aliases || []), it.description, cat.label, ...(cat.aliases || [])].join(' '));
      it._compact = it._hay.replace(/ /g, '');
    });
    if (!S.floors.length) { $('loading').textContent = 'The map has no floors yet.'; return; }

    buildSvg();
    buildFloorTabs();
    buildChips();
    showUpdated(data.updated);
    bindMap();
    bindSearch();
    bindTheme();

    // deep links: p/<item>/ (or the older ?item=)  or  ?floor= & cat=, plus ?here= (QR code
    // on a sign: "You are here" at that item's spot, kept while browsing)
    const q = new URLSearchParams(location.search);
    const item = S.itemById[pathItem() || q.get('item')];
    const floor = S.floorById[q.get('floor')];
    const cat = S.catByLink[q.get('cat')];
    S.here = S.itemById[q.get('here')] || null;
    S.hereAt = performance.now();
    if (S.here) setTimeout(placeMarkers, HERE_TAG_MS + 50);
    setFloor((item && item.floor) || (floor && floor.id) || (S.here && S.here.floor) || S.floors[0].id, { noUrl: true });
    if (item) selectItem(item.id, { noUrl: true, instant: true });
    else if (cat) selectCat(cat.id, { noUrl: true, keepFloor: !!floor });
    else if (S.here) {
      const [cw, ch] = size(), k = S.fitK * 1.6;
      setView({ k, x: cw / 2 - k * S.here.pin[0], y: ch / 2 - k * S.here.pin[1] }, true);
    }
    S.ready = true;
  }
  const HERE_TAG_MS = 8000;
  // the items plus the "You are here" spot when it is on this floor
  const withHere = (items) => (S.here && S.here.floor === S.floor && !items.includes(S.here) ? [...items, S.here] : items);

  function showUpdated(iso) {
    const d = new Date(iso);
    if (!iso || isNaN(d)) return;
    const fmt = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
    $('updated').textContent = 'Map updated ' + fmt.format(d);
  }

  // ---------------------------------------------------------------- svg setup
  // Layers, bottom to top: background (muted when a full-colour copy exists),
  // grey copy of it (shown while something is selected), full-colour copy
  // clipped to the selection, light veil, highlight tint, printed labels
  // (vector: each part greyed/faded/hidden on its own, see renderLabels),
  // then screen-space markers.
  function buildSvg() {
    const defs = el('defs', {}, svg);
    const mask = el('mask', { id: 'hole', maskUnits: 'userSpaceOnUse' }, defs);
    maskG = el('g', {}, mask);
    clipG = el('clipPath', { id: 'sel', clipPathUnits: 'userSpaceOnUse' }, defs);
    vp = el('g', {}, svg);
    bgLayer = el('g', {}, vp);
    greyLayer = el('g', { class: 'grey-layer' }, vp);
    fullLayer = el('g', { 'clip-path': 'url(#sel)' }, vp);
    dimRect = el('rect', { class: 'dim', mask: 'url(#hole)' }, vp);
    hlLayer = el('g', {}, vp);
    labelLayer = el('g', { class: 'label-layer' }, vp);
    svg.classList.toggle('dark', mapDark);
    traceLayer = el('g', { class: 'trace-layer' }, vp); // outline drawn by the card's round icon
    markerLayer = el('g', {}, svg); // screen space: markers keep their size when zooming
  }

  const fulls = {}, labs = {};
  const layerImg = (f, href, parent) => el('image', { x: 0, y: 0, width: f.width, height: f.height, preserveAspectRatio: 'none', href }, parent);
  function showOnly(store, id) { for (const [fid, im] of Object.entries(store)) im.style.display = fid === id ? '' : 'none'; }
  function ensureLayers(f) {
    if (f.labels && !labs[f.id]) labs[f.id] = /\.svg([?#]|$)/i.test(f.labels) ? vectorLabels(f) : layerImg(f, pic(f, 'labels'), labelLayer);
    showOnly(labs, f.id);
    showOnly(fulls, f.id);
    showOnly(greyBgs, f.id);
  }

  // Printed labels as vectors (maps/<floor>-labels.svg, made by the import).
  // The file's content goes into the map itself, so it stays sharp at any
  // zoom and each part can be greyed, faded or hidden on its own. The groups
  // inside its top-level <g> are tagged: data-i = ids of the items whose
  // label/pin it is, data-sel = shown only while that item is selected (Org
  // fair boxes), class="chrome" = title and legend. Colours are classes; the
  // file's own <style> has their grey (.off) and dark-mode (svg.dark) versions.
  // item.mapNote: a line of text under the item's printed label, left-aligned like it (the Org fair's
  // opening hours), in the label's colour class, as a run of its own tagged
  // with the item, so it greys, fades and recolours with the label
  function addMapNotes(f, g) {
    const top = [...g.children].find((n) => n.localName === 'g');
    if (!top) return;
    for (const it of S.items) {
      if (it.floor !== f.id || !it.mapNote || !Array.isArray(it.labelBoxes) || !it.labelBoxes.length) continue;
      const [x, y, w, h] = it.labelBoxes[it.labelBoxes.length - 1]; // the label itself
      const label = [...top.children].find((r) => (r.getAttribute('data-i') || '').split(' ').includes(it.id) && r.querySelector('use'));
      const cls = label?.querySelector('use')?.getAttribute('class') || '';
      const run = el('g', { 'data-i': it.id }, top);
      const t = el('text', { x, y: y + h + 13, class: `map-note ${cls}` }, run);
      t.textContent = it.mapNote;
    }
  }
  function vectorLabels(f) {
    const g = el('g', {}, labelLayer);
    fetch(f.labels).then((r) => { if (!r.ok) throw new Error(r.status); return r.text(); }).then((txt) => {
      const root = new DOMParser().parseFromString(txt, 'image/svg+xml').documentElement;
      if (root.localName !== 'svg') throw new Error('not an SVG');
      for (const n of [...root.childNodes]) g.appendChild(document.importNode(n, true));
      addMapNotes(f, g);
      const runs = [];
      for (const top of g.children) {
        if (top.localName !== 'g') continue;
        for (const r of top.children) {
          if (r.localName !== 'g') continue;
          r._ids = (r.getAttribute('data-i') || '').split(' ').filter(Boolean);
          r._sel = r.getAttribute('data-sel');
          r._chrome = r.classList.contains('chrome');
          runs.push(r);
        }
      }
      g._runs = runs;
      if (f.id === S.floor) render({ noUrl: true });
    }).catch((e) => console.error('labels', f.labels, e));
    return g;
  }

  // Grey copies of the plan, made in the browser (no extra download): while
  // something is selected, everything else loses its colour instead of being
  // darkened. Made once per floor, when the browser is idle.
  const greyBgs = {}, greyBusy = {};
  let greyGen = 0; // bumped when the theme changes: late copies of the old theme are dropped
  const GREY_BG_SAT = 0.12;
  function greyed(src, sat) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        try {
          const c = document.createElement('canvas');
          c.width = img.naturalWidth; c.height = img.naturalHeight;
          const ctx = c.getContext('2d', { willReadFrequently: true });
          ctx.drawImage(img, 0, 0);
          const d = ctx.getImageData(0, 0, c.width, c.height), a = d.data;
          for (let i = 0; i < a.length; i += 4) {
            const l = 0.299 * a[i] + 0.587 * a[i + 1] + 0.114 * a[i + 2];
            a[i] = l + (a[i] - l) * sat; a[i + 1] = l + (a[i + 1] - l) * sat; a[i + 2] = l + (a[i + 2] - l) * sat;
          }
          ctx.putImageData(d, 0, 0);
          c.toBlob((b) => (b ? resolve(URL.createObjectURL(b)) : reject(new Error('toBlob'))), 'image/webp', 0.85);
        } catch (e) { reject(e); }
      };
      img.onerror = reject;
      img.src = src;
    });
  }
  function prepareGrey(f) {
    if (greyBusy[f.id]) return;
    greyBusy[f.id] = true;
    const gen = greyGen;
    const idle = window.requestIdleCallback || ((fn) => setTimeout(fn, 200));
    const done = (store, layer) => (url) => {
      if (gen !== greyGen) { URL.revokeObjectURL(url); return; }
      const im = layerImg(f, url, layer);
      im.style.display = 'none'; // until ready, and only on its own floor
      im.addEventListener('load', () => {
        store[f.id] = im;
        ensureLayers(S.floorById[S.floor]);
        if (f.id === S.floor) render({ noUrl: true });
      }, { once: true });
    };
    idle(() => {
      if (gen !== greyGen) return;
      greyed(pic(f, 'background'), GREY_BG_SAT).then(done(greyBgs, greyLayer)).catch(() => {});
    });
  }
  // the full-colour copy is only fetched once something on that floor is highlighted
  function ensureFull(f) {
    if (f.backgroundHighlight && !fulls[f.id]) fulls[f.id] = layerImg(f, pic(f, 'backgroundHighlight'), fullLayer);
    showOnly(fulls, f.id);
  }
  function ensureBg(f) {
    if (bgs[f.id]) return bgs[f.id];
    const img = layerImg(f, pic(f, 'background'), bgLayer);
    img.addEventListener('load', () => { if (f.id === S.floor) $('loading').hidden = true; });
    // a dropped download (venue Wi-Fi): try again by itself, three times
    let tries = 0;
    img.addEventListener('error', () => {
      if (tries < 3) {
        tries++;
        setTimeout(() => img.setAttribute('href', `${pic(f, 'background')}${pic(f, 'background').includes('?') ? '&' : '?'}retry=${tries}`), 800 * tries);
      } else if (f.id === S.floor) $('loading').textContent = 'Could not load this floor plan. Check your connection and reload.';
    });
    bgs[f.id] = img;
    return img;
  }

  // the theme changed: swap every floor picture already made, redo the grey copies
  function applyMapTheme() {
    const dark = pageIsDark();
    syncThemeBtn();
    if (dark === mapDark) return;
    mapDark = dark;
    svg.classList.toggle('dark', dark); // vector labels recolour through CSS
    if (!S.ready && !S.floors.length) return;
    for (const [store, key] of [[bgs, 'background'], [fulls, 'backgroundHighlight'], [labs, 'labels']]) {
      for (const [fid, im] of Object.entries(store)) if (im.localName === 'image') im.setAttribute('href', pic(S.floorById[fid], key));
    }
    greyGen++;
    for (const [fid, im] of Object.entries(greyBgs)) {
      const url = im.getAttribute('href');
      im.remove();
      if (url && url.startsWith('blob:')) URL.revokeObjectURL(url);
      delete greyBgs[fid];
    }
    for (const fid of Object.keys(greyBusy)) delete greyBusy[fid];
    const f = S.floorById[S.floor];
    if (f) { prepareGrey(f); render({ noUrl: true }); }
  }
  const THEME_TEXT = { auto: 'Colours: automatic (like your phone)', light: 'Colours: light', dark: 'Colours: dark' };
  function syncThemeBtn() {
    const b = $('themeBtn'), t = themeChoice();
    b.dataset.mode = t;
    b.title = THEME_TEXT[t] + ' – tap to change';
    b.setAttribute('aria-label', THEME_TEXT[t] + '. Tap to change.');
    const bar = pageIsDark() ? '#16181d' : '#ffffff';
    for (const m of document.querySelectorAll('meta[name="theme-color"]')) m.setAttribute('content', bar);
  }
  function bindTheme() {
    $('themeBtn').addEventListener('click', () => {
      const next = THEMES[(THEMES.indexOf(themeChoice()) + 1) % THEMES.length];
      if (next === 'auto') delete document.documentElement.dataset.theme;
      else document.documentElement.dataset.theme = next;
      try { if (next === 'auto') localStorage.removeItem('venueMap.theme'); else localStorage.setItem('venueMap.theme', next); } catch (e) { /* ignore */ }
      applyMapTheme();
      toast({ auto: 'Colours follow your phone', light: 'Light colours', dark: 'Dark colours' }[next], 1600);
    });
    darkMq.addEventListener('change', applyMapTheme);
    syncThemeBtn();
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
      if (f.color) b.style.setProperty('--fc', f.color);
      // tapping the floor you're on again = show the whole floor
      b.addEventListener('click', () => { if (f.id === S.floor) fit(false); else { S.cameFrom = null; setFloor(f.id); } });
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
    prepareGrey(f);
    const hole = svg.querySelector('#hole');
    hole.setAttribute('x', 0); hole.setAttribute('y', 0); hole.setAttribute('width', f.width); hole.setAttribute('height', f.height);
    if (changed || opts.refit) fit(true);
    // back on the "You are here" floor: show the tag again for a moment
    if (changed && S.ready && S.here && S.here.floor === id) { S.hereAt = performance.now(); setTimeout(placeMarkers, HERE_TAG_MS + 50); }
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
  // free part of the map: the card at the bottom floats over it
  function freeBox() {
    const [cw, ch] = size();
    const sh = $('sheet');
    const bottom = sh.hidden ? 0 : sh.offsetHeight + 8;
    return { x0: 0, y0: 44, x1: cw, y1: Math.max(ch * 0.4, ch - bottom) }; // y0: below the Aa button
  }
  // Bring one item into view. Zoom in (to at least 2.2 × the whole-floor
  // zoom), but never so far that part of its outline is off screen: a big
  // room like the Arnheim-Foyer must look big. Rooms are centred on their
  // outline, things with only a pin on the pin.
  function centreOn(it, instant) {
    const fb = freeBox(), m = 36; // margin: room for the marker above the pin
    let k = Math.max(S.view.k, S.fitK * 2.2);
    let cx = it.pin[0], cy = it.pin[1];
    const b = it._pts && bounds([it]);
    if (b) {
      const fitWhole = Math.min((fb.x1 - fb.x0 - 2 * m) / Math.max(b.x1 - b.x0, 1), (fb.y1 - fb.y0 - 2 * m) / Math.max(b.y1 - b.y0, 1));
      k = Math.max(Math.min(k, fitWhole), S.fitK * 0.6);
      cx = (b.x0 + b.x1) / 2; cy = (b.y0 + b.y1) / 2;
    }
    setView({ k, x: (fb.x0 + fb.x1) / 2 - k * cx, y: (fb.y0 + fb.y1) / 2 - k * cy }, instant);
  }
  // world-space bounds of some items (shapes, else pins)
  function bounds(items) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const it of items) for (const [x, y] of it._pts || [it.pin]) {
      x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y);
    }
    return isFinite(x0) ? { x0, y0, x1, y1 } : null;
  }
  // how many of these items are (at least partly) on screen right now
  function countVisible(items) {
    const fb = freeBox(), { k, x, y } = S.view;
    return items.filter((it) => {
      const b = bounds([it]);
      return x + k * b.x1 > fb.x0 && x + k * b.x0 < fb.x1 && y + k * b.y1 > fb.y0 && y + k * b.y0 < fb.y1;
    }).length;
  }
  // Bring all these items on screen with as little movement as possible:
  // keep the zoom if they fit, else zoom out just enough; then pan the least.
  function showItems(items, instant) {
    const b = bounds(items);
    if (!b) return;
    const fb = freeBox(), m = 36; // margin: room for pins drawn above their spot
    const aw = fb.x1 - fb.x0 - 2 * m, ah = fb.y1 - fb.y0 - 2 * m;
    let { k, x, y } = S.view;
    const need = Math.min(aw / Math.max(b.x1 - b.x0, 1), ah / Math.max(b.y1 - b.y0, 1));
    if (k > need) {
      // zoom out around the middle of the free area
      const cx = (fb.x0 + fb.x1) / 2, cy = (fb.y0 + fb.y1) / 2;
      const nk = Math.max(need, S.fitK * 0.6);
      x = cx - (cx - x) * (nk / k); y = cy - (cy - y) * (nk / k); k = nk;
    }
    const sx0 = x + k * b.x0, sx1 = x + k * b.x1, sy0 = y + k * b.y0, sy1 = y + k * b.y1;
    const lo = (a0, a1, l, h) => (a1 - a0 > h - l ? (l + h) / 2 - (a0 + a1) / 2 : a0 < l ? l - a0 : a1 > h ? h - a1 : 0);
    x += lo(sx0, sx1, fb.x0 + m, fb.x1 - m);
    y += lo(sy0, sy1, fb.y0 + m, fb.y1 - m);
    setView({ k, x, y }, instant);
  }

  // ---------------------------------------------------------------- render
  function render(opts = {}) {
    const f = S.floorById[S.floor];
    const cat = S.cat && S.catById[S.cat];
    // floor tabs
    const floorsWithCat = new Set(cat ? S.items.filter((i) => inCat(i, cat.id)).map((i) => i.floor) : []);
    document.querySelectorAll('#floors button').forEach((b) => {
      const on = b.dataset.floor === S.floor;
      b.setAttribute('aria-selected', on);
      b.tabIndex = on ? 0 : -1;
      const dot = floorsWithCat.has(b.dataset.floor);
      b.innerHTML = `<span>${esc(S.floorById[b.dataset.floor].shortName || S.floorById[b.dataset.floor].name)}</span>` +
        (dot ? `<span class="has" style="background:${cat.color || 'currentColor'}" title="Has ${esc(catTitle(cat))}"></span>` : '');
    });
    // chips
    document.querySelectorAll('.chip').forEach((b) => b.setAttribute('aria-pressed', b.dataset.cat === S.cat));

    // which items are emphasised
    if (S.way && S.floor !== S.way.from) S.way = null; // went to another floor: the way hint is done
    let hl = [];
    if (S.item) hl = [S.itemById[S.item]];
    else if (S.way) hl = [...S.way.lifts, ...S.way.stairs];
    else if (cat) hl = S.items.filter((i) => inCat(i, cat.id) && i.floor === f.id);
    const dimOn = !!(S.item || cat || S.way);
    const layered = !!f.backgroundHighlight;
    dimRect.style.opacity = dimOn ? 1 : 0;
    dimRect.classList.toggle('light', layered);
    greyLayer.style.opacity = dimOn && greyBgs[f.id] ? 1 : 0;
    const outline = OUTLINE || !layered; // with a full-colour copy the colour itself is the highlight

    maskG.innerHTML = '';
    hlLayer.innerHTML = '';
    // the selection changed: stop the outline of the old one
    const same = S.hl && S.hl.length === hl.length && hl.every((it, i) => S.hl[i] === it);
    if (!same) { clearTimeout(traceT); traceLayer.innerHTML = ''; }
    clipG.innerHTML = '';
    el('rect', { x: 0, y: 0, width: f.width, height: f.height, fill: '#fff' }, maskG);
    if (layered && hl.some((i) => i._pts)) ensureFull(f);
    for (const it of hl) {
      const c = look(it).color || '#e33';
      if (it._polys.length) {
        for (const poly of it._polys) {
          const d = poly.map((p) => p.join(',')).join(' ');
          el('polygon', { points: d, fill: '#000' }, maskG);
          el('polygon', { points: d }, clipG);
          if (outline) el('polygon', { points: d, class: 'hl-halo' }, hlLayer);
          // dark category colours (e.g. rooms) would darken the area: brighten it instead
          el('polygon', { points: d, class: 'hl' + (layered ? ' over-full' : '') + (isDark(c) ? ' lighten' : '') + (outline ? '' : ' no-line'), fill: c, stroke: c }, hlLayer);
        }
      } else if (!f.labels) {
        // no separate label layer: reveal the printed pin through the veil
        el('circle', { cx: it.pin[0], cy: it.pin[1], r: 40 / S.view.k, fill: '#000' }, maskG);
      }
    }
    S.hl = hl;
    renderLabels(f, hl, dimOn);
    $('labelsBtn').setAttribute('aria-pressed', S.allLabels);
    const lt = S.allLabels ? 'Fade labels of other things' : 'Show all labels as printed';
    $('labelsBtn').title = lt; $('labelsBtn').setAttribute('aria-label', lt);
    $('labelsBtn').hidden = !f.labels;
    applyView();
    renderSheet(hl, cat, floorsWithCat);
    if (!$('search').hidden) {
      if (S.searchCat !== S.cat) { $('onlyCat').checked = true; syncCatToggle(); runSearch(); }
      else if (S.searchFloor !== S.floor) runSearch(); // follow the floor you switched to
    }
    if (!opts.noUrl && S.ready) updateUrl();
  }

  // Which printed labels show, and how (classes: style.css, colours: the SVG's
  // own <style>). While something is selected, everything that isn't one of
  // its labels turns grey and faded (.off); the title and legend are always
  // faint (.faint); things printed only for a selection (Org fair boxes) are
  // hidden otherwise. "Aa" (S.allLabels) shows everything exactly as printed.
  function renderLabels(f, hl, selecting) {
    const lab = labs[f.id];
    if (!lab) return;
    const all = S.allLabels;
    if (!lab._runs) {
      // a picture of the labels (not made by this import): fade it as a whole
      if (lab.localName === 'image') lab.style.opacity = all || !selecting ? 1 : 0.55;
      return;
    }
    const on = new Set(selecting ? hl.map((i) => i.id) : []);
    for (const r of lab._runs) {
      const mine = r._sel ? on.has(r._sel) : r._ids.some((id) => on.has(id));
      r.classList.toggle('hidden', !all && !!r._sel && !mine);
      r.classList.toggle('off', !all && selecting && !mine);
      r.classList.toggle('faint', !all && r._chrome);
    }
  }

  // where a marker's tip goes: top middle of the printed label box that
  // contains the pin, else the pin itself
  function markerSpot(it) {
    const [px, py] = it.pin;
    const b = (it.labelBoxes || []).find(([bx, by, bw, bh]) => px >= bx && px <= bx + bw && py >= by && py <= by + bh);
    return b ? [b[0] + b[2] / 2, b[1]] : it.pin;
  }
  function placeMarkers() {
    markerLayer.innerHTML = '';
    const { k, x, y } = S.view;
    if (S.here && S.here.floor === S.floor) {
      // "You are here": blue dot with a label, always on top of the plan
      const g = el('g', { class: 'here', transform: `translate(${x + k * S.here.pin[0]} ${y + k * S.here.pin[1]})` }, markerLayer);
      el('circle', { class: 'here-halo', r: 16 }, g);
      el('circle', { class: 'here-dot', r: 8 }, g);
      // the tag only for the first seconds: after that it would hide printed labels
      if (performance.now() - S.hereAt < HERE_TAG_MS) {
        // keep the tag on screen when the dot is near an edge
        const sx = x + k * S.here.pin[0], cw = size()[0];
        const dx = Math.min(Math.max(sx, 48), cw - 48) - sx;
        el('rect', { class: 'here-tag', x: dx - 44, y: 14, width: 88, height: 22, rx: 11 }, g);
        el('text', { class: 'here-text', x: dx, y: 25.5 }, g).textContent = 'You are here';
      }
    }
    if (!S.hl) return;
    for (const it of S.hl) {
      // printed pins/labels already show where things are; a marker only for
      // the searched/tapped item, or things with nothing printed on the plan
      if (S.item !== it.id && (it.labelBoxes?.length || it._pts)) continue;
      const cat = look(it);
      const ripple = S.item === it.id && !it._polys.length && performance.now() - S.pulseAt < 3500;
      if (cat.marker === false) {
        // the plan prints its own pin here (meeting points): a second one
        // beside it only confuses. Ripple round the printed pin instead.
        if (ripple) {
          const [px, py] = it.pin;
          const b = (it.labelBoxes || []).find(([bx, by, bw, bh]) => px >= bx && px <= bx + bw && py >= by && py <= by + bh);
          const [cx, cy] = b ? [b[0] + b[2] / 2, b[1] + b[3] / 2] : it.pin;
          el('circle', { class: 'pulse', cx: x + k * cx, cy: y + k * cy, r: 14 }, markerLayer);
        }
        continue;
      }
      // the pin is often the middle of the printed name: then stand on top of
      // the name (its label box), so the marker never covers it
      const [ax, ay] = markerSpot(it);
      const sx = x + k * ax, sy = y + k * ay - (ay !== it.pin[1] ? 2 : 0);
      // ripple only where nothing else shows it: a highlighted room needs none
      if (ripple) el('circle', { class: 'pulse', cx: sx, cy: sy, r: 14 }, markerLayer);
      // teardrop: the tip is exactly on the spot, the head floats above it
      const g = el('g', { class: 'marker', transform: `translate(${sx} ${sy})` }, markerLayer);
      el('path', { class: 'bg', d: 'M0 0C-3-7-14-13-14-24a14 14 0 1 1 28 0C14-13 3-7 0 0z', fill: cat.color || '#555' }, g);
      if (ICONS[cat.icon]?.emoji) el('circle', { cx: 0, cy: -24, r: 10.5, fill: '#fff' }, g);
      const ig = el('g', { class: 'glyph', transform: 'translate(-9 -33) scale(0.75)' }, g);
      ig.innerHTML = iconMarkup(cat.icon);
    }
  }

  // bottom sheet: selected item, or category summary / empty state
  function renderSheet(hl, cat, floorsWithCat) {
    const sh = $('sheet');
    const close = `<button class="icon-btn close" aria-label="Clear"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6.4 5 5.6 5.6L17.6 5 19 6.4 13.4 12l5.6 5.6-1.4 1.4-5.6-5.6L6.4 19 5 17.6l5.6-5.6L5 6.4z"/></svg></button>`;
    // a pill per floor; the one you're on has the same hairline as its floor tab
    const pill = (f) => `<button data-goto="${esc(f.id)}"${f.id === S.floor ? ' class="cur"' : ''} style="--fc:${esc(f.color || 'transparent')}">${esc(f.name)}</button>`;
    const floorPills = (ids) => S.floors.filter((f) => ids.has(f.id)).map(pill).join('');
    if (!S.item && S.way) {
      const w = S.way, it = S.itemById[w.item], tf = S.floorById[w.to];
      const ff = S.floorById[w.from];
      const dir = (tf.order ?? 0) > (ff.order ?? 0) ? 'up' : 'down';
      const opt = (arr, cid, one) => (arr.length ? `<b style="color:${esc(S.catById[cid]?.color || 'inherit')}">${one}</b>` : '');
      const via = w.via ? ` (they go to the ${esc(S.floorById[w.via].name)}: change there)` : '';
      const parts = [opt(w.lifts, 'lifts', 'lift'), opt(w.stairs, 'stairs', 'stairs') + via].filter(Boolean);
      const txt = parts.length
        ? `Take the ${parts.join(' or the ')} ${dir} to the ${esc(tf.name)}.`
        : `No lift or stairs on this floor are marked as going to the ${esc(tf.name)}. Ask at the Info Desk.`;
      sh.innerHTML = `<div class="grow"><div class="name">To ${esc(it.name)}</div><div class="sub">${txt}</div>` +
        `<div class="links strong"><button data-goitem="${esc(it.id)}">Go to the ${esc(tf.name)}</button></div></div>${close}`;
    } else if (S.item) {
      const it = S.itemById[S.item], c = S.catById[it.category];
      const g = S.catById[chipOf(c.id)]; // lifts: "All Stairs & lifts"
      const n = S.items.filter((i) => inCat(i, g.id)).length;
      const allBtn = g.chip !== false && n > 1 ? `<button data-cat="${esc(g.id)}">All ${esc(catTitle(g))} (${n})</button>` : '';
      // item.links: buttons that open a web page (e.g. directions to the entrance)
      const ext = (Array.isArray(it.links) ? it.links : []).filter((l) => l && l.label && /^https:\/\//.test(l.url))
        .map((l) => `<a href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.label)}</a>`).join('');
      const links = `<div class="links">${shareBtn(it.id)}${ext}${allBtn}</div>`;
      sh.innerHTML = `${dotBtn(look(it), 'Show it on the map')}<div class="grow"><div class="name">${esc(it.name)}</div>` +
        `<div class="sub">${esc([it.description, c.label, S.floorById[it.floor].name].filter(Boolean).join(' · '))}</div>${links}</div>${close}`;
    } else if (cat) {
      const n = hl.length;
      const pills = floorPills(floorsWithCat);
      const title = catTitle(cat), group = members(cat.id);
      const here = S.floorById[S.floor].name;
      const none = `<span class="none">No ${esc(title)} on the ${esc(here)}</span>`;
      if (!floorsWithCat.size) {
        sh.innerHTML = `${catDot(cat)}<div class="grow"><div class="name">${esc(title)}: not on the map yet.</div></div>${close}`;
      } else if (cat.cardList) {
        // one line per item, with its floor (Fairs & booths: each fair is on one floor)
        const list = listItems(cat.id);
        // tapping a name shows it (on its floor) and stays on this card; the link icon shares it
        const rows = list.map((i) => `<li><button class="item-name" data-zoom="${esc(i.id)}" title="Show it on the map">${catDot(look(i), 26)}<span>${esc(i.name)}</span></button>` +
          `<span class="links">${shareBtn(i.id)}${pill(S.floorById[i.floor])}</span></li>`).join('');
        sh.innerHTML = `<div class="grow"><div class="name">${esc(title)}</div><ul class="item-lines">${rows}</ul></div>${close}`;
      } else if (group.length > 1) {
        // a line per category, each with its own round icon (Stairs 3 / Lifts 1)
        const rows = group.map((c) => {
          const k = hl.filter((i) => i.category === c.id).length;
          return `<li>${k ? dotBtn(c, `Show the ${c.label} on this floor`, c.id) : catDot(c)}<span>${esc(c.label)}: <b>${k || '<span class="muted">none on this floor</span>'}</b></span></li>`;
        }).join('');
        sh.innerHTML = `<div class="grow"><div class="name">${n ? `${esc(title)} on the ${esc(here)}` : none}</div>` +
          `<ul class="cat-lines">${rows}</ul><div class="links">${pills}</div></div>${close}`;
      } else {
        sh.innerHTML = (n ? dotBtn(cat, `Show all ${title} on this floor`) : catDot(cat)) +
          `<div class="grow"><div class="name">${n ? `${esc(title)}: ${n} on this floor` : none}</div>` +
          `<div class="links">${pills}</div></div>${close}`;
      }
    } else {
      sh.hidden = true;
      return;
    }
    sh.hidden = false;
    sh.querySelector('.close').onclick = () => { S.item = null; S.cat = null; S.way = null; render(); };
    sh.querySelectorAll('[data-way]').forEach((b) => (b.onclick = () => showWay(S.item, b.dataset.way)));
    sh.querySelectorAll('[data-goitem]').forEach((b) => (b.onclick = () => { const from = S.floor; S.way = null; selectItem(b.dataset.goitem); S.cameFrom = from; render(); }));
    sh.querySelectorAll('[data-goto]').forEach((b) => (b.onclick = () => setFloor(b.dataset.goto)));
    sh.querySelectorAll('[data-cat]').forEach((b) => (b.onclick = () => selectCat(b.dataset.cat, { force: true, keepFloor: true })));
    const dots = [...sh.querySelectorAll('.dot-btn')], dot = dots[0];
    if (dot && !dotSeen) {
      // once per selection (HINT_MS, see .dot-btn.hint in style.css). The card is
      // redrawn now and then (pictures loading, Aa …): the rings carry on where
      // they were instead of starting again or stopping.
      const key = S.item || 'cat:' + S.cat;
      if (key !== hintKey) { hintKey = key; hintAt = performance.now(); }
      const t = performance.now() - hintAt;
      if (t < HINT_MS) {
        dot.classList.add('hint');
        dot.style.setProperty('--hint', (S.item ? look(S.itemById[S.item]) : S.catById[dot.dataset.dot] || cat).color || 'var(--accent)');
        dot.style.setProperty('--hint-delay', (500 - t) / 1000 + 's');
      }
    }
    // round icon: show and outline what the card is about (data-dot: only that category,
    // e.g. the lifts on the Stairs & lifts card)
    dots.forEach((d) => (d.onclick = () => {
      if (!dotSeen) {
        dotSeen = true;
        dots.forEach((x) => x.classList.remove('hint'));
        try { localStorage.setItem('venueMap.dotSeen', '1'); } catch (e) { /* ignore */ }
      }
      const items = d.dataset.dot ? S.hl.filter((i) => i.category === d.dataset.dot) : S.hl;
      if (S.item) { S.pulseAt = performance.now(); centreOn(S.itemById[S.item]); setTimeout(placeMarkers, 3600); }
      else showItems(withHere(items));
      traceOutlines(items);
    }));
    sh.querySelectorAll('[data-share]').forEach((b) => (b.onclick = () => shareItem(S.itemById[b.dataset.share])));
    // a line of a list card: go to its floor and outline it. Like the round
    // icons: keep the zoom unless it doesn't fit, pan only if needed
    sh.querySelectorAll('[data-zoom]').forEach((b) => (b.onclick = () => {
      const it = S.itemById[b.dataset.zoom];
      if (it.floor !== S.floor) setFloor(it.floor);
      showItems([it]);
      traceOutlines([it]);
    }));
  }
  // the classic chain-link icon: share sheet on phones, copy the link elsewhere
  function shareBtn(id) {
    const label = navigator.share ? 'Share' : 'Copy link';
    return `<button class="link-btn" data-share="${esc(id)}" aria-label="${label}" title="${label}">` +
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z"/></svg></button>';
  }
  // Draw an outline around the things the card shows, keep it a moment, then
  // fade it out (timing: .trace in style.css). Shapes get their outline,
  // things with only a pin a circle around it.
  // quick = on selecting something: shorter, and only for things with a shape
  // (a pin gets its ripple instead). The card's round icon plays the full one.
  // The dash runs along pathLength="1", so it closes exactly once round at any
  // zoom. That only works with a stroke in map units: with
  // vector-effect: non-scaling-stroke browsers measure the dash on screen and
  // the outline stopped short (zoomed in) or wrapped round (zoomed out).
  // So the line width is set per zoom instead.
  const TRACE_MS = 2000; // draw 1 s + stay 0.5 s + fade 0.5 s
  const TRACE_QUICK_MS = 1200; // draw 0.6 s + stay 0.25 s + fade 0.35 s (.trace.quick)
  let traceT = 0;
  function traceOutlines(items, quick) {
    clearTimeout(traceT);
    traceLayer.innerHTML = '';
    const k = animState ? animState.to.k : S.view.k; // the zoom it is moving to
    const cls = quick ? ' quick' : '';
    for (const it of items || []) {
      if (quick && !it._polys.length) continue;
      const c = look(it).color || '#e33';
      const shapes = it._polys.length
        ? it._polys.map((poly) => ['polygon', { points: poly.map((q) => q.join(',')).join(' ') }])
        : [['circle', { cx: it.pin[0], cy: it.pin[1], r: 26 / k }]];
      for (const [tag, a] of shapes) {
        el(tag, { ...a, class: 'trace-halo' + cls, pathLength: 1, 'stroke-width': 8 / k }, traceLayer);
        el(tag, { ...a, class: 'trace' + cls, pathLength: 1, stroke: c, 'stroke-width': 4 / k }, traceLayer);
      }
    }
    traceT = setTimeout(() => (traceLayer.innerHTML = ''), (quick ? TRACE_QUICK_MS : TRACE_MS) + 100);
  }
  function dotBtn(c, label, only) {
    return `<button class="dot-btn"${only ? ` data-dot="${esc(only)}"` : ''} aria-label="${esc(label)}" title="${esc(label)}">${catDot(c)}</button>`;
  }
  // "meet me at C3": a link that opens the map on that spot
  function shareItem(it) {
    const url = new URL(itemPath(it.id), SITE).href; // its own page: the preview shows its name and floor
    const f = S.floorById[it.floor];
    if (navigator.share) {
      navigator.share({ title: it.name, text: `${it.name} (${f.name})`, url }).catch(() => {});
    } else if (navigator.clipboard) {
      navigator.clipboard.writeText(url).then(() => toast('Link copied'), () => toast(url, 5000));
    } else toast(url, 5000);
  }

  // short message in the middle of the map
  let toastT = 0;
  function toast(text, ms = 2200) {
    const t = $('toast');
    t.textContent = text;
    t.hidden = false;
    t.classList.remove('out');
    clearTimeout(toastT);
    toastT = setTimeout(() => { t.classList.add('out'); toastT = setTimeout(() => (t.hidden = true), 300); }, ms);
  }

  // ---------------------------------------------------------------- categories
  function buildChips() {
    const box = $('chips');
    box.innerHTML = '';
    for (const c of S.cats) {
      if (c.chip === false || (c.chipWith && S.catById[c.chipWith])) continue;
      const b = document.createElement('button');
      b.className = 'chip';
      b.dataset.cat = c.id;
      b.innerHTML = `${groupDot(c.id, 32)}<span>${esc(catTitle(c))}</span>`;
      b.addEventListener('click', () => selectCat(c.id));
      box.appendChild(b);
    }
  }

  // "How to get here": on the floor you come from, highlight the lifts and
  // stairs that go to the item's floor (item.connects); with a "You are here"
  // dot on that floor, only the nearest lift and the nearest stairs.
  function wayFrom(from, to) {
    const order = (fid) => S.floorById[fid].order ?? 0;
    const on = (cid) => S.items.filter((i) => i.floor === from && i.category === cid && Array.isArray(i.connects));
    const direct = (cid) => on(cid).filter((i) => i.connects.includes(to));
    let lifts = direct('lifts'), stairs = direct('stairs'), via = null;
    if (!stairs.length) {
      // stairs that go part of the way: change floors on the way
      const up = order(to) > order(from);
      const toward = (fid) => (up ? order(fid) > order(from) && order(fid) < order(to) : order(fid) < order(from) && order(fid) > order(to));
      // only the ones that get closest, e.g. not the spiral stairs that stop a floor earlier
      const best = (i) => i.connects.filter((fid) => S.floorById[fid] && toward(fid)).sort((a, b) => Math.abs(order(to) - order(a)) - Math.abs(order(to) - order(b)))[0];
      const part = on('stairs').filter((i) => best(i) !== undefined);
      if (part.length) {
        via = part.map(best).sort((a, b) => Math.abs(order(to) - order(a)) - Math.abs(order(to) - order(b)))[0];
        stairs = part.filter((i) => best(i) === via);
      }
    }
    if (S.here && S.here.floor === from) {
      const near = (arr) => arr.length ? [arr.reduce((a, b) => (dist(a) <= dist(b) ? a : b))] : [];
      const dist = (i) => Math.hypot(i.pin[0] - S.here.pin[0], i.pin[1] - S.here.pin[1]);
      lifts = near(lifts); stairs = near(stairs);
    }
    return { lifts, stairs, via };
  }
  function showWay(itemId, from) {
    const it = S.itemById[itemId];
    if (!it || !S.floorById[from]) return;
    S.way = { item: it.id, from, to: it.floor, ...wayFrom(from, it.floor) };
    S.item = null; S.cat = null;
    if (S.floor !== from) setFloor(from); else render();
    requestAnimationFrame(() => { if (S.way && S.hl.length) showItems(withHere(S.hl)); });
  }

  function selectCat(id, opts = {}) {
    if (S.cat === id && !opts.force) { S.cat = null; render(opts); return; }
    S.cat = id;
    S.way = null;
    S.item = null;
    const c = S.catById[id];
    const floors = [...new Set(S.items.filter((i) => inCat(i, id)).map((i) => i.floor))];
    // "lives on one floor": explicit category.floor, or all its items are on one floor
    const target = (c.floor && S.floorById[c.floor]) ? c.floor : (floors.length === 1 ? floors[0] : null);
    if (target && target !== S.floor && !opts.keepFloor) {
      setFloor(target, opts);
      if (S.ready) toast(`${catTitle(c)}: ${S.floorById[target].name}`);
    } else {
      render(opts);
      if (S.ready) {
        // none of them on screen (zoomed into another corner): bring them in
        if (S.hl.length && !countVisible(S.hl)) requestAnimationFrame(() => showItems(withHere(S.hl)));
      }
    }
    const chip = document.querySelector(`.chip[data-cat="${CSS.escape(id)}"]`);
    if (chip) chip.scrollIntoView({ inline: 'nearest', block: 'nearest', behavior: reduceMotion ? 'auto' : 'smooth' });
  }

  function selectItem(id, opts = {}) {
    const it = S.itemById[id];
    if (!it) return;
    S.cat = null;
    S.way = null;
    S.item = id;
    S.pulseAt = performance.now();
    S.cameFrom = it.floor !== S.floor && S.ready ? S.floor : null;
    if (it.floor !== S.floor) {
      setFloor(it.floor, { noUrl: true });
      if (S.ready) toast(`Switched to the ${S.floorById[it.floor].name}`);
    }
    render(opts);
    centreOn(it, !!opts.instant);
    traceOutlines([it], true);
    setTimeout(placeMarkers, 3600); // drop the pulse ring after it finishes
  }

  function updateUrl() {
    const p = new URLSearchParams();
    if (!S.item) {
      if (S.floor !== S.floors[0].id) p.set('floor', S.floor);
      if (S.cat) p.set('cat', S.catById[S.cat].link || S.cat);
    }
    if (S.here) p.set('here', S.here.id);
    if (OUTLINE) p.set('outline', '1');
    const qs = p.toString();
    history.replaceState(null, '', new URL((S.item ? itemPath(S.item) : '') + (qs ? `?${qs}` : ''), SITE).href);
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
    // the floating card's height lifts the zoom button and the "updated" line
    const sheet = $('sheet');
    new ResizeObserver(() => mapEl.style.setProperty('--sheet-h', sheet.hidden ? '0px' : sheet.offsetHeight + 8 + 'px')).observe(sheet);
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
      if (d < bd && (!S.cat || inCat(it, S.cat))) { bd = d; best = it; }
    }
    // then a printed label (text), e.g. tapping "Nap Rooms"
    if (!best) {
      let ba = 4000; // pt²: only label-sized boxes, not whole areas
      const hits = [];
      for (const it of here) {
        if (S.cat && !inCat(it, S.cat)) continue;
        for (const [bx, by, bw, bh] of it.labelBoxes || []) {
          if (wx < bx || wx > bx + bw || wy < by || wy > by + bh || bw * bh > ba) continue;
          if (bw * bh < ba) { ba = bw * bh; hits.length = 0; }
          hits.push(it);
        }
      }
      // one label shared by several areas of one category (Org fair title): show the category
      if (hits.length > 1 && hits.every((i) => i.category === hits[0].category) && S.catById[chipOf(hits[0].category)].chip !== false) {
        selectCat(chipOf(hits[0].category), { force: true, keepFloor: true });
        return;
      }
      best = hits[0] || null;
    }
    if (!best) {
      const inside = here.filter((i) => i._polys.some((poly) => inPoly(wx, wy, poly)) && (!S.cat || inCat(i, S.cat)))
        .sort((a, b) => a._area - b._area);
      best = inside[0] || null;
    }
    if (best) {
      const changed = S.item !== best.id;
      S.item = best.id; S.way = null; S.pulseAt = 0; render();
      if (changed) traceOutlines([best], true);
    } else if (S.item) {
      S.item = null; render();
    }
  }

  // ---------------------------------------------------------------- search
  function bindSearch() {
    const panel = $('search'), btn = $('searchBtn'), input = $('q');
    const open = () => {
      panel.hidden = false; btn.setAttribute('aria-expanded', 'true');
      $('onlyCat').checked = true; // with a category selected, search starts within it
      syncCatToggle();
      runSearch();
      requestAnimationFrame(scrollToFloor); // some browsers restore the old scroll position on reopening
      if (!matchMedia('(pointer: coarse)').matches) input.focus(); // on phones the keyboard would cover the room list
    };
    const close = () => { panel.hidden = true; btn.setAttribute('aria-expanded', 'false'); };
    btn.addEventListener('click', () => (panel.hidden ? open() : close()));
    $('searchClose').addEventListener('click', close);
    input.addEventListener('input', runSearch);
    input.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter' || !norm(input.value)) return;
      const first = $('results').querySelector('button[data-item]');
      if (first) { e.preventDefault(); first.click(); }
    });
    $('allFloors').checked = S.allFloors;
    $('allFloors').addEventListener('change', (e) => { S.allFloors = e.target.checked; runSearch(); });
    $('onlyCat').addEventListener('change', runSearch);
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
      .sort((a, b) => a.score - b.score || (b.it.floor === S.floor) - (a.it.floor === S.floor) || // this floor first
        (S.floorById[a.it.floor].order ?? 0) - (S.floorById[b.it.floor].order ?? 0) || a.it.name.localeCompare(b.it.name, undefined, { numeric: true }))
      .map((r) => r.it);
  }

  // one result row; the left bar shows the floor's colour (floor.color)
  function resultRow(it, showFloor) {
    const c = look(it), f = S.floorById[it.floor];
    const sub = [it.description, showFloor ? f.name : ''].filter(Boolean).join(' · ');
    return `<li style="--floor:${esc(f.color || 'transparent')}"><button data-item="${esc(it.id)}">${catDot(c)}<span><span class="name">${esc(it.name)}</span>` +
      (sub ? `<br><span class="sub">${esc(sub)}</span>` : '') + `</span></button></li>`;
  }

  // the "Only <category>" toggle: shown while a category is selected on the map
  function syncCatToggle() {
    const cat = S.cat && S.catById[S.cat];
    $('onlyCatWrap').hidden = !cat;
    if (cat) $('onlyCatLabel').textContent = `Only ${catTitle(cat)}`;
    S.searchCat = S.cat;
  }
  const searchCat = () => (S.cat && $('onlyCat').checked ? S.cat : null);

  // empty search = every named room (or everything in the selected category),
  // grouped by floor, opened at the current floor
  const ROOM_CAT = 'rooms';
  function renderRoomList(ul, cat) {
    // rooms moved to another category (the Spontaneous Conversation Area, in Extra) keep their room-… id and stay listed
    const rooms = S.items.filter((i) => inCat(i, cat || ROOM_CAT) || (!cat && i.id.startsWith('room-')));
    if (!rooms.length) { ul.innerHTML = `<li class="hint">Type a room name or a meeting point like “C3”.</li>`; return; }
    const floors = S.allFloors ? S.floors : [S.floorById[S.floor]];
    ul.innerHTML = floors.map((f) => {
      const here = rooms.filter((i) => i.floor === f.id).sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
      if (!here.length) return '';
      return `<li class="floor-head" data-floor-head="${esc(f.id)}" style="--floor:${esc(f.color || 'transparent')}">${esc(f.name)}</li>` +
        here.map((it) => resultRow(it, false)).join('');
    }).join('') || `<li class="hint">None on this floor – <button data-all="1">show all floors</button></li>`;
    scrollToFloor();
  }
  // open the list at the current floor's heading
  function scrollToFloor() {
    const ul = $('results');
    const head = ul.querySelector(`[data-floor-head="${CSS.escape(S.floor)}"]`);
    ul.scrollTop = 0; // measure with nothing stuck (the headings are sticky)
    if (head) ul.scrollTop = head.offsetTop - ul.offsetTop;
  }

  function runSearch() {
    const q = $('q').value, ul = $('results');
    S.searchFloor = S.floor;
    const cat = searchCat();
    const all = search(q).filter((i) => !cat || inCat(i, cat));
    const list = S.allFloors ? all : all.filter((i) => i.floor === S.floor);
    if (!norm(q)) { renderRoomList(ul, cat); return; }
    let html = list.slice(0, 40).map((it) => resultRow(it, S.allFloors)).join('');
    const elsewhere = all.length - list.length;
    if (!S.allFloors && elsewhere > 0) {
      html += `<li class="hint">${list.length ? '' : 'Nothing on this floor. '}${elsewhere} more on other floors – <button data-all="1">search all floors</button></li>`;
    } else if (!all.length) {
      html = `<li class="hint">No matches for “${esc(q)}”${cat ? ` in ${esc(catTitle(S.catById[cat]))}` : ''}.</li>`;
    }
    ul.innerHTML = html;
  }
})();
