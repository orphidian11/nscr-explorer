import json, math
d=json.load(open('alignment_v3.json'))
pts=d['points']
print('points',len(pts),'spacing',d['sample_spacing_m'],'range',d['range_m'])
sp=[math.dist(pts[i],pts[i+1]) for i in range(len(pts)-1)]
print('max step between 10m samples: %.2f m (expected ~10)'%max(sp))
print('stations:',d['stations_s'])
print('gaps:',d['gaps'])
print('first',pts[0],'last',pts[-1])
v2=json.load(open('alignment_extended_v2.json'))['points']
# compare near Bicutan: nearest v3 sample to v2's s=0 point (505424.97,1598613.14 is s=-3635)
p0=v2[0]
near=min(pts,key=lambda q:math.hypot(q[0]-p0[0],q[1]-p0[1]))
print('v2 s=-3635 pt',p0,'nearest v3',near,'dist %.1f m'%math.hypot(near[0]-p0[0],near[1]-p0[1]))
