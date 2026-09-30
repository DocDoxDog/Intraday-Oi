import { TerminalLayout, EmptyTerminalState } from "../components/TerminalLayout";
import { getTerminalExpiry } from "../lib/terminal";

export const dynamic = "force-dynamic";

export default async function OptionsPage() {
  const payload = await getTerminalExpiry("GC");
  return (
    <TerminalLayout title="Options" eyebrow="EXPIRATION MATRIX">
      {!payload ? <EmptyTerminalState /> : (
        <section className="panel">
          <div className="eyebrow">EXPIRY</div>
          <h2>Canonical expiry contributions</h2>
          <pre className="code-panel">{JSON.stringify(payload.data, null, 2)}</pre>
        </section>
      )}
    </TerminalLayout>
  );
}
