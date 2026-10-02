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

    fig_width = max(12, 2.0 + 1.45 * len(columns))
    fig_height = max(6, 2.0 + 0.30 * min(len(rows), 45))
    fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=150)
    ax.axis("off")

    headers = ["Strike"] + [
        f"DTE {col['dte']:.2f}\n{col['code']}" if isinstance(col.get("dte"), (int, float))
        else str(col["code"])
        for col in columns
    ]

    cell_text = []
    cell_colors = []
    for row in rows:
        values = [row["strike"]]
        colors = ["#eeeeee"]
        for col in columns:
            value = row.get(col["code"])
            values.append("" if value is None else f"{value:+.1f}")
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

    totals = ["Panel total"] + [
        f"{gamma_matrix.get('totals', {}).get(col['code'], 0):+.1f}"
        for col in columns
    ]
    cell_text.append(totals)
    cell_colors.append(["#d0d7de"] + [
        "#b7e1cd" if gamma_matrix.get("totals", {}).get(col["code"], 0) > 0
        else "#f4b6b6" if gamma_matrix.get("totals", {}).get(col["code"], 0) < 0
        else "#d9dee7"
        for col in columns
    ])

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
        f"{title} — $10 Strike Detail | Multi-Expiration",
        fontsize=16,
        weight="bold",
        pad=16,
    )

    fig.text(
        0.5,
        0.025,
        "Blank = no matching source observation | values are deterministic source-derived GEX",
        ha="center",
        fontsize=8,
    )

    fig.tight_layout(rect=(0, 0.05, 1, 0.98))
    out = BytesIO()
    fig.savefig(out, format="png", bbox_inches="tight")
    plt.close(fig)
    return out.getvalue()
