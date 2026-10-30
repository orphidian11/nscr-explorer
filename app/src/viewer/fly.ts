import * as THREE from 'three'
import type { OrbitControls } from 'three/addons/controls/OrbitControls.js'

/**
 * Free-flight mode: pointer-lock WASD movement that follows the full view
 * direction (including pitch), Space/C for vertical, Shift boost, Esc exits.
 * Sized for corridor-scale travel between stations (~2 km apart).
 */

const FLY_SPEED = 60 // m/s — inter-station distances are kilometres
const RUN_MULT = 2

export interface FlyController {
  enter: () => void
  exit: () => void
  isActive: () => boolean
  /** Per-frame update; no-op when inactive. */
  update: (deltaSeconds: number) => void
  dispose: () => void
}

export function createFlyController(
  camera: THREE.PerspectiveCamera,
  domElement: HTMLElement,
  controls: OrbitControls,
): FlyController {
  const hint = document.createElement('div')
  hint.className = 'walk-hint'
  hint.textContent =
    'FLY: click to lock - WASD move (follows view) - Space/C up/down - Shift boost - Esc exit'
  hint.style.cssText =
    'position:absolute;top:12px;left:50%;transform:translateX(-50%);' +
    'padding:6px 14px;border-radius:6px;background:rgba(0,0,0,0.65);color:#fff;' +
    'font:13px/1.4 system-ui,sans-serif;pointer-events:none;display:none;z-index:10;'
  domElement.style.position = domElement.style.position || 'relative'
  domElement.parentElement?.appendChild(hint)

  let active = false
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
      // Esc pressed (or lock lost) -> leave fly mode.
      exit()
    }
  }

  const onClick = (): void => {
    if (active && !document.pointerLockElement) void domElement.requestPointerLock()
  }

  const syncEuler = (): void => {
    camera.rotation.set(pitch, yaw, 0, 'YXZ')
  }

  const enter = (): void => {
    if (active) return
    active = true
    controls.enabled = false
    const dir = new THREE.Vector3()
    camera.getWorldDirection(dir)
    yaw = Math.atan2(-dir.x, -dir.z)
    syncEuler()
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
    const speed = FLY_SPEED * (keys.has('ShiftLeft') || keys.has('ShiftRight') ? RUN_MULT : 1)
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
  }

  const dispose = (): void => {
    exit()
    hint.remove()
  }

  return { enter, exit, isActive: () => active, update, dispose }
}
