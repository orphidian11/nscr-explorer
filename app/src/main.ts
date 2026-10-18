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

// OSM ground: re-anchored to each station's manifest origin (Bicutan and FTI sit
// ~2 km apart — a fixed anchor leaves the other station floating in the void).
let ground: ReturnType<typeof createGroundLayer> | null = null
let groundAnchor = ''
const FALLBACK_ANCHOR = { lat: 14.488419, lon: 121.045368 } // Bicutan (PROJ-transformed)

function setGroundAnchor(anchor: { lat: number; lon: number }): void {
  const key = `${anchor.lat.toFixed(6)},${anchor.lon.toFixed(6)}`
  if (key === groundAnchor) return
  groundAnchor = key
  if (ground) {
    viewer.scene.remove(ground.group)
    ground.dispose()
  }
  ground = createGroundLayer({ lat: anchor.lat, lon: anchor.lon, zoom: 17 })
  ground.group.position.y = 0.05 // above the scene's base ground plane to avoid z-fighting
  viewer.scene.add(ground.group)
  void ground.load().then(() => {
    if (groundAnchor !== key) return // stale load from a disposed ground
    panel.setStatus(`${stationLayers.size} layers + OSM ground (${groundAttribution})`)
  })
}

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
    setGroundAnchor(station.originWgs84 ?? FALLBACK_ANCHOR)
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
