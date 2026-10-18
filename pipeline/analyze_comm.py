import ezdxf, math, json
from collections import defaultdict
base=r"E:/NSCR/pipeline/dxf/xrefs/"
BB=(504685,504810,1602280,1602465)

def ent_pts(e):
    t=e.dxftype()
    if t=="INSERT":
        return [(e.dxf.insert.x,e.dxf.insert.y)]
    if t in ("LINE",):
        return [(e.dxf.start.x,e.dxf.start.y),(e.dxf.end.x,e.dxf.end.y)]
    if t in ("LWPOLYLINE",):
        return [(p[0],p[1]) for p in e.get_points()]
    if t=="POLYLINE":
        return [(v.dxf.location.x,v.dxf.location.y) for v in e.vertices]
    if t in ("CIRCLE",):
        return [(e.dxf.center.x,e.dxf.center.y)]
    if t in ("ARC",):
        return [(e.dxf.center.x,e.dxf.center.y)]
    return []

def clusters(pts, r=6.0):
    cl=[]
    for p in pts:
        placed=False
        for c in cl:
            if math.dist(p,c[0])<r:
                c.append(p); placed=True; break
        if not placed: cl.append([p])
    # merge pass
    merged=True
    while merged:
        merged=False
        for i in range(len(cl)):
            for j in range(i+1,len(cl)):
                if math.dist(cl[i][0],cl[j][0])<r:
                    cl[i]+=cl[j]; del cl[j]; merged=True; break
            if merged: break
    return [(sum(p[0] for p in c)/len(c), sum(p[1] for p in c)/len(c), len(c)) for c in sorted(cl,key=lambda c:-len(c))]

# alignment azimuth -28.3 deg => direction vector (sin,cos) of azimuth? Azimuth measured from north: az=-28.3 -> dx=sin(-28.3), dy=cos(-28.3)
az=math.radians(-28.3)
ux,uy=math.sin(az),math.cos(az)  # along-track
def side(e,n):
    # cross product with along-track unit from station centre
    ce,cn=(504747.5,1602372.5)
    de,dn=e-ce,n-cn
    cross=ux*dn-uy*de  # >0 left of travel
    return "left(travel)" if cross>0 else "right(travel)"

for f in ["X_Bic_Sta_Ground Floor.dxf","X_Bic_Sta_Concourse.dxf","X_Bic_Sta_Platform.dxf"]:
    doc=ezdxf.readfile(base+f); msp=doc.modelspace()
    print("="*20,f)
    for lay in ["A-DOOR","A-GATE","A-STAIRS","A-ESCALATOR","A-Elev-Pen2","A-RAMP","A-SLAB","A-ROLLER SHUTTER DOOR"]:
        pts=[]
        inb=0; outb=0
        for e in msp.query(f'*[layer=="{lay}"]'):
            p=ent_pts(e)
            if not p: continue
            c=(sum(x for x,_ in p)/len(p), sum(y for _,y in p)/len(p))
            if BB[0]<=c[0]<=BB[1] and BB[2]<=c[1]<=BB[3]:
                inb+=1; pts.append(c)
            else: outb+=1
        print(f"{lay}: in_bbox={inb} out={outb}")
        for e,n,cnt in clusters(pts)[:12]:
            print(f"   cluster e={e:.1f} n={n:.1f} n_ent={cnt} side={side(e,n)}")
