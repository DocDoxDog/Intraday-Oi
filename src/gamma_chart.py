"""Render the canonical multi-expiration GEX matrix as a Telegram-ready PNG."""

from __future__ import annotations

from io import BytesIO
from typing import Any


def render_gamma_table(gamma_matrix: dict[str, Any], title: str = "Gold Gamma Table") -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    columns = gamma_matrix.get("columns") or []
    rows = gamma_matrix.get("matrix") or []
    if not columns or not rows:
        raise ValueError("GAMMA_MATRIX_EMPTY")

    # Telegram/LINE should be readable without pinch-zooming. Keep the matrix
    # compact and focus on the 31 strikes nearest the current price while the
    # full source rows remain stored in Supabase.
    current_price = gamma_matrix.get("current_price")
    display_rows = rows
    if isinstance(current_price, (int, float)) and len(rows) > 31:
        display_rows = sorted(
            rows,
            key=lambda row: abs(float(row.get("strike", 0)) - float(current_price)),
        )[:31]
        display_rows = sorted(display_rows, key=lambda row: float(row["strike"]), reverse=True)
    else:
        display_rows = sorted(rows, key=lambda row: float(row["strike"]), reverse=True)

    fig_width = max(9.5, 2.1 + 1.10 * len(columns))
    fig_height = max(5.6, 1.6 + 0.24 * min(len(display_rows) + 1, 34))
    fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=150)
    ax.axis("off")

    headers = ["Price ↓"] + [
        (
            f"{str(col.get('expiry_date', ''))[8:10]}/{str(col.get('expiry_date', ''))[5:7]} "
            f"{col.get('weekday_short', '')}\n{col['code']}\nDTE {col['dte']:.2f}"
            if isinstance(col.get("dte"), (int, float))
            else f"{str(col.get('expiry_date', ''))[8:10]}/{str(col.get('expiry_date', ''))[5:7]} "
                 f"{col.get('weekday_short', '')}\n{col['code']}\n{'OBSERVED' if col.get('status') == 'OBSERVED' else 'NO DATA'}"
        )
        for col in columns
    ]

    cell_text = []
    cell_colors = []
    for row in display_rows:
        values = [row["strike"]]
        colors = ["#eeeeee"]
        for col in columns:
            value = row.get(col["code"])
            # Canonical GEX is stored in USD per 1% move; render in $M to match
            # the analyst-facing Gamma Table convention.
            values.append("" if value is None else f"{value / 1_000_000:+.1f}")
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
    total_values = []
    total_colors = ["#d0d7de"]
    for col in columns:
        value = totals_map.get(col["code"])
        total_values.append("" if value is None else f"{value / 1_000_000:+.1f}")
        total_colors.append(
            "#b7e1cd" if isinstance(value, (int, float)) and value > 0
            else "#f4b6b6" if isinstance(value, (int, float)) and value < 0
            else "#d9dee7"
        )
    cell_text.append(["Panel total"] + total_values)
    cell_colors.append(total_colors)

    table = ax.table(
        cellText=cell_text,
        colLabels=headers,
        cellColours=cell_colors,
        cellLoc="center",
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.25)

    for cell in table.get_celld().values():
        cell.set_edgecolor("#333333")
    for col_index in range(len(headers)):
        header = table[(0, col_index)]
        header.set_facecolor("#263238")
        header.get_text().set_color("white")
        header.get_text().set_weight("bold")

    ax.set_title(
        f"{title} — $M per 1% move | Multi-Expiration",
        fontsize=16,
        weight="bold",
        pad=16,
    )

    fig.text(
        0.5,
        0.025,
        "เรียงราคาสูง → ต่ำ | ช่องว่าง = ยังไม่มี source observation | ตัวเลข = $M ต่อการขยับ 1% | แสดง 31 strike ใกล้ราคาปัจจุบัน",
        ha="center",
        fontsize=8,
    )

    fig.tight_layout(rect=(0, 0.05, 1, 0.98))
    out = BytesIO()
    fig.savefig(out, format="png", bbox_inches="tight")
    plt.close(fig)
    return out.getvalue()
