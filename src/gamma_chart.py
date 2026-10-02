"""Render compact and full multi-expiration GEX tables."""

from __future__ import annotations

from io import BytesIO
from typing import Any


def _observed_columns(gamma_matrix: dict[str, Any]) -> list[dict[str, Any]]:
    columns = [
        c for c in (gamma_matrix.get("columns") or [])
        if c.get("status") == "OBSERVED"
    ]
    return columns or list(gamma_matrix.get("columns") or [])


def _render(gamma_matrix: dict[str, Any], *, full: bool) -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    all_columns = _observed_columns(gamma_matrix)
    display_columns = gamma_matrix.get("display_columns") or all_columns[:7]
    columns = all_columns if full else list(display_columns)
    rows = list(gamma_matrix.get("matrix") or [])
    if not columns or not rows:
        raise ValueError("GAMMA_MATRIX_EMPTY")

    current_price = gamma_matrix.get("current_price")
    if (
        not full
        and isinstance(current_price, (int, float))
        and len(rows) > 31
    ):
        rows = sorted(
            rows,
            key=lambda row: abs(
                float(row.get("strike", 0)) - float(current_price)
            ),
        )[:25]

    rows = sorted(rows, key=lambda row: float(row["strike"]), reverse=True)

    ncols = len(columns)
    fig_width = max(12.5, 2.0 + 1.65 * ncols)
    row_count = len(rows) + 1
    fig_height = max(
        7.0 if not full else 8.0,
        1.7 + (0.28 if not full else 0.19) * min(row_count, 145),
    )

    fig, ax = plt.subplots(
        figsize=(fig_width, fig_height),
        dpi=160,
        facecolor="white",
    )
    ax.axis("off")

    headers = ["PRICE"] + [
        (
            f"{col.get('code', 'UNKNOWN')}\n"
            f"DTE {float(col['dte']):.2f}"
            if isinstance(col.get("dte"), (int, float))
            else f"{col.get('code', 'UNKNOWN')}\nDTE —"
        )
        for col in columns
    ]

    cell_text: list[list[str]] = []
    cell_colors: list[list[str]] = []

    for row in rows:
        values = [f"{float(row['strike']):.2f}"]
        colors = ["#eeeeee"]
        for col in columns:
            value = row.get(col["code"])
            values.append(
                "" if value is None else f"{float(value) / 1_000_000:+.2f}"
            )
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

    totals_map = gamma_matrix.get("totals") or {}
    total_values = ["TOTAL"]
    total_colors = ["#d0d7de"]

    for col in columns:
        value = totals_map.get(col["code"])
        total_values.append(
            "" if value is None else f"{float(value) / 1_000_000:+.2f}"
        )
        total_colors.append(
            "#b7e1cd"
            if isinstance(value, (int, float)) and value > 0
            else "#f4b6b6"
            if isinstance(value, (int, float)) and value < 0
            else "#d9dee7"
        )

    cell_text.append(total_values)
    cell_colors.append(total_colors)

    table = ax.table(
        cellText=cell_text,
        colLabels=headers,
        cellColours=cell_colors,
        cellLoc="center",
        bbox=[0.01, 0.035 if not full else 0.025, 0.98, 0.90 if not full else 0.94],
        colWidths=[0.12] + [0.88 / ncols] * ncols,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.5 if full else 9.5)
    table.scale(1, 1.10 if full else 1.12)

    for (row_index, _col_index), cell in table.get_celld().items():
        cell.set_edgecolor("#333333")
        if row_index == 0:
            cell.set_height(0.145 if full else 0.225)
            cell.get_text().set_weight("bold")
            cell.get_text().set_color("white")
            cell.get_text().set_fontsize(10.5 if full else 15)
            cell.set_facecolor("#263238")

    title = (
        "GOLD GAMMA TABLE — FULL DATA"
        if full
        else "GOLD GAMMA TABLE — Multi-Expiration"
    )
    subtitle = (
        f"All available observed strikes and series ({len(all_columns)}) • $M per 1% move • blank = no source observation"
        if full
        else "25 strikes around current Futures price • DTE shown in header • $M per 1% move"
    )

    fig.suptitle(
        title,
        fontsize=17 if not full else 15,
        weight="bold",
        y=0.985,
    )
    fig.text(0.5, 0.015, subtitle, ha="center", fontsize=8)

    fig.tight_layout(
        rect=(0.015, 0.025, 0.985, 0.955 if full else 0.96)
    )

    out = BytesIO()
    fig.savefig(
        out,
        format="png",
        bbox_inches="tight",
        facecolor="white",
    )
    plt.close(fig)
    return out.getvalue()


def render_gamma_table(
    gamma_matrix: dict[str, Any],
    title: str = "Gold Gamma Table",
) -> bytes:
    """Compact table for the primary user-facing Gamma image."""
    return _render(gamma_matrix, full=False)


def render_gamma_table_full(gamma_matrix: dict[str, Any]) -> bytes:
    """Full available observed matrix, every stored strike."""
    return _render(gamma_matrix, full=True)
