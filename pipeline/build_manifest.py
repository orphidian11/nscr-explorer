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

# Platform slab from A-SLAB closed outline (use bbox of PL segs as slab; refine later)
pe = all_bbox([SEGS["pl"]])
slab = {"kind":"box",
        "size":[round(pe[2]-pe[0],1), 0.4, round(pe[3]-pe[1],1)],
        "pos":[round((pe[0]+pe[2])/2 - E0,1), 11.70, round(-((pe[1]+pe[3])/2 - N0),1)],
        "meta":{"src":"X_Bic_Sta_Platform A-SLAB bbox","ffl":11.90}}

# Tracks: along the long (eastings/x) axis, top of rail +10.80 (from Section dims)
L_along = pe[2]-pe[0]
tracks = []
for off in (-6.75, 6.75):
    tracks.append({"kind":"box","size":[round(L_along+40,1), 0.3, 1.6],
                   "pos":[0, 10.65, round(off,2)],
                   "meta":{"src":"typical double track, 6.75 m offset (DFR 8.7 m spacing), TOR +10.80"}})

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

manifest = {
  "name": "Bicutan Station (NSCR CP S-03c)",
  "crs": "PRS92 PTM Zone III (EPSG:3123), metres",
  "origin_easting": round(E0,2), "origin_northing": round(N0,2),
  "origin_wgs84": {"lat": 14.48748, "lon": 121.04571,
                   "note": "approx; refine by transforming origin_easting/northing via PROJ EPSG:3123->4326"},
  "levels_m": {"ground_ffl":0.50,"concourse_ffl":4.60,"top_of_rail":10.80,"platform_ffl":11.90,
               "top_of_beam":15.90,"roof":24.70},
  "sources": ["X_Bic_Sta_Ground Floor.dxf","X_Bic_Sta_Concourse.dxf","X_Bic_Sta_Platform.dxf",
              "X_Bic_Sta_Section.dxf","foundation plan (columns.json)","facade A-CLAD (canopy.json)"],
  "objects": {"walls": walls, "platform": [slab], "tracks": tracks,
              "piers": piers, "stairs": stairs, "vault": vault, "lattice": lattice}
}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(manifest, open(OUT,"w"), indent=1)
print("walls:", len(walls), "| piers:", len(piers), "| tracks:", len(tracks), "| stairs:", len(stairs),
      "| lattice segs:", len(lattice), "| vault profile pts:", len(profile_offsets))
print("origin E,N:", round(E0,2), round(N0,2), "| along-track length:", round(L_along,1), "m")
print("written:", OUT, os.path.getsize(OUT)//1024, "KB")
