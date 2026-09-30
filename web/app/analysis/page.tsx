import { TerminalLayout, EmptyTerminalState } from "../components/TerminalLayout";
import { getInternal } from "../lib/terminal";

export const dynamic = "force-dynamic";

export default async function AnalysisPage() {
  const payload = await getInternal<unknown>("/api/v1/analysis/GC");
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
