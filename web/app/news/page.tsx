import { TerminalLayout, EmptyTerminalState } from "../components/TerminalLayout";
import { getTerminalNews } from "../lib/terminal"; 

export const dynamic = "force-dynamic";

export default async function NewsPage() {
  const payload = await getTerminalNews("GC");
  return (
    <TerminalLayout title="News">
      {!payload ? <EmptyTerminalState /> : (
        <section className="panel">
          <div className="eyebrow">WHAT'S IMPORTANT NOW</div>
          <h2>Verified stories</h2>
          <pre className="code-panel">{JSON.stringify(payload.data, null, 2)}</pre>
        </section>
      )}
    </TerminalLayout>
  );
}
