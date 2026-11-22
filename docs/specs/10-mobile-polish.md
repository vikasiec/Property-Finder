# Feature Spec: Mobile Layout Polish

## User story
"I'm browsing flats on my phone while commuting. The map is great but the overlays panel is impossible to use and compare mode is broken."

## Current state
- Mobile breakpoint: `max-width: 700px` (see `main.js` line 10)
- Panel slides up from bottom on mobile
- Tab bar: Search | Society (see `mtabs` in index.html)
- Map takes full screen behind the panel
- Some features built for desktop need touch optimization

## Issues to fix

### 1. Layers panel overflow
The layers menu (map style + colour-by + overlays) opens as a floating panel anchored to bottom-right. On mobile it overflows the screen, especially with all the colour-by and overlay options.

**Fix:**
```css
@media (max-width: 700px) {
  .layer-menu {
    position: fixed;
    bottom: 60px;    /* above the mobile tab bar */
    left: 8px;
    right: 8px;
    max-height: 60vh;
    overflow-y: auto;
    border-radius: 12px;
    background: rgba(20, 20, 30, 0.95);
    backdrop-filter: blur(12px);
    padding: 12px;
    box-shadow: 0 -4px 24px rgba(0,0,0,0.5);
  }
  
  /* Overlay behind the layer menu */
  .layers.open::before {
    content: '';
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.4);
    z-index: 9;
  }
}
```

### 2. Compare mode on mobile
Compare mode shows societies side by side — doesn't work on narrow screens.

**Fix:**
- On mobile, stack compare cards vertically instead of side by side
- Add swipe navigation between compared societies
- Show a sticky comparison summary bar at the top

```css
@media (max-width: 700px) {
  .compare-panel {
    flex-direction: column;
    max-height: 70vh;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
  }
  
  .compare-card {
    width: 100%;
    min-width: unset;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    padding-bottom: 12px;
    margin-bottom: 12px;
  }
  
  /* Swipe hint */
  .compare-panel::after {
    content: 'Scroll to compare';
    display: block;
    text-align: center;
    color: rgba(255,255,255,0.4);
    font-size: 11px;
    padding: 8px;
  }
}
```

### 3. Society card overflow
The society detail card opens as a large panel. On mobile it should be a full-screen bottom sheet with a drag handle.

**Fix:**
```css
@media (max-width: 700px) {
  .card {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    max-height: 85vh;
    overflow-y: auto;
    border-radius: 16px 16px 0 0;
    padding-bottom: env(safe-area-inset-bottom, 16px);
    z-index: 100;
  }
  
  /* Drag handle */
  .card::before {
    content: '';
    display: block;
    width: 36px;
    height: 4px;
    background: rgba(255,255,255,0.3);
    border-radius: 2px;
    margin: 8px auto 12px;
  }
}
```

Add swipe-down-to-close:
```javascript
if (mobile) {
  let startY, startH;
  const card = $('card');
  
  card.addEventListener('touchstart', e => {
    startY = e.touches[0].clientY;
    startH = card.offsetHeight;
  }, { passive: true });
  
  card.addEventListener('touchmove', e => {
    const dy = e.touches[0].clientY - startY;
    if (dy > 0) { // dragging down
      card.style.transform = `translateY(${dy}px)`;
      card.style.transition = 'none';
    }
  }, { passive: true });
  
  card.addEventListener('touchend', e => {
    const dy = e.changedTouches[0].clientY - startY;
    card.style.transition = 'transform 0.3s ease';
    if (dy > 100) {
      // Dismiss
      card.style.transform = 'translateY(100%)';
      setTimeout(() => { card.hidden = true; card.style.transform = ''; }, 300);
    } else {
      card.style.transform = '';
    }
  });
}
```

### 4. Commute panel on mobile
The commute panel needs to coexist with the bottom panel. Currently it may overlap.

**Fix:**
```css
@media (max-width: 700px) {
  .commute-panel {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    max-height: 50vh;
    border-radius: 16px 16px 0 0;
    padding: 16px;
    padding-bottom: env(safe-area-inset-bottom, 16px);
    z-index: 90;
    background: rgba(20, 20, 30, 0.95);
    backdrop-filter: blur(12px);
  }
  
  /* When commute is open, collapse the main panel */
  .commute-panel:not([hidden]) ~ .panel.left {
    max-height: 0;
    overflow: hidden;
  }
}
```

### 5. Touch-friendly filter controls
- Chip/pill buttons too small for thumb tapping
- Range sliders hard to grab

**Fix:**
```css
@media (max-width: 700px) {
  .chips button, .tiles button {
    min-height: 40px;
    min-width: 40px;
    font-size: 13px;
    padding: 8px 12px;
  }
  
  input[type="range"] {
    height: 32px;
    -webkit-appearance: none;
  }
  input[type="range"]::-webkit-slider-thumb {
    width: 28px;
    height: 28px;
    -webkit-appearance: none;
    background: #00bcd4;
    border-radius: 50%;
    cursor: pointer;
  }
  
  .seg button {
    min-height: 36px;
    padding: 6px 14px;
  }
}
```

### 6. Search results overlay
On mobile, search autocomplete results should be a full-width dropdown, not a small popup.

**Fix:**
```css
@media (max-width: 700px) {
  #q-results {
    position: fixed;
    left: 0;
    right: 0;
    max-height: 50vh;
    overflow-y: auto;
    background: rgba(20, 20, 30, 0.98);
    border-radius: 0;
    padding: 0;
    z-index: 200;
  }
  
  #q-results li {
    padding: 12px 16px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    min-height: 44px;
    display: flex;
    align-items: center;
  }
}
```

### 7. Bottom safe area
Ensure all bottom-anchored elements respect the iPhone safe area (notch/home indicator).

```css
@supports (padding-bottom: env(safe-area-inset-bottom)) {
  .panel.left,
  .card,
  .commute-panel,
  .layer-menu {
    padding-bottom: calc(12px + env(safe-area-inset-bottom));
  }
}
```

### 8. Topbar button overflow
The topbar has many buttons (Guide, Replay, Tour, Theme, Commute, Compare, Research log, Hide). On mobile some overflow.

**Fix:**
```css
@media (max-width: 700px) {
  .topbar {
    gap: 2px;
    padding: 4px 6px;
    overflow-x: auto;
    scrollbar-width: none;
    -webkit-overflow-scrolling: touch;
  }
  .topbar::-webkit-scrollbar { display: none; }
  
  .topbar button {
    font-size: 11px;
    padding: 4px 8px;
    white-space: nowrap;
    flex-shrink: 0;
  }
  
  /* Hide less essential buttons on mobile */
  #btn-replay, #btn-tour, #btn-log, #btn-hide {
    display: none;
  }
}
```

## Testing checklist
- [ ] Layers panel opens as bottom sheet on mobile, dismissable
- [ ] Compare mode scrolls vertically, all data visible
- [ ] Society card is a draggable bottom sheet, swipe to dismiss
- [ ] Commute panel doesn't overlap filter panel
- [ ] All tap targets are at least 40px
- [ ] Range sliders are thumb-friendly
- [ ] Search results are full-width on mobile
- [ ] iPhone safe area respected
- [ ] Topbar doesn't overflow, essential buttons visible
- [ ] No horizontal scroll on any panel
- [ ] All modals (paste, onboard) work on mobile

## Files to change
- `web/src/style.css` — all the `@media (max-width: 700px)` rules above
- `web/src/main.js` — touch gestures for card dismiss, layer panel dismiss
- `web/index.html` — add `mobile-only` class to collapse button if not already

## Don't touch
- Desktop layout
- Filter logic
- Data pipeline
- Map rendering
