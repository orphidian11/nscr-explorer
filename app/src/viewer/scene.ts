import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { createWalkController } from './walk'
import type { WalkController } from './walk'

export type CameraPresetName = 'orbit' | 'walk' | 'fly' | 'top'

export interface CameraPreset {
  label: string
  /** Camera position [x, y, z] in meters. */
  position: [number, number, number]
  /** OrbitControls target [x, y, z] in meters. */
  target: [number, number, number]
}

export const CAMERA_PRESETS: Record<CameraPresetName, CameraPreset> = {
  orbit: { label: 'Orbit', position: [115, 75, 115], target: [0, 8, 0] },
  walk: { label: 'Walk', position: [26, 1.7, 78], target: [0, 10, -10] },
  fly: { label: 'Fly', position: [200, 120, 380], target: [-460, 5, -880] },
  top: { label: 'Top', position: [0.01, 230, 0.01], target: [0, 0, 0] },
}

const SKY_COLOR = 0xaecbe4
const GROUND_SIZE = 200 // meters
const GRID_CELL = 10 // meters -> 200 / 10 = 20 divisions

export interface ViewerScene {
  scene: THREE.Scene
  camera: THREE.PerspectiveCamera
  renderer: THREE.WebGLRenderer
  controls: OrbitControls
  walk: WalkController
  applyPreset: (name: CameraPresetName) => void
  /** Recompute the presets so they frame the given bounds, then apply 'orbit'. */
  fitCameraTo: (box: THREE.Box3) => void
  /** Register a handler for click-picks on station geometry (drag-safe). */
  setPickHandler: (handler: ((worldPoint: THREE.Vector3) => void) | null) => void
  setGridVisible: (visible: boolean) => void
  dispose: () => void
}

/** Working copy of the presets, rescaled by fitCameraTo to frame a station. */
const activePresets: Record<CameraPresetName, CameraPreset> = { ...CAMERA_PRESETS }

export function createViewerScene(container: HTMLElement): ViewerScene {
  const width = Math.max(container.clientWidth, 1)
  const height = Math.max(container.clientHeight, 1)

  const renderer = new THREE.WebGLRenderer({ antialias: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setSize(width, height)
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  container.appendChild(renderer.domElement)

  // OrbitControls calls setPointerCapture on pointerdown; it throws NotFoundError
  // when the pointer is already gone (fast clicks, focus edges). Capture failure
  // only affects drag continuation, so degrade gracefully instead of erroring.
  const proto = Element.prototype as unknown as { setPointerCapture: (...a: unknown[]) => void }
  const originalCapture = proto.setPointerCapture
  proto.setPointerCapture = function (...args: unknown[]) {
    try {
      originalCapture.apply(this, args)
    } catch {
      /* pointer no longer active — ignore */
    }
  }

  const scene = new THREE.Scene()
  scene.background = new THREE.Color(SKY_COLOR)
  scene.fog = new THREE.Fog(SKY_COLOR, 420, 1500)

  const camera = new THREE.PerspectiveCamera(55, width / height, 0.1, 2500)
  camera.position.set(...CAMERA_PRESETS.orbit.position)

  const controls = new OrbitControls(camera, renderer.domElement)
  controls.target.set(...CAMERA_PRESETS.orbit.target)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.maxPolarAngle = Math.PI * 0.495
  controls.minDistance = 2
  controls.maxDistance = 900
  controls.update()

  const hemisphere = new THREE.HemisphereLight(0xd9e8ff, 0x51604f, 1.1)
  scene.add(hemisphere)

  const sun = new THREE.DirectionalLight(0xfff1de, 2.6)
  sun.position.set(90, 150, 70)
  sun.castShadow = true
  sun.shadow.mapSize.set(2048, 2048)
  sun.shadow.camera.left = -170
  sun.shadow.camera.right = 170
  sun.shadow.camera.top = 170
  sun.shadow.camera.bottom = -170
  sun.shadow.camera.near = 20
  sun.shadow.camera.far = 500
  sun.shadow.bias = -0.0004
  sun.shadow.normalBias = 0.03
  scene.add(sun)

  // Ground plane: GROUND_SIZE x GROUND_SIZE m with a GRID_CELL m grid.
  const ground = new THREE.Group()
  ground.name = 'ground'

  const groundMesh = new THREE.Mesh(
    new THREE.PlaneGeometry(GROUND_SIZE, GROUND_SIZE),
    new THREE.MeshStandardMaterial({ color: 0x93a08b, roughness: 1, metalness: 0 }),
  )
  groundMesh.rotation.x = -Math.PI / 2
  groundMesh.receiveShadow = true

  const grid = new THREE.GridHelper(GROUND_SIZE, GROUND_SIZE / GRID_CELL, 0x51779c, 0x7d94aa)
  grid.position.y = 0.02
  const gridMaterial = grid.material as THREE.Material
  gridMaterial.transparent = true
  gridMaterial.opacity = 0.35

  ground.add(groundMesh, grid)
  scene.add(ground)

  const resize = (): void => {
    const w = container.clientWidth
    const h = container.clientHeight
    if (w === 0 || h === 0) return
    camera.aspect = w / h
    camera.updateProjectionMatrix()
    renderer.setSize(w, h)
  }
  const resizeObserver = new ResizeObserver(resize)
  resizeObserver.observe(container)

  const walk = createWalkController(camera, renderer.domElement, controls)

  // Click-pick: raycast station geometry on genuine clicks (not orbit drags).
  const pickState: { handler: ((worldPoint: THREE.Vector3) => void) | null } = { handler: null }
  let downX = 0
  let downY = 0
  const raycaster = new THREE.Raycaster()
  renderer.domElement.addEventListener('pointerdown', (e) => {
    downX = e.clientX
    downY = e.clientY
  })
  renderer.domElement.addEventListener('pointerup', (e) => {
    const handler = pickState.handler
    if (!handler) return
    if (Math.hypot(e.clientX - downX, e.clientY - downY) > 5) return // was a drag
    const rect = renderer.domElement.getBoundingClientRect()
    const ndc = new THREE.Vector2(
      ((e.clientX - rect.left) / rect.width) * 2 - 1,
      -((e.clientY - rect.top) / rect.height) * 2 + 1,
    )
    raycaster.setFromCamera(ndc, camera)
    const hits = raycaster.intersectObjects(scene.children, true)
    const hit = hits.find((h) => !h.object.name.startsWith('tile-')) // ignore ground tiles
    if (hit) handler(hit.point)
  })

  renderer.setAnimationLoop((time) => {
    const last = (renderer as unknown as { __lastFrameTime?: number }).__lastFrameTime
    const dt = last === undefined ? 0 : Math.min((time - last) / 1000, 0.1)
    ;(renderer as unknown as { __lastFrameTime?: number }).__lastFrameTime = time
    walk.update(dt)
    controls.update()
    renderer.render(scene, camera)
  })

  const applyPreset = (name: CameraPresetName): void => {
    if (name === 'walk' || name === 'fly') {
      walk.enter(name)
      return
    }
    walk.exit()
    const preset = activePresets[name]
    camera.position.set(...preset.position)
    controls.target.set(...preset.target)
    controls.update()
  }

  const fitCameraTo = (box: THREE.Box3): void => {
    const center = box.getCenter(new THREE.Vector3())
    const size = box.getSize(new THREE.Vector3())
    const radius = Math.max(size.length() / 2, 10)
    const dist = radius * 1.9

    const orbitDir = new THREE.Vector3(0.72, 0.42, 0.72).normalize()
    activePresets.orbit = {
      label: 'Orbit',
      position: [center.x + orbitDir.x * dist, center.y + orbitDir.y * dist, center.z + orbitDir.z * dist],
      target: [center.x, center.y, center.z],
    }
    // Eye-level view along the long axis of the station.
    const longAxis = Math.abs(size.x) >= Math.abs(size.z) ? 1 : 0
    const walkOffset = longAxis === 1 ? [0.1, radius * 0.4, dist * 0.95] : [dist * 0.95, radius * 0.4, 0.1]
    activePresets.walk = {
      label: 'Walk',
      position: [center.x + walkOffset[0], Math.max(center.y + walkOffset[1], 1.7), center.z + walkOffset[2]],
      target: [center.x, center.y + size.y * 0.25, center.z],
    }
    activePresets.top = {
      label: 'Top',
      position: [center.x + 0.01, center.y + dist * 1.35, center.z + 0.01],
      target: [center.x, center.y, center.z],
    }
    // Fly starts high and off to the side, looking toward the station centre —
    // a good vantage to fly the corridor from.
    activePresets.fly = {
      label: 'Fly',
      position: [
        center.x + orbitDir.x * dist * 1.2,
        center.y + dist * 0.5,
        center.z + orbitDir.z * dist * 1.2,
      ],
      target: [center.x, center.y, center.z],
    }

    controls.maxDistance = dist * 6
    // The far plane must cover the framed extent — a ±4 km viaduct blows past a
    // fixed 2500 m far plane and renders as a blank sky-coloured viewport.
    camera.far = Math.max(camera.far, dist * 6)
    camera.updateProjectionMatrix()
    if (scene.fog instanceof THREE.Fog) {
      scene.fog.near = dist * 1.6
      scene.fog.far = dist * 6
    }
    applyPreset('orbit')
  }

  const setGridVisible = (visible: boolean): void => {
    grid.visible = visible
  }

  const dispose = (): void => {
    renderer.setAnimationLoop(null)
    resizeObserver.disconnect()
    controls.dispose()
    walk.dispose()
    renderer.dispose()
    renderer.domElement.remove()
  }

  const setPickHandler = (handler: ((worldPoint: THREE.Vector3) => void) | null): void => {
    pickState.handler = handler
  }
  return { scene, camera, renderer, controls, walk, applyPreset, fitCameraTo, setPickHandler, setGridVisible, dispose }
}
