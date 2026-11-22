# Feature Spec: UI Overhaul — Decision-Focused Interface

## Goal
The map is strong. The rest of the UI — topbar, filters panel, society cards, compare, search — needs to help users make decisions faster. This spec covers 7 changes that work together.

---

## 1. Topbar cleanup — overflow menu

### Problem
9 buttons in the topbar. Most users don't need Guide/Replay/Tour/Hide after first visit. On mobile it's a horizontal scroll.

### Solution
Keep 4 primary actions visible: **Theme, Commute, Metro, Compare**. Move the rest into a "..." overflow menu.

### HTML change in `web/index.html`
Replace the topbar contents:
```html
<div class="topbar">
  <button id="btn-theme" title="Light or dark" aria-label="Switch theme"></button>
  <button id="btn-commute" title="Commute radius">Commute</button>
  <button id="btn-metro-search" title="Search along metro">Metro</button>
  <button id="btn-compare" title="Compare societies">Compare</button>
  <button id="btn-copyurl" title="Copy link to filters">Copy link</button>
  <div class="topbar-overflow">
    <button id="btn-overflow" title="More options" aria-label="More options">···</button>
    <div class="overflow-menu" id="overflow-menu" hidden>
      <button id="btn-guide">Guide</button>
      <button id="btn-replay">Replay intro</button>
      <button id="btn-tour">Fly through matches</button>
      <button id="btn-log">Research log</button>
      <button id="btn-hide">Hide panels</button>
    </div>
  </div>
  <button id="btn-mhide" class="mobile-only" title="Toggle panel">Hide panel</button>
</div>
```

### JS in `main.js`
```javascript
$('btn-overflow').onclick = () => {
  const menu = $('overflow-menu');
  menu.hidden = !menu.hidden;
};
document.addEventListener('click', (e) => {
  if (!e.target.closest('.topbar-overflow')) $('overflow-menu').hidden = true;
});
```

### CSS
```css
.topbar-overflow { position: relative; }
.overflow-menu {
  position: absolute; top: 100%; right: 0; z-index: 20;
  background: var(--glass-strong); border: 1px solid var(--line);
  border-radius: 8px; padding: 4px 0; min-width: 160px;
  backdrop-filter: blur(16px);
}
.overflow-menu button {
  display: block; width: 100%; text-align: left;
  padding: 8px 14px; background: none; border: none;
  color: var(--fg); font-size: 13px; cursor: pointer;
}
.overflow-menu button:hover { background: var(--line); }
```

### Don't touch
- Button functionality — same event handlers, just moved
- Mobile tab bar (mtabs)

---

## 2. Sort dropdown with optgroup categories

### Problem
13 sort options in a flat dropdown. Hard to scan.

### Solution
Group into categories using `<optgroup>`:

```html
<select id="f-sort" aria-label="Sort results">
  <optgroup label="Relevance">
    <option value="best">Best match</option>
    <option value="score">Property Finder score</option>
    <option value="rating">Resident rating</option>
  </optgroup>
  <optgroup label="Price">
    <option value="price">Price, low to high</option>
    <option value="listings">Most listings</option>
    <option value="trend-up">Price trend, fastest rising</option>
    <option value="trend-stable">Price trend, most stable</option>
  </optgroup>
  <optgroup label="Location">
    <option value="distance">Nearest to pin</option>
    <option value="station">Nearest to station</option>
    <option value="commute">Shortest drive</option>
  </optgroup>
  <optgroup label="Quality">
    <option value="liquidity">Resale liquidity</option>
    <option value="builder">Builder track record</option>
    <option value="greenery">Greenest first</option>
    <option value="rain-low">Least rainfall</option>
  </optgroup>
</select>
```

### CSS — style optgroups
```css
#f-sort optgroup { font-weight: 600; font-size: 11px; color: var(--muted); }
```

### Don't touch
- Sort logic in `sorted()` function — values unchanged

---

## 3. Compact score pills on card with expandable details

### Problem
Society cards show 6+ signal badges stacked vertically. With rainfall chart, a card can be 800px+ tall. Users scroll past useful info.

### Solution
Show a **compact score row** of small pills at the top of the card. Each pill is a coloured circle + number. Click "Show details" to expand full signals + rainfall chart.

### Card layout change
In `renderCard(s)`, after the header/price section, add a compact row:

```javascript
function scoreRow(s) {
  const pills = [];
  if (s.green_score != null) pills.push(pill('green', s.green_score, s.green_label, '#22c55e'));
  if (s.safety_score != null) pills.push(pill('safety', s.safety_score, s.safety_score > 70 ? 'Safe' : s.safety_score >= 40 ? 'Moderate' : 'Concern',
    s.safety_score > 70 ? '#22c55e' : s.safety_score >= 40 ? '#eab308' : '#ef4444'));
  if (s.noise_score != null) pills.push(pill('noise', s.noise_score, s.noise_score > 50 ? 'Noisy' : 'Quiet',
    s.noise_score > 50 ? '#f97316' : '#22c55e'));
  if (s.liquidity_score != null) pills.push(pill('liquidity', s.liquidity_score, s.liquidity_score >= 70 ? 'High' : s.liquidity_score >= 40 ? 'Medium' : 'Low',
    s.liquidity_score >= 70 ? '#22c55e' : s.liquidity_score >= 40 ? '#eab308' : '#ef4444'));
  if (s.rain_annual != null) pills.push(pill('rain', s.rain_annual, `${s.rain_annual} mm/yr`, '#3b82f6'));
  if (s.walk_score != null) pills.push(pill('walk', s.walk_score, 'Walk score', '#84cc16'));
  if (!pills.length) return '';
  return `<div class="score-pills">${pills.join('')}</div>`;
}

function pill(key, value, label, color) {
  return `<div class="score-pill" title="${label}: ${value}">
    <i style="background:${color}"></i>
    <span class="pill-val">${typeof value === 'number' && value > 999 ? Math.round(value) : value}</span>
    <span class="pill-label">${label}</span>
  </div>`;
}
```

Place it right after the header:
```javascript
${scoreRow(s)}
<details class="card-details">
  <summary>Show details</summary>
  ${signalRows(s).join('')}
  ${rainfallChart(s)}
  ${/* similar areas, builder info, etc. */}
</details>
```

### CSS
```css
.score-pills { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0; }
.score-pill {
  display: flex; align-items: center; gap: 4px;
  padding: 3px 8px; border-radius: 999px;
  background: var(--glass); font-size: 11px;
}
.score-pill i { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.pill-val { font-weight: 600; }
.pill-label { color: var(--muted); }
.card-details summary {
  cursor: pointer; font-size: 12px; color: var(--accent);
  padding: 6px 0; user-select: none;
}
.card-details summary::-webkit-details-marker { display: none; }
.card-details summary::before { content: '▸ '; }
.card-details[open] summary::before { content: '▾ '; }
```

### Don't touch
- The score pills are read-only — no new data computation
- Keep existing signalRows() as the expanded view

---

## 4. Search result previews

### Problem
Search dropdown shows only society names. No way to compare without clicking each one.

### Solution
Show 2-3 key metrics inline in search results.

### In the search result rendering (wherever `#q-results` items are built):
```javascript
function searchResultItem(s) {
  const price = s.psf_now ? `₹${Math.round(s.psf_now).toLocaleString()}/sqft` : '';
  const green = s.green_score != null ? `🌳${s.green_score}` : '';
  const safety = s.safety_score != null ? `🛡${s.safety_score}` : '';
  const meta = [price, green, safety].filter(Boolean).join(' · ');
  return `<li data-id="${s.id}">
    <div class="sr-name">${esc(s.name)}</div>
    <div class="sr-meta">${s.locality || ''} ${meta ? '· ' + meta : ''}</div>
  </li>`;
}
```

### CSS
```css
#q-results li { padding: 8px 12px; cursor: pointer; }
#q-results li:hover { background: var(--line); }
.sr-name { font-weight: 500; font-size: 13px; }
.sr-meta { font-size: 11px; color: var(--muted); margin-top: 2px; }
```

### Don't touch
- Search matching logic
- Keyboard navigation in results

---

## 5. Locality Dashboard view

### Problem
Users see society-level data but can't compare whole localities at a glance. "Should I look in Baner or Wakad?" has no quick answer.

### Solution
A "Localities" button in the topbar that opens a sortable table showing all localities with their average scores.

### HTML
Add button to topbar (primary group):
```html
<button id="btn-localities" title="Compare localities">Localities</button>
```

Add modal:
```html
<div class="modal" id="locality-modal" hidden>
  <div class="locality-sheet">
    <div class="k row">Locality Dashboard <button class="iconbtn" id="locality-close" aria-label="Close">×</button></div>
    <div class="locality-controls">
      <input type="search" id="loc-search" placeholder="Filter localities" aria-label="Filter localities">
      <select id="loc-sort" aria-label="Sort localities">
        <option value="count">Most societies</option>
        <option value="price-low">Price low to high</option>
        <option value="price-high">Price high to low</option>
        <option value="green">Greenest</option>
        <option value="safe">Safest</option>
        <option value="quiet">Quietest</option>
        <option value="liquid">Best liquidity</option>
        <option value="rain-low">Least rain</option>
      </select>
    </div>
    <div class="locality-table-wrap">
      <table class="locality-table">
        <thead>
          <tr>
            <th>Locality</th>
            <th>Societies</th>
            <th>Avg ₹/sqft</th>
            <th>Green</th>
            <th>Safety</th>
            <th>Noise</th>
            <th>Liquidity</th>
            <th>Rain mm/yr</th>
            <th>Walk</th>
          </tr>
        </thead>
        <tbody id="loc-rows"></tbody>
      </table>
    </div>
  </div>
</div>
```

### JS — build the table
```javascript
function buildLocalityDashboard() {
  const locs = {};
  for (const s of data.societies) {
    const loc = (s.locality || '').trim();
    if (!loc) continue;
    if (!locs[loc]) locs[loc] = { name: loc, count: 0, prices: [], green: [], safety: [], noise: [], liquidity: [], rain: [], walk: [] };
    const L = locs[loc];
    L.count++;
    if (s.psf_now) L.prices.push(s.psf_now);
    if (s.green_score != null) L.green.push(s.green_score);
    if (s.safety_score != null) L.safety.push(s.safety_score);
    if (s.noise_score != null) L.noise.push(s.noise_score);
    if (s.liquidity_score != null) L.liquidity.push(s.liquidity_score);
    if (s.rain_annual != null) L.rain.push(s.rain_annual);
    if (s.walk_score != null) L.walk.push(s.walk_score);
  }
  return Object.values(locs).map(L => ({
    ...L,
    avg_price: L.prices.length ? Math.round(avg(L.prices)) : null,
    avg_green: L.green.length ? Math.round(avg(L.green)) : null,
    avg_safety: L.safety.length ? Math.round(avg(L.safety)) : null,
    avg_noise: L.noise.length ? Math.round(avg(L.noise)) : null,
    avg_liquidity: L.liquidity.length ? Math.round(avg(L.liquidity)) : null,
    avg_rain: L.rain.length ? Math.round(avg(L.rain)) : null,
    avg_walk: L.walk.length ? Math.round(avg(L.walk)) : null,
  }));
}

function avg(arr) { return arr.reduce((a, b) => a + b, 0) / arr.length; }

function renderLocalityDashboard() {
  const rows = buildLocalityDashboard();
  // Sort by selected criteria
  const sortKey = $('loc-sort').value;
  const sorters = {
    count: (a, b) => b.count - a.count,
    'price-low': (a, b) => (a.avg_price ?? 9e9) - (b.avg_price ?? 9e9),
    'price-high': (a, b) => (b.avg_price ?? 0) - (a.avg_price ?? 0),
    green: (a, b) => (b.avg_green ?? -1) - (a.avg_green ?? -1),
    safe: (a, b) => (b.avg_safety ?? -1) - (a.avg_safety ?? -1),
    quiet: (a, b) => (a.avg_noise ?? 999) - (b.avg_noise ?? 999),
    liquid: (a, b) => (b.avg_liquidity ?? -1) - (a.avg_liquidity ?? -1),
    'rain-low': (a, b) => (a.avg_rain ?? 9999) - (b.avg_rain ?? 9999),
  };
  rows.sort(sorters[sortKey] || sorters.count);

  const filter = ($('loc-search').value || '').toLowerCase();
  const filtered = filter ? rows.filter(r => r.name.toLowerCase().includes(filter)) : rows;

  $('loc-rows').innerHTML = filtered.map(r => `<tr>
    <td><a class="loc-link" data-loc="${esc(r.name)}">${esc(r.name)}</a></td>
    <td>${r.count}</td>
    <td>${r.avg_price != null ? '₹' + r.avg_price.toLocaleString() : '—'}</td>
    <td>${scoreCell(r.avg_green, 75, 50)}</td>
    <td>${scoreCell(r.avg_safety, 70, 40)}</td>
    <td>${scoreCell(r.avg_noise, 999, 50, true)}</td>
    <td>${scoreCell(r.avg_liquidity, 70, 40)}</td>
    <td>${r.avg_rain != null ? r.avg_rain : '—'}</td>
    <td>${scoreCell(r.avg_walk, 75, 50)}</td>
  </tr>`).join('');
}

function scoreCell(val, good, mid, invert = false) {
  if (val == null) return '—';
  let cls;
  if (invert) cls = val <= mid ? 'cell-good' : val <= good ? 'cell-mid' : 'cell-bad';
  else cls = val >= good ? 'cell-good' : val >= mid ? 'cell-mid' : 'cell-bad';
  return `<span class="${cls}">${val}</span>`;
}
```

Clicking a locality name filters the main results to that locality:
```javascript
$('loc-rows').addEventListener('click', (e) => {
  const link = e.target.closest('.loc-link');
  if (!link) return;
  $('q').value = link.dataset.loc;
  $('locality-modal').hidden = true;
  applyFilters();
});
```

### CSS
```css
.locality-sheet {
  width: min(900px, 95vw); max-height: 85vh;
  background: var(--glass-strong); border-radius: 12px;
  padding: 16px 20px; overflow: auto;
  backdrop-filter: blur(16px);
}
.locality-controls { display: flex; gap: 10px; margin: 10px 0; }
.locality-controls input { flex: 1; }
.locality-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.locality-table th {
  text-align: left; padding: 6px 8px; font-weight: 600;
  border-bottom: 1px solid var(--line); font-size: 11px;
  color: var(--muted); white-space: nowrap; cursor: pointer;
}
.locality-table td { padding: 6px 8px; border-bottom: 1px solid var(--line); }
.locality-table tr:hover { background: var(--line); }
.loc-link { color: var(--accent); cursor: pointer; text-decoration: none; }
.loc-link:hover { text-decoration: underline; }
.cell-good { color: #22c55e; font-weight: 600; }
.cell-mid { color: #eab308; font-weight: 600; }
.cell-bad { color: #ef4444; font-weight: 600; }

@media (max-width: 700px) {
  .locality-table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  .locality-table { min-width: 700px; }
}
```

### Don't touch
- Existing filter logic
- Map interactions

---

## 6. Radar chart in Compare mode

### Problem
Compare modal shows societies side by side as text. With 7+ score dimensions, a visual comparison is much faster.

### Solution
Add a radar/spider chart SVG at the top of the compare modal. Each society gets a coloured polygon on the same axes.

### JS — SVG radar chart
```javascript
const RADAR_AXES = [
  { key: 'green_score', label: 'Greenery', max: 100 },
  { key: 'safety_score', label: 'Safety', max: 100 },
  { key: 'noise_inv', label: 'Quiet', max: 100 },  // inverted: 100 - noise_score
  { key: 'liquidity_score', label: 'Liquidity', max: 100 },
  { key: 'walk_score', label: 'Walkability', max: 100 },
  { key: 'score', label: 'Rating', max: 10 },
];

const RADAR_COLORS = ['#3b82f6', '#f97316', '#22c55e', '#a855f7'];

function radarChart(societies) {
  const n = RADAR_AXES.length;
  const size = 220, cx = size / 2, cy = size / 2, r = 90;
  const angleStep = (2 * Math.PI) / n;

  // Grid circles
  let svg = `<svg viewBox="0 0 ${size} ${size}" class="radar-svg">`;
  for (const frac of [0.25, 0.5, 0.75, 1]) {
    const pts = [];
    for (let i = 0; i < n; i++) {
      const a = -Math.PI / 2 + i * angleStep;
      pts.push(`${cx + r * frac * Math.cos(a)},${cy + r * frac * Math.sin(a)}`);
    }
    svg += `<polygon points="${pts.join(' ')}" fill="none" stroke="var(--line)" stroke-width="0.5"/>`;
  }

  // Axis lines + labels
  for (let i = 0; i < n; i++) {
    const a = -Math.PI / 2 + i * angleStep;
    const x2 = cx + r * Math.cos(a), y2 = cy + r * Math.sin(a);
    svg += `<line x1="${cx}" y1="${cy}" x2="${x2}" y2="${y2}" stroke="var(--line)" stroke-width="0.5"/>`;
    const lx = cx + (r + 14) * Math.cos(a), ly = cy + (r + 14) * Math.sin(a);
    svg += `<text x="${lx}" y="${ly}" text-anchor="middle" dominant-baseline="central" fill="var(--muted)" font-size="9">${RADAR_AXES[i].label}</text>`;
  }

  // Society polygons
  societies.forEach((s, si) => {
    const pts = [];
    for (let i = 0; i < n; i++) {
      const axis = RADAR_AXES[i];
      let val = axis.key === 'noise_inv' ? 100 - (s.noise_score || 50) : (s[axis.key] || 0);
      if (axis.key === 'score') val = (val / axis.max) * 100;
      else val = Math.min(val / axis.max * 100, 100);
      const frac = val / 100;
      const a = -Math.PI / 2 + i * angleStep;
      pts.push(`${cx + r * frac * Math.cos(a)},${cy + r * frac * Math.sin(a)}`);
    }
    const color = RADAR_COLORS[si % RADAR_COLORS.length];
    svg += `<polygon points="${pts.join(' ')}" fill="${color}" fill-opacity="0.15" stroke="${color}" stroke-width="1.5"/>`;
  });

  svg += '</svg>';

  // Legend
  const legend = societies.map((s, i) =>
    `<span class="radar-legend-item"><i style="background:${RADAR_COLORS[i % RADAR_COLORS.length]}"></i>${esc(s.name)}</span>`
  ).join('');

  return `<div class="radar-wrap">${svg}<div class="radar-legend">${legend}</div></div>`;
}
```

### Where to insert
In `showCompare()`, before the existing comparison grid:
```javascript
const chart = radarChart(compareSocieties);
$('compare-body').innerHTML = chart + existingCompareGrid;
```

### CSS
```css
.radar-wrap { text-align: center; margin-bottom: 16px; }
.radar-svg { width: 260px; height: 260px; }
.radar-legend { display: flex; justify-content: center; gap: 14px; margin-top: 8px; flex-wrap: wrap; }
.radar-legend-item { display: flex; align-items: center; gap: 5px; font-size: 12px; }
.radar-legend-item i { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
```

### Don't touch
- Compare selection logic
- Existing side-by-side text comparison (keep it below the chart)

---

## 7. Composite "Decision Score" with adjustable weights

### Problem
Users see 7 separate scores but no single "is this a good buy for me?" answer. Different buyers care about different things — a family prioritizes safety and greenery, an investor prioritizes liquidity and trend.

### Solution
A weighted composite score (0–100) shown on each society. Users can adjust weights via sliders in a "My Priorities" section in the filter panel.

### HTML — add section to filter panel (before "Matching societies")
```html
<section class="priorities" id="priorities">
  <div class="k row">My priorities <button class="linkbtn" id="pri-reset">Reset</button></div>
  <div class="pri-sliders">
    <label><span>Price</span><input type="range" data-pri="price" min="0" max="10" value="5"><span class="pri-val">5</span></label>
    <label><span>Greenery</span><input type="range" data-pri="green" min="0" max="10" value="3"><span class="pri-val">3</span></label>
    <label><span>Safety</span><input type="range" data-pri="safety" min="0" max="10" value="5"><span class="pri-val">5</span></label>
    <label><span>Quiet</span><input type="range" data-pri="quiet" min="0" max="10" value="3"><span class="pri-val">3</span></label>
    <label><span>Liquidity</span><input type="range" data-pri="liquidity" min="0" max="10" value="4"><span class="pri-val">4</span></label>
    <label><span>Walkability</span><input type="range" data-pri="walk" min="0" max="10" value="3"><span class="pri-val">3</span></label>
    <label><span>Builder</span><input type="range" data-pri="builder" min="0" max="10" value="3"><span class="pri-val">3</span></label>
  </div>
</section>
```

### JS — compute composite score
```javascript
const DEFAULT_WEIGHTS = { price: 5, green: 3, safety: 5, quiet: 3, liquidity: 4, walk: 3, builder: 3 };
let weights = { ...DEFAULT_WEIGHTS };

function decisionScore(s) {
  const components = [];
  const w = weights;

  // Price: invert — lower price = higher score. Normalize against city range.
  if (w.price > 0 && s.psf_now) {
    const range = priceRange(); // { min, max } from data
    const norm = 100 - ((s.psf_now - range.min) / (range.max - range.min || 1)) * 100;
    components.push({ score: Math.max(0, Math.min(100, norm)), weight: w.price });
  }
  if (w.green > 0 && s.green_score != null) components.push({ score: s.green_score, weight: w.green });
  if (w.safety > 0 && s.safety_score != null) components.push({ score: s.safety_score, weight: w.safety });
  if (w.quiet > 0 && s.noise_score != null) components.push({ score: 100 - s.noise_score, weight: w.quiet });
  if (w.liquidity > 0 && s.liquidity_score != null) components.push({ score: s.liquidity_score, weight: w.liquidity });
  if (w.walk > 0 && s.walk_score != null) components.push({ score: s.walk_score, weight: w.walk });
  if (w.builder > 0 && s.builder_record?.delivery_pct != null) {
    components.push({ score: s.builder_record.delivery_pct, weight: w.builder });
  }

  if (!components.length) return null;
  const totalWeight = components.reduce((sum, c) => sum + c.weight, 0);
  return Math.round(components.reduce((sum, c) => sum + c.score * c.weight, 0) / totalWeight);
}

// Cache price range
let _priceRange;
function priceRange() {
  if (_priceRange) return _priceRange;
  const vals = data.societies.map(s => s.psf_now).filter(Boolean);
  vals.sort((a, b) => a - b);
  _priceRange = {
    min: vals[Math.floor(vals.length * 0.05)] || 0,
    max: vals[Math.floor(vals.length * 0.95)] || 1,
  };
  return _priceRange;
}
```

### Display on card and results
In the result list item, show the decision score as a coloured badge:
```javascript
function decisionBadge(score) {
  if (score == null) return '';
  const color = score >= 75 ? '#22c55e' : score >= 50 ? '#eab308' : '#ef4444';
  return `<span class="decision-badge" style="background:${color}">${score}</span>`;
}
```

### Sort option
Add to the sort dropdown under Relevance:
```html
<option value="decision">My priorities score</option>
```
Sort: `(decisionScore(b) ?? -1) - (decisionScore(a) ?? -1)`

### Persist weights
Store in localStorage:
```javascript
store.set('pf-weights', weights);
// On load:
weights = { ...DEFAULT_WEIGHTS, ...store.get('pf-weights', {}) };
```

### URL param
Encode as `pri=5,3,5,3,4,3,3` (ordered: price, green, safety, quiet, liquidity, walk, builder)

### CSS
```css
.pri-sliders label {
  display: grid; grid-template-columns: 80px 1fr 24px;
  align-items: center; gap: 6px; font-size: 12px; margin: 3px 0;
}
.pri-sliders input[type="range"] { width: 100%; }
.pri-val { font-weight: 600; text-align: right; font-size: 11px; }
.decision-badge {
  display: inline-block; width: 28px; height: 28px; line-height: 28px;
  text-align: center; border-radius: 50%; font-size: 11px;
  font-weight: 700; color: #fff; flex-shrink: 0;
}
```

### Don't touch
- Existing Property Finder score (keep it separate — this is user-defined)
- Filter logic

---

## Files to create/change

All changes are in existing files:
- `web/index.html` — topbar restructure, sort optgroups, priorities section, locality modal, radar chart container
- `web/src/main.js` — overflow menu, locality dashboard builder, radar chart SVG, decision score computation, compact score pills, search result previews
- `web/src/style.css` — all new component styles listed above

No new files needed. No pipeline changes.

## Don't touch
- Map rendering
- Filter matching logic
- Data loading
- Colour-by modes
- Overlay toggles
- Pipeline scripts
- Compare selection logic (only add radar chart on top)

## Implementation order
1. Topbar cleanup (simplest, immediate visual improvement)
2. Sort optgroups (one HTML change)
3. Search result previews (small JS change)
4. Compact score pills (refactor card rendering)
5. Locality dashboard (new modal)
6. Radar chart in compare (new SVG builder)
7. Decision score with weights (new computation + UI)
