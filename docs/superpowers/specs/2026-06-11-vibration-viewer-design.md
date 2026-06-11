# Vibration Mode Viewer — Design Spec

**Date:** 2026-06-11  
**Status:** Approved

---

## Overview

A single self-contained HTML file (no build step, open directly in browser) that loads a molecular vibrational mode dataset and visualizes atomic displacements in 3D using Three.js. Supports Gaussian log files (standard and modified MBH/local mode format) and a canonical JSON format.

---

## Architecture

Single HTML file with inline JavaScript organized into named sections:

1. Element data table (CPK colors + van der Waals radii, all 118 elements, Jmol scheme)
2. File parsers (Gaussian log auto-detect, JSON pass-through)
3. Three.js scene setup
4. Molecule rendering (ball-and-stick)
5. Arrow rendering (quiver)
6. Animation loop
7. UI / event handlers

**Planned future refactor:** split into `index.html` + `parser.js` + `renderer.js` + `ui.js` (Approach C) once multiple parsers accumulate. No structural changes needed to enable this — the sections map directly to files.

---

## Data Schema

Internal representation (also the accepted JSON file format):

```json
{
  "title": "H2O_CN_MBH",
  "atoms": [
    { "element": "O", "x": -0.00, "y": -1.31, "z": 0.13 }
  ],
  "bonds": [[0, 1], [0, 2]],
  "modes": [
    {
      "index": 1,
      "frequency": 100.44,
      "reduced_mass": 8.108,
      "intensity": 2.541,
      "displacements": [
        { "dx": 0.00, "dy": 0.14, "dz": 0.03 }
      ]
    }
  ]
}
```

- `bonds` is optional. If absent, bonds are auto-detected from geometry.
- `intensity` is optional. Omitted if the source does not provide it.
- `displacements` has one entry per atom, same order as `atoms`.
- Atomic numbers in Gaussian log are mapped to element symbols via a lookup table.

---

## File Parsers

### Gaussian Log Parser (`parseGaussianLog`)

**Auto-detection of format variant:**

| Condition | Format |
|---|---|
| `Frequencies --` values are sequential integers (1.0000, 2.0000, …) | **Modified** (MBH/local mode) |
| `Frequencies --` values are real numbers | **Standard** Gaussian |

**Field mapping by format:**

| File field | Standard meaning | Modified meaning |
|---|---|---|
| `Frequencies --` | frequency (cm⁻¹) | mode index |
| `Red. masses --` | reduced mass (AMU) | reduced mass (AMU) |
| `Frc consts --` | force constant (ignored) | intensity |
| `IR Inten --` | intensity | frequency (cm⁻¹) |

**Parsing steps:**
1. Read the last `Standard orientation` block for atom coordinates (atomic number → element symbol).
2. Collect all frequency blocks. Each block has 1–3 modes in parallel columns.
3. Parse displacement table (`Atom AN X Y Z …`) — each row has one (dx, dy, dz) triplet per mode in the block.
4. Assemble into internal schema.

### JSON Parser (`parseJSON`)

Validates presence of required fields and passes through directly. `bonds` and `intensity` are accepted but not required.

### Format Detection on Load

File extension determines parser: `.log` / `.out` → Gaussian, `.json` → JSON.

---

## Rendering

### Ball-and-Stick with CPK Colors

- **Atom spheres:** shared `SphereGeometry`, per-element `MeshStandardMaterial` using Jmol CPK colors. Visual radius = `vdW_radius[element] × ball_scale` where `ball_scale` is driven by the Ball Size slider.
- **Bond cylinders:** shared `CylinderGeometry` (pre-rotated 90° on X so `lookAt` aligns to bond axis). Radius driven by Stick Size slider.
- **Sticks Only mode:** sets `ball_scale` to 0 (spheres invisible) and disables the Ball Size slider.
- All atoms and bonds placed in `moleculeGroup`. Molecule centered at origin on load.

### Bond Detection

O(N²) pairwise distance check: bond exists if `distance < tolerance × (covalent_radius[i] + covalent_radius[j])` and `distance > 0.1 Å`. Default tolerance = 1.25×. Recomputed only on molecule load or when tolerance/bond list changes.

**Stored state:**
- `defaultBonds` — auto-detected list at current tolerance (or `bonds` array from JSON file).
- `currentBonds` — what is currently rendered. Starts equal to `defaultBonds`, editable by user.

### Arrow Construction (Quiver)

Each arrow = cylinder (shaft) + cone (head), assembled into a `THREE.Group` at atom position. Direction set via `lookAt(atom_pos + displacement_direction)`. Length = `MAX_ARROW_LEN × |displacement[i]| / max_displacement_in_mode`. Arrows with displacement below 1% of mode max are hidden. All arrows in `arrowGroup`.

### Scene Lighting

Ambient light + two directional lights (inherited from existing viewer). Camera: `PerspectiveCamera`, position Z = `max(10, maxRadius × 2.5)`.

---

## Display Modes

Controlled by a single `displayMode` state: `'animation'` | `'quiver'` | `'both'`.

| Mode | `moleculeGroup` | `arrowGroup` |
|---|---|---|
| Animation | atoms oscillate each frame | hidden |
| Quiver | atoms at equilibrium | static arrows at equilibrium |
| Both | atoms oscillate each frame | arrow origins follow atom positions |

**Animation formula:**
```
offset(t) = amplitude × sin(2π × t / T)
atom_pos(t) = equilibrium_pos + offset(t) × displacement
```
Period `T` = 2 seconds (fixed, visually comfortable). `amplitude` driven by the Amplitude slider.

**Interaction pause:** `isUserInteracting` flag (set on mousedown/touchstart, cleared on mouseup/touchend) pauses atom position updates. Arrow visibility and mode switching still work while paused.

**Mode switch behavior:**
1. Displacement vectors replaced with new mode data.
2. Arrow geometry rebuilt.
3. Animation time `t` reset to 0.
4. Amplitude slider value unchanged.

---

## UI Layout

Fixed left panel (~300px), full-height Three.js canvas on the right. Dark theme (matching existing viewer).

```
┌─────────────────────┬──────────────────────────────┐
│  Vibration Viewer   │                              │
│                     │                              │
│ [Upload / Drop]     │      3D Canvas               │
│─────────────────────│      (Three.js)              │
│ [Index▾] [Freq▾]    │                              │
│ ┌─────────────────┐ │                              │
│ │ #1  100.4 cm⁻¹  │ │                              │
│ │     m=8.11      │ │                              │
│ │ #2  114.9 cm⁻¹  │ │                              │
│ │ ...             │ │                              │
│ └─────────────────┘ │                              │
│─────────────────────│                              │
│ [Anim] [Quiver] [Both]                             │
│ Amplitude  [──●───] │                              │
│ Ball size  [──●───] │                              │
│ Stick size [──●───] │                              │
│ [ ] Sticks only     │                              │
│─────────────────────│                              │
│ [▸ Advanced]        │                              │
└─────────────────────┴──────────────────────────────┘
```

**Mode list rows:** index, frequency (cm⁻¹), reduced mass. Intensity column shown only if present in data. Selected row highlighted. Sorted by Index or Freq via toggle buttons above the list.

**Advanced panel (collapsed by default):**
```
┌─ Advanced ──────────────────────────┐
│ ─ Connectivity ─                    │
│ Tolerance  [──●───]  1.25×          │
│ Bond list (JSON):                   │
│ ┌─────────────────────────────────┐ │
│ │ [[0,1],[1,2],...]               │ │
│ └─────────────────────────────────┘ │
│ [Apply]         [Restore Default]   │
└─────────────────────────────────────┘
```

Tolerance slider regenerates default bonds and updates textarea in real time. Apply parses textarea JSON and re-renders. Restore Default resets to auto-detected bonds at current tolerance.

---

## File Structure

```
vib_viewer/
  xyz_viewer/
    xyz_molecule_viewer.html     # existing viewer (unchanged)
  vib_viewer/
    vibration_viewer.html        # new viewer
  example/
    H2O_CN_MBH.log               # example modified Gaussian log
  docs/
    superpowers/specs/
      2026-06-11-vibration-viewer-design.md
```

---

## Out of Scope (this version)

- Internal coordinate displacements (back-projection to Cartesian)
- Animation speed control
- Multiple simultaneous molecule views
- Export / screenshot functionality
