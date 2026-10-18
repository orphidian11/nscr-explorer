import ezdxf, math
from collections import defaultdict
base=r"E:/NSCR/pipeline/dxf/xrefs/"

def ent_pts(e):
    t=e.dxftype()
    if t=="INSERT": return [(e.dxf.insert.x,e.dxf.insert.y)]
    if t=="LINE": return [(e.dxf.start.x,e.dxf.start.y),(e.dxf.end.x,e.dxf.end.y)]
    if t=="LWPOLYLINE": return [(p[0],p[1]) for p in e.get_points()]
    if t=="POLYLINE": return [(v.dxf.location.x,v.dxf.location.y) for v in e.vertices]
    if t in ("CIRCLE","ARC"): return [(e.dxf.center.x,e.dxf.center.y)]
    return []

# 1) escalator geometry extents on ground & concourse
for f in ["X_Bic_Sta_Ground Floor.dxf","X_Bic_Sta_Concourse.dxf"]:
    doc=ezdxf.readfile(base+f)
    xs=[];ys=[]
    for e in doc.modelspace().query('*[layer=="A-ESCALATOR"]'):
        for p in ent_pts(e): xs.append(p[0]); ys.append(p[1])
    if xs: print(f,"A-ESCALATOR bbox E",min(xs),max(xs),"N",min(ys),max(ys))

# 2) wall bboxes per level (all entities on wall-ish layers), full extents
for f,name in [("X_Bic_Sta_Ground Floor.dxf","ground"),("X_Bic_Sta_Concourse.dxf","concourse"),("X_Bic_Sta_Platform.dxf","platform")]:
    doc=ezdxf.readfile(base+f)
    xs=[];ys=[]
    for e in doc.modelspace():
        if "WALL" not in e.dxf.layer.upper(): continue
        for p in ent_pts(e): xs.append(p[0]); ys.append(p[1])
    print(name,"WALL bbox E",round(min(xs),1),round(max(xs),1),"N",round(min(ys),1),round(max(ys),1),"n_ent layers:",len(set(e.dxf.layer for e in doc.modelspace() if "WALL" in e.dxf.layer.upper())))

# 3) ground slab: check other candidate layers for floor plate
doc=ezdxf.readfile(base+"X_Bic_Sta_Ground Floor.dxf")
cnt=defaultdict(int)
for e in doc.modelspace(): cnt[e.dxf.layer]+=1
for k,v in sorted(cnt.items()):
    if v>0: print("GF layer",k,v)
