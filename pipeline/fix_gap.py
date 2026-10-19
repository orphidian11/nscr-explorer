"""Fix the 4 km alignment gap (s +1280 -> +5277) using real OSM corridor pieces.

The DXF centerline breaks at s +1280 (xref gap); OSM's NSCR construction line
covers Bicutan->gap-start and resumes south of FTI, but is itself disconnected
across the middle. Strategy:
  1. DXF points up to the gap start (s <= 1250)
  2. OSM component A (connected to the DXF end) for its real extent
  3. Cubic Hermite bridge between component A's end and component B's start,
     with tangents from each component's real end azimuth
  4. OSM component B south of FTI
  5. DXF points from s >= 5277 northward
Output: pipeline/alignment_extended_v2.json (same schema as v1).
"""
import json, math

E0, N0 = 504743.75, 1602372.38
TUX, TUZ = -0.474, -0.881  # along-axis unit at Bicutan (az ~ -28.3 deg from N)
B_LAT, B_LON = 14.488419, 121.045368  # scene anchor WGS84

def dm(a, b):
    pa = (a["lat"], a["lon"]) if isinstance(a, dict) else a
    pb = (b["lat"], b["lon"]) if isinstance(b, dict) else b
    return math.hypot((pa[0]-pb[0])*111000, (pa[1]-pb[1])*111320*math.cos(math.radians(14.5)))

# --- load DXF-derived points (v1) with their s ---
v1 = json.load(open(r"E:\NSCR\pipeline\alignment_extended.json"))["points"]
def to_local_wgs84(lat, lon):
    # WGS84 -> local metres relative to the anchor (same math as ground.ts, inverse)
    dlat = lat - B_LAT
    dlon = lon - B_LON
    north = dlat * 110540
    east = dlon * 111320 * math.cos(math.radians(B_LAT))
    return (east, -north)
def s_of_local(x, z):
    return x * TUX + z * TUZ

v1_s = []
for p in v1:
    x, z = p[0] - E0, -(p[1] - N0)
    v1_s.append((s_of_local(x, z), p))

# --- OSM components ---
osm = json.load(open(r"E:\NSCR\pipeline\osm_rail.json"))
ways = [e for e in osm["elements"] if e["type"] == "way" and len(e.get("geometry", [])) >= 2
        and e.get("tags", {}).get("railway") in ("rail", "construction", "abandoned", "disused")
        and e.get("tags", {}).get("service") != "crossover"
        and e.get("tags", {}).get("railway") != "light_rail"]
# components by endpoint connectivity
parent = {}
def key(p): return (round(p["lat"], 6), round(p["lon"], 6))
def find(k):
    parent.setdefault(k, k)
    while parent[k] != k:
        parent[k] = parent[parent[k]]
        k = parent[k]
    return k
def union(a, b):
    ra, rb = find(a), find(b)
    if ra != rb: parent[ra] = rb
comps = {}
for w in ways:
    g = w["geometry"]
    keys = [key(g[0]), key(g[-1])]
    for k in keys: find(k)
    union(keys[0], keys[1])
    comps.setdefault(find(key(g[0])), []).extend(g)
def key(p): return (round(p["lat"], 6), round(p["lon"], 6))

# For each component: dedupe consecutive points, convert to local, compute s-range
comp_info = []
for root, g in comps.items():
    pts = [g[0]]
    for p in g[1:]:
        if dm(p, pts[-1]) > 1.0:
            pts.append(p)
    local = [to_local_wgs84(p["lat"], p["lon"]) for p in pts]
    ss = [s_of_local(x, z) for x, z in local]
    comp_info.append({"pts_local": local, "pts_wgs": pts, "s_min": min(ss), "s_max": max(ss),
                      "n": len(pts)})
comp_info.sort(key=lambda c: c["s_min"])
for c in comp_info:
    print(f"component: n={c['n']:4d}  s {c['s_min']:+7.0f} .. {c['s_max']:+7.0f}  length {sum(dm(a,b) for a,b in zip(c['pts_wgs'], c['pts_wgs'][1:])):.0f} m")

# --- assemble ---
GAP_START = 1250.0
GAP_END = 5277.0
out_s = []
result = []  # (s, local_x, local_z)

# 1) DXF points s <= GAP_START
for s, p in sorted(v1_s, key=lambda t: t[0]):
    if s <= GAP_START:
        x, z = p[0] - E0, -(p[1] - N0)
        result.append((s, x, z))

# 2/3/4) OSM components + hermite bridges, northward
last_s = GAP_START
last_pt = (result[-1][1], result[-1][2])
last_tan = None

def tangent_at(c, idx, step=3):
    i0, i1 = max(0, idx - step), min(len(c["pts_local"]) - 1, idx + step)
    dx = c["pts_local"][i1][0] - c["pts_local"][i0][0]
    dz = c["pts_local"][i1][1] - c["pts_local"][i0][1]
    L = math.hypot(dx, dz) or 1.0
    return (dx / L, dz / L)

# OSM components: keep only points INSIDE the gap window (s in [GAP_START, GAP_END]).
# Everything outside is already covered by the DXF centerline — letting it through
# duplicates the corridor as a laterally-offset parallel copy (the "veer" bug).
gap_comps = []
for c in comp_info:
    pts = [(i, s_of_local(*p)) for i, p in enumerate(c["pts_local"])]
    in_gap = [(i, s) for i, s in pts if GAP_START <= s <= GAP_END]
    if len(in_gap) >= 2:
        gap_comps.append((c, in_gap))
# Use ONLY the largest component — it covers the whole gap on its own; the
# smaller overlapping ones are parallel/duplicate mappings that zigzag the path.
gap_comps.sort(key=lambda t: -(t[0]["n"]))
print("gap components:", [(f"s {min(s for _,s in g):.0f}..{max(s for _,s in g):.0f} n={len(g)}",) for _, g in gap_comps])
gap_comps = gap_comps[:1]
print("using single largest component")

last_s = GAP_START
last_pt = (result[-1][1], result[-1][2])
last_tan = (TUX, TUZ)

def tangent_at(c, idx, step=3):
    i0, i1 = max(0, idx - step), min(len(c["pts_local"]) - 1, idx + step)
    dx = c["pts_local"][i1][0] - c["pts_local"][i0][0]
    dz = c["pts_local"][i1][1] - c["pts_local"][i0][1]
    L = math.hypot(dx, dz) or 1.0
    return (dx / L, dz / L)

def hermite_to(target, target_tan_out):
    global last_s, last_pt, last_tan
    gap_len = math.dist(last_pt, target)
    if gap_len < 20:
        return
    t0 = last_tan
    t1 = (-target_tan_out[0], -target_tan_out[1])
    n_bridge = max(int(gap_len / 10), 8)
    p0 = last_pt; p3 = target
    p1 = (p0[0] + t0[0] * gap_len / 3, p0[1] + t0[1] * gap_len / 3)
    p2 = (p3[0] + t1[0] * gap_len / 3, p3[1] + t1[1] * gap_len / 3)
    for k in range(1, n_bridge + 1):
        t = k / n_bridge
        h = lambda a, b, cc, d, t: ((1-t)**3*a + 3*(1-t)**2*t*b + 3*(1-t)*t*t*cc + t**3*d)
        result.append((last_s + gap_len * t, h(p0[0], p1[0], p2[0], p3[0], t), h(p0[1], p1[1], p2[1], p3[1], t)))
    last_s += gap_len
    last_pt = target
    print(f"hermite bridge: {gap_len:.0f} m (s -> {last_s:+.0f})")

for c, in_gap in gap_comps:
    # component chain: order pts by cumulative distance from the in-gap end
    i0 = in_gap[0][0]
    # orient: walk from in_gap[0] toward in_gap[-1] along index order or reverse
    if in_gap[-1][0] > in_gap[0][0]:
        idxs = [i for i, _ in in_gap]
    else:
        idxs = [i for i, _ in reversed(in_gap)]
    # hermite from current position to the component entry
    c_entry = c["pts_local"][idxs[0]]
    hermite_to(c_entry, tangent_at(c, idxs[0]))
    # component points (real geometry)
    prev_i = idxs[0]
    for i in idxs[1:]:
        x, z = c["pts_local"][i]
        last_s += math.dist(c["pts_local"][prev_i], (x, z))
        last_pt = (x, z)
        result.append((last_s, x, z))
        prev_i = i
    last_tan = tangent_at(c, idxs[-1])

# 5) DXF points s >= 5277
for s, p in sorted(v1_s, key=lambda t: t[0]):
    if s >= GAP_END:
        x, z = p[0] - E0, -(p[1] - N0)
        if not result or s > result[-1][0]:
            result.append((s, x, z))

# sort, dedupe, clamp to the +/-4.5 km window, then drop jitter
result.sort(key=lambda t: t[0])
result = [r for r in result if -4500 <= r[0] <= 4500]
clean = [result[0]]
for r in result[1:]:
    if r[0] - clean[-1][0] >= 5:
        clean.append(r)
# sanity: no s-jump over 60 m (would signal a bad splice)
jumps = [(clean[i][0], clean[i+1][0] - clean[i][0]) for i in range(len(clean)-1) if clean[i+1][0] - clean[i][0] > 60]
for s, j in jumps: print(f"WARN s-jump {j:.0f} m at s={s:.0f}")
if not jumps: print("no s-jumps > 60 m — splice continuous")

# uniform resample every 10 m along s (linear interp), so deck segments are even
res = []
target = clean[0][0]
i = 0
while target <= clean[-1][0] and i < len(clean) - 1:
    while i < len(clean) - 2 and clean[i+1][0] < target:
        i += 1
    s0, x0, z0 = clean[i]
    s1, x1, z1 = clean[i+1]
    t = (target - s0) / max(s1 - s0, 1e-6)
    res.append((target, x0 + (x1-x0)*t, z0 + (z1-z0)*t))
    target += 10
clean = res
print("resampled:", len(clean), "pts @10 m")

# convert to manifest schema
pts = [[round(E0 + x, 2), round(N0 - z, 2)] for (s, x, z) in clean]
out = {"points": pts, "sample_spacing_m": 10, "range_m": [round(clean[0][0]), round(clean[-1][0])],
       "gaps": [], "notes": "v2: 4 km xref gap bridged with real OSM NSCR construction-way geometry "
       "(components A/B) + Hermite curve anchored to both real end tangents; OSM data (c) OpenStreetMap contributors"}
json.dump(out, open(r"E:\NSCR\pipeline\alignment_extended_v2.json", "w"), indent=1)
print("v2 points:", len(pts), "| s range:", out["range_m"])
