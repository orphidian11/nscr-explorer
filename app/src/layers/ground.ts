/**
 * ground.ts — OSM raster-tile ground layer for the local ENU scene.
 *
 * Builds a THREE.Group of textured PlaneGeometry tiles (Web-Mercator slippy
 * tiles) laid flat on the y=0 plane, georeferenced to an anchor lat/lon.
 *
 * Local frame: +x = east (m), +z = -north (m), +y = up.
 * Tile geometry is laid out in Web-Mercator metres; the east axis is scaled
 * by cos(anchorLat) (≈0.9682 at Bicutan 14.48748°N) so that local metre
 * units match true ground metres — i.e. the ground plane is uniformly
 * compressed in x by cos(lat), and everything placed through
 * latLonToLocal() with the same anchor lands correctly on the tiles.
 *
 * Tile source: https://tile.openstreetmap.org/{z}/{x}/{y}.png (CORS-enabled).
 * Usage policy requires visible attribution — export `groundAttribution` and
 * show it in the UI. Be gentle: cache is shared, tiles fetched once.
 */

import * as THREE from 'three';
import {
  OSM_TILE_TEMPLATE,
  OSM_TILE_ATTRIBUTION,
  TileCoord,
  latToTileY,
  lonToTileX,
  latToMercY,
  lonToMercX,
  tileWorldSize,
  clampTileX,
  clampTileY,
  loadTileTexture,
  WEB_MERCATOR_RADIUS,
} from './tiles';

/** Attribution string the UI must display while the ground layer is visible. */
export const groundAttribution = OSM_TILE_ATTRIBUTION;

export interface GroundLayerOptions {
  /** Anchor latitude (degrees, WGS84). */
  lat: number;
  /** Anchor longitude (degrees, WGS84). */
  lon: number;
  /** Tile zoom level (17 ≈ station detail, 15 ≈ line overview). */
  zoom: number;
  /** Ground coverage radius in metres. Defaults per zoom level below. */
  radiusMeters?: number;
  /** Tile URL template; defaults to OSM standard tiles. */
  tileTemplate?: string;
  /** Optional tint applied while tiles load (default: neutral asphalt grey). */
  placeholderColor?: number;
}

/** Default coverage radius (m) per zoom level. */
const DEFAULT_RADIUS: Record<number, number> = {
  15: 2000,
  16: 1200,
  17: 700,
  18: 300,
};

export interface GroundLayer {
  /** Group containing the tile meshes; add to the scene, position at origin. */
  group: THREE.Group;
  /** Number of tile meshes currently live (updates as streaming progresses). */
  readonly tileCount: number;
  /**
   * Stream tiles around a camera position (local metres, layer frame).
   * Idempotent + throttled: no-op unless the camera moved ≥ half a tile.
   */
  update: (centerX: number, centerZ: number) => void;
  /** Loads all pending tile textures; resolves when every job finished or failed. */
  load: () => Promise<void>;
  /** Dispose geometries/materials and remove from parent. */
  dispose: () => void;
}

/**
 * Convert lat/lon to local ENU metres relative to an anchor.
 * x = east, y = 0 (up, caller sets altitude), z = -north.
 * Applies the Web-Mercator cos(lat) scale correction on the east axis.
 */
export function latLonToLocal(
  lat: number,
  lon: number,
  anchorLat: number,
  anchorLon: number,
): { x: number; y: number; z: number } {
  const cosLat = Math.cos((anchorLat * Math.PI) / 180);
  const dxMerc = lonToMercX(lon) - lonToMercX(anchorLon);
  const dyMerc = latToMercY(lat) - latToMercY(anchorLat);
  return {
    x: dxMerc * cosLat,
    y: 0,
    z: -dyMerc,
  };
}

/**
 * Inverse of latLonToLocal for the horizontal plane: local metres (relative to
 * the anchor) back to lat/lon. east = x / cosLat, north = -z, then invert the
 * Web-Mercator projection (exact inverse of the forward math above).
 */
export function localToLatLon(
  x: number,
  z: number,
  anchorLat: number,
  anchorLon: number,
): { lat: number; lon: number } {
  const cosLat = Math.cos((anchorLat * Math.PI) / 180);
  const east = x / cosLat;
  const north = -z;
  const mercX = lonToMercX(anchorLon) + east;
  const mercY = latToMercY(anchorLat) + north;
  const lon = (mercX / WEB_MERCATOR_RADIUS) * (180 / Math.PI);
  const lat = (2 * Math.atan(Math.exp(mercY / WEB_MERCATOR_RADIUS)) - Math.PI / 2) * (180 / Math.PI);
  return { lat, lon };
}

export function createGroundLayer(options: GroundLayerOptions): GroundLayer {
  const { lat: anchorLat, lon: anchorLon, zoom } = options;
  const radius =
    options.radiusMeters ?? DEFAULT_RADIUS[zoom] ?? (zoom >= 17 ? 700 : 2000);
  const template = options.tileTemplate ?? OSM_TILE_TEMPLATE;

  const group = new THREE.Group();
  group.name = 'osm-ground';

  const cosLat = Math.cos((anchorLat * Math.PI) / 180);
  const mercTileSize = tileWorldSize(zoom); // Web-Mercator metres per tile edge
  // True ground metres per tile: east-west shrinks by cos(lat).
  const tileEast = mercTileSize * cosLat;
  const tileNorth = mercTileSize;

  interface LiveTile {
    mesh: THREE.Mesh;
    material: THREE.MeshBasicMaterial;
    coord: TileCoord;
  }
  /** Live tiles keyed by "x/y" (zoom is fixed per layer instance). */
  const tiles = new Map<string, LiveTile>();
  const jobs = new Set<Promise<unknown>>();
  const placeholderColor = options.placeholderColor ?? 0x8a8f94;

  const geometry = new THREE.PlaneGeometry(1, 1);
  // PlaneGeometry is in the XY plane; rotate flat onto the ground.
  geometry.rotateX(-Math.PI / 2);

  function createTile(tx: number, ty: number): void {
    const coord: TileCoord = {
      z: zoom,
      x: clampTileX(tx, zoom),
      y: clampTileY(ty, zoom),
    };
    // Skip duplicate clamped tiles at the map's polar edges.
    if (coord.x !== tx || coord.y !== ty) return;
    const key = `${coord.x}/${coord.y}`;
    if (tiles.has(key)) return;

    // Tile centre: convert the tile index back to lon/lat, then to local
    // metres via the standard Web-Mercator projection relative to the anchor.
    // (Direct (tx+0.5)*tileSize arithmetic is wrong: tile-x is measured from
    // lon -180°, so the 2^z/2 term matters — it caused a ~19,400 km offset.)
    const R = (mercTileSize * Math.pow(2, zoom)) / (2 * Math.PI);
    const centreLon = (((tx + 0.5) / Math.pow(2, zoom)) * 360) - 180;
    // Inverse slippy-map: tile-y fraction -> mercator angle -> latitude.
    const yMerc = (1 - (2 * (ty + 0.5)) / Math.pow(2, zoom)) * Math.PI;
    const clat = (Math.atan(Math.sinh(yMerc)) * 180) / Math.PI;
    const east = R * ((centreLon * Math.PI) / 180 - (anchorLon * Math.PI) / 180);
    const north = R * (Math.log(Math.tan(Math.PI / 4 + (clat * Math.PI) / 360)) - Math.log(Math.tan(Math.PI / 4 + (anchorLat * Math.PI) / 360)));
    const centreX = east * cosLat; // cos(lat) scale correction (x only)
    const centreZ = -north;

    const material = new THREE.MeshBasicMaterial({
      color: placeholderColor,
    });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = `tile-${zoom}-${coord.x}-${coord.y}`;
    mesh.position.set(centreX, 0, centreZ);
    mesh.scale.set(tileEast, 1, tileNorth);
    mesh.renderOrder = -10;
    group.add(mesh);
    tiles.set(key, { mesh, material, coord });

    const job = loadTileTexture(coord, template).then((tex) => {
      if (tex) {
        material.map = tex;
        material.color.set(0xffffff);
        material.needsUpdate = true;
      }
    });
    jobs.add(job);
    void job.finally(() => jobs.delete(job));
  }

  /** Camera (local metres) at the last update, for the half-tile throttle. */
  let lastX = Number.NaN;
  let lastZ = Number.NaN;

  function update(centerX: number, centerZ: number): void {
    // Throttle: ignore sub-half-tile movement (a tile is ~118 m at z17).
    if (!Number.isNaN(lastX)) {
      const dx = centerX - lastX;
      const dz = centerZ - lastZ;
      if (dx * dx + dz * dz < (tileEast / 2) * (tileEast / 2)) return;
    }
    lastX = centerX;
    lastZ = centerZ;

    const { lat, lon } = localToLatLon(centerX, centerZ, anchorLat, anchorLon);
    const centreTileX = lonToTileX(lon, zoom);
    const centreTileY = latToTileY(lat, zoom);

    // One extra tile of margin so edge tiles can be partially visible.
    const span = radius / tileEast + 1;
    const minTx = Math.floor(centreTileX - span);
    const maxTx = Math.ceil(centreTileX + span);
    const minTy = Math.floor(centreTileY - span / cosLat);
    const maxTy = Math.ceil(centreTileY + span / cosLat);

    const needed = new Set<string>();
    for (let ty = minTy; ty <= maxTy; ty++) {
      for (let tx = minTx; tx <= maxTx; tx++) {
        const coordX = clampTileX(tx, zoom);
        const coordY = clampTileY(ty, zoom);
        if (coordX !== tx || coordY !== ty) continue;
        const key = `${coordX}/${coordY}`;
        needed.add(key);
        if (!tiles.has(key)) createTile(tx, ty);
      }
    }

    // Dispose tiles that fell outside the streamed set. Geometry is shared —
    // dispose materials only; textures stay in the shared LRU cache.
    for (const [key, tile] of tiles) {
      if (needed.has(key)) continue;
      group.remove(tile.mesh);
      tile.material.dispose();
      tiles.delete(key);
    }
  }

  // Initial coverage around the anchor (local origin).
  update(0, 0);

  return {
    group,
    get tileCount() {
      return tiles.size;
    },
    update,
    load: () => Promise.all([...jobs]).then(() => undefined),
    dispose: () => {
      for (const tile of tiles.values()) {
        // Texture cache is shared — do not dispose cached textures here.
        tile.material.dispose();
      }
      tiles.clear();
      jobs.clear();
      geometry.dispose();
      group.removeFromParent();
    },
  };
}
