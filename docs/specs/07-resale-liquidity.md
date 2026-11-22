# Feature Spec: Resale Liquidity Score

## User story
"If I need to sell this flat in 3 years, will it sell quickly or sit on the market for months?"

## What it does
Each society gets a **liquidity_score** (0–100) estimating how easy it is to resell. Shown on the card and available as a sort/filter. Based on listing turnover, market depth, and pricing efficiency.

## Signals (all derivable from existing + periodic crawl data)

### Signal 1: Listing depth (current snapshot)
- `sale_count`: number of active sale listings right now
- `rent_count`: number of active rental listings right now
- More listings = more market activity = easier to sell
- But TOO many listings (high inventory) = oversupply = harder to sell
- **Sweet spot**: 5-20 sale listings for a mid-size society

### Signal 2: Listing turnover (requires periodic crawls)
- Crawl the same city every 2-4 weeks
- Compare listing IDs between crawls: how many are new, how many disappeared
- Disappeared listings ≈ sold or delisted
- **Turnover rate** = disappeared / total per period
- High turnover = properties sell faster

### Signal 3: Price consistency
- Low variance in listing prices = market consensus on value = easier pricing = faster sale
- High variance = uncertainty = buyers hesitate
- Use `price_min`, `price_max`, and listing price spread from BHK data

### Signal 4: Rental demand
- High `rent_count` relative to `sale_count` = strong rental market = investors interested = liquidity
- Rental yield (already computed) also signals investor interest

## Scoring formula

```python
def calc_liquidity_score(society, locality_stats):
    score = 50  # base
    
    # Listing depth: 5-20 is ideal
    sales = society.get('sale_count', 0)
    if sales >= 5:
        score += 15
    elif sales >= 2:
        score += 8
    if sales > 30:  # oversupply penalty
        score -= 10
    
    # Rental demand
    rents = society.get('rent_count', 0)
    if rents >= 3:
        score += 10
    if rents >= 10:
        score += 5
    
    # Price consistency (low spread = good)
    if society.get('price_min') and society.get('price_max'):
        spread = (society['price_max'] - society['price_min']) / society['price_min']
        if spread < 0.3:   # <30% spread
            score += 10
        elif spread > 1.0:  # >100% spread
            score -= 10
    
    # Rental yield (high yield attracts investors)
    yld = society.get('rental_yield')
    if yld and yld > 4:
        score += 10
    elif yld and yld > 3:
        score += 5
    
    # Locality popularity (many societies with listings in same area)
    loc_listings = locality_stats.get(society['locality'], {}).get('total_listings', 0)
    if loc_listings > 100:
        score += 10
    elif loc_listings > 50:
        score += 5
    
    # Developer reputation (branded sells faster)
    if society.get('builder_record', {}).get('total', 0) > 5:
        score += 5
    
    # Ready to move (can transact immediately)
    if society.get('status') == 'Ready to Move':
        score += 5
    
    return max(0, min(100, score))
```

## Implementation in `build_city.py`

```python
def add_liquidity_scores(societies):
    # Pre-compute locality stats
    loc_stats = defaultdict(lambda: {'total_listings': 0})
    for s in societies:
        loc = s.get('locality', '')
        loc_stats[loc]['total_listings'] += (s.get('sale_count', 0) + s.get('rent_count', 0))
    
    for s in societies:
        s['liquidity_score'] = calc_liquidity_score(s, loc_stats)
        s['liquidity_label'] = (
            'High' if s['liquidity_score'] >= 70 else
            'Medium' if s['liquidity_score'] >= 40 else
            'Low'
        )
```

## Periodic crawl for turnover (Phase 2)

This requires running the crawler periodically and storing snapshots:

```python
# pipeline/liquidity_track.py (new file, Phase 2)
def track_listings(city_id):
    """
    1. Load current mb_projects.json
    2. Load previous snapshot from pipeline/cache/listing_snapshots/<city>/<date>.json
    3. For each society, compare listing IDs (or listing counts as proxy)
    4. Compute turnover_rate = (disappeared + new) / (previous_total) per 30 days
    5. Save current snapshot for next comparison
    
    Output: out/<city>/liquidity_tracking.json
    """
```

**For MVP**: Use the single-snapshot signals only (listing depth, price consistency, rental demand). Turnover requires multiple crawls over time.

## Frontend changes

### Society card
Show liquidity badge:
```javascript
function liquidityBadge(s) {
  if (s.liquidity_score == null) return '';
  const level = s.liquidity_score >= 70 ? 'high' : s.liquidity_score >= 40 ? 'med' : 'low';
  const colors = { high: '#4caf50', med: '#ff9800', low: '#f44336' };
  return `
    <div class="liquidity-row">
      <span class="liq-badge liq-${level}">${s.liquidity_label} liquidity</span>
      <span class="fine" title="Score: ${s.liquidity_score}/100. Based on listing depth, price consistency, and rental demand.">
        ${s.sale_count} sale + ${s.rent_count} rental listings
      </span>
    </div>
  `;
}
```

### Sort option
```html
<option value="liquidity">Resale liquidity</option>
```

### Colour-by mode (stretch goal)
Add "Liquidity" colour-by: green (high) → yellow (medium) → red (low).

## Files to create/change
- `pipeline/build_city.py` — add `calc_liquidity_score()`, `add_liquidity_scores()`
- `pipeline/liquidity_track.py` — NEW (Phase 2): periodic listing tracking
- `web/src/main.js` — add `liquidityBadge()`, liquidity sort
- `web/src/style.css` — liquidity badge styles
- `web/index.html` — add sort option

## Don't touch
- Crawler (single snapshot works for MVP)
- Filter logic (beyond sort)
- Existing rental yield computation
