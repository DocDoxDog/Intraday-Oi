"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type Data = any;

const nf = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function price(v: unknown) {
  return typeof v === "number" && Number.isFinite(v) ? nf.format(v) : "—";
}

function compact(v: unknown) {
  if (typeof v !== "number" || !Number.isFinite(v)) return "—";
  const a = Math.abs(v);
  if (a >= 1_000_000) return (v / 1_000_000).toFixed(1) + "M";
  if (a >= 1_000) return (v / 1_000).toFixed(1) + "K";
  return v.toFixed(0);
}

function stateLabel(v: unknown) {
  const s = String(v ?? "UNKNOWN").toUpperCase();
  return ({
    CONFIRMED: "ยืนยันแล้ว",
    TRIGGERED: "เข้าโซน • รอยืนยัน",
    ARMED: "รอจังหวะ",
    CONDITIONAL: "รอเงื่อนไข",
    DATA_INSUFFICIENT: "ข้อมูลไม่พอ",
    NO_TRADE: "NO TRADE",
  } as Record<string, string>)[s] ?? s;
}

function StatePill({ value }: { value: unknown }) {
  const s = String(value ?? "UNKNOWN").toUpperCase();
  return <span className={"pill " + s.toLowerCase()}>{stateLabel(value)}</span>;
}

function SetupCard({ title, tone, setup }: { title: string; tone: "long" | "short"; setup: any }) {
  if (!setup) return null;
  const state = setup.state ?? "UNKNOWN";
  const targets = Array.isArray(setup.targets) ? setup.targets.filter((x: any) => typeof x === "number") : [];
  const isLong = tone === "long";
  const action = isLong
    ? "รอราคาเบรก/ยืนเหนือโซน และ M15/M5 ยืนยันขึ้น"
    : "รอเด้งกลับทดสอบโซน แล้วไม่ผ่าน + M15/M5 ยืนยันลง";

  return (
    <article className={"setup-card " + tone}>
      <div className="setup-head">
        <div>
          <span className="eyebrow">{isLong ? "🟢 LONG" : "🔴 SHORT"}</span>
          <h3>{title}</h3>
        </div>
        <StatePill value={state} />
      </div>
      <div className="setup-action">{action}</div>
      <div className="trade-numbers">
        <div><span>เข้า</span><strong>{price(setup.trigger ?? setup.entry_reference)}</strong></div>
        <div><span>SL</span><strong>{price(setup.stop)}</strong></div>
        <div className="targets"><span>TP</span><strong>{targets.length ? targets.map(price).join(" → ") : "ยังไม่มี"}</strong></div>
      </div>
      {setup.rr1_eligible === false && <div className="risk-warn">Risk/Reward ยังไม่ผ่านเกณฑ์ → ไม่ฝืนเข้า</div>}
    </article>
  );
}

function GammaTable({ gamma }: { gamma: any }) {
  const columns = gamma?.displayColumns?.length ? gamma.displayColumns : (gamma?.columns ?? []).slice(0, 7);
  const matrix = gamma?.matrix ?? [];
  const primary = gamma?.primary ?? [];

  const nearestRows = useMemo(() => {
    const current = Number(gamma?.currentPrice);
    const sorted = [...matrix].sort((a, b) => Math.abs((a.strike ?? 0) - current) - Math.abs((b.strike ?? 0) - current));
    return sorted.slice(0, 28).sort((a, b) => (b.strike ?? 0) - (a.strike ?? 0));
  }, [matrix, gamma?.currentPrice]);

  return (
    <section className="panel gamma-panel" id="gamma">
      <div className="panel-head">
        <div><span className="eyebrow">OPTIONS STRUCTURE</span><h2>Gamma Table</h2></div>
        <span className="source-tag">CME / QuikStrike</span>
      </div>
      <div className="gamma-meta">
        <span>เขียว = +GEX</span><span>แดง = −GEX</span><span>— = ไม่มี source observation</span>
      </div>
      <div className="table-scroll">
        <table className="gamma-matrix">
          <thead><tr><th>Strike</th>{columns.map((c: any) => <th key={c.code}>{c.code}<small>{c.dte != null ? "DTE " + Number(c.dte).toFixed(1) : "DTE —"}</small></th>)}</tr></thead>
          <tbody>
            {nearestRows.map((row: any) => (
              <tr key={String(row.strike)}>
                <th>{price(row.strike)}</th>
                {columns.map((c: any) => {
                  const v = row[c.code];
                  const cls = typeof v !== "number" ? "empty" : v > 0 ? "positive" : v < 0 ? "negative" : "zero";
                  return <td className={cls} key={c.code}>{typeof v === "number" ? (v / 1_000_000).toFixed(1) : "—"}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className="gamma-detail">
        <summary>ดู Call / Put OI และ GEX ราย Strike</summary>
        <div className="table-scroll">
          <table className="detail-table">
            <thead><tr><th>Strike</th><th>Call OI</th><th>Put OI</th><th>Call GEX</th><th>Put GEX</th><th>Net GEX</th></tr></thead>
            <tbody>
              {primary.slice(0, 35).map((r: any) => (
                <tr key={String(r.strike)}>
                  <th>{price(r.strike)}</th><td>{compact(r.call_oi)}</td><td>{compact(r.put_oi)}</td>
                  <td className={r.call_gex > 0 ? "up" : ""}>{compact(r.call_gex)}</td>
                  <td className={r.put_gex < 0 ? "down" : ""}>{compact(r.put_gex)}</td>
                  <td className={r.net_gex > 0 ? "up" : r.net_gex < 0 ? "down" : ""}>{compact(r.net_gex)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}

function LevelRail({ levels }: { levels: any }) {
  return (
    <section className="panel" id="levels">
      <div className="panel-head"><div><span className="eyebrow">PRICE MAP</span><h2>Key Levels</h2></div></div>
      <div className="levels-grid">
        <div className="level-column">
          <div className="level-label resistance-label">แนวต้าน</div>
          {([["R3", levels.r3], ["R2", levels.r2], ["R1", levels.r1]] as const).map(([name, value]) =>
            <div className="level-row resistance" key={name}><span>{name}</span><strong>{price(value)}</strong></div>)}
        </div>
        <div className="decision-card">
          <span>จุดเปลี่ยน</span><strong>{price(levels.longTrigger ?? levels.shortTrigger)}</strong>
          <small>ยืนเหนือ → มองขึ้น<br/>รีเทสต์ไม่ผ่าน → มองลง</small>
        </div>
        <div className="level-column">
          <div className="level-label support-label">แนวรับ</div>
          {([["S1", levels.s1], ["S2", levels.s2], ["S3", levels.s3]] as const).map(([name, value]) =>
            <div className="level-row support" key={name}><span>{name}</span><strong>{price(value)}</strong></div>)}
        </div>
      </div>
    </section>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/market", { cache: "no-store" });
      const json = await res.json();
      if (!res.ok || json.status === "ERROR") throw new Error(json.error ?? "โหลดข้อมูลไม่สำเร็จ");
      setData(json);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "โหลดข้อมูลไม่สำเร็จ");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = window.setInterval(load, 60_000);
    return () => window.clearInterval(id);
  }, [load]);

  if (loading && !data) return <main className="shell"><div className="loading">กำลังโหลด Market State…</div></main>;
  if (error && !data) return <main className="shell"><div className="error-card"><b>Dashboard ยังอ่านข้อมูลไม่ได้</b><span>{error}</span></div></main>;
  if (!data) return null;

  const market = data.market ?? {};
  const regime = data.regime ?? {};
  const levels = data.levels ?? {};
  const trade = data.trade ?? {};
  const gamma = data.gamma ?? {};
  const isBear = String(regime.bias).toUpperCase().includes("SELL") || String(regime.bias).toUpperCase().includes("BEAR");
  const updated = data.observedAt
    ? new Date(data.observedAt).toLocaleString("th-TH", { timeZone: "Asia/Bangkok", hour: "2-digit", minute: "2-digit", day: "2-digit", month: "short" })
    : "—";

  return (
    <main className="shell">
      <header className="topbar">
        <div><div className="brand"><span className="brand-dot" /> GOLD MARKET INTELLIGENCE</div><div className="subbrand">CME • OI • GAMMA • ORDER FLOW • MARKET STRUCTURE</div></div>
        <button className="refresh" onClick={load} aria-label="Refresh">↻</button>
      </header>

      <section className="hero">
        <div className="hero-main">
          <span className="eyebrow">FUTURES {market.contract ?? "GC"}</span>
          <div className="hero-price">{price(market.cfd ?? market.futures)}</div>
          <div className="hero-sub"><span>Futures {price(market.futures)}</span><span>Spot {price(market.spot)}</span><span>Basis {market.basis != null ? (market.basis >= 0 ? "+" : "") + price(market.basis) : "—"}</span></div>
        </div>
        <div className={"regime-card " + (isBear ? "bear" : "bull")}>
          <span className="eyebrow">MARKET REGIME</span><strong>{regime.bias ?? "WAIT"}</strong><StatePill value={trade.status ?? regime.status}/><small>{regime.marketRegime ?? "UNKNOWN"}</small>
        </div>
      </section>

      <nav className="quick-nav"><a href="#action">Action</a><a href="#gamma">Gamma</a><a href="#levels">Levels</a><a href="#plan">Plan</a></nav>

      <section className="panel action-panel" id="action">
        <div className="panel-head"><div><span className="eyebrow">DECISION LAYER</span><h2>Action Zones</h2></div><span className="source-tag">รอ Action ไม่ไล่ราคา</span></div>
        <div className="action-grid">
          <div className="action-zone short"><span>🔴 SHORT</span><strong>{price(levels.shortTrigger)}</strong><small>Retest → Reject → Confirm</small></div>
          <div className="action-zone long"><span>🟢 LONG</span><strong>{price(levels.longTrigger)}</strong><small>Break/Hold → Confirm</small></div>
          {levels.longSupportTrigger != null && <div className="action-zone support"><span>🟢 LONG รับด้านล่าง</span><strong>{price(levels.longSupportTrigger)}</strong><small>Support → Reaction → Confirm</small></div>}
        </div>
        <div className="action-note">สิ่งที่ระบบรู้แน่คือ “โซนที่ควรรอ” ส่วน Direction ต้องให้ Price Action + Technical + Flow ยืนยัน</div>
      </section>

      <GammaTable gamma={gamma}/>
      <LevelRail levels={levels}/>

      <section className="panel" id="plan">
        <div className="panel-head"><div><span className="eyebrow">EXECUTION ROADMAP</span><h2>Trade Plan</h2></div><StatePill value={trade.status}/></div>
        <div className="plan-grid">
          <SetupCard title="Failed Retest" tone="short" setup={trade.short}/>
          <SetupCard title="Breakout / Reclaim" tone="long" setup={trade.long}/>
          <SetupCard title="Support Reaction" tone="long" setup={trade.longSupport}/>
        </div>
        <div className="no-trade">ไม่มี Confirmation หรือ Risk/Reward ไม่ผ่าน → <b>NO TRADE</b></div>
      </section>

      <section className="two-col">
        <section className="panel">
          <div className="panel-head"><div><span className="eyebrow">FLOW / TECHNICAL</span><h2>Market Read</h2></div></div>
          <p className="read-text">{regime.overview || regime.what || "ยังไม่มี market narrative ที่ยืนยันได้"}</p>
          <div className="metric-list">
            <div><span>HTF</span><strong>{String(data.technical?.htf ?? "UNKNOWN").toUpperCase()}</strong></div>
            <div><span>M15</span><strong>{data.technical?.m15?.trend ?? "—"}</strong></div>
            <div><span>M5</span><strong>{data.technical?.m5?.trend ?? "—"}</strong></div>
            <div><span>Location</span><strong>{levels.location ?? "UNKNOWN"}</strong></div>
          </div>
        </section>
        <section className="panel">
          <div className="panel-head"><div><span className="eyebrow">MACRO / CONTEXT</span><h2>Why</h2></div></div>
          <p className="read-text">{regime.why || "ยังไม่มีเหตุผลจาก evidence pack เพิ่มเติม"}</p>
          <div className="context-line">{regime.macro || "ไม่มี Macro/News evidence ที่เพียงพอ"}</div>
          <div className="context-line">{regime.financialEngineering || "ไม่มี Financial Engineering context เพิ่มเติม"}</div>
        </section>
      </section>

      <footer><span>Evidence &gt; Story</span><span>Updated {updated} ICT</span><span>Analysis only • No order execution</span></footer>
    </main>
  );
}
