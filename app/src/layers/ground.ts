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
  17: 600,
  18: 300,
};

export interface GroundLayer {
  /** Group containing the tile meshes; add to the scene, position at origin. */
  group: THREE.Group;
  /** Number of tile meshes created. */
  tileCount: number;
  /** Loads all tile textures; resolves when every tile finished or failed. */
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

export function createGroundLayer(options: GroundLayerOptions): GroundLayer {
  const { lat: anchorLat, lon: anchorLon, zoom } = options;
  const radius =
    options.radiusMeters ?? DEFAULT_RADIUS[zoom] ?? (zoom >= 17 ? 600 : 2000);
  const template = options.tileTemplate ?? OSM_TILE_TEMPLATE;

  const group = new THREE.Group();
  group.name = 'osm-ground';

  const cosLat = Math.cos((anchorLat * Math.PI) / 180);
  const mercTileSize = tileWorldSize(zoom); // Web-Mercator metres per tile edge
  // True ground metres per tile: east-west shrinks by cos(lat).
  const tileEast = mercTileSize * cosLat;
  const tileNorth = mercTileSize;

  // Anchor point in fractional tile space and in mercator metres.
  const anchorTileX = lonToTileX(anchorLon, zoom);
  const anchorTileY = latToTileY(anchorLat, zoom);

  // Range of tiles to cover the radius (with one extra tile of margin so the
  // edge tiles can be partially visible without gaps at the rim).
  const tileSpan = radius / tileEast + 1;
  const minTx = Math.floor(anchorTileX - tileSpan);
  const maxTx = Math.ceil(anchorTileX + tileSpan);
  const minTy = Math.floor(anchorTileY - tileSpan / cosLat);
  const maxTy = Math.ceil(anchorTileY + tileSpan / cosLat);

  const geometry = new THREE.PlaneGeometry(1, 1);
  // PlaneGeometry is in the XY plane; rotate flat onto the ground.
  geometry.rotateX(-Math.PI / 2);

  const jobs: Array<Promise<unknown>> = [];
  let tileCount = 0;

  for (let ty = minTy; ty <= maxTy; ty++) {
    for (let tx = minTx; tx <= maxTx; tx++) {
      const coord: TileCoord = {
        z: zoom,
        x: clampTileX(tx, zoom),
        y: clampTileY(ty, zoom),
      };
      // Skip duplicate clamped tiles at the map's polar edges.
      if (coord.x !== tx || coord.y !== ty) continue;

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
        color: options.placeholderColor ?? 0x8a8f94,
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.name = `tile-${zoom}-${coord.x}-${coord.y}`;
      mesh.position.set(centreX, 0, centreZ);
      mesh.scale.set(tileEast, 1, tileNorth);
      mesh.renderOrder = -10;
      group.add(mesh);
      tileCount++;

      jobs.push(
        loadTileTexture(coord, template).then((tex) => {
          if (tex) {
            material.map = tex;
            material.color.set(0xffffff);
            material.needsUpdate = true;
          }
        }),
      );
    }
  }

  return {
    group,
    tileCount,
    load: () => Promise.all(jobs).then(() => undefined),
    dispose: () => {
      for (const child of group.children) {
        const mesh = child as THREE.Mesh;
        const mat = mesh.material as THREE.MeshBasicMaterial | undefined;
        // Texture cache is shared — do not dispose cached textures here.
        mat?.dispose();
      }
      geometry.dispose();
      group.removeFromParent();
    },
  };
}
