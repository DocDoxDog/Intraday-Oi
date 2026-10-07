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
    TRIGGERED_WAIT_CONFIRMATION: "เข้าโซน • รอยืนยัน",
    ARMED: "รอจังหวะ",
    APPROACHING: "กำลังเข้าโซน",
    IN_ZONE: "อยู่ในโซน • รอ Action",
    WAIT: "WAIT",
    CONDITIONAL: "รอเงื่อนไข",
    DATA_INSUFFICIENT: "ข้อมูลไม่พอ",
    INVALIDATED: "หลุดเงื่อนไข",
    NO_TRADE: "NO TRADE",
  } as Record<string, string>)[s] ?? s;
}

function StatePill({ value }: { value: unknown }) {
  const s = String(value ?? "UNKNOWN").toUpperCase();
  return <span className={"pill " + s.toLowerCase()}>{stateLabel(value)}</span>;
}

function ActionStateCard({ label, setup, tone }: { label: string; setup: any; tone: "long" | "short" }) {
  if (!setup) return null;
  return (
    <article className={"action-state-card " + tone}>
      <div><span className="eyebrow">{label}</span><StatePill value={setup.state}/></div>
      <strong>{price(setup.zone_price)}</strong>
      <small>{setup.action ?? setup.event_required ?? "รอ Action"}</small>
    </article>
  );
}

function AuctionPanel({ auction }: { auction: any }) {
  return (
    <section className="panel">
      <div className="panel-head"><div><span className="eyebrow">AUCTION / PROFILE</span><h2>Auction</h2></div><span className="source-tag">{auction?.mode ?? "UNKNOWN"}</span></div>
      <div className="metric-list">
        <div><span>POC</span><strong>{price(auction?.poc)}</strong></div>
        <div><span>VAH</span><strong>{price(auction?.vah)}</strong></div>
        <div><span>VAL</span><strong>{price(auction?.val)}</strong></div>
        <div><span>Session High</span><strong>{price(auction?.session_high)}</strong></div>
        <div><span>Session Low</span><strong>{price(auction?.session_low)}</strong></div>
        <div><span>HVN</span><strong>{(auction?.hvn ?? []).map((x: any) => price(x)).join(" • ") || "—"}</strong></div>
        <div><span>LVN</span><strong>{(auction?.lvn ?? []).map((x: any) => price(x)).join(" • ") || "—"}</strong></div>
      </div>
      {auction?.approximation && <div className="context-line">โปรไฟล์เป็น BAR PROXY: ใช้ OHLCV ไม่ใช่ tick-by-tick volume profile</div>}
    </section>
  );
}

function MacroPanel({ macro }: { macro: any }) {
  const series = macro?.series ?? {};
  const item = (key: string) => series[key] ?? {};
  return (
    <section className="panel">
      <div className="panel-head"><div><span className="eyebrow">GOLD MACRO STATE</span><h2>{macro?.macro_bias ?? "UNKNOWN"}</h2></div><span className="source-tag">FRED</span></div>
      <div className="metric-list">
        <div><span>Real 10Y</span><strong>{price(item("real_10y").value)} · {item("real_10y").direction ?? "—"}</strong></div>
        <div><span>Nominal 10Y</span><strong>{price(item("nominal_10y").value)} · {item("nominal_10y").direction ?? "—"}</strong></div>
        <div><span>Fed Funds</span><strong>{price(item("policy_rate").value)} · {item("policy_rate").direction ?? "—"}</strong></div>
        <div><span>Broad USD</span><strong>{price(item("broad_usd").value)} · {item("broad_usd").direction ?? "—"}</strong></div>
      </div>
      <div className="context-line">Macro = context/regime ไม่ใช่ intraday entry signal</div>
    </section>
  );
}

function DataClockPanel({ clock }: { clock: any }) {
  const entries = Array.isArray(clock?.entries) ? clock.entries : [];
  return (
    <section className="panel">
      <div className="panel-head"><div><span className="eyebrow">DATA CLOCK</span><h2>Source Freshness</h2></div></div>
      <div className="clock-list">
        {entries.map((x: any) => (
          <div className="clock-row" key={x.name}>
            <div><strong>{x.name}</strong><small>{x.source} · {x.clock}</small></div>
            <StatePill value={x.status}/>
          </div>
        ))}
      </div>
    </section>
  );
}

function PlanCard({ title, tone, setup }: { title: string; tone: "long" | "short"; setup: any }) {
  if (!setup) return null;
  const state = setup.state ?? "UNKNOWN";
  const targets = Array.isArray(setup.targets) ? setup.targets : [];
  const action = setup.action ?? (
    tone === "long"
      ? "รอ Action ฝั่งซื้อในโซน"
      : "รอ Action ฝั่งขายในโซน"
  );
  const risk = setup.risk ?? {};
  const riskBlocked = setup.risk_blocked || risk.status === "NO_TRADE";

  return (
    <article className={"setup-card " + tone}>
      <div className="setup-head">
        <div>
          <span className="eyebrow">{tone === "long" ? "🟢 BUY" : "🔴 SELL"}</span>
          <h3>{title}</h3>
        </div>
        <StatePill value={state}/>
      </div>

      <div className="setup-action">{action}</div>

      <div className="trade-numbers">
        <div><span>เข้าเมื่อ</span><strong>{price(setup.trigger ?? setup.entry_reference)}</strong></div>
        <div><span>SL</span><strong>{price(setup.stop)}</strong></div>
      </div>

      <div className="tp-ladder">
        {[0, 1, 2, 3, 4].map((idx) => (
          <div key={idx} className="tp-row">
            <span>TP{idx + 1}</span>
            <strong>{price(targets[idx])}</strong>
          </div>
        ))}
      </div>

      {riskBlocked && <div className="risk-warn">Risk gate: {risk.reason ? String(risk.reason).replaceAll("_", " ") : "ยังไม่ผ่าน"} → ไม่ฝืนเข้า</div>}
      {Array.isArray(setup.confirmation) && setup.confirmation.length > 0 && (
        <div className="confirm-line">ต้องรอ: {setup.event_required ?? "confirmation"} </div>
      )}
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
  const resistance = [
    ["R1", levels.r1], ["R2", levels.r2], ["R3", levels.r3], ["R4", levels.r4],
  ];
  const support = [
    ["S1", levels.s1], ["S2", levels.s2], ["S3", levels.s3], ["S4", levels.s4],
  ];

  return (
    <section className="panel" id="levels">
      <div className="panel-head">
        <div><span className="eyebrow">PRICE MAP</span><h2>Key Levels</h2></div>
        <span className="source-tag">โซน ≠ Entry</span>
      </div>
      <div className="levels-clean">
        <div className="level-block resistance-block">
          <div className="level-label resistance-label">🔴 ต้าน</div>
          {resistance.map(([name, value]) =>
            <div className="level-row resistance" key={name}><span>{name}</span><strong>{price(value)}</strong></div>)}
        </div>

        <div className="mean-block">
          <span className="eyebrow">MEAN</span>
          <strong>{price(levels.pivot)}</strong>
          <small>จุดกึ่งกลางของ Market Map</small>
        </div>

        <div className="level-block support-block">
          <div className="level-label support-label">🟢 รับ</div>
          {support.map(([name, value]) =>
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
          <div className="action-zone long"><span>🟢 BUY — เบรกต้าน</span><strong>{price(levels.longReclaimTrigger ?? levels.callWall)}</strong><small>Break → Hold → Retest → Buy</small></div>
          <div className="action-zone support"><span>🟢 BUY — รับด้านล่าง</span><strong>{price(levels.longSupportTrigger ?? levels.putWall)}</strong><small>Support → Reaction → Buy</small></div>
          <div className="action-zone short"><span>🔴 SELL — ต้านไม่ผ่าน</span><strong>{price(levels.shortRejectionTrigger ?? levels.callWall)}</strong><small>Retest → Reject → Sell</small></div>
          <div className="action-zone short"><span>🔴 SELL — หลุดแนวรับ</span><strong>{price(levels.shortBreakdownTrigger ?? levels.putWall)}</strong><small>Break → Retest Fail → Sell</small></div>
        </div>
        <div className="action-note">ระดับราคาเป็น “โซน” ไม่ใช่ออเดอร์ทันที — แตะอย่างเดียวไม่ถือว่าเข้า ต้องเกิด Action + confirmation</div>
        <div className="action-state-grid">
          <ActionStateCard label="BUY — BREAKOUT / RECLAIM" setup={data.actionZones?.setups?.breakout_retest_long} tone="long"/>
          <ActionStateCard label="BUY — SUPPORT REACTION" setup={data.actionZones?.setups?.reversal_long} tone="long"/>
          <ActionStateCard label="SELL — RESISTANCE REJECTION" setup={data.actionZones?.setups?.reversal_short} tone="short"/>
          <ActionStateCard label="SELL — SUPPORT BREAKDOWN" setup={data.actionZones?.setups?.breakout_retest_short} tone="short"/>
        </div>
      </section>

      <GammaTable gamma={gamma}/>
      <LevelRail levels={levels}/>

      <section className="panel" id="plan">
        <div className="panel-head">
          <div><span className="eyebrow">EXECUTION ROADMAP</span><h2>Trade Plan — 4 ทาง</h2></div>
          <StatePill value={trade.status}/>
        </div>
        <div className="preferred-plan">
          <span className="eyebrow">แผนที่ให้ความสำคัญตอนนี้</span>
          <strong>{trade.preferredSetup ?? "WAIT"}</strong>
          <small>{trade.preferredAction ?? "รอให้เกิด Action ที่โซน"}</small>
        </div>
        <div className="plan-grid">
          <PlanCard title="BUY 1 — เบรกแนวต้าน" tone="long" setup={trade.buyBreakout}/>
          <PlanCard title="BUY 2 — เด้งจากแนวรับ" tone="long" setup={trade.buySupport}/>
          <PlanCard title="SELL 1 — ต้านไม่ผ่าน" tone="short" setup={trade.sellRejection}/>
          <PlanCard title="SELL 2 — หลุดแนวรับ" tone="short" setup={trade.sellBreakdown}/>
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

      <section className="two-col">
        <AuctionPanel auction={data.auction}/>
        <MacroPanel macro={data.macro}/>
      </section>
      <section className="two-col">
        <section className="panel">
          <div className="panel-head"><div><span className="eyebrow">ORDER FLOW</span><h2>Flow State</h2></div><span className="source-tag">{data.flow?.status ?? "UNKNOWN"}</span></div>
          <div className="metric-list">
            <div><span>Buy Aggression</span><strong>{compact(data.flow?.aggression?.buy)}</strong></div>
            <div><span>Sell Aggression</span><strong>{compact(data.flow?.aggression?.sell)}</strong></div>
            <div><span>Delta</span><strong>{compact(data.flow?.aggression?.delta)}</strong></div>
            <div><span>Book Imbalance</span><strong>{data.flow?.book?.imbalance != null ? Number(data.flow.book.imbalance).toFixed(2) : "—"}</strong></div>
          </div>
          <div className="context-line">{data.flow?.availability === "NOT_PROVIDED" ? "ยังไม่มี tick/order-book source จึงไม่สรุป aggressor flow" : "Flow ใช้เป็น evidence ไม่ใช่ direction oracle"}</div>
        </section>
        <DataClockPanel clock={data.dataClock}/>
      </section>

      <footer><span>Evidence &gt; Story</span><span>Updated {updated} ICT</span><span>Analysis only • No order execution</span></footer>
    </main>
  );
}
