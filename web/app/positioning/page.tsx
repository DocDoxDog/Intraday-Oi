import { TerminalLayout, EmptyTerminalState } from "../components/TerminalLayout";
import { getTerminalPositioning } from "../lib/terminal";

export const dynamic = "force-dynamic";

export default async function PositioningPage() {
  const payload = await getTerminalPositioning("GC");
  return (
    <TerminalLayout title="Positioning" eyebrow="OI · GEX · DEX">
      {!payload ? <EmptyTerminalState /> : (
        <section className="panel">
          <div className="eyebrow">CANONICAL POSITIONING</div>
          <h2>GC</h2>
          <pre className="code-panel">{JSON.stringify(payload.data, null, 2)}</pre>
        </section>
      )}
    </TerminalLayout>
  );
}
