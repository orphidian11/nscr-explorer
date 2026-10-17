# NSCR 3D Station Viewer

Vite + TypeScript + Three.js web app for viewing NSCR station geometry in 3D.
Currently renders a placeholder massing for **Bicutan Station**, driven entirely
by a data manifest.

## Commands

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # type-check (tsc --noEmit) + vite build -> dist/
npm run preview
```

## Structure

```
index.html
src/
  main.ts                 # wires scene + station + panel
  style.css
  vite-env.d.ts
  viewer/scene.ts         # renderer, camera, OrbitControls, lights, 200x200 m ground + 10 m grid, camera presets
  viewer/loaders.ts       # GLTFLoader (meshopt-enabled) + loadStation(manifestUrl)
  layers/station.ts       # generic manifest -> Three.js geometry builder
  ui/panel.ts             # left panel: station name, layer toggles, camera presets
  data/bicutan-placeholder.json
```

## Station manifest format

The manifest lists layers; each layer holds primitives. Positions are primitive
centers in meters, +Y up, track axis along Z.

```jsonc
{
  "id": "...", "name": "Bicutan Station",
  "layers": [
    {
      "id": "platform", "label": "Platform", "visible": true,
      "primitives": [
        { "kind": "box", "name": "...", "size": [10, 0.5, 120], "position": [0, 8.05, 0], "color": "#ccd1d9" },
        { "kind": "cylinder", "height": 7.8, "radiusTop": 1, "radiusBottom": 1.25, "position": [0, 3.9, 15] },
        { "kind": "gltf", "url": "/models/station.glb", "position": [0, 0, 0], "rotationDeg": [0, 90, 0] }
      ]
    }
  ]
}
```

`gltf` primitives reference external GLTF/GLB models (meshopt compression is
supported out of the box) — real CAD-extracted geometry can replace the
placeholder by editing only the manifest.
