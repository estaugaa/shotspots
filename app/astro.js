let TZ="America/Los_Angeles";
/* ---------- Math helpers ---------- */
const D2R=Math.PI/180, R2D=180/Math.PI;
const rev=x=>x-Math.floor(x/360)*360;
const sind=x=>Math.sin(x*D2R), cosd=x=>Math.cos(x*D2R), asind=x=>Math.asin(Math.max(-1,Math.min(1,x)))*R2D, atan2d=(y,x)=>Math.atan2(y,x)*R2D;
const angDiff=(a,b)=>((a-b+540)%360)-180;
const dS=date=>date.getTime()/864e5+2440587.5-2451543.5;

/* ---------- Ephemeris (Schlyter low-precision with lunar perturbations, ~1-2 arcmin) ---------- */
function sunEcl(d){
  const w=282.9404+4.70935e-5*d, e=0.016709-1.151e-9*d, M=rev(356.0470+0.9856002585*d);
  const E=M+R2D*e*sind(M)*(1+e*cosd(M));
  const xv=cosd(E)-e, yv=Math.sqrt(1-e*e)*sind(E);
  return {lon:rev(atan2d(yv,xv)+w), r:Math.hypot(xv,yv), M, w};
}
function eclToEq(lon,lat,r,d){
  const ecl=23.4393-3.563e-7*d;
  const x=r*cosd(lon)*cosd(lat), y=r*sind(lon)*cosd(lat), z=r*sind(lat);
  const ye=y*cosd(ecl)-z*sind(ecl), ze=y*sind(ecl)+z*cosd(ecl);
  return {ra:rev(atan2d(ye,x)), dec:atan2d(ze,Math.hypot(x,ye))};
}
function moonEcl(d){
  const N=rev(125.1228-0.0529538083*d), i=5.1454, w=rev(318.0634+0.1643573223*d), a=60.2666, e=0.0549, M=rev(115.3654+13.0649929509*d);
  let E=M+R2D*e*sind(M)*(1+e*cosd(M));
  for(let k=0;k<4;k++) E=E-(E-R2D*e*sind(E)-M)/(1-e*cosd(E));
  const xv=a*(cosd(E)-e), yv=a*Math.sqrt(1-e*e)*sind(E), v=atan2d(yv,xv); let r=Math.hypot(xv,yv);
  const xh=r*(cosd(N)*cosd(v+w)-sind(N)*sind(v+w)*cosd(i)), yh=r*(sind(N)*cosd(v+w)+cosd(N)*sind(v+w)*cosd(i)), zh=r*sind(v+w)*sind(i);
  let lon=atan2d(yh,xh), lat=atan2d(zh,Math.hypot(xh,yh));
  const s=sunEcl(d), Ms=s.M, Ls=rev(s.M+s.w), Lm=rev(M+w+N), D=Lm-Ls, F=Lm-N;
  lon+=-1.274*sind(M-2*D)+0.658*sind(2*D)-0.186*sind(Ms)-0.059*sind(2*M-2*D)-0.057*sind(M-2*D+Ms)+0.053*sind(M+2*D)+0.046*sind(2*D-Ms)+0.041*sind(M-Ms)-0.035*sind(D)-0.031*sind(M+Ms)-0.015*sind(2*F-2*D)+0.011*sind(M-4*D);
  lat+=-0.173*sind(F-2*D)-0.055*sind(M-F-2*D)-0.046*sind(M+F-2*D)+0.033*sind(F+2*D)+0.017*sind(2*M+F);
  r+=-0.58*cosd(M-2*D)-0.46*cosd(2*D);
  return {lon:rev(lon),lat,r,sunLon:s.lon};
}
function horiz(ra,dec,date,lat,lon){
  const d=dS(date), s=sunEcl(d), Ls=rev(s.M+s.w);
  const UT=((date.getTime()/36e5)%24+24)%24;
  const HA=rev(Ls+180+UT*15+lon)-ra;
  const x=cosd(HA)*cosd(dec), y=sind(HA)*cosd(dec), z=sind(dec);
  const xh=x*sind(lat)-z*cosd(lat), zh=x*cosd(lat)+z*sind(lat);
  return {az:rev(atan2d(y,xh)+180), alt:asind(zh)};
}
const refr=h=>h>-2?1.02/Math.tan((h+10.3/(h+5.11))*D2R)/60:0;
function sunPos(date,lat,lon){ const d=dS(date), s=sunEcl(d), q=eclToEq(s.lon,0,s.r,d), p=horiz(q.ra,q.dec,date,lat,lon); return {az:p.az,alt:p.alt,app:p.alt+refr(p.alt)}; }
function moonPos(date,lat,lon){
  const d=dS(date), m=moonEcl(d), q=eclToEq(m.lon,m.lat,m.r,d), p=horiz(q.ra,q.dec,date,lat,lon);
  const topo=p.alt-asind(1/m.r)*cosd(p.alt);
  const el=rev(m.lon-m.sunLon), cosE=cosd(el)*cosd(m.lat);
  return {az:p.az,alt:topo,app:topo+refr(topo),illum:(1-cosE)/2,age:el/360};
}
function gcPos(date,lat,lon){ const p=horiz(266.405,-28.936,date,lat,lon); return {az:p.az,alt:p.alt}; }
function phaseName(age){ const n=["New moon","Waxing crescent","First quarter","Waxing gibbous","Full moon","Waning gibbous","Last quarter","Waning crescent"]; return n[Math.floor(age*8+0.5)%8]; }

/* ---------- Time helpers (America/Los_Angeles) ---------- */
function tzOffsetMin(date){
  const p=new Intl.DateTimeFormat("en-US",{timeZone:TZ,hourCycle:"h23",year:"numeric",month:"numeric",day:"numeric",hour:"numeric",minute:"numeric",second:"numeric"}).formatToParts(date);
  const g=t=>+p.find(x=>x.type===t).value;
  return (Date.UTC(g("year"),g("month")-1,g("day"),g("hour")%24,g("minute"),g("second"))-date.getTime())/60000;
}
const __offCache={};
function laDate(ymd,minutes){ const [y,m,d]=ymd.split("-").map(Number); const base=Date.UTC(y,m-1,d,0,0);
  let off=__offCache[ymd]; if(off===undefined){ off=tzOffsetMin(new Date(base+12*36e5)); __offCache[ymd]=off; }
  return new Date(base+minutes*60000-off*60000); }
function laYMD(date){ const p=new Intl.DateTimeFormat("en-CA",{timeZone:TZ,year:"numeric",month:"2-digit",day:"2-digit"}).format(date); return p; }
function addDays(ymd,n){ const [y,m,d]=ymd.split("-").map(Number); const t=new Date(Date.UTC(y,m-1,d+n)); return t.toISOString().slice(0,10); }
const fmtT=d=>d?__fmt("hm",{o:{hour:"numeric",minute:"2-digit"}}).format(d):"–";
/* ---- v36 perf: cached formatters, day-base cache, memoized dayEvents ---- */
const __fmtCache={};
function __fmt(key,opts){ const k=key+"|"+TZ; return __fmtCache[k]||(__fmtCache[k]=new Intl.DateTimeFormat(opts.locale||"en-US",Object.assign({timeZone:TZ},opts.o))); }
laYMD=function(date){ return __fmt("ymd",{locale:"en-CA",o:{year:"numeric",month:"2-digit",day:"2-digit"}}).format(date); };
const __baseCache={};
laDate=function(ymd,minutes){ let B=__baseCache[ymd]; if(B===undefined){ const [y,m,d]=ymd.split("-").map(Number); const base=Date.UTC(y,m-1,d,0,0); let off=__offCache[ymd]; if(off===undefined){ off=tzOffsetMin(new Date(base+12*36e5)); __offCache[ymd]=off; } B=base-off*60000; __baseCache[ymd]=B; } return new Date(B+minutes*60000); };
const fmtD=ymd=>{ const [y,m,d]=ymd.split("-").map(Number); return new Date(Date.UTC(y,m-1,d,12)).toLocaleDateString("en-US",{timeZone:"UTC",weekday:"short",month:"short",day:"numeric"}); };

/* Crossings of a threshold during a local day; returns [{t, dir}] */
function crossings(ymd,fn,thr,step=10){
  const out=[]; let prevT=laDate(ymd,0), prev=fn(prevT)-thr;
  for(let m=step;m<=1440;m+=step){
    const t=laDate(ymd,m), v=fn(t)-thr;
    if((prev<0)!==(v<0)){ let a=prevT.getTime(), b=t.getTime(), fa=prev;
      for(let k=0;k<14;k++){ const mid=(a+b)/2, fm=fn(new Date(mid))-thr; if((fa<0)===(fm<0)){a=mid;fa=fm;}else b=mid; }
      out.push({t:new Date((a+b)/2),dir:v>prev?"up":"down"}); }
    prevT=t; prev=v;
  }
  return out;
}

/* ---------- Geometry: targets & vantages ---------- */
const RE=6371000, KREF=0.87;
function geoTo(a,b){ const p1=a.lat*D2R,p2=b.lat*D2R,dl=(b.lon-a.lon)*D2R;
  const y=Math.sin(dl)*Math.cos(p2), x=Math.cos(p1)*Math.sin(p2)-Math.sin(p1)*Math.cos(p2)*Math.cos(dl);
  const d=RE*Math.acos(Math.max(-1,Math.min(1,Math.sin(p1)*Math.sin(p2)+Math.cos(p1)*Math.cos(p2)*Math.cos(dl))));
  return {az:rev(Math.atan2(y,x)*R2D), dist:d}; }
function appAlt(h0,h1,d){ return Math.atan((h1-h0)/d)*R2D-KREF*d/(2*RE)*R2D; }
function targetFrom(v,t){ const g=geoTo(v,t); return {az:g.az, alt:appAlt(v.elev,t.elev,g.dist), dist:g.dist}; }


const __dayEvCache={};
function dayEvents(v,ymd){ const k=(Math.round(v.lat*20)/20)+","+(Math.round(v.lon*20)/20)+","+ymd; return __dayEvCache[k]||(__dayEvCache[k]=__dayEventsRaw(v,ymd)); }
function __dayEventsRaw(v,ymd){
  const sf=t=>sunPos(t,v.lat,v.lon).alt, mf=t=>moonPos(t,v.lat,v.lon).alt;
  const pick=(arr,dir)=>{ const x=arr.find(c=>c.dir===dir); return x?x.t:null; };
  const rs=crossings(ymd,sf,-0.833), g6=crossings(ymd,sf,6), c6=crossings(ymd,sf,-6), a18=crossings(ymd,sf,-18), mr=crossings(ymd,mf,-0.8,10);
  return {astroDawn:pick(a18,"up"),civilDawn:pick(c6,"up"),sunrise:pick(rs,"up"),goldEndAM:pick(g6,"up"),goldStartPM:pick(g6,"down"),sunset:pick(rs,"down"),civilDusk:pick(c6,"down"),astroDusk:pick(a18,"down"),moonrise:pick(mr,"up"),moonset:pick(mr,"down")};
}
