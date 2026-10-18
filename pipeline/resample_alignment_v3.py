"""Sample NSCR mainline centerline every 10 m, -4..+4 km from Bicutan (v3, explicit mainline chain)."""
import json, math
import ezdxf

DXF = 'E:/NSCR/pipeline/dxf_align/X_DD_NSRP_Main_Alignment.dxf'
OUT = 'E:/NSCR/pipeline/alignment_extended.json'
BICU = (504743.75, 1602372.38)

def dist(p, q): return math.hypot(p[0]-q[0], p[1]-q[1])

def densify(pl):
    pts = [(float(p[0]), float(p[1])) for p in pl.get_points()]
    bulges = [float(p[3]) if len(p) > 3 else 0.0 for p in pl.get_points()]
    out = [pts[0]]
    for i in range(len(pts)-1):
        x1, y1 = pts[i]; x2, y2 = pts[i+1]; b = bulges[i]
        if abs(b) < 1e-9:
            out.append(pts[i+1]); continue
        chord = math.hypot(x2-x1, y2-y1)
        if chord < 1e-9: continue
        theta = 4*math.atan(b)
        r = chord/(2*math.sin(abs(theta)/2))
        mx, my = (x1+x2)/2, (y1+y2)/2
        d = r*math.cos(theta/2)*(1 if theta > 0 else -1)
        nx, ny = -(y2-y1)/chord, (x2-x1)/chord
        cx, cy = mx+d*nx, my+d*ny
        a1 = math.atan2(y1-cy, x1-cx)
        steps = max(2, int(abs(theta)*r/1.0))
        for k in range(1, steps):
            a = a1 + theta*k/steps
            out.append((cx+r*math.cos(a), cy+r*math.sin(a)))
        out.append(pts[i+1])
    return out

# index polylines by (layer, Nmin) as in the diagnostic
idx = {}
for e in ezdxf.readfile(DXF).modelspace().query('LWPOLYLINE'):
    if e.dxf.layer in ('S_NSRP_Center Line', 'S_NSCR TRACKS',
                       '001_Line Center (N1)', '002__Line_Center km(Ver 3.0.0)'):
        pts = [(float(p[0]), float(p[1])) for p in e.get_points()]
        key = round(min(p[1] for p in pts), 6)
        idx.setdefault((e.dxf.layer, key), []).append(pts)

def grab(layer, nmin):
    for (lay, k), v in idx.items():
        if lay == layer and abs(k-nmin) < 2.0:
            return v[0]
    raise KeyError((layer, nmin))

# Explicit mainline chain, south -> north (from corridor diagnostic).
# nmin values from diag: 14:1573869.8, 20:1583742.7, 27:1601933.7, 31:1602254.4,
# 30:1602441.98, 13:1603305.5, 2:1607108.2, 18:1608122.4, 25:1612805.8,
# 26:1613088.4, 19:1613767.5, 12:1613810.3
ORDER = [('S_NSRP_Center Line', 1573869.82), ('S_NSRP_Center Line', 1583742.72),
         ('S_NSRP_Center Line', 1601933.66), ('S_NSRP_Center Line', 1602254.38),
         ('S_NSRP_Center Line', 1602441.98), ('S_NSRP_Center Line', 1603305.54),
         ('S_NSRP_Center Line', 1607108.19), ('S_NSRP_Center Line', 1608122.35),
         ('S_NSRP_Center Line', 1612805.84), ('S_NSRP_Center Line', 1613088.36),
         ('S_NSRP_Center Line', 1613767.47), ('S_NSRP_Center Line', 1613810.33)]
chain = []
gaps = []
bridge_marks = []
prev_end = None
for lay, nmin in ORDER:
    raw = grab(lay, nmin)
    dens = None
    # densify via ezdxf entity: rebuild from raw + recompute bulges? simpler: re-find entity
    for e in ezdxf.readfile(DXF).modelspace().query('LWPOLYLINE'):
        if e.dxf.layer == lay:
            p0 = (float(e.get_points()[0][0]), float(e.get_points()[0][1]))
            if abs(min(float(p[1]) for p in e.get_points()) - nmin) < 2.0:
                dens = densify(e); break
    # orient: start nearer previous end (or northernmost-first default)
    if prev_end is not None and dist(dens[0], prev_end) > dist(dens[-1], prev_end):
        dens = dens[::-1]
    if prev_end is not None:
        g = dist(dens[0], prev_end)
        if g > 5.0:
            bridge_marks.append((len(chain), g, prev_end, dens[0]))  # chain index where bridge lands
            gaps.append({'bridge_start_E': round(prev_end[0], 2), 'bridge_start_N': round(prev_end[1], 2),
                         'bridge_end_E': round(dens[0][0], 2), 'bridge_end_N': round(dens[0][1], 2)})
    chain.extend(dens)
    prev_end = chain[-1]

cum = [0.0]
for i in range(1, len(chain)):
    cum.append(cum[-1] + dist(chain[i-1], chain[i]))
bi = min(range(len(chain)), key=lambda i: dist(chain[i], BICU))
s0 = cum[bi]
print('chain pts', len(chain), 'length', round(cum[-1], 1))
print('Bicutan vertex dist', round(dist(chain[bi], BICU), 2), 's0', round(s0, 1))
print('south end', tuple(round(v, 1) for v in chain[0]), 'north end', tuple(round(v, 1) for v in chain[-1]))
print('bridges (linear, from->to):')
for g in gaps: print('  ', g)

# gaps only at polyline junctions (bridges), not intra-polyline long segments
gap_list = []
for k, size, p_from, p_to in bridge_marks:
    gap_list.append({'s_start': round(cum[k-1]-s0, 1), 's_end': round(cum[k]-s0, 1),
                     'size_m': round(size, 1),
                     'from': [round(p_from[0], 2), round(p_from[1], 2)],
                     'to': [round(p_to[0], 2), round(p_to[1], 2)]})
print('gap list (s rel. Bicutan):')
for g in gap_list: print('  ', g)

def sample_at(s):
    if s < cum[0] or s > cum[-1]: return None
    lo, hi = 0, len(cum)-1
    while lo < hi-1:
        mid = (lo+hi)//2
        if cum[mid] <= s: lo = mid
        else: hi = mid
    t = (s-cum[lo])/(cum[hi]-cum[lo]) if cum[hi] > cum[lo] else 0
    return [round(chain[lo][0]+t*(chain[hi][0]-chain[lo][0]), 3),
            round(chain[lo][1]+t*(chain[hi][1]-chain[lo][1]), 3)]

pts, s = [], s0-4000.0
while s <= s0+4000.0+1e-9:
    pts.append(sample_at(s)); s += 10.0
n_valid = sum(1 for p in pts if p is not None)
null_runs, run = [], None
for i, p in enumerate(pts):
    sh = -4000+10*i
    if p is None:
        run = [sh, sh] if run is None else [run[0], sh]
    else:
        if run: null_runs.append(run); run = None
if run: null_runs.append(run)
print('samples', len(pts), 'valid', n_valid, 'null s-ranges', null_runs)

# gap summary as {s,size_m}
gaps_out = [{'s': g['s_start'], 'size_m': g['size_m']} for g in gap_list]

# verification: Sucat via PTM (EPSG:3123) forward approximation
def tm_forward(lon, lat, lon0=121.0, k0=0.99995, fe=500000.0, fn=0.0,
               a=6378388.0, rf=297.0):  # PRS92 uses international-ish ellipsoid; approx
    f = 1/rf; e2 = 2*f - f*f
    ph = math.radians(lat); dl = math.radians(lon-lon0)
    N = a/math.sqrt(1-e2*math.sin(ph)**2)
    T = math.tan(ph)**2; C = e2/(1-e2)*math.cos(ph)**2
    A = math.cos(ph)*dl
    M = a*((1 - e2/4 - 3*e2**2/64 - 5*e2**3/256)*ph
           - (3*e2/8 + 3*e2**2/32 + 45*e2**3/1024)*math.sin(2*ph)
           + (15*e2**2/256 + 45*e2**3/1024)*math.sin(4*ph)
           - (35*e2**3/3072)*math.sin(6*ph))
    E = fe + k0*N*(A + (1-T+C)*A**3/6 + (5-18*T+T*T+72*C-58*e2)*A**5/120)
    Nn = fn + k0*(M + N*math.tan(ph)*(A*A/2 + (5-T+9*C+4*C*C)*A**4/24
                  + (61-58*T+T*T+600*C-330*e2)*A**6/720))
    return E, Nn
sucat = tm_forward(121.05093, 14.45214)
print('Sucat approx (E,N)', tuple(round(v, 1) for v in sucat))
hits = [(cum[i]-s0, dist(chain[i], sucat)) for i in range(len(chain)) if dist(chain[i], sucat) < 500]
if hits:
    best = min(hits, key=lambda h: h[1])
    print('Sucat nearest s =', round(best[0], 1), 'offset', round(best[1], 1))
print('Bicutan s =', round(min(cum[i]-s0 for i in range(len(chain)) if dist(chain[i], BICU) < 100), 1))

out = {
    'points': pts, 'sample_spacing_m': 10, 'range_m': [-4000, 4000],
    'gaps': gaps_out,
    'notes': ('Mainline chain of S_NSRP_Center Line LWPOLYLINEs (western/PTM corridor) from '
              'X_DD_NSRP_Main_Alignment.dxf, ordered S->N and densified (bulge arcs, ~1 m chords). '
              's=0 at Bicutan station E 504743.75 N 1602372.38 (PRS92 Zone III), s positive northward. '
              'Gaps >5 m between polylines (xref breaks) are bridged LINEARLY and listed in gaps '
              '(s_start/s_end relative to Bicutan); note the ~4 km north gap around s=+1.3..+5.3 km '
              '(between N 1603571 and N 1607108) is a straight-chord approximation across missing '
              'xref data. Null samples lie outside polyline extent.')
}
json.dump(out, open(OUT, 'w'))
print('wrote', OUT)
