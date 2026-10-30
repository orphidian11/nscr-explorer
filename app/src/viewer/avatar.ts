import * as THREE from 'three'

/**
 * Procedural human avatar — a 1.75 m scale reference that walks the station.
 * Built entirely from primitives (no asset files, no animation mixer): the
 * walk/run cycle drives the limb pivots with sine swings whose amplitude and
 * frequency follow the ground speed, plus a hip bob and a run lean.
 */

export const AVATAR_HEIGHT = 1.75 // metres, top of head

// Speed reference for gait blending (mirrors the controller's RUN_SPEED).
const RUN_REF = 7

// Proportions (8-head canon), metres. Pivots: hips at 0.90, shoulders at 1.42.
const HIP_Y = 0.9
const HIP_X = 0.09
const SHOULDER_Y = 1.42
const SHOULDER_X = 0.215

const VEST = 0xf97316 // hi-vis orange, reads against grey concrete
const STRIPE = 0xf1f5f9
const SLEEVE = 0x334155
const TROUSERS = 0x1e293b
const SKIN = 0xc98e6a
const SHOE = 0x0f172a

export interface Avatar {
  group: THREE.Group
  /** Drive the gait. speed = horizontal ground speed in m/s (0 = idle). */
  update: (dt: number, speed: number) => void
  dispose: () => void
}

export function createAvatar(): Avatar {
  const mat = (color: number): THREE.MeshStandardMaterial =>
    new THREE.MeshStandardMaterial({ color, roughness: 0.85, metalness: 0 })
  const materials = [VEST, STRIPE, SLEEVE, TROUSERS, SKIN, SHOE].map(mat)

  const group = new THREE.Group()
  group.name = 'avatar' // the model faces +Z of this group

  const mesh = (geometry: THREE.BufferGeometry, material: THREE.Material): THREE.Mesh => {
    const m = new THREE.Mesh(geometry, material)
    m.castShadow = true
    return m
  }

  // Upper body (torso, head, arms) rides a lean pivot at hip height so a run
  // tilts it forward while the legs stay attached at the hips.
  const upper = new THREE.Group()
  upper.position.y = HIP_Y
  group.add(upper)

  const torso = mesh(new THREE.CapsuleGeometry(0.16, 0.2, 6, 16), materials[0])
  torso.position.y = 1.16 - HIP_Y
  const band = mesh(new THREE.BoxGeometry(0.3, 0.06, 0.33), materials[1])
  band.position.y = 1.24 - HIP_Y
  const head = mesh(new THREE.SphereGeometry(0.115, 20, 14), materials[4])
  head.position.y = 1.635 - HIP_Y
  upper.add(torso, band, head)

  const arms: THREE.Group[] = []
  for (const side of [-1, 1]) {
    const pivot = new THREE.Group()
    pivot.position.set(side * SHOULDER_X, SHOULDER_Y - HIP_Y, 0)
    const arm = mesh(new THREE.CapsuleGeometry(0.055, 0.51, 4, 10), materials[2])
    arm.position.y = -0.31
    pivot.add(arm)
    upper.add(pivot)
    arms.push(pivot)
  }

  const legs: THREE.Group[] = []
  for (const side of [-1, 1]) {
    const pivot = new THREE.Group()
    pivot.position.set(side * HIP_X, HIP_Y, 0)
    const leg = mesh(new THREE.CapsuleGeometry(0.08, 0.72, 4, 10), materials[3])
    leg.position.y = -0.44
    const foot = mesh(new THREE.BoxGeometry(0.11, 0.07, 0.26), materials[5])
    foot.position.set(0, -0.865, 0.05)
    pivot.add(leg, foot)
    group.add(pivot)
    legs.push(pivot)
  }
  const [armL, armR] = arms
  const [legL, legR] = legs

  let phase = 0
  let amp = 0
  let lean = 0

  const update = (dt: number, speed: number): void => {
    if (dt <= 0) return
    const moving = speed > 0.05
    const gait = THREE.MathUtils.clamp(speed / RUN_REF, 0, 1)
    // Leg half-swing: ~32 deg walking, ~46 deg sprinting; eases out on stop.
    const targetAmp = moving ? THREE.MathUtils.lerp(0.56, 0.8, gait) : 0
    amp += (targetAmp - amp) * Math.min(1, 10 * dt)
    // Step cycle 1.2..2.8 Hz, scaled by speed.
    if (moving) phase += THREE.MathUtils.clamp(speed / 0.9, 1.2, 2.8) * Math.PI * 2 * dt
    const s = Math.sin(phase)
    legL.rotation.x = s * amp
    legR.rotation.x = -s * amp
    armL.rotation.x = -s * amp * 0.75
    armR.rotation.x = s * amp * 0.75
    const targetLean = moving ? 0.1 * gait : 0
    lean += (targetLean - lean) * Math.min(1, 6 * dt)
    upper.rotation.x = lean
    // Hip bob at twice the step frequency — only the upper body rides it so
    // the feet stay near the ground.
    upper.position.y = HIP_Y + (moving ? Math.abs(Math.cos(phase)) * 0.035 : 0)
  }

  const dispose = (): void => {
    group.traverse((object) => {
      const m = object as THREE.Mesh
      if (m.isMesh) m.geometry.dispose()
    })
    for (const material of materials) material.dispose()
  }

  return { group, update, dispose }
}
