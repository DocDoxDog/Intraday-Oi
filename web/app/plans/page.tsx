import { TerminalLayout, EmptyTerminalState } from "../components/TerminalLayout";
import { getTerminalPlan } from "../lib/terminal";

export const dynamic = "force-dynamic";

export default async function PlansPage() {
  const payload = await getTerminalPlan("GC");
  return (
    <TerminalLayout title="Plans">
      {!payload ? <EmptyTerminalState /> : (
        <section className="panel">
          <div className="eyebrow">SCENARIO ENGINE</div>
          <h2>Conditional scenarios</h2>
          <pre className="code-panel">{JSON.stringify(payload.data, null, 2)}</pre>
        </section>
      )}
    </TerminalLayout>
  );
}
