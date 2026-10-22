"""alignment_v3: full NSCR mainline chain (Sucat -> past EDSA), OSM gap splicing."""
import json, math
import ezdxf, numpy as np
from pyproj import Transformer

DXF = 'E:/NSCR/pipeline/dxf_align/X_DD_NSRP_Main_Alignment.dxf'
OUT = 'E:/NSCR/pipeline/alignment_v3.json'
E0, N0 = 504743.75, 1602372.38  # Bicutan s=0 (PRS92 PTM)
tr = Transformer.from_crs('EPSG:4326', 'EPSG:3123', always_xy=True)
def w2p(lon, lat): return tr.transform(lon, lat)

# --- 1) chain the mainline (explicit ORDER, proven in resample_alignment_v3) ---
doc = ezdxf.readfile(DXF)
def densify(e, max_chord=10.0):
    pts = [(float(p[0]), float(p[1])) for p in e.get_points()]
    bul = [float(p[3]) if len(p) > 3 else 0.0 for p in e.get_points()]
    out = [pts[0]]
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]; x2, y2 = pts[i + 1]; b = bul[i]
        chord = math.hypot(x2 - x1, y2 - y1)
        if chord < 1e-9: continue
        if abs(b) < 1e-9:
            n = max(1, int(chord / max_chord))
            for k in range(1, n + 1):
                t = k / n
                out.append((x1 + t * (x2 - x1), y1 + t * (y2 - y1)))
            continue
        th = 4 * math.atan(b); r = chord / (2 * math.sin(abs(th) / 2))
        d = r * math.cos(th / 2) * (1 if th > 0 else -1)
        nx, ny = -(y2 - y1) / chord, (x2 - x1) / chord
        cx, cy = (x1 + x2) / 2 + d * nx, (y1 + y2) / 2 + d * ny
        a1 = math.atan2(y1 - cy, x1 - cx); steps = max(2, int(abs(th) * r / 1.0))
        for k in range(1, steps):
            a = a1 + th * k / steps
            out.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        out.append(pts[i + 1])
    return out

ORDER = [1573869.82, 1583742.72, 1601933.66, 1602254.38, 1602441.98, 1603305.54,
         1607108.19, 1608122.35, 1612805.84, 1613088.36, 1613767.47, 1613810.33]
ents = {}
for e in doc.modelspace().query('LWPOLYLINE'):
    if e.dxf.layer == 'S_NSRP_Center Line':
        p = [(float(q[0]), float(q[1])) for q in e.get_points()]
        if len(p) < 2: continue
        k = round(min(q[1] for q in p), 6)
        if any(abs(k - o) < 2.0 for o in ORDER): ents[k] = e
assert len(ents) == len(ORDER), (len(ents), len(ORDER))

def dist(p, q): return math.hypot(p[0] - q[0], p[1] - q[1])
chain = []; prev_end = None; jgaps = []
for o in ORDER:
    k = min(ents, key=lambda k: abs(k - o))
    d = densify(ents[k])
    if prev_end is not None and dist(d[0], prev_end) > dist(d[-1], prev_end):
        d = d[::-1]
    if prev_end is not None:
        g = dist(d[0], prev_end)
        if g > 5.0:
            jgaps.append({'from': prev_end, 'to': d[0], 'size': g})
    chain.extend(d); prev_end = chain[-1]

cum = np.concatenate([[0.0], np.cumsum([dist(chain[i - 1], chain[i]) for i in range(1, len(chain))])])
chain_np = np.array(chain)
bi = int(np.argmin(np.hypot(chain_np[:, 0] - E0, chain_np[:, 1] - N0)))
print(f'chain: {len(chain)} pts, {cum[-1]:.0f} m, Bicutan snap err {dist(chain[bi], (E0, N0)):.2f} m')
for g in jgaps:
    print(f"gap {g['size']:.1f} m at {tuple(round(v,1) for v in g['from'])} -> {tuple(round(v,1) for v in g['to'])}")

bx, by = w2p(121.045368, 14.488419)
print('pyproj WGS84->PTM Bicutan check: dE %.2f dN %.2f' % (bx - E0, by - N0))

# --- 2) OSM components in PTM ---
osm = json.load(open('osm_rail.json'))
ways = [e for e in osm['elements'] if e['type'] == 'way' and len(e.get('geometry', [])) >= 2
        and e.get('tags', {}).get('railway') in ('rail', 'construction', 'abandoned', 'disused')
        and e.get('tags', {}).get('service') != 'crossover']
parent = {}
def key(p): return (round(p['lat'], 6), round(p['lon'], 6))
def find(k):
    parent.setdefault(k, k)
    while parent[k] != k: parent[k] = parent[parent[k]]; k = parent[k]
    return k
comps = {}
for w in ways:
    g = w['geometry']; a, b = key(g[0]), key(g[-1]); find(a); find(b)
    if find(a) != find(b): parent[find(a)] = find(b)
    comps.setdefault(find(key(g[0])), []).append(g)
comp_pts = []
for root, gs in comps.items():
    seq = []
    for g in gs: seq.extend(g)
    pts = []; prev_ll = None
    for p in seq:
        if prev_ll is not None and abs(p['lat'] - prev_ll[0]) * 110540 < 1.0 \
           and abs(p['lon'] - prev_ll[1]) * 111320 * math.cos(math.radians(14.49)) < 1.0:
            continue
        E, N = w2p(p['lon'], p['lat']); pts.append((E, N)); prev_ll = (p['lat'], p['lon'])
    if len(pts) >= 2: comp_pts.append(pts)
print('OSM components:', len(comp_pts))

def tangent(idx, step=3):
    i0, i1 = max(0, idx - step), min(len(chain) - 1, idx + step)
    dx, dz = chain[i1][0] - chain[i0][0], chain[i1][1] - chain[i0][1]
    L = math.hypot(dx, dz) or 1.0; return (dx / L, dz / L)

def hermite(p0, t0, p3, t3_out):
    L = math.dist(p0, p3)
    if L < 15: return []
    t1 = (-t3_out[0], -t3_out[1])
    p1 = (p0[0] + t0[0] * L / 3, p0[1] + t0[1] * L / 3)
    p2 = (p3[0] + t1[0] * L / 3, p3[1] + t1[1] * L / 3)
    n = max(int(L / 5), 6); out = []
    for k in range(1, n + 1):
        t = k / n
        h = lambda a, b, c, d: ((1-t)**3*a + 3*(1-t)**2*t*b + 3*(1-t)*t*t*c + t**3*d)
        out.append((h(p0[0], p1[0], p2[0], p3[0]), h(p0[1], p1[1], p2[1], p3[1])))
    return out

def seg_dist(P, A, B):
    ax, ay = A; bx, by = B; px, py = P
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / L2))
    return math.hypot(px - (ax + t * vx), py - (ay + t * vy))

# --- 3) assemble: DXF runs + splices at junction gaps ---
idx_bounds = []
for g in jgaps:
    iA = min(range(len(chain)), key=lambda i: dist(chain[i], g['from']))
    iB = min(range(len(chain)), key=lambda i: dist(chain[i], g['to']))
    idx_bounds.append((g, iA, iB))
cur = 0; plan = []
for g, iA, iB in idx_bounds:
    plan.append(('dxf', cur, iA)); plan.append(('gap', g, iA, iB)); cur = iB
plan.append(('dxf', cur, len(chain) - 1))

path = []; gaps_report = []
for item in plan:
    if item[0] == 'dxf':
        _, a, b = item
        for i in range(a, b + 1): path.append((chain[i][0], chain[i][1]))
        continue
    _, g, iA, iB = item
    size = g['size']
    pA = (chain[iA][0], chain[iA][1]); pB = (chain[iB][0], chain[iB][1])
    tA = tangent(iA); tB = tangent(iB)
    comp = None
    if size > 20.0:
        cands = []
        for ci, pts in enumerate(comp_pts):
            inwin = [(k, p) for k, p in enumerate(pts) if seg_dist(p, pA, pB) < 500.0]
            if len(inwin) >= 2: cands.append((len(inwin), ci, inwin))
        if cands:
            cands.sort(key=lambda t: -t[0])
            _, ci, inwin = cands[0]
            pts_all = comp_pts[ci]
            # order in-window points by a northward-constrained nearest-neighbour walk from
            # the entry (raw component index order is arbitrary; unconstrained NN wanders
            # into sidings/parallel ways)
            remaining = [p for _, p in inwin]
            comp = [min(remaining, key=lambda p: dist(p, pA))]
            remaining.remove(comp[0])
            while remaining:
                cand = [p for p in remaining if dist(p, comp[-1]) <= 400.0]
                if not cand: break
                nxt = min(cand, key=lambda p: dist(p, pB))
                if dist(nxt, pB) > dist(comp[-1], pB) + 50.0: break
                comp.append(nxt); remaining.remove(nxt)
            walk_len = sum(dist(a, b) for a, b in zip(comp, comp[1:]))
            if walk_len > max(2.5 * size, size + 300.0):
                print(f'  gap {size:.0f} m: OSM walk len {walk_len:.0f} m suspicious -> hermite fallback')
                comp = None
    if comp is not None:
        def comp_tan(i, step=3):
            aa = max(0, i - step); bb = min(len(comp) - 1, i + step)
            dx = comp[bb][0] - comp[aa][0]; dz = comp[bb][1] - comp[aa][1]
            L = math.hypot(dx, dz) or 1.0; return (dx / L, dz / L)
        p_cur = path[-1]
        entry = comp[0]
        if dist(p_cur, entry) > 15.0:
            path.extend(hermite(p_cur, tA, entry, comp_tan(0)))
        prev = comp[0]; prev_i = 0
        for j in range(1, len(comp)):
            p = comp[j]
            if dist(p, prev) > 60.0:
                path.extend(hermite(prev, comp_tan(prev_i), p, comp_tan(j)))
            else:
                path.append(p)
            prev = p; prev_i = j
        if dist(path[-1], pB) > 15.0:
            path.extend(hermite(path[-1], comp_tan(len(comp) - 1), pB, (-tB[0], -tB[1])))
        gaps_report.append({'size_m': round(size, 1), 'spliced': 'osm', 'osm_pts': len(comp)})
        print(f"gap {size:.0f} m: OSM {len(comp)} pts")
    else:
        path.extend(hermite(path[-1], tA, pB, (-tB[0], -tB[1])))
        gaps_report.append({'size_m': round(size, 1), 'spliced': 'hermite'})
        print(f"gap {size:.0f} m: hermite only")

# --- 4) s = cumulative arclength of the assembled path, 0 at Bicutan ---
dists = [0.0]
for i in range(1, len(path)):
    dists.append(dists[-1] + dist(path[i - 1], path[i]))
path_np = np.array(path)
bip = int(np.argmin(np.hypot(path_np[:, 0] - E0, path_np[:, 1] - N0)))
s = np.array(dists) - dists[bip]
print(f'assembled: {len(path)} pts, s range {s[0]:.1f}..{s[-1]:.1f}, Bicutan err '
      f'{dist(path[bip], (E0, N0)):.2f} m')
big = [(round(float(s[i]), 1), round(dist(path[i - 1], path[i]), 1))
       for i in range(1, len(path)) if dist(path[i - 1], path[i]) > 60.0]
print('holes >60 m in assembled path:', big if big else 'NONE')
expected_len = cum[-1] + sum(g['size'] for g in jgaps)
actual_len = dists[-1]
print(f'length check: assembled {actual_len:.0f} m vs expected {expected_len:.0f} m '
      f'({(actual_len-expected_len)/expected_len*100:+.1f}%)')

# --- 5) stations ---
def s_of_station(lon, lat):
    E, N = w2p(lon, lat)
    d = np.hypot(path_np[:, 0] - E, path_np[:, 1] - N); i = int(np.argmin(d))
    return float(s[i]), float(d[i])
stations = {'Bicutan': 0.0}
sucat_s = edsa_s = None
for name, lon, lat in [('Sucat', 121.0509333, 14.4521389),
                       ('Senate-DepEd(BUE)', 121.0261389, 14.5239),
                       ('EDSA', 121.0164972, 14.5417583)]:
    sv, d = s_of_station(lon, lat)
    stations[name] = round(sv, 1)
    if name == 'Sucat': sucat_s = sv
    if name == 'EDSA': edsa_s = sv
    print(f'{name}: s={sv:.1f} (perp offset {d:.0f} m)')

# --- 6) clip to Sucat-500 .. EDSA+2000, resample 10 m ---
lo, hi = sucat_s - 500.0, edsa_s + 2000.0
m = (s >= lo) & (s <= hi)
cs = s[m]; Es = path_np[m, 0]; Ns = path_np[m, 1]
ss = np.arange(math.ceil(cs[0] / 10) * 10, cs[-1], 10.0)
Ei = np.interp(ss, cs, Es); Ni = np.interp(ss, cs, Ns)
res = [[round(float(e), 3), round(float(n), 3)] for e, n in zip(Ei, Ni)]
gaps_out = []
for gr, (g, iA, iB) in zip(gaps_report, idx_bounds):
    sA = float(s[min(range(len(path)), key=lambda i: dist(path[i], g['from']))])
    sB = float(s[min(range(len(path)), key=lambda i: dist(path[i], g['to']))])
    gaps_out.append({'s': round(sA, 1), 'size_m': gr['size_m'],
                     'spliced': gr['spliced'], 's_end': round(sB, 1)})
out = {'points': res, 'sample_spacing_m': 10,
       'range_m': [round(float(ss[0])), round(float(ss[-1]))],
       'gaps': [g for g in gaps_out if lo <= g['s'] <= hi],
       'stations_s': stations,
       'notes': ('v3: mainline chain of 12 S_NSRP_Center Line LWPOLYLINEs (ORDER per '
                 'resample_alignment_v3.py) from X_DD_NSRP_Main_Alignment.dxf, densified to '
                 '<=10 m chords (bulge arcs at ~1 m), oriented S->N; s = cumulative arclength '
                 'of the assembled path, 0 at Bicutan (E 504743.75 N 1602372.38, PRS92 PTM / '
                 'EPSG:3123). Junction gaps >5 m spliced with real OSM NSCR rail/construction '
                 'geometry (osm_rail.json; single largest component within 500 m of the gap '
                 'chord, Hermite bridges anchored to DXF end tangents; gaps <20 m bridged '
                 'directly). WGS84->PTM via pyproj EPSG:3123. OSM data (c) OpenStreetMap '
                 'contributors.')}
json.dump(out, open(OUT, 'w'))
print('wrote', OUT, '| points', len(res), '| range', out['range_m'])
print('gaps in output:', json.dumps(out['gaps']))
