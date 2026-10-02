"""Central LLM adapter for Intraday-Oi.

Intraday-Oi owns the complete supaBOT-compatible governed LLM path locally.

The repository owns deterministic calculations, routing, structured output, verification, and telemetry; no separate supaBOT checkout is required.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

try:
    from .local_supabot import LocalSupaBOTError, generate_market_narrative
except ImportError:
    from local_supabot import LocalSupaBOTError, generate_market_narrative


DEFAULT_GATEWAY_PATH = "/internal/v1/llm/generate"
TASK = "market.narrative"
PROMPT_VERSION = "intraday-oi-market-analyst-v3"
DATASET_VERSION = "quikstrike-oi-view-v2"
CALCULATION_VERSION = "intraday-oi-calcs-v1"


class SupaBOTLLMError(RuntimeError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise SupaBOTLLMError("INVALID_AS_OF") from exc
    if dt.tzinfo is None:
        raise SupaBOTLLMError("AS_OF_TIMEZONE_REQUIRED")
    return dt.astimezone(timezone.utc).isoformat()


def _product(parsed: dict[str, Any]) -> str:
    explicit = parsed.get("product_symbol")
    if explicit:
        return str(explicit).upper()
    raw = parsed.get("raw_series") or {}
    product = raw.get("product")
    if isinstance(product, dict) and product.get("symbol"):
        return str(product["symbol"]).upper()
    contract = str(parsed.get("contract") or "").upper()
    match = re.search(r"\b(GC|SI|CL|ES|NQ)\b", contract)
    if match:
        return match.group(1)
    raise SupaBOTLLMError("PRODUCT_UNRESOLVED")


def _level_candidates(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    raw = parsed.get("raw_series") or {}
    gex = raw.get("gex") or {}
    rows = raw.get("strike_rows") or []
    levels: list[dict[str, Any]] = []

    def to_display_price(price: Any) -> Any:
        if not isinstance(price, (int, float)) or price <= 0:
            return None
        future_price = parsed.get("future_price")
        cfd_price = parsed.get("cfd_price")
        if isinstance(future_price, (int, float)) and isinstance(cfd_price, (int, float)):
            return float(price) - float(future_price) + float(cfd_price)
        return float(price)

    def add(level_id: str, price: Any, reason: str, source: str) -> None:
        display_price = to_display_price(price)
        if display_price is not None:
            levels.append({
                "id": level_id,
                "price": display_price,
                "reason": reason,
                "source": source,
            })

    current_price = parsed.get("cfd_price", parsed.get("future_price"))
    if isinstance(current_price, (int, float)) and current_price > 0:
        levels.append({
            "id": "price:current",
            "price": float(current_price),
            "reason": "current reference price",
            "source": "parsed.current",
        })

    add("gex:gamma_flip", gex.get("gamma_flip"), "cumulative GEX crossing", "raw_series.gex")
    add("gex:call_wall", gex.get("call_wall"), "largest positive call GEX strike", "raw_series.gex")
    add("gex:put_wall", gex.get("put_wall"), "largest negative put GEX strike", "raw_series.gex")
    add("gex:max_abs_net", gex.get("max_abs_gex_strike"), "largest absolute net GEX strike", "raw_series.gex")

    ranked = sorted(
        (row for row in rows if isinstance(row, dict) and isinstance(row.get("strike"), (int, float))),
        key=lambda row: abs(float(row.get("net_gex") or 0)),
        reverse=True,
    )
    for row in ranked[:12]:
        strike = float(row["strike"])
        slug = ("%.8f" % strike).rstrip("0").rstrip(".").replace("-", "m").replace(".", "p")
        add(
            f"gex:strike:{slug}",
            strike,
            "deterministic net GEX strike",
            "raw_series.gex.rows",
        )
    return levels


def _json_safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return str(value)


def _summarize_input(parsed: dict[str, Any], history: dict[str, Any] | None) -> dict[str, Any]:
    raw = parsed.get("raw_series") or {}
    rows = raw.get("strike_rows") or []
    gex = raw.get("gex") or {}
    totals = raw.get("totals") or {}
    top_gex = sorted(
        (
            {
                "strike": row.get("strike"),
                "call_gex": row.get("call_gex"),
                "put_gex": row.get("put_gex"),
                "net_gex": row.get("net_gex"),
                "gamma_source": row.get("gamma_source"),
            }
            for row in rows
            if isinstance(row, dict) and row.get("strike") is not None
        ),
        key=lambda row: abs(float(row.get("net_gex") or 0)),
        reverse=True,
    )[:15]

    current = {
        k: v
        for k, v in parsed.items()
        if k not in {"screenshot"}
    }
    current["raw_series"] = {
        "totals": totals,
        "dte": raw.get("dte"),
        "heading": raw.get("heading"),
        "expected_ranges": raw.get("expected_ranges") or [],
        "cfd_expected_ranges": raw.get("cfd_expected_ranges") or [],
        "gex": {
            "status": gex.get("status"),
            "net_gex": gex.get("net_gex"),
            "call_gex_total": gex.get("call_gex_total"),
            "put_gex_total": gex.get("put_gex_total"),
            "gamma_flip": gex.get("gamma_flip"),
            "call_wall": gex.get("call_wall"),
            "put_wall": gex.get("put_wall"),
            "max_abs_gex_strike": gex.get("max_abs_gex_strike"),
            "gex_unit": gex.get("gex_unit"),
            "gamma_source": gex.get("gamma_source"),
            "rows": top_gex,
        },
        "multi_expiry_gamma": {
            "version": (raw.get("multi_expiry_gamma") or {}).get("version"),
            "status": (raw.get("multi_expiry_gamma") or {}).get("status"),
            "expiration_count": (raw.get("multi_expiry_gamma") or {}).get("expiration_count"),
            "columns": (raw.get("multi_expiry_gamma") or {}).get("columns") or [],
            "zones": raw.get("multi_expiry_gamma_zones") or {},
            "totals": (raw.get("multi_expiry_gamma") or {}).get("totals") or {},
        },
        "oi_rows": [
            {
                "strike": row.get("strike"),
                "oiCall": row.get("oiCall"),
                "oiPut": row.get("oiPut"),
                "oiTotal": row.get("oiTotal"),
                "oiCallChange": row.get("oiCallChange"),
                "oiPutChange": row.get("oiPutChange"),
                "vol": row.get("vol"),
            }
            for row in rows[:120]
        ],
    }
    current["news_context"] = [
        {
            "source": item.get("source"),
            "headline": item.get("headline"),
            "summary": item.get("summary"),
            "url": item.get("url"),
            "published_at": item.get("published_at"),
            "category": item.get("category"),
            "relevance": item.get("relevance"),
            "rights_status": item.get("rights_status"),
        }
        for item in (parsed.get("news_context") or [])[:10]
        if isinstance(item, dict)
    ]
    return {
        "current": _json_safe(current),
        "history": _json_safe(history or {}),
        "deterministic_levels": _level_candidates(parsed),
        "data_limitations": [
            "Open Interest is positioning data; it is not equivalent to traded intraday volume.",
            "Only source-supplied or deterministically derived values may be stated as numbers.",
            "Publication/availability timing of the QuikStrike snapshot is not assumed unless supplied by the source.",
        ],
    }


STATIC_PROMPT = """
คุณคือ GOLD MARKET ANALYST ของระบบ Intraday-Oi
ทำงานแบบ Quantitative + Financial Engineering + Macro Economics + Microeconomics + Market Psychology

เป้าหมาย:
อธิบายว่า “ตลาดกำลังอยู่ในสภาวะอะไร → อะไรเป็นแรงขับเคลื่อน → ระดับไหนสำคัญ → ตลาดจะตอบสนองอย่างไร → ต้องเห็นอะไรจึงเข้าเทรด”
ห้ามเดาทิศทางจาก indicator เดียว และห้ามสร้างตัวเลขที่ไม่มีหลักฐาน

ลำดับการวิเคราะห์:
MACRO
→ MARKET REGIME
→ GEX / FINANCIAL ENGINEERING
→ OI / ΔOI / VOLATILITY
→ LIQUIDITY / MARKET MICROSTRUCTURE
→ PRICE ACTION / TECHNICAL
→ MARKET PSYCHOLOGY / GAME THEORY
→ TRADE TRIGGER
→ RISK MANAGEMENT

MARKET REGIME:
เลือกจาก POSITIVE_GAMMA_MEAN_REVERSION, NEGATIVE_GAMMA_VOLATILITY_EXPANSION,
RANGE, BREAKOUT, BREAKDOWN, TRANSITION_UNCERTAIN
โดยใช้ GEX + OI + Price/Technical + Volatility + Macro ร่วมกัน
GEX เพียงอย่างเดียวห้ามตัดสิน regime

FINANCIAL ENGINEERING:
พิจารณา GEX, Gamma Mean/Pivot, Gamma Flip/Regime Change, Strike Concentration,
OI, ΔOI, Call/Put positioning, Expiration, IV, IV Term Structure, Volatility Skew,
Dealer Hedging, Delta Hedging, Convexity, Liquidity, Pinning/Magnet และ Acceleration Zones
Positive Gamma ≠ Direction
Negative Gamma ≠ Direction
GEX ใช้เพื่ออธิบาย hedging behavior, regime, levels และ risk ของ volatility

MACRO:
แยก STRUCTURAL MACRO กับ SHORT-TERM MACRO CATALYST
พิจารณา Fed, Rates, Real Yields, DXY, Inflation, CPI/PCE, Employment/NFP,
GDP, Liquidity, Treasury Yields, Central Bank demand, Geopolitical risk,
Growth/Recession expectations, Fiscal policy และ Opportunity Cost
สรุป Macro เป็น TAILWIND / HEADWIND / NEUTRAL เมื่อมี evidence
ห้ามใช้ Macro อย่างเดียวสร้าง trade

MARKET MICROSTRUCTURE:
แยก LEVEL ออกจาก TRIGGER
ดู Supply/Demand, Liquidity, Bid/Ask, Depth, Order Flow, Volume,
Volume Imbalance, Absorption, Aggressive Buyers/Sellers, Stop Liquidity,
Liquidity Sweep, Breakout/Failed Breakout, Auction และ Price Discovery
เช่น 4200 = LEVEL แต่ 4200 Break + Retest Fail = TRIGGER

MARKET PSYCHOLOGY / GAME THEORY:
ประเมิน Fear, Greed, FOMO, Panic, Profit Taking, Anchoring, Herding,
Loss Aversion, Position Crowding, Trapped Traders และ Stop Clustering
ถามเสมอว่า: ใครเสียเปรียบเมื่อ level แตก? ใครต้อง hedge? ใครติด position?
ใครต้อง chase? จุดไหน stop/liquidity มีแนวโน้มกระจุกตัว?
ห้ามสรุป psychology โดยไม่มี Price/OI/Liquidity evidence

GAMMA MAP:
หา Gamma Mean/Pivot, Resistance, First Defense, Secondary Defense,
Gamma Flip, Acceleration Level, Major Liquidity และ Next Target
4200, 4195, 4190–4180, 4175, 4150 เป็น HYPOTHESIS เท่านั้น
ต้องตรวจสอบกับข้อมูลล่าสุดก่อนใช้

LONG LOGIC:
Pullback → Support Hold/Absorption → Selling Pressure ลด → OI/Volume/Technical confirm → LONG
หรือ Resistance Break → Hold Above → Retest Success → Momentum confirm → LONG

SHORT LOGIC:
Break → Retest → Failure → Seller Confirm → OI/Volume/Technical confirm → SHORT
ห้าม SHORT หรือ LONG เพราะ Break เพียงครั้งเดียว

FALSE BREAKOUT / FALSE BREAKDOWN:
วิเคราะห์ทั้ง genuine และ false case ทุกครั้ง
Break แล้ว reclaim/กลับเข้า range = false-break risk สูงขึ้น

BAYESIAN THINKING:
BASE CASE / ALTERNATIVE CASE / INVALIDATION CASE
ห้ามสร้าง Probability เป็นตัวเลขถ้าไม่มีสถิติรองรับ

TRADE PLAN — ต้องมีทุกครั้ง:
- ห้ามตอบ NO_TRADE เพียงเพราะข้อมูลบางชั้นหาย
- เมื่อ evidence ยังไม่พอ ให้ใช้ CONDITIONAL + WAIT และทำ “แผนเฝ้ารอ” จาก deterministic levels
- เมื่อ trigger และ confirmation ครบ ให้ใช้ READY
- Entry / Stop / TP1 / TP2 ต้องอ้างอิง deterministic_levels หรือ current price เท่านั้น
- หากยังไม่มี trigger ให้ Entry เป็นเงื่อนไข เช่น “รอ Break/Retest ที่ <level>” ไม่ใช่เลขสมมติ
- ต้องระบุ Direction, Entry, Stop, TP1, TP2, Trigger, Invalidation, Risk/Reward และ Market Condition
- ห้ามสร้างตัวเลขราคาใหม่
- NO_TRADE ใช้เฉพาะกรณีไม่มี current price หรือไม่มี price level ที่ใช้ conditional plan ได้จริง

CORE:
LEVEL ≠ SIGNAL
Gamma ≠ Direction
OI ≠ Direction
News ≠ Entry
Breakout ≠ Confirmation
Support ≠ Automatic Long
Resistance ≠ Automatic Short
Evidence > Assumption
Confirmation > Prediction
Risk Management > Confidence

OUTPUT:
JSON ตาม schema เท่านั้น
market_overview = ภาพรวม
what = WHAT
why = WHY
positioning = POSITIONING
levels = KEY LEVELS
scenarios = Bull/Bear/Sideway พร้อม condition + confirmation + invalidation
trade_plan = conditional/ready plan ที่ใช้ได้ทุกครั้ง
evidence_refs ใช้เฉพาะ input_refs
ห้ามอ้าง Macro/News ถ้าไม่มี evidence
ภาษาไทยธรรมชาติ เหมือน trader อธิบายให้คนทั่วไปเข้าใจ
"""


def analyze_with_supabot(parsed: dict[str, Any], history: dict[str, Any] | None = None) -> dict[str, Any]:
    now = _utc_now()
    as_of = _iso(parsed.get("observed_at") or parsed.get("retrieved_at") or now)
    product = _product(parsed)
    payload = _summarize_input(parsed, history)

    input_refs = [
        "itb:oi:deterministic",
        "itb:oi:history",
        "itb:news:latest",
    ]
    evidence = {
        "itb:oi:deterministic": {
            "source": "cme_quikstrike",
            "observed_at": as_of,
            "ingestion_time": as_of,
            "dataset_version": DATASET_VERSION,
            "calculation_version": CALCULATION_VERSION,
            "payload": payload["current"],
            "deterministic_levels": payload["deterministic_levels"],
        },
        "itb:oi:history": {
            "source": "intraday_oi_history_store",
            "observed_at": as_of,
            "ingestion_time": as_of,
            "payload": payload["history"],
        },
        "itb:news:latest": {
            "source": "governed_macro_news_feeds",
            "observed_at": as_of,
            "ingestion_time": as_of,
            "payload": {"items": payload["current"].get("news_context") or []},
        },
    }

    envelope = {
        "request_id": f"itb-{uuid.uuid4()}",
        "run_id": f"itb-oi-{uuid.uuid4()}",
        "task": TASK,
        "repo": "DocDoxDog/Intraday-Oi",
        "product": product,
        "as_of": as_of,
        "data_status": "VALID",
        "dataset_version": DATASET_VERSION,
        "calculation_version": CALCULATION_VERSION,
        "prompt_version": PROMPT_VERSION,
        "input_refs": input_refs,
        "input_payload": {
            "market_snapshot": payload["current"],
            "deterministic_levels": payload["deterministic_levels"],
            "data_limitations": payload["data_limitations"],
        },
        "evidence": evidence,
        "model_policy": {
            "provider": "gemini",
            "selection": "local_supaBOT_task_router",
            "execution_authority": "deterministic_engine_only",
        },
        "output_schema_version": "market-analyst.v2",
    }

    try:
        result = generate_market_narrative(
            envelope,
            static_prefix=STATIC_PROMPT,
            dynamic={"format": "human_analyst_thai", "priority": ["WHAT","WHY","POSITIONING","LEVELS","SCENARIO","CONFIRMATION","INVALIDATION","WAIT"]},
        )
    except LocalSupaBOTError as exc:
        raise SupaBOTLLMError(str(exc)) from exc

    if result.get("status") != "SUCCESS":
        raise SupaBOTLLMError(f"GATEWAY_STATUS:{result.get('status')}")

    claims = result.get("claims")
    if not isinstance(claims, dict):
        raise SupaBOTLLMError("GATEWAY_CLAIMS_INVALID")

    output = dict(claims)
    output["short_bias"] = claims.get("bias", "WAIT")
    output["_llm_telemetry"] = {
        "task": TASK,
        "model": result.get("model"),
        "actual_model": result.get("actual_model"),
        "requested_model": result.get("requested_model"),
        "model_version": result.get("model_version"),
        "run_id": result.get("run_id"),
        "request_id": result.get("request_id"),
        "fallback_used": result.get("fallback_used", False),
        "latency_ms": result.get("latency_ms"),
    }
    output["llm_run_id"] = result.get("run_id")
    output["llm_verification"] = result.get("verification")
    output["evidence_refs"] = claims.get("evidence_refs", [])
    output["data_limitations"] = claims.get("data_limitations") or payload["data_limitations"]
    return output
