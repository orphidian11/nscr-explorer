# Plan: Third-Person Avatar Walk Mode

Status: **PROPOSED — awaiting review. Nothing is implemented.**
Scope: replace the first-person Walk camera with a human-scale avatar that walks
around the station, seen from a third-person camera.

---

## 0. Interpretation (assumption to confirm)

"Have it walk around the station" = **user-controlled avatar**: the visitor
drives it with WASD + mouse (standard third-person action-game controls).
Not an autonomous NPC wandering on its own (that is a cheap follow-up later —
see §9).

## 1. What is discarded vs kept

| Item | Today | After |
|---|---|---|
| `Walk` preset | First-person pointer-lock camera at eye 1.6 m | **Discarded** — replaced by avatar mode (same button) |
| `walk.ts` movement code | WASD moves the camera; eye snapped to hardcoded floors | **Discarded** — avatar walks, camera follows on a boom |
| Floor-snap logic `floorYAt()` | Hardcoded Bicutan constants (ground 0.5 / concourse 4.6 / platform 11.9) | **Replaced** (see §4 — Bicutan-only constants are wrong for Sucat +16.60 / EDSA at-grade) |
| `Fly` preset | Free flight, 60 m/s, shares the controller | **Kept unchanged** (separate mode; say the word if you want it gone too) |
| `Orbit` / `Top` presets, ground streaming, click-to-select, pick handler | — | Kept unchanged |

## 2. Avatar design (Decision D1)

**Recommended — procedural low-poly human built from Three.js primitives**
(capsules + boxes, one Group, casts a real shadow — the renderer's shadow map
is already enabled):

- Standing height **1.75 m** (8-head canon): head sphere Ø 0.23 m at ~1.64 m,
  torso capsule ~0.50 m, arm capsules 0.62 m pivoted at the shoulders (1.42 m),
  leg capsules 0.85 m pivoted at the hips (0.90 m), small foot boxes.
  Collision footprint ~Ø 0.4 m.
- Procedural animation, no asset files: leg swing ±~30° and counter-swinging
  arms at a step frequency proportional to ground speed (~1.7 Hz walk,
  ~2.3 Hz run), torso bob ~0.03 m, slight forward lean when running,
  subtle idle sway when standing.
- Hi-vis commuter colouring (orange vest / dark trousers) so the figure reads
  against grey concrete.
- Zero new dependencies, zero asset downloads, no licensing questions, adds
  ~0 KB to the bundle, works offline.

**Alternative — rigged GLTF character** (e.g. Mixamo export or a free CC model)
with baked idle/walk/run clips cross-faded via `AnimationMixer`. Looks more
realistic; costs a 2–5 MB asset committed to the repo, a license check, and
mixer/fade code. GLTFLoader ships with `three` 0.186 already, so no install
needed either way.

Scale is the point either way: the avatar doubles as a **human scale reference**
standing in the scene (see D6).

## 3. Controls and third-person camera

- Enter: `Walk` panel button → "Click to walk" → pointer lock (same flow as
  today). Esc exits to Orbit.
- **Mouse** orbits the camera boom around the avatar (pointer-locked, yaw free,
  pitch clamped).
- **WASD** moves the avatar relative to the camera's yaw (standard TPS); the
  avatar smoothly turns to face its movement direction (~10 rad/s slerp).
  Speeds: walk **3.5 m/s**, Shift run **7 m/s** (replaces 4 / 8).
- **Camera boom**: 4.5 m behind, 2.2 m above the avatar's feet, look-at chest
  (+1.35 m). Mouse-wheel zoom 2–8 m.
- No jump/crouch in v1. No wall collision in v1 (avatar can pass through
  walls — same as today's first-person walk; see §9 for the phase-2 fix).

## 4. Ground model — where the avatar can stand (Decision D2)

**Recommended — raycast-down ground query instead of hardcoded floors.**
Each frame, cast a ray from just above the avatar's feet downward:

- Candidate surfaces = the loaded station's walkable layers (`floors`,
  `platform`, `stairs`) + the streamed OSM tile group + the base ground plane.
  Three.js raycasts InstancedMesh natively; the candidate set is bounded, so
  this is per-frame cheap.
- Step-up allowance ≤ 0.4 m (climb actual stair-step geometry — the manifests
  have a `stairs` key; Bicutan carries real stair prims), smooth lerp when
  stepping off an edge (reuse today's `EYE_LERP` pattern for fall settle).
- Fallback if nothing hit: base ground at y = 0.

Why replace the constants: they are **Bicutan-only**. Sucat's real levels are
GF +1.00, concourse +7.85, platform +16.60; EDSA is at-grade; FTI platform
+2.00. Today's first-person walk already stands you 4.7 m below Sucat's
platform. The raycast model fixes that class of bug for **all 8 manifests**
including the 5-station corridor, with no per-station tuning — consistent with
the project rule that geometry is manifest-driven, not hardcoded.

## 5. Spawn and lifecycle (Decision D4)

- **Spawn**: at the current camera XZ, snapped to the ground below (matches
  today's walk-enter behaviour); if nothing walkable is found within range,
  spawn at the station bbox centre on the ground. Station-entrance spawning is
  possible later (entrances are recorded for Bicutan in `commuter.json`).
- **Station switch**: the avatar is removed and re-spawned after the new
  manifest loads — each manifest has its own local frame, so a persistent
  avatar would sit kilometres off.
- **After Esc** (D6): recommend the avatar **stays standing** where you left it,
  as a human-scale reference visible from Orbit/Top; removed on station change.

## 6. Code changes

| File | Change |
|---|---|
| `src/viewer/avatar.ts` **(new)** | Avatar mesh factory + procedural walk/idle/run animation. Knows nothing about input or camera. |
| `src/viewer/avatarController.ts` **(new)** | Pointer-lock input, movement + turning, raycast ground query, camera boom, hint UI, enter/exit lifecycle, `isActive()`. Patterns reused from today's `walk.ts`. |
| `src/viewer/walk.ts` → `src/viewer/fly.ts` | First-person walk code deleted; file keeps only Fly mode (renamed to say what it is). |
| `src/viewer/scene.ts` | Preset `'walk'` → `'avatar'` internally; render loop calls avatar update when active (still skips `controls.update()` while a nav mode owns the camera — the maxDistance-leash pitfall); `fitCameraTo` rescales the avatar spawn framing instead of the walk preset pose. |
| `src/main.ts` | Disposes/respawns the avatar on station change; hands the walkable-candidate groups to the controller after each manifest load. |
| `src/ui/panel.ts` | Hint text: "Click to walk — WASD move — mouse orbits camera — Shift run — Esc exit". Button label per D5. |
| `src/ui/changelog.ts` | New entry at top + `APP_VERSION` bump (v1.1.0). |
| `SPEC.md` | Status-log entry after implementation. |

No new npm dependencies (option A). ~400 new LOC, ~130 removed.

## 7. Verification plan

1. `npm run build` (tsc + vite) clean.
2. **Headless mechanics test** (hidden-tab rAF pitfall): drive the controller
   with fixed `dt` via `window.__viewer` and assert displacement ≈ speed × time,
   correct ground Y after a platform step, yaw turn completes.
3. **Browser screenshots at eye level of the camera** (not orbit views):
   - avatar on the platform beside a 0.5 m column and under the +9.75 beams —
     scale cross-check against drawn elements;
   - mid-stride walk frame and run frame;
   - third-person framing on concourse + at grade.
4. Proof GIF assembled from sampled frames → `docs/avatar-walk-proof.gif`
   (same convention as `fly-mode-proof.gif`).
5. **No deploy to production** — build verified locally only, per the release
   gate; version bump and deploy happen after your approval.

## 8. Decisions for your review

| # | Decision | Recommendation | Alternative |
|---|---|---|---|
| D1 | Avatar rendering | Procedural primitives + programmatic animation | Rigged GLTF character with baked clips (realistic, +2–5 MB asset) |
| D2 | Ground model | Raycast-down vs walkable layers (station-agnostic) | Keep hardcoded Bicutan floor constants |
| D3 | Fly mode | Keep unchanged | Discard too |
| D4 | Spawn point | Below current camera, snapped to ground | Fixed station-entrance spawn |
| D5 | Panel button label | Keep "Walk" | Rename to "Avatar" |
| D6 | Avatar after Esc | Persists as a scale reference until station change | Removed on exit |

## 9. Explicitly out of scope (phase-2 candidates)

- Wall collision (2D push-out against the manifest's wall segments — feasible
  later since walls are line segments), camera anti-clip raycast on the boom.
- Jump/crouch, escalator rides.
- Autonomous ambient commuters (NPCs) walking the platform — an easy follow-up
  reusing this avatar at near-zero extra code.
- Entrance-anchored spawn for stations with recorded entrances.
