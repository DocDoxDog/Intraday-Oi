import { TerminalLayout, EmptyTerminalState } from "../components/TerminalLayout";
import { getTerminalAnalysis } from "../lib/terminal";

export const dynamic = "force-dynamic";

export default async function AnalysisPage() {
  const payload = await getTerminalAnalysis("GC");
  return (
    <TerminalLayout title="Analysis">
      {!payload ? <EmptyTerminalState /> : (
        <section className="panel">
          <div className="eyebrow">EVIDENCE-FIRST</div>
          <h2>Market analysis</h2>
          <pre className="code-panel">{JSON.stringify(payload.data, null, 2)}</pre>
        </section>
      )}
    </TerminalLayout>
  );
}
