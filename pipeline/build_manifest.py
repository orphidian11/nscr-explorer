"""Build NSCR station 3D manifests from CAD-extracted DXF geometry + alignment_v3.

Sources (all ezdxf-parsed, georeferenced PRS92 Zone III / EPSG:3123, metres):
  Bicutan (bicutan-real.json):
  - X_Bic_Sta_Ground Floor.dxf  WALL/A-WALL segments -> ground-level walls, FFL +0.50
  - X_Bic_Sta_Concourse.dxf     A-WALL segments      -> concourse walls, FFL +4.60
  - X_Bic_Sta_Platform.dxf      A-SLAB/A-BALUSTRADE   -> platform slab outline, FFL +11.90
  Sucat (sucat-real.json):
  - X_Suc_Sta_Ground Floor.dxf / Concourse.dxf  A-WALL segments
  - X_Suc_Sta_Platform.dxf      A-PLATFORM / A-PSD footprint -> 2 side platforms
  - Levels from X_Suc_Sta_Section.dxf dimension texts (verified):
    GF +1.00 | Concourse +7.85 | Top of rail +15.50 | Platform FFL +16.60
  Senate-DepEd (BUE) / EDSA: massing from stations_north_south.json bbox + DFR type
  (levels assumed Bicutan-like / FTI-like respectively - flagged in meta).

Alignment: alignment_v3.json - 1526 pts @10 m along the assembled NSCR main
alignment (12 S_NSRP_Center Line LWPOLYLINEs, OSM/hermite splices in the gaps).
s below is the CUMULATIVE ARCLENGTH OF THE ASSEMBLED POINT ARRAY.  NOTE:
alignment_v3.json's own stations_s (Bicutan 0 / Sucat -4381 / BUE +4857 /
EDSA +8395) use a nominal axis that does not match the assembled geometry (the
OSM splices change real arclength); here station s values are GEOMETRIC
nearest-approach projections of each station centre onto the actual point
array - the deck then really passes the stations.

Deck base profile (piecewise linear): elevated (BASE_Y 10.6) at Sucat, Bicutan
and BUE; at-grade (0.60) at FTI and EDSA; linear ramps between, at-grade run
from FTI to EDSA, elevated south of Sucat and north of BUE.
"""
import ezdxf, os, json, math, bisect

OUT = r"E:\NSCR\app\src\data"
SEGS = json.load(open(r"E:\NSCR\pipeline\wall_segments.json"))
STN = {s["id"]: s for s in json.load(open(r"E:\NSCR\pipeline\stations_north_south.json"))["stations"]}

WALL_T = 0.25  # wall thickness, m (assumption; refine from double-line spacing)

def _atomic_json_dump(obj, path, attempts=12):
    # Windows: the dev server's watcher / antivirus can briefly hold the target
    # after a rename - retry, then fall back to an in-place write.
    import time as _time
    tmp = path + ".tmp"
    for i in range(attempts):
        try:
            with open(tmp, "w") as fh:
                json.dump(obj, fh, indent=1)
            os.replace(tmp, path)
            return
        except PermissionError:
            _time.sleep(1.0 + i * 0.5)
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=1)

def as_list(x):
    return x if isinstance(x, list) else [x]

# ================= alignment_v3 (the single corridor spine) =================
AL = json.load(open(r"E:\NSCR\pipeline\alignment_v3.json"))
ALP = AL["points"]
CUM = [0.0]
for i in range(1, len(ALP)):
    CUM.append(CUM[-1] + math.dist(ALP[i - 1], ALP[i]))
S_END = CUM[-1]

def al_point_at(sv):
    """PRS92 (e,n) at global arclength sv (linear interp between samples)."""
    sv = min(max(sv, 0.0), S_END)
    i = bisect.bisect_left(CUM, sv)
    if i <= 0:
        return ALP[0]
    if i >= len(ALP):
        return ALP[-1]
    t = (sv - CUM[i - 1]) / (CUM[i] - CUM[i - 1])
    return (ALP[i - 1][0] + (ALP[i][0] - ALP[i - 1][0]) * t,
            ALP[i - 1][1] + (ALP[i][1] - ALP[i - 1][1]) * t)

def al_tangent_at(sv):
    d = 10.0
    p1, p2 = al_point_at(max(sv - d, 0.0)), al_point_at(min(sv + d, S_END))
    L = math.dist(p1, p2) or 1.0
    return ((p2[0] - p1[0]) / L, (p2[1] - p1[1]) / L)

def al_nearest_s(en):
    """global arclength of the closest-approach sample to PRS92 point en."""
    best = min(range(len(ALP)), key=lambda i: math.hypot(ALP[i][0] - en[0], ALP[i][1] - en[1]))
    return CUM[best], math.hypot(ALP[best][0] - en[0], ALP[best][1] - en[1])

# Station s along the assembled array (geometric nearest approach)
SUC = STN["sucat"]["center_prs92"]; S_SUC, d_suc = al_nearest_s((SUC["e"], SUC["n"]))
BUE = STN["senate-deped_bue"]["center_prs92"]; S_BUE, d_bue = al_nearest_s((BUE["e"], BUE["n"]))
EDS = STN["edsa"]["center_prs92"]; S_EDS, d_eds = al_nearest_s((EDS["e"], EDS["n"]))
FTIc = json.load(open(r"E:\NSCR\pipeline\fti.json"))["center_prs92"]; S_FTI, d_fti = al_nearest_s((FTIc["e"], FTIc["n"]))
assert max(d_suc, d_bue, d_eds, d_fti) < 15, "station centre off the v3 alignment"

def heading_rotY(dx, dz):
    return -math.atan2(dz, dx)  # three.js rotY aligning box +x with (dx,dz)

def lerp_pt(p1, p2, t):
    return (p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t)

# ================= Bicutan local frame (origin = wall bbox centre) ==========
def all_bbox(segs_list):
    pts = [p for segs in segs_list for s in segs for p in s]
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)

b = all_bbox([SEGS["gf"], SEGS["cc"], SEGS["pl"]])
E0, N0 = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2

def to_local_bic(seg):
    (e1, n1), (e2, n2) = seg
    return (round(e1 - E0, 2), round(-(n1 - N0), 2)), (round(e2 - E0, 2), round(-(n2 - N0), 2))

def wall_boxes(segs, base_y, top_y, to_local, src):
    boxes = []
    for seg in segs:
        (x1, z1), (x2, z2) = to_local(seg)
        L = math.dist((x1, z1), (x2, z2))
        cx, cz = (x1 + x2) / 2, (z1 + z2) / 2
        ang = math.degrees(math.atan2(z2 - z1, x2 - x1))
        boxes.append({"kind": "box", "size": [round(L + WALL_T, 2), round(top_y - base_y, 2), WALL_T],
                      "pos": [round(cx, 2), round((base_y + top_y) / 2, 2), round(cz, 2)],
                      "rotY": round(-math.radians(ang), 4),
                      "meta": {"src": src + " wall segment", "base": base_y, "top": top_y}})
    return boxes

walls = wall_boxes(SEGS["gf"], 0.50, 4.60, to_local_bic, "X_Bic_Sta") \
      + wall_boxes(SEGS["cc"], 4.60, 11.90, to_local_bic, "X_Bic_Sta")

# Local-frame alignment samples (full 15 km corridor, Bicutan local frame)
al_pts = [(p[0] - E0, -(p[1] - N0)) for p in ALP]
# local s: arclength minus the arclength at the frame origin's nearest sample
_s0_cum, _ = al_nearest_s((E0, N0))
def g2l(sv):  # global arclength -> Bicutan-local s
    return sv - _s0_cum

d0 = min(range(len(al_pts)), key=lambda i: math.hypot(*al_pts[i]))
_j = min(d0 + 1, len(al_pts) - 1)
tux, tuz = al_pts[_j][0] - al_pts[d0][0], al_pts[_j][1] - al_pts[d0][1]
tl = math.hypot(tux, tuz); tux, tuz = tux / tl, tuz / tl

fti_x, fti_z = FTIc["e"] - E0, -(FTIc["n"] - N0)

_s_all = [x * tux + z * tuz for key in ("gf", "cc", "pl") for seg in SEGS[key]
          for (x, z) in ((e - E0, -(n - N0)) for (e, n) in seg)]
S_LO, S_HI = min(_s_all), max(_s_all)

def track_frame_pt(along_s, offset):
    return [round(tux * along_s - tuz * offset, 2), round(tuz * along_s + tux * offset, 2)]

# --- Station boxes (Bicutan-local s) + deck profile -------------------------
TRACK_OFF = 4.4       # track centreline offset (8.8 m spacing)
BASE_Y = 10.6         # elevated deck base (rail base)
AG_Y = 0.60           # at-grade rail base (FTI DFR design)
FTI_HALF = 75.0       # 140 m footprint + margin (estimate)
FTI_L = g2l(S_FTI); EDS_L = g2l(S_EDS); BUE_L = g2l(S_BUE); SUC_L = g2l(S_SUC)
BIC_C = (S_LO + S_HI) / 2
FTI_LO, FTI_HI = FTI_L - FTI_HALF, FTI_L + FTI_HALF
STATION_BOXES = sorted([
    (SUC_L - 120, SUC_L + 120),
    (S_LO, S_HI),                       # Bicutan
    (FTI_LO, FTI_HI),
    (EDS_L - 120, EDS_L + 120),
    (BUE_L - 120, BUE_L + 120),
])
assert all(STATION_BOXES[i][1] < STATION_BOXES[i + 1][0] for i in range(len(STATION_BOXES) - 1)), 'station boxes overlap'
AT_GRADE_BOXES = [(FTI_LO, FTI_HI), (EDS_L - 120, EDS_L + 120)]  # bed (no webs) through these

# Deck profile nodes (local s, base_y): elevated at Sucat/Bicutan/BUE,
# at-grade at FTI/EDSA, linear ramps between; flat elevated S of Sucat / N of BUE.
DECK_NODES = sorted([
    (SUC_L, BASE_Y), (BIC_C, BASE_Y), (FTI_L, AG_Y),
    (EDS_L, AG_Y), (BUE_L, BASE_Y),
])
def deck_base_y(s):
    if s <= DECK_NODES[0][0]:
        return DECK_NODES[0][1]
    if s >= DECK_NODES[-1][0]:
        return DECK_NODES[-1][1]
    for (s1, y1), (s2, y2) in zip(DECK_NODES, DECK_NODES[1:]):
        if s1 <= s <= s2:
            return y1 + (y2 - y1) * (s - s1) / max(s2 - s1, 1.0)
    return BASE_Y

# ================= Bicutan station objects (unchanged extraction) ===========
platform = []
PLAT_HALF_W = 2.0
PLAT_OFF = 9.0
PLAT_TOP = 11.90
_end_n = (504694.6 - E0, -(1602447.25 - N0))
_end_s = (504777.55 - E0, -(1602286.4 - N0))
s_n = _end_n[0] * tux + _end_n[1] * tuz
s_s = _end_s[0] * tux + _end_s[1] * tuz
P_LO, P_HI = min(s_n, s_s) - 3.9, max(s_n, s_s) + 3.9
P_C = (P_LO + P_HI) / 2
P_LEN = P_HI - P_LO
L_along = P_LEN

for side in (-1, 1):
    cx, cz = track_frame_pt(P_C, side * PLAT_OFF)
    platform.append({"kind": "box", "size": [round(P_LEN, 1), 0.4, PLAT_HALF_W * 2],
                     "pos": [cx, round(PLAT_TOP - 0.2, 2), cz],
                     "rotY": round(heading_rotY(tux, tuz), 4),
                     "color": "#c3c8cd",
                     "meta": {"src": "X_Bic_Sta_Platform A-BALUSTRADE footprint; side platform, edge ~7.0 m offset (6.97 m dim)"}})
    tx, tz = track_frame_pt(P_C, side * (PLAT_OFF - PLAT_HALF_W + 0.35))
    platform.append({"kind": "box", "size": [round(P_LEN - 1.0, 1), 0.06, 0.7],
                     "pos": [tx, round(PLAT_TOP + 0.06, 2), tz],
                     "rotY": round(heading_rotY(tux, tuz), 4),
                     "color": "#d9a821",
                     "meta": {"src": "tactile warning strip (standard PT detail)"}})
    px, pz = track_frame_pt(P_C, side * (PLAT_OFF - PLAT_HALF_W - 0.05))
    platform.append({"kind": "box", "size": [round(P_LEN, 1), 1.2, 0.12],
                     "pos": [px, round(PLAT_TOP + 0.6, 2), pz],
                     "rotY": round(heading_rotY(tux, tuz), 4),
                     "color": "#b7bcc2",
                     "meta": {"src": "inner-edge balustrade (A-BALUSTRADE line)"}})
for cE, cN in ((504694.6, 1602447.25), (504777.55, 1602286.4)):
    ex, ez = cE - E0, -(cN - N0)
    platform.append({"kind": "box", "size": [round(7.8, 1), 1.4, 4.0],
                     "pos": [round(ex, 2), round(PLAT_TOP + 0.7, 2), round(ez, 2)],
                     "rotY": round(heading_rotY(tux, tuz), 4),
                     "color": "#b7bcc2",
                     "meta": {"src": "X_Bic_Sta_Platform A-BALUSTRADE end wall (real bbox)"}})

tracks = []
alT = S_HI - S_LO
alC = (S_LO + S_HI) / 2
for off in (-TRACK_OFF, TRACK_OFF):
    tracks.append({"kind": "box", "size": [round(alT + 2, 1), 0.3, 1.6],
                   "pos": [round(tux * alC - tuz * off, 2), 10.65, round(tuz * alC + tux * off, 2)],
                   "rotY": round(heading_rotY(tux, tuz), 4),
                   "meta": {"src": "typical double track along NSCR alignment, 8.8 m spacing per section DIMS (+/-4.4 m), TOR +10.80"}})

COLUMNS = json.load(open(r"E:\NSCR\pipeline\columns.json"))["columns"]
piers = []
for col in COLUMNS:
    x, z = col["e"] - E0, -(col["n"] - N0)
    piers.append({"kind": "cylinder", "radius": 0.5, "height": 15.85,
                  "pos": [round(x, 2), round(15.85 / 2, 2), round(z, 2)],
                  "meta": {"src": "foundation plan column pad (columns.json)",
                           "pad_size_m": col["size"],
                           "note": "5.4/6.8 m are pile-cap pad sizes, not column widths"}})

CANOPY = json.load(open(r"E:\NSCR\pipeline\canopy.json"))
prof = CANOPY["roof_profile"]["points"]
apex_e = max(prof, key=lambda p: p[1])[0]
mid_e = (min(p[0] for p in prof) + max(p[0] for p in prof)) / 2
assert abs(apex_e - mid_e) < 0.5, f"apex {apex_e} off profile mid {mid_e}"
profile_offsets = [[round(p[0] - apex_e, 2), round(p[1], 2)] for p in prof]
rg = CANOPY["roof_profile"]["ridge"]
r1 = (rg["E_start"] - E0, -(rg["N_start"] - N0))
r2 = (rg["E_end"] - E0, -(rg["N_end"] - N0))
vault = {"kind": "vault", "profile": profile_offsets,
         "axisStart": [round(r1[0], 2), round(r1[1], 2)],
         "axisEnd": [round(r2[0], 2), round(r2[1], 2)],
         "meta": {"src": "X_Bic_Sta_Section.dxf transverse arch + ridge setout",
                  "span_m": CANOPY["roof_profile"]["span_transverse"],
                  "apex_elev": CANOPY["roof_profile"]["apex_elev"],
                  "eave_elev": CANOPY["roof_profile"]["eave_elev"],
                  "radius_m": CANOPY["roof_profile"]["radius"]}}

lattice = []
for pl in CANOPY["facade"]["polylines"]:
    for (e1, n1), (e2, n2) in zip(pl, pl[1:]):
        x1, z1 = e1 - E0, -(n1 - N0)
        x2, z2 = e2 - E0, -(n2 - N0)
        L = math.dist((x1, z1), (x2, z2))
        if L < 0.05:
            continue
        ang = math.atan2(z2 - z1, x2 - x1)
        lattice.append({"kind": "box",
                        "size": [round(L + 0.08, 2), 15.9, 0.08],
                        "pos": [round((x1 + x2) / 2, 2), 7.95, round((z1 + z2) / 2, 2)],
                        "rotY": round(-ang, 4),
                        "meta": {"src": "A-CLAD FRAMING outline (facade.json)"}})

stairs = []
for z in (-30, 30):
    for lvl, (by, ty) in enumerate([(0.50, 4.60), (4.60, 11.90)]):
        stairs.append({"kind": "box", "size": [6.0, ty - by, 4.0],
                       "pos": [round(-L_along / 2 + 10 + lvl * 8, 1), round((by + ty) / 2, 2), z],
                       "meta": {"src": "regularized stair core (A-STAIRS clusters seen in GF/Platform plans)"}})

FR = json.load(open(r"E:\NSCR\pipeline\framing.json"))
beams = []
for lvl in FR["levels"]:
    if lvl["name"] != "GL +9.750":
        continue
    elev = lvl["elev"]
    for bb in lvl["beams"]:
        w = bb["width_m"]
        for (e1, n1), (e2, n2) in bb["segments"]:
            x1, z1 = e1 - E0, -(n1 - N0)
            x2, z2 = e2 - E0, -(n2 - N0)
            L = math.dist((x1, z1), (x2, z2))
            if L < 1.0:
                continue
            ang = math.degrees(math.atan2(z2 - z1, x2 - x1))
            beams.append({"kind": "box",
                          "size": [round(L, 2), 0.8, w],
                          "pos": [round((x1 + x2) / 2, 2), round(elev + 0.4, 2), round((z1 + z2) / 2, 2)],
                          "rotY": round(-math.radians(ang), 4),
                          "meta": {"src": "framing.json GL +9.750 " + bb["kind"], "width_m": w}})

CM = json.load(open(r"E:\NSCR\pipeline\commuter.json"))
floors = []
for fl in CM["floors"]:
    key = "gf" if fl["name"] == "ground" else "cc"
    pts = [(e - E0, -(n - N0)) for seg in SEGS[key] for (e, n) in seg]
    ss = [x * tux + z * tuz for x, z in pts]
    offs = [x * -tuz + z * tux for x, z in pts]
    L = max(ss) - min(ss)
    s_mid = (max(ss) + min(ss)) / 2
    W = min(max(offs) - min(offs), 38.5 if key == "cc" else 45.0)
    off_mid = (max(offs) + min(offs)) / 2
    cx = tux * s_mid - tuz * off_mid
    cz = tuz * s_mid + tux * off_mid
    floors.append({"kind": "box", "size": [round(L, 1), 0.3, round(W, 1)],
                   "pos": [round(cx, 2), round(fl["elev"] - 0.15, 2), round(cz, 2)],
                   "rotY": round(heading_rotY(tux, tuz), 4),
                   "color": "#d6d9dd" if fl["name"] == "concourse" else "#c9ccd0",
                   "meta": {"src": "wall-segment projection (commuter.json floors)", "name": fl["name"], "elev": fl["elev"]}})

# ================= Corridor viaduct (deck + piers, Bicutan frame) ===========
DECK_W = 5.14
WEB_T = 0.3
BASE_T = 0.3
WEB_H = 1.2

viaduct_deck = []
viaduct_piers = []
for i in range(len(al_pts) - 1):
    p1, p2 = al_pts[i], al_pts[i + 1]
    s1, s2 = g2l(CUM[i]), g2l(CUM[i + 1])
    lo, hi = min(s1, s2), max(s1, s2)
    spans = []
    cur = lo
    for (b_lo, b_hi) in STATION_BOXES:
        if b_hi <= cur or b_lo >= hi:
            continue
        if b_lo > cur:
            spans.append((cur, min(hi, b_lo)))
        cur = max(cur, b_hi)
    if cur < hi:
        spans.append((cur, hi))
    # at-grade bed through the at-grade station boxes (no webs, flat)
    beds = []
    for (b_lo, b_hi) in AT_GRADE_BOXES:
        bs, be = max(lo, b_lo), min(hi, b_hi)
        if be - bs >= 1.0:
            beds.append((bs, be))
    if not spans and not beds:
        continue
    L = math.dist(p1, p2)
    dx, dz = (p2[0] - p1[0]) / L, (p2[1] - p1[1]) / L
    rot = heading_rotY(dx, dz)
    perp = (dz, -dx)

    def emit_deck(sa, sb, base_mid, webs=True, src_note="alignment_v3 U-girder (simplified)"):
        q1 = lerp_pt(p1, p2, (sa - s1) / (s2 - s1))
        q2 = lerp_pt(p1, p2, (sb - s1) / (s2 - s1))
        seg_l = math.dist(q1, q2)
        if seg_l < 1.0:
            return
        mx, mz = (q1[0] + q2[0]) / 2, (q1[1] + q2[1]) / 2
        for off in (-TRACK_OFF, TRACK_OFF):
            cx, cz = mx + perp[0] * off, mz + perp[1] * off
            viaduct_deck.append({"kind": "box", "size": [round(seg_l + 0.1, 2), BASE_T, DECK_W],
                                 "pos": [round(cx, 2), round(base_mid - BASE_T / 2, 2), round(cz, 2)], "rotY": round(rot, 4),
                                 "meta": {"src": src_note + " base slab"}})
            if not webs:
                continue
            for w in (-1, 1):
                wx, wz = cx + perp[0] * w * (DECK_W / 2 - WEB_T / 2), cz + perp[1] * w * (DECK_W / 2 - WEB_T / 2)
                viaduct_deck.append({"kind": "box", "size": [round(seg_l + 0.1, 2), WEB_H, WEB_T],
                                     "pos": [round(wx, 2), round(base_mid + WEB_H / 2, 2), round(wz, 2)], "rotY": round(rot, 4),
                                     "meta": {"src": src_note + " web"}})

    for (sa, sb) in spans:
        if sb - sa < 1.0:
            continue
        ym = deck_base_y((sa + sb) / 2)
        emit_deck(sa, sb, ym, webs=ym > 3.0,
                  src_note="alignment_v3 at-grade track bed" if ym <= 3.0 else "alignment_v3 U-girder (simplified)")
    for (bsa, bsb) in beds:
        emit_deck(bsa, bsb, AG_Y, webs=False, src_note="at-grade track bed through at-grade station box")

# Piers every 40 m, skipped inside ANY station box and on at-grade stretches
for i in range(0, len(al_pts), 4):
    p = al_pts[i]
    s = g2l(CUM[i])
    if any(b_lo <= s <= b_hi for (b_lo, b_hi) in STATION_BOXES):
        continue
    py = deck_base_y(s)
    if py < 2.0:
        continue  # at-grade: no pier columns
    q2 = al_pts[min(i + 1, len(al_pts) - 1)]
    rot = heading_rotY(q2[0] - p[0], q2[1] - p[1])
    L = math.dist(p, q2) or 1.0
    perp = ((q2[1] - p[1]) / L, -(q2[0] - p[0]) / L)
    col_h = max(py - 0.6, 1.0)
    for off in (-1.5, 1.5):
        viaduct_piers.append({"kind": "cylinder", "radius": 0.5, "height": round(col_h, 2),
                              "pos": [round(p[0] + perp[0] * off, 2), round(col_h / 2, 2), round(p[1] + perp[1] * off, 2)],
                              "meta": {"src": "alignment_v3 twin pier column, 40 m spacing (CAD pier markers)"}})
    viaduct_deck.append({"kind": "box", "size": [2.5, 0.8, 5.6],
                         "pos": [round(p[0], 2), round(py - 0.4, 2), round(p[1], 2)], "rotY": round(rot, 4),
                         "meta": {"src": "alignment_v3 pier cap beam (rendered with deck layer; schema keeps piers cylinders-only)"}})

manifest = {
  "name": "Bicutan Station (NSCR CP S-03c)",
  "crs": "PRS92 PTM Zone III (EPSG:3123), metres",
  "origin_easting": round(E0, 2), "origin_northing": round(N0, 2),
  "origin_wgs84": {"lat": 14.488419, "lon": 121.045368,
                   "note": "approx; refine by transforming origin_easting/northing via PROJ EPSG:3123->4326"},
  "levels_m": {"ground_ffl": 0.50, "concourse_ffl": 4.60, "top_of_rail": 10.80, "platform_ffl": 11.90,
               "top_of_beam": 15.90, "roof": 24.70},
  "sources": ["X_Bic_Sta_Ground Floor.dxf", "X_Bic_Sta_Concourse.dxf", "X_Bic_Sta_Platform.dxf",
              "X_Bic_Sta_Section.dxf", "foundation plan (columns.json)", "facade A-CLAD (canopy.json)",
              "main alignment + viaduct section (alignment_v3.json)"],
  "objects": {"walls": walls, "platform": platform, "tracks": tracks,
              "piers": piers, "stairs": stairs, "vault": vault, "lattice": lattice,
              "viaduct_deck": viaduct_deck, "viaduct_piers": viaduct_piers,
              "beams": beams, "floors": floors}
}
os.makedirs(OUT, exist_ok=True)
_atomic_json_dump(manifest, os.path.join(OUT, "bicutan-real.json"))
print("Bicutan: walls", len(walls), "| piers", len(piers), "| viaduct deck boxes", len(viaduct_deck),
      "| viaduct pier columns", len(viaduct_piers), "| station extent", round(S_LO, 1), "to", round(S_HI, 1))
print("  station s (Bicutan-local): Sucat", round(SUC_L, 1), "FTI", round(FTI_L, 1),
      "EDSA", round(EDS_L, 1), "BUE", round(BUE_L, 1))

# ================= shared rebase / massing helpers ==========================
def rebase(objs, dx, dz):
    out = []
    for o in objs:
        o = dict(o)
        o["pos"] = [round(o["pos"][0] + dx, 2), o["pos"][1], round(o["pos"][2] + dz, 2)]
        out.append(o)
    return out

def approach_deck_in_frame(centre, tangent_local):
    """Corridor deck/piers within +/-1.5 km of the station, rebased into the
    station's own local frame (origin = station centre)."""
    tux_, tuz_ = tangent_local
    dx, dz = (centre["e"] - E0), -(centre["n"] - N0)
    vd, vp = [], []
    for o0 in viaduct_deck:
        x, z = o0["pos"][0], o0["pos"][2]
        if abs((x - dx) * tux_ + (z - dz) * tuz_) <= 1500:
            o = dict(o0); o["pos"] = [round(o0["pos"][0] - dx, 2), o0["pos"][1], round(o0["pos"][2] - dz, 2)]
            vd.append(o)
    for o0 in viaduct_piers:
        x, z = o0["pos"][0], o0["pos"][2]
        if abs((x - dx) * tux_ + (z - dz) * tuz_) <= 1500:
            o = dict(o0); o["pos"] = [round(o0["pos"][0] - dx, 2), o0["pos"][1], round(o0["pos"][2] - dz, 2)]
            vp.append(o)
    return vd, vp

def local_tangent(s_glob):
    tx, tz_en = al_tangent_at(s_glob)
    return tx, -tz_en  # local z = -(N - N0) flip

# ================= FTI station manifest (v1.0.0) ============================
# JICA DFR Type E' at-grade design (superseded by the as-built underground CP
# NSCR-03-B station - rendered as the DFR massing). Levels (ASSUMED): ground
# +0.50, top of rail +0.90, platform FFL +2.00, flat canopy soffit +6.00.
def make_at_grade_massing(centre, s_glob, plat_w, plat_l, rail, plat, ground_w=25.0, note=""):
    """DFR Type-E-like at-grade island-platform massing in the STATION's own
    local frame (origin = station centre)."""
    tux_, tuz_ = local_tangent(s_glob)
    cx, cz = 0.0, 0.0
    hr = round(heading_rotY(tux_, tuz_), 4)
    objs = {}
    objs["platform"] = [
        {"kind": "box", "size": [plat_l, 0.4, plat_w], "pos": [cx, round(plat - 0.2, 2), cz], "rotY": hr,
         "color": "#c3c8cd", "meta": {"src": "island platform massing (DFR type)", "assumption": f"length {plat_l} m; width {plat_w} m standard"}},
    ]
    for s_edge in (-plat_l / 2, plat_l / 2):
        objs["platform"].append({"kind": "box", "size": [1.0, 1.2, plat_w],
                                 "pos": [round(cx + tux_ * s_edge, 2), round(plat + 0.6, 2), round(cz + tux_ * s_edge, 2)], "rotY": hr,
                                 "color": "#b7bcc2", "meta": {"src": "platform end wall (ASSUMED)"}})
    for side in (-1, 1):
        objs["platform"].append({"kind": "box", "size": [round(plat_l - 2, 1), 0.06, 0.7],
                                 "pos": [round(cx - tuz_ * side * (plat_w / 2 - 0.35), 2), round(plat + 0.06, 2), round(cz + tux_ * side * (plat_w / 2 - 0.35), 2)], "rotY": hr,
                                 "color": "#d9a821", "meta": {"src": "tactile warning strip (ASSUMED placement)"}})
    objs["tracks"] = []
    for off in (-TRACK_OFF, TRACK_OFF):
        objs["tracks"].append({"kind": "box", "size": [round(plat_l + 40, 1), 0.3, 1.6],
                               "pos": [round(cx - tuz_ * off, 2), round(rail - 0.15, 2), round(cz + tux_ * off, 2)], "rotY": hr,
                               "meta": {"src": "8.8 m spacing through station; rail top (ASSUMED at-grade level)"}})
    objs["floors"] = [{"kind": "box", "size": [round(plat_l + 20, 1), 0.3, ground_w],
                       "pos": [cx, round(0.50 - 0.15, 2), cz], "rotY": hr, "color": "#c9ccd0",
                       "meta": {"src": "ground slab (ASSUMED extent)"}}]
    objs["stairs"] = []
    for s_off in (-plat_l / 2 + 25.0, plat_l / 2 - 25.0):
        objs["stairs"].append({"kind": "box", "size": [6.0, 1.6, 4.0],
                               "pos": [round(cx + tux_ * s_off - tuz_ * (plat_w / 2 + 3.0), 2), 1.3,
                                       round(cz + tuz_ * s_off + tux_ * (plat_w / 2 + 3.0), 2)], "rotY": hr,
                               "meta": {"src": "stair core ground->platform (ASSUMED position)"}})
    objs["piers"] = []
    for s_off in range(int(-plat_l / 2) + 10, int(plat_l / 2) - 9, 30):
        for side in (-1, 1):
            objs["piers"].append({"kind": "cylinder", "radius": 0.35, "height": 5.85,
                                  "pos": [round(cx + tux_ * s_off - tuz_ * side * (plat_w / 2 + 1.5), 2), 5.85 / 2,
                                          round(cz + tux_ * s_off + tux_ * side * (plat_w / 2 + 1.5), 2)],
                                  "meta": {"src": "canopy support column (ASSUMED 30 m spacing)"}})
    objs["canopy_box"] = [{"kind": "box", "size": [round(plat_l + 10, 1), 0.3, ground_w],
                           "pos": [cx, 6.0, cz], "rotY": hr, "color": "#d4d8dc",
                           "meta": {"src": "flat canopy roof (ASSUMED)" + ("; " + note if note else "")}}]
    objs["viaduct_deck"], objs["viaduct_piers"] = approach_deck_in_frame(centre, (tux_, tuz_))
    return objs

fti_objs = make_at_grade_massing(
    FTIc, S_FTI, 8.0, 140.0, 0.90, 2.00,
    note="DFR at-grade design superseded by as-built underground CP NSCR-03-B")
fti_manifest = {
  "name": "FTI Station (NSCR CP S-03b) - JICA massing",
  "crs": "PRS92 PTM Zone III (EPSG:3123), metres",
  "origin_easting": round(FTIc["e"], 2), "origin_northing": round(FTIc["n"], 2),
  "origin_wgs84": {"lat": 14.504494, "lon": 121.036389,
                   "note": "printed coordinate on DFR Fig 4.4.9 (p.485); ~250 m uncertainty"},
  "levels_m": {"ground_ffl": 0.50, "top_of_rail": 0.90, "platform_ffl": 2.00,
               "canopy": 6.0, "note": "ASSUMED - not dimensioned in the DFR"},
  "sources": ["jica_southline_feasibility_dfr.pdf p.195 (Fig 4.2.56), p.500-502 (Type E'), p.485 (siting)",
              "alignment_v3.json centerline",
              "NOTE: DFR at-grade design superseded by as-built underground CP NSCR-03-B station"],
  "objects": fti_objs
}
_atomic_json_dump(fti_manifest, os.path.join(OUT, "fti-massing.json"))
print("FTI massing: platform", len(fti_objs["platform"]), "| approach deck", len(fti_objs["viaduct_deck"]),
      "| s(local)", round(FTI_L, 1))

# ================= Sucat REAL-geometry manifest =============================
# Levels VERIFIED from X_Suc_Sta_Section.dxf texts: GF +1.00, concourse +7.85,
# top of rail +15.50, platform FFL +16.60.
SUC_E0 = SUC["e"]; SUC_N0 = SUC["n"]
SUC_GF, SUC_CC, SUC_TOR, SUC_PLAT = 1.00, 7.85, 15.50, 16.60
SUC_DXF = r"E:\NSCR\pipeline\dxf\CP_S-03c_01_SUC_AR"
SUC_ENV = (505330.0, 1597800.0, 505530.0, 1598300.0)  # entity filter (station envelope)

def extract_wall_segs(paths, layers):
    """LINE/LWPOLYLINE wall segments in PRS92 from the given DXFs/layers."""
    segs = []
    for path in paths:
        doc = ezdxf.readfile(os.path.join(SUC_DXF, path))
        for e in doc.modelspace():
            lay = e.dxf.layer
            if lay not in layers:
                continue
            try:
                if e.dxftype() == 'LINE':
                    cand = [((e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y))]
                elif e.dxftype() == 'LWPOLYLINE':
                    pts = [(p[0], p[1]) for p in e.get_points('xy')]
                    cand = list(zip(pts, pts[1:]))
                else:
                    continue
            except Exception:
                continue
            for (e1, n1), (e2, n2) in cand:
                for (ex, ny) in ((e1, n1), (e2, n2)):
                    if not (SUC_ENV[0] <= ex <= SUC_ENV[2] and SUC_ENV[1] <= ny <= SUC_ENV[3]):
                        break
                else:
                    if math.dist((e1, n1), (e2, n2)) > 0.05:
                        segs.append(((e1, n1), (e2, n2)))
    return segs

suc_gf_segs = extract_wall_segs(["X_Suc_Sta_Ground Floor.dxf"], {"A-WALL", "A-WALL2"})
suc_cc_segs = extract_wall_segs(["X_Suc_Sta_Concourse.dxf"], {"A-WALL"})

def to_local_suc(seg):
    (e1, n1), (e2, n2) = seg
    return (round(e1 - SUC_E0, 2), round(-(n1 - SUC_N0), 2)), (round(e2 - SUC_E0, 2), round(-(n2 - SUC_N0), 2))

suc_walls = wall_boxes(suc_gf_segs, SUC_GF, SUC_CC, to_local_suc, "X_Suc_Sta GF A-WALL") \
          + wall_boxes(suc_cc_segs, SUC_CC, SUC_PLAT, to_local_suc, "X_Suc_Sta_Concourse A-WALL")

stx, stz = local_tangent(S_SUC)
def suc_frame_pt(along_s, offset):
    return [round(stx * along_s - stz * offset, 2), round(stz * along_s + stx * offset, 2)]
suc_hr = round(heading_rotY(stx, stz), 4)

# Platform footprint from A-PLATFORM / A-PSD (Platform plan) -> per-side extents
doc = ezdxf.readfile(os.path.join(SUC_DXF, "X_Suc_Sta_Platform.dxf"))
plat_pts = []
for e in doc.modelspace():
    if e.dxf.layer not in ("A-PLATFORM", "A-PSD", "HANDRAIL", "A-WALL 2"):
        continue
    try:
        if e.dxftype() == 'LINE':
            pts = [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
        elif e.dxftype() == 'LWPOLYLINE':
            pts = [(p[0], p[1]) for p in e.get_points('xy')]
        else:
            continue
    except Exception:
        continue
    for (ex, ny) in pts:
        if SUC_ENV[0] <= ex <= SUC_ENV[2] and SUC_ENV[1] <= ny <= SUC_ENV[3]:
            x, z = ex - SUC_E0, -(ny - SUC_N0)
            plat_pts.append((x * stx + z * stz, x * -stz + z * stx))  # (s, off)
suc_platform = []
sides = []
PLEN = 190.0
PC = 0.0
if plat_pts:
    ss = [p[0] for p in plat_pts]
    PL = min(ss) - 2.0; PH = max(ss) + 2.0
    PC, PLEN = (PL + PH) / 2, PH - PL
    south = sorted(p[1] for p in plat_pts if p[1] < -6.5)
    north = sorted(p[1] for p in plat_pts if p[1] > 6.5)
    if south and north:
        sides = [((south[0] + south[-1]) / 2, (south[-1] - south[0]) / 2),
                 ((north[0] + north[-1]) / 2, (north[-1] - north[0]) / 2)]
    for off_mid, half_w in sides:
        cx, cz = suc_frame_pt(PC, off_mid)
        suc_platform.append({"kind": "box", "size": [round(PLEN, 1), 0.4, round(half_w * 2, 1)],
                             "pos": [cx, round(SUC_PLAT - 0.2, 2), cz], "rotY": suc_hr, "color": "#c3c8cd",
                             "meta": {"src": "X_Suc_Sta_Platform A-PLATFORM/A-PSD/HANDRAIL/A-WALL 2 footprint (per-side extents)"}})
        for edge in (-1, 1):
            ex_, ez_ = suc_frame_pt(PC, off_mid + edge * half_w)
            suc_platform.append({"kind": "box", "size": [round(PLEN - 1, 1), 0.06, 0.7],
                                 "pos": [ex_, round(SUC_PLAT + 0.06, 2), ez_], "rotY": suc_hr, "color": "#d9a821",
                                 "meta": {"src": "tactile warning strip (platform edge)"}})
suc_platform_src = "X_Suc_Sta_Platform A-PLATFORM/A-PSD/HANDRAIL/A-WALL 2 footprint (per-side extents)"
if not suc_platform:
    suc_platform_src = "STANDARD side platforms (A-PLATFORM footprint not parseable) - ASSUMED"
    PLEN = 190.0
    for side in (-1, 1):
        cx, cz = suc_frame_pt(0.0, side * 9.0)
        suc_platform.append({"kind": "box", "size": [PLEN, 0.4, 4.0],
                             "pos": [cx, round(SUC_PLAT - 0.2, 2), cz], "rotY": suc_hr, "color": "#c3c8cd",
                             "meta": {"src": suc_platform_src}})

suc_tracks = []
for off in (-TRACK_OFF, TRACK_OFF):
    cx, cz = suc_frame_pt(PC, off)
    suc_tracks.append({"kind": "box", "size": [round(PLEN + 40, 1), 0.3, 1.6],
                       "pos": [cx, round(SUC_TOR - 0.15, 2), cz], "rotY": suc_hr,
                       "meta": {"src": "8.8 m track spacing (DFR); rail top +15.50 (X_Suc_Sta_Section)"}})

suc_floors = []
for key, base in (("gf", SUC_GF), ("cc", SUC_CC)):
    segs = suc_gf_segs if key == "gf" else suc_cc_segs
    pts = [(e - SUC_E0, -(n - SUC_N0)) for seg in segs for (e, n) in seg]
    if not pts:
        continue
    ssv = [x * stx + z * stz for x, z in pts]
    offv = [x * -stz + z * stx for x, z in pts]
    L = max(ssv) - min(ssv)
    sm = (max(ssv) + min(ssv)) / 2
    W = min(max(offv) - min(offv), 45.0)
    om = (max(offv) + min(offv)) / 2
    cx, cz = suc_frame_pt(sm, om)
    suc_floors.append({"kind": "box", "size": [round(L, 1), 0.3, round(W, 1)],
                       "pos": [cx, round(base - 0.15, 2), cz], "rotY": suc_hr,
                       "color": "#c9ccd0" if key == "gf" else "#d6d9dd",
                       "meta": {"src": "X_Suc_Sta " + ("Ground Floor" if key == "gf" else "Concourse") + " wall projection", "elev": base}})

suc_stairs = []
for s_off in (-PLEN / 2 + 15, PLEN / 2 - 15):
    for by, ty in ((SUC_GF, SUC_CC), (SUC_CC, SUC_PLAT)):
        suc_stairs.append({"kind": "box", "size": [6.0, ty - by, 4.0],
                           "pos": [round(stx * (PC + s_off), 2), round((by + ty) / 2, 2), round(stz * (PC + s_off), 2)],
                           "meta": {"src": "regularized stair core (A-STAIRS clusters in Sucat plans)"}})

suc_dx_bic, suc_dz_bic = SUC_E0 - E0, -(SUC_N0 - N0)  # Sucat centre in Bicutan frame
suc_vd, suc_vp = approach_deck_in_frame(SUC, (stx, stz))

suc_manifest = {
  "name": "Sucat Station (NSCR CP S-03c)",
  "crs": "PRS92 PTM Zone III (EPSG:3123), metres",
  "origin_easting": round(SUC_E0, 2), "origin_northing": round(SUC_N0, 2),
  "origin_wgs84": {"lat": STN["sucat"]["center_wgs84"]["lat"], "lon": STN["sucat"]["center_wgs84"]["lon"]},
  "levels_m": {"ground_ffl": SUC_GF, "concourse_ffl": SUC_CC, "top_of_rail": SUC_TOR, "platform_ffl": SUC_PLAT,
               "note": "VERIFIED from X_Suc_Sta_Section.dxf level texts"},
  "sources": ["X_Suc_Sta_Ground Floor.dxf", "X_Suc_Sta_Concourse.dxf", "X_Suc_Sta_Platform.dxf",
              "X_Suc_Sta_Section.dxf (levels)", "alignment_v3.json", "stations_north_south.json"],
  "meta": {
    "geometry": "REAL walls from A-WALL layers; platform footprint from " + suc_platform_src,
    "assumptions": ["wall thickness 0.25 m (as Bicutan)",
                    "no vault/lattice: Sucat section shows a rigid-frame roof, not extracted",
                    "stairs regularized", "approach viaduct simplified U-girders from the corridor model"],
  },
  "objects": {"walls": suc_walls, "platform": suc_platform, "tracks": suc_tracks,
              "stairs": suc_stairs, "floors": suc_floors,
              "viaduct_deck": suc_vd, "viaduct_piers": suc_vp}
}
_atomic_json_dump(suc_manifest, os.path.join(OUT, "sucat-real.json"))
print("Sucat: gf walls", len(suc_gf_segs), "| cc walls", len(suc_cc_segs), "| platform objs", len(suc_platform),
      "| approach deck", len(suc_vd), "| s(local)", round(g2l(S_SUC), 1))

# ================= Senate-DepEd (BUE) + EDSA massing ========================
def make_elevated_massing(centre, s_glob, bbox):
    """Type C'-like elevated massing, Bicutan-like levels (ASSUMED, flagged)."""
    tux_, tuz_ = local_tangent(s_glob)
    hr = round(heading_rotY(tux_, tuz_), 4)
    corners = [(bbox["min_e"], bbox["min_n"]), (bbox["max_e"], bbox["min_n"]),
               (bbox["max_e"], bbox["max_n"]), (bbox["min_e"], bbox["max_n"])]
    ss, offs = [], []
    for (ex, ny) in corners:
        x, z = ex - centre["e"], -(ny - centre["n"])
        ss.append(x * tux_ + z * tuz_)
        offs.append(x * -tuz_ + z * tux_)
    L = max(ss) - min(ss); W = min(max(offs) - min(offs), 45.0)
    sm, om = (max(ss) + min(ss)) / 2, (max(offs) + min(offs)) / 2
    def fp(along, off):
        return [round(tux_ * along - tuz_ * off, 2), round(tuz_ * along + tux_ * off, 2)]
    objs = {"platform": [], "tracks": [], "floors": [], "stairs": [], "piers": []}
    PLAT_TOP = 11.90
    for side in (-1, 1):
        cx, cz = fp(sm, side * 9.0)
        objs["platform"].append({"kind": "box", "size": [round(L, 1), 0.4, 4.0],
                                 "pos": [cx, round(PLAT_TOP - 0.2, 2), cz], "rotY": hr, "color": "#c3c8cd",
                                 "meta": {"src": "side platform massing (ASSUMED - Bicutan-like; no arch DWGs parsed)"}})
    for off in (-TRACK_OFF, TRACK_OFF):
        cx, cz = fp(sm, off)
        objs["tracks"].append({"kind": "box", "size": [round(L + 20, 1), 0.3, 1.6],
                               "pos": [cx, 10.65, cz], "rotY": hr,
                               "meta": {"src": "8.8 m track spacing, TOR +10.80 (ASSUMED Bicutan-like)"}})
    cx, cz = fp(sm, om)
    objs["floors"].append({"kind": "box", "size": [round(L, 1), 0.3, round(W, 1)],
                           "pos": [cx, 0.35, cz], "rotY": hr, "color": "#c9ccd0",
                           "meta": {"src": "ground slab from DXF bbox projection"}})
    objs["floors"].append({"kind": "box", "size": [round(L - 10, 1), 0.3, 38.5],
                           "pos": [cx, 4.45, cz], "rotY": hr, "color": "#d6d9dd",
                           "meta": {"src": "concourse slab (ASSUMED +4.60, Bicutan-like)"}})
    for s_off in (-L / 2 + 15, L / 2 - 15):
        for by, ty in ((0.50, 4.60), (4.60, 11.90)):
            sx, sz = fp(s_off, om)
            objs["stairs"].append({"kind": "box", "size": [6.0, ty - by, 4.0],
                                   "pos": [sx, round((by + ty) / 2, 2), sz],
                                   "meta": {"src": "regularized stair core (ASSUMED)"}})
    for s_off in range(int(-L / 2) + 10, int(L / 2) - 9, 30):
        for side in (-1, 1):
            px, pz = fp(s_off, side * 11.0)
            objs["piers"].append({"kind": "cylinder", "radius": 0.5, "height": 15.3,
                                  "pos": [px, 15.3 / 2, pz],
                                  "meta": {"src": "elevated station support column (ASSUMED 30 m spacing)"}})
    objs["canopy_box"] = [{"kind": "box", "size": [round(L + 10, 1), 0.4, round(W + 6, 1)],
                           "pos": [cx, 16.5, cz], "rotY": hr, "color": "#d4d8dc",
                           "meta": {"src": "flat canopy roof massing (ASSUMED soffit +16.5, just above top-of-beam +15.9)"}}]
    objs["viaduct_deck"], objs["viaduct_piers"] = approach_deck_in_frame(centre, (tux_, tuz_))
    return objs

bue_objs = make_elevated_massing(BUE, S_BUE, STN["senate-deped_bue"]["bbox_prs92"])
bue_manifest = {
  "name": "Senate-DepEd Station (NSCR BUE set) - massing",
  "crs": "PRS92 PTM Zone III (EPSG:3123), metres",
  "origin_easting": round(BUE["e"], 2), "origin_northing": round(BUE["n"], 2),
  "origin_wgs84": {"lat": STN["senate-deped_bue"]["center_wgs84"]["lat"], "lon": STN["senate-deped_bue"]["center_wgs84"]["lon"]},
  "levels_m": {"ground_ffl": 0.50, "concourse_ffl": 4.60, "top_of_rail": 10.80, "platform_ffl": 11.90,
               "note": "ASSUMED Bicutan-like (Type C' elevated) - no section sheet parsed for BUE"},
  "sources": ["stations_north_south.json bbox_prs92 (X_Bue_Sta_Intermediate Floor Level 2.dxf)",
              "JICA DFR p.500 Table 4.4.3 (Type C')", "alignment_v3.json"],
  "meta": {"assumptions": ["all levels Bicutan-like (flagged)", "platform width/offset standard", "stairs/canopy regularized"]},
  "objects": bue_objs
}
_atomic_json_dump(bue_manifest, os.path.join(OUT, "senate-deped-massing.json"))
print("BUE massing:", {k: len(as_list(v)) for k, v in bue_objs.items()}, "| s(local)", round(BUE_L, 1))

edsa_objs = make_at_grade_massing(
    EDS, S_EDS, 8.0, 200.0, 0.90, 2.00,
    note="Type E at-grade island platform, FTI-like levels (ASSUMED)")
edsa_manifest = {
  "name": "EDSA Station (NSCR) - massing",
  "crs": "PRS92 PTM Zone III (EPSG:3123), metres",
  "origin_easting": round(EDS["e"], 2), "origin_northing": round(EDS["n"], 2),
  "origin_wgs84": {"lat": STN["edsa"]["center_wgs84"]["lat"], "lon": STN["edsa"]["center_wgs84"]["lon"]},
  "levels_m": {"ground_ffl": 0.50, "top_of_rail": 0.90, "platform_ffl": 2.00, "canopy": 6.0,
               "note": "ASSUMED FTI-like (Type E at-grade) - no section sheet parsed for EDSA"},
  "sources": ["stations_north_south.json bbox_prs92 (X_EDS_SS-ST-CONCOURSE FLOOR FRAMING PLAN.dxf)",
              "JICA DFR p.500 Table 4.4.3 (Type E)", "alignment_v3.json"],
  "meta": {"assumptions": ["all levels FTI-like (flagged)", "island platform 200 m x 8 m", "stairs/canopy regularized"]},
  "objects": edsa_objs
}
_atomic_json_dump(edsa_manifest, os.path.join(OUT, "edsa-massing.json"))
print("EDSA massing:", {k: len(as_list(v)) for k, v in edsa_objs.items()})

# ================= Line manifests ===========================================
# line-bicutan-fti.json (kept, v1.0.0) and line-corridor.json (all 5 stations).
POS_KEYS = ("platform", "tracks", "floors", "stairs", "piers", "canopy_box", "walls")
def to_world(objs, dx, dz):
    out = {}
    for k, v in objs.items():
        if k in POS_KEYS:
            out[k] = rebase(as_list(v), dx, dz)
    return out

bue_world = to_world(bue_objs, BUE["e"] - E0, -(BUE["n"] - N0))
edsa_world = to_world(edsa_objs, EDS["e"] - E0, -(EDS["n"] - N0))
fti_world = to_world(fti_objs, fti_x, fti_z)
suc_world = to_world({"walls": suc_walls, "platform": suc_platform, "tracks": suc_tracks,
                      "stairs": suc_stairs, "floors": suc_floors}, suc_dx_bic, suc_dz_bic)

def merge(*dicts):
    out = {}
    for d in dicts:
        for k, v in d.items():
            out.setdefault(k, [])
            out[k] = out[k] + as_list(v)
    return out

bic_core = {"walls": walls, "platform": platform, "tracks": tracks, "piers": piers, "stairs": stairs,
            "floors": floors, "vault": vault, "lattice": lattice, "beams": beams,
            "viaduct_deck": viaduct_deck, "viaduct_piers": viaduct_piers}

line_fti_objects = merge(bic_core, fti_world)
line_fti = {
  "name": "Bicutan <-> FTI (line, v1.0.0)",
  "crs": "PRS92 PTM Zone III (EPSG:3123), metres",
  "origin_easting": round(E0, 2), "origin_northing": round(N0, 2),
  "origin_wgs84": {"lat": 14.488419, "lon": 121.045368},
  "levels_m": {"ground_ffl": 0.50, "concourse_ffl": 4.60, "top_of_rail": 10.80, "platform_ffl": 11.90, "roof": 24.70},
  "sources": ["bicutan-real.json objects", "fti-massing.json objects (rebased)", "alignment_v3.json deck"],
  "objects": line_fti_objects
}
_atomic_json_dump(line_fti, os.path.join(OUT, "line-bicutan-fti.json"))
print("line-bicutan-fti written:", sum(len(v) for v in line_fti_objects.values()), "objects")

line_corridor_objects = merge(bic_core, fti_world, suc_world, bue_world, edsa_world)
line_corridor = {
  "name": "Bicutan <-> Sucat / Bicutan <-> EDSA-BUE (corridor, v1.0.0)",
  "crs": "PRS92 PTM Zone III (EPSG:3123), metres",
  "origin_easting": round(E0, 2), "origin_northing": round(N0, 2),
  "origin_wgs84": {"lat": 14.488419, "lon": 121.045368},
  "levels_m": {"ground_ffl": 0.50, "concourse_ffl": 4.60, "top_of_rail": 10.80, "platform_ffl": 11.90, "roof": 24.70},
  "sources": ["bicutan-real.json", "fti-massing.json", "sucat-real.json", "senate-deped-massing.json",
              "edsa-massing.json (all rebased to the Bicutan frame)", "alignment_v3.json full-corridor deck"],
  "meta": {"stations_s_local": {"sucat": round(SUC_L, 1), "bicutan": round(BIC_C, 1), "fti": round(FTI_L, 1),
                                 "edsa": round(EDS_L, 1), "bue": round(BUE_L, 1)},
            "s_note": "s = arclength of the assembled alignment_v3 point array relative to the Bicutan frame origin; "
                      "alignment_v3.json's own stations_s use a nominal axis that ignores the OSM splice lengths",
            "deck_profile": "elevated +10.6 at Sucat/Bicutan/BUE, at-grade +0.6 at FTI/EDSA, linear ramps between"},
  "objects": line_corridor_objects
}
_atomic_json_dump(line_corridor, os.path.join(OUT, "line-corridor.json"))
print("line-corridor written:", sum(len(v) for v in line_corridor_objects.values()), "objects")
sizes = {f: os.path.getsize(os.path.join(OUT, f)) // 1024 for f in sorted(os.listdir(OUT)) if f.endswith(".json")}
print("data dir KB:", sizes)
