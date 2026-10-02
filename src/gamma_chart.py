"""Render the canonical multi-expiration GEX matrix as a Telegram-ready PNG."""

from __future__ import annotations

from io import BytesIO
from typing import Any


"""Render compact and full multi-expiration GEX tables."""
from __future__ import annotations
from io import BytesIO
from typing import Any


def _observed_columns(gamma_matrix: dict[str, Any]) -> list[dict[str, Any]]:
    columns = [c for c in (gamma_matrix.get("columns") or []) if c.get("status") == "OBSERVED"]
    return columns or list(gamma_matrix.get("columns") or [])


def _render(gamma_matrix: dict[str, Any], *, full: bool) -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    columns = _observed_columns(gamma_matrix)
    rows = list(gamma_matrix.get("matrix") or [])
    if not columns or not rows:
        raise ValueError("GAMMA_MATRIX_EMPTY")

    current_price = gamma_matrix.get("current_price")
    if not full and isinstance(current_price, (int, float)) and len(rows) > 31:
        rows = sorted(
            rows,
            key=lambda row: abs(float(row.get("strike", 0)) - float(current_price)),
        )[:31]

    rows = sorted(rows, key=lambda row: float(row["strike"]), reverse=True)

    ncols = len(columns)
    fig_width = max(12.5, 2.0 + 1.65 * ncols)
    row_count = len(rows) + 1
    fig_height = max(7.0 if not full else 9.0, 2.0 + 0.255 * min(row_count, 145))
    fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=160)
    ax.axis("off")

    headers = ["PRICE"] + [
        f"{col.get('code','UNKNOWN')}\nDTE {col.get('dte'):.2f}"
        if isinstance(col.get("dte"), (int, float))
        else f"{col.get('code','UNKNOWN')}\nDTE —"
        for col in columns
    ]

    cell_text: list[list[str]] = []
    cell_colors: list[list[str]] = []
    for row in rows:
        values = [f"{float(row['strike']):.2f}"]
        colors = ["#eeeeee"]
        for col in columns:
            value = row.get(col["code"])
            values.append("" if value is None else f"{float(value) / 1_000_000:+.2f}")
            if value is None:
                colors.append("#ffffff")
            elif value > 0:
                colors.append("#b7e1cd")
            elif value < 0:
                colors.append("#f4b6b6")
            else:
                colors.append("#d9dee7")
        cell_text.append(values)
        cell_colors.append(colors)

    totals_map = gamma_matrix.get("totals", {})
    total_values = ["TOTAL"]
    total_colors = ["#d0d7de"]
    for col in columns:
        value = totals_map.get(col["code"])
        total_values.append("" if value is None else f"{float(value) / 1_000_000:+.2f}")
        total_colors.append(
            "#b7e1cd" if isinstance(value, (int, float)) and value > 0
            else "#f4b6b6" if isinstance(value, (int, float)) and value < 0
            else "#d9dee7"
        )
    cell_text.append(total_values)
    cell_colors.append(total_colors)

    table = ax.table(
        cellText=cell_text,
        colLabels=headers,
        cellColours=cell_colors,
        cellLoc="center",
        loc="center",
        colWidths=[0.12] + [0.88 / ncols] * ncols,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.5 if full else 9)
    table.scale(1, 1.18)

    for (row_index, col_index), cell in table.get_celld().items():
        cell.set_edgecolor("#333333")
        if row_index == 0:
            cell.set_height(0.055 if full else 0.085)
            cell.get_text().set_weight("bold")
            cell.get_text().set_color("white")
            cell.get_text().set_fontsize(11 if full else 13)
            cell.set_facecolor("#263238")

    title = (
        "GOLD GAMMA TABLE — FULL DATA"
        if full
        else "GOLD GAMMA TABLE — Multi-Expiration"
    )
    subtitle = (
        "All available observed strikes • $M per 1% move • blank = no source observation"
        if full
        else "31 strikes around current Futures price • $M per 1% move"
    )
    fig.suptitle(title, fontsize=17 if not full else 15, weight="bold", y=0.99)
    fig.text(0.5, 0.015, subtitle, ha="center", fontsize=8)

    fig.tight_layout(rect=(0.015, 0.035, 0.985, 0.96 if full else 0.965))
    out = BytesIO()
    fig.savefig(out, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out.getvalue()


def render_gamma_table(gamma_matrix: dict[str, Any], title: str = "Gold Gamma Table") -> bytes:
    """Compact table for Telegram/LINE message 1."""
    return _render(gamma_matrix, full=False)


def render_gamma_table_full(gamma_matrix: dict[str, Any]) -> bytes:
    """Full available observed matrix for the detail message."""
    return _render(gamma_matrix, full=True)
