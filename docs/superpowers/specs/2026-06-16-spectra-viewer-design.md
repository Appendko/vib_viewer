# Spectra Viewer Tool — Design Spec

**Date:** 2026-06-16  
**Status:** Approved by user

---

## Context

The FBR_1D anharmonic pipeline produces three output levels that all represent IR spectra at different detail levels:
- `.peak` — raw freq/intensity pairs (thousands of peaks), no metadata
- `.spec` — same peaks plus dominant assignment label and projection%
- `.out` — full computation log; projection section contains each peak with up to 10 sub-projection lines

These need to be visualized and compared against experimental FTIR data. The existing harmonic IR panel in `vib_viewer/vibration_viewer.html` is modal (tied to the 3D viewer) and only handles one spectrum at a time. This tool is a dedicated, independent spectra manipulator.

---

## New File

`spectra_viewer/spectra_viewer.html` — standalone, linked from `index.html`.

Same pattern as all other tools: single self-contained HTML file, inline JS, no build step, dark theme. No Three.js — uses the browser's native `<canvas>` 2D API.

---

## Parsers

Auto-detection by file extension and content sniffing; no explicit type selector needed.

| Input format | Detection | Parsed output |
|---|---|---|
| `.peak` | two numeric columns, whitespace-separated | `{type:'peaks', data:[{f, i}]}` |
| `.spec` | four comma-sep fields, third field matches `<n\|...>` | `{type:'peaks', data:[{f, i, label, proj}]}` |
| `.out` | contains `"Projection (to cumsum"` header | `{type:'peaks', data:[{f, i, label, proj, projections:[{label,pct}]}]}` |
| `.jdx` / `.dx` | `##TITLE=` or `##DATA TYPE=` header | `{type:'continuous', data:[{f, i}]}` |
| two-col text | whitespace-sep, numeric, no `##` header | `{type:'continuous', data:[{f, i}]}` |
| CSV | comma-sep, numeric or with header row | `{type:'continuous', data:[{f, i}]}` |

**`.out` parsing detail:** scan for the line `"Projection (to cumsum"` and skip the next line (column header). Then parse blocks: a line with all four non-empty fields starts a new peak; lines where field 1 and 2 are empty or whitespace only add to the current peak's `projections` array.

**JCAMP-DX parsing:** support `##XYPOINTS= (XY..XY)` and `##XYDATA= (X++(Y..Y))` with SQZ/DIF/DUP decompression. Limitation: compressed multi-block formats not supported; most modern FTIR instrument exports use simple XY pairs or XYDATA.

**Broadening (peaks → continuous):**
- Lorentzian: `I * (γ/2)² / ((f − f₀)² + (γ/2)²)`, where `γ = FWHM`
- Gaussian: `I * exp(−4 ln 2 * (f − f₀)² / FWHM²)`
- Both require summing contributions from every peak at each frequency grid point.
- Grid resolution: 1 cm⁻¹ (configurable); clamp to visible freq range for performance.
- Applied to `.peak` and `.spec`/`.out` data; experimental continuous data is never broadened.

---

## Dataset Object

```javascript
{
  id,           // unique string (UUID or counter)
  name,         // filename (user-editable label)
  type,         // 'peaks' | 'continuous'
  rawData,      // parsed array (immutable)
  color,        // hex string, auto-assigned from palette
  visible,      // bool (eye toggle)
  normalized,   // bool — divide by max before plotting
  scale,        // float multiplier (0.1 – 100), default 1.0
  fwhm,         // float cm⁻¹ or null (falls back to global)
  lineshape,    // 'lorentzian' | 'gaussian' or null (falls back to global)
  freqScale,    // float multiplicative correction (default 1.0, range 0.95–1.05)
  freqOffset,   // float additive correction cm⁻¹ (default 0, range ±200)
  baselineMode, // 'none' | 'constant' | 'linear' — baseline subtraction
}
```

Color palette: 8-color cycle distinct enough for dark backgrounds (matching existing tool aesthetic):
`#22d3ee, #f59e0b, #a78bfa, #34d399, #f87171, #60a5fa, #fb923c, #e879f9`

---

## UI Layout

### Overall page structure
```
┌─────────────────────────────────────────────────────┐
│ [Spectra Viewer]              [Overlay][Stack][2-col]│
├──────────────┬──────────────────────────────────────┤
│  LEFT SIDEBAR│         PLOT AREA                    │
│  (220px)     │                                      │
│              │  (canvas or multiple canvases here)  │
│              │                                      │
│              ├──────────────────────────────────────┤
│              │  PEAK INFO PANEL (collapsed by       │
│              │  default, expands on click)           │
└──────────────┴──────────────────────────────────────┘
```

### Left sidebar

**Dataset list (scrollable):**
Each loaded dataset row:
```
[●color] [👁] name.ext  [.spec]  [×]
  ▸ (expand for per-dataset controls)
```
Per-dataset controls (in collapsible section):
- Scale: preset buttons (×0.1 | ×1 | ×8 | ×100) + numeric input
- Normalize: toggle
- FWHM override: input (blank = use global)
- Freq correction: scale input (1.000, range 0.95–1.05) + offset input (0, ±200 cm⁻¹)
- Baseline: `[None ▾]` dropdown (None / Constant / Linear)

**Bottom of sidebar — global controls:**
- `[+ Load file]` button (accepts multiple files; drag-and-drop on sidebar also works)
- Lineshape: `[Lorentzian ▾]` | `[Gaussian ▾]`
- FWHM: slider + value label (5–50 cm⁻¹, default 10)
- Freq range: min input + max input + range slider (synchronized with plot zoom)
- Intensity threshold: hide peaks below X km/mol (applies to `.peak`/`.spec`/`.out` only)
- Invert y-axis: toggle
- `[Export PNG]` button

### Plot area — Overlay mode

Single `<canvas>` spanning full width and height.  
All visible datasets drawn on the same axes.  
Y-axis: intensity in dataset units (km/mol) or normalized 0–1 if any dataset has normalize on.  
Color-coded legend in corner (dataset name + color swatch).

### Plot area — Stack mode

N `<canvas>` elements in a vertical column, each fixed height (min 120px, shrinks to fit).  
All share identical x-axis (same freq range), synchronized zoom/pan.  
Each row has a small y-label (dataset name).  
Rows reorderable by drag.

### Plot area — 2-col mode

Two side-by-side `<canvas>` elements.  
Each has a dataset selector (dropdown showing all loaded datasets).  
X-axes locked (shared freq range, synchronized zoom/pan).

### Axis rendering

Both axes drawn via Canvas 2D:
- X (wavenumber cm⁻¹): labeled ticks, right-to-left convention (high→low) optionally toggled to left-to-right
- Y (intensity): auto-scaled to visible range
- Grid lines: faint dashed lines at major ticks

---

## Zoom / Pan / Inspect

**Zoom:** scroll wheel on plot → zoom x-axis centered on cursor. Y auto-rescales.  
**Pan:** click-drag → translate x-axis.  
**Reset:** double-click → restore full freq range.  
**Freq range inputs** in sidebar stay synchronized with plot zoom.

**Hover:** crosshair line at cursor freq + floating tooltip showing the nearest peak within ±5 cm⁻¹:
- `.out` / `.spec` data: `freq cm⁻¹  intensity` on line 1, then up to 3 projection lines (`label  pct%`) below
- Continuous data: `freq cm⁻¹  intensity` only
- No tooltip if no peak is within tolerance

**Click-to-inspect:** click anywhere on plot →
- Finds nearest peak from any visible `.spec`/`.out` dataset within ±5 cm⁻¹ tolerance
- Opens peak info panel below plot (persists until next click):
  - `.out` data: full projection table (all terms up to cumsum 99%, bra|ket + %, formatted)
  - `.spec` data: dominant assignment label + %
  - Continuous data: freq + intensity at click point

---

## Features Summary

| Feature | Notes |
|---|---|
| Overlay / Stack / 2-col layout | mode tabs in header |
| Per-dataset color, visibility, label | sidebar list |
| Per-dataset intensity scale | ×0.1 to ×100, presets + custom |
| Per-dataset normalize | divide by max |
| Per-dataset FWHM override | or use global |
| Per-dataset freq correction | ×scale + +offset |
| Per-dataset baseline subtraction | constant or linear |
| Global lineshape (L/G) | with per-dataset override |
| Global FWHM slider | |
| Global freq range slider | synced to plot zoom |
| Intensity threshold filter | for peak-type data only |
| Click-to-inspect | full projection for .out |
| Hover crosshair + tooltip | nearest peak label + up to 3 projections |
| Zoom/pan/reset | scroll, drag, double-click |
| Inverted y-axis | for transmittance-style |
| Export PNG | canvas toBlob download |
| x-axis direction toggle | high→low (default) or low→high |

---

## Out of Scope (YAGNI)

- Real-time nonlinear peak fitting
- Peak integration / area calculation
- Batch export of broadened spectra as CSV
- 2D correlation spectroscopy maps
- Raman / NMR support

---

## Verification

1. Open `spectra_viewer/spectra_viewer.html` directly in browser
2. Load `example/FBR_1D.peak` → see broadened spectrum plotted with Lorentzian
3. Load `example/FBR_1D.spec` → second spectrum added; toggle overlay/stack/2-col
4. Load `example/FBR_1D.out` → click a peak → see full projection breakdown in info panel
5. Load an experimental CSV → continuous curve overlaid
6. Adjust FWHM slider → broadening updates live
7. Toggle normalize → y-axes rescale to 0–1
8. Adjust freq correction scale/offset per dataset → peaks shift
9. Zoom (scroll), pan (drag), reset (double-click)
10. Export PNG → downloads image of current view
11. `index.html` has a working link to `spectra_viewer/spectra_viewer.html`
