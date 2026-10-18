import ezdxf
base=r"E:/NSCR/pipeline/dxf/xrefs_site/"
doc=ezdxf.readfile(base+"X_Bic_Site Plan.dxf")
msp=doc.modelspace()
texts=[]
for e in msp:
    if e.dxftype() in ("TEXT","MTEXT"):
        t=e.dxf.text if e.dxftype()=="TEXT" else e.plain_text()
        p=(e.dxf.insert.x,e.dxf.insert.y) if e.dxftype()=="TEXT" else (e.dxf.insert.x,e.dxf.insert.y)
        texts.append((t.strip(),p))
for t,p in texts:
    if any(k in t.upper() for k in ["ENTR","EXIT","GATE","ACCESS","WALK","PARK","DROP","PLAZA","SLEX","FTI","STAIR","ESCAL"]):
        print(repr(t), "at %.0f,%.0f"%p)
print("total texts",len(texts))
# overall site extent of text
if texts:
    print("text extent E %.0f..%.0f N %.0f..%.0f"%(min(p[0] for _,p in texts),max(p[0] for _,p in texts),min(p[1] for _,p in texts),max(p[1] for _,p in texts)))
