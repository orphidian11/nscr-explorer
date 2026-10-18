"""Build Bicutan station 3D manifest from CAD-extracted DXF geometry.

Sources (all ezdxf-parsed, georeferenced PRS92 Zone III / EPSG:3123, metres):
  - X_Bic_Sta_Ground Floor.dxf  WALL/A-WALL segments -> ground-level walls, FFL +0.50
  - X_Bic_Sta_Concourse.dxf     A-WALL segments      -> concourse walls, FFL +4.60
  - X_Bic_Sta_Platform.dxf      A-SLAB/A-BALUSTRADE   -> platform slab outline, FFL +11.90
Levels from X_Bic_Sta_Section.dxf dimension texts (verified):
  GF +0.50 | Concourse +4.60 | Top of rail +10.80 | Platform FFL +11.90 | Beam +15.90 | Roof +24.70
Local frame: x = (E - E0), z = -(N - N0), y = elevation. Origin = wall-bbox centre.
"""
import ezdxf, os, json, math

XREF = r"E:\NSCR\pipeline\dxf\xrefs"
OUT = r"E:\NSCR\app\src\data\bicutan-real.json"
SEGS = json.load(open(r"E:\NSCR\pipeline\wall_segments.json"))

E0 = None; N0 = None  # set below
WALL_T = 0.25  # wall thickness, m (assumption; refine from double-line spacing)

import os as _os

def _atomic_json_dump(obj, path, attempts=5):
    # Windows: the dev server's watcher can briefly lock the target — retry,
    # and fall back to a plain in-place write if replace keeps failing.
    import time as _time
    tmp = path + ".tmp"
    for i in range(attempts):
        try:
            with open(tmp, "w") as fh:
                json.dump(obj, fh, indent=1)
            _os.replace(tmp, path)
            return
        except PermissionError:
            _time.sleep(0.5 * (i + 1))
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=1)

def all_bbox(segs_list):
    pts = [p for segs in segs_list for s in segs for p in s]
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)

b = all_bbox([SEGS["gf"], SEGS["cc"], SEGS["pl"]])
E0, N0 = (b[0]+b[2])/2, (b[1]+b[3])/2

def to_local(seg):
    (e1,n1),(e2,n2) = seg
    return (round(e1-E0,2), round(-(n1-N0),2)), (round(e2-E0,2), round(-(n2-N0),2))

def wall_boxes(segs, base_y, top_y):
    boxes = []
    for seg in segs:
        (x1,z1),(x2,z2) = to_local(seg)
        L = math.dist((x1,z1),(x2,z2))
        cx, cz = (x1+x2)/2, (z1+z2)/2
        ang = math.degrees(math.atan2(z2-z1, x2-x1))
        boxes.append({"kind":"box","size":[round(L+WALL_T,2), round(top_y-base_y,2), WALL_T],
                      "pos":[round(cx,2), round((base_y+top_y)/2,2), round(cz,2)],
                      "rotY": round(-math.radians(ang),4),
                      "meta":{"src":"X_Bic_Sta wall segment","base":base_y,"top":top_y}})
    return boxes

walls = wall_boxes(SEGS["gf"], 0.50, 4.60) + wall_boxes(SEGS["cc"], 4.60, 11.90)

# --- NSCR main-alignment loading (viaduct.json, X_DD_NSRP_Main_Alignment) ---
# 201 sampled [e,n] pts every 10 m, +/-1000 m along the alignment through Bicutan.
# Needed before the tracks: the station long axis (and tracks) runs PARALLEL to
# the alignment (~63 deg in the local XZ frame), not along local x.
ALX = json.load(open(r"E:\NSCR\pipeline\alignment_extended.json"))
al_pts = [(p[0] - E0, -(p[1] - N0)) for p in ALX["points"]
          if p is not None and p[0] is not None and p[1] is not None]  # local x,z, +/-4 km
assert len(al_pts) == len(ALX["points"]), 'null points in alignment_extended.json'
# FTI station (fti.json): Type E' at-grade, island platform, 25 m wide, ~140 m long.
# PRS92 centre; along-track s from the extended alignment. Design superseded by the
# as-built underground station (CP NSCR-03-B) - rendered as DFR-design massing.
FTI = json.load(open(r"E:\NSCR\pipeline\fti.json"))
fti_x, fti_z = FTI["center_prs92"]["e"] - E0, -(FTI["center_prs92"]["n"] - N0)

# Closest-approach point = local s=0; near-station tangent defines "along".
d0 = min(range(len(al_pts)), key=lambda i: math.hypot(*al_pts[i]))
_j = min(d0 + 1, len(al_pts) - 1)
tux, tuz = al_pts[_j][0] - al_pts[d0][0], al_pts[_j][1] - al_pts[d0][1]
tl = math.hypot(tux, tuz); tux, tuz = tux / tl, tuz / tl

# Station extent along the alignment: project every wall-segment endpoint
# (bbox corners would overstate it for the rotated footprint).
def lerp_pt(p1, p2, t):
    return (p1[0] + (p2[0] - p1[0]) * t, p1[1] + (p2[1] - p1[1]) * t)

def heading_rotY(dx, dz):
    return -math.atan2(dz, dx)  # three.js rotY aligning box +x with (dx,dz)

_s_all = [x * tux + z * tuz for key in ("gf", "cc", "pl") for seg in SEGS[key]
          for (x, z) in ((e - E0, -(n - N0)) for (e, n) in seg)]
S_LO, S_HI = min(_s_all), max(_s_all)
FTI_S = fti_x * tux + fti_z * tuz          # along-track s of FTI centre
FTI_HALF = 75.0                            # 140 m footprint + margin (estimate, not dimensioned)
FTI_LO, FTI_HI = FTI_S - FTI_HALF, FTI_S + FTI_HALF
STATION_BOXES = sorted([(S_LO, S_HI), (FTI_LO, FTI_HI)])  # sorted: clip sweep assumes ordered boxes
assert all(STATION_BOXES[i][1] < STATION_BOXES[i+1][0] for i in range(len(STATION_BOXES)-1)), 'station boxes overlap'
# Deck level: Bicutan elevated at BASE_Y; descends to at-grade FTI (rail base +0.60)
# across the run between the two station boxes (simplification of the real gradient).
FTI_BASE_Y = 0.60
def deck_base_y(s):
    if s >= S_HI:  # between the stations
        t = min(max((s - S_HI) / max(FTI_LO - S_HI, 1.0), 0.0), 1.0)
        return BASE_Y + (FTI_BASE_Y - BASE_Y) * t
    if s <= S_LO:  # south of Bicutan stays elevated (no second station in window)
        return BASE_Y
    return BASE_Y

# Tracks: along the alignment axis through the station centre, top of rail +10.80
# (from Section dims). 8.8 m track spacing per section DIMS (X_Bic_Sta_Section.dxf)
# -> +/-4.4 m perpendicular to the centreline. Length spans the station footprint
# along the alignment. (Earlier renders had tracks along local x - perpendicular
# to the real alignment; now oriented along the alignment tangent.)
TRACK_OFF = 4.4       # track centreline offset from alignment (8.8 m spacing)
alT = S_HI - S_LO
alC = (S_LO + S_HI) / 2
tracks = []
for off in (-TRACK_OFF, TRACK_OFF):
    tracks.append({"kind": "box", "size": [round(alT + 2, 1), 0.3, 1.6],
                   "pos": [round(tux * alC - tuz * off, 2), 10.65, round(tuz * alC + tux * off, 2)],
                   "rotY": round(heading_rotY(tux, tuz), 4),
                   "meta": {"src": "typical double track along NSCR alignment, 8.8 m spacing per section DIMS (+/-4.4 m), TOR +10.80"}})

# Platform: TWO SIDE PLATFORMS from the real balustrade footprint (X_Bic_Sta_Platform
# A-BALUSTRADE): end walls at E 504690.7-504698.5 (N end) and 504773.7-504781.4 (S end),
# 4.0 m across-track. Platform edges at ~7.0 m offset from the centreline (the 6.97 m
# section dim = U-girder outer edge 4.4+2.57), so each side platform is ~4 m wide
# centred at +/-9.0 m. Top +11.90 (1.1 m above rail top +10.80). Yellow tactile
# strips + inner-edge parapets added as detail.
PLAT_HALF_W = 2.0     # half of the 4.0 m across-track width
PLAT_OFF = 9.0        # side-platform centre offset from centreline
PLAT_TOP = 11.90

def track_frame_pt(along_s, offset):
    # point at along-offset s and across-track offset from the centreline
    return [round(tux * along_s - tuz * offset, 2), round(tuz * along_s + tux * offset, 2)]

# along-track s interval of the platform: project the two end-wall centres
_end_n = (504694.6 - E0, -(1602447.25 - N0))
_end_s = (504777.55 - E0, -(1602286.4 - N0))
s_n = _end_n[0] * tux + _end_n[1] * tuz
s_s = _end_s[0] * tux + _end_s[1] * tuz
P_LO, P_HI = min(s_n, s_s) - 3.9, max(s_n, s_s) + 3.9   # extend past the end walls
P_C = (P_LO + P_HI) / 2
P_LEN = P_HI - P_LO
L_along = P_LEN  # platform along-track extent (stairs regularisation + reference)

platform = []
for side in (-1, 1):
    cx, cz = track_frame_pt(P_C, side * PLAT_OFF)
    # main slab (top at PLAT_TOP)
    platform.append({"kind": "box", "size": [round(P_LEN, 1), 0.4, PLAT_HALF_W * 2],
                     "pos": [cx, round(PLAT_TOP - 0.2, 2), cz],
                     "rotY": round(heading_rotY(tux, tuz), 4),
                     "color": "#c3c8cd",
                     "meta": {"src": "X_Bic_Sta_Platform A-BALUSTRADE footprint; side platform, edge ~7.0 m offset (6.97 m dim)"}})
    # tactile warning strip along the inner (track-side) edge, yellow
    tx, tz = track_frame_pt(P_C, side * (PLAT_OFF - PLAT_HALF_W + 0.35))
    platform.append({"kind": "box", "size": [round(P_LEN - 1.0, 1), 0.06, 0.7],
                     "pos": [tx, round(PLAT_TOP + 0.06, 2), tz],
                     "rotY": round(heading_rotY(tux, tuz), 4),
                     "color": "#d9a821",
                     "meta": {"src": "tactile warning strip (standard PT detail)"}})
    # inner-edge parapet/handrail
    px, pz = track_frame_pt(P_C, side * (PLAT_OFF - PLAT_HALF_W - 0.05))
    platform.append({"kind": "box", "size": [round(P_LEN, 1), 1.2, 0.12],
                     "pos": [px, round(PLAT_TOP + 0.6, 2), pz],
                     "rotY": round(heading_rotY(tux, tuz), 4),
                     "color": "#b7bcc2",
                     "meta": {"src": "inner-edge balustrade (A-BALUSTRADE line)"}})

# end walls from the real balustrade bboxes (7.8 x 4.0 m at each platform end)
for cE, cN in ((504694.6, 1602447.25), (504777.55, 1602286.4)):
    ex, ez = cE - E0, -(cN - N0)
    platform.append({"kind": "box", "size": [round(7.8, 1), 1.4, 4.0],
                     "pos": [round(ex, 2), round(PLAT_TOP + 0.7, 2), round(ez, 2)],
                     "rotY": round(heading_rotY(tux, tuz), 4),
                     "color": "#b7bcc2",
                     "meta": {"src": "X_Bic_Sta_Platform A-BALUSTRADE end wall (real bbox)"}})


# --- Real structural columns (X_BIC-ST-FOUNDATION PLAN via columns.json) ---
# 2.1 m = real column pad width; 5.4 / 6.8 m sizes are PILE-CAP pad sizes,
# not column widths — all are rendered as slender r=0.5 m cylinders.
COLUMNS = json.load(open(r"E:\NSCR\pipeline\columns.json"))["columns"]
piers = []
for col in COLUMNS:
    x, z = col["e"] - E0, -(col["n"] - N0)
    piers.append({"kind": "cylinder", "radius": 0.5, "height": 15.85,
                  "pos": [round(x, 2), round(15.85 / 2, 2), round(z, 2)],
                  "meta": {"src": "foundation plan column pad (columns.json)",
                           "pad_size_m": col["size"],
                           "note": "5.4/6.8 m are pile-cap pad sizes, not column widths"}})

# --- Barrel-vault canopy (canopy.json roof_profile + ridge) ---
CANOPY = json.load(open(r"E:\NSCR\pipeline\canopy.json"))
prof = CANOPY["roof_profile"]["points"]  # [[sheet easting, elev], ...]
apex_e = max(prof, key=lambda p: p[1])[0]          # sheet easting of apex
mid_e = (min(p[0] for p in prof) + max(p[0] for p in prof)) / 2
assert abs(apex_e - mid_e) < 0.5, f"apex {apex_e} off profile mid {mid_e}"
# Profile 'easting' is the TRANSVERSE direction in the rotated section sheet
# frame; the apex sits on the station centreline, so across-track offset =
# sheet_easting - apex_easting (metres, +/- about the centreline).
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

# --- Facade lattice (A-CLAD FRAMING outlines, plan view) ---
# 2D plan polylines without height -> thin 0.08 m frames extruded +0 -> +15.9.
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

# Stair cores ground->concourse->platform at the two ends of the concourse (from GF A-STAIRS clusters)
stairs = []
for z in (-30, 30):
    for lvl,(by,ty) in enumerate([(0.50,4.60),(4.60,11.90)]):
        stairs.append({"kind":"box","size":[6.0, ty-by, 4.0],
                       "pos":[round(-L_along/2+10 + lvl*8,1), round((by+ty)/2,2), z],
                       "meta":{"src":"regularized stair core (A-STAIRS clusters seen in GF/Platform plans)"}})



# --- Framing beams (framing.json, GL +9.750 level) ---
# Portal beams under the tracks at +9.75 (1.0 m wide), longitudinal beams; all
# georeferenced PRS92 (extract_framing.py). Rendered as boxes along their segments.
FR = json.load(open(r"E:\NSCR\pipeline\framing.json"))
beams = []
for lvl in FR["levels"]:
    if lvl["name"] != "GL +9.750":
        continue
    elev = lvl["elev"]
    for b in lvl["beams"]:
        w = b["width_m"]
        for (e1, n1), (e2, n2) in b["segments"]:
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
                          "meta": {"src": "framing.json GL +9.750 " + b["kind"], "width_m": w}})

# --- Walkable floor slabs ---
# Ground +0.50 and concourse +4.60 plates. Footprint from the ACTUAL wall-segment
# endpoints projected onto the alignment frame (axis-aligned bboxes overstate a
# rotated footprint by ~30% per axis). Concourse clamped to the 38.5 m grid width.
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

# --- NSCR main-alignment viaduct (reuses al_pts/tangent/extent loaded above) ---
# Per-track U-girders at +/-4.4 m (8.8 m spacing, section DIMS), simplified as
# 3 boxes per segment (base slab + 2 webs); piers every 40 m (CAD pier markers),
# twin 0.5 m columns + cap beam. Deck segments are trimmed to abut the station
# footprint ends (projected onto the near-station alignment tangent) - no gap/overlap.
DECK_W = 5.14         # U-girder outer width per track (section DIMS)
WEB_T = 0.3           # web thickness (simplification)
BASE_T = 0.3          # base slab thickness
WEB_H = 1.2           # web height above base slab
BASE_Y = 10.6         # top of base slab = rail base level; rails at +10.80

viaduct_deck = []   # U-girder boxes (base + webs); pier caps appended here too
viaduct_piers = []  # 0.5 m columns (cylinders)
for i in range(len(al_pts) - 1):
    p1, p2 = al_pts[i], al_pts[i + 1]
    s1, s2 = p1[0] * tux + p1[1] * tuz, p2[0] * tux + p2[1] * tuz
    lo, hi = min(s1, s2), max(s1, s2)
    # Clip the 10-m segment against BOTH station boxes; emit the outside parts.
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
    # At-grade bed through the FTI box: base slab only (ballast bed), no webs.
    bed_span = (max(lo, FTI_LO), min(hi, FTI_HI))
    if not spans and bed_span[1] - bed_span[0] < 1.0:
        continue
    L = math.dist(p1, p2)
    dx, dz = (p2[0] - p1[0]) / L, (p2[1] - p1[1]) / L
    rot = heading_rotY(dx, dz)
    perp = (dz, -dx)  # across-track unit (x,z)
    def emit_deck(sa, sb, base_mid, webs=True, src_note="alignment_extended U-girder (simplified)"):
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
        emit_deck(sa, sb, deck_base_y((sa + sb) / 2))
    if bed_span[1] - bed_span[0] >= 1.0:
        emit_deck(bed_span[0], bed_span[1], FTI_BASE_Y, webs=False,
                  src_note="at-grade track bed through FTI (Type E' at-grade design)")

# Piers every 40 m along the alignment (every 4th 10-m sample = CAD pier spacing),
# skipped inside the station box. Twin 0.5 m columns ground(+1.0)->+10.0 plus a
# cap beam (5.6 across x 0.8 x 2.5 along) at +10.2, abutting the deck soffit.
for i in range(0, len(al_pts), 4):
    p = al_pts[i]
    s = p[0] * tux + p[1] * tuz
    if any(b_lo <= s <= b_hi for (b_lo, b_hi) in STATION_BOXES):
        continue
    q2 = al_pts[min(i + 1, len(al_pts) - 1)]
    rot = heading_rotY(q2[0] - p[0], q2[1] - p[1])
    L = math.dist(p, q2) or 1.0
    perp = ((q2[1] - p[1]) / L, -(q2[0] - p[0]) / L)
    py = deck_base_y(s)  # local deck base; columns rise from ground to the soffit
    col_h = max(py - 0.6, 1.0)
    for off in (-1.5, 1.5):
        viaduct_piers.append({"kind": "cylinder", "radius": 0.5, "height": round(col_h, 2),
                              "pos": [round(p[0] + perp[0] * off, 2), round(col_h / 2, 2), round(p[1] + perp[1] * off, 2)],
                              "meta": {"src": "alignment_extended twin pier column, 40 m spacing (CAD pier markers)"}})
    viaduct_deck.append({"kind": "box", "size": [2.5, 0.8, 5.6],
                         "pos": [round(p[0], 2), round(py - 0.4, 2), round(p[1], 2)], "rotY": round(rot, 4),
                         "meta": {"src": "alignment_extended pier cap beam (rendered with deck layer; schema keeps piers cylinders-only)"}})

manifest = {
  "name": "Bicutan Station (NSCR CP S-03c)",
  "crs": "PRS92 PTM Zone III (EPSG:3123), metres",
  "origin_easting": round(E0,2), "origin_northing": round(N0,2),
  "origin_wgs84": {"lat": 14.48748, "lon": 121.04571,
                   "note": "approx; refine by transforming origin_easting/northing via PROJ EPSG:3123->4326"},
  "levels_m": {"ground_ffl":0.50,"concourse_ffl":4.60,"top_of_rail":10.80,"platform_ffl":11.90,
               "top_of_beam":15.90,"roof":24.70},
  "sources": ["X_Bic_Sta_Ground Floor.dxf","X_Bic_Sta_Concourse.dxf","X_Bic_Sta_Platform.dxf",
              "X_Bic_Sta_Section.dxf","foundation plan (columns.json)","facade A-CLAD (canopy.json)",
              "main alignment + viaduct section (viaduct.json)"],
  "objects": {"walls": walls, "platform": platform, "tracks": tracks,
              "piers": piers, "stairs": stairs, "vault": vault, "lattice": lattice,
              "viaduct_deck": viaduct_deck, "viaduct_piers": viaduct_piers,
              "beams": beams, "floors": floors}
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
_atomic_json_dump(manifest, OUT)
print("walls:", len(walls), "| piers:", len(piers), "| tracks:", len(tracks), "| stairs:", len(stairs),
      "| lattice segs:", len(lattice), "| vault profile pts:", len(profile_offsets))
print("viaduct deck boxes:", len(viaduct_deck), "| viaduct pier columns:", len(viaduct_piers),
      "| station extent along alignment:", round(S_LO,1), "to", round(S_HI,1), "m")
print("origin E,N:", round(E0,2), round(N0,2), "| along-track length:", round(L_along,1), "m")
print("written:", OUT, os.path.getsize(OUT)//1024, "KB")


# ================= FTI station manifest (v0.7.0) =================
# JICA DFR Type E' at-grade design (superseded by the as-built underground CP
# NSCR-03-B station - rendered as the DFR massing). NOT from arch DWGs: every
# element below carries a flagged assumption in meta. Same origin frame as
# Bicutan so the viaduct geometry is shared.
# Levels (ASSUMED): ground +0.50, top of rail +0.90, platform FFL +2.00
# (1.1 m above rail), flat canopy soffit +6.00.
FTI_PLATFORM_W = 8.0    # island platform between the tracks
FTI_PLATFORM_L = 140.0  # footprint length estimate (not dimensioned in DFR)
FTI_RAIL = 0.90
FTI_PLAT = 2.00

fti_platform = []
# Local frame is FTI-CENTRED (origin_easting/northing = FTI centre) so the OSM
# ground tiles (anchored at origin_wgs84 = FTI) align with the geometry.
cx, cz = 0.0, 0.0
fti_platform.append({"kind": "box", "size": [FTI_PLATFORM_L, 0.4, FTI_PLATFORM_W],
                     "pos": [round(cx, 2), round(FTI_PLAT - 0.2, 2), round(cz, 2)],
                     "rotY": round(heading_rotY(tux, tuz), 4), "color": "#c3c8cd",
                     "meta": {"src": "JICA DFR Type E' island platform (p.195, p.500-502)",
                              "assumption": "length 140 m estimate; width 25 m standard"}})
for s_edge in (-FTI_PLATFORM_L / 2, FTI_PLATFORM_L / 2):
    ex = cx + tux * s_edge
    ez = cz + tuz * s_edge
    fti_platform.append({"kind": "box", "size": [1.0, 1.2, FTI_PLATFORM_W],
                         "pos": [round(ex, 2), round(FTI_PLAT + 0.6, 2), round(ez, 2)],
                         "rotY": round(heading_rotY(tux, tuz), 4), "color": "#b7bcc2",
                         "meta": {"src": "platform end wall (ASSUMED)"}})
# tactile strips on both platform edges
for side in (-1, 1):
    tx = cx + (-tuz) * side * (FTI_PLATFORM_W / 2 - 0.35)
    tz = cz + tux * side * (FTI_PLATFORM_W / 2 - 0.35)
    fti_platform.append({"kind": "box", "size": [round(FTI_PLATFORM_L - 2, 1), 0.06, 0.7],
                         "pos": [round(tx, 2), round(FTI_PLAT + 0.06, 2), round(tz, 2)],
                         "rotY": round(heading_rotY(tux, tuz), 4), "color": "#d9a821",
                         "meta": {"src": "tactile warning strip (ASSUMED placement)"}})

fti_tracks = []
for off in (-TRACK_OFF, TRACK_OFF):
    fti_tracks.append({"kind": "box", "size": [round(FTI_PLATFORM_L + 40, 1), 0.3, 1.6],
                       "pos": [round(cx + (-tuz) * off, 2), round(FTI_RAIL - 0.15, 2), round(cz + tux * off, 2)],
                       "rotY": round(heading_rotY(tux, tuz), 4),
                       "meta": {"src": "8.8 m spacing through FTI; rail top +0.90 (ASSUMED at-grade level)"}})

fti_floors = [{"kind": "box", "size": [round(FTI_PLATFORM_L + 20, 1), 0.3, 25.0],
               "pos": [round(cx, 2), round(0.50 - 0.15, 2), round(cz, 2)],
               "rotY": round(heading_rotY(tux, tuz), 4), "color": "#c9ccd0",
               "meta": {"src": "Type E' ground slab, 25 m width standard (ASSUMED extent)"}}]

fti_stairs = []
for s_off in (-45.0, 45.0):
    sx = cx + tux * s_off
    sz = cz + tuz * s_off
    fti_stairs.append({"kind": "box", "size": [6.0, 1.6, 4.0],
                       "pos": [round(sx - tuz * (FTI_PLATFORM_W / 2 + 3.0), 2), 1.3,
                               round(sz + tux * (FTI_PLATFORM_W / 2 + 3.0), 2)],
                       "rotY": round(heading_rotY(tux, tuz), 4),
                       "meta": {"src": "stair core ground->platform (ASSUMED position)"}})

# Canopy support columns along both platform edges (ASSUMED positions)
fti_piers = []
for s_off in range(-60, 61, 30):
    for side in (-1, 1):
        px = cx + tux * s_off + (-tuz) * side * (FTI_PLATFORM_W / 2 + 1.5)
        pz = cz + tuz * s_off + tux * side * (FTI_PLATFORM_W / 2 + 1.5)
        fti_piers.append({"kind": "cylinder", "radius": 0.35, "height": 5.85,
                          "pos": [round(px, 2), 5.85 / 2, round(pz, 2)],
                          "meta": {"src": "canopy support column (ASSUMED 30 m spacing)"}})

fti_canopy = {"kind": "box", "size": [round(FTI_PLATFORM_L + 10, 1), 0.3, 25.0],
              "pos": [round(cx, 2), 6.0, round(cz, 2)],
              "rotY": round(heading_rotY(tux, tuz), 4), "color": "#d4d8dc",
              "meta": {"src": "flat canopy roof (ASSUMED - Type E' canopy form not dimensioned in DFR)"}}

# FTI's own approaches: reuse the Bicutan-frame deck/piers within +/-1.5 km of
# FTI, rebased into the FTI-centred frame (the ramp and at-grade bed included).
def near_fti_deck(o):
    x, z = o["pos"][0], o["pos"][2]
    s = x * tux + z * tuz
    return abs(s - FTI_S) <= 1500
fti_viaduct_deck = []
for o0 in viaduct_deck:
    if near_fti_deck(o0):
        o = dict(o0); o["pos"] = [round(o0["pos"][0] - fti_x, 2), o0["pos"][1], round(o0["pos"][2] - fti_z, 2)]
        fti_viaduct_deck.append(o)
fti_viaduct_piers = []
for o0 in viaduct_piers:
    if near_fti_deck(o0):
        o = dict(o0); o["pos"] = [round(o0["pos"][0] - fti_x, 2), o0["pos"][1], round(o0["pos"][2] - fti_z, 2)]
        fti_viaduct_piers.append(o)


fti_manifest = {
  "name": "FTI Station (NSCR CP S-03b) - JICA massing",
  "crs": "PRS92 PTM Zone III (EPSG:3123), metres",
  "origin_easting": round(FTI["center_prs92"]["e"], 2), "origin_northing": round(FTI["center_prs92"]["n"], 2),
  "origin_wgs84": {"lat": 14.504494, "lon": 121.036389,
                   "note": "printed coordinate on DFR Fig 4.4.9 (p.485); ~250 m uncertainty"},
  "levels_m": {"ground_ffl": 0.50, "top_of_rail": FTI_RAIL, "platform_ffl": FTI_PLAT,
               "canopy": 6.0, "note": "ASSUMED - not dimensioned in the DFR"},
  "sources": ["jica_southline_feasibility_dfr.pdf p.195 (Fig 4.2.56), p.500-502 (Type E'), p.485 (siting)",
              "alignment_extended.json centerline",
              "NOTE: DFR at-grade design superseded by as-built underground CP NSCR-03-B station"],
  "objects": {"platform": fti_platform, "tracks": fti_tracks, "floors": fti_floors,
              "stairs": fti_stairs, "canopy_box": [fti_canopy], "piers": fti_piers,
              "viaduct_deck": fti_viaduct_deck, "viaduct_piers": fti_viaduct_piers}
}
with open(r"E:\NSCR\app\src\data\fti-massing.json", "w") as fh:
    _atomic_json_dump(fti_manifest, r"E:\NSCR\app\src\data\fti-massing.json")
print("FTI manifest:", len(fti_platform), "platform objs | origin frame shared with Bicutan | FTI s =", round(FTI_S, 1))
def as_list(x):
    return x if isinstance(x, list) else [x]



# ================= Line manifest: Bicutan <-> FTI (v0.8.0) =================
# Both stations + full viaduct in ONE scene (Bicutan local frame) so the user
# can travel the corridor continuously. FTI objects are rebased from their
# FTI-centred frame back into the Bicutan frame (+fti_x, fti_z).
def rebase(objs, dx, dz):
    out = []
    for o in objs:
        o = dict(o)
        o["pos"] = [round(o["pos"][0] + dx, 2), o["pos"][1], round(o["pos"][2] + dz, 2)]
        out.append(o)
    return out

fti_dx, fti_dz = fti_x, fti_z   # FTI centre in the Bicutan local frame
line_objects = {
    "walls": walls,
    "platform": list(as_list(platform)) + rebase(as_list(fti_platform), fti_dx, fti_dz),
    "tracks": tracks + rebase(fti_tracks, fti_dx, fti_dz),
    "piers": piers + rebase(fti_piers, fti_dx, fti_dz),
    "stairs": stairs + rebase(fti_stairs, fti_dx, fti_dz),
    "floors": floors + rebase(fti_floors, fti_dx, fti_dz),
    "vault": vault,
    "lattice": lattice,
    "beams": beams,
    "canopy_box": rebase([fti_canopy], fti_dx, fti_dz),
    "viaduct_deck": viaduct_deck,
    "viaduct_piers": viaduct_piers,
}
def as_list(x):
    return x if isinstance(x, list) else [x]
line_manifest = {
  "name": "Bicutan <-> FTI (line, v0.8.0)",
  "crs": "PRS92 PTM Zone III (EPSG:3123), metres",
  "origin_easting": round(E0, 2), "origin_northing": round(N0, 2),
  "origin_wgs84": {"lat": 14.488419, "lon": 121.045368},
  "levels_m": {"ground_ffl": 0.50, "concourse_ffl": 4.60, "top_of_rail": 10.80,
               "platform_ffl": 11.90, "roof": 24.70},
  "sources": ["bicutan-real.json objects", "fti-massing.json objects (rebased)"],
  "objects": line_objects
}
with open(r"E:\\NSCR\\app\\src\\data\\line-bicutan-fti.json", "w") as fh:
    _atomic_json_dump(line_manifest, r"E:\NSCR\app\src\data\line-bicutan-fti.json")
print("line manifest written:", sum(len(v) if isinstance(v, list) else 1 for v in line_objects.values()), "objects")
