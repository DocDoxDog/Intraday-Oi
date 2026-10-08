"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type Data = any;

const nf = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

function num(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function price(value: unknown) {
  const n = num(value);
  return n === null ? "—" : nf.format(n);
}

function signed(value: unknown) {
  const n = num(value);
  return n === null ? "—" : (n >= 0 ? "+" : "") + nf.format(n);
}

function compact(value: unknown) {
  const n = num(value);
  if (n === null) return "—";
  const a = Math.abs(n);
  if (a >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (a >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return n.toFixed(0);
}

function stateLabel(value: unknown) {
  const s = String(value ?? "UNKNOWN").toUpperCase();
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

function Panel({
  id,
  eyebrow,
  title,
  meta,
  children,
  className = "",
}: {
  id?: string;
  eyebrow: string;
  title: string;
  meta?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section id={id} className={"panel " + className}>
      <div className="panel-head">
        <div>
          <span className="eyebrow">{eyebrow}</span>
          <h2>{title}</h2>
        </div>
        {meta}
      </div>
      {children}
    </section>
  );
}

function getKeyLevels(levels: any, current: number | null) {
  const canonical = Array.isArray(levels?.keyLevels)
    ? levels.keyLevels
        .map((item: any) => ({
          price: num(item?.price ?? item?.level ?? item?.value),
          role: String(item?.role ?? "").toUpperCase(),
          source: String(item?.source ?? item?.basis ?? "market map"),
          label: item?.label ?? item?.name ?? null,
        }))
        .filter((item: any) => item.price !== null)
    : [];

  if (canonical.length) return canonical.sort((a: any, b: any) => b.price - a.price);

  const fallback = [
    ["R4", levels?.r4, "RESISTANCE_CANDIDATE"],
    ["R3", levels?.r3, "RESISTANCE_CANDIDATE"],
    ["R2", levels?.r2, "RESISTANCE_CANDIDATE"],
    ["R1", levels?.r1, "RESISTANCE_CANDIDATE"],
    ["MEAN", levels?.pivot, "MEAN"],
    ["S1", levels?.s1, "SUPPORT_CANDIDATE"],
    ["S2", levels?.s2, "SUPPORT_CANDIDATE"],
    ["S3", levels?.s3, "SUPPORT_CANDIDATE"],
    ["S4", levels?.s4, "SUPPORT_CANDIDATE"],
  ]
    .map(([label, value, role]) => ({ label, price: num(value), role, source: "market map" }))
    .filter((item: any) => item.price !== null);

  return fallback.sort((a: any, b: any) => b.price - a.price);
}

function levelTone(role: string) {
  if (role.includes("RESIST")) return "resistance";
  if (role.includes("SUPPORT")) return "support";
  return "mean";
}

function levelPosition(value: number, min: number, max: number) {
  if (max === min) return 50;
  return ((max - value) / (max - min)) * 100;
}

function RouteCard({
  title,
  subtitle,
  tone,
  setup,
}: {
  title: string;
  subtitle: string;
  tone: "buy" | "sell";
  setup: any;
}) {
  if (!setup) return null;
  const targets = Array.isArray(setup.targets) ? setup.targets : [];
  const risk = setup.risk ?? {};
  const blocked = Boolean(setup.risk_blocked) || risk.status === "NO_TRADE";
  const trigger = setup.trigger ?? setup.entry_reference;

  return (
    <article className={"route-card " + tone}>
      <div className="route-top">
        <div>
          <span className="route-label">{tone === "buy" ? "BUY" : "SELL"}</span>
          <h3>{title}</h3>
          <p>{subtitle}</p>
        </div>
        <StatePill value={setup.state}/>
      </div>

      <div className="route-action">{setup.action ?? "รอ Action ที่โซน"}</div>

      {setup.watch_level != null && trigger == null ? (
        <div className="watch-box">
          เฝ้าระดับ <strong>{price(setup.watch_level)}</strong>
          <span> ยังไม่เข้าโซน Local</span>
        </div>
      ) : (
        <div className="route-levels">
          <div>
            <span>เข้าเมื่อ</span>
            <strong>{price(trigger)}</strong>
          </div>
          <div>
            <span>SL</span>
            <strong>{price(setup.stop)}</strong>
          </div>
          <div>
            <span>TP1</span>
            <strong>{price(targets[0])}</strong>
          </div>
          <div>
            <span>TP2</span>
            <strong>{price(targets[1])}</strong>
          </div>
        </div>
      )}

      {Array.isArray(setup.confirmation) && setup.confirmation.length > 0 && (
        <div className="route-footer">ต้องรอ: {setup.event_required ?? "confirmation"}</div>
      )}

      {blocked && (
        <div className="risk-gate">
          Risk gate • {risk.reason ? String(risk.reason).replaceAll("_", " ") : "ยังไม่ผ่าน"} → NO TRADE
        </div>
      )}
    </article>
  );
}

function GammaTable({ gamma }: { gamma: any }) {
  const columns = gamma?.displayColumns?.length
    ? gamma.displayColumns
    : (gamma?.columns ?? []).slice(0, 7);
  const matrix = Array.isArray(gamma?.matrix) ? gamma.matrix : [];
  const primary = Array.isArray(gamma?.primary) ? gamma.primary : [];

  const nearestRows = useMemo(() => {
    const current = num(gamma?.currentPrice);
    const sorted = [...matrix].sort((a, b) =>
      Math.abs((a.strike ?? 0) - (current ?? 0)) -
      Math.abs((b.strike ?? 0) - (current ?? 0))
    );
    return sorted.slice(0, 32).sort((a, b) => (b.strike ?? 0) - (a.strike ?? 0));
  }, [matrix, gamma?.currentPrice]);

  return (
    <Panel
      id="gamma"
      eyebrow="OPTIONS STRUCTURE"
      title="Gamma Table"
      meta={<span className="source-tag">CME / QuikStrike</span>}
      className="gamma-panel"
    >
      <div className="gamma-topline">
        <div>
          <span>Current</span>
          <strong>{price(gamma?.currentPrice)}</strong>
        </div>
        <div>
          <span>State</span>
          <strong>{gamma?.status ?? "UNKNOWN"}</strong>
        </div>
        <div className="gamma-legend">
          <span><i className="dot positive"/> +GEX</span>
          <span><i className="dot negative"/> −GEX</span>
        </div>
      </div>

      <div className="table-scroll">
        <table className="gamma-matrix">
          <thead>
            <tr>
              <th>Strike</th>
              {columns.map((column: any) => (
                <th key={column.code}>
                  {column.code}
                  <small>{column.dte != null ? "DTE " + Number(column.dte).toFixed(1) : "DTE —"}</small>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {nearestRows.map((row: any) => (
              <tr key={String(row.strike)}>
                <th>{price(row.strike)}</th>
                {columns.map((column: any) => {
                  const value = row[column.code];
                  const cls =
                    typeof value !== "number"
                      ? "empty"
                      : value > 0
                        ? "positive"
                        : value < 0
                          ? "negative"
                          : "zero";

                  return (
                    <td className={cls} key={column.code}>
                      {typeof value === "number" ? (value / 1_000_000).toFixed(1) : "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <details className="gamma-detail">
        <summary>เปิด Call / Put OI + GEX ราย Strike</summary>
        <div className="table-scroll detail-scroll">
          <table className="detail-table">
            <thead>
              <tr>
                <th>Strike</th>
                <th>Call OI</th>
                <th>Put OI</th>
                <th>Call GEX</th>
                <th>Put GEX</th>
                <th>Net GEX</th>
              </tr>
            </thead>
            <tbody>
              {primary.slice(0, 40).map((row: any) => (
                <tr key={String(row.strike)}>
                  <th>{price(row.strike)}</th>
                  <td>{compact(row.call_oi)}</td>
                  <td>{compact(row.put_oi)}</td>
                  <td className={row.call_gex > 0 ? "up" : ""}>{compact(row.call_gex)}</td>
                  <td className={row.put_gex < 0 ? "down" : ""}>{compact(row.put_gex)}</td>
                  <td className={row.net_gex > 0 ? "up" : row.net_gex < 0 ? "down" : ""}>{compact(row.net_gex)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </Panel>
  );
}

function FlowSpine({
  levels,
  current,
}: {
  levels: any;
  current: number | null;
}) {
  const points = getKeyLevels(levels, current);
  if (!points.length) {
    return (
      <Panel eyebrow="MARKET MAP" title="Flow Spine">
        <div className="empty-state">ยังไม่มี structural levels ที่ยืนยันได้</div>
      </Panel>
    );
  }

  const values = points.map((x: any) => x.price) as number[];
  const max = Math.max(...values, current ?? -Infinity);
  const min = Math.min(...values, current ?? Infinity);
  const currentPos = current === null ? null : levelPosition(current, min, max);

  return (
    <Panel
      id="levels"
      eyebrow="MARKET MAP"
      title="Flow Spine"
      meta={<span className="source-tag">สูง → ต่ำ</span>}
      className="flow-spine-panel"
    >
      <div className="spine-wrap">
        <div className="spine">
          <div className="spine-grid"/>
          <div className="spine-line"/>
          {currentPos !== null && (
            <div className="current-marker" style={{ top: `${currentPos}%` }}>
              <span>NOW</span>
              <strong>{price(current)}</strong>
            </div>
          )}
          {points.map((point: any, index: number) => {
            const pos = levelPosition(point.price, min, max);
            const tone = levelTone(point.role);
            return (
              <div
                key={`${point.label ?? point.price}-${index}`}
                className={`level-marker ${tone}`}
                style={{ top: `${pos}%` }}
              >
                <i/>
                <div>
                  <span>{point.label ?? (tone === "resistance" ? "ต้าน" : tone === "support" ? "รับ" : "MEAN")}</span>
                  <strong>{price(point.price)}</strong>
                </div>
              </div>
            );
          })}
          <div className="scanline"/>
        </div>

        <div className="spine-read">
          <div className="spine-read-head">
            <span className="eyebrow">PRICE LOCATION</span>
            <StatePill value={levels?.location}/>
          </div>
          <div className="spine-highlight">
            <span>Call Wall</span>
            <strong>{price(levels?.callWall)}</strong>
          </div>
          <div className="spine-highlight">
            <span>Mean</span>
            <strong>{price(levels?.pivot)}</strong>
          </div>
          <div className="spine-highlight">
            <span>Put Wall</span>
            <strong>{price(levels?.putWall)}</strong>
          </div>
          <p>ระดับเหล่านี้คือ Market Map; จุดเข้าใช้เฉพาะเมื่อ Action + Confirmation + Risk ผ่าน</p>
        </div>
      </div>
    </Panel>
  );
}

function MarketNarrative({
  regime,
  priceMemory,
  levels,
  trade,
}: {
  regime: any;
  priceMemory: any;
  levels: any;
  trade: any;
}) {
  const path = String(priceMemory?.path_direction ?? priceMemory?.direction ?? "UNKNOWN").toUpperCase();
  const swingHigh = num(priceMemory?.swing_high ?? priceMemory?.high);
  const swingLow = num(priceMemory?.swing_low ?? priceMemory?.low);
  const origin =
    path !== "UNKNOWN"
      ? `OHLC memory: path ${path}${swingLow !== null && swingHigh !== null ? ` • swing ${price(swingLow)} → ${price(swingHigh)}` : ""}`
      : "OHLC memory: รอ history ที่ยืนยันได้";

  return (
    <Panel
      eyebrow="AI FLOW ANALYSIS"
      title="Market Read"
      meta={<span className="live-chip"><i/> LIVE</span>}
      className="narrative-panel"
    >
      <div className="narrative-steps">
        <div className="narrative-step">
          <span>01 / WHERE PRICE CAME FROM</span>
          <strong>{origin}</strong>
        </div>
        <div className="narrative-step active">
          <span>02 / WHAT PRICE IS TESTING</span>
          <strong>{regime?.overview || "ยังไม่มี narrative ที่ยืนยันได้"}</strong>
        </div>
        <div className="narrative-step">
          <span>03 / WHAT HAPPENS NEXT</span>
          <strong>{trade?.preferredAction || "รอ Action ที่โซนใกล้ราคา"}</strong>
        </div>
      </div>

      <div className="narrative-footer">
        <div>
          <span>Location</span>
          <strong>{levels?.location ?? "UNKNOWN"}</strong>
        </div>
        <div>
          <span>Why</span>
          <strong>{regime?.why || "ยังไม่มีเหตุผลเพิ่มเติมจาก evidence pack"}</strong>
        </div>
      </div>
    </Panel>
  );
}

function EvidenceStack({ data }: { data: any }) {
  const macro = data.macro ?? {};
  const series = macro.series ?? {};
  const item = (key: string) => series[key] ?? {};
  const flow = data.flow ?? {};
  const gamma = data.gamma ?? {};
  const tech = data.technical ?? {};

  return (
    <div className="evidence-grid">
      <div className="evidence-card">
        <div className="evidence-icon">Γ</div>
        <div>
          <span>GAMMA</span>
          <strong>{gamma.status ?? "UNKNOWN"}</strong>
          <small>options structure</small>
        </div>
      </div>

      <div className="evidence-card">
        <div className="evidence-icon">OI</div>
        <div>
          <span>POSITIONING</span>
          <strong>{data.regime?.microstructure || "ดูจาก OI / GEX"}</strong>
          <small>positioning evidence</small>
        </div>
      </div>

      <div className="evidence-card">
        <div className="evidence-icon">IV</div>
        <div>
          <span>VOLATILITY</span>
          <strong>{data.regime?.macro ? "มี context" : "ยังไม่ยืนยัน"}</strong>
          <small>DTE {data.market?.dte != null ? Number(data.market.dte).toFixed(1) : "—"}</small>
        </div>
      </div>

      <div className="evidence-card">
        <div className="evidence-icon">FX</div>
        <div>
          <span>MACRO</span>
          <strong>{macro.macro_bias ?? "UNKNOWN"}</strong>
          <small>
            USD {item("broad_usd").value != null ? price(item("broad_usd").value) : "—"} •
            Real 10Y {item("real_10y").value != null ? price(item("real_10y").value) : "—"}
          </small>
        </div>
      </div>

      <div className="evidence-card">
        <div className="evidence-icon">Δ</div>
        <div>
          <span>FLOW</span>
          <strong>{flow.status ?? "UNKNOWN"}</strong>
          <small>{flow.availability === "NOT_PROVIDED" ? "ไม่มี tick/order-book source" : "order flow evidence"}</small>
        </div>
      </div>

      <div className="evidence-card">
        <div className="evidence-icon">TF</div>
        <div>
          <span>STRUCTURE</span>
          <strong>{String(tech.htf ?? "UNKNOWN").toUpperCase()}</strong>
          <small>H1 / M15 / M5 alignment</small>
        </div>
      </div>
    </div>
  );
}

function DataClock({ clock }: { clock: any }) {
  const entries = Array.isArray(clock?.entries) ? clock.entries : [];
  return (
    <Panel
      eyebrow="DATA TRUST"
      title="Source Clock"
      meta={<span className="source-tag">freshness</span>}
      className="clock-panel"
    >
      <div className="clock-list">
        {entries.length ? entries.map((item: any) => (
          <div className="clock-row" key={item.name}>
            <div>
              <strong>{item.name}</strong>
              <span>{item.source} · {item.clock}</span>
            </div>
            <StatePill value={item.status}/>
          </div>
        )) : (
          <div className="empty-state">ยังไม่มี source clock</div>
        )}
      </div>
    </Panel>
  );
}

function MacroPanel({ macro }: { macro: any }) {
  const series = macro?.series ?? {};
  const item = (key: string) => series[key] ?? {};
  return (
    <Panel
      eyebrow="MACRO / CONTEXT"
      title={macro?.macro_bias ?? "Macro State"}
      meta={<span className="source-tag">FRED</span>}
    >
      <div className="macro-grid">
        <div><span>Real 10Y</span><strong>{price(item("real_10y").value)}</strong><small>{item("real_10y").direction ?? "—"}</small></div>
        <div><span>Nominal 10Y</span><strong>{price(item("nominal_10y").value)}</strong><small>{item("nominal_10y").direction ?? "—"}</small></div>
        <div><span>Fed Funds</span><strong>{price(item("policy_rate").value)}</strong><small>{item("policy_rate").direction ?? "—"}</small></div>
        <div><span>Broad USD</span><strong>{price(item("broad_usd").value)}</strong><small>{item("broad_usd").direction ?? "—"}</small></div>
      </div>
      <div className="context-line">Macro ใช้กำหนด context/regime ไม่ใช่ปุ่มเข้าแบบ intraday โดยตรง</div>
    </Panel>
  );
}

function AuctionPanel({ auction }: { auction: any }) {
  return (
    <Panel eyebrow="AUCTION / PROFILE" title="Auction" meta={<span className="source-tag">{auction?.mode ?? "UNKNOWN"}</span>}>
      <div className="macro-grid auction-grid">
        <div><span>POC</span><strong>{price(auction?.poc)}</strong></div>
        <div><span>VAH</span><strong>{price(auction?.vah)}</strong></div>
        <div><span>VAL</span><strong>{price(auction?.val)}</strong></div>
        <div><span>Session High</span><strong>{price(auction?.session_high)}</strong></div>
        <div><span>Session Low</span><strong>{price(auction?.session_low)}</strong></div>
        <div><span>HVN</span><strong>{(auction?.hvn ?? []).map((x: any) => price(x)).join(" • ") || "—"}</strong></div>
      </div>
      {auction?.approximation && (
        <div className="context-line">BAR PROXY — ใช้ OHLCV ไม่ใช่ tick-by-tick volume profile</div>
      )}
    </Panel>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [pulse, setPulse] = useState(false);

  const load = useCallback(async () => {
    try {
      setPulse(true);
      const response = await fetch("/api/market", { cache: "no-store" });
      const json = await response.json();
      if (!response.ok || json.status === "ERROR") {
        throw new Error(json.error ?? "โหลดข้อมูลไม่สำเร็จ");
      }
      setData(json);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "โหลดข้อมูลไม่สำเร็จ");
    } finally {
      setLoading(false);
      window.setTimeout(() => setPulse(false), 650);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = window.setInterval(load, 60_000);
    return () => window.clearInterval(interval);
  }, [load]);

  if (loading && !data) {
    return (
      <main className="app-shell">
        <div className="ambient-grid"/>
        <div className="loader-screen">
          <div className="loader-core"><span/></div>
          <strong>กำลังประกอบ Market State…</strong>
          <small>CME / OI / Gamma / OHLC / Macro</small>
        </div>
      </main>
    );
  }

  if (error && !data) {
    return (
      <main className="app-shell">
        <div className="ambient-grid"/>
        <div className="loader-screen error-screen">
          <strong>Dashboard ยังอ่านข้อมูลไม่ได้</strong>
          <span>{error}</span>
        </div>
      </main>
    );
  }

  if (!data) return null;

  const market = data.market ?? {};
  const regime = data.regime ?? {};
  const levels = data.levels ?? {};
  const trade = data.trade ?? {};
  const current = num(market.cfd ?? market.futures);
  const priceMemory = data.technical?.priceMemory ?? {};
  const isBear = String(regime.bias).toUpperCase().includes("SELL") || String(regime.bias).toUpperCase().includes("BEAR");
  const updated = data.observedAt
    ? new Date(data.observedAt).toLocaleString("th-TH", {
        timeZone: "Asia/Bangkok",
        hour: "2-digit",
        minute: "2-digit",
        day: "2-digit",
        month: "short",
      })
    : "—";

  const distanceToMean = current !== null && num(levels.pivot) !== null
    ? current - Number(levels.pivot)
    : null;

  return (
    <main className={`app-shell ${pulse ? "refresh-pulse" : ""}`}>
      <div className="ambient-grid"/>
      <div className="ambient-glow glow-a"/>
      <div className="ambient-glow glow-b"/>

      <header className="topbar">
        <div className="brand-block">
          <div className="brand-line">
            <span className="brand-mark"><i/><i/><i/></span>
            <strong>GOLD / INTELLIGENCE</strong>
            <span className="brand-badge">INTRADAY-OI</span>
          </div>
          <div className="subbrand">FLOW ANALYSIS DESK · CME · OI · GAMMA · OHLC MEMORY · MACRO</div>
        </div>

        <div className="top-actions">
          <div className="live-chip"><i/> LIVE <span>{updated} ICT</span></div>
          <button className="refresh-button" onClick={load} aria-label="Refresh market data">↻</button>
        </div>
      </header>

      <nav className="command-bar" aria-label="Dashboard sections">
        <a href="#decision">Decision</a>
        <a href="#levels">Market Map</a>
        <a href="#plan">Trade Plan</a>
        <a href="#gamma">Gamma</a>
        <a href="#evidence">Evidence</a>
      </nav>

      <section className="hero-grid">
        <article className="price-stage">
          <div className="stage-noise"/>
          <div className="stage-top">
            <span className="eyebrow">FUTURES {market.contract ?? "GC"}</span>
            <span className="source-tag">CFD VIEW</span>
          </div>

          <div className="price-line">
            <span className="currency">$</span>
            <span className="hero-price">{price(current)}</span>
          </div>

          <div className="price-meta">
            <span>Futures <strong>{price(market.futures)}</strong></span>
            <span>Spot <strong>{price(market.spot)}</strong></span>
            <span>Basis <strong>{signed(market.basis)}</strong></span>
            <span>DTE <strong>{market.dte != null ? Number(market.dte).toFixed(2) : "—"}</strong></span>
          </div>

          <div className="ticker-strip">
            <div>
              <span>PRICE PATH</span>
              <strong>{String(priceMemory?.path_direction ?? "UNKNOWN").toUpperCase()}</strong>
            </div>
            <div>
              <span>MEAN DIST.</span>
              <strong>{distanceToMean === null ? "—" : signed(distanceToMean)}</strong>
            </div>
            <div>
              <span>LOCATION</span>
              <strong>{levels.location ?? "UNKNOWN"}</strong>
            </div>
          </div>
          <div className="price-scan"/>
        </article>

        <article className={`regime-stage ${isBear ? "bear" : "bull"}`}>
          <div className="stage-top">
            <span className="eyebrow">MARKET REGIME</span>
            <StatePill value={trade.status ?? regime.status}/>
          </div>
          <div className="regime-word">{regime.bias ?? "WAIT"}</div>
          <div className="regime-state">{regime.marketRegime ?? "UNKNOWN"}</div>
          <p>{regime.overview || regime.what || "ยังไม่มี market narrative ที่ยืนยันได้"}</p>
          <div className="regime-bar"><span/></div>
          <div className="regime-footer">
            <span>HTF <strong>{String(data.technical?.htf ?? "UNKNOWN").toUpperCase()}</strong></span>
            <span>M15 <strong>{data.technical?.m15?.trend ?? "—"}</strong></span>
            <span>M5 <strong>{data.technical?.m5?.trend ?? "—"}</strong></span>
          </div>
        </article>
      </section>

      <section className="flow-story-grid" id="decision">
        <article className="flow-story">
          <div className="flow-story-head">
            <div>
              <span className="eyebrow">THE MARKET STORY</span>
              <h2>ราคาอยู่ตรงไหนใน Flow?</h2>
            </div>
            <span className="route-tag">{trade.preferredSetup ?? "WAIT"}</span>
          </div>

          <div className="story-track">
            <div className="story-node">
              <span>ORIGIN</span>
              <strong>
                {priceMemory?.first_close != null
                  ? `จาก ${price(priceMemory.first_close)}`
                  : "ดูจาก OHLC Memory"}
              </strong>
              <small>{String(priceMemory?.path_direction ?? "UNKNOWN").toUpperCase()} path</small>
            </div>

            <div className="story-arrow">→</div>

            <div className="story-node focus">
              <span>NOW / TEST</span>
              <strong>{levels.location ?? "UNKNOWN"}</strong>
              <small>{regime.overview || "กำลังรอ narrative"}</small>
            </div>

            <div className="story-arrow">→</div>

            <div className="story-node">
              <span>NEXT</span>
              <strong>{trade.preferredSetup ?? "WAIT"}</strong>
              <small>{trade.preferredAction ?? "รอ Action ที่โซนใกล้ราคา"}</small>
            </div>
          </div>
        </article>

        <article className="decision-stage">
          <span className="eyebrow">DECISION LAYER</span>
          <div className="decision-main">
            <span>แผนที่กำลังได้เปรียบ</span>
            <strong>{trade.preferredSetup ?? "WAIT"}</strong>
          </div>
          <p>{trade.preferredAction ?? "ไม่ไล่ราคา • รอ Action + Confirmation"}</p>
          <div className="decision-meter"><span/></div>
          <small>ไม่มี Confirmation / Risk ไม่ผ่าน → NO TRADE</small>
        </article>
      </section>

      <MarketNarrative regime={regime} priceMemory={priceMemory} levels={levels} trade={trade}/>

      <FlowSpine levels={levels} current={current}/>

      <Panel
        eyebrow="EXECUTION"
        title="Trade Plan — 4 ทาง"
        id="plan"
        meta={<StatePill value={trade.status}/>}
        className="trade-panel"
      >
        <div className="plan-callout">
          <div>
            <span className="eyebrow">PREFERRED ROUTE</span>
            <strong>{trade.preferredSetup ?? "WAIT"}</strong>
            <small>{trade.preferredAction ?? "รอให้เกิด Action ที่โซนใกล้ราคา"}</small>
          </div>
          <div className="risk-rule">ZONE ≠ ENTRY</div>
        </div>

        <div className="route-grid">
          <RouteCard
            title="เบรกแนวต้าน"
            subtitle="Break → Hold → Retest"
            tone="buy"
            setup={trade.buyBreakout}
          />
          <RouteCard
            title="เด้งจากแนวรับ"
            subtitle="Support → Reaction → BOS"
            tone="buy"
            setup={trade.buySupport}
          />
          <RouteCard
            title="ต้านไม่ผ่าน"
            subtitle="Retest → Reject → BOS"
            tone="sell"
            setup={trade.sellRejection}
          />
          <RouteCard
            title="หลุดแนวรับ"
            subtitle="Break → Retest Fail"
            tone="sell"
            setup={trade.sellBreakdown}
          />
        </div>

        <div className="no-trade-strip">แตะระดับ ≠ เข้า • ต้อง Action + Confirmation + Risk ผ่าน</div>
      </Panel>

      <section className="evidence-section" id="evidence">
        <div className="section-heading">
          <div>
            <span className="eyebrow">EVIDENCE STACK</span>
            <h2>หลักฐานที่กำลังหนุน / ขัดกับ Flow</h2>
          </div>
          <span className="section-note">Evidence &gt; Story</span>
        </div>
        <EvidenceStack data={data}/>
      </section>

      <section className="split-grid">
        <AuctionPanel auction={data.auction}/>
        <MacroPanel macro={data.macro}/>
      </section>

      <Panel
        eyebrow="DATA / MICROSTRUCTURE"
        title="Flow State"
        meta={<span className="source-tag">{data.flow?.status ?? "UNKNOWN"}</span>}
      >
        <div className="flow-metrics">
          <div><span>Buy Aggression</span><strong>{compact(data.flow?.aggression?.buy)}</strong></div>
          <div><span>Sell Aggression</span><strong>{compact(data.flow?.aggression?.sell)}</strong></div>
          <div><span>Delta</span><strong>{compact(data.flow?.aggression?.delta)}</strong></div>
          <div><span>Book Imbalance</span><strong>{data.flow?.book?.imbalance != null ? Number(data.flow.book.imbalance).toFixed(2) : "—"}</strong></div>
        </div>
        <div className="context-line">
          {data.flow?.availability === "NOT_PROVIDED"
            ? "ยังไม่มี tick/order-book source จึงไม่สรุป aggressor flow เป็นข้อเท็จจริง"
            : "Flow เป็น evidence ประกอบ ไม่ใช่ direction oracle"}
        </div>
      </Panel>

      <GammaTable gamma={data.gamma}/>

      <DataClock clock={data.dataClock}/>

      <footer>
        <span>INTRADAY-OI</span>
        <span>Updated {updated} ICT</span>
        <span>Analysis only · No order execution</span>
      </footer>
    </main>
  );
}
