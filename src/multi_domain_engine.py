"""Deterministic multi-domain market intelligence and trade-plan ranking."""
from __future__ import annotations
from math import sqrt
from statistics import mean, pstdev
from typing import Any

def _n(v: Any):
    try:
        return None if v is None or v == "" or isinstance(v, bool) else float(v)
    except (TypeError, ValueError):
        return None

def _ohlcv(parsed, tf):
    return list((((parsed.get("technical_context") or {}).get("ohlcv") or {}).get(tf)) or [])

def _z(xs, x):
    if x is None or len(xs) < 20: return None
    s=pstdev(xs)
    return round((x-mean(xs))/s,4) if s else None

def build_quant_evidence(parsed):
    out={"status":"UNKNOWN","timeframes":{}}
    for tf in ("m5","m15","m30","h1","h4","d1"):
        bars=_ohlcv(parsed,tf); closes=[_n(x.get("close")) for x in bars]; closes=[x for x in closes if x is not None]
        if len(closes)<20: continue
        rs=[closes[i]/closes[i-1]-1 for i in range(1,len(closes)) if closes[i-1]]
        trs=[]
        for i in range(max(1,len(bars)-100),len(bars)):
            c,p=bars[i],bars[i-1]
            trs.append(max(c["high"]-c["low"],abs(c["high"]-p["close"]),abs(c["low"]-p["close"])))
        atr=mean(trs[-14:]) if len(trs)>=14 else None
        out["timeframes"][tf]={
            "return_20": round(closes[-1]/closes[-21]-1,6) if len(closes)>=21 else None,
            "return_zscore": _z(rs[-100:],rs[-1] if rs else None),
            "realized_vol_proxy": round(sqrt(mean([x*x for x in rs[-20:]]))*sqrt(252),6) if len(rs)>=20 else None,
            "atr14": round(atr,5) if atr is not None else None,
            "atr_percentile": round(sum(x<=atr for x in trs[-100:])/min(100,len(trs))*100,2) if atr is not None else None,
        }
    out["status"]="AVAILABLE" if out["timeframes"] else "UNKNOWN"
    return out

def _macro(parsed,state):
    source=state.get("macro") or (parsed.get("raw_series") or {}).get("macro_state") or {}
    items=parsed.get("news_context") or []
    high=[x for x in items if isinstance(x,dict) and str(x.get("relevance") or "").upper()=="HIGH"]
    channels=[]
    for x in high:
        for c in x.get("market_channels") or []:
            if c not in channels: channels.append(str(c))
    label=str(source.get("bias") or source.get("gold_bias") or source.get("status") or "").upper()
    regime="GOLD_SUPPORTIVE" if "SUPPORT" in label else "GOLD_HEADWIND" if ("HEADWIND" in label or "BEAR" in label) else (label or "UNKNOWN")
    return {"regime":regime,"high_relevance_events":len(high),"channels":channels,
            "transmission":"rates/real-yield/USD/liquidity matter only when observed price response agrees"}

def _micro(state):
    t=state.get("technical") or {}; events=[]
    for tf in ("d1","h4","h1","m30","m15","m5"):
        x=t.get(tf) or {}
        for k in ("bos","choch","sweep"):
            v=str(x.get(k) or "none")
            if v!="none": events.append(f"{tf}:{k}={v}")
    return {"events":events,"liquidity_events":[x for x in events if ":sweep=" in x],
            "structure_events":[x for x in events if ":bos=" in x or ":choch=" in x],
            "interpretation":"level and event are kept separate; no tick-level aggressor claim without trade/book data"}

def _psych(state):
    f=state.get("flow") or {}; g=state.get("gamma") or {}; t=state.get("technical") or {}; m=[]
    if any(str((t.get(x) or {}).get("sweep") or "none")!="none" for x in ("m5","m15","h1")): m.append("liquidity_sweep")
    if _n(g.get("net_gex")) is not None and _n(g.get("net_gex"))<0: m.append("hedging_can_amplify_breaks")
    if f.get("oi_change_put") is not None or f.get("oi_change_call") is not None: m.append("positioning_activity_without_aggressor_side")
    return {"mechanisms":m,"interpretation":"behavior is inferred from observable liquidity/positioning mechanisms, not emotion"}

def _pattern_families(state, side):
    t=state.get("technical") or {}; m5=t.get("m5") or {}; m15=t.get("m15") or {}
    fam=[]
    sweep=str(m5.get("sweep") or "none")
    choch=str(m5.get("choch") or "none")
    bos=str(m5.get("bos") or "none")
    if (side.startswith("LONG") and "sell_side" in sweep) or (side.startswith("SHORT") and "buy_side" in sweep):
        fam += ["ICT","SMC","WYCKOFF","CRT"]
    if (side.startswith("LONG") and "bullish" in choch) or (side.startswith("SHORT") and "bearish" in choch):
        fam += ["SMC","CISD"]
    if (side.startswith("LONG") and "bullish" in bos) or (side.startswith("SHORT") and "bearish" in bos):
        fam += ["ICT","SMC","CISD","TTRADES"]
    if m5.get("fvg") or m15.get("fvg"): fam.append("ICT")
    div=m5.get("divergence") or {}
    if div.get("status")=="DETECTED": fam.append("TTRADES")
    # Conservative Elliott candidate: enough alternating swing information is
    # required; the label is never treated as a completed wave count.
    if m5.get("prior_high") is not None and m5.get("prior_low") is not None:
        fam.append("ELLIOTT_CANDIDATE")
    # MSNR is a level-reaction framework; route levels themselves are source-derived.
    fam.append("MSNR")
    return list(dict.fromkeys(fam))

def _name(route,state):
    t=state.get("technical") or {}; m5=t.get("m5") or {}; m15=t.get("m15") or {}
    r=str(route.get("route") or ""); side=str(route.get("side") or "").upper()
    fam=_pattern_families(state,side); features=[]
    if m5.get("sweep") not in (None,"none"): features.append("LIQUIDITY_SWEEP")
    if m5.get("choch") not in (None,"none"): features.append("CHoCH")
    if m5.get("bos") not in (None,"none"): features.append("BOS")
    if m5.get("fvg") or m15.get("fvg"): features.append("FVG")
    if (m5.get("divergence") or {}).get("status")=="DETECTED": features.append("DIVERGENCE")
    if r == "BUY_BREAKOUT": n="ICT/SMC Breakout-Reclaim"
    elif r == "BUY_SUPPORT": n="ICT Liquidity-Sweep Reversal" if "LIQUIDITY_SWEEP" in features else "SMC Support Reversal"
    elif r == "SELL_REJECTION": n="ICT/SMC Rejection at Liquidity"
    elif r == "SELL_BREAKDOWN": n="CRT/SMC Breakdown-Retest"
    elif r == "RANGE_MEAN_REVERSION_LONG": n="MSNR/Gamma-Band Mean Reversion Long"
    elif r == "RANGE_MEAN_REVERSION_SHORT": n="MSNR/Gamma-Band Mean Reversion Short"
    else: n="Deterministic Structural Setup"
    return n,features,fam

def _risk_ratio(side, entry, stop, tp):
    if None in (entry, stop, tp):
        return None
    risk = entry - stop if side == "LONG" else stop - entry
    reward = tp - entry if side == "LONG" else entry - tp
    if risk <= 0 or reward <= 0:
        return None
    return reward / risk


def _technical_setup_candidates(state, parsed):
    """Build additional strategy candidates from observed OHLC geometry only.

    These are independent setup hypotheses, not renamed execution routes.
    Every level must come from a stored candle, FVG boundary, or Fibonacci
    swing derived from stored OHLC. Invalid geometry is discarded.
    """
    technical = state.get("technical") or {}
    current = _n((state.get("price") or {}).get("cfd"))
    if current is None:
        return []

    out = []

    def add(route, strategy, side, entry, stop, target, evidence, families):
        e, s, t = _n(entry), _n(stop), _n(target)
        if None in (e, s, t):
            return
        if side == "LONG" and not (s < e < t):
            return
        if side == "SHORT" and not (s > e > t):
            return
        rr = _risk_ratio(side, e, s, t)
        if rr is None or rr < 1.0:
            return
        out.append({
            "route": route,
            "strategy": strategy,
            "side": side,
            "entry": e,
            "stop": s,
            "targets": [t],
            "score": 0.0,
            "evidence": list(evidence),
            "features": [],
            "strategy_families": list(families),
            "geometry_source": "OHLC_DERIVED",
            "_rr": rr,
        })

    for tf in ("m5", "m15", "m30", "h1"):
        x = technical.get(tf) or {}
        bars = _ohlcv(parsed, tf)
        if not bars:
            bars = list((state.get("ohlcv") or {}).get(tf) or [])
        if not bars:
            continue
        last = bars[-1]
        last_high, last_low = _n(last.get("high")), _n(last.get("low"))
        lookback = bars[-21:-1] if len(bars) > 21 else bars[:-1]
        prior_high = max((_n(b.get("high")) for b in lookback), default=last_high)
        prior_low = min((_n(b.get("low")) for b in lookback), default=last_low)
        swing_high = max((_n(b.get("high")) for b in bars[-50:]), default=last_high)
        swing_low = min((_n(b.get("low")) for b in bars[-50:]), default=last_low)

        sweep = str(x.get("sweep") or "none")
        if "sell_side_sweep" in sweep:
            add(
                f"LIQUIDITY_SWEEP_LONG_{tf.upper()}",
                f"ICT/SMC Liquidity Sweep Reversal ({tf.upper()})",
                "LONG", current, last_low, prior_high,
                [f"{tf.upper()} sell-side sweep", "prior swing low/high"],
                ["ICT", "SMC", "WYCKOFF", "CRT"],
            )
        elif "buy_side_sweep" in sweep:
            add(
                f"LIQUIDITY_SWEEP_SHORT_{tf.upper()}",
                f"ICT/SMC Liquidity Sweep Reversal ({tf.upper()})",
                "SHORT", current, last_high, prior_low,
                [f"{tf.upper()} buy-side sweep", "prior swing high/low"],
                ["ICT", "SMC", "WYCKOFF", "CRT"],
            )

        fvg = x.get("fvg") or {}
        fvg_side = str(fvg.get("side") or "").lower()
        fvg_low, fvg_high = _n(fvg.get("low")), _n(fvg.get("high"))
        if fvg_side == "bullish":
            add(
                f"FVG_RECLAIM_LONG_{tf.upper()}",
                f"ICT FVG Rebalance ({tf.upper()})",
                "LONG", fvg_high, prior_low, prior_high,
                [f"{tf.upper()} bullish FVG", "OHLC prior range"],
                ["ICT", "SMC"],
            )
        elif fvg_side == "bearish":
            add(
                f"FVG_RECLAIM_SHORT_{tf.upper()}",
                f"ICT FVG Rebalance ({tf.upper()})",
                "SHORT", fvg_low, prior_high, prior_low,
                [f"{tf.upper()} bearish FVG", "OHLC prior range"],
                ["ICT", "SMC"],
            )

        fib = x.get("fibonacci") or {}
        hi, lo = _n(fib.get("swing_high")), _n(fib.get("swing_low"))
        r62_bull = _n(fib.get("retracement_62_bullish", fib.get("retracement_62")))
        r79_bull = _n(fib.get("retracement_79_bullish", fib.get("retracement_79")))
        r62_bear = _n(fib.get("retracement_62_bearish"))
        r79_bear = _n(fib.get("retracement_79_bearish"))
        trend = str(x.get("trend") or "").lower()
        if trend == "bullish":
            add(
                f"FIB_OTE_LONG_{tf.upper()}",
                f"MSNR/ICT Fibonacci Reclaim ({tf.upper()})",
                "LONG", r79_bull or r62_bull, lo, hi,
                [f"{tf.upper()} Fibonacci OTE", "swing high/low"],
                ["ICT", "MSNR", "TTRADES"],
            )
        elif trend == "bearish":
            add(
                f"FIB_OTE_SHORT_{tf.upper()}",
                f"MSNR/ICT Fibonacci Rejection ({tf.upper()})",
                "SHORT", r79_bear or r62_bear, hi, lo,
                [f"{tf.upper()} Fibonacci OTE", "swing high/low"],
                ["ICT", "MSNR", "TTRADES"],
            )

        # BOS/CHoCH candidates are derived from confirmed OHLC swing geometry,
        # not from an LLM label. They provide genuinely different plans when
        # the four option-structure routes collapse to only one or two valid
        # execution geometries.
        bos = str(x.get("bos") or "none").lower()
        choch = str(x.get("choch") or "none").lower()
        if "bullish_bos" in bos and current >= prior_high:
            add(
                f"BOS_CONTINUATION_LONG_{tf.upper()}",
                f"SMC/ICT BOS Continuation ({tf.upper()})",
                "LONG", prior_high, last_low, swing_high,
                [f"{tf.upper()} bullish BOS", "prior swing high", "swing high"],
                ["SMC", "ICT", "CISD", "TTRADES"],
            )
        elif "bearish_bos" in bos and current <= prior_low:
            add(
                f"BOS_CONTINUATION_SHORT_{tf.upper()}",
                f"SMC/ICT BOS Continuation ({tf.upper()})",
                "SHORT", prior_low, last_high, swing_low,
                [f"{tf.upper()} bearish BOS", "prior swing low", "swing low"],
                ["SMC", "ICT", "CISD", "TTRADES"],
            )

        if "bullish_choch" in choch:
            add(
                f"CHOCH_REVERSAL_LONG_{tf.upper()}",
                f"SMC CHoCH Reversal ({tf.upper()})",
                "LONG", current, last_low, prior_high,
                [f"{tf.upper()} bullish CHoCH", "liquidity shift", "prior swing"],
                ["SMC", "CISD", "ICT"],
            )
        elif "bearish_choch" in choch:
            add(
                f"CHOCH_REVERSAL_SHORT_{tf.upper()}",
                f"SMC CHoCH Reversal ({tf.upper()})",
                "SHORT", current, last_high, prior_low,
                [f"{tf.upper()} bearish CHoCH", "liquidity shift", "prior swing"],
                ["SMC", "CISD", "ICT"],
            )

        # CRT reference-candle expansion: only emit when price has actually
        # expanded through the completed candle range. The candle itself is
        # the source of entry/invalidation; no synthetic ATR target is used.
        if last_high is not None and last_low is not None:
            if current > last_high and prior_high > current:
                add(
                    f"CRT_EXPANSION_LONG_{tf.upper()}",
                    f"CRT Range Expansion ({tf.upper()})",
                    "LONG", last_high, last_low, prior_high,
                    [f"{tf.upper()} reference-candle high", "range expansion", "prior high"],
                    ["CRT", "TTRADES"],
                )
            elif current < last_low and prior_low < current:
                add(
                    f"CRT_EXPANSION_SHORT_{tf.upper()}",
                    f"CRT Range Expansion ({tf.upper()})",
                    "SHORT", last_low, last_high, prior_low,
                    [f"{tf.upper()} reference-candle low", "range expansion", "prior low"],
                    ["CRT", "TTRADES"],
                )

    # De-duplicate exact geometry; different strategy families with identical
    # levels are not useful as separate plans.
    deduped, seen = [], set()
    for item in out:
        key = (
            item["side"],
            round(item["entry"], 5),
            round(item["stop"], 5),
            round(item["targets"][0], 5),
        )
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped

def rank_trade_candidates(state, execution, parsed=None):
    """Rank distinct, source-derived setup candidates.

    The engine can emit up to five plans. Four are structural routes from the
    deterministic execution engine; two optional range-reversion routes use
    the observed current price plus the same source-derived local boundaries.
    No synthetic price ladder is created.
    """
    t = state.get("technical") or {}
    d = state.get("decision") or {}
    structural = str(d.get("structural_bias") or "MIXED").upper()
    current = _n((state.get("price") or {}).get("cfd"))
    routes = [r for r in (execution.get("routes") or []) if isinstance(r, dict)]

    def score_route(r):
        e = _n(r.get("trigger"))
        s = _n(r.get("stop"))
        targets = [_n(x) for x in r.get("targets") or [] if _n(x) is not None]
        if e is None or s is None or not targets:
            return None
        side = str(r.get("side") or "").upper()
        score = 20.0
        reasons = []
        aligned = (
            (structural == "BULLISH" and side.startswith("LONG"))
            or (structural == "BEARISH" and side.startswith("SHORT"))
        )
        if aligned:
            score += 12; reasons.append("HTF alignment")
        elif structural in ("BULLISH", "BEARISH"):
            score -= 8; reasons.append("countertrend")

        for tf, w in (("d1", 4), ("h4", 8), ("h1", 7), ("m30", 5), ("m15", 5), ("m5", 4)):
            tr = str((t.get(tf) or {}).get("trend") or "").lower()
            if (side.startswith("LONG") and tr == "bullish") or (side.startswith("SHORT") and tr == "bearish"):
                score += w
            elif (side.startswith("LONG") and tr == "bearish") or (side.startswith("SHORT") and tr == "bullish"):
                score -= 2

        m5 = t.get("m5") or {}
        m15 = t.get("m15") or {}
        ev = f"{m5.get('choch') or ''} {m5.get('bos') or ''}"
        if (side.startswith("LONG") and "bullish" in ev) or (side.startswith("SHORT") and "bearish" in ev):
            score += 8; reasons.append("structure event")
        sw = str(m5.get("sweep") or "")
        if (side.startswith("LONG") and "sell_side" in sw) or (side.startswith("SHORT") and "buy_side" in sw):
            score += 6; reasons.append("liquidity sweep")
        dv = m5.get("divergence") or {}
        if (side.startswith("LONG") and dv.get("type") == "bullish_regular") or (side.startswith("SHORT") and dv.get("type") == "bearish_regular"):
            score += 5; reasons.append("divergence")
        if m5.get("fvg") or m15.get("fvg"):
            score += 3; reasons.append("FVG")
        if (r.get("risk") or {}).get("status") == "PASS":
            score += 6; reasons.append("risk geometry")
        rr = (r.get("rr") or [None])[0]
        if isinstance(rr, (int, float)):
            score += min(8.0, max(0.0, float(rr) * 2.0))
        name, features, families = _name(r, state)
        return {
            "route": r.get("route"),
            "strategy": name,
            "side": side,
            "entry": e,
            "stop": s,
            "targets": targets[:5],
            "score": round(score, 2),
            "evidence": reasons,
            "features": features,
            "strategy_families": families,
        }

    rows = []
    for r in routes:
        item = score_route(r)
        if item:
            rows.append(item)

    # Add genuinely different OHLC-derived setup hypotheses when the four
    # canonical execution routes do not provide enough distinct geometry.
    # These remain research candidates until the normal risk/plan gate accepts
    # them; no level is manufactured.
    for candidate in _technical_setup_candidates(state, parsed):
        score = 16.0
        side = candidate["side"]
        if (structural == "BULLISH" and side == "LONG") or (structural == "BEARISH" and side == "SHORT"):
            score += 10.0
        elif structural in ("MIXED", "TRANSITION", "NEUTRAL"):
            score += 4.0
        else:
            score -= 6.0
        tf_name = candidate["route"].rsplit("_", 1)[-1].lower()
        tf_weight = {"d1": 8, "h1": 7, "m30": 5, "m15": 4, "m5": 3}.get(tf_name, 2)
        score += tf_weight
        score += min(12.0, candidate["_rr"] * 2.0)
        candidate["score"] = round(score, 2)
        candidate.pop("_rr", None)
        rows.append(candidate)

    # Optional mean-reversion routes are valid only when price is actually
    # inside two source-derived local boundaries. This gives the ranking engine
    # a fifth distinct setup class without inventing levels.
    if current is not None:
        upper = _n((state.get("market_map") or {}).get("local_action_resistance"))
        lower = _n((state.get("market_map") or {}).get("local_action_support"))
        if upper is not None and lower is not None and lower < current < upper:
            band = upper - lower
            if band > 0:
                for side in ("LONG", "SHORT"):
                    if side == "LONG":
                        entry, stop, tp = current, lower, upper
                    else:
                        entry, stop, tp = current, upper, lower
                    rr = _risk_ratio(side, entry, stop, tp)
                    if rr is None or rr < 1.0:
                        continue
                    score = 18.0
                    reasons = ["inside local structural band", "source-derived band target"]
                    if structural == "MIXED":
                        score += 8
                    elif (structural == "BULLISH" and side == "LONG") or (structural == "BEARISH" and side == "SHORT"):
                        score += 4
                    else:
                        score -= 8
                    # Negative gamma is a direct penalty for mean reversion:
                    # it increases the chance that a boundary break extends.
                    gex = _n(((state.get("gamma") or {}).get("net_gex")))
                    if gex is not None and gex < 0:
                        score -= 5; reasons.append("negative gamma penalty")
                    route = f"RANGE_MEAN_REVERSION_{side}"
                    rows.append({
                        "route": route,
                        "strategy": "MSNR/Gamma-Band Mean Reversion " + ("Long" if side == "LONG" else "Short"),
                        "side": side,
                        "entry": entry,
                        "stop": stop,
                        "targets": [tp],
                        "score": round(score, 2),
                        "evidence": reasons,
                        "features": ["RANGE", "MEAN_REVERSION"],
                        "strategy_families": ["MSNR", "TTRADES"],
                    })

    rows.sort(key=lambda x: (x["score"], len(x["targets"])), reverse=True)
    selected = []
    seen = set()
    for x in rows:
        key = (x["route"], x["side"], round(float(x["entry"]), 5), round(float(x["stop"]), 5))
        if key in seen:
            continue
        seen.add(key)
        x["rank"] = len(selected) + 1
        selected.append(x)
        if len(selected) == 5:
            break
    return selected

def build_multi_domain_context(parsed,state,execution):
    quant=build_quant_evidence(parsed)
    macro=_macro(parsed,state); micro=_micro(state); psychology=_psych(state)
    candidates=rank_trade_candidates(state,execution,parsed)
    # Keep deterministic context available to the ranking layer and downstream
    # renderers without making the score a probability.
    state["quant"] = quant
    state["macro"] = macro
    state["psychology"] = psychology
    conflicts=[]
    structural=str((state.get("decision") or {}).get("structural_bias") or "MIXED").upper()
    for x in candidates:
        if structural=="BULLISH" and x["side"].startswith("SHORT"): conflicts.append("countertrend:"+str(x["route"]))
        if structural=="BEARISH" and x["side"].startswith("LONG"): conflicts.append("countertrend:"+str(x["route"]))
    return {"version":"multi-domain-v1","macro":macro,"microstructure":micro,"psychology":psychology,
            "quant":quant,"strategy_candidates":candidates,"conflicts":conflicts,
            "method":"evidence-first deterministic ranking; score is not probability"}
