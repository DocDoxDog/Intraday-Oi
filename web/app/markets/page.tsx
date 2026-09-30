import { TerminalLayout, EmptyTerminalState } from "../components/TerminalLayout";
import { getTerminalMarket } from "../lib/terminal";

export const dynamic = "force-dynamic";

export default async function MarketsPage() {
  const payload = await getTerminalMarket("GC");
  return (
    <TerminalLayout title="Markets">
      {!payload ? <EmptyTerminalState /> : (
        <section className="metrics-grid">
          <div className="metric"><div className="metric-label">REFERENCE</div><div className="metric-value">GC</div><div className="metric-note">Canonical reference market</div></div>
          <div className="metric"><div className="metric-label">PRICE</div><div className="metric-value">{payload.data.market_state.price ?? "—"}</div></div>
          <div className="metric"><div className="metric-label">DATA STATUS</div><div className="metric-value">{payload.data.market_state.data_status}</div></div>
          <div className="metric"><div className="metric-label">DATA AGE</div><div className="metric-value">{payload.data.market_state.data_age_seconds ?? "—"}s</div></div>
        </section>
      )}
    </TerminalLayout>
  );
}
