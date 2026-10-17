import * as THREE from 'three'

/**
 * Manifest-driven station geometry.
 *
 * The manifest describes each station as a list of layers, each holding a list
 * of primitives (box / cylinder / gltf reference). Positions are primitive
 * centers in meters, +Y up. This is deliberately generic: real CAD-extracted
 * geometry can later replace the placeholder by swapping the manifest data
 * (more primitives, or `gltf` references to converted meshes) with no code
 * changes.
 */

export interface ManifestPrimitiveBase {
  name?: string
  color?: string
  opacity?: number
  /** Primitive center [x, y, z] in meters. Defaults to origin. */
  position?: [number, number, number]
  /** Rotation in degrees around X/Y/Z, applied XYZ order. */
  rotationDeg?: [number, number, number]
}

export interface BoxPrimitive extends ManifestPrimitiveBase {
  kind: 'box'
  /** [width(x), height(y), depth(z)] in meters. */
  size: [number, number, number]
}

export interface CylinderPrimitive extends ManifestPrimitiveBase {
  kind: 'cylinder'
  height: number
  radiusTop?: number
  radiusBottom?: number
  radialSegments?: number
}

export interface GltfPrimitive extends ManifestPrimitiveBase {
  kind: 'gltf'
  /** URL of a GLTF/GLB model (e.g. meshopt-compressed CAD export). */
  url: string
}

export type ManifestPrimitive = BoxPrimitive | CylinderPrimitive | GltfPrimitive

export interface ManifestLayer {
  id: string
  label?: string
  visible?: boolean
  primitives: ManifestPrimitive[]
}

export interface StationManifest {
  id?: string
  name: string
  description?: string
  units?: string
  layers: ManifestLayer[]
}

export interface GltfRef {
  layerId: string
  objectName: string
  url: string
}

export interface StationLayerHandle {
  id: string
  label: string
  group: THREE.Group
  setVisible: (visible: boolean) => void
  visible: () => boolean
}

export interface StationModel {
  name: string
  root: THREE.Group
  layers: StationLayerHandle[]
  /** GLTF placeholder slots waiting to be filled by loaders.ts. */
  gltfRefs: GltfRef[]
}

const DEFAULT_COLOR = '#b9bfc7'

function applyTransform(object: THREE.Object3D, primitive: ManifestPrimitive, index: number): void {
  const [x = 0, y = 0, z = 0] = primitive.position ?? []
  object.position.set(x, y, z)
  if (primitive.rotationDeg) {
    const [rx = 0, ry = 0, rz = 0] = primitive.rotationDeg
    object.rotation.set(
      THREE.MathUtils.degToRad(rx),
      THREE.MathUtils.degToRad(ry),
      THREE.MathUtils.degToRad(rz),
    )
  }
  object.name = primitive.name ?? `${primitive.kind}-${index}`
}

function createMaterial(primitive: ManifestPrimitive): THREE.MeshStandardMaterial {
  const material = new THREE.MeshStandardMaterial({
    color: new THREE.Color(primitive.color ?? DEFAULT_COLOR),
    roughness: 0.85,
    metalness: 0.08,
  })
  if (primitive.opacity !== undefined && primitive.opacity < 1) {
    material.transparent = true
    material.opacity = primitive.opacity
  }
  return material
}

function createPrimitiveObject(
  primitive: ManifestPrimitive,
  index: number,
  gltfRefs: GltfRef[],
  layerId: string,
): THREE.Object3D | null {
  switch (primitive.kind) {
    case 'box': {
      const mesh = new THREE.Mesh(
        new THREE.BoxGeometry(primitive.size[0], primitive.size[1], primitive.size[2]),
        createMaterial(primitive),
      )
      mesh.castShadow = true
      mesh.receiveShadow = true
      applyTransform(mesh, primitive, index)
      return mesh
    }
    case 'cylinder': {
      const mesh = new THREE.Mesh(
        new THREE.CylinderGeometry(
          primitive.radiusTop ?? 1,
          primitive.radiusBottom ?? 1,
          primitive.height,
          primitive.radialSegments ?? 24,
        ),
        createMaterial(primitive),
      )
      mesh.castShadow = true
      mesh.receiveShadow = true
      applyTransform(mesh, primitive, index)
      return mesh
    }
    case 'gltf': {
      // Empty transform slot; loaders.ts fills it with the loaded GLTF scene
      // so the manifest position/rotation also applies to external models.
      const slot = new THREE.Group()
      applyTransform(slot, primitive, index)
      const objectName = `gltf-ref-${layerId}-${index}`
      slot.name = objectName
      gltfRefs.push({ layerId, objectName, url: primitive.url })
      return slot
    }
    default: {
      console.warn(`[station] Skipping unsupported primitive kind: ${(primitive as { kind: string }).kind}`)
      return null
    }
  }
}

export function buildStation(manifest: StationManifest): StationModel {
  const root = new THREE.Group()
  root.name = `station-${manifest.id ?? 'unnamed'}`

  const layers: StationLayerHandle[] = []
  const gltfRefs: GltfRef[] = []

  for (const layer of manifest.layers ?? []) {
    const group = new THREE.Group()
    group.name = `layer-${layer.id}`
    group.visible = layer.visible ?? true

    ;(layer.primitives ?? []).forEach((primitive, index) => {
      const object = createPrimitiveObject(primitive, index, gltfRefs, layer.id)
      if (object) group.add(object)
    })

    layers.push({
      id: layer.id,
      label: layer.label ?? layer.id,
      group,
      setVisible: (visible) => {
        group.visible = visible
      },
      visible: () => group.visible,
    })
    root.add(group)
  }

  return { name: manifest.name, root, layers, gltfRefs }
}

/**
 * Real CAD-derived manifest schema (bicutan-real.json): a nested `objects`
 * object with bulk arrays of same-kind primitives instead of `layers`.
 * Rendered with InstancedMesh (one draw call per kind) so ~700 CAD segments
 * stay cheap on the GPU.
 */

export interface RealBoxObject {
  kind: 'box'
  size: [number, number, number]
  pos: [number, number, number]
  rotY?: number
  meta?: Record<string, unknown>
}

export interface RealCylinderObject {
  kind: 'cylinder'
  radius: number
  height: number
  pos: [number, number, number]
  rotY?: number
  meta?: Record<string, unknown>
}

export interface RealVaultObject {
  kind: 'vault'
  /** Across-track arch profile: [offset from centreline (m), elevation (m)], eave→apex→eave. */
  profile: [number, number][]
  axisStart: [number, number]
  axisEnd: [number, number]
  meta?: Record<string, unknown>
}

export interface RealStationManifest {
  name: string
  crs?: string
  origin_easting?: number
  origin_northing?: number
  origin_wgs84?: { lat: number; lon: number; note?: string }
  levels_m?: Record<string, number>
  sources?: string[]
  objects: {
    walls?: RealBoxObject[]
    platform?: RealBoxObject
    tracks?: RealBoxObject | RealBoxObject[]
    piers?: RealCylinderObject[]
    stairs?: RealBoxObject | RealBoxObject[]
    vault?: RealVaultObject
    lattice?: RealBoxObject[]
    /** Viaduct U-girder boxes + pier cap beams, along the NSCR main alignment. */
    viaduct_deck?: RealBoxObject[]
    /** Viaduct twin columns (0.5 m cylinders), ground -> +10.0. */
    viaduct_piers?: RealCylinderObject[]
  }
}

export function isRealStationManifest(manifest: unknown): manifest is RealStationManifest {
  return (
    typeof manifest === 'object' &&
    manifest !== null &&
    'objects' in manifest &&
    !('layers' in manifest)
  )
}

const CONCRETE_BASE = new THREE.Color('#9aa1a9')
const PLATFORM_COLOR = new THREE.Color('#c3c8cd')
const TRACK_COLOR = new THREE.Color('#3c4046')
const STAIR_COLOR = new THREE.Color('#aab0b6')
const PIER_COLOR = new THREE.Color('#8f959c')
const LATTICE_COLOR = new THREE.Color('#e2e5e8')
const VAULT_COLOR = new THREE.Color('#d4d8dc')
const VIADUCT_DECK_COLOR = new THREE.Color('#6f7680') // steel grey

/** Subtle per-instance lightness variation so instanced walls don't look flat. */
function varyColor(index: number, base: THREE.Color): THREE.Color {
  const hsl = { h: 0, s: 0, l: 0 }
  base.getHSL(hsl)
  const jitter = (((index * 2654435761) % 1000) / 1000 - 0.5) * 0.07 // ±3.5% lightness
  return new THREE.Color().setHSL(hsl.h, hsl.s, THREE.MathUtils.clamp(hsl.l + jitter, 0, 1))
}

function boxMatrix(obj: RealBoxObject, target: THREE.Matrix4): THREE.Matrix4 {
  const [sx, sy, sz] = obj.size
  const [x, y, z] = obj.pos
  const rot = obj.rotY ?? 0
  target.compose(
    new THREE.Vector3(x, y, z),
    new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), rot),
    new THREE.Vector3(sx, sy, sz),
  )
  return target
}

function makeInstancedBoxes(
  objects: RealBoxObject[],
  baseColor: THREE.Color,
): THREE.InstancedMesh {
  const geometry = new THREE.BoxGeometry(1, 1, 1)
  const material = new THREE.MeshStandardMaterial({ roughness: 0.85, metalness: 0.08 })
  const mesh = new THREE.InstancedMesh(geometry, material, objects.length)
  const matrix = new THREE.Matrix4()
  objects.forEach((obj, index) => {
    mesh.setMatrixAt(index, boxMatrix(obj, matrix))
    mesh.setColorAt(index, varyColor(index, baseColor))
  })
  mesh.instanceMatrix.needsUpdate = true
  if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
  mesh.castShadow = true
  mesh.receiveShadow = true
  mesh.name = `instanced-boxes-${objects.length}`
  return mesh
}

function makeInstancedCylinders(objects: RealCylinderObject[]): THREE.InstancedMesh {
  const geometry = new THREE.CylinderGeometry(1, 1, 1, 20)
  const material = new THREE.MeshStandardMaterial({ roughness: 0.85, metalness: 0.1 })
  const mesh = new THREE.InstancedMesh(geometry, material, objects.length)
  const matrix = new THREE.Matrix4()
  objects.forEach((obj, index) => {
    matrix.compose(
      new THREE.Vector3(obj.pos[0], obj.pos[1], obj.pos[2]),
      new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), obj.rotY ?? 0),
      new THREE.Vector3(obj.radius, obj.height, obj.radius),
    )
    mesh.setMatrixAt(index, matrix)
    mesh.setColorAt(index, varyColor(index, PIER_COLOR))
  })
  mesh.instanceMatrix.needsUpdate = true
  if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
  mesh.castShadow = true
  mesh.receiveShadow = true
  mesh.name = `instanced-piers-${objects.length}`
  return mesh
}

/**
 * Barrel-vault roof: extrude the across-track arch profile along the station
 * axis as a thin-shell strip (two-sided, semi-translucent).
 */
function makeVaultMesh(obj: RealVaultObject): THREE.Mesh {
  const profile = obj.profile
  const [ax1, az1] = obj.axisStart
  const [ax2, az2] = obj.axisEnd
  const axisDx = ax2 - ax1
  const axisDz = az2 - az1
  const axisLen = Math.hypot(axisDx, axisDz)
  const axisSteps = Math.max(2, Math.min(48, Math.round(axisLen / 4)))
  const axisUx = axisDx / axisLen
  const axisUz = axisDz / axisLen
  // Across-track unit vector perpendicular to the axis in XZ.
  let acrossX = -axisUz
  let acrossZ = axisUx
  if (acrossX < 0) { acrossX = -acrossX; acrossZ = -acrossZ }

  const rows = profile.length
  const cols = axisSteps + 1
  const positions = new Float32Array(rows * cols * 3)
  const indices: number[] = []
  for (let i = 0; i < rows; i++) {
    const [offset, elev] = profile[i]
    for (let j = 0; j < cols; j++) {
      const t = (j / axisSteps) * axisLen
      const base = (i * cols + j) * 3
      positions[base] = ax1 + axisUx * t + acrossX * offset
      positions[base + 1] = elev
      positions[base + 2] = az1 + axisUz * t + acrossZ * offset
    }
  }
  for (let i = 0; i < rows - 1; i++) {
    for (let j = 0; j < cols - 1; j++) {
      const a = i * cols + j
      const b = a + 1
      const c = a + cols
      const d = c + 1
      indices.push(a, c, b, b, c, d)
    }
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geometry.setIndex(indices)
  geometry.computeVertexNormals()
  const material = new THREE.MeshStandardMaterial({
    color: VAULT_COLOR,
    roughness: 0.55,
    metalness: 0.1,
    transparent: true,
    opacity: 0.6,
    side: THREE.DoubleSide,
  })
  const mesh = new THREE.Mesh(geometry, material)
  mesh.castShadow = true
  mesh.receiveShadow = true
  mesh.name = 'vault-shell'
  return mesh
}

function makeSingleBox(obj: RealBoxObject, color: THREE.Color): THREE.Mesh {
  const mesh = new THREE.Mesh(
    new THREE.BoxGeometry(obj.size[0], obj.size[1], obj.size[2]),
    new THREE.MeshStandardMaterial({ color, roughness: 0.85, metalness: 0.08 }),
  )
  mesh.position.set(obj.pos[0], obj.pos[1], obj.pos[2])
  mesh.rotation.y = obj.rotY ?? 0
  mesh.castShadow = true
  mesh.receiveShadow = true
  return mesh
}

function asArray<T>(value: T | T[] | undefined): T[] {
  if (value === undefined) return []
  return Array.isArray(value) ? value : [value]
}

export function buildRealStation(manifest: RealStationManifest): StationModel {
  const root = new THREE.Group()
  root.name = `station-real`
  const objects = manifest.objects
  const layers: StationLayerHandle[] = []

  const addLayer = (id: string, label: string, children: THREE.Object3D[]): void => {
    if (children.length === 0) return
    const group = new THREE.Group()
    group.name = `layer-${id}`
    for (const child of children) group.add(child)
    layers.push({
      id,
      label,
      group,
      setVisible: (visible) => {
        group.visible = visible
      },
      visible: () => group.visible,
    })
    root.add(group)
  }

  addLayer('walls', `Walls (${objects.walls?.length ?? 0})`, objects.walls ? [makeInstancedBoxes(objects.walls, CONCRETE_BASE)] : [])
  addLayer('platform', 'Platform', asArray(objects.platform).map((obj) => makeSingleBox(obj, PLATFORM_COLOR)))
  addLayer('tracks', 'Tracks', asArray(objects.tracks).map((obj) => makeSingleBox(obj, TRACK_COLOR)))
  addLayer('piers', `Piers (${objects.piers?.length ?? 0})`, objects.piers ? [makeInstancedCylinders(objects.piers)] : [])
  addLayer('stairs', 'Stairs / cores', asArray(objects.stairs).map((obj) => makeSingleBox(obj, STAIR_COLOR)))
  if (objects.vault) addLayer('canopy', 'Canopy (vault)', [makeVaultMesh(objects.vault)])
  addLayer('lattice', `Facade lattice (${objects.lattice?.length ?? 0})`, objects.lattice ? [makeInstancedBoxes(objects.lattice, LATTICE_COLOR)] : [])
  addLayer('viaduct_deck', `Viaduct deck (${objects.viaduct_deck?.length ?? 0})`, objects.viaduct_deck ? [makeInstancedBoxes(objects.viaduct_deck, VIADUCT_DECK_COLOR)] : [])
  addLayer('viaduct_piers', `Viaduct piers (${objects.viaduct_piers?.length ?? 0})`, objects.viaduct_piers ? [makeInstancedCylinders(objects.viaduct_piers)] : [])

  return { name: manifest.name, root, layers, gltfRefs: [] }
}
