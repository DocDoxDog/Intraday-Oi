import Link from "next/link";
import type { ReactNode } from "react";

export const terminalNav = [
  ["Overview", "/overview"],
  ["Markets", "/markets"],
  ["Positioning", "/positioning"],
  ["Options", "/options"],
  ["News", "/news"],
  ["Analysis", "/analysis"],
  ["Plans", "/plans"],
  ["Research", "/research"],
  ["Backtest", "/backtest"],
  ["Alerts", "/alerts"],
  ["System", "/system"],
];

export function TerminalLayout({ title, eyebrow = "MARKET TERMINAL", children }: { title: string; eyebrow?: string; children: ReactNode }) {
  return (
    <main className="terminal">
      <aside className="sidebar">
        <div className="brand">
          <div className="eyebrow">MARKET TERMINAL</div>
          <div className="brand-title">OI POSITIONING</div>
          <div className="brand-subtitle">INTELLIGENCE</div>
        </div>
        <nav>
          {terminalNav.map(([label, href], index) => (
            <Link className="nav-item" href={href} key={href}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              {label}
            </Link>
          ))}
        </nav>
      </aside>
      <section className="canvas">
        <header className="topbar">
          <div>
            <div className="eyebrow">{eyebrow}</div>
            <h1>{title}</h1>
          </div>
          <div className="status-cluster">
            <span className={process.env.WEB_TERMINAL_ENABLED === "true" ? "status" : "status unknown"}>
              {process.env.WEB_TERMINAL_ENABLED === "true" ? "SERVER READ" : "TERMINAL LOCKED"}
            </span>
          </div>
        </header>
        {children}
      </section>
    </main>
  );
}

export function EmptyTerminalState({ title = "Data unavailable", detail = "Enable the server-side terminal only after customer authentication and data licensing gates are complete." }) {
  return (
    <section className="empty-state">
      <div className="empty-title">{title}</div>
      <p>{detail}</p>
    </section>
  );
}
