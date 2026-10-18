# NSCR EXPLORER

A browser-based 3D exploration app for the **North–South Commuter Railway (NSCR)** in Metro Manila, Philippines — built to visualize what the line will feel like once operational, starting with **Bicutan station (CP S-03c)** and the elevated viaduct toward **FTI (S-03b)**.

**Live: [https://nscr-explorer.web.app](https://nscr-explorer.web.app)**

![version](https://img.shields.io/badge/version-v0.6.0-blue)

---

## What it does

- **Real CAD geometry** — every element traces to a source drawing. Station walls, columns, the barrel-vault canopy, facade lattice, framing beams, and platform details are extracted from the DOTr/GCR CP S-03c architectural and structural DWG sets (converted DWG → DXF → JSON).
- **True georeferencing** — drawings are PRS92 PTM Zone III (EPSG:3123); the viewer anchors them to WGS84 via the NAMRIA 7-parameter Helmert (validated against an independent OSM station node to within ~60 m).
- **OpenStreetMap ground** — raster tiles rendered under the local ENU scene, so the station sits on the real Bicutan road network and the SLEX/PNR corridor.
- **Elevated viaduct** — U-girder deck and twin-column piers at the CAD-true 40 m spacing, following the extracted alignment centerline, running ±1 km on both sides of the station.
- **First-person Walk mode** — click the canvas, WASD + mouse; eye height clamps to the floor you're standing on (ground +0.50 m, concourse +4.60 m, platform +11.90 m).
- **Versioned releases** — the header badge opens full release notes (v0.1.0 → current).

Open the app and click **Walk** to enter the station; **Orbit/Top** for overview.

## Architecture

```
E:\NSCR\
  NSCR_drawings\        # source DWG/PDF (9+ GB, gitignored — see its DOWNLOAD_INVENTORY.md)
  pipeline\             # DWG -> DXF -> JSON geometry extraction (Python, ezdxf + pyproj)
    build_manifest.py   #   regenerates app/src/data/*.json from the extracted JSON
    *.json              #   extracted: walls, columns, canopy, viaduct, commuter, framing
  app\                  # Vite + TypeScript + Three.js viewer (deployed to Firebase Hosting)
    src/viewer/         #   scene, camera presets, first-person walk controller
    src/layers/         #   instanced station builder, OSM tile ground layer
    src/ui/             #   panel, release notes
    src/data/           #   generated station manifests (do not hand-edit)
  SPEC.md               # living spec: phases, verified constants, per-iteration status log
  docs\                 # deployment research
```

The viewer renders a **manifest-driven** scene: `build_manifest.py` emits typed primitives (`box` / `cylinder` / `vault` with a `meta.source` per element), so regenerating or adding geometry never touches viewer code. All repeated elements render via `InstancedMesh` — ~3,000 objects in a handful of draw calls.

## Data pipeline

1. **DWG → DXF** — ODA File Converter 27.9 (portable, `pipeline/oda_bin/`), ASCII DXF, AutoCAD 2018, audit on
2. **Parse & extract** — `ezdxf`, layer-semantic filtering (A-WALL, A-BALUSTRADE, PILE CAPS, S-BEAM-ELE, …), endpoint dedupe, bbox filtering
3. **Georeference** — `pyproj` EPSG:3123 → EPSG:4326 (never hand-rolled Helmert — sign-convention traps cost ~160 m)
4. **Validate** — transformed anchors cross-checked against independent OSM nodes; levels taken from the section sheet's own dimension texts
5. **Render** — manifest JSON → instanced Three.js scene over OSM raster tiles (Web-Mercator math with a cos(lat) scale correction)

## Development

```bash
cd app
npm install
npm run dev -- --port 5173   # dev server
npm run build                # tsc --noEmit && vite build
firebase deploy --only hosting --project nscr-explorer
```

Regenerate station geometry from the extracted CAD JSON:

```bash
python pipeline/build_manifest.py
```

## Data sources & attribution

- **Engineering drawings:** DOTr/GCR CAD release (General Bid Bulletin No. 6, CP S-03a/S-03c) and JICA South Line Feasibility Study Draft Final Report — used here for research/visualization.
- **Map imagery:** © OpenStreetMap contributors (tiles: openstreetmap.org) — displayed with attribution in-app.
- FTI (S-03b) station geometry is **JICA-typology massing** (its own architectural drawing set is not public); every placeholder element is flagged in its manifest `meta`.

## Status & roadmap

See [`SPEC.md`](SPEC.md) for the full phased plan and per-iteration log. Done: single-station CAD detail (v0.1–0.6), viaduct runs, walk mode, Firebase Hosting. Next: FTI station integration (v0.7), line segment to Sucat, entrance/circulation visualization, passenger-tour experience.

---

*Research/visualization project — not affiliated with DOTr, PNR, or JICA.*
