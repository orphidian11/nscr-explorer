/**
 * tiles.ts — Web-Mercator (slippy tile) math + texture loading for the OSM
 * raster ground layer.
 *
 * Reference frame (matches the NSCR viewer's local ENU frame):
 *   +x = east (metres), +z = -north (metres), +y = up.
 *
 * Positions are computed in Web-Mercator metre space, then the east axis is
 * multiplied by cos(anchorLat) so local units are true ground metres at the
 * anchor latitude. At Bicutan (14.48748°N) cos(lat) ≈ 0.9682.
 */

import * as THREE from 'three';

export const OSM_TILE_TEMPLATE = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';

/** Fallback style (CARTO Voyager) — free, CORS-enabled, generous caching. */
export const CARTO_VOYAGER_TILE_TEMPLATE =
  'https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png';

/**
 * Required attribution. `groundAttribution` must be displayed by the UI
 * whenever the ground layer is visible (OSM tile usage policy:
 * https://operations.osmfoundation.org/policies/tiles/).
 */
export const OSM_TILE_ATTRIBUTION =
  '© OpenStreetMap contributors (tiles: openstreetmap.org)';
export const CARTO_TILE_ATTRIBUTION =
  '© OpenStreetMap contributors © CARTO';

/** Web-Mercator earth radius used by the slippy-map projection (metres). */
export const WEB_MERCATOR_RADIUS = 6378137;

/** Full equatorial circumference in Web-Mercator metres. */
export const WEB_MERCATOR_CIRCUMFERENCE = 2 * Math.PI * WEB_MERCATOR_RADIUS;

export const TILE_SIZE_PX = 256;

export interface TileCoord {
  z: number;
  x: number;
  y: number;
}

/** Fractional tile-x for a longitude at zoom `z` (slippy-map formula). */
export function lonToTileX(lon: number, z: number): number {
  return ((lon + 180) / 360) * Math.pow(2, z);
}

/** Fractional tile-y for a latitude at zoom `z` (slippy-map formula). */
export function latToTileY(lat: number, z: number): number {
  const latRad = (lat * Math.PI) / 180;
  return (
    ((1 -
      Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) *
    Math.pow(2, z)
  );
}

/** Web-Mercator easting (metres) for a longitude. */
export function lonToMercX(lon: number): number {
  return WEB_MERCATOR_RADIUS * ((lon * Math.PI) / 180);
}

/** Web-Mercator northing (metres) for a latitude. */
export function latToMercY(lat: number): number {
  // Clamped so latitudes beyond ±85.0511° don't produce Infinity.
  const clampedRad =
    (Math.max(-85.05112878, Math.min(85.05112878, lat)) * Math.PI) / 180;
  return (
    WEB_MERCATOR_RADIUS *
    Math.log(Math.tan(Math.PI / 4 + clampedRad / 2))
  );
}

/**
 * Side length of one tile in Web-Mercator metres at zoom `z`.
 * Multiply by cos(anchorLat) for true ground metres east-west.
 */
export function tileWorldSize(z: number): number {
  return WEB_MERCATOR_CIRCUMFERENCE / Math.pow(2, z);
}

/** Clamp tile indices to the valid range for the zoom level. */
export function clampTileX(x: number, z: number): number {
  const max = Math.pow(2, z) - 1;
  return Math.max(0, Math.min(max, Math.floor(x)));
}

/** Clamp tile-y to the valid range for the zoom level (no wrap). */
export function clampTileY(y: number, z: number): number {
  const max = Math.pow(2, z) - 1;
  return Math.max(0, Math.min(max, Math.floor(y)));
}

export function tileUrl(coord: TileCoord, template = OSM_TILE_TEMPLATE): string {
  return template
    .replace('{z}', String(coord.z))
    .replace('{x}', String(coord.x))
    .replace('{y}', String(coord.y))
    .replace('{r}', '');
}

/**
 * Texture cache shared by all ground layers, keyed by `z/x/y@template`.
 * Textures are fetched as blobs (CORS-safe) and never evicted for the
 * session — the tile sets used here are small (tens of tiles).
 */
const textureCache = new Map<string, THREE.Texture>();

export function cachedTextureCount(): number {
  return textureCache.size;
}

export async function loadTileTexture(
  coord: TileCoord,
  template: string = OSM_TILE_TEMPLATE,
): Promise<THREE.Texture | null> {
  const key = `${coord.z}/${coord.x}/${coord.y}@${template}`;
  const cached = textureCache.get(key);
  if (cached) return cached;

  try {
    const res = await fetch(tileUrl(coord, template), {
      // OSM policy: a descriptive User-Agent cannot be set from browsers, but
      // the Referer does that job; keep the request cache-friendly.
      headers: { Accept: 'image/png,image/*;q=0.8' },
    });
    if (!res.ok) {
      console.warn(`[tiles] tile ${key} HTTP ${res.status}`);
      return null;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const texture = await new Promise<THREE.Texture | null>((resolve) => {
      new THREE.TextureLoader().load(
        url,
        (tex) => resolve(tex),
        undefined,
        (err) => {
          console.warn(`[tiles] tile ${key} decode failed`, err);
          resolve(null);
        },
      );
    });
    URL.revokeObjectURL(url);
    if (!texture) return null;
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.minFilter = THREE.LinearFilter;
    texture.generateMipmaps = false;
    textureCache.set(key, texture);
    return texture;
  } catch (err) {
    console.warn(`[tiles] tile ${key} fetch failed`, err);
    return null;
  }
}
