# Vibration Mode Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single self-contained HTML file that loads Gaussian log or JSON vibration data and renders atomic displacement modes in 3D with Three.js.

**Architecture:** Single HTML file with inline JS organized into labeled sections. A canonical internal JSON schema decouples parsers from rendering. Three.js scene holds two `THREE.Group` objects (`moleculeGroup` for ball-and-stick, `arrowGroup` for displacement arrows) with parallel tracking arrays for efficient per-frame updates.

**Tech Stack:** Three.js r128 (CDN), vanilla JS, no build step.

---

## File Structure

| File | Purpose |
|---|---|
| `vib_viewer/vibration_viewer.html` | Single deliverable — all HTML, CSS, JS inline |
| `example/H2O_CN_MBH.log` | Existing example file used for startup load and manual verification |

---

## Global State Reference

All tasks reference these globals. Defined in Task 1 and populated by later tasks.

```javascript
// Parsed data
let currentMoleculeData = null; // { title, atoms[], modes[] }
let currentMode        = null;  // one mode object { index, frequency, reduced_mass, intensity?, displacements[] }
let currentBonds       = [];    // [[i,j], ...] — what is rendered
let defaultBonds       = [];    // auto-detected (or from JSON) — used by Restore Default

// Three.js
let scene, camera, renderer;
let moleculeGroup, arrowGroup;

// Parallel tracking arrays (indices match atoms[] / currentBonds[])
let atomMeshes       = [];
let bondMeshes       = [];
let arrowMeshGroups  = [];

// Display state
let displayMode       = 'animation'; // 'animation' | 'quiver' | 'both'
let isUserInteracting = false;
let animationTime     = 0;
let lastTimestamp     = null;

// Visual controls
let ballScale     = 0.4;   // multiplier on vdW radius
let stickRadius   = 0.12;  // cylinder radius in scene units
let sticksOnly    = false;
let bondTolerance = 1.25;
let amplitude     = 1.0;
```

---

## Task 1: HTML Scaffold and CSS Layout

**Files:**
- Create: `vib_viewer/vibration_viewer.html`

- [ ] **Step 1: Create the file with full layout**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Vibration Mode Viewer</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body {
      margin: 0; padding: 0; overflow: hidden;
      background: #111827;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      color: #f9fafb;
      display: flex; height: 100vh;
    }
    /* ── Left Panel ── */
    #panel {
      width: 300px; min-width: 300px;
      background: #1f2937;
      border-right: 1px solid #374151;
      display: flex; flex-direction: column;
      overflow: hidden;
    }
    #panel-header {
      padding: 16px 16px 10px;
      border-bottom: 1px solid #374151;
    }
    #panel-header h1 { margin: 0 0 10px; font-size: 1.1rem; font-weight: 600; color: #f3f4f6; }
    .upload-area {
      border: 1px dashed #4b5563;
      border-radius: 8px;
      padding: 10px;
      text-align: center;
      cursor: pointer;
      font-size: 0.85rem;
      color: #9ca3af;
      position: relative;
      transition: border-color 0.2s, background 0.2s;
    }
    .upload-area:hover { border-color: #60a5fa; background: rgba(96,165,250,0.05); }
    .upload-area input[type=file] {
      position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; height: 100%;
    }
    #file-name { margin-top: 4px; font-size: 0.75rem; color: #6b7280; min-height: 1em; }
    /* ── Mode List ── */
    #mode-list-section { display: flex; flex-direction: column; flex: 1; overflow: hidden; padding: 8px 12px 0; }
    .sort-bar { display: flex; gap: 6px; margin-bottom: 6px; }
    .sort-btn {
      flex: 1; padding: 5px; border: 1px solid #374151; border-radius: 6px;
      background: #374151; color: #d1d5db; font-size: 0.8rem; cursor: pointer;
      transition: background 0.15s;
    }
    .sort-btn.active { background: #3b82f6; border-color: #3b82f6; color: #fff; }
    #mode-list {
      flex: 1; overflow-y: auto; border-radius: 6px;
      border: 1px solid #374151;
    }
    .mode-row {
      padding: 7px 10px; cursor: pointer; border-bottom: 1px solid #1f2937;
      font-size: 0.82rem; display: grid;
      grid-template-columns: 2rem 1fr auto;
      gap: 4px; align-items: center;
      transition: background 0.1s;
    }
    .mode-row:hover { background: #2d3748; }
    .mode-row.selected { background: #1d4ed8; }
    .mode-idx { color: #9ca3af; font-size: 0.75rem; }
    .mode-freq { font-weight: 600; color: #e5e7eb; }
    .mode-meta { font-size: 0.73rem; color: #9ca3af; text-align: right; }
    /* ── Controls ── */
    #controls { padding: 10px 12px; border-top: 1px solid #374151; }
    .display-btns { display: flex; gap: 5px; margin-bottom: 10px; }
    .disp-btn {
      flex: 1; padding: 6px 4px; border: 1px solid #374151; border-radius: 6px;
      background: #374151; color: #d1d5db; font-size: 0.8rem; cursor: pointer;
      transition: background 0.15s;
    }
    .disp-btn.active { background: #059669; border-color: #059669; color: #fff; }
    .slider-row { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
    .slider-label { font-size: 0.78rem; color: #9ca3af; width: 72px; flex-shrink: 0; }
    .slider-row input[type=range] { flex: 1; accent-color: #3b82f6; }
    .slider-val { font-size: 0.75rem; color: #6b7280; width: 30px; text-align: right; }
    .checkbox-row { display: flex; align-items: center; gap: 6px; font-size: 0.82rem; color: #9ca3af; margin-top: 4px; }
    .checkbox-row input[type=checkbox] { accent-color: #3b82f6; }
    /* ── Advanced Panel ── */
    #advanced-toggle {
      width: 100%; padding: 8px 12px; background: none; border: none;
      border-top: 1px solid #374151; color: #9ca3af; font-size: 0.8rem;
      text-align: left; cursor: pointer; display: flex; align-items: center; gap: 6px;
    }
    #advanced-toggle:hover { color: #d1d5db; }
    #advanced-body { padding: 10px 12px; border-top: 1px solid #2d3748; display: none; }
    #advanced-body.open { display: block; }
    .adv-label { font-size: 0.78rem; color: #9ca3af; margin-bottom: 4px; margin-top: 8px; }
    #bond-list-textarea {
      width: 100%; height: 80px; background: #111827; border: 1px solid #374151;
      border-radius: 6px; color: #d1d5db; font-size: 0.75rem; font-family: monospace;
      padding: 6px; resize: vertical;
    }
    .adv-btns { display: flex; gap: 6px; margin-top: 6px; }
    .adv-btn {
      flex: 1; padding: 5px; border: 1px solid #374151; border-radius: 6px;
      background: #374151; color: #d1d5db; font-size: 0.78rem; cursor: pointer;
    }
    .adv-btn:hover { background: #4b5563; }
    /* ── Canvas ── */
    #canvas-container { flex: 1; position: relative; }
    #drop-overlay {
      position: fixed; inset: 0;
      background: rgba(17,24,39,0.9); color: #60a5fa;
      display: flex; justify-content: center; align-items: center;
      font-size: 2rem; font-weight: bold; z-index: 100;
      opacity: 0; pointer-events: none; transition: opacity 0.2s;
    }
    #drop-overlay.active { opacity: 1; }
  </style>
</head>
<body>

  <div id="panel">
    <div id="panel-header">
      <h1>Vibration Viewer</h1>
      <div class="upload-area">
        Click or drop .log / .json
        <input type="file" id="file-input" accept=".log,.out,.json">
      </div>
      <div id="file-name"></div>
    </div>

    <div id="mode-list-section">
      <div class="sort-bar">
        <button class="sort-btn active" id="sort-index-btn">Index</button>
        <button class="sort-btn" id="sort-freq-btn">Freq</button>
      </div>
      <div id="mode-list"></div>
    </div>

    <div id="controls">
      <div class="display-btns">
        <button class="disp-btn active" data-mode="animation">Anim</button>
        <button class="disp-btn" data-mode="quiver">Quiver</button>
        <button class="disp-btn" data-mode="both">Both</button>
      </div>
      <div class="slider-row">
        <span class="slider-label">Amplitude</span>
        <input type="range" id="amplitude-slider" min="0" max="3" step="0.05" value="1.0">
        <span class="slider-val" id="amplitude-val">1.0</span>
      </div>
      <div class="slider-row">
        <span class="slider-label">Ball size</span>
        <input type="range" id="ball-slider" min="0.1" max="1.0" step="0.05" value="0.4">
        <span class="slider-val" id="ball-val">0.4</span>
      </div>
      <div class="slider-row">
        <span class="slider-label">Stick size</span>
        <input type="range" id="stick-slider" min="0.02" max="0.3" step="0.01" value="0.12">
        <span class="slider-val" id="stick-val">0.12</span>
      </div>
      <div class="checkbox-row">
        <input type="checkbox" id="sticks-only-cb">
        <label for="sticks-only-cb">Sticks only</label>
      </div>
    </div>

    <button id="advanced-toggle">▸ Advanced</button>
    <div id="advanced-body">
      <div class="adv-label">Bond tolerance</div>
      <div class="slider-row">
        <input type="range" id="tolerance-slider" min="0.8" max="1.8" step="0.05" value="1.25">
        <span class="slider-val" id="tolerance-val">1.25×</span>
      </div>
      <div class="adv-label">Bond list (JSON)</div>
      <textarea id="bond-list-textarea" spellcheck="false"></textarea>
      <div class="adv-btns">
        <button class="adv-btn" id="apply-bonds-btn">Apply</button>
        <button class="adv-btn" id="restore-bonds-btn">Restore Default</button>
      </div>
    </div>
  </div>

  <div id="drop-overlay">Drop .log or .json file here</div>
  <div id="canvas-container"></div>

  <script>
    // === 1. ELEMENT DATA ===
    // === 2. PARSERS ===
    // === 3. SCENE SETUP ===
    // === 4. MOLECULE RENDERING ===
    // === 5. ARROW RENDERING ===
    // === 6. ANIMATION LOOP ===
    // === 7. UI / EVENT HANDLERS ===
  </script>
</body>
</html>
```

- [ ] **Step 2: Open in browser and verify layout**

```
open vib_viewer/vibration_viewer.html
```

Expected: dark two-panel layout renders. Left panel shows "Vibration Viewer", upload area, empty mode list, display buttons (Anim active), three sliders, Sticks only checkbox, Advanced toggle. Right side is black canvas area. No JS errors in console.

- [ ] **Step 3: Commit**

```bash
git init   # only if not already a git repo
git add vib_viewer/vibration_viewer.html
git commit -m "feat: add vibration viewer HTML scaffold with two-panel layout"
```

---

## Task 2: Element Data Tables

**Files:**
- Modify: `vib_viewer/vibration_viewer.html` — replace `// === 1. ELEMENT DATA ===` comment

- [ ] **Step 1: Add element data inside the `<script>` block**

Replace `// === 1. ELEMENT DATA ===` with:

```javascript
// === 1. ELEMENT DATA ===
// Jmol CPK color scheme, all 118 elements
const ELEMENT_COLORS = {
  H:0xFFFFFF, He:0xD9FFFF, Li:0xCC80FF, Be:0xC2FF00, B:0xFFB5B5,
  C:0x909090, N:0x3050F8, O:0xFF0D0D, F:0x90E050, Ne:0xB3E3F5,
  Na:0xAB5CF2, Mg:0x8AFF00, Al:0xBFA6A6, Si:0xF0C8A0, P:0xFF8000,
  S:0xFFFF30, Cl:0x1FF01F, Ar:0x80D1E3, K:0x8F40D4, Ca:0x3DFF00,
  Sc:0xE6E6E6, Ti:0xBFC2C7, V:0xA6A6AB, Cr:0x8A99C7, Mn:0x9C7AC7,
  Fe:0xE06633, Co:0xF090A0, Ni:0x50D050, Cu:0xC88033, Zn:0x7D80B0,
  Ga:0xC28F8F, Ge:0x668F8F, As:0xBD80E3, Se:0xFFA100, Br:0xA62929,
  Kr:0x5CB8D1, Rb:0x702EB0, Sr:0x00FF00, Y:0x94FFFF, Zr:0x94E0E0,
  Nb:0x73C2C9, Mo:0x54B5B5, Tc:0x3B9E9E, Ru:0x248F8F, Rh:0x0A7D8C,
  Pd:0x006985, Ag:0xC0C0C0, Cd:0xFFD98F, In:0xA67573, Sn:0x668080,
  Sb:0x9E63B5, Te:0xD47A00, I:0x940094, Xe:0x429EB0, Cs:0x57178F,
  Ba:0x00C900, La:0x70D4FF, Ce:0xFFFFC7, Pr:0xD9FFC7, Nd:0xC7FFC7,
  Pm:0xA3FFC7, Sm:0x8FFFC7, Eu:0x61FFC7, Gd:0x45FFC7, Tb:0x30FFC7,
  Dy:0x1FFFC7, Ho:0x00FF9C, Er:0x00E675, Tm:0x00D452, Yb:0x00BF38,
  Lu:0x00AB24, Hf:0x4DC2FF, Ta:0x4DA6FF, W:0x2194D6, Re:0x267DAB,
  Os:0x266696, Ir:0x175487, Pt:0xD0D0E0, Au:0xFFD123, Hg:0xB8B8D0,
  Tl:0xA6544D, Pb:0x575961, Bi:0x9E4FB5, Po:0xAB5C00, At:0x754F45,
  Rn:0x428296, Fr:0x420066, Ra:0x007D00, Ac:0x70ABFA, Th:0x00BAFF,
  Pa:0x00A1FF, U:0x008FFF, Np:0x0080FF, Pu:0x006BFF, Am:0x545CF2,
  Cm:0x785CE3, Bk:0x8A4FE3, Cf:0xA136D4, Es:0xB31FD4, Fm:0xB31FBA,
  Md:0xB30DA6, No:0xBD0D87, Lr:0xC70066, Rf:0xCC0059, Db:0xD1004F,
  Sg:0xD90045, Bh:0xE00038, Hs:0xE6002E, Mt:0xEB0026,
  DEFAULT: 0xFF69B4
};

// Van der Waals radii in Å (Bondi/Alvarez) — used for atom sphere size
const VDW_RADII = {
  H:1.20, He:1.40, Li:1.82, Be:1.53, B:1.92, C:1.70, N:1.55, O:1.52,
  F:1.47, Ne:1.54, Na:2.27, Mg:1.73, Al:1.84, Si:2.10, P:1.80, S:1.80,
  Cl:1.75, Ar:1.88, K:2.75, Ca:2.31, Sc:2.11, Ti:2.00, V:2.00, Cr:2.00,
  Mn:2.00, Fe:2.00, Co:2.00, Ni:1.63, Cu:1.40, Zn:1.39, Ga:1.87, Ge:2.11,
  As:1.85, Se:1.90, Br:1.85, Kr:2.02, Rb:3.03, Sr:2.49, Y:2.40, Zr:2.30,
  Nb:2.15, Mo:2.10, Tc:2.05, Ru:2.05, Rh:2.00, Pd:2.05, Ag:2.10, Cd:2.18,
  In:1.93, Sn:2.17, Sb:2.06, Te:2.06, I:1.98, Xe:2.16, Cs:3.43, Ba:2.68,
  Pt:2.13, Au:2.14, Hg:2.23, Tl:1.96, Pb:2.02, Bi:2.07, DEFAULT:2.00
};

// Covalent radii in Å (Alvarez 2008 single bond) — used for bond detection
const COVALENT_RADII = {
  H:0.31, He:0.28, Li:1.28, Be:0.96, B:0.84, C:0.76, N:0.71, O:0.66,
  F:0.57, Ne:0.58, Na:1.66, Mg:1.41, Al:1.21, Si:1.11, P:1.07, S:1.05,
  Cl:1.02, Ar:1.06, K:2.03, Ca:1.76, Sc:1.70, Ti:1.60, V:1.53, Cr:1.39,
  Mn:1.61, Fe:1.52, Co:1.50, Ni:1.24, Cu:1.32, Zn:1.22, Ga:1.22, Ge:1.20,
  As:1.19, Se:1.20, Br:1.20, Kr:1.16, Rb:2.20, Sr:1.95, Y:1.90, Zr:1.75,
  Nb:1.64, Mo:1.54, Tc:1.47, Ru:1.46, Rh:1.42, Pd:1.39, Ag:1.45, Cd:1.44,
  In:1.42, Sn:1.39, Sb:1.39, Te:1.38, I:1.39, Xe:1.40, Cs:2.44, Ba:2.15,
  La:2.07, Hf:1.75, Ta:1.70, W:1.62, Re:1.51, Os:1.44, Ir:1.41, Pt:1.36,
  Au:1.36, Hg:1.32, Tl:1.45, Pb:1.46, Bi:1.48, DEFAULT:1.50
};

// Atomic number → element symbol
const AN_TO_SYMBOL = {
  1:'H',2:'He',3:'Li',4:'Be',5:'B',6:'C',7:'N',8:'O',9:'F',10:'Ne',
  11:'Na',12:'Mg',13:'Al',14:'Si',15:'P',16:'S',17:'Cl',18:'Ar',
  19:'K',20:'Ca',21:'Sc',22:'Ti',23:'V',24:'Cr',25:'Mn',26:'Fe',
  27:'Co',28:'Ni',29:'Cu',30:'Zn',31:'Ga',32:'Ge',33:'As',34:'Se',
  35:'Br',36:'Kr',37:'Rb',38:'Sr',39:'Y',40:'Zr',41:'Nb',42:'Mo',
  43:'Tc',44:'Ru',45:'Rh',46:'Pd',47:'Ag',48:'Cd',49:'In',50:'Sn',
  51:'Sb',52:'Te',53:'I',54:'Xe',55:'Cs',56:'Ba',57:'La',58:'Ce',
  59:'Pr',60:'Nd',61:'Pm',62:'Sm',63:'Eu',64:'Gd',65:'Tb',66:'Dy',
  67:'Ho',68:'Er',69:'Tm',70:'Yb',71:'Lu',72:'Hf',73:'Ta',74:'W',
  75:'Re',76:'Os',77:'Ir',78:'Pt',79:'Au',80:'Hg',81:'Tl',82:'Pb',
  83:'Bi',84:'Po',85:'At',86:'Rn',87:'Fr',88:'Ra',89:'Ac',90:'Th',
  91:'Pa',92:'U',93:'Np',94:'Pu',95:'Am',96:'Cm',97:'Bk',98:'Cf',
  99:'Es',100:'Fm',101:'Md',102:'No',103:'Lr',104:'Rf',105:'Db',
  106:'Sg',107:'Bh',108:'Hs',109:'Mt'
};
```

- [ ] **Step 2: Verify in browser console**

Open `vib_viewer/vibration_viewer.html`, open DevTools console, run:

```javascript
console.assert(ELEMENT_COLORS['C'] === 0x909090, 'Carbon color wrong');
console.assert(VDW_RADII['O'] === 1.52, 'Oxygen vdW wrong');
console.assert(COVALENT_RADII['H'] === 0.31, 'Hydrogen cov radius wrong');
console.assert(AN_TO_SYMBOL[8] === 'O', 'AN 8 should be O');
```

Expected: no assertion failures.

- [ ] **Step 3: Commit**

```bash
git add vib_viewer/vibration_viewer.html
git commit -m "feat: add Jmol CPK color table, vdW/covalent radii, atomic number map"
```

---

## Task 3: JSON Parser

**Files:**
- Modify: `vib_viewer/vibration_viewer.html` — replace `// === 2. PARSERS ===` comment

- [ ] **Step 1: Add JSON parser**

Replace `// === 2. PARSERS ===` with:

```javascript
// === 2. PARSERS ===

function parseJSON(text) {
  const data = JSON.parse(text);
  if (!data.atoms || !Array.isArray(data.atoms)) throw new Error('JSON missing atoms array');
  if (!data.modes || !Array.isArray(data.modes)) throw new Error('JSON missing modes array');
  data.atoms.forEach((a, i) => {
    if (!a.element) throw new Error('Atom ' + i + ' missing element');
    if (a.x === undefined || a.y === undefined || a.z === undefined)
      throw new Error('Atom ' + i + ' missing coordinates');
  });
  data.modes.forEach((m, i) => {
    if (!m.displacements || m.displacements.length !== data.atoms.length)
      throw new Error('Mode ' + i + ' displacements length mismatch');
  });
  if (!data.title) data.title = 'Untitled';
  return data;
}
```

- [ ] **Step 2: Verify in browser console**

```javascript
const sample = JSON.stringify({
  title: 'test', atoms: [{element:'O',x:0,y:0,z:0}],
  modes: [{index:1,frequency:100,reduced_mass:1.0,displacements:[{dx:0.1,dy:0,dz:0}]}]
});
const r = parseJSON(sample);
console.assert(r.atoms.length === 1, 'atoms');
console.assert(r.modes[0].frequency === 100, 'freq');

// Test error on bad input
try { parseJSON('{"atoms":[]}'); console.error('Should have thrown'); }
catch(e) { console.log('Correctly threw:', e.message); }
```

Expected: no assertion failures; error message printed for bad input.

- [ ] **Step 3: Commit**

```bash
git add vib_viewer/vibration_viewer.html
git commit -m "feat: add JSON parser with validation"
```

---

## Task 4: Gaussian Log Parser

**Files:**
- Modify: `vib_viewer/vibration_viewer.html` — add after `parseJSON` function

- [ ] **Step 1: Add Gaussian log parser**

Add after the `parseJSON` function (still inside `// === 2. PARSERS ===`):

```javascript
function parseGaussianLog(text) {
  const lines = text.split('\n');

  // ── Coordinates: last Standard orientation (fall back to Input orientation) ──
  const atoms = [];
  let orientIdx = -1;
  for (let i = lines.length - 1; i >= 0; i--) {
    if (lines[i].includes('Standard orientation:') || lines[i].includes('Input orientation:')) {
      orientIdx = i; break;
    }
  }
  if (orientIdx === -1) throw new Error('No orientation block found in log file');

  // Skip: header line, dashes, col-name line 1, col-name line 2, dashes  (5 lines)
  let i = orientIdx + 5;
  while (i < lines.length) {
    const line = lines[i].trim();
    if (line.startsWith('---')) break;
    const parts = line.split(/\s+/);
    if (parts.length >= 6) {
      const sym = AN_TO_SYMBOL[parseInt(parts[1])] || 'X';
      atoms.push({ element: sym, x: parseFloat(parts[3]), y: parseFloat(parts[4]), z: parseFloat(parts[5]) });
    }
    i++;
  }
  if (atoms.length === 0) throw new Error('No atoms parsed from orientation block');

  // ── Detect format variant ──
  // Modified format: Frequencies -- values are sequential integers (1.0000, 2.0000, ...)
  let isModified = false;
  for (let j = 0; j < lines.length; j++) {
    const t = lines[j].trim();
    if (t.startsWith('Frequencies --')) {
      const vals = t.split('--')[1].trim().split(/\s+/).map(Number);
      isModified = vals.length > 0 && vals.every(v => Math.abs(v - Math.round(v)) < 0.001 && v >= 1);
      break;
    }
  }

  // ── Parse frequency blocks ──
  const parseVals = line => line.split('--')[1].trim().split(/\s+/).map(Number);
  const modes = [];
  let j = 0;
  while (j < lines.length) {
    if (!lines[j].trim().startsWith('Frequencies --')) { j++; continue; }

    const freqVals   = parseVals(lines[j]);
    const redmVals   = parseVals(lines[j + 1]);
    const frcVals    = parseVals(lines[j + 2]);
    const intVals    = parseVals(lines[j + 3]);
    const nModes     = freqVals.length;

    const blockModes = freqVals.map((_, k) => ({
      index:        isModified ? Math.round(freqVals[k]) : modes.length + k + 1,
      frequency:    isModified ? intVals[k]              : freqVals[k],
      reduced_mass: redmVals[k],
      intensity:    isModified ? frcVals[k]              : intVals[k],
      displacements: []
    }));

    // Advance to displacement table header line
    j += 4;
    while (j < lines.length && !lines[j].trim().startsWith('Atom')) j++;
    j++; // skip the 'Atom AN X Y Z ...' header

    let atomCount = 0;
    while (j < lines.length && atomCount < atoms.length) {
      const line = lines[j].trim();
      if (!line || line.startsWith('Frequencies') || line.startsWith('---')) break;
      const parts = line.split(/\s+/);
      // Row layout: [atomIdx, AN, dx0, dy0, dz0,  dx1, dy1, dz1,  dx2, dy2, dz2]
      if (parts.length >= 2 + nModes * 3) {
        for (let k = 0; k < nModes; k++) {
          blockModes[k].displacements.push({
            dx: parseFloat(parts[2 + k * 3]),
            dy: parseFloat(parts[3 + k * 3]),
            dz: parseFloat(parts[4 + k * 3])
          });
        }
        atomCount++;
      }
      j++;
    }

    // Only add fully parsed modes
    blockModes.filter(m => m.displacements.length === atoms.length).forEach(m => modes.push(m));
  }

  if (modes.length === 0) throw new Error('No vibrational modes parsed from log file');

  return { title: 'Gaussian Log', atoms, modes };
}

// Auto-detect format and dispatch
function parseFile(text, filename) {
  const ext = filename.split('.').pop().toLowerCase();
  if (ext === 'json') return parseJSON(text);
  return parseGaussianLog(text); // .log, .out, or anything else
}
```

- [ ] **Step 2: Verify in browser console**

After loading the page, run in console (requires the example file text — paste the first 10 lines manually or load via fetch if serving locally):

```javascript
// Quick structural check on the known example file
// Fetch only works from http://, not file://. 
// Instead open the file, copy its content, then:
// const logText = `<paste content here>`;
// const r = parseGaussianLog(logText);
// console.assert(r.atoms.length === 5, '5 atoms (O,H,H,C,N)');
// console.assert(r.modes.length === 8, '8 modes');
// console.assert(r.modes[0].index === 1, 'first mode index = 1');
// console.assert(Math.abs(r.modes[0].frequency - 100.44) < 0.1, 'first freq ~100.44');
// console.assert(r.modes[0].displacements.length === 5, '5 displacements');
// console.log('format:', r.modes[0].index === 1 ? 'modified ✓' : 'standard');
```

Expected: all assertions pass, format detected as modified.

- [ ] **Step 3: Commit**

```bash
git add vib_viewer/vibration_viewer.html
git commit -m "feat: add Gaussian log parser with modified/standard format auto-detection"
```

---

## Task 5: Three.js Scene Setup and Interaction

**Files:**
- Modify: `vib_viewer/vibration_viewer.html` — replace `// === 3. SCENE SETUP ===`

- [ ] **Step 1: Add global state variables and scene init**

Replace `// === 3. SCENE SETUP ===` with:

```javascript
// === 3. SCENE SETUP ===

// Global state (see plan header for full reference)
let currentMoleculeData = null, currentMode = null;
let currentBonds = [], defaultBonds = [];
let scene, camera, renderer, moleculeGroup, arrowGroup;
let atomMeshes = [], bondMeshes = [], arrowMeshGroups = [];
let displayMode = 'animation', isUserInteracting = false;
let animationTime = 0, lastTimestamp = null;
let ballScale = 0.4, stickRadius = 0.12, sticksOnly = false;
let bondTolerance = 1.25, amplitude = 1.0;

function initScene() {
  const container = document.getElementById('canvas-container');

  scene = new THREE.Scene();

  camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 2000);
  camera.position.set(0, 0, 15);

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setSize(container.clientWidth, container.clientHeight);
  renderer.setPixelRatio(window.devicePixelRatio);
  container.appendChild(renderer.domElement);

  scene.add(new THREE.AmbientLight(0xffffff, 0.5));
  const d1 = new THREE.DirectionalLight(0xffffff, 0.7);
  d1.position.set(10, 20, 15);
  scene.add(d1);
  const d2 = new THREE.DirectionalLight(0xaaccff, 0.3);
  d2.position.set(-10, -10, -15);
  scene.add(d2);

  moleculeGroup = new THREE.Group();
  arrowGroup    = new THREE.Group();
  scene.add(moleculeGroup);
  scene.add(arrowGroup);

  setupInteraction(container);
  window.addEventListener('resize', () => {
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
  });
}

function setupInteraction(container) {
  let prev = { x: 0, y: 0 };

  const getXY = e => e.touches
    ? { x: e.touches[0].clientX, y: e.touches[0].clientY }
    : { x: e.offsetX, y: e.offsetY };

  const onStart = e => { isUserInteracting = true; prev = getXY(e); };
  const onEnd   = ()  => { isUserInteracting = false; };
  const onMove  = e  => {
    if (!isUserInteracting) return;
    const cur = getXY(e);
    moleculeGroup.rotation.y += (cur.x - prev.x) * 0.008;
    moleculeGroup.rotation.x += (cur.y - prev.y) * 0.008;
    arrowGroup.rotation.y = moleculeGroup.rotation.y;
    arrowGroup.rotation.x = moleculeGroup.rotation.x;
    prev = cur;
  };

  container.addEventListener('mousedown',  onStart);
  document.addEventListener('mouseup',     onEnd);
  document.addEventListener('mousemove',   onMove);
  container.addEventListener('touchstart', onStart, { passive: false });
  container.addEventListener('touchend',   onEnd);
  container.addEventListener('touchmove',  onMove,  { passive: false });

  container.addEventListener('wheel', e => {
    camera.position.z = Math.max(3, Math.min(200, camera.position.z + e.deltaY * 0.05));
  });
}
```

- [ ] **Step 2: Verify in browser console**

Add `initScene(); animate();` calls at the bottom of the script (temporarily), reload, confirm:
- No console errors
- Black canvas fills the right side
- No molecule yet (correct)

Remove the temporary calls after verifying — they'll be added properly in Task 12.

- [ ] **Step 3: Commit**

```bash
git add vib_viewer/vibration_viewer.html
git commit -m "feat: add Three.js scene init, camera, lights, and mouse/touch interaction"
```

---

## Task 6: Bond Detection and Molecule Rendering

**Files:**
- Modify: `vib_viewer/vibration_viewer.html` — replace `// === 4. MOLECULE RENDERING ===`

- [ ] **Step 1: Add bond detection and render functions**

Replace `// === 4. MOLECULE RENDERING ===` with:

```javascript
// === 4. MOLECULE RENDERING ===

function detectBonds(atoms, tolerance) {
  const bonds = [];
  for (let i = 0; i < atoms.length; i++) {
    for (let j = i + 1; j < atoms.length; j++) {
      const ri = COVALENT_RADII[atoms[i].element] || COVALENT_RADII.DEFAULT;
      const rj = COVALENT_RADII[atoms[j].element] || COVALENT_RADII.DEFAULT;
      const dx = atoms[i].x - atoms[j].x;
      const dy = atoms[i].y - atoms[j].y;
      const dz = atoms[i].z - atoms[j].z;
      const distSq = dx*dx + dy*dy + dz*dz;
      const thresh = tolerance * (ri + rj);
      if (distSq < thresh * thresh && distSq > 0.01) bonds.push([i, j]);
    }
  }
  return bonds;
}

// Shared geometries — created once, reused across all atom/bond meshes
const _sphereGeo = new THREE.SphereGeometry(1, 32, 32);
const _cylGeo    = (() => { const g = new THREE.CylinderGeometry(1, 1, 1, 12); g.rotateX(Math.PI / 2); return g; })();

function renderMolecule(atoms, bonds) {
  // Dispose existing meshes
  while (moleculeGroup.children.length > 0) {
    const c = moleculeGroup.children[0];
    moleculeGroup.remove(c);
    if (c.material) c.material.dispose();
  }
  atomMeshes = [];
  bondMeshes = [];

  // Cache per-element materials
  const matCache = {};
  const getAtomMat = elem => {
    if (!matCache[elem]) {
      matCache[elem] = new THREE.MeshStandardMaterial({
        color: ELEMENT_COLORS[elem] || ELEMENT_COLORS.DEFAULT,
        roughness: 0.35, metalness: 0.3
      });
    }
    return matCache[elem];
  };

  // Atom spheres
  atoms.forEach((atom, i) => {
    const r = VDW_RADII[atom.element] || VDW_RADII.DEFAULT;
    const mesh = new THREE.Mesh(_sphereGeo, getAtomMat(atom.element));
    mesh.scale.setScalar(sticksOnly ? 0 : r * ballScale);
    mesh.position.set(atom.x, atom.y, atom.z);
    mesh.userData = { type: 'atom', atomIndex: i };
    moleculeGroup.add(mesh);
    atomMeshes.push(mesh);
  });

  // Bond cylinders
  const bondMat = new THREE.MeshStandardMaterial({ color: 0x9ca3af, roughness: 0.4, metalness: 0.6 });
  bonds.forEach(([i, j]) => {
    const v1 = new THREE.Vector3(atoms[i].x, atoms[i].y, atoms[i].z);
    const v2 = new THREE.Vector3(atoms[j].x, atoms[j].y, atoms[j].z);
    const mesh = new THREE.Mesh(_cylGeo, bondMat);
    setBondTransform(mesh, v1, v2);
    moleculeGroup.add(mesh);
    bondMeshes.push(mesh);
  });

  // Center camera
  let maxDistSq = 0;
  atoms.forEach(a => { const d = a.x*a.x + a.y*a.y + a.z*a.z; if (d > maxDistSq) maxDistSq = d; });
  moleculeGroup.rotation.set(0, 0, 0);
  arrowGroup.rotation.set(0, 0, 0);
  camera.position.set(0, 0, Math.max(10, Math.sqrt(maxDistSq) * 2.5));
  camera.lookAt(0, 0, 0);
}

function setBondTransform(mesh, v1, v2) {
  const mid  = v1.clone().add(v2).multiplyScalar(0.5);
  const dist = v1.distanceTo(v2);
  const dir  = v2.clone().sub(v1).normalize();
  mesh.position.copy(mid);
  mesh.scale.set(stickRadius, stickRadius, dist);
  const up = new THREE.Vector3(0, 0, 1);
  if (Math.abs(dir.dot(up) + 1) < 0.0001) {
    mesh.quaternion.set(1, 0, 0, 0); // 180° antiparallel edge case
  } else {
    mesh.quaternion.setFromUnitVectors(up, dir);
  }
}
```

- [ ] **Step 2: Wire up a quick smoke test in the console**

In browser console, after `initScene()` has been called (add temporarily to bottom of script for this test):

```javascript
const testAtoms = [
  {element:'C', x:0, y:0, z:0},
  {element:'C', x:1.54, y:0, z:0}
];
const bonds = detectBonds(testAtoms, 1.25);
console.assert(bonds.length === 1, 'Should detect 1 C-C bond, got: ' + bonds.length);
renderMolecule(testAtoms, bonds);
// Verify in canvas: two grey spheres connected by a grey stick
```

Expected: two CPK carbon spheres with one bond visible on canvas.

- [ ] **Step 3: Commit**

```bash
git add vib_viewer/vibration_viewer.html
git commit -m "feat: add bond detection and ball-and-stick molecule renderer with CPK colors"
```

---

## Task 7: Mode List UI

**Files:**
- Modify: `vib_viewer/vibration_viewer.html` — replace `// === 7. UI / EVENT HANDLERS ===`

- [ ] **Step 1: Add mode list functions**

Replace `// === 7. UI / EVENT HANDLERS ===` with:

```javascript
// === 7. UI / EVENT HANDLERS ===

let sortMode = 'index'; // 'index' | 'freq'

function populateModeList(modes) {
  const list = document.getElementById('mode-list');
  list.innerHTML = '';

  const hasIntensity = modes.some(m => m.intensity !== undefined);
  const sorted = [...modes].sort((a, b) =>
    sortMode === 'freq' ? a.frequency - b.frequency : a.index - b.index
  );

  sorted.forEach(mode => {
    const row = document.createElement('div');
    row.className = 'mode-row';
    row.dataset.index = mode.index;

    const metaStr = hasIntensity
      ? `m=${mode.reduced_mass.toFixed(2)}&nbsp;&nbsp;I=${mode.intensity.toFixed(1)}`
      : `m=${mode.reduced_mass.toFixed(2)}`;

    row.innerHTML = `
      <span class="mode-idx">#${mode.index}</span>
      <span class="mode-freq">${mode.frequency.toFixed(1)} cm⁻¹</span>
      <span class="mode-meta">${metaStr}</span>
    `;
    row.addEventListener('click', () => selectMode(mode));
    list.appendChild(row);
  });
}

function selectMode(mode) {
  currentMode = mode;
  animationTime = 0;
  lastTimestamp = null;

  // Update highlighted row
  document.querySelectorAll('.mode-row').forEach(r => r.classList.remove('selected'));
  const target = document.querySelector(`.mode-row[data-index="${mode.index}"]`);
  if (target) {
    target.classList.add('selected');
    target.scrollIntoView({ block: 'nearest' });
  }

  buildArrows(currentMoleculeData.atoms, mode);
}

// Sort buttons
document.getElementById('sort-index-btn').addEventListener('click', () => {
  sortMode = 'index';
  document.getElementById('sort-index-btn').classList.add('active');
  document.getElementById('sort-freq-btn').classList.remove('active');
  if (currentMoleculeData) populateModeList(currentMoleculeData.modes);
});
document.getElementById('sort-freq-btn').addEventListener('click', () => {
  sortMode = 'freq';
  document.getElementById('sort-freq-btn').classList.add('active');
  document.getElementById('sort-index-btn').classList.remove('active');
  if (currentMoleculeData) populateModeList(currentMoleculeData.modes);
});
```

- [ ] **Step 2: Add display mode buttons**

Add after the sort button listeners:

```javascript
// Display mode buttons
document.querySelectorAll('.disp-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    displayMode = btn.dataset.mode;
    document.querySelectorAll('.disp-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    if (displayMode === 'quiver' || displayMode === 'both') {
      arrowGroup.visible = true;
    } else {
      arrowGroup.visible = false;
    }
    // Reset atom positions to equilibrium when switching away from animation
    if (currentMoleculeData && currentMode) {
      atomMeshes.forEach((mesh, i) => {
        const a = currentMoleculeData.atoms[i];
        mesh.position.set(a.x, a.y, a.z);
      });
      currentBonds.forEach(([i, j], idx) => {
        setBondTransform(bondMeshes[idx],
          atomMeshes[i].position, atomMeshes[j].position);
      });
    }
  });
});
```

- [ ] **Step 3: Verify in browser console**

```javascript
// Simulate loading modes
const fakeModes = [
  {index:1,frequency:100.4,reduced_mass:8.11,intensity:2.5,displacements:[]},
  {index:2,frequency:114.9,reduced_mass:7.25,intensity:7.4,displacements:[]},
];
populateModeList(fakeModes);
```

Expected: two rows appear in the mode list with correct values. Clicking "Freq" sort button reverses order.

- [ ] **Step 4: Commit**

```bash
git add vib_viewer/vibration_viewer.html
git commit -m "feat: add mode list with sort buttons and display mode switcher"
```

---

## Task 8: Arrow (Quiver) Rendering

**Files:**
- Modify: `vib_viewer/vibration_viewer.html` — replace `// === 5. ARROW RENDERING ===`

- [ ] **Step 1: Add arrow build and update functions**

Replace `// === 5. ARROW RENDERING ===` with:

```javascript
// === 5. ARROW RENDERING ===

const MAX_ARROW_LEN  = 3.0;  // scene units for the longest arrow in a mode
const MIN_DISP_FRAC  = 0.01; // hide arrows below 1% of mode max displacement
const ARROW_COLOR    = 0x00FFAA;

function buildArrows(atoms, mode) {
  // Dispose existing arrows
  while (arrowGroup.children.length > 0) {
    const g = arrowGroup.children[0];
    arrowGroup.remove(g);
    g.traverse(c => { if (c.geometry) c.geometry.dispose(); if (c.material) c.material.dispose(); });
  }
  arrowMeshGroups = [];

  const mags = mode.displacements.map(d => Math.sqrt(d.dx*d.dx + d.dy*d.dy + d.dz*d.dz));
  const maxMag = Math.max(...mags);
  if (maxMag === 0) return;

  const arrowMat = new THREE.MeshStandardMaterial({ color: ARROW_COLOR, roughness: 0.3, metalness: 0.2 });

  atoms.forEach((atom, i) => {
    const group = new THREE.Group();
    group.position.set(atom.x, atom.y, atom.z);

    const frac = mags[i] / maxMag;
    if (frac >= MIN_DISP_FRAC) {
      const totalLen  = MAX_ARROW_LEN * frac;
      const shaftLen  = totalLen * 0.78;
      const headLen   = totalLen * 0.22;
      const shaftR    = 0.055;
      const headR     = 0.13;

      // Shaft: CylinderGeometry along Y, translate so base is at origin
      const shaftGeo = new THREE.CylinderGeometry(shaftR, shaftR, shaftLen, 8);
      shaftGeo.translate(0, shaftLen / 2, 0);
      group.add(new THREE.Mesh(shaftGeo, arrowMat));

      // Head: cone at tip
      const headGeo = new THREE.ConeGeometry(headR, headLen, 8);
      headGeo.translate(0, shaftLen + headLen / 2, 0);
      group.add(new THREE.Mesh(headGeo, arrowMat));

      // Rotate group so +Y points along displacement direction
      const dir = new THREE.Vector3(mode.displacements[i].dx, mode.displacements[i].dy, mode.displacements[i].dz).normalize();
      const up  = new THREE.Vector3(0, 1, 0);
      if (Math.abs(dir.dot(up) + 1) < 0.0001) {
        group.quaternion.set(1, 0, 0, 0); // antiparallel edge case
      } else {
        group.quaternion.setFromUnitVectors(up, dir);
      }
    }

    arrowGroup.add(group);
    arrowMeshGroups.push(group);
  });

  arrowGroup.rotation.copy(moleculeGroup.rotation);
  arrowGroup.visible = (displayMode === 'quiver' || displayMode === 'both');
}

function updateArrowPositions() {
  atomMeshes.forEach((mesh, i) => {
    if (arrowMeshGroups[i]) arrowMeshGroups[i].position.copy(mesh.position);
  });
}
```

- [ ] **Step 2: Verify in browser console**

With a molecule loaded (from Task 6 smoke test):

```javascript
const testMode = {
  index: 1, frequency: 100, reduced_mass: 1,
  displacements: [
    {dx: 0.5, dy: 0, dz: 0},
    {dx: -0.5, dy: 0, dz: 0}
  ]
};
buildArrows(
  [{element:'C',x:-0.77,y:0,z:0},{element:'C',x:0.77,y:0,z:0}],
  testMode
);
arrowGroup.visible = true;
```

Expected: two green arrows pointing in opposite directions along X, longer than the atoms.

- [ ] **Step 3: Commit**

```bash
git add vib_viewer/vibration_viewer.html
git commit -m "feat: add quiver arrow rendering with proportional scaling"
```

---

## Task 9: Animation Loop

**Files:**
- Modify: `vib_viewer/vibration_viewer.html` — replace `// === 6. ANIMATION LOOP ===`

- [ ] **Step 1: Add the animation loop and amplitude slider**

Replace `// === 6. ANIMATION LOOP ===` with:

```javascript
// === 6. ANIMATION LOOP ===

const ANIM_PERIOD = 2.0; // seconds per oscillation cycle

function updateDisplay(t) {
  if (!currentMode || !currentMoleculeData) return;

  const offset = (displayMode === 'animation' || displayMode === 'both')
    ? amplitude * Math.sin(2 * Math.PI * t / ANIM_PERIOD)
    : 0;

  // Update atom positions
  atomMeshes.forEach((mesh, i) => {
    const a = currentMoleculeData.atoms[i];
    const d = currentMode.displacements[i];
    mesh.position.set(a.x + offset * d.dx, a.y + offset * d.dy, a.z + offset * d.dz);
  });

  // Update bond positions when atoms have moved
  if (displayMode === 'animation' || displayMode === 'both') {
    currentBonds.forEach(([i, j], idx) => {
      if (bondMeshes[idx]) setBondTransform(bondMeshes[idx], atomMeshes[i].position, atomMeshes[j].position);
    });
  }

  // Update arrow positions in 'both' mode
  if (displayMode === 'both') updateArrowPositions();
}

function animate(timestamp) {
  requestAnimationFrame(animate);

  if (lastTimestamp === null) lastTimestamp = timestamp;

  if (!isUserInteracting && currentMode && (displayMode === 'animation' || displayMode === 'both')) {
    animationTime += (timestamp - lastTimestamp) / 1000;
  }
  lastTimestamp = timestamp;

  updateDisplay(animationTime);
  renderer.render(scene, camera);
}
```

- [ ] **Step 2: Add amplitude slider handler**

Add after the animation functions (still inside `// === 6. ANIMATION LOOP ===`):

```javascript
const amplitudeSlider = document.getElementById('amplitude-slider');
const amplitudeVal    = document.getElementById('amplitude-val');
amplitudeSlider.addEventListener('input', () => {
  amplitude = parseFloat(amplitudeSlider.value);
  amplitudeVal.textContent = amplitude.toFixed(2);
});
```

- [ ] **Step 3: Verify**

Load a molecule from Task 6, select a mode via `selectMode(fakeModes[0])` in console, set `displayMode = 'animation'`, then confirm atoms oscillate on canvas when `animate()` is called.

- [ ] **Step 4: Commit**

```bash
git add vib_viewer/vibration_viewer.html
git commit -m "feat: add animation loop with sinusoidal oscillation and amplitude slider"
```

---

## Task 10: Visual Controls (Ball/Stick Sliders, Sticks Only)

**Files:**
- Modify: `vib_viewer/vibration_viewer.html` — add to `// === 7. UI / EVENT HANDLERS ===`

- [ ] **Step 1: Add ball size, stick size, and sticks-only handlers**

Add after the display mode button listeners in `// === 7. UI / EVENT HANDLERS ===`:

```javascript
// Ball size slider
const ballSlider = document.getElementById('ball-slider');
const ballVal    = document.getElementById('ball-val');
ballSlider.addEventListener('input', () => {
  ballScale = parseFloat(ballSlider.value);
  ballVal.textContent = ballScale.toFixed(2);
  if (!sticksOnly) applyBallScale();
});

// Stick size slider
const stickSlider = document.getElementById('stick-slider');
const stickVal    = document.getElementById('stick-val');
stickSlider.addEventListener('input', () => {
  stickRadius = parseFloat(stickSlider.value);
  stickVal.textContent = stickRadius.toFixed(2);
  bondMeshes.forEach(mesh => {
    mesh.scale.x = stickRadius;
    mesh.scale.y = stickRadius;
  });
});

// Sticks only toggle
const sticksOnlyCb = document.getElementById('sticks-only-cb');
sticksOnlyCb.addEventListener('change', () => {
  sticksOnly = sticksOnlyCb.checked;
  ballSlider.disabled = sticksOnly;
  applyBallScale();
});

function applyBallScale() {
  atomMeshes.forEach((mesh, i) => {
    const elem = currentMoleculeData ? currentMoleculeData.atoms[i].element : 'C';
    const r = VDW_RADII[elem] || VDW_RADII.DEFAULT;
    mesh.scale.setScalar(sticksOnly ? 0 : r * ballScale);
  });
}
```

- [ ] **Step 2: Verify**

With a molecule on screen:
- Drag Ball size slider → spheres grow/shrink without rebuilding
- Drag Stick size slider → cylinders thicken/thin without rebuilding
- Check Sticks only → spheres disappear, ball slider grays out; uncheck → spheres return

- [ ] **Step 3: Commit**

```bash
git add vib_viewer/vibration_viewer.html
git commit -m "feat: add ball/stick size sliders and sticks-only toggle"
```

---

## Task 11: Advanced Panel — Connectivity Editing

**Files:**
- Modify: `vib_viewer/vibration_viewer.html` — add to `// === 7. UI / EVENT HANDLERS ===`

- [ ] **Step 1: Add advanced panel toggle and connectivity handlers**

Add after the sticks-only handler:

```javascript
// Advanced panel toggle
const advToggle = document.getElementById('advanced-toggle');
const advBody   = document.getElementById('advanced-body');
advToggle.addEventListener('click', () => {
  advBody.classList.toggle('open');
  advToggle.textContent = advBody.classList.contains('open') ? '▾ Advanced' : '▸ Advanced';
});

// Tolerance slider — regenerates default bonds in real time
const toleranceSlider = document.getElementById('tolerance-slider');
const toleranceVal    = document.getElementById('tolerance-val');
toleranceSlider.addEventListener('input', () => {
  bondTolerance = parseFloat(toleranceSlider.value);
  toleranceVal.textContent = bondTolerance.toFixed(2) + '×';
  if (currentMoleculeData) {
    defaultBonds = detectBonds(currentMoleculeData.atoms, bondTolerance);
    updateBondTextarea(defaultBonds);
    applyBonds(defaultBonds);
  }
});

// Apply button — parse textarea and re-render bonds
document.getElementById('apply-bonds-btn').addEventListener('click', () => {
  const textarea = document.getElementById('bond-list-textarea');
  try {
    const parsed = JSON.parse(textarea.value);
    if (!Array.isArray(parsed)) throw new Error('Expected array');
    applyBonds(parsed);
    currentBonds = parsed;
  } catch (e) {
    alert('Invalid bond list JSON: ' + e.message);
  }
});

// Restore Default — reset to auto-detected bonds
document.getElementById('restore-bonds-btn').addEventListener('click', () => {
  currentBonds = defaultBonds.slice();
  updateBondTextarea(currentBonds);
  applyBonds(currentBonds);
});

function updateBondTextarea(bonds) {
  document.getElementById('bond-list-textarea').value = JSON.stringify(bonds);
}

function applyBonds(bonds) {
  currentBonds = bonds;
  if (!currentMoleculeData) return;
  renderMolecule(currentMoleculeData.atoms, bonds);
  if (currentMode) buildArrows(currentMoleculeData.atoms, currentMode);
}
```

- [ ] **Step 2: Verify**

With molecule loaded:
- Open Advanced panel → textarea shows current bond list as JSON
- Edit a bond pair in textarea, click Apply → bond appears/disappears on canvas
- Click Restore Default → original connectivity restored
- Drag tolerance slider → bonds update live and textarea reflects new list

- [ ] **Step 3: Commit**

```bash
git add vib_viewer/vibration_viewer.html
git commit -m "feat: add advanced connectivity editor with tolerance slider and apply/restore"
```

---

## Task 12: File Loading, Drag & Drop, and Startup

**Files:**
- Modify: `vib_viewer/vibration_viewer.html` — add to `// === 7. UI / EVENT HANDLERS ===`, add `window.onload`

- [ ] **Step 1: Add file loading logic**

Add after the connectivity handlers:

```javascript
function loadMoleculeData(data, filename) {
  currentMoleculeData = data;
  currentMode = null;
  animationTime = 0;
  lastTimestamp = null;

  // Center molecule at origin
  const cx = data.atoms.reduce((s, a) => s + a.x, 0) / data.atoms.length;
  const cy = data.atoms.reduce((s, a) => s + a.y, 0) / data.atoms.length;
  const cz = data.atoms.reduce((s, a) => s + a.z, 0) / data.atoms.length;
  data.atoms.forEach(a => { a.x -= cx; a.y -= cy; a.z -= cz; });

  // Bonds: use explicit bonds from JSON if present, else auto-detect
  defaultBonds = data.bonds ? data.bonds : detectBonds(data.atoms, bondTolerance);
  currentBonds = defaultBonds.slice();
  updateBondTextarea(currentBonds);

  renderMolecule(data.atoms, currentBonds);
  populateModeList(data.modes);
  document.getElementById('file-name').textContent = filename;

  // Auto-select first mode
  if (data.modes.length > 0) selectMode(data.modes[0]);
}

function handleFile(file) {
  const reader = new FileReader();
  reader.onload = e => {
    try {
      const data = parseFile(e.target.result, file.name);
      loadMoleculeData(data, file.name);
    } catch (err) {
      alert('Error loading file: ' + err.message);
    }
  };
  reader.readAsText(file);
}

// File input button
document.getElementById('file-input').addEventListener('change', e => {
  if (e.target.files.length > 0) handleFile(e.target.files[0]);
});

// Drag & drop
const overlay = document.getElementById('drop-overlay');
window.addEventListener('dragover',  e => { e.preventDefault(); overlay.classList.add('active'); });
window.addEventListener('dragleave', e => { e.preventDefault(); overlay.classList.remove('active'); });
window.addEventListener('drop', e => {
  e.preventDefault();
  overlay.classList.remove('active');
  if (e.dataTransfer.files.length > 0) handleFile(e.dataTransfer.files[0]);
});
```

- [ ] **Step 2: Add `window.onload` with startup example**

Add after all the event handlers, before the closing `</script>`:

```javascript
window.onload = function () {
  initScene();
  animate();

  // Load example file on startup
  fetch('../example/H2O_CN_MBH.log')
    .then(r => r.ok ? r.text() : Promise.reject('fetch failed'))
    .then(text => {
      const data = parseGaussianLog(text);
      loadMoleculeData(data, 'H2O_CN_MBH.log');
    })
    .catch(() => {
      // Silently skip if fetch fails (e.g. opened via file:// — user loads manually)
    });
};
```

- [ ] **Step 3: Serve locally and verify end-to-end**

```bash
# Python simple server from project root
python3 -m http.server 8080
```

Open `http://localhost:8080/vib_viewer/vibration_viewer.html`

Full verification checklist:
- [ ] H2O_CN_MBH.log loads on startup, 5 atoms and 8 modes appear
- [ ] Molecule renders with CPK colors (O red, H white, C grey, N blue)
- [ ] Mode list shows 8 entries; mode #1 selected and highlighted
- [ ] Animation mode: atoms oscillate. Sort by Freq button reorders list.
- [ ] Quiver mode: static green arrows on each atom showing displacements
- [ ] Both mode: arrows ride with oscillating atoms
- [ ] Amplitude slider changes oscillation magnitude
- [ ] Ball size slider resizes spheres; Stick size slider resizes cylinders
- [ ] Sticks Only: spheres disappear, slider grays out
- [ ] Drag & drop a .json file with the schema from Task 3 — loads correctly
- [ ] Advanced panel: edit tolerance, Apply bond changes, Restore Default

- [ ] **Step 4: Final commit**

```bash
git add vib_viewer/vibration_viewer.html
git commit -m "feat: complete vibration mode viewer with file loading and startup example"
```

---

## Self-Review Checklist

| Spec requirement | Covered in |
|---|---|
| Gaussian log parser — standard + modified format auto-detect | Task 4 |
| JSON schema with optional bonds/intensity | Task 3 |
| Full Jmol CPK color table, 118 elements | Task 2 |
| Ball-and-stick with adjustable ball/stick size | Tasks 6, 10 |
| Sticks-only mode disables ball slider | Task 10 |
| Scrollable mode list with Index/Freq sort | Task 7 |
| Intensity column shown only if present | Task 7 (`hasIntensity` flag) |
| Animation / Quiver / Both display modes | Tasks 8, 9 |
| Single amplitude slider | Task 9 |
| Arrows proportional to displacement magnitude | Task 8 |
| Arrows ride with atoms in Both mode | Task 9 (`updateArrowPositions`) |
| Advanced panel: tolerance slider + bond list editor | Task 11 |
| Apply / Restore Default connectivity | Task 11 |
| defaultBonds vs currentBonds separation | Tasks 11, 12 |
| Auto-select first mode on load | Task 12 |
| Molecule centered at origin on load | Task 12 |
| Drag & drop + click-to-upload | Task 12 |
| Startup loads example file | Task 12 |
| Interaction pauses animation | Tasks 5, 9 |
