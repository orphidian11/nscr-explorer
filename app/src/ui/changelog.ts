// Release notes for NSCR EXPLORER. Latest first. Keep new versions at the TOP.
export interface Release {
  version: string
  date: string
  sections: Array<{ title: 'New features' | 'Fixes' | 'Other changes'; items: string[] }>
}

export const APP_VERSION = 'v1.0.0'

export const RELEASES: Release[] = [
  {
    version: 'v1.0.0',
    date: '2026-10-22',
    sections: [
      {
        title: 'New features',
        items: [
          'Three new stations: Sucat with REAL CAD geometry (walls from the A-WALL layers of the CP S-03c Sucat set, platform footprints from the A-PSD/HANDRAIL outlines, levels verified from X_Suc_Sta_Section: GF +1.00, concourse +7.85, rail +15.50, platform +16.60) — plus Senate-DepEd (BUE, elevated Type C′ massing) and EDSA (at-grade Type E massing) from the DXF station bboxes, all assumptions flagged in the manifests',
          'Corridor extended to ~15 km: new "Line: Sucat ↔ Bicutan ↔ EDSA (corridor)" default view covering all 5 stations with the full viaduct deck/piers over the whole alignment_v3 (1526 pts @10 m), elevated at Sucat/Bicutan/Senate-DepEd and at-grade at FTI/EDSA with linear ramps between',
        ],
      },
      {
        title: 'Other changes',
        items: [
          'Alignment source switched to alignment_v3.json; station positions are geometric nearest-approach projections onto the assembled alignment (alignment_v3\'s nominal station chainages ignore the OSM splice lengths and would misplace the deck by up to 5 km)',
        ],
      },
    ],
  },
  {
    version: 'v0.9.1',
    date: '2026-10-20',
    sections: [
      {
        title: 'Fixes',
        items: [
          'Corridor alignment: the viaduct no longer veers off the rail corridor — the 4 km drawing-data gap is now bridged with the real NSCR construction geometry from OpenStreetMap (plus a tangent-anchored curve at the splice), instead of a straight chord that drifted up to 355 m from the true alignment. A duplicate parallel corridor near the station was also eliminated',
          'Fly mode stopped at the station centre: OrbitControls clamped the camera to its target every frame — the leash is removed so you can fly the full Bicutan ↔ FTI corridor',
          'Blue haze when navigating away from a station: streamed map coverage widened to 1,200 m, the ground rim now fades into the sky via distance-adaptive fog, and the camera can never outrun the streamed area',
          'Top preset rendered uniform blue (fog saturated at its 2.9 km vantage) — fog now scales with camera distance',
          'Camera far plane now rescales with the framed extent; the camera frames the station core instead of the multi-km viaduct',
          'OrbitControls setPointerCapture NotFoundError on fast clicks suppressed',
          'Station manifests are written atomically and fetched with no-store, so a dev-time regeneration can no longer serve a partial file',
        ],
      },
      {
        title: 'Other changes',
        items: [
          'Line view (Bicutan ↔ FTI) is now the default on load',
          'Orbit zoom-out range raised to 5 km to cover the whole corridor',
        ],
      },
    ],
  },
  {
    version: 'v0.9.0',
    date: '2026-10-19',
    sections: [
      {
        title: 'New features',
        items: [
          'Fly mode: free WASD flight following the view direction, Space/C for up/down, Shift to boost (60 m/s base) — navigate the corridor without fighting scroll-zoom',
          'FTI at-grade track bed: the U-girder now continues through the FTI box as an at-grade ballast-style bed, and the standalone FTI view includes its full approach viaduct (±1.5 km, with the descent ramp)',
        ],
      },
    ],
  },
  {
    version: 'v0.8.0',
    date: '2026-10-19',
    sections: [
      {
        title: 'New features',
        items: [
          'Continuous map coverage: OSM tiles now stream dynamically around the camera, so the ground follows you along the whole line (no more void between stations)',
          'Click-to-select: clicking any station or viaduct element in the 3D scene auto-selects the nearest station in the dropdown and loads it',
          'New "Line: Bicutan ↔ FTI" option — both stations and the full viaduct in one scene for continuous travel',
        ],
      },
      {
        title: 'Fixes',
        items: [
          'Bicutan viewport rendered blank after the viaduct extension: the camera far plane now rescales with the framed extent, and the camera frames the station core instead of the full multi-km viaduct',
        ],
      },
    ],
  },
  {
    version: 'v0.7.0',
    date: '2026-10-19',
    sections: [
      {
        title: 'New features',
        items: [
          'Line extended to FTI station (S-03b): the elevated viaduct now descends along the real alignment from Bicutan to FTI (~2 km), rendered as an at-grade approach',
          'FTI station massing from the JICA DFR Type E\' design: island platform, tracks, ground slab, stair cores, flat canopy — added to the station picker as "FTI (JICA massing)"',
          'Alignment re-sampled to ±4 km from the main-alignment DWG (801 points)',
        ],
      },
      {
        title: 'Other changes',
        items: [
          'FTI geometry is JICA-typology massing, NOT from arch DWGs (S-03b drawing set is not public) — every element flagged in the manifest. The DFR at-grade design is also superseded by the as-built underground station (CP NSCR-03-B)',
          'The alignment DWG has a 4 km xref gap covering the Bicutan–FTI stretch; samples there are a straight-line bridge (the corridor is near-straight), flagged in the manifest',
        ],
      },
    ],
  },
  {
    version: 'v0.6.0',
    date: '2026-10-18',
    sections: [
      {
        title: 'New features',
        items: [
          'First-person Walk mode: click the canvas, WASD + mouse look, Shift to run, Esc to exit. Eye height clamps to the floor you stand on (ground, concourse or platform) with a smooth drop between levels',
          'Walkable floor slabs at ground (+0.50 m) and concourse (+4.60 m) levels, extracted from the station wall geometry',
          'Framing beams at the +9.75 m level (525 members: 32 portal beams under the tracks at ~10 m rhythm, transverse and longitudinal) from the GL +9.750 framing plan',
          'New toggleable layers: Framing beams, Floors (walkable)',
        ],
      },
      {
        title: 'Other changes',
        items: [
          'Commuter analysis from CAD: 3 ground entrances (south, north, mid-station plaza — all FTI side), 12 vertical-circulation items, 89 concourse fare gates recorded in commuter.json',
        ],
      },
    ],
  },
  {
    version: 'v0.5.0',
    date: '2026-10-18',
    sections: [
      {
        title: 'New features',
        items: [
          'Real platform rebuilt from the A-BALUSTRADE footprint: two side platforms (~4 m wide at ±9.0 m from the centreline, 188.8 m long)',
          'Yellow tactile warning strips along the track-side platform edges, inner-edge parapets, and real 7.8×4.0 m end walls',
          'Per-object colours in the manifest (used by the tactile strips)',
        ],
      },
      {
        title: 'Fixes',
        items: [
          'The platform previously rendered as one giant grey slab spanning the whole plan bbox',
        ],
      },
    ],
  },
  {
    version: 'v0.4.0',
    date: '2026-10-18',
    sections: [
      {
        title: 'New features',
        items: [
          'Elevated viaduct on both sides of the station: simplified 3-box U-girder per track per 10 m segment along ±1 km of the real alignment (1,138 boxes)',
          'Viaduct piers: twin columns + cap beams at the CAD-true 40 m spacing (46 piers), skipped through the station box',
          'New layers: Viaduct deck, Viaduct piers',
        ],
      },
      {
        title: 'Fixes',
        items: [
          'Track spacing corrected from ±6.75 m to ±4.4 m (8.8 m, per the section drawing dimensions)',
          'Tracks re-oriented parallel to the NSCR alignment — they previously ran perpendicular to the real corridor',
        ],
      },
    ],
  },
  {
    version: 'v0.3.0',
    date: '2026-10-18',
    sections: [
      {
        title: 'New features',
        items: [
          'Real structural columns: 108 positions from the foundation plan (replacing regularized placeholders)',
          'Barrel-vault canopy: true circular arc (span 41.03 m, rise 6.23 m, apex +24.70 m) extruded 180 m along the ridge, from the section rigid-frame geometry',
          'Facade lattice: 324 members from 204 A-CLAD FRAMING polylines',
          'New layers: Piers (real), Canopy (vault), Facade lattice',
        ],
      },
    ],
  },
  {
    version: 'v0.2.0',
    date: '2026-10-18',
    sections: [
      {
        title: 'New features',
        items: [
          'Real CAD geometry: 663 wall segments at true PRS92 Zone III coordinates from the Bicutan architectural set',
          'OpenStreetMap ground layer, georeferenced to the station (station origin matches the OSM node within ~60 m)',
          'Station picker: real CAD model vs placeholder',
        ],
      },
      {
        title: 'Fixes',
        items: [
          'Vertical levels corrected to the section-drawing values (Ground +0.50, Concourse +4.60, Top of Rail +10.80, Platform +11.90, Roof +24.70)',
          'OSM tile layout: fixed a Web-Mercator tile-x error that placed all tiles ~19,400 km east of the station',
          'Tile layer lifted above the base ground plane to stop z-fighting',
        ],
      },
    ],
  },
  {
    version: 'v0.1.0',
    date: '2026-10-18',
    sections: [
      {
        title: 'New features',
        items: [
          'Initial release: Vite + TypeScript + Three.js viewer',
          'Manifest-driven station geometry (box / cylinder primitives, instanced rendering)',
          'Orbit / Walk / Top camera presets and per-layer visibility toggles',
          'Placeholder Bicutan station (platform, concourse, piers, tracks)',
        ],
      },
    ],
  },
]
