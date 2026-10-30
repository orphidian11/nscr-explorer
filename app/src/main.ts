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

/** Fog + camera limits derived from the streamed-ground radius, so the visible
 * horizon always ends inside the streamed area (no blue void beyond it). */
function applyHorizonLimits(): void {
  if (!ground) return
  const r = ground.radiusMeters
  // Room to fly the corridor: the streamed ground follows the camera, so the
  // camera range just needs to cover the station-to-station stretch (~2.5 km).
  viewer.controls.maxDistance = 5000
  // Fog is distance-adaptive (see updateGroundStreaming); keep the far plane
  // generous for the multi-km presets.
  viewer.camera.far = Math.max(viewer.camera.far, r * 5)
  viewer.camera.updateProjectionMatrix()
}

function setGroundAnchor(anchor: { lat: number; lon: number }): void {
  const key = `${anchor.lat.toFixed(6)},${anchor.lon.toFixed(6)}`
  if (key === groundAnchor) return
  groundAnchor = key
  if (ground) {
    viewer.avatar.setTileGroup(null) // tiles are being disposed
    viewer.scene.remove(ground.group)
    ground.dispose()
  }
  ground = createGroundLayer({ lat: anchor.lat, lon: anchor.lon, zoom: 17 })
  ground.group.position.y = 0.05 // above the scene's base ground plane to avoid z-fighting
  viewer.scene.add(ground.group)
  viewer.avatar.setTileGroup(ground.group) // OSM tiles are walkable ground
  // Keep the horizon honest: fog fades the streamed ground's rim into the sky
  // and the camera can never pull back past the streamed area, so dragging or
  // flying toward the next station always has ground under it.
  applyHorizonLimits()
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
  // Adaptive fog: distance-based so it never saturates at high-altitude presets
  // (Top sits 2.9 km up) while still hiding the streamed-ground rim up close.
  if (ground && viewer.scene.fog instanceof THREE.Fog) {
    const d = viewer.camera.position.distanceTo(viewer.controls.target)
    viewer.scene.fog.near = Math.max(ground.radiusMeters * 0.6, d * 0.8)
    viewer.scene.fog.far = viewer.scene.fog.near + ground.radiusMeters * 1.8
  }
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
  // The avatar lives in the station's local frame — drop it (and its
  // walkable-ground references) with the rest of the scene.
  viewer.avatar.onStationUnload()
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
    // Hand the avatar the station's walkable layers (floors/platform/stairs);
    // the base plane + OSM tiles were registered once at scene creation.
    viewer.avatar.setStationGroups(
      ['floors', 'platform', 'stairs']
        .map((id) => stationLayers.get(id)?.group)
        .filter((group): group is THREE.Group => group != null),
    )
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
    applyHorizonLimits()  // fitCameraTo sets dist-based fog; clamp back to the streamed radius
    // Avatar spawn fallback (D4): if the camera is far outside the station
    // (corridor view), spawn on the walkable mesh nearest the camera — that
    // point is walkable by construction, unlike the corridor's bbox centre,
    // which lands in the inter-station gap.
    let nearest: { x: number; z: number } | null = null
    let nearestD = Infinity
    const meshBox = new THREE.Box3()
    const meshCentre = new THREE.Vector3()
    for (const id of ['floors', 'platform', 'stairs']) {
      const group = stationLayers.get(id)?.group
      if (!group) continue
      group.traverse((object) => {
        const mesh = object as THREE.Mesh
        if (!mesh.isMesh) return
        meshBox.setFromObject(mesh)
        meshBox.getCenter(meshCentre)
        const d = Math.hypot(meshCentre.x - viewer.camera.position.x, meshCentre.z - viewer.camera.position.z)
        if (d < nearestD) {
          nearestD = d
          nearest = { x: meshCentre.x, z: meshCentre.z }
        }
      })
    }
    viewer.avatar.setSpawnFallback(nearest)
    panel.setStatus(`${station.layers.length} layers loaded from manifest`)
  } catch (error) {
    console.error('[main] Station load failed:', error)
    panel.setStatus(error instanceof Error ? error.message : String(error), 'error')
  }
}

void loadAndShow('line-corridor')
