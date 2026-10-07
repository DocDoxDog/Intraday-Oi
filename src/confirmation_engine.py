"""Setup-specific deterministic confirmation."""
from __future__ import annotations
from typing import Any

def _trend(s,tf): return str(((s.get("technical") or {}).get(tf) or {}).get("trend") or "").lower()
def _bos(s,tf): return str(((s.get("technical") or {}).get(tf) or {}).get("bos") or "").lower()

def confirm_setup(setup:dict[str,Any], market_state:dict[str,Any])->dict[str,Any]:
    side=str(setup.get("side") or "").upper()
    kind=str(setup.get("setup_type") or "").upper()
    regime=str((market_state.get("regime") or {}).get("regime") or "UNKNOWN").upper()
    m15,m5=_trend(market_state,"m15"),_trend(market_state,"m5")
    bos=_bos(market_state,"m5")
    long_bos=bos in {"bullish","bull","up","bos_up","bullish_bos","break_up"}
    short_bos=bos in {"bearish","bear","down","bos_down","bearish_bos","break_down"}
    checks=[]
    checks.append({"name":"zone_event","pass":setup.get("state") in {"TRIGGERED","CONFIRMED"}})
    if side=="LONG":
        checks += [{"name":"m15_alignment","pass":m15=="bullish"},
                   {"name":"m5_alignment","pass":m5=="bullish"},
                   {"name":"m5_structure_shift","pass":long_bos}]
    else:
        checks += [{"name":"m15_alignment","pass":m15=="bearish"},
                   {"name":"m5_alignment","pass":m5=="bearish"},
                   {"name":"m5_structure_shift","pass":short_bos}]
    if kind=="REVERSAL":
        checks[0]["name"]="rejection_or_absorption_event"
    if kind=="BREAKOUT_RETEST":
        checks[0]["name"]="breakout_acceptance_retest_event"
    if kind=="PULLBACK":
        checks[0]["name"]="pullback_reaction_event"
    regime_allowed = not (regime=="EVENT")
    checks.append({"name":"regime_gate","pass":regime_allowed})
    passed=all(bool(x.get("pass")) for x in checks)
    state="CONFIRMED" if passed else "TRIGGERED_WAIT_CONFIRMATION" if setup.get("state")=="TRIGGERED" else setup.get("state","WAIT")
    return {"state":state,"confirmed":passed,"checks":checks,
            "reason":"All required deterministic checks passed." if passed else "One or more required confirmation checks are not satisfied."}
