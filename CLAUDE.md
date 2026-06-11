# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

No build step. Open `xyz_viewer/xyz_molecule_viewer.html` directly in a browser:

```sh
open xyz_viewer/xyz_molecule_viewer.html
```

## Architecture

The entire application is a single self-contained HTML file with inline JavaScript. There is no package manager, bundler, or test framework. Three.js is loaded from CDN (`r128`).

The JS is organized into five logical sections (marked with comment headers):

1. **ELEMENT_DATA map** — per-element color (`0xhex`) and covalent radius (Å) used for both sphere scaling and bond detection.

2. **Three.js init** — creates `scene`, `camera`, `renderer`, and `moleculeGroup` (a `THREE.Group` that holds all atom/bond meshes and is the rotation target).

3. **File parsing & bond logic** (`processXYZ`) — reads the XYZ format (line 0: atom count, line 1: comment, lines 2+: `ELEMENT x y z`), centers the molecule at the origin, then runs an O(N²) bond search using the rule: two atoms are bonded if their distance < 1.25 × (sum of their covalent radii), with a lower bound of 0.1 Å to skip self-pairs.

4. **3D rendering** (`renderMolecule`) — clears `moleculeGroup`, then adds `MeshStandard` spheres (shared `SphereGeometry`, per-element materials) for atoms and cylinders for bonds. Bond cylinders use a shared `CylinderGeometry` pre-rotated 90° on X so that `mesh.lookAt(v2)` correctly aligns the cylinder along the bond axis. Camera Z is set to `max(10, maxRadius * 2.5)`.

5. **Interaction & animation** — mouse/touch drag rotates `moleculeGroup` in X/Y; scroll moves `camera.position.z` (clamped 3–200). The animation loop auto-spins when the user is not interacting.

## Key Design Details

- **Bond cylinder trick**: `CylinderGeometry` defaults to Y-axis; it is pre-rotated `Math.PI/2` on X so its length axis becomes Z, making `lookAt` work without an intermediate quaternion rotation.
- **Atom visual size**: rendered at `elData.radius * 0.5` scale (ball-and-stick aesthetic, not space-filling).
- **Element fallback**: any unknown element symbol uses `ELEMENT_DATA['DEFAULT']` (pink, radius 0.8 Å).
- **Memory cleanup**: `renderMolecule` disposes `geometry` and `material` from every previous child before rebuilding.
