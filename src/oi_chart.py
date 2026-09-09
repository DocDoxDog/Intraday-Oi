"""OI Positioning chart; deliberately does not label OI as traded volume."""
from __future__ import annotations
from io import BytesIO


def render_oi_positioning(rows: list[dict], title: str = "Gold OI Intraday Positioning") -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    data = [r for r in rows if isinstance(r.get("strike"), (int, float))]
    data.sort(key=lambda r: r["strike"])
    strikes = [r["strike"] for r in data]
    put_oi = [r.get("oiPut") or 0 for r in data]
    call_oi = [r.get("oiCall") or 0 for r in data]
    put_change = [r.get("oi_delta_put") if r.get("oi_delta_put") is not None else r.get("oiPutChange") or r.get("oichgvPut") or 0 for r in data]
    call_change = [r.get("oi_delta_call") if r.get("oi_delta_call") is not None else r.get("oiCallChange") or r.get("oichgvCall") or 0 for r in data]

    fig, ax = plt.subplots(figsize=(14, 6), dpi=130)
    width = 0.36
    x = list(range(len(strikes)))
    ax.bar([i - width / 2 for i in x], put_oi, width, color="#f2b544", label="Put OI")
    ax.bar([i + width / 2 for i in x], call_oi, width, color="#4285d4", label="Call OI")
    ax.set_xticks(x)
    ax.set_xticklabels([f"{s:g}" for s in strikes], rotation=60, ha="right", fontsize=8)
    ax.set_ylabel("Open Interest (contracts)")
    ax.set_title(f"{title} — OI Positioning (not traded volume)", loc="left", fontsize=14, weight="bold")
    ax.grid(axis="y", alpha=.25)
    ax.legend(loc="upper left", ncol=2)
    ax.text(.99, 1.02, "ΔOI: change vs EOD | Churn: |ΔPut|+|ΔCall|", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=9, color="#555")

    # Show ΔOI only when the source actually supplies numeric changes.
    if any(put_change) or any(call_change):
        ax2 = ax.twinx()
        ax2.plot(x, put_change, color="#d99000", linestyle="--", linewidth=1.2, alpha=.8, label="Put ΔOI")
        ax2.plot(x, call_change, color="#1d5fae", linestyle="--", linewidth=1.2, alpha=.8, label="Call ΔOI")
        ax2.set_ylabel("ΔOI vs EOD")
        ax2.axhline(0, color="#777", linewidth=.7)

    fig.tight_layout()
    out = BytesIO()
    fig.savefig(out, format="png", bbox_inches="tight")
    plt.close(fig)
    return out.getvalue()
