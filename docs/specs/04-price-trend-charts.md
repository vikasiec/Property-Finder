# Feature Spec: Price Trend Charts per Society

## User story
"Is this area getting expensive or flattening out? I want to know if I'm buying at the peak."

## What it does
Shows a sparkline / mini chart of price-per-sqft over time (1-5 years) on each society card, and a full trend chart in an expanded view.

## Data available

The Magicbricks crawler already captures `psf_trend` data (price per sqft over time) for many societies. Check the crawled data:

### In `pipeline/mb_crawl.py`
The project page parser already extracts `pricetrend` data from Magicbricks. It's available as:
```python
# From the crawled project page:
# "pricetrend": [{"date": "2023-01", "psf": 5200}, {"date": "2023-06", "psf": 5500}, ...]
```

### In `pipeline/build_city.py`
Currently `psf_now` is set on each society but trend data may not be passed through.

**Step 1**: Verify what trend data the crawler captures. Check `pipeline/out/pune/mb_projects.json` for a sample project's trend data.

**Step 2**: If trend data exists in crawled data but isn't in `pune.json`, pipe it through in `build_city.py`:
```python
# In build_city.py, when building society dict:
society['trend'] = project.get('pricetrend', [])  # list of {date, psf} objects
```

If trend data is NOT available from the crawler, we can build it from periodic crawl snapshots over time (not available now — would need multiple crawls weeks apart).

## Frontend changes

### Sparkline on society card
When trend data exists, show a tiny inline sparkline next to price_sqft:

```javascript
function sparkline(trend, width = 60, height = 20) {
  if (!trend || trend.length < 2) return '';
  const vals = trend.map(t => t.psf);
  const min = Math.min(...vals), max = Math.max(...vals);
  const range = max - min || 1;
  const points = vals.map((v, i) => 
    `${(i / (vals.length - 1)) * width},${height - ((v - min) / range) * height}`
  ).join(' ');
  
  const lastVal = vals[vals.length - 1];
  const firstVal = vals[0];
  const change = ((lastVal - firstVal) / firstVal * 100).toFixed(1);
  const color = change >= 0 ? '#4caf50' : '#f44336';
  
  return `
    <span class="sparkline" title="₹${firstVal} → ₹${lastVal}/sqft (${change > 0 ? '+' : ''}${change}%)">
      <svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
        <polyline points="${points}" fill="none" stroke="${color}" stroke-width="1.5"/>
      </svg>
      <span class="trend-change" style="color:${color}">${change > 0 ? '↑' : '↓'}${Math.abs(change)}%</span>
    </span>
  `;
}
```

### Where to show on card
In the card rendering in `main.js`, after the price/sqft line:
```javascript
// After: ₹5,200/sqft
// Show: ₹5,200/sqft [sparkline] ↑12.5%
const trendHtml = s.trend ? sparkline(s.trend) : '';
html += `<div class="card-psf">₹${formatINR(s.psf_now)}/sqft ${trendHtml}</div>`;
```

### Expanded trend chart (on click)
When user clicks the sparkline or a "Show trend" link, show a larger chart:

```javascript
function renderTrendChart(trend, container) {
  const width = 280, height = 140, pad = 30;
  const vals = trend.map(t => t.psf);
  const dates = trend.map(t => t.date);
  const min = Math.min(...vals) * 0.95;
  const max = Math.max(...vals) * 1.05;
  
  const scaleX = i => pad + (i / (vals.length - 1)) * (width - 2 * pad);
  const scaleY = v => height - pad - ((v - min) / (max - min)) * (height - 2 * pad);
  
  const path = vals.map((v, i) => `${i === 0 ? 'M' : 'L'}${scaleX(i)},${scaleY(v)}`).join(' ');
  
  // Y-axis labels
  const yLabels = [min, (min + max) / 2, max].map(v => 
    `<text x="${pad - 4}" y="${scaleY(v)}" text-anchor="end" font-size="9" fill="#999">₹${Math.round(v)}</text>`
  ).join('');
  
  // X-axis labels (first, middle, last)
  const xIdxs = [0, Math.floor(dates.length / 2), dates.length - 1];
  const xLabels = xIdxs.map(i =>
    `<text x="${scaleX(i)}" y="${height - 5}" text-anchor="middle" font-size="9" fill="#999">${dates[i]}</text>`
  ).join('');
  
  container.innerHTML = `
    <svg width="${width}" height="${height}" class="trend-chart">
      <path d="${path}" fill="none" stroke="#00bcd4" stroke-width="2"/>
      ${vals.map((v, i) => `<circle cx="${scaleX(i)}" cy="${scaleY(v)}" r="3" fill="#00bcd4"/>`).join('')}
      ${yLabels}
      ${xLabels}
    </svg>
  `;
}
```

### Sort by price trend
Add sort option: "Price trend (fastest rising)" and "Price trend (most stable)":
```javascript
case 'trend-up':
  return trendPct(b) - trendPct(a);  // descending by appreciation
case 'trend-stable':
  return Math.abs(trendPct(a)) - Math.abs(trendPct(b));  // closest to 0% change first

function trendPct(s) {
  if (!s.trend || s.trend.length < 2) return 0;
  const first = s.trend[0].psf, last = s.trend[s.trend.length - 1].psf;
  return ((last - first) / first) * 100;
}
```

## Colour-by enhancement
In the existing "Price ₹/sqft" colour-by mode, optionally add a toggle to show "Price change %" instead of absolute price. But this is a stretch goal.

## Styles

```css
.sparkline {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  vertical-align: middle;
}
.trend-change {
  font-size: 11px;
  font-weight: 600;
}
.trend-chart {
  background: rgba(0,0,0,0.3);
  border-radius: 8px;
  padding: 4px;
}
```

## Files to change
- `pipeline/build_city.py` — ensure `trend` data passes through to `pune.json`
- `web/src/main.js` — add `sparkline()`, `renderTrendChart()`, trend sort, card integration
- `web/src/style.css` — sparkline and chart styles
- `web/index.html` — add trend sort options to the sort dropdown

## Don't touch
- Crawler (data should already be there)
- Filter logic
- Other colour-by modes
