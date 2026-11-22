# Feature Spec: Neighbourhood Comparison

## User story
"I like Baner but it's over budget. Where else has a similar vibe but cheaper?"

## What it does
When viewing a society or filtering by locality, the app suggests **similar neighbourhoods** based on price range, amenity mix, walk score, transit access, and overall profile. Users can discover areas they hadn't considered.

## How similarity works

### Locality profile vector
Each locality gets a profile computed from its societies:

```python
def locality_profile(locality_name, societies):
    loc_socs = [s for s in societies if s.get('locality') == locality_name]
    if not loc_socs: return None
    
    return {
        'name': locality_name,
        'count': len(loc_socs),
        'med_psf': median([s['psf_now'] for s in loc_socs if s.get('psf_now')]),
        'med_walk_score': median([s['walk_score'] for s in loc_socs if s.get('walk_score')]),
        'med_yield': median([s['rental_yield'] for s in loc_socs if s.get('rental_yield')]),
        'has_metro': any(s.get('nearby', {}).get('metro', {}).get('m', 9999) < 1500 for s in loc_socs),
        'has_school_near': pct([isNear(s, 'school') for s in loc_socs]),
        'has_hospital_near': pct([isNear(s, 'hospital') for s in loc_socs]),
        'has_park_near': pct([isNear(s, 'park') for s in loc_socs]),
        'med_rating': median([s['rating'] for s in loc_socs if s.get('rating')]),
        'ready_pct': pct([s.get('status') == 'Ready to Move' for s in loc_socs]),
        'top_amenities': most_common_amenities(loc_socs),
        'lat': median([s['lat'] for s in loc_socs]),
        'lng': median([s['lng'] for s in loc_socs]),
    }
```

### Similarity score
Cosine distance on normalized profile vectors:

```python
def similarity(a, b):
    """
    Compare two locality profiles. Lower = more similar.
    
    Features and weights:
    - med_psf: weight 2 (normalize to 0-1 by city range)
    - med_walk_score: weight 1.5
    - med_yield: weight 1
    - has_metro: weight 1 (binary)
    - has_school_near: weight 0.5
    - has_hospital_near: weight 0.5
    - has_park_near: weight 0.5
    - med_rating: weight 1
    - ready_pct: weight 0.5
    
    Exclude geographic distance from similarity (we WANT to find
    similar-but-different areas, not just adjacent ones).
    """
    features = ['med_psf', 'med_walk_score', 'med_yield', 'has_metro', 
                'has_school_near', 'has_hospital_near', 'has_park_near',
                'med_rating', 'ready_pct']
    weights = [2, 1.5, 1, 1, 0.5, 0.5, 0.5, 1, 0.5]
    
    # Normalize each feature to 0-1 range across all localities
    # Then weighted euclidean distance
    dist = sum(w * (norm(a[f]) - norm(b[f]))**2 for f, w in zip(features, weights))
    return sqrt(dist)
```

### Pre-compute at build time
In `build_city.py`, compute all locality profiles and for each, find the top 5 most similar:

```python
def compute_similar_localities(societies):
    profiles = {}
    for loc in set(s.get('locality') for s in societies if s.get('locality')):
        profiles[loc] = locality_profile(loc, societies)
    
    similar = {}
    for loc, prof in profiles.items():
        dists = [(other, similarity(prof, oprof)) 
                 for other, oprof in profiles.items() if other != loc]
        dists.sort(key=lambda x: x[1])
        similar[loc] = [
            {
                'name': name,
                'score': round(100 - dist * 10),  # invert: 100 = identical
                'med_psf': profiles[name]['med_psf'],
                'count': profiles[name]['count'],
                'diff_psf_pct': round((profiles[name]['med_psf'] - prof['med_psf']) / prof['med_psf'] * 100)
            }
            for name, dist in dists[:5]
        ]
    return similar
```

### Output in city JSON
Add to city data:
```json
{
  "similar_localities": {
    "Baner": [
      {"name": "Balewadi", "score": 92, "med_psf": 7200, "count": 180, "diff_psf_pct": -8},
      {"name": "Wakad", "score": 87, "med_psf": 6100, "count": 220, "diff_psf_pct": -22},
      {"name": "Hinjewadi", "score": 83, "med_psf": 5800, "count": 310, "diff_psf_pct": -26}
    ]
  }
}
```

## Frontend changes

### "Similar areas" panel on locality search
When user searches/filters to a specific locality, show a banner:

```javascript
function showSimilarLocalities(locality) {
  const similar = data.similar_localities?.[locality];
  if (!similar || similar.length === 0) return;
  
  const html = `
    <div class="similar-areas" id="similar-areas">
      <div class="k">If you like ${esc(locality)}, also consider:</div>
      <div class="similar-chips">
        ${similar.map(s => `
          <button class="similar-chip" data-loc="${esc(s.name)}">
            <b>${esc(s.name)}</b>
            <span class="fine">${s.count} societies · ₹${formatINR(s.med_psf)}/sqft
            ${s.diff_psf_pct < 0 ? `<span class="cheaper">${s.diff_psf_pct}%</span>` : 
              `<span class="pricier">+${s.diff_psf_pct}%</span>`}
            </span>
          </button>
        `).join('')}
      </div>
    </div>
  `;
  
  // Insert after the search input
  const existing = $('similar-areas');
  if (existing) existing.remove();
  $('q').closest('div').insertAdjacentHTML('afterend', html);
  
  // Clicking a chip searches for that locality
  document.querySelectorAll('.similar-chip').forEach(btn => {
    btn.onclick = () => {
      $('q').value = btn.dataset.loc;
      $('q').dispatchEvent(new Event('input'));
    };
  });
}
```

### Trigger
Show similar localities when:
1. User types a locality name in search and results are filtered to that area
2. User clicks a locality name in a society card
3. All visible results are from the same locality

### Society card
On each card, below the locality name:
```html
<span class="fine clickable" onclick="showSimilarLocalities('${s.locality}')">
  Similar areas ›
</span>
```

## Styles
```css
.similar-areas { 
  padding: 8px 12px; 
  background: rgba(0,188,212,0.08); 
  border-radius: 8px; 
  margin: 8px 0; 
}
.similar-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.similar-chip {
  background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.15);
  border-radius: 8px; padding: 6px 10px; cursor: pointer; text-align: left;
}
.similar-chip:hover { background: rgba(255,255,255,0.15); }
.cheaper { color: #4caf50; font-weight: 600; }
.pricier { color: #ff9800; font-weight: 600; }
```

## Files to change
- `pipeline/build_city.py` — add `compute_similar_localities()`, include in output JSON
- `web/src/main.js` — add `showSimilarLocalities()`, trigger logic
- `web/src/style.css` — similar area chip styles
- `web/index.html` — no changes needed (dynamic rendering)

## Don't touch
- Filter logic
- Search logic (similar area clicks feed into existing search)
- Colour-by modes
