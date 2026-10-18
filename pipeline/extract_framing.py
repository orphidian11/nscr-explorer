"""Extract Bicutan station framing beams from framing-plan DXFs.

All three framing plans are georeferenced (PRS92 metres, EPSG:3123).
Station long axis measured at 116.8 deg in drawing coords (atan2 frame),
i.e. azimuth ~ -28.3 deg from north -- matches verified station azimuth.
Beams are drawn as paired edge lines; widths recovered from edge-pair
perpendicular separation.
"""
import ezdxf, math, json, re
from collections import Counter

def unit(d):
    a = math.radians(d)
    return (math.cos(a), math.sin(a))

LONG_DEG = 116.8   # along-alignment direction (drawing coords)
TRANS_DEG = 26.8   # transverse direction

def grow_lines(items, perp_tol=0.15, along_tol=8.0):
    """items: [((a1,c1),(a2,c2)), ...] segments in a frame where beams run along
    the 'a' axis. Returns polyline lines: {'pts': [(a,c) sorted by a], 'a0','a1'}.
    Polyline representation follows curvature (station alignment curves)."""
    def pt_seg_dist(p, q, x):
        ax, ay = q[0] - p[0], q[1] - p[1]
        L2 = ax * ax + ay * ay
        if L2 < 1e-12:
            return math.hypot(x[0] - p[0], x[1] - p[1])
        t = max(0.0, min(1.0, ((x[0] - p[0]) * ax + (x[1] - p[1]) * ay) / L2))
        return math.hypot(x[0] - (p[0] + t * ax), x[1] - (p[1] + t * ay))
    def dist_to_line(ln, x):
        pts = ln['pts']
        # reference = the polyline segment nearest in 'a'; use its INFINITE
        # extension so collinear continuation fragments attach (dist = perp
        # offset only, not distance-to-endpoint)
        best = min(range(len(pts) - 1),
                   key=lambda i: abs((pts[i][0] + pts[i + 1][0]) / 2 - x[0]))
        p, q = pts[best], pts[best + 1]
        ax, ay = q[0] - p[0], q[1] - p[1]
        L = math.hypot(ax, ay)
        if L < 1e-9:
            return math.hypot(x[0] - p[0], x[1] - p[1])
        return abs((x[0] - p[0]) * ay - (x[1] - p[1]) * ax) / L
    def plen(pq):
        return math.hypot(pq[1][0] - pq[0][0], pq[1][1] - pq[0][1])
    lines = []
    for pq in sorted(items, key=plen, reverse=True):
        p, q = pq
        placed = False
        for ln in lines:
            if max(p[0], q[0]) < ln['a0'] - along_tol or min(p[0], q[0]) > ln['a1'] + along_tol:
                continue
            if dist_to_line(ln, p) < perp_tol and dist_to_line(ln, q) < perp_tol:
                ln['pts'].extend([p, q])
                ln['pts'].sort()
                ln['a0'] = min(ln['a0'], p[0], q[0])
                ln['a1'] = max(ln['a1'], p[0], q[0])
                placed = True
                break
        if not placed:
            lines.append({'pts': sorted([p, q]), 'a0': min(p[0], q[0]), 'a1': max(p[0], q[0])})
    return lines

def _c_at(ln, a):
    """interpolated cross value of polyline at along-position a"""
    pts = ln['pts']
    if a <= pts[0][0]:
        return pts[0][1]
    if a >= pts[-1][0]:
        return pts[-1][1]
    import bisect
    i = bisect.bisect_left([p[0] for p in pts], a)
    a0, c0 = pts[i - 1]; a1, c1 = pts[i]
    if abs(a1 - a0) < 1e-9:
        return c0
    return c0 + (c1 - c0) * (a - a0) / (a1 - a0)

def extract_level(fn, beam_layers, tag_layers):
    doc = ezdxf.readfile(fn)
    msp = doc.modelspace()
    U = unit(LONG_DEG); N = (-U[1], U[0])
    # absolute -> local (along, cross)
    def loc(p):
        dx, dy = p[0], p[1]
        return (dx * U[0] + dy * U[1], dx * N[0] + dy * N[1])
    segs = []
    for e in msp:
        if e.dxftype() == 'LINE' and e.dxf.layer.upper() in beam_layers:
            s = loc((e.dxf.start.x, e.dxf.start.y))
            en = loc((e.dxf.end.x, e.dxf.end.y))
            if math.dist(s, en) < 0.05:
                continue
            ang = math.degrees(math.atan2(en[1] - s[1], en[0] - s[0])) % 180
            segs.append((s, en, ang))
    tags = []
    for e in msp:
        if e.dxftype() in ('TEXT', 'MTEXT') and e.dxf.layer.upper() in tag_layers:
            t = (e.dxf.text if e.dxftype() == 'TEXT' else e.plain_text()).strip()
            if re.fullmatch(r'[A-Z]{1,3}\d{1,2}[A-Z]?', t):
                tags.append((t, loc((e.dxf.insert.x, e.dxf.insert.y))))
    beams = []
    for fam in ('transverse', 'longitudinal'):
        # in local frame: transverse beams run along c (fixed a); longitudinal run along a (fixed c)
        # grow lines in rotated coords so the "along" of the fit is the beam direction
        fam_segs = []
        for s, en, ang in segs:
            # ang is in the LOCAL frame (0 = longitudinal, 90 = transverse)
            if fam == 'transverse' and abs(ang - 90.0) > 2.0:
                continue
            if fam == 'longitudinal' and not (ang < 2.0 or ang > 178.0):
                continue
            if fam == 'transverse':
                fam_segs.append(((s[1], s[0]), (en[1], en[0])))  # swap -> fit along c
            else:
                fam_segs.append((s, en))
        lines = grow_lines(fam_segs)
        # pair lines whose perpendicular separation is a beam width and which overlap
        # separation measured at the mid of the overlap
        beams_fam = []
        used = [False] * len(lines)
        for i in range(len(lines)):
            if used[i]:
                continue
            for j in range(i + 1, len(lines)):
                if used[j]:
                    continue
                ov0 = max(lines[i]['a0'], lines[j]['a0'])
                ov1 = min(lines[i]['a1'], lines[j]['a1'])
                if ov1 - ov0 < 0.3 * min(lines[i]['a1'] - lines[i]['a0'],
                                         lines[j]['a1'] - lines[j]['a0']):
                    continue  # need >=30% along-overlap
                # sampled mean separation across the overlap
                K = 7
                seps = []
                for k in range(K):
                    am = ov0 + (ov1 - ov0) * k / (K - 1)
                    seps.append(abs(_c_at(lines[j], am) - _c_at(lines[i], am)))
                w = sum(seps) / len(seps)
                if max(seps) - min(seps) > 0.6:
                    continue  # separation not constant -> not an edge pair
                if 0.30 <= w <= 1.40:
                    a0 = min(lines[i]['a0'], lines[j]['a0'])
                    a1 = max(lines[i]['a1'], lines[j]['a1'])
                    # centre polyline = midline between the two edges
                    cmid = [(a, (_c_at(lines[i], a) + _c_at(lines[j], a)) / 2)
                            for a, _ in lines[i]['pts']]
                    beams_fam.append({'a0': a0, 'a1': a1, 'c': _c_at(lines[i], (ov0 + ov1) / 2),
                                      'cmid': cmid, 'w': w, 'fam': fam})
                    used[i] = used[j] = True
                    break
        # post-merge fragment beams (same offset/width, adjacent extents);
        # wider tolerance for longitudinal girders (curved, >=1.5 m apart)
        if fam == 'longitudinal':
            off_tol, w_tol, gap_tol = 0.65, 0.35, 2.5
        else:
            off_tol, w_tol, gap_tol = 0.22, 0.12, 1.5
        fb = sorted(beams_fam, key=lambda b: (b['c'], b['a0']))
        groups = []
        cur = [fb[0]] if fb else []
        for b in fb[1:]:
            prev = cur[-1]
            if (abs(b['c'] - prev['c']) < off_tol and abs(b['w'] - prev['w']) < w_tol
                    and b['a0'] <= prev['a1'] + gap_tol and b['a1'] >= prev['a0'] - gap_tol):
                cur.append(b)
            else:
                groups.append(cur)
                cur = [b]
        if cur:
            groups.append(cur)
        merged = []
        for g in groups:
            m = dict(g[0])
            m['a0'] = min(b['a0'] for b in g)
            m['a1'] = max(b['a1'] for b in g)
            m['w'] = max(b['w'] for b in g)
            m['c'] = sum(b['c'] for b in g) / len(g)
            pts = sorted([p for b in g for p in b['cmid']])
            m['cmid'] = pts
            m['nfrag'] = len(g)
            merged.append(m)
        beams_fam = merged
        # map back to absolute xy: local (a,c) -> xy = a*U + c*N
        for b in beams_fam:
            seg = []
            if fam == 'longitudinal':
                # cmid: (a=along, c=cross); beam may curve -> sample every ~5 m
                span = b['a1'] - b['a0']
                ns = max(2, min(40, int(span / 5) + 1))
                for k in range(ns):
                    a = b['a0'] + span * k / (ns - 1)
                    c = _c_at({'pts': b['cmid']}, a)
                    seg.append((a * U[0] + c * N[0], a * U[1] + c * N[1]))
            else:
                # transverse (swapped coords): cmid (a=cross, c=along); straight
                (a0, c0) = b['cmid'][0]; (a1, c1) = b['cmid'][-1]
                seg = [(c0 * U[0] + a0 * N[0], c0 * U[1] + a0 * N[1]),
                       (c1 * U[0] + a1 * N[0], c1 * U[1] + a1 * N[1])]
            b['seg'] = [list(p) for p in seg]
            # nearest tag to beam midpoint
            bx = (seg[0][0] + seg[-1][0]) / 2; by = (seg[0][1] + seg[-1][1]) / 2
            bl = ((bx * U[0] + by * U[1]), (bx * N[0] + by * N[1]))
            best = None
            for t, (ta, tc) in tags:
                d = math.hypot(ta - bl[0], tc - bl[1])
                if d < 1.6 and (best is None or d < best[1]):
                    best = (t, d)
            b['tag'] = best[0] if best else None
        beams.extend(beams_fam)
    return beams

def summarize(beams):
    out = {}
    for fam in ('transverse', 'longitudinal'):
        fb = sorted([b for b in beams if b['fam'] == fam], key=lambda b: b['c'])
        wc = Counter(round(b['w'], 2) for b in fb)
        # spacing of portal (w>=0.8) transverse beams
        info = {'n': len(fb), 'widths': dict(wc.most_common(6))}
        if fam == 'transverse':
            port = [b for b in fb if b['w'] >= 0.8]
            sp = [round(port[i + 1]['c'] - port[i]['c'], 2) for i in range(len(port) - 1)]
            info['portal_n'] = len(port)
            info['portal_spacings'] = sp
            sec = [b for b in fb if 0.3 <= b['w'] < 0.8]
            ssp = [round(sec[i + 1]['c'] - sec[i]['c'], 2) for i in range(len(sec) - 1)]
            info['secondary_n'] = len(sec)
            info['secondary_spacings'] = ssp
        else:
            info['offsets'] = [round(b['c'], 1) for b in fb]
        out[fam] = info
    return out

if __name__ == '__main__':
    jobs = [
        ('GL +8.30', 8.30, 'dxf/struct_out/X_BIC-ST-GL +8.30 FRAMING PLAN.dxf',
         {'S-BEAM-ELE', 'GIRDER'}, {'GIRDER_TEXT35'}),
        ('GL +9.750', 9.75, 'dxf/struct_out/X_BIC-ST-GL +9.750 FRAMING PLAN.dxf',
         {'S-BEAM-ELE'}, {'GIRDER_TEXT35'}),
        ('CONCOURSE', None, 'dxf/struct_out/X_BIC-ST-CONCOURSE FLOOR FRAMING PLAN.dxf',
         {'BEAM'}, {'BEAM_TEXT35', 'GIRDER_TEXT35'}),
    ]
    levels = []
    for name, elev, fn, bl, tl in jobs:
        beams = extract_level(fn, bl, tl)
        # drop sub-2m stubs (closing fragments / joints)
        beams = [b for b in beams if (b['a1'] - b['a0']) >= 2.0]
        lvl_beams = []
        for b in beams:
            fam = b['fam']
            if fam == 'transverse':
                kind = 'transverse'
                role = 'portal' if b['w'] >= 0.8 else 'secondary'
            else:
                kind = 'longitudinal'
                role = 'girder' if b['w'] >= 0.8 else 'secondary'
            lvl_beams.append({
                'kind': kind, 'role': role,
                'segments': [b['seg']] if len(b['seg']) == 2 else
                            [[b['seg'][i], b['seg'][i + 1]] for i in range(len(b['seg']) - 1)],
                'width_m': round(b['w'], 2),
                'span_m': round(b['a1'] - b['a0'], 1),
                'tag': b.get('tag'),
            })
        # stats
        tr = [b for b in beams if b['fam'] == 'transverse']
        port = [b for b in tr if b['w'] >= 0.8]
        port.sort(key=lambda b: b['c'])
        sp = [round(port[i + 1]['c'] - port[i]['c'], 2) for i in range(len(port) - 1)]
        clean = [g for g in sp if g > 3]
        sec = [b for b in tr if 0.3 <= b['w'] < 0.8]
        sec.sort(key=lambda b: b['c'])
        ssp = [g for g in (round(sec[i + 1]['c'] - sec[i]['c'], 2)
                           for i in range(len(sec) - 1)) if g > 1.2]
        widths_port = sorted(set(round(b['w'], 2) for b in port))
        widths_sec = sorted(set(round(b['w'], 2) for b in sec))
        notes = (f"Georeferenced PRS92 EPSG:3123 (line ents at E~504.5k, N~1602k). "
                 f"Beams drawn as paired edge lines; width = edge-pair separation. "
                 f"Portal transverse beams (w {widths_port} m) n={len(port)}, rhythm "
                 f"median {sorted(clean)[len(clean)//2] if clean else 0:.2f} m, "
                 f"secondary transverse (w {widths_sec} m) n={len(sec)}, rhythm median "
                 f"{sorted(ssp)[len(ssp)//2] if ssp else 0:.2f} m. "
                 f"Axis 116.8 deg in drawing coords (azimuth ~ -27 deg from north).")
        if name == 'GL +8.30':
            notes += (" This grade-level sheet is sparse: 0.8/1.2 m-wide sub-2m stubs "
                      "at 10-m rhythm are COLUMN cross-sections (800x1200), filtered "
                      "out; only real beams kept.")
        levels.append({
            'name': name, 'elev': elev,
            'beams': lvl_beams,
            'sheet_local': False,
            'notes': notes,
            'grid': {
                'portal_spacing_m': sorted(clean)[len(clean)//2] if clean else None,
                'portal_widths_m': widths_port,
                'secondary_spacing_m': sorted(ssp)[len(ssp)//2] if ssp else None,
                'secondary_widths_m': widths_sec,
                'transverse_n': len(tr), 'portal_n': len(port),
                'longitudinal_n': len(beams) - len(tr),
            },
            'source_file': fn,
        })
        print(f"{name}: {len(lvl_beams)} beams "
              f"(portal {len(port)}, secondary trans {len(sec)}, "
              f"long {len(beams)-len(tr)})")
        json.dump(beams, open(f'_beams_{name.replace(" ", "_").replace("+", "p")}.json', 'w'))

    out = {
        'levels': levels,
        'sources': [j[2] for j in jobs],
        'notes': ("All three framing plans are georeferenced (PRS92 / EPSG:3123 "
                  "metres, INSUNITS=6) - no sheet-local transform needed. "
                  "Station long axis at 116.8 deg in drawing coords (atan2 frame), "
                  "azimuth ~ -27 deg from north (matches alignment azimuth -27.28). "
                  "Structural grid from the GRIDS block dims on GL +8.30: "
                  "longitudinal grid lines 6.4/12.3/6.4 m apart, full transverse "
                  "width 38.5 m; transverse grid ~4.58 m chain (82.5 m). "
                  "Beam widths recovered from paired edge-line separations "
                  "(plans at 1:1 scale): portal/girder ~1.0 m, secondary ~0.4-0.5 m. "
                  "GL +9.750 portal beams every ~9-10 m span 17-43 m rel-cross "
                  "-24..+20, covering both tracks (rel-cross -3.8/+5.0, spacing 8.8). "
                  "Concourse elevation not stated on the sheet (elev null). "
                  "Coordinates: absolute PRS92 EPSG:3123 easting/northing."),
    }
    json.dump(out, open('framing.json', 'w'), indent=1)
    print('wrote framing.json')
