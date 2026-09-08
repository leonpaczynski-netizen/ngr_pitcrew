from pitcrew.store.db import Store
from PIL import Image, ImageDraw, ImageFont
import sqlite3
s=Store(); c=sqlite3.connect('data/pitcrew.db'); c.row_factory=sqlite3.Row
lid=list(c.execute("select id from laps where session_id=151 and lap_num=10"))[0][0]
F=s.get_lap_frames(lid)['frames']
xs=[f['pos_x'] for f in F]; zs=[f['pos_z'] for f in F]
x0,x1,z0,z1=min(xs),max(xs),min(zs),max(zs)
W,H=1240,1180
LEFT,RIGHT,TOP,BOT=330,300,150,80          # margins leave room for labels
sc=min((W-LEFT-RIGHT)/(x1-x0),(H-TOP-BOT)/(z1-z0))
ox=LEFT+((W-LEFT-RIGHT)-(x1-x0)*sc)/2
def P(f): return (ox+(f['pos_x']-x0)*sc, H-BOT-(f['pos_z']-z0)*sc)
img=Image.new('RGB',(W,H),(16,17,20)); d=ImageDraw.Draw(img)
def col(v):
    t=max(0.0,min(1.0,(v-90)/(285-90)))
    return (int(40+215*t), int(60+120*(1-abs(t-0.5)*2)), int(230-190*t))
for a,b in zip(F,F[1:]): d.line([P(a),P(b)],fill=col(a['speed_kph']),width=9)
try:
    fb=ImageFont.truetype("arialbd.ttf",22); fs=ImageFont.truetype("arial.ttf",17); ft=ImageFont.truetype("arialbd.ttf",31)
except: fb=fs=ft=ImageFont.load_default()
def pin(dist,label,note,side='r',ring=(255,255,255),off=0):
    f=min(F,key=lambda f:abs(f['lap_distance_m']-dist)); x,y=P(f)
    d.ellipse([x-11,y-11,x+11,y+11],outline=ring,width=4)
    wl=d.textlength(label,font=fb); wn=d.textlength(note,font=fs) if note else 0
    if side=='r': tx=x+22; anchor=None
    else:         tx=x-22-max(wl,wn)
    ty=y-(24 if note else 11)+off
    d.text((tx,ty),label,font=fb,fill=(255,255,255))
    if note: d.text((tx,ty+24),note,font=fs,fill=ring)
pin(220,"Hell Corner","",'r')
pin(1225,"Griffins Bend","",'r')
pin(1820,"The Cutting","rear spinning 56% on power",'l',(255,120,90))
pin(2620,"McPhillamy Park","2.3 g, flat out",'l')
pin(3060,"SKYLINE","caught it laps 2-4, ZERO since",'l',(120,230,255),-34)
pin(3260,"The Dipper","",'r')
pin(3620,"Forrest's Elbow","onto Conrod",'l')
pin(5220,"The Chase","280 -> 128 km/h",'r')
pin(5830,"Murray's","",'r')
sf=P(F[0]); d.ellipse([sf[0]-9,sf[1]-9,sf[0]+9,sf[1]+9],fill=(255,255,255))
d.text((sf[0]-52,sf[1]-46),"START / FINISH",font=fs,fill=(255,255,255))
d.text((44,40),"Mount Panorama — your lap 10, 2:03.003",font=ft,fill=(255,255,255))
d.text((46,82),"Huracan GT3 · session 151 · 8 Sep 2026 · colour is speed",font=fs,fill=(150,155,165))
lx,ly=W-290,120
for i in range(250): d.line([(lx+i,ly),(lx+i,ly+18)],fill=col(90+(285-90)*i/250))
d.text((lx,ly-24),"speed",font=fs,fill=(150,155,165))
d.text((lx,ly+23),"90",font=fs,fill=(150,155,165)); d.text((lx+196,ly+23),"285 km/h",font=fs,fill=(150,155,165))
img.save('exports/bathurst_s151.png'); print("saved")
