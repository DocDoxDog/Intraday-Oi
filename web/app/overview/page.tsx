import { getMarketState } from "../lib/api";
export const dynamic = "force-dynamic";

const nav = [["Overview","/overview"],["Positioning","/positioning"],["Options","/options"],["Research","/research"],["Backtest","/backtest"],["Signals","/signals"],["AI Trader","/ai-trader"],["Alerts","/alerts"],["System","/system"]];

function metric(label:string,value:string|number|null|undefined,note?:string){
  return <div className="metric"><div className="metric-label">{label}</div><div className="metric-value">{value ?? "—"}</div>{note ? <div className="metric-note">{note}</div> : null}</div>;
}
export default async function OverviewPage(){
  const payload=await getMarketState("GC");
  const state=payload?.data.market_state;
  return <main className="terminal">
    <aside className="sidebar"><div className="brand"><div className="eyebrow">MARKET TERMINAL</div><div className="brand-title">OI POSITIONING</div><div className="brand-subtitle">INTELLIGENCE</div></div>
      <nav>{nav.map(([label,href],i)=><a className={i===0?"nav-item active":"nav-item"} href={href} key={href}><span>{String(i+1).padStart(2,"0")}</span>{label}</a>)}</nav>
    </aside>
    <section className="canvas">
      <header className="topbar"><div><div className="eyebrow">COMMAND CENTER</div><h1>GC Overview</h1></div>
        <div className="status-cluster"><span className={state?.data_status==="VALID"?"status":"status unknown"}>{state?.data_status ?? "DATA UNAVAILABLE"}</span><span className="timestamp">{payload?.as_of ?? "—"}</span></div>
      </header>
      {!state ? <section className="empty-state"><div className="empty-title">MarketState unavailable</div><p>Connect CANONICAL_MARKET_STATE_URL on the server runtime. The browser never receives the service token.</p></section> :
      <>
        <section className="metrics-grid">
          {metric("PRICE",state.price)}{metric("POSITIONING",state.positioning_regime)}{metric("VOLATILITY",state.volatility_regime)}
          {metric("NET GEX",state.gex,state.sign_convention ?? undefined)}{metric("GAMMA FLIP",state.gamma_flip)}{metric("CALL WALL",state.call_wall)}
          {metric("PUT WALL",state.put_wall)}{metric("DATA AGE",state.data_age_seconds == null ? "—" : state.data_age_seconds + "s")}
        </section>
        <section className="panel"><div className="panel-head"><div><div className="eyebrow">POSITIONING MAP</div><h2>Price × modelled exposure</h2></div><div className="legend"><span>GEX</span><span>OI</span><span>ΔOI</span><span>DEX</span></div></div>
          <div className="map"><div className="map-line" />
            {state.call_wall != null ? <div className="level call" style={{left:"82%"}}><b>CALL WALL</b><span>{state.call_wall}</span></div>:null}
            {state.gamma_flip != null ? <div className="level flip" style={{left:"48%"}}><b>GAMMA FLIP</b><span>{state.gamma_flip}</span></div>:null}
            {state.price != null ? <div className="level spot" style={{left:"56%"}}><b>SPOT</b><span>{state.price}</span></div>:null}
            {state.put_wall != null ? <div className="level put" style={{left:"18%"}}><b>PUT WALL</b><span>{state.put_wall}</span></div>:null}
          </div>
          <div className="panel-foot"><span>Assumption: {state.sign_convention ?? "none disclosed"}</span><span>Gamma source: {state.gamma_source ?? "unknown"}</span><span>Quality: {state.data_quality.toFixed(2)}</span></div>
        </section>
        <section className="split"><div className="panel compact"><div className="eyebrow">WHAT CHANGED</div>{metric("OI",state.oi,state.oi_change==null?undefined:"ΔOI " + state.oi_change)}{metric("DEX",state.dex)}{metric("IV",state.iv)}{metric("REALIZED VOL",state.realized_vol)}</div>
          <div className="panel compact"><div className="eyebrow">EVIDENCE</div><div className="evidence-list">{(state.evidence??[]).map(x=><div key={x}>{x}</div>)}{(state.assumptions??[]).map(x=><div className="muted" key={x}>ASSUMPTION · {x}</div>)}</div></div></section>
        <footer className="provenance"><span>Dataset {state.dataset_version}</span><span>Calculation {state.calculation_version}</span><span>Observed state is distinguished from inferred positioning.</span></footer>
      </>}
    </section>
  </main>;
}