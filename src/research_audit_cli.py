"""CLI adapter that turns a trade/evidence JSON file into an auditable report.

Input JSON:
{
  "strategy_id": "gamma_break_acceptance",
  "strategy_version": "v1",
  "oos_months": 4,
  "trades_r": [0.4, -1.0, 0.7, ...],
  "max_drawdown_r": -2.3,
  "cost_degradation_r": 0.08,
  "pit_rows": [{"event_time": "...", "as_of": "..."}],
  "strategy_trials": [[...], [...], ...]
}

The command never promotes live trading; it only reports the evidence stage.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.evidence_audit import cscv_pbo, evaluate_promotion
from src.point_in_time import validate_dataset


def build_report(payload: dict[str, Any]) -> dict[str, Any]:
    returns = payload.get("trades_r") or []
    trials = payload.get("strategy_trials") or []
    pbo_result = cscv_pbo(trials) if trials else {"pbo": None, "splits": 0}

    pit_rows = payload.get("pit_rows") or []
    pit = validate_dataset(pit_rows) if pit_rows else {
        "rows": 0,
        "failed_rows": 0,
        "failure_rate": None,
        "status": "DATA_INSUFFICIENT",
    }

    result = evaluate_promotion(
        oos_returns_r=returns,
        oos_months=int(payload.get("oos_months") or 0),
        pbo=pbo_result.get("pbo"),
        max_drawdown_r=payload.get("max_drawdown_r"),
        cost_degradation_r=payload.get("cost_degradation_r"),
        live_trades=int(payload.get("live_trades") or 0),
        live_days=int(payload.get("live_days") or 0),
        live_mode=bool(payload.get("live_mode")),
    )
    result["strategy_id"] = payload.get("strategy_id")
    result["strategy_version"] = payload.get("strategy_version")
    result["pit"] = pit
    result["pbo_detail"] = pbo_result
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit an Intraday-Oi research result.")
    parser.add_argument("input", type=Path, help="JSON evidence input")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    report = build_report(payload)
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(encoded)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
