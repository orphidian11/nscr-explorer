import * as THREE from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js'
import { buildStation, buildRealStation, isRealStationManifest } from '../layers/station'
import type { StationManifest, StationModel } from '../layers/station'

let loaderInstance: GLTFLoader | null = null

/** Shared GLTFLoader configured with meshopt decoding for compressed CAD exports. */
export function getGltfLoader(): GLTFLoader {
  if (!loaderInstance) {
    loaderInstance = new GLTFLoader()
    loaderInstance.setMeshoptDecoder(MeshoptDecoder)
  }
  return loaderInstance
}

/** Load a GLTF/GLB model and return its scene with shadow flags enabled. */
export async function loadGltf(url: string): Promise<THREE.Group> {
  const gltf = await getGltfLoader().loadAsync(url)
  gltf.scene.traverse((object) => {
    const mesh = object as THREE.Mesh
    if (mesh.isMesh) {
      mesh.castShadow = true
      mesh.receiveShadow = true
    }
  })
  return gltf.scene
}

/**
 * Load a station from a JSON manifest URL and build its geometry.
 * Any `gltf` primitives referenced by the manifest are resolved here, so real
 * CAD-extracted models can be dropped in without code changes.
 */
export async function loadStation(manifestUrl: string): Promise<StationModel> {
  // no-store: dev regenerations must never be shadowed by a cached partial body
  const response = await fetch(manifestUrl, { cache: 'no-store' })
  if (!response.ok) {
    throw new Error(`Failed to load station manifest ${manifestUrl}: HTTP ${response.status}`)
  }

  const manifest = (await response.json()) as StationManifest | unknown
  if (!manifest || typeof manifest !== 'object') {
    throw new Error(`Invalid station manifest at ${manifestUrl}`)
  }

  // Two schemas are supported: the flat `layers` placeholder manifest and the
  // nested CAD-derived `objects` manifest (InstancedMesh builder).
  const model = isRealStationManifest(manifest)
    ? buildRealStation(manifest)
    : buildStation(manifest as StationManifest)

  await Promise.all(
    model.gltfRefs.map(async (ref) => {
      try {
        const scene = await loadGltf(ref.url)
        const slot = model.root.getObjectByName(ref.objectName)
        if (slot) {
          slot.add(scene)
        } else {
          console.warn(`[loaders] GLTF slot "${ref.objectName}" not found in built station`)
        }
      } catch (error) {
        console.warn(`[loaders] Failed to load GLTF reference "${ref.url}"`, error)
      }
    }),
  )

  return model
}
