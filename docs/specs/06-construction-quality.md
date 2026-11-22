# Feature Spec: Construction Quality Signals

## User story
"This builder says possession in 2025. But do they actually deliver on time? How many complaints has RERA received about them?"

## What it does
Shows two signals per society on the card:

1. **Builder track record**: % of projects delivered on time, total project count, average delay
2. **RERA complaint count**: number of complaints filed against this project/builder on the state RERA portal

## Data sources

### 1. Delivery track record (from existing data)
We already have `possession` and `possession_year` on each society, plus `status` ("Ready to Move", "Under Construction", etc.). For each builder/developer:

```python
# In build_city.py, compute from existing data:
def builder_track_record(societies):
    """
    Group societies by developer name.
    For each developer:
    - Count total projects
    - Count "Ready to Move" projects (delivered)
    - For delivered projects, compare original possession date vs actual
      (if available from Magicbricks "originally promised" field)
    - Calculate: on_time_pct, avg_delay_months, total_projects
    """
    by_dev = defaultdict(list)
    for s in societies:
        if s.get('developer'):
            by_dev[s['developer']].append(s)
    
    records = {}
    for dev, projects in by_dev.items():
        total = len(projects)
        delivered = [p for p in projects if p.get('status') == 'Ready to Move']
        records[dev] = {
            'total_projects': total,
            'delivered': len(delivered),
            'delivery_pct': round(len(delivered) / total * 100) if total else 0,
            # avg_delay requires original vs actual possession dates
        }
    return records
```

### 2. MahaRERA complaint data (Pune/Mumbai)
- Portal: https://maharera.maharashtra.gov.in
- Has project-wise complaint count and status
- **Scraping approach**: Search by project RERA ID → get complaint count

```python
# pipeline/rera_fetch.py (new file)
def fetch_rera_complaints(city_id, societies):
    """
    For each society with a rera_id:
    1. Query MahaRERA portal API/page for the project
    2. Extract: complaint_count, complaint_types, resolved_count
    
    For builders without RERA ID:
    - Search by developer name + project name
    
    Maharashtra: https://maharera.maharashtra.gov.in
    Karnataka: https://rera.karnataka.gov.in
    Haryana: https://haryanarera.gov.in
    Telangana: https://rera.telangana.gov.in
    
    Output: out/<city>/rera_complaints.json
    {
        "by_project": {
            "P52100000123": {"complaints": 5, "resolved": 3, "types": ["delay", "quality"]},
            ...
        },
        "by_builder": {
            "Godrej Properties": {"total_complaints": 15, "projects_with_complaints": 3},
            ...
        }
    }
    """
```

**Note**: RERA portals often have captchas or require specific form submissions. If direct scraping is blocked:
- Use the RERA ID from Magicbricks data to do manual lookups
- Create a curated `data/rera/<city>_complaints.json` from periodic manual checks
- Or just show the RERA ID as a link to the portal

### 3. Google Reviews sentiment (stretch goal)
- Already have `rating` and `rating_count` from Magicbricks
- Could supplement with Google Places API reviews (sentiment analysis)
- Expensive and not needed for MVP

## Integration in `build_city.py`

Add to each society:
```python
society['builder_record'] = {
    'total': 12,           # builder's total projects in this city
    'delivered': 8,        # projects delivered
    'delivery_pct': 67,    # % delivered
    'avg_delay': 14,       # average delay in months (null if unknown)
}
society['rera_complaints'] = 3    # complaint count (null if no RERA data)
society['rera_link'] = 'https://maharera.maharashtra.gov.in/project/P52100000123'
```

## Frontend changes

### Society card
Add a "Builder" section between ratings and price:

```javascript
function builderSection(s) {
  const rec = s.builder_record;
  if (!rec) return '';
  
  const badge = rec.delivery_pct >= 80 ? 'builder-good' :
                rec.delivery_pct >= 50 ? 'builder-avg' : 'builder-poor';
  
  let html = `
    <div class="builder-info">
      <div class="k">Builder: ${esc(s.developer)}</div>
      <div class="builder-stats">
        <span class="builder-badge ${badge}">${rec.delivery_pct}% delivered</span>
        <span class="fine">${rec.delivered}/${rec.total} projects</span>
        ${rec.avg_delay ? `<span class="fine">Avg delay: ${rec.avg_delay} months</span>` : ''}
      </div>
  `;
  
  if (s.rera_complaints != null) {
    const level = s.rera_complaints === 0 ? 'none' : s.rera_complaints <= 3 ? 'few' : 'many';
    html += `
      <div class="rera-row">
        <span class="rera-badge rera-${level}">${s.rera_complaints} RERA complaints</span>
        ${s.rera_link ? `<a href="${s.rera_link}" target="_blank" class="fine">View on RERA</a>` : ''}
      </div>
    `;
  }
  
  html += '</div>';
  return html;
}
```

### Sort by builder quality
Add sort option:
```html
<option value="builder">Builder track record</option>
```
Sort by `delivery_pct` descending, then `rera_complaints` ascending.

### Builder filter (stretch goal)
Add a checkbox: "Only trusted builders (>80% delivery rate)"

## Styles
```css
.builder-info { margin: 8px 0; padding: 8px 0; border-top: 1px solid rgba(255,255,255,0.1); }
.builder-badge { font-size: 11px; padding: 2px 6px; border-radius: 4px; font-weight: 600; }
.builder-good { background: rgba(76,175,80,0.2); color: #4caf50; }
.builder-avg { background: rgba(255,152,0,0.2); color: #ff9800; }
.builder-poor { background: rgba(244,67,54,0.2); color: #f44336; }
.rera-badge { font-size: 11px; padding: 2px 6px; border-radius: 4px; }
.rera-none { color: #4caf50; }
.rera-few { color: #ff9800; }
.rera-many { color: #f44336; }
```

## Files to create/change
- `pipeline/rera_fetch.py` — NEW: fetch RERA complaint data (or document manual curation)
- `pipeline/build_city.py` — add `builder_record` computation, integrate RERA data
- `web/src/main.js` — add `builderSection()`, builder sort
- `web/src/style.css` — builder badge and stats styles
- `web/index.html` — add builder sort option

## MVP scope
1. Builder track record from existing data (delivery %) — no new data fetch needed
2. RERA link (just link to the portal with RERA ID) — no scraping needed
3. RERA complaint count — manual curation for top 50 builders initially, automate later

## Don't touch
- Magicbricks crawler
- Rating system
- Filter logic (beyond adding sort option)
