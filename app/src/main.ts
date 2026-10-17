import './style.css'
import * as THREE from 'three'
import { createViewerScene } from './viewer/scene'
import type { CameraPresetName } from './viewer/scene'
import { loadStation } from './viewer/loaders'
import type { StationLayerHandle } from './layers/station'
import { createPanel } from './ui/panel'
import { createGroundLayer, groundAttribution } from './layers/ground'

const container = document.querySelector<HTMLElement>('#app')
if (!container) {
  throw new Error('#app container not found in index.html')
}

const viewer = createViewerScene(container)
;(window as unknown as { __viewer?: unknown }).__viewer = viewer
const stationLayers = new Map<string, StationLayerHandle>()
let currentRoot: THREE.Group | null = null

// Station anchor: Bicutan wall-bbox centre transformed PRS92 (EPSG:3123) -> WGS84 via PROJ.
// Cross-checks with the OSM station node (14.48804, 121.04544) to within ~60 m.
const STATION_ANCHOR = { lat: 14.488419, lon: 121.045368 }
const ground = createGroundLayer({ lat: STATION_ANCHOR.lat, lon: STATION_ANCHOR.lon, zoom: 17 })
ground.group.position.y = 0.05 // above the scene's base ground plane to avoid z-fighting
viewer.scene.add(ground.group)
void ground.load().then(() => {
  ;(window as unknown as { __ground?: unknown }).__ground = ground
  panel.setStatus(`${stationLayers.size} layers + OSM ground (${groundAttribution})`)
})

const panel = createPanel(container, {
  onLayerToggle: (id, visible) => {
    if (id === 'grid') {
      viewer.setGridVisible(visible)
      return
    }
    stationLayers.get(id)?.setVisible(visible)
  },
  onCameraPreset: (preset: CameraPresetName) => {
    viewer.applyPreset(preset)
  },
  onStationChange: (stationId) => {
    void loadAndShow(stationId)
  },
})
panel.setStatus('Loading station manifest…')

function manifestUrlFor(stationId: string): string {
  return new URL(`./data/${stationId}.json`, import.meta.url).href
}

/** Remove the current station's meshes and free GPU resources. */
function disposeCurrentStation(): void {
  if (!currentRoot) return
  viewer.scene.remove(currentRoot)
  currentRoot.traverse((object) => {
    const mesh = object as THREE.Mesh
    if (mesh.isMesh) {
      mesh.geometry?.dispose()
      const material = mesh.material
      if (Array.isArray(material)) material.forEach((m) => m.dispose())
      else material?.dispose()
    }
  })
  currentRoot = null
  stationLayers.clear()
}

async function loadAndShow(stationId: string): Promise<void> {
  panel.setStatus('Loading station manifest…')
  disposeCurrentStation()
  try {
    const station = await loadStation(manifestUrlFor(stationId))
    viewer.scene.add(station.root)
    currentRoot = station.root
    for (const layer of station.layers) {
      stationLayers.set(layer.id, layer)
    }
    panel.setStation(station.name, [
      ...station.layers.map((layer) => ({ id: layer.id, label: layer.label, visible: layer.visible() })),
      { id: 'grid', label: 'Ground grid', visible: true },
    ])
    // Frame the camera on the real footprint of whichever manifest loaded.
    const bounds = new THREE.Box3().setFromObject(station.root)
    viewer.fitCameraTo(bounds)
    panel.setStatus(`${station.layers.length} layers loaded from manifest`)
  } catch (error) {
    console.error('[main] Station load failed:', error)
    panel.setStatus(error instanceof Error ? error.message : String(error), 'error')
  }
}

void loadAndShow('bicutan-real')
