# NSCR 3D Line Explorer — SPEC.md

**Status:** v0.1 (living spec — updated each iteration)
**Data source:** `E:\NSCR\NSCR_drawings\` (see `NSCR_drawings/DOWNLOAD_INVENTORY.md`)
**Goal:** A browser-based 3D app to explore the North–South Commuter Railway as it will feel when operational — start small (one station), grow to the full line.

---

## 1. Product vision

Two users, one scene:

- **Passenger** — "What will my commute feel like?" Walk through stations, see platforms, entrances, fare gates, how the station connects to Skyway/C6/FTI, travel the line at eye level.
- **Railway operator** — "Can we run this?" Inspect track geometry, clearances, platform–train interface, signage/egress, depot and stabling, line-wide asset overview.

## 2. Non-negotiables

1. **Drawings are the source of truth.** Every 3D element traces to a DWG or JICA PDF; metadata records the source file + sheet.
2. **Web-based, high performance.** Three.js + WebGL, target 60 fps on a mid laptop. Techniques: instanced meshes for piers/girders, LOD, draco/meshopt compression, tile-based streaming for the full line, frustum culling.
3. **Real-world coordinates.** All geometry in true georeferenced coordinates (Philippine zone III / convert to a local ENU frame per tile) so map merge is native, not fudged.
4. **Iterative.** Every phase ships a usable viewer. No big-bang.

## 3. Architecture

```
E:\NSCR\
  NSCR_drawings\          # source CAD/PDF (read-only)
  pipeline\               # DWG -> DXF -> JSON geometry extractors
  data\                   # generated: geometry JSON/glTF, station manifests, alignment track
  app\                    # web app (Vite + Three.js + TypeScript)
    src/
      viewer/             # scene, camera, controls
      layers/             # rail, stations, terrain, osm-tiles
      ui/                 # station list, timeline, tour mode
  SPEC.md                 # this file
```

- **Map merge: OpenStreetMap via MapLibre GL or Cesium ion-free workflow.** Decision: start with **Three.js + raster OSM tiles on a ground plane** (simple, fast, no account needed); evaluate CesiumJS in Phase 3 if terrain/3D-tiles demand it. Google Maps 3D Tiles requires an API key + billing — offered as an option, not the default.
- **Data flow:** DWG → DXF (ODA File Converter) → ezdxf parse → typed JSON (alignment centerlines, viaduct sections, station GA outlines) → glTF/meshopt assets → app loads per-tile.

## 4. Phases

| Phase | Deliverable | Source |
|---|---|---|
| 0. Data prep | Bicutan arch zip extracted; DWGs converted to DXF; key sheets identified | S-03c BIC_AR zip |
| 1. Single station | Bicutan station: 3D massing from GA drawings + viaduct segment + track, orbit/walk camera | BIC_AR DWGs, DFR p501+ |
| 2. Context | OSM tile ground + nearby landmarks (SM Bicutan, Skyway, C6) approximated | OSM, DFR p485–486 |
| 3. Line segment | Bicutan ↔ FTI ↔ Sucat viaduct run from alignment + typical sections | VIA03c, ATG, alignment DWGs |
| 4. Full line | All stations, streaming tiles, line-wide flythrough | all downloaded sets + PhilGEPS fetch |
| 5. Experience | Passenger walk mode, operator overlay mode, train ride simulation | — |

## 5. Feature backlog

### Passenger
- First-person station walkthrough (entrance → concourse → platform)
- Timetable-aware train arrival animation + boarding simulation
- "How do I get here?" — entrance picker showing nearest landmarks/connections
- Accessibility view: elevators, ramps, tactile paths highlighted
- Crowding/comfort simulation at peak hours

### Operator
- Clearance & structure gauge visualization (live vs. rolling stock envelope)
- Asset layer: click any pier/girder → source drawing sheet reference
- Signage/egress audit mode (exit travel distances)
- Maintenance access overlay (depot leads, stabling)
- Construction-progress toggle: design model vs. as-built photos when available

### Recommended additions
- Day/night + weather lighting presets
- Screenshot/video tour export (shareable stakeholder previews)
- VR (WebXR) walkthrough toggle
- Line dashboard: station-by-station KPIs (dwell, headway) overlaid on 3D

## 6. Performance budget

- First tile load < 3 s on broadband; total line < 40 MB meshopt
- Draw calls < 500 per view (instancing for repeated elements)
- 60 fps on integrated GPU at 1080p

## 7. Subagent delegation plan

- **Geometry extraction** (strong reasoning model): parse DXF, derive 3D coordinates, resolve drawing ambiguity.
- **DWG conversion & file ops** (fast model): zips, ODA conversion, inventory scripts.
- **Web app build** (strong coding model): Three.js viewer, loaders, UI.
- **Research** (fast model): OSM/tile workflows, DWG tooling fallbacks.

## 8. Verified constants (research, 2026-10-18)

- **Bicutan NSCR:** 14.48748, 121.04571 (WGS84; OSM node 3729353499 agrees to ~60 m)
- **Sucat NSCR:** 14.45214, 121.05093; Bicutan↔Sucat ≈ 3.97 km
- **Ground plane (zero-account):** OSM raster `https://tile.openstreetmap.org/{z}/{x}/{y}.png`; z17–18 for station views (1.16/0.58 m/px), z14–15 for line views; Web-Mercator frame needs `cos(14.49°) ≈ 0.9682` scale correction. Key-free alternates: Wikimedia Maps, CARTO voyager.
- **Google Photorealistic 3D Tiles:** requires billing (Enterprise SKU, ~$6/1k root tileset requests; child tile fetches free). Only viable via CesiumJS + attribution — Phase 4 option, not default.
- **Drawing CRS:** PRS92 / PTM Zone III = **EPSG:3123** (CM 121°E, false easting 500,000). PRS92→WGS84 via NAMRIA 7-param Helmert: ΔX −127.62195, ΔY −67.24478, ΔZ −47.04305; Rx −3.06762″, Ry −4.90291″, Rz −1.57790″; scale 1.06002 ppm. Use PROJ `EPSG:3123→4326`, never hand-rolled (sign-convention traps).

## 9. Status log

- **Phase 0 ✅** — Bicutan AR zip extracted (152 files: full arch set + perspectives + georeferenced topo/alignment DWGs). ODA File Converter 27.9 portable at `pipeline/oda_bin/` (MSI needed admin extract workaround). 74/74 DWGs → DXF AC1032 at `pipeline/dxf/{stations,xrefs}/`, ezdxf-verified (`_verify_report.json`; 3 are title sheets with paper-space-only content).
- **Phase 1 (app shell) ✅** — `app/` Vite+TS+Three.js builds & serves; manifest-driven placeholder station (platform +8.3 m, concourse +4.0 m, stair cores, 6 tapered piers @30 m, double track @±6.75 m); dev server verified 200 on root + manifest.
- **Iteration 2 ✅** — Real CAD geometry live: 663 wall boxes at true PRS92 positions (`build_manifest.py` → `app/src/data/bicutan-real.json`), levels from Section dims (GF +0.50 / Concourse +4.60 / TOR +10.80 / Platform +11.90 / Roof +24.70). Instanced rendering. OSM ground layer live and georeferenced — station origin PRS92→WGS84 = 14.488419, 121.045368 (matches OSM node within ~60 m); verified via browser screenshots. vs architect's `BICUTAN.jpg`: layering/piers/tracks match; canopy/lattice/girder were gaps → Iteration 3.
- **Iteration 3 ✅** — Real structural + architectural detail: 108 column pads from the foundation plan (replacing regularized 8-m piers, instanced r=0.5 m cylinders to +15.85); barrel-vault canopy from the section's rigid-frame geometry (true circular arc, span 41.03 m, rise 6.23 m, R 36.925, apex +24.70, eaves +18.48, extruded 180 m along the ridge; profile sheet-frame→across-track conversion documented in build_manifest.py); facade lattice (324 instanced segments from 204 A-CLAD FRAMING polylines, +0→+15.9). Verified orbit + top screenshots: vault aligned over platform, coherent pier grid, lattice on edges, nothing misplaced. Remaining known assumptions: arch east/west symmetry; lattice drawn full-height (no per-polyline z); GL+8.30 framing plan was sheet-local (couldn't cross-check foundation vs framing).
- **Iteration 4 ✅** — Viaduct + track fixes from `viaduct.json` (X_DD_NSRP_Main_Alignment + section POST block): tracks now ±4.4 m (8.8 m spacing per section DIMS) AND re-oriented along the alignment tangent — they previously ran along local x, perpendicular to the real corridor; track length spans the station footprint along the alignment (−95.6…+93.7 m). Viaduct: 364 U-girder base slabs + 728 webs (simplified 3-box U per 10-m segment per track) along ±1000 m of alignment, trimmed to abut the station ends; 46 piers @40 m (CAD pier markers) outside the station box = 92 twin 0.5 m cylinders + cap beams. New layers `viaduct_deck` / `viaduct_piers`. Verified orbit + top screenshots. Note: `fitCameraTo` frames the full 2 km viaduct so the station renders small in Top.
- **Iteration 5 ✅** — Platform rebuilt from the real balustrade footprint: the old single 109×176 m bbox slab (the "large grey rectangle") replaced with two side platforms (~4 m wide at ±9.0 m offset from the centreline — platform edges at the 6.97 m U-girder dim; 188.8 m along the axis per the 181 m end-wall spacing), yellow tactile warning strips, inner-edge parapets, and real end walls (7.8×4.0 m). Per-object `color` now honoured in both box paths of station.ts. Verified: strips render, no giant rectangle, composition coherent.
- **Iteration 6 ✅** — Portal beams + walkable floors + walk mode: framing beams extracted from the GL +9.750 plan (525 beams: 32 portal @~10 m rhythm under the tracks, transverse + longitudinal; 1:1 scale from edge-pair separation; plans were georeferenced, not sheet-local); ground +0.50 and concourse +4.60 walkable floor slabs (wall-segment projection, 185×38 m); first-person walk mode (pointer-lock WASD, eye 1.6 m clamped to the floor you're over, smooth drop between levels). Verified: structural sandwich reads (deck → +9.75 beams → piers → concourse → ground), walk mode at eye 1.6 m with hint overlay.
- **Iteration 7 (v0.7.0, NOT deployed — pending user review) ✅** — Line extended to FTI: alignment re-sampled ±4 km (801 pts; 4 km xref gap north of Bicutan bridged straight — flagged), viaduct 4800 deck boxes + 192 piers, deck descends +10.45 → +0.45 m between stations; FTI station as JICA Type E′ at-grade massing (island platform, canopy on columns; all elements flagged — no S-03b arch DWGs, DFR design superseded by as-built underground CP NSCR-03-B). OSM ground re-anchors per station (manifest origin_wgs84); FTI manifest FTI-centred. FTI s = 2024.7 vs geodesic 2025. Independent code review passed; UI/UX review caught ground-anchoring + frame-rebasing bugs (fixed).
- **Iteration 8 (v0.8.0, NOT deployed) ✅** — Continuous corridor experience: dynamic OSM tile streaming around the camera (ground follows navigation); click-to-select (raycast pick → nearest station anchor → auto-select + load); "Line: Bicutan ↔ FTI" merged scene option. Also fixed the blank-Bicutan far-plane bug (see iteration 7.5 hotfix `1be23f3`). Verified: mid-corridor map continuous, click FTI platform in line mode auto-selects FTI.
- **Iteration 9 (v0.9.0, NOT deployed) ✅** — Fly mode (WASD follows view direction, Space/C vertical, Shift boost 60→120 m/s; Fly preset starts high over the station core looking along the corridor) + FTI at-grade track bed through the station box (base slab only, no webs) + FTI standalone manifest now includes its ±1.5 km approach viaduct with the descent ramp (1,819 deck boxes, 142 piers).
- **Iteration 10 (v1.0.0, NOT deployed) ✅** — 4-station corridor: Sucat from its real arch DXF set (1199 walls, georeferenced, OSM-anchored); Senate-DepEd (Type C′ elevated) + EDSA (Type E at-grade) massing; alignment_v3 (1526 pts @10 m, OSM-spliced, 0.6 m agreement with v2 in the overlap); line-corridor.json (5 stations, ~15 km); line view default. Independent code review passed. Subagent also fixed vault-array handling in station.ts. BUE canopy corrected from +24.7 to +16.5.
- **Iteration 11 (v1.1.0, NOT deployed — plan in `docs/plan-avatar-third-person.md`, approved) ✅** — Third-person avatar walk mode replaces the first-person Walk camera: procedural 1.75 m human (primitives only, hi-vis vest, casts shadow) with gait driven by ground speed (leg/arm sine swings 1.2–2.8 Hz, hip bob, run lean); mouse orbits a 4.5 m boom around it (wheel 2–8 m), WASD camera-relative (3.5 m/s walk, 7 m/s run), turn-to-face slerp. Ground model switched from hardcoded Bicutan floor constants to per-frame raycast-down against floors/platform/stairs layers + OSM tiles + base plane (≤0.4 m step-up climbs real stair geometry, lerped falls) — fixes Sucat (+16.60 platform) and all other manifests. Spawn below camera snapped to ground; corridor view falls back to the walkable mesh nearest the camera (bbox centre lands in inter-station gaps). Avatar persists after Esc as a scale reference; orbit re-targets it; removed on station switch. `walk.ts` → `fly.ts` (fly unchanged, measured exactly 60 m/s). Verified: fixed-dt mechanics (7.0 m/2 s walk, 7.0 m/1 s run, 3.5 m/1 s strafe), Sucat platform/concourse levels by raycast, third-person screenshots, `docs/avatar-walk-proof.gif`. TS pitfall re-encountered: setter-closure-mutated state needs a holder object (`ext`) or it narrows to `never` inside other closures.
- **Commuter review (CAD-extracted)** — 3 ground entrances: south entry (E 504783, N 1602292, east/FTI side, with drop-off + escalator), north entry (E 504731, N 1602430), mid-station STATION PLAZA exit (E 504765, N 1602368, east side, 3 doors + gate line); west/SLEX edge has no ground entry (elevated walkway NW at 504652, 1602597). Circulation: 3 stair cores GF→concourse, 1 escalator, 2 concourse→platform stair clusters, 4 elevator shafts serving all 3 levels. Fare gates (89) on the concourse.

## 10. Open questions

- FTI (S-03b) station arch drawings not in S03A/S03C — need own GBB hunt.
- Vertical station dimensions: confirm from arch DWGs once extracted (DFR gives plan widths).
- Georeferencing: DWGs may be in local site coordinates — anchor via Bicutan station lat/lon from siting maps (DFR p485–486).
