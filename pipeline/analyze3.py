import ezdxf, math
base=r"E:/NSCR/pipeline/dxf/xrefs/"
BB=(504685,504810,1602280,1602465)
def ent_pts(e):
    t=e.dxftype()
    if t=="INSERT": return [(e.dxf.insert.x,e.dxf.insert.y)]
    if t=="LINE": return [(e.dxf.start.x,e.dxf.start.y),(e.dxf.end.x,e.dxf.end.y)]
    if t=="LWPOLYLINE": return [(p[0],p[1]) for p in e.get_points()]
    if t=="POLYLINE": return [(v.dxf.location.x,v.dxf.location.y) for v in e.vertices]
    if t in ("CIRCLE","ARC"): return [(e.dxf.center.x,e.dxf.center.y)]
    return []
def inbb(p,m=25): return BB[0]-m<=p[0]<=BB[1]+m and BB[2]-m<=p[1]<=BB[3]+m

for f,name in [("X_Bic_Sta_Ground Floor.dxf","ground"),("X_Bic_Sta_Concourse.dxf","concourse")]:
    doc=ezdxf.readfile(base+f)
    print("="*15,name)
    for lay in ["A-ESCALATOR","A-Elev-Pen2"]:
        xs=[];ys=[]
        for e in doc.modelspace().query(f'*[layer=="{lay}"]'):
            pts=[p for p in ent_pts(e) if inbb(p)]
            if len(pts)==len(ent_pts(e)) and pts:
                xs+= [p[0] for p in pts]; ys+=[p[1] for p in pts]
        if xs: print(lay,"bbox E %.1f..%.1f N %.1f..%.1f centre(%.1f,%.1f)"%(min(xs),max(xs),min(ys),max(ys),sum(xs)/len(xs),sum(ys)/len(ys)))
    # wall bbox within bbox
    xs=[];ys=[]
    for e in doc.modelspace():
        if "WALL" not in e.dxf.layer.upper(): continue
        for p in ent_pts(e):
            if inbb(p): xs.append(p[0]); ys.append(p[1])
    print("WALL bbox E %.1f..%.1f N %.1f..%.1f"%(min(xs),max(xs),min(ys),max(ys)))
