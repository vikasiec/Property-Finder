# Feature Spec: Shareable Filtered URLs

## User story
"I found the perfect search — 3BHK in Baner under 1.2Cr with a pool. I want to send this exact view to my partner."

## What it does
Every filter change updates the URL in the browser's address bar. Pasting the URL into a browser recreates the exact same search, filters, and view state. No login needed.

## URL parameter design

### Current parameters (already implemented)
```
?city=pune
?map=streets | light
?open=<society_id>
?nointro
```

### New parameters to add
```
?city=pune
&bhk=2,3                    # BHK types
&room=11.25x12.25           # min bedroom (feet, orientation-free)
&area=15.3                  # min bedroom area (gaj)
&sqft=1200-2000             # min-max home size
&price=50L-1.5Cr            # buy budget range
&rent=15K-30K               # rent budget range  
&mode=buy                   # buy or rent
&amen=pool,gym,squash       # amenities
&near=metro,school          # nearby filters
&ready=1                    # ready to move only
&q=Baner                    # search text
&sort=price                 # sort order
&kind=apartment             # property type
&colorby=yield              # colour-by mode
&est=0                      # exclude "probably fits" estimates
```

### Compact encoding rules
- Prices: `50L` = 50 lakh, `1.5Cr` = 1.5 crore, `15K` = 15,000
- Room sizes: `11.25x12.25` (feet, decimal)
- Lists: comma-separated, no spaces
- Booleans: presence = true (`&ready=1`), absence = false
- Ranges: `min-max` (either side optional: `-2000` = max 2000, `50L-` = min 50L)

### Example URLs
```
# 3BHK in Baner under 1.2Cr with pool, sorted by price
?city=pune&q=Baner&bhk=3&price=-1.2Cr&amen=pool&sort=price

# 2-3 BHK apartments, 15+ gaj bedroom, near metro, rent mode
?city=pune&bhk=2,3&kind=apartment&area=15.3&near=metro&mode=rent

# Specific society open
?city=pune&open=mb-123456

# Compare mode with two societies
?city=pune&compare=mb-123,mb-456
```

## Implementation

### Writing URL (on every filter change)

```javascript
function syncUrlFromFilters() {
  const p = new URLSearchParams();
  
  // Always include city
  p.set('city', cityId);
  
  // Only include non-default values
  if (crit.bhk.length) p.set('bhk', crit.bhk.join(','));
  if (crit.room) p.set('room', `${crit.room.a}x${crit.room.b}`);
  if (crit.roomArea) p.set('area', crit.roomArea);
  if (crit.minSqft) p.set('sqft', crit.maxSqft ? `${crit.minSqft}-${crit.maxSqft}` : `${crit.minSqft}-`);
  else if (crit.maxSqft) p.set('sqft', `-${crit.maxSqft}`);
  
  if (crit.mode === 'rent') {
    p.set('mode', 'rent');
    if (crit.minRent || crit.maxRent) p.set('rent', priceRange(crit.minRent, crit.maxRent));
  } else {
    if (crit.minPrice || crit.maxPrice) p.set('price', priceRange(crit.minPrice, crit.maxPrice));
  }
  
  if (crit.amenities.length) p.set('amen', crit.amenities.join(','));
  if (crit.near.length) p.set('near', crit.near.join(','));
  if (crit.ready) p.set('ready', '1');
  if (crit.q) p.set('q', crit.q);
  if (!crit.estimates) p.set('est', '0');
  if (crit.kinds.length && !(crit.kinds.length === 1 && crit.kinds[0] === 'apartment')) {
    p.set('kind', crit.kinds.join(','));
  }
  
  if (sortBy !== 'best') p.set('sort', sortBy);
  if (colorByMode !== 'off') p.set('colorby', colorByMode);
  if (baseMode !== 'streets') p.set('map', baseMode);
  if (selected) p.set('open', selected);
  
  // Update URL without page reload
  const url = `${location.pathname}?${p.toString()}`;
  history.replaceState(null, '', url);
}

function priceRange(min, max) {
  const fmt = v => {
    if (!v) return '';
    if (v >= 10000000) return `${(v / 10000000).toFixed(v % 10000000 ? 1 : 0)}Cr`;
    if (v >= 100000) return `${(v / 100000).toFixed(v % 100000 ? 1 : 0)}L`;
    if (v >= 1000) return `${(v / 1000).toFixed(0)}K`;
    return v;
  };
  if (min && max) return `${fmt(min)}-${fmt(max)}`;
  if (min) return `${fmt(min)}-`;
  return `-${fmt(max)}`;
}
```

### Reading URL (on page load)

```javascript
function readFiltersFromUrl() {
  const p = new URLSearchParams(location.search);
  
  if (p.has('bhk')) crit.bhk = p.get('bhk').split(',').map(Number).filter(n => n > 0);
  
  if (p.has('room')) {
    const [a, b] = p.get('room').split('x').map(Number);
    if (a && b) crit.room = { a, b };
  }
  if (p.has('area')) {
    const v = parseFloat(p.get('area'));
    if (v > 0) { crit.roomArea = v; roomMode = 'area'; }
  }
  
  if (p.has('sqft')) {
    const [lo, hi] = p.get('sqft').split('-');
    if (lo) crit.minSqft = parseInt(lo);
    if (hi) crit.maxSqft = parseInt(hi);
  }
  
  if (p.has('mode')) crit.mode = p.get('mode') === 'rent' ? 'rent' : 'buy';
  
  if (p.has('price')) {
    const [lo, hi] = p.get('price').split('-');
    crit.minPrice = parsePrice(lo);
    crit.maxPrice = parsePrice(hi);
  }
  if (p.has('rent')) {
    const [lo, hi] = p.get('rent').split('-');
    crit.minRent = parsePrice(lo);
    crit.maxRent = parsePrice(hi);
  }
  
  if (p.has('amen')) crit.amenities = p.get('amen').split(',').filter(Boolean);
  if (p.has('near')) crit.near = p.get('near').split(',').filter(Boolean);
  if (p.has('ready')) crit.ready = p.get('ready') === '1';
  if (p.has('q')) crit.q = p.get('q');
  if (p.has('est')) crit.estimates = p.get('est') !== '0';
  if (p.has('kind')) crit.kinds = p.get('kind').split(',').filter(Boolean);
  if (p.has('sort')) sortBy = p.get('sort');
  if (p.has('colorby')) colorByMode = p.get('colorby');
}

function parsePrice(s) {
  if (!s) return null;
  s = s.trim().toUpperCase();
  if (s.endsWith('CR')) return parseFloat(s) * 10000000;
  if (s.endsWith('L')) return parseFloat(s) * 100000;
  if (s.endsWith('K')) return parseFloat(s) * 1000;
  return parseInt(s) || null;
}
```

### Integration points

1. **Call `readFiltersFromUrl()`** in `boot()` after loading data, before first `apply()`
2. **Call `syncUrlFromFilters()`** at the end of `apply()` and whenever a UI control changes
3. **Update UI controls to match URL state**: after reading URL params, set slider values, check checkboxes, select radio buttons to match `crit`

### Share button
Add a "Copy link" button near the results count:
```html
<button class="linkbtn" id="btn-copyurl" title="Copy shareable link">Copy link</button>
```

```javascript
$('btn-copyurl').onclick = () => {
  navigator.clipboard.writeText(location.href).then(() => {
    $('btn-copyurl').textContent = 'Copied!';
    setTimeout(() => { $('btn-copyurl').textContent = 'Copy link'; }, 2000);
  });
};
```

## Edge cases
- Empty/default values: don't include in URL (keep it clean)
- Invalid URL params: ignore silently, use defaults
- My list: don't encode in URL (it's localStorage-bound, could be huge)
- Commute pin: could encode as `&pin=18.52,73.85&radius=5` but skip for MVP

## Files to change
- `web/src/main.js` — add `syncUrlFromFilters()`, `readFiltersFromUrl()`, `parsePrice()`, share button logic
- `web/index.html` — add "Copy link" button
- `web/src/style.css` — minimal (button already exists as `.linkbtn`)

## Don't touch
- Filter logic in `filters.js`
- Pipeline / data
- Existing URL params (`?city`, `?map`, `?open`, `?nointro`)
