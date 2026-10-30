import * as THREE from 'three'
import type { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { createAvatar } from './avatar'
import type { Avatar } from './avatar'

/**
 * Third-person avatar walk mode.
 *
 * Click canvas -> pointer lock; the mouse orbits the camera boom around the
 * avatar, WASD moves the avatar relative to the camera (Shift runs), Esc
 * exits to orbit. The avatar stands on whatever the raycast-down ground
 * query finds under it: the station's floors/platform/stairs layers plus the
 * OSM ground — no hardcoded floor levels, so it works on every station
 * manifest. Steps up to 0.4 m (real stair steps) are climbed; drops lerp
 * smoothly. There is no wall collision in v1 and no jump.
 */

export const WALK_SPEED = 3.5 // m/s
export const RUN_SPEED = 7 // m/s

const LOOK_TARGET_HEIGHT = 1.35 // chest, above the avatar's feet
const BOOM_DIST_DEFAULT = 4.5
const BOOM_DIST_MIN = 2
const BOOM_DIST_MAX = 8
const STEP_UP = 0.4 // climbable step height (stair risers)
const GROUND_LERP = 10 // per-second lerp factor for settling down a drop
const TURN_RATE = 12 // per-second exponential factor for turn-to-face
const PITCH_MIN = -0.2
const PITCH_MAX = 1.25
const MOUSE_SENS = 0.0022
/** If the camera XZ is farther than this from the station core, spawn at the
 * core centre instead (the corridor's orbit camera sits kilometres out). */
const SPAWN_FALLBACK_DIST = 400

const DOWN = new THREE.Vector3(0, -1, 0)

export interface AvatarController {
  enter: () => void
  exit: () => void
  isActive: () => boolean
  /** Per-frame update; no-op when inactive. */
  update: (deltaSeconds: number) => void
  /** Scene-owned ground that is always walkable (base plane + OSM tiles). */
  setBaseGroups: (groups: THREE.Object3D[]) => void
  /** The streamed OSM tile layer (re-anchored per station; null when disposed). */
  setTileGroup: (group: THREE.Object3D | null) => void
  /** Station core centre — spawn fallback when the camera is far outside it. */
  setSpawnFallback: (point: { x: number; z: number } | null) => void
  /** Walkable layer groups of the loaded station (floors/platform/stairs). */
  setStationGroups: (groups: THREE.Object3D[]) => void
  /** Station is being swapped: exit, remove the avatar, drop station ground. */
  onStationUnload: () => void
  dispose: () => void
}

export function createAvatarController(
  scene: THREE.Scene,
  camera: THREE.PerspectiveCamera,
  domElement: HTMLElement,
  controls: OrbitControls,
): AvatarController {
  const hint = document.createElement('div')
  hint.className = 'walk-hint'
  hint.textContent =
    'Click to walk — WASD move — mouse orbits camera — Shift run — wheel zooms — Esc exit'
  hint.style.cssText =
    'position:absolute;top:12px;left:50%;transform:translateX(-50%);' +
    'padding:6px 14px;border-radius:6px;background:rgba(0,0,0,0.65);color:#fff;' +
    'font:13px/1.4 system-ui,sans-serif;pointer-events:none;display:none;z-index:10;'
  domElement.style.position = domElement.style.position || 'relative'
  domElement.parentElement?.appendChild(hint)

  let active = false
  let avatar: Avatar | null = null
  const baseGroups: THREE.Object3D[] = []
  let stationGroups: THREE.Object3D[] = []
  // Holder object: these are mutated only through setter closures, and TS
  // narrows a plain `let` to `never`/`null` inside the other closures.
  const ext = {
    tileGroup: null as THREE.Object3D | null,
    spawnFallback: null as { x: number; z: number } | null,
  }

  // Avatar state: pos = feet position, yaw = facing (facing vector is
  // (sin yaw, 0, cos yaw) since the model faces +Z).
  const pos = new THREE.Vector3()
  let avatarYaw = 0
  let groundY = 0
  let camYaw = 0
  let camPitch = 0.32
  let boomDist = BOOM_DIST_DEFAULT

  const keys = new Set<string>()
  const raycaster = new THREE.Raycaster()
  const candidateMeshes: THREE.Mesh[] = []
  const rayOrigin = new THREE.Vector3()
  const lookTarget = new THREE.Vector3()

  const onKeyDown = (e: KeyboardEvent): void => {
    keys.add(e.code)
  }
  const onKeyUp = (e: KeyboardEvent): void => {
    keys.delete(e.code)
  }
  const onMouseMove = (e: MouseEvent): void => {
    if (!active || document.pointerLockElement !== domElement) return
    camYaw -= e.movementX * MOUSE_SENS
    camPitch += e.movementY * MOUSE_SENS
    camPitch = Math.max(PITCH_MIN, Math.min(PITCH_MAX, camPitch))
  }
  const onWheel = (e: WheelEvent): void => {
    if (!active) return
    boomDist = Math.max(
      BOOM_DIST_MIN,
      Math.min(BOOM_DIST_MAX, boomDist * (1 + e.deltaY * 0.001)),
    )
  }
  const onPointerLockChange = (): void => {
    if (active && document.pointerLockElement !== domElement) {
      // Esc pressed (or lock lost) -> leave avatar mode.
      exit()
    }
  }
  const onClick = (): void => {
    if (active && !document.pointerLockElement) void domElement.requestPointerLock()
  }

  /** Highest walkable surface strictly below fromY at (x, z); null if none. */
  function queryGroundY(x: number, z: number, fromY: number): number | null {
    candidateMeshes.length = 0
    const collect = (group: THREE.Object3D): void => {
      group.traverse((object) => {
        if ((object as THREE.Mesh).isMesh && object.visible) {
          candidateMeshes.push(object as THREE.Mesh)
        }
      })
    }
    for (const group of baseGroups) collect(group)
    for (const group of stationGroups) collect(group)
    if (ext.tileGroup) collect(ext.tileGroup)
    if (candidateMeshes.length === 0) return null
    raycaster.set(rayOrigin.set(x, fromY, z), DOWN)
    raycaster.far = fromY + 100
    const hits = raycaster.intersectObjects(candidateMeshes, false)
    return hits.length > 0 ? hits[0].point.y : null
  }

  /** Shortest-arc exponential approach of yaw toward target. */
  function dampYaw(current: number, target: number, lambda: number, dt: number): number {
    let d = (target - current) % (Math.PI * 2)
    if (d > Math.PI) d -= Math.PI * 2
    if (d < -Math.PI) d += Math.PI * 2
    return current + d * (1 - Math.exp(-lambda * dt))
  }

  const enter = (): void => {
    if (active) return
    active = true
    controls.enabled = false
    // Spawn below the current camera XZ, snapped to the highest walkable
    // surface under it (D4) — but if the camera is far outside the station
    // core (corridor view), spawn at the core centre instead.
    let startX = camera.position.x
    let startZ = camera.position.z
    if (
      ext.spawnFallback &&
      Math.hypot(startX - ext.spawnFallback.x, startZ - ext.spawnFallback.z) > SPAWN_FALLBACK_DIST
    ) {
      startX = ext.spawnFallback.x
      startZ = ext.spawnFallback.z
    }
    groundY = queryGroundY(startX, startZ, camera.position.y) ?? 0
    pos.set(startX, groundY, startZ)
    // Face where the camera was looking; camera starts behind the avatar.
    const dir = camera.getWorldDirection(new THREE.Vector3())
    avatarYaw = Math.atan2(dir.x, dir.z)
    camYaw = avatarYaw + Math.PI
    camPitch = 0.32
    boomDist = BOOM_DIST_DEFAULT
    if (!avatar) {
      avatar = createAvatar()
      scene.add(avatar.group)
    }
    avatar.group.position.copy(pos)
    avatar.group.rotation.y = avatarYaw
    hint.style.display = 'block'
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('pointerlockchange', onPointerLockChange)
    domElement.addEventListener('click', onClick)
    domElement.addEventListener('wheel', onWheel, { passive: true })
  }

  const exit = (): void => {
    if (!active) return
    active = false
    if (document.pointerLockElement === domElement) document.exitPointerLock()
    controls.enabled = true
    // The avatar stays standing where it was left (D6) as a human scale
    // reference; orbit now circles its last position.
    controls.target.set(pos.x, pos.y + LOOK_TARGET_HEIGHT, pos.z)
    keys.clear()
    hint.style.display = 'none'
    window.removeEventListener('keydown', onKeyDown)
    window.removeEventListener('keyup', onKeyUp)
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('pointerlockchange', onPointerLockChange)
    domElement.removeEventListener('click', onClick)
    domElement.removeEventListener('wheel', onWheel)
  }

  const update = (dt: number): void => {
    if (!active || dt <= 0) return

    // Movement relative to the camera yaw (forward = camera->avatar direction).
    const fx = -Math.sin(camYaw)
    const fz = -Math.cos(camYaw)
    const rx = -fz // right = forward x up
    const rz = fx
    let mx = 0
    let mz = 0
    if (keys.has('KeyW') || keys.has('ArrowUp')) {
      mx += fx
      mz += fz
    }
    if (keys.has('KeyS') || keys.has('ArrowDown')) {
      mx -= fx
      mz -= fz
    }
    if (keys.has('KeyD') || keys.has('ArrowRight')) {
      mx += rx
      mz += rz
    }
    if (keys.has('KeyA') || keys.has('ArrowLeft')) {
      mx -= rx
      mz -= rz
    }
    const len = Math.hypot(mx, mz)
    const moving = len > 0
    const speed = moving ? (keys.has('ShiftLeft') || keys.has('ShiftRight') ? RUN_SPEED : WALK_SPEED) : 0
    if (moving) {
      pos.x += (mx / len) * speed * dt
      pos.z += (mz / len) * speed * dt
      avatarYaw = dampYaw(avatarYaw, Math.atan2(mx, mz), TURN_RATE, dt)
    }

    // Ground: accept surfaces up to STEP_UP above the current level (stairs),
    // ignore walls/roof hits, settle smoothly when dropping off an edge.
    const hit = queryGroundY(pos.x, pos.z, pos.y + 0.5)
    if (hit !== null && hit <= groundY + STEP_UP) groundY = hit
    if (pos.y < groundY) {
      pos.y = Math.min(groundY, pos.y + GROUND_LERP * dt) // quick step-up
    } else {
      pos.y += (groundY - pos.y) * Math.min(1, GROUND_LERP * dt) // smooth fall
    }

    if (avatar) {
      avatar.group.position.copy(pos)
      avatar.group.rotation.y = avatarYaw
      avatar.update(dt, moving ? speed : 0)
    }

    // Camera boom: orbit camYaw/camPitch around the chest, distance boomDist.
    lookTarget.set(pos.x, pos.y + LOOK_TARGET_HEIGHT, pos.z)
    const cosP = Math.cos(camPitch)
    camera.position.set(
      lookTarget.x + Math.sin(camYaw) * cosP * boomDist,
      lookTarget.y + Math.sin(camPitch) * boomDist,
      lookTarget.z + Math.cos(camYaw) * cosP * boomDist,
    )
    camera.lookAt(lookTarget)
    // Keep OrbitControls' target in sync (controls stay disabled) so the
    // distance-adaptive fog and ground streaming track the avatar.
    controls.target.copy(lookTarget)
  }

  const removeAvatar = (): void => {
    if (!avatar) return
    scene.remove(avatar.group)
    avatar.dispose()
    avatar = null
  }

  const onStationUnload = (): void => {
    exit()
    removeAvatar()
    stationGroups = []
  }

  const dispose = (): void => {
    exit()
    removeAvatar()
    hint.remove()
  }

  return {
    enter,
    exit,
    isActive: () => active,
    update,
    setBaseGroups: (groups) => {
      baseGroups.length = 0
      baseGroups.push(...groups)
    },
    setTileGroup: (group) => {
      ext.tileGroup = group
    },
    setSpawnFallback: (point) => {
      ext.spawnFallback = point
    },
    setStationGroups: (groups) => {
      stationGroups = groups
    },
    onStationUnload,
    dispose,
  }
}
