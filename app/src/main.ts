import './style.css'
import * as THREE from 'three'
import { createViewerScene } from './viewer/scene'
import type { CameraPresetName } from './viewer/scene'
import { loadStation } from './viewer/loaders'
import type { StationLayerHandle } from './layers/station'
import { createPanel, STATION_OPTIONS } from './ui/panel'
import { createGroundLayer, groundAttribution, localToLatLon } from './layers/ground'

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

// Camera-follow tile streaming: stream OSM tiles around the camera's XZ
// position. scene.ts's render loop is owned elsewhere, so hook the controls'
// 'change' event plus a 1 Hz fallback (walk mode moves the camera without a
// controls change). update() throttles internally to half-tile movement.
function updateGroundStreaming(): void {
  ground?.update(viewer.camera.position.x, viewer.camera.position.z)
}
viewer.controls.addEventListener('change', updateGroundStreaming)
// Timer handle intentionally not stored — streaming runs for the page lifetime.
setInterval(updateGroundStreaming, 1000)

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

// Click-to-select: clicking station geometry selects the nearest station in the
// dropdown (and loads it if it differs from what's loaded).
let loadedStationId = ''
const METRES_PER_DEG_LAT = 110540
viewer.setPickHandler((worldPoint) => {
  // The scene's local origin IS the loaded manifest's anchor; geolocate the
  // clicked point, then pick the nearest station anchor.
  const origin = STATION_OPTIONS.find((o) => o.id === loadedStationId)
  const anchor = origin?.lat != null && origin.lon != null
    ? { lat: origin.lat, lon: origin.lon }
    : FALLBACK_ANCHOR
  const hit = localToLatLon(worldPoint.x, worldPoint.z, anchor.lat, anchor.lon)
  let nearest: { id: string; d: number } | null = null
  for (const opt of STATION_OPTIONS) {
    if (opt.lat == null || opt.lon == null) continue
    const dx = (opt.lon - hit.lon) * Math.cos((hit.lat * Math.PI) / 180) * 111320
    const dz = -(opt.lat - hit.lat) * METRES_PER_DEG_LAT
    const d = Math.hypot(dx, dz)
    if (nearest == null || d < nearest.d) nearest = { id: opt.id, d }
  }
  if (nearest && nearest.id !== loadedStationId) {
    void loadAndShow(nearest.id)
  }
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
  loadedStationId = stationId
  panel.setStationValue(stationId)
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
    // Frame the camera on the station core, excluding the multi-km viaduct —
    // framing the full viaduct centres the camera kilometres from the station.
    const coreBounds = new THREE.Box3()
    for (const layer of station.layers) {
      if (layer.id.startsWith('viaduct')) continue
      coreBounds.expandByObject(layer.group)
    }
    const bounds = coreBounds.isEmpty()
      ? new THREE.Box3().setFromObject(station.root)
      : coreBounds
    viewer.fitCameraTo(bounds)
    panel.setStatus(`${station.layers.length} layers loaded from manifest`)
  } catch (error) {
    console.error('[main] Station load failed:', error)
    panel.setStatus(error instanceof Error ? error.message : String(error), 'error')
  }
}

void loadAndShow('bicutan-real')
