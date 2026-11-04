"use client";

import { useMemo, useRef, useState } from "react";

type Any = any;
type Mode = "cfd" | "fut";

const n = (v: unknown) => typeof v === "number" && Number.isFinite(v);
const p2 = (v: unknown) => n(v) ? Number(v).toLocaleString("en-US",{minimumFractionDigits:2,maximumFractionDigits:2}) : "—";
const p0 = (v: unknown) => n(v) ? Number(v).toLocaleString("en-US",{maximumFractionDigits:0}) : "—";
const pct = (v: unknown) => n(v) ? Number(v).toFixed(1) + "%" : "—";
const signed = (v: unknown) => n(v) ? (Number(v) >= 0 ? "+" : "−") + Math.abs(Number(v)).toFixed(2) : "—";
const compact = (v: unknown) => {
  if (!n(v)) return "—";
  const x = Math.abs(Number(v));
  const s = Number(v) < 0 ? "−" : "";
  if (x >= 1e9) return s + (x/1e9).toFixed(2) + "B";
  if (x >= 1e6) return s + (x/1e6).toFixed(1) + "M";
  if (x >= 1e3) return s + (x/1e3).toFixed(1) + "K";
  return s + x.toFixed(0);
};
const ticks = (lo:number, hi:number, count:number) => {
  if (!(hi > lo)) return [lo];
  const raw=(hi-lo)/Math.max(1,count);
  const mag=Math.pow(10,Math.floor(Math.log10(raw)));
  const step=[1,2,2.5,5,10].map(x=>x*mag).find(x=>x>=raw) ?? raw;
  const out:number[]=[];
  for(let x=Math.ceil(lo/step)*step;x<=hi+1e-9;x+=step) out.push(Number(x.toFixed(6)));
  return out;
};
const xOf=(r:Any,c:Any,m:Mode)=>m==="cfd" ? (n(r.strikeCfd)?r.strikeCfd:n(c.basis)?r.strike-c.basis:null) : r.strike;
const priceOf=(c:Any,m:Mode)=>m==="cfd" ? (n(c.cfd)?c.cfd:n(c.futures)&&n(c.basis)?c.futures-c.basis:null) : c.futures;
const bandsOf=(c:Any,m:Mode)=>{
  return (c.expected??[]).map((b:Any,i:number)=>({
    title:b.title??(i+1)+" SD",
    lo:m==="cfd"?(b.lowerCfd??(n(c.basis)?b.lower-c.basis:null)):b.lower,
    hi:m==="cfd"?(b.upperCfd??(n(c.basis)?b.upper-c.basis:null)):b.upper
  })).filter((x:Any)=>n(x.lo)&&n(x.hi)).sort((a:Any,b:Any)=>(a.hi-a.lo)-(b.hi-b.lo));
};

function OiChart({cme,mode}:{cme:Any;mode:Mode}) {
  const W=760,H=360,L=44,R=14,T=108,B=28;
  const price=priceOf(cme,mode), bands=bandsOf(cme,mode);
  const rows=(cme.rows??[]).map((r:Any)=>({...r,x:xOf(r,cme,mode)})).filter((r:Any)=>n(r.x)&&n(r.oiCall)&&n(r.oiPut));
  if(!rows.length||price===null) return <div className="kt-empty">ยังไม่มีข้อมูล OI รายสไตรค์</div>;
  const outer=bands[bands.length-1], pad=outer?(outer.hi-outer.lo)*.06:price*.02;
  const lo=outer?outer.lo-pad:price*.9, hi=outer?outer.hi+pad:price*1.1;
  const vis=rows.filter((r:Any)=>r.x>=lo&&r.x<=hi);
  if(!vis.length) return <div className="kt-empty">ไม่มีสไตรค์ในกรอบที่ตลาดคาด</div>;
  const ymax=Math.max(...vis.map((r:Any)=>Math.max(r.oiCall,r.oiPut)),1)*1.1;
  const X=(v:number)=>L+(v-lo)/(hi-lo)*(W-L-R), base=H-B, Y=(v:number)=>base-v/ymax*(base-T);
  const sd=bands.length?(bands[0].hi-bands[0].lo)/2:(hi-lo)/6;
  const curve:string[]=[]; const area:string[]=[];
  for(let i=0;i<=140;i++){const v=lo+(hi-lo)*i/140;const h=Math.exp(-.5*Math.pow((v-price)/sd,2))*(base-T)*.8;curve.push((i?"L":"M")+X(v).toFixed(1)+","+(base-h).toFixed(1));if(Math.abs(v-price)<=sd)area.push((area.length?"L":"M")+X(v).toFixed(1)+","+(base-h).toFixed(1));}
  const areaPath=area.length?area.join(" ")+" L"+X(price+sd).toFixed(1)+","+base+" L"+X(price-sd).toFixed(1)+","+base+" Z":"";
  const xt=ticks(lo,hi,7), yt=ticks(0,ymax,3);
  return <svg className="kt-svg" viewBox={"0 0 "+W+" "+H} role="img" aria-label="Open Interest และกรอบที่ตลาดคาด">
    {yt.map(t=><g key={"y"+t}><line className="kt-grid" x1={L} x2={W-R} y1={Y(t)} y2={Y(t)}/><text className="kt-axis" x={L-6} y={Y(t)+3} textAnchor="end">{compact(t)}</text></g>)}
    {xt.map(t=><text key={"x"+t} className="kt-axis" x={X(t)} y={H-8} textAnchor="middle">{p0(t)}</text>)}
    {areaPath&&<path className="kt-sd1" d={areaPath}/>}<path className="kt-curve" d={curve.join(" ")}/>
    {vis.map((r:Any)=><g key={r.strike}><rect className="kt-put" x={X(r.x)-3} y={Y(r.oiPut)} width={3} height={base-Y(r.oiPut)}/><rect className="kt-call" x={X(r.x)} y={Y(r.oiCall)} width={3} height={base-Y(r.oiCall)}/></g>)}
    {bands.slice().reverse().map((b:Any,i:number)=>{const y=16+i*22;const half=(b.hi-b.lo)/2;return <g key={b.title+i}><line className="kt-br" x1={X(b.lo)} x2={X(b.hi)} y1={y} y2={y}/><line className="kt-br" x1={X(b.lo)} x2={X(b.lo)} y1={y-4} y2={y+4}/><line className="kt-br" x1={X(b.hi)} x2={X(b.hi)} y1={y-4} y2={y+4}/><text className="kt-br-t" x={(X(b.lo)+X(b.hi))/2} y={y+4} textAnchor="middle">{b.title} ±{half.toFixed(1)}</text><text className="kt-axis" x={X(b.lo)} y={y+16} textAnchor="middle">{p0(b.lo)}</text><text className="kt-axis" x={X(b.hi)} y={y+16} textAnchor="middle">{p0(b.hi)}</text></g>})}
    <line className="kt-price" x1={X(price)} x2={X(price)} y1={T-8} y2={base}/><rect className="kt-tag" x={X(price)-30} y={T-22} width={60} height={14} rx={3}/><text className="kt-tag-t" x={X(price)} y={T-12} textAnchor="middle">{p2(price)}</text>
  </svg>;
}

function SmileChart({cme,mode}:{cme:Any;mode:Mode}) {
  const W=420,H=230,L=38,R=12,T=16,B=26,price=priceOf(cme,mode);
  const rows=(cme.rows??[]).map((r:Any)=>({...r,x:xOf(r,cme,mode)})).filter((r:Any)=>n(r.x)&&n(r.vol)&&r.vol>0);
  if(rows.length<3||price===null) return <div className="kt-empty">ยังไม่มี IV รายสไตรค์</div>;
  const bands=bandsOf(cme,mode), outer=bands[bands.length-1], lo=outer?.lo??price*.9, hi=outer?.hi??price*1.1;
  const vis=rows.filter((r:Any)=>r.x>=lo&&r.x<=hi); if(vis.length<3) return <div className="kt-empty">IV ไม่พอในกรอบ</div>;
  const vmin=Math.floor(Math.min(...vis.map((r:Any)=>r.vol))-.5), vmax=Math.ceil(Math.max(...vis.map((r:Any)=>r.vol))+.5);
  const X=(v:number)=>L+(v-lo)/(hi-lo)*(W-L-R),Y=(v:number)=>H-B-(v-vmin)/(vmax-vmin)*(H-B-T);
  const d=vis.map((r:Any,i:number)=>(i?"L":"M")+X(r.x).toFixed(1)+","+Y(r.vol).toFixed(1)).join(" ");
  return <svg className="kt-svg" viewBox={"0 0 "+W+" "+H} role="img" aria-label="IV Smile">{ticks(vmin,vmax,3).map(t=><g key={t}><line className="kt-grid" x1={L} x2={W-R} y1={Y(t)} y2={Y(t)}/><text className="kt-axis" x={L-5} y={Y(t)+3} textAnchor="end">{t.toFixed(1)}%</text></g>)}{ticks(lo,hi,4).map(t=><text key={t} className="kt-axis" x={X(t)} y={H-8} textAnchor="middle">{p0(t)}</text>)}<line className="kt-price dashed" x1={X(price)} x2={X(price)} y1={T} y2={H-B}/><path className="kt-line" d={d}/></svg>;
}

function GammaBars({cme,mode}:{cme:Any;mode:Mode}) {
  const W=420,H=230,L=54,R=12,T=16,B=26,price=priceOf(cme,mode);
  const bars=(cme.gamma?.bars??[]).map((r:Any)=>({x:mode==="cfd"?(n(r.strikeCfd)?r.strikeCfd:null):r.strike,v:r.v})).filter((r:Any)=>n(r.x)&&n(r.v));
  if(bars.length<3||price===null) return <div className="kt-empty">ยังไม่มี GEX รายสไตรค์</div>;
  const bands=bandsOf(cme,mode),outer=bands[bands.length-1],lo=outer?.lo??price*.9,hi=outer?.hi??price*1.1,vis=bars.filter((r:Any)=>r.x>=lo&&r.x<=hi);
  const m=Math.max(...vis.map((r:Any)=>Math.abs(r.v)),1)*1.1,X=(v:number)=>L+(v-lo)/(hi-lo)*(W-L-R),mid=(H-B+T)/2,Y=(v:number)=>mid-v/m*((H-B-T)/2),bw=Math.max(1.2,(W-L-R)/Math.max(vis.length,1)*.7);
  return <svg className="kt-svg" viewBox={"0 0 "+W+" "+H} role="img" aria-label="Gamma ตามราคาใช้สิทธิ์"><line className="kt-grid" x1={L} x2={W-R} y1={mid} y2={mid}/>{ticks(lo,hi,4).map(t=><text key={t} className="kt-axis" x={X(t)} y={H-8} textAnchor="middle">{p0(t)}</text>)}{vis.map((r:Any,i:number)=><rect key={i} className={r.v>=0?"kt-gpos":"kt-gneg"} x={X(r.x)-bw/2} width={bw} y={r.v>=0?Y(r.v):mid} height={Math.abs(Y(r.v)-mid)}/>)}<line className="kt-price dashed" x1={X(price)} x2={X(price)} y1={T} y2={H-B}/>{n(cme.gamma?.flip)&&<line className="kt-flip" x1={X(mode==="cfd"&&n(cme.basis)?cme.gamma.flip-cme.basis:cme.gamma.flip)} x2={X(mode==="cfd"&&n(cme.basis)?cme.gamma.flip-cme.basis:cme.gamma.flip)} y1={T} y2={H-B}/>}</svg>;
}

function ProfileChart({cme,mode}:{cme:Any;mode:Mode}) {
  const curve=(cme.gamma?.curve??[]).filter((p:Any)=>n(p.spot)&&n(p.net_gex));
  if(curve.length<5) return <div className="kt-empty">ต้องมี IV รายสไตรค์ + DTE</div>;
  const sh=mode==="cfd"&&n(cme.basis)?cme.basis:0,pts=curve.map((p:Any)=>({x:p.spot-sh,v:p.net_gex})),lo=pts[0].x,hi=pts[pts.length-1].x,m=Math.max(...pts.map((p:Any)=>Math.abs(p.v)),1)*1.1;
  const X=(v:number)=>56+(v-lo)/(hi-lo)*(420-56-12),mid=107,Y=(v:number)=>mid-v/m*80,d=pts.map((p:Any,i:number)=>(i?"L":"M")+X(p.x).toFixed(1)+","+Y(p.v).toFixed(1)).join(" "),price=priceOf(cme,mode);
  return <svg className="kt-svg" viewBox="0 0 420 200" role="img" aria-label="Gamma เปลี่ยนเครื่องหมาย">{ticks(lo,hi,4).map(t=><text key={t} className="kt-axis" x={X(t)} y={192} textAnchor="middle">{p0(t)}</text>)}<line className="kt-grid" x1="56" x2="408" y1={mid} y2={mid}/><path className="kt-line" d={d}/>{price!==null&&price>=lo&&price<=hi&&<line className="kt-price dashed" x1={X(price)} x2={X(price)} y1="14" y2="174"/>}</svg>;
}

function Kpi({label,value,sub,tone}:{label:string;value:string;sub?:string;tone?:string}) {
  return <div className="kt-kpi"><span className="kt-kpi-l">{label}</span><strong className={tone?("kt-"+tone):""}>{value}</strong>{sub&&<small>{sub}</small>}</div>;
}

export function CmeLive({data}:{data:Any}) {
  const c=data?.cme; const [mode,setMode]=useState<Mode>("cfd"); const scrollRef=useRef<HTMLDivElement|null>(null);
  const clocks=useMemo(()=>Array.isArray(data?.dataClock?.entries)?data.dataClock.entries:[],[data]);
  if(!c||!Array.isArray(c.rows)||!c.rows.length) return <section className="kt-wrap" id="cme"><div className="kt-card"><span className="eyebrow">CME Data</span><h1>ข้อมูลทางการจาก CME</h1><div className="kt-empty">ยังไม่มี OI รายสไตรค์ใน snapshot ล่าสุด</div></div></section>;
  const updated=data?.observedAt?new Date(data.observedAt).toLocaleString("th-TH",{timeZone:"Asia/Bangkok",hour:"2-digit",minute:"2-digit",day:"2-digit",month:"short"}):"—";
  const oiAsOf=clocks.find((x:Any)=>String(x.name??"").toLowerCase().includes("oi"))?.as_of??null;
  const ratio=c.totals?.ratioPutCall; const callHeavy=n(ratio)?ratio<1:null; const price=priceOf(c,mode);
  const mp=n(c.maxPain)?(mode==="cfd"&&n(c.basis)?c.maxPain-c.basis:c.maxPain):null; const g=c.gamma??{},sg=c.sigma??{},rv=c.realized??{};
  const cols=(data?.gamma?.columns??[]).slice(0,4);
  return <section className="kt-wrap" id="cme">
    <div className="kt-card">
      <div className="kt-head"><div><span className="eyebrow">CME Data</span><h1>ข้อมูลทางการจาก CME</h1></div><div className="kt-seg"><button className={mode==="cfd"?"on":""} onClick={()=>setMode("cfd")}>CFD · XAUUSD</button><button className={mode==="fut"?"on":""} onClick={()=>setMode("fut")}>Futures · GC</button></div></div>
      <div className="kt-chips">{oiAsOf&&<span>OI ณ {String(oiAsOf).slice(0,10)}</span>}<span>อัปเดต {updated} ICT</span><span>Basis {signed(c.basis)} ณ snapshot</span>{n(c.dte)&&<span>DTE {Number(c.dte).toFixed(1)}</span>}</div>
      {cols.length>0&&<div className="kt-pills">{cols.map((x:Any,i:number)=><span key={x.code} className={"kt-pill"+(i===0?" on":"")}>{x.code}{n(x.dte)?" · "+Math.round(x.dte)+" วัน":""}</span>)}</div>}
      <div className="kt-kpis">
        <Kpi label="กรอบที่ตลาดคาด · วันนี้" value={n(sg.d1)?"±"+Number(sg.d1).toFixed(2):"—"} sub={n(sg.week)?"สัปดาห์นี้ ±"+Number(sg.week).toFixed(2):undefined}/>
        <Kpi label="ATM IV" value={pct(c.iv?.atm)} sub={c.iv?.source==="atm_interpolated_at_forward"?"คำนวณที่ราคา forward":"ค่า IV จาก chain"}/>
        <Kpi label="Put/Call (OI)" value={n(ratio)?Number(ratio).toFixed(2):"—"} sub={callHeavy===null?undefined:callHeavy?"Call มากกว่า Put":"Put มากกว่า Call"} tone={callHeavy===null?undefined:callHeavy?"up":"down"}/>
        <Kpi label="Max Pain" value={p2(mp)} sub={n(c.maxPain)?"CME "+p0(c.maxPain):undefined}/>
        <Kpi label="หมดอายุ" value={n(c.dte)?Math.round(c.dte)+" วัน":"—"} sub={c.expectedSource==="source"?"SD จาก CME":"SD คำนวณจาก ATM IV"}/>
      </div>
    </div>

    <div className="kt-card">
      <div className="kt-sub"><h2>Open Interest × กรอบที่ตลาดคาด</h2><span className="source-tag">{mode==="cfd"?"ระดับ CFD":"ระดับ Futures"}</span></div>
      <div className="kt-legend"><span><i className="sw put"/> Put ({p0(c.totals?.put)})</span><span><i className="sw call"/> Call ({p0(c.totals?.call)})</span><span><i className="sw line"/> ราคา {p2(price)}</span><span><i className="sw area"/> โซน 1 SD</span></div>
      <div className="kt-scroll" ref={scrollRef}><div className="kt-minw"><OiChart cme={c} mode={mode}/></div></div>
      <p className="kt-note">CW/PW = กำแพง OI อันดับ 1–3 · MP = Max Pain · OI เป็นข้อมูล snapshot ไม่ใช่ aggressor flow</p>
    </div>

    <div className="kt-card">
      <div className="kt-sub"><h2>เมตริกจากข้อมูล CME</h2><span className="source-tag">ออปชั่น {n(c.dte)?Math.round(c.dte)+" วัน":""}</span></div>
      <div className="kt-metrics">
        <div><span>Skew 25Δ</span><strong>{signed(c.iv?.skew25)}</strong><small>{n(c.iv?.skew25)?(c.iv.skew25>0?"Put แพงกว่า Call":"Call แพงกว่า Put"):"ไม่มีข้อมูล delta"}</small></div>
        <div><span>Gamma (GEX)</span><strong className={n(g.net)?(g.net<0?"kt-down":"kt-up"):""}>{compact(g.net)}</strong><small>{n(g.flip)?"flip "+p0(g.flip):"ยังไม่พบ flip"}</small></div>
        <div><span>IV Rank</span><strong>—</strong><small>ต้องสะสมประวัติ IV</small></div>
        <div><span>Put/Call (ปริมาณ)</span><strong>—</strong><small>ไม่มี volume source</small></div>
        <div><span>OI ในกรอบสัปดาห์</span><strong>{c.concentration?pct(c.concentration.pct):"—"}</strong><small>{c.concentration?"ช่วง "+p0(c.concentration.low)+"–"+p0(c.concentration.high):""}</small></div>
      </div>
      <div className="kt-two"><div className="kt-mini"><h3>IV ตามราคาใช้สิทธิ์ (Smile)</h3><SmileChart cme={c} mode={mode}/></div><div className="kt-mini"><h3>Gamma ตามราคาใช้สิทธิ์</h3><GammaBars cme={c} mode={mode}/></div></div>
      {Array.isArray(c.ivTerm)&&c.ivTerm.length>0&&<div className="kt-term"><span>โครงสร้าง IV</span>{c.ivTerm.map((x:Any)=><b key={String(x.code)}>{x.code} {pct(x.iv)}</b>)}</div>}
    </div>

    <div className="kt-two kt-gap">
      <div className="kt-card"><div className="kt-sub"><h2>Gamma เปลี่ยนเครื่องหมายที่ราคาใด</h2><span className="source-tag">spot-grid</span></div><ProfileChart cme={c} mode={mode}/></div>
      <div className="kt-card"><div className="kt-sub"><h2>Noise vs Stop</h2><span className="source-tag">23 ชม./วัน</span></div>
        <div className="kt-sigma"><div><span>15 นาที</span><strong>±{n(sg.m15)?Number(sg.m15).toFixed(1):"—"}</strong></div><div><span>1 ชม.</span><strong>±{n(sg.h1)?Number(sg.h1).toFixed(1):"—"}</strong></div><div><span>4 ชม.</span><strong>±{n(sg.h4)?Number(sg.h4).toFixed(1):"—"}</strong></div><div><span>1 วัน</span><strong>±{n(sg.d1)?Number(sg.d1).toFixed(1):"—"}</strong></div></div>
        <div className="kt-metrics two"><div><span>IV (ATM)</span><strong>{pct(c.iv?.atm)}</strong></div><div><span>Realized (M5)</span><strong>{rv.status==="OK"?pct(rv.rv):"—"}</strong><small>{rv.status==="OK"?"จากแท่งราคา":"แท่งราคาไม่พอ"}</small></div><div><span>IV − RV</span><strong className={n(rv.vrp)?(rv.vrp<0?"kt-down":"kt-up"):""}>{signed(rv.vrp)}</strong><small>{n(rv.vrp)?(rv.vrp<0?"ตลาดวิ่งแรงกว่าที่ option บอก":"option แพงกว่าที่วิ่งจริง"):""}</small></div></div>
        <p className="kt-note">Stop ที่แคบเกิน noise 1 ชม. มีโอกาสโดนแตะก่อน — ใช้ risk gate จาก Trade Plan ร่วมด้วย</p>
      </div>
    </div>
  </section>;
}
