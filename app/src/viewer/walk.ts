import * as THREE from 'three'
import type { OrbitControls } from 'three/addons/controls/OrbitControls.js'

/**
 * First-person WALK mode.
 *
 * Click canvas -> pointer lock; WASD/arrows move, mouse looks, Shift runs
 * (x2), Esc exits. Eye height is 1.6 m above the highest floor level whose
 * horizontal extent contains the camera XZ position. Stairs/elevators are
 * not walkable (no vertical movement in v1); walking off a floor edge drops
 * the camera to the floor below (smoothly lerped).
 */

export const EYE_HEIGHT = 1.6 // metres

// Floor levels verified from drawings (metres).
const GROUND_Y = 0.5
const CONCOURSE_Y = 4.6
const PLATFORM_Y = 11.9

/**
 * Floor extents, station local frame (x = east, z = -north), station centred
 * at origin, long axis rotated ~63 deg in XZ. Conservative axis-aligned
 * bbox for the station building footprint (ground + concourse). Kept as
 * module constants so they are easy to refine.
 */
const STATION_HALF = 60 // x -60..60, z -60..60

// Platform geometry: track centreline runs through origin along d, two side
// platforms 4 m wide at +/-9 m lateral offset, 190 m long.
const TRACK_DIR = new THREE.Vector2(-0.474, -0.881).normalize()
const PLATFORM_HALF_WIDTH = 2 // 4 m wide
const PLATFORM_OFFSET = 9 // centre of each platform from track centreline
const PLATFORM_HALF_LENGTH = 95 // 190 m long

interface Floor {
  y: number
  contains: (x: number, z: number) => boolean
}

const inStation = (x: number, z: number): boolean =>
  Math.abs(x) <= STATION_HALF && Math.abs(z) <= STATION_HALF

/** Signed lateral distance from the track centreline through origin. */
function lateralFromTrack(x: number, z: number): number {
  // cross(dir, p) in 2D: dir.x * p.z - dir.z * p.x (z here is the XZ-plane axis)
  return TRACK_DIR.x * z - TRACK_DIR.y * x
}

/** Signed along-track distance from origin. */
function alongTrack(x: number, z: number): number {
  return TRACK_DIR.x * x + TRACK_DIR.y * z
}

const FLOORS: Floor[] = [
  {
    y: PLATFORM_Y,
    contains: (x, z) => {
      const lat = Math.abs(lateralFromTrack(x, z))
      const along = Math.abs(alongTrack(x, z))
      return (
        along <= PLATFORM_HALF_LENGTH &&
        (Math.abs(lat - PLATFORM_OFFSET) <= PLATFORM_HALF_WIDTH ||
          Math.abs(lat + PLATFORM_OFFSET) <= PLATFORM_HALF_WIDTH)
      )
    },
  },
  { y: CONCOURSE_Y, contains: inStation },
  { y: GROUND_Y, contains: inStation },
]

/** Highest floor level whose extent contains (x, z); base plane at y=0. */
export function floorYAt(x: number, z: number): number {
  for (const floor of FLOORS) {
    if (floor.contains(x, z)) return floor.y
  }
  return 0
}

const WALK_SPEED = 4 // m/s
const FLY_SPEED = 60 // m/s — corridor distances between stations are ~2 km
const RUN_MULT = 2
const EYE_LERP = 8 // per-second lerp factor for vertical settle

export type NavMode = 'walk' | 'fly'

export interface WalkController {
  enter: (mode?: NavMode) => void
  exit: () => void
  isActive: () => boolean
  getMode: () => NavMode
  /** Per-frame update; no-op when inactive. */
  update: (deltaSeconds: number) => void
  dispose: () => void
}

export function createWalkController(
  camera: THREE.PerspectiveCamera,
  domElement: HTMLElement,
  controls: OrbitControls,
): WalkController {
  const hint = document.createElement('div')
  hint.className = 'walk-hint'
  hint.textContent = 'Click to walk - WASD move - mouse look - Esc exit'
  hint.style.cssText =
    'position:absolute;top:12px;left:50%;transform:translateX(-50%);' +
    'padding:6px 14px;border-radius:6px;background:rgba(0,0,0,0.65);color:#fff;' +
    'font:13px/1.4 system-ui,sans-serif;pointer-events:none;display:none;z-index:10;'
  domElement.style.position = domElement.style.position || 'relative'
  domElement.parentElement?.appendChild(hint)

  let active = false
  let mode: NavMode = 'walk'
  let yaw = 0
  let pitch = 0
  const keys = new Set<string>()
  const forward = new THREE.Vector3()
  const right = new THREE.Vector3()

  const onKeyDown = (e: KeyboardEvent): void => {
    keys.add(e.code)
  }
  const onKeyUp = (e: KeyboardEvent): void => {
    keys.delete(e.code)
  }

  const onMouseMove = (e: MouseEvent): void => {
    if (!active || document.pointerLockElement !== domElement) return
    yaw -= e.movementX * 0.0022
    pitch -= e.movementY * 0.0022
    const limit = Math.PI / 2 - 0.01
    pitch = Math.max(-limit, Math.min(limit, pitch))
  }

  const onPointerLockChange = (): void => {
    if (active && document.pointerLockElement !== domElement) {
      // Esc pressed (or lock lost) -> leave walk mode.
      exit()
    }
  }

  const onClick = (): void => {
    if (active) void domElement.requestPointerLock()
  }

  const syncEuler = (): void => {
    camera.rotation.set(pitch, yaw, 0, 'YXZ')
  }

  const enter = (navMode: NavMode = 'walk'): void => {
    if (active && mode === navMode) return
    if (active) exit()
    active = true
    mode = navMode
    controls.enabled = false
    if (mode === 'walk') {
      // Start at the current camera XZ, snapped to the floor below.
      const eye = floorYAt(camera.position.x, camera.position.z) + EYE_HEIGHT
      camera.position.y = eye
      pitch = 0
    }
    const dir = new THREE.Vector3()
    camera.getWorldDirection(dir)
    yaw = Math.atan2(-dir.x, -dir.z)
    syncEuler()
    hint.textContent =
      mode === 'fly'
        ? 'FLY: click to lock - WASD move (follows view) - Space/C up/down - Shift boost - Esc exit'
        : 'Click to walk - WASD move - mouse look - Esc exit'
    hint.style.display = 'block'
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('pointerlockchange', onPointerLockChange)
    domElement.addEventListener('click', onClick)
  }

  const exit = (): void => {
    if (!active) return
    active = false
    if (document.pointerLockElement === domElement) document.exitPointerLock()
    controls.enabled = true
    keys.clear()
    hint.style.display = 'none'
    window.removeEventListener('keydown', onKeyDown)
    window.removeEventListener('keyup', onKeyUp)
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('pointerlockchange', onPointerLockChange)
    domElement.removeEventListener('click', onClick)
  }

  const update = (dt: number): void => {
    if (!active || dt <= 0) return
    const run = keys.has('ShiftLeft') || keys.has('ShiftRight')
    const speed = (mode === 'fly' ? FLY_SPEED : WALK_SPEED) * (run ? RUN_MULT : 1)

    if (mode === 'fly') {
      // Free flight: movement follows the full view direction (incl. pitch),
      // Space/C for vertical, no ground clamping (min y 0.5 to stay above ground).
      camera.getWorldDirection(forward)
      right.set(forward.z, 0, -forward.x).normalize()
      const move = new THREE.Vector3()
      if (keys.has('KeyW') || keys.has('ArrowUp')) move.add(forward)
      if (keys.has('KeyS') || keys.has('ArrowDown')) move.sub(forward)
      if (keys.has('KeyD') || keys.has('ArrowRight')) move.add(right)
      if (keys.has('KeyA') || keys.has('ArrowLeft')) move.sub(right)
      if (keys.has('Space')) move.y += 1
      if (keys.has('KeyC') || keys.has('ControlLeft')) move.y -= 1
      if (move.lengthSq() > 0) {
        move.normalize().multiplyScalar(speed * dt)
        camera.position.add(move)
      }
      if (camera.position.y < 0.5) camera.position.y = 0.5
      syncEuler()
      return
    }

    // Camera-relative movement in the horizontal plane (yaw only).
    forward.set(-Math.sin(yaw), 0, -Math.cos(yaw))
    right.set(forward.z, 0, -forward.x) // 90 deg to the right of forward

    let moveX = 0
    let moveZ = 0
    if (keys.has('KeyW') || keys.has('ArrowUp')) {
      moveX += forward.x
      moveZ += forward.z
    }
    if (keys.has('KeyS') || keys.has('ArrowDown')) {
      moveX -= forward.x
      moveZ -= forward.z
    }
    if (keys.has('KeyD') || keys.has('ArrowRight')) {
      moveX += right.x
      moveZ += right.z
    }
    if (keys.has('KeyA') || keys.has('ArrowLeft')) {
      moveX -= right.x
      moveZ -= right.z
    }

    const len = Math.hypot(moveX, moveZ)
    if (len > 0) {
      const step = (speed * dt) / len
      camera.position.x += moveX * step
      camera.position.z += moveZ * step
    }

    // Eye height: 1.6 m above the highest floor under the camera; lerped so
    // walking off an edge drops smoothly to the floor below.
    const targetEye = floorYAt(camera.position.x, camera.position.z) + EYE_HEIGHT
    camera.position.y += (targetEye - camera.position.y) * Math.min(1, EYE_LERP * dt)
    syncEuler()
  }

  const dispose = (): void => {
    exit()
    hint.remove()
  }

  return { enter, exit, isActive: () => active, getMode: () => mode, update, dispose }
}
