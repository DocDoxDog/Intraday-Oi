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
PROMPT_VERSION = "intraday-oi-market-analyst-v5"
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
    """Build the finite set of price references the analyst is allowed to use."""
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
            return round(float(price) - float(future_price) + float(cfd_price), 5)
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
            "price": round(float(current_price), 5),
            "reason": "current reference price",
            "source": "parsed.current",
        })

    # Options/GEX references.
    add("gex:gamma_flip", gex.get("gamma_flip"), "cumulative GEX crossing", "raw_series.gex")
    add("gex:call_wall", gex.get("call_wall"), "largest positive call GEX strike", "raw_series.gex")
    add("gex:put_wall", gex.get("put_wall"), "largest negative put GEX strike", "raw_series.gex")
    add("gex:max_abs_net", gex.get("max_abs_gex_strike"), "largest absolute net GEX strike", "raw_series.gex")

    gamma = raw.get("multi_expiry_gamma") or {}
    zones = raw.get("multi_expiry_gamma_zones") or {}
    add("gamma:highest_positive", zones.get("highest_positive_gamma"), "highest aggregate positive gamma concentration", "raw_series.multi_expiry_gamma")
    add("gamma:highest_negative", zones.get("highest_negative_gamma"), "highest aggregate negative gamma concentration", "raw_series.multi_expiry_gamma")
    for prefix, items in (
        ("gamma:positive", zones.get("positive_concentrations") or []),
        ("gamma:negative", zones.get("negative_concentrations") or []),
    ):
        for item in items[:10]:
            if isinstance(item, dict):
                strike = item.get("strike")
                slug = str(strike).replace(".", "p")
                add(
                    f"{prefix}:{slug}",
                    strike,
                    "multi-expiry GEX concentration",
                    "raw_series.multi_expiry_gamma",
                )

    ranked = sorted(
        (
            row for row in rows
            if isinstance(row, dict) and isinstance(row.get("strike"), (int, float))
        ),
        key=lambda row: abs(float(row.get("net_gex") or 0)),
        reverse=True,
    )
    for row in ranked[:20]:
        strike = float(row["strike"])
        slug = ("%.8f" % strike).rstrip("0").rstrip(".").replace("-", "m").replace(".", "p")
        add(
            f"gex:strike:{slug}",
            strike,
            "deterministic net GEX strike",
            "raw_series.gex.rows",
        )

    # Market-state levels are already normalized to CFD coordinates and are
    # authoritative candidates for the analyst; do not force the model to
    # reconstruct them from raw Futures strikes.
    market_state = raw.get("market_state") or {}
    state_levels = market_state.get("levels") or {}
    for level_id, value in state_levels.items():
        if isinstance(value, (int, float)):
            levels.append({
                "id": f"market_state:{level_id}",
                "price": round(float(value), 5),
                "reason": "deterministic normalized CFD level",
                "source": "raw_series.market_state.levels",
            })

    gamma_state = market_state.get("gamma") or {}
    gamma_mean = gamma_state.get("gamma_mean")
    if isinstance(gamma_mean, (int, float)):
        levels.append({
            "id": "gamma:mean",
            "price": round(float(gamma_mean), 5) if parsed.get("cfd_price") is not None else None,
            "reason": "deterministic gamma mean",
            "source": "raw_series.market_state.gamma",
        })
    for item in gamma_state.get("acceleration_zones") or []:
        strike = item.get("strike_futures") if isinstance(item, dict) else None
        if isinstance(strike, (int, float)):
            converted = to_display_price(strike)
            if converted is not None:
                levels.append({
                    "id": f"gamma:acceleration:{strike}",
                    "price": converted,
                    "reason": "deterministic gamma acceleration zone",
                    "source": "raw_series.market_state.gamma",
                })

    # Technical prices are deterministic Twelve Data evidence and live in CFD
    # coordinates already. They are references, not automatic support/resistance.
    technical = parsed.get("technical_context") or {}
    timeframes = technical.get("timeframes") or {}
    technical_keys = (
        "ema50", "ema200", "previous_close", "prior_high", "prior_low",
        "swing_high", "swing_low",
    )
    for tf, context in timeframes.items():
        if not isinstance(context, dict):
            continue
        for key in technical_keys:
            add(
                f"technical:{tf}:{key}",
                context.get(key),
                f"{tf.upper()} {key.replace('_', ' ')}",
                f"technical_context.{tf}",
            )
        fib = context.get("fibonacci") or {}
        for key in ("retracement_62", "retracement_79"):
            add(
                f"technical:{tf}:fib:{key}",
                fib.get(key),
                f"{tf.upper()} Fibonacci {key}",
                f"technical_context.{tf}.fibonacci",
            )
        fvg = context.get("fvg") or {}
        if isinstance(fvg, dict):
            add(
                f"technical:{tf}:fvg_low",
                fvg.get("low"),
                f"{tf.upper()} FVG low",
                f"technical_context.{tf}.fvg",
            )
            add(
                f"technical:{tf}:fvg_high",
                fvg.get("high"),
                f"{tf.upper()} FVG high",
                f"technical_context.{tf}.fvg",
            )

    return levels


def _json_safe(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return str(value)


def _compact_history(parsed: dict[str, Any], history: dict[str, Any] | None) -> dict[str, Any]:
    history = history or {}

    def compact_snapshot(row: Any) -> dict[str, Any] | None:
        if not isinstance(row, dict):
            return None
        raw = row.get("raw_series") or {}
        totals = raw.get("totals") or {}
        gex = raw.get("gex") or {}
        return {
            "captured_at": row.get("captured_at"),
            "future_price": row.get("future_price"),
            "future_chg": row.get("future_chg"),
            "vol": row.get("vol"),
            "vol_chg": row.get("vol_chg"),
            "oi_put": totals.get("open_interest_view_put", totals.get("open_interest_put")),
            "oi_call": totals.get("open_interest_view_call", totals.get("open_interest_call")),
            "oi_total": totals.get("open_interest_view_total", totals.get("open_interest_total")),
            "oi_change_put": (
                totals.get("oi_delta_put")
                if totals.get("oi_delta_put") is not None
                else totals.get("oi_change_put")
            ),
            "oi_change_call": (
                totals.get("oi_delta_call")
                if totals.get("oi_delta_call") is not None
                else totals.get("oi_change_call")
            ),
            "oi_change_total": totals.get("oi_delta_total"),
            "churn": totals.get("churn"),
            "gex_net": gex.get("net_gex"),
            "gamma_flip": gex.get("gamma_flip"),
            "call_wall": gex.get("call_wall"),
            "put_wall": gex.get("put_wall"),
        }

    current_raw = parsed.get("raw_series") or {}
    current_totals = current_raw.get("totals") or {}
    current_gex = current_raw.get("gex") or {}
    current = {
        "future_price": parsed.get("future_price"),
        "vol": parsed.get("vol"),
        "oi_put": current_totals.get("open_interest_view_put", current_totals.get("open_interest_put")),
        "oi_call": current_totals.get("open_interest_view_call", current_totals.get("open_interest_call")),
        "oi_total": current_totals.get("open_interest_view_total", current_totals.get("open_interest_total")),
        "oi_change_put": (
            current_totals.get("oi_delta_put")
            if current_totals.get("oi_delta_put") is not None
            else current_totals.get("oi_change_put")
        ),
        "oi_change_call": (
            current_totals.get("oi_delta_call")
            if current_totals.get("oi_delta_call") is not None
            else current_totals.get("oi_change_call")
        ),
        "oi_change_total": (
            current_totals.get("oi_delta_total")
            if current_totals.get("oi_delta_total") is not None
            else current_totals.get("oi_change_total")
        ),
        "churn": current_totals.get("churn"),
        "gex_net": current_gex.get("net_gex"),
        "gamma_flip": current_gex.get("gamma_flip"),
        "call_wall": current_gex.get("call_wall"),
        "put_wall": current_gex.get("put_wall"),
    }

    def diff(base: dict | None) -> dict:
        if not base:
            return {"status": "UNKNOWN"}
        out = {"status": "VALID"}
        for key in (
            "future_price", "vol", "oi_put", "oi_call", "oi_total",
            "oi_change_put", "oi_change_call", "oi_change_total",
            "churn", "gex_net",
        ):
            now_value = current.get(key)
            old_value = base.get(key)
            if isinstance(now_value, (int, float)) and isinstance(old_value, (int, float)):
                out[key] = round(float(now_value) - float(old_value), 6)
            else:
                out[key] = None
        return out

    hour = compact_snapshot(history.get("hour_ago"))
    today = history.get("today") or {"count": 0}
    yesterday = history.get("yesterday") or {"count": 0}

    today_open = {
        "future_price": today.get("future_price_open"),
        "vol": today.get("vol_last") if today.get("count") == 1 else None,
        "oi_put": (today.get("oi_first") or {}).get("oi_put"),
        "oi_call": (today.get("oi_first") or {}).get("oi_call"),
        "oi_total": (today.get("oi_first") or {}).get("oi_total"),
        "oi_change_put": (today.get("oi_first") or {}).get("oi_change_put"),
        "oi_change_call": (today.get("oi_first") or {}).get("oi_change_call"),
        "oi_change_total": (today.get("oi_first") or {}).get("oi_change_total"),
        "churn": (today.get("oi_first") or {}).get("churn"),
        "gex_net": (today.get("oi_first") or {}).get("gex_net"),
    }
    yesterday_last = today_open.copy()
    if yesterday.get("count"):
        yesterday_last = {
            "future_price": yesterday.get("future_price_last"),
            "vol": yesterday.get("vol_last"),
            "oi_put": (yesterday.get("oi_last") or {}).get("oi_put"),
            "oi_call": (yesterday.get("oi_last") or {}).get("oi_call"),
            "oi_total": (yesterday.get("oi_last") or {}).get("oi_total"),
            "oi_change_put": (yesterday.get("oi_last") or {}).get("oi_change_put"),
            "oi_change_call": (yesterday.get("oi_last") or {}).get("oi_change_call"),
            "oi_change_total": (yesterday.get("oi_last") or {}).get("oi_change_total"),
            "churn": (yesterday.get("oi_last") or {}).get("churn"),
            "gex_net": (yesterday.get("oi_last") or {}).get("gex_net"),
        }

    return {
        "hour_ago": hour,
        "today": today,
        "yesterday": yesterday,
        "changes": {
            "vs_hour_ago": diff(hour),
            "vs_today_open": diff(today_open),
            "vs_yesterday_last": diff(yesterday_last if yesterday.get("count") else None),
        },
    }


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
        "product_symbol": parsed.get("product_symbol"),
        "contract": parsed.get("contract"),
        "observed_at": parsed.get("observed_at"),
        "future_price": parsed.get("future_price"),
        "future_chg": parsed.get("future_chg"),
        "spot_price": parsed.get("spot_price"),
        "basis_diff": parsed.get("basis_diff"),
        "cfd_price": parsed.get("cfd_price"),
        "price_conversion": parsed.get("price_conversion"),
        "dte": parsed.get("dte"),
        "vol": parsed.get("vol"),
        "vol_chg": parsed.get("vol_chg"),
        "technical_context": parsed.get("technical_context") or {},
        "raw_series": {
            "market_state": raw.get("market_state") or {},
            "totals": totals,
            "dte": raw.get("dte"),
            "heading": raw.get("heading"),
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
            },
            "multi_expiry_gamma": {
                "version": (raw.get("multi_expiry_gamma") or {}).get("version"),
                "status": (raw.get("multi_expiry_gamma") or {}).get("status"),
                "expiration_count": (raw.get("multi_expiry_gamma") or {}).get("expiration_count"),
                "columns": [
                    {
                        "code": col.get("code"),
                        "dte": col.get("dte"),
                        "observed_at": col.get("observed_at"),
                        "status": col.get("status"),
                    }
                    for col in ((raw.get("multi_expiry_gamma") or {}).get("columns") or [])[:10]
                ],
                "zones": raw.get("multi_expiry_gamma_zones") or {},
                "totals": (raw.get("multi_expiry_gamma") or {}).get("totals") or {},
            },
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
            for row in sorted(
                rows,
                key=lambda row: abs(float(row.get("net_gex") or 0))
                if isinstance(row, dict) and isinstance(row.get("strike"), (int, float))
                else 0.0,
                reverse=True,
            )[:40]
            if isinstance(row, dict)
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
        for item in (parsed.get("news_context") or [])[:8]
        if isinstance(item, dict)
    ]
    return {
        "current": _json_safe(current),
        "history": _json_safe(_compact_history(parsed, history)),
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

วิเคราะห์ “ตอนนี้” ทันทีจากข้อมูลที่ได้รับ ไม่ต้องรอ confirmation เพิ่มเพื่อเริ่มวิเคราะห์
แต่ต้องแยกให้ชัดระหว่าง MARKET VIEW กับ TRADE TRIGGER

DECISION FLOW
MACRO
→ MARKET REGIME
→ GEX / FINANCIAL ENGINEERING
→ OI / ΔOI / CHURN / VOLATILITY
→ HISTORY CHANGE (1H / TODAY / YESTERDAY)
→ LIQUIDITY / MARKET MICROSTRUCTURE
→ PRICE ACTION / TECHNICAL
→ MARKET PSYCHOLOGY / GAME THEORY
→ SCENARIOS
→ TRADE PLAN / RISK

FINANCIAL ENGINEERING
พิจารณา GEX, Gamma Mean/Pivot, Positive/Negative Gamma, Gamma Flip,
Strike Concentration, OI, ΔOI, Call/Put positioning, Expiration, IV,
IV Term Structure, Volatility Skew, Dealer Hedging, Delta Hedging,
Convexity, Liquidity, Pinning/Magnet และ Acceleration Zones
Gamma ไม่ใช่ direction: Positive Gamma/Negative Gamma ใช้อธิบาย hedging flow,
volatility behavior, regime และ price structure เท่านั้น

MACRO
แยก STRUCTURAL MACRO กับ SHORT-TERM CATALYST
ดู Fed, rates, real yields, DXY, inflation, CPI/PCE, employment/NFP, GDP,
Treasury yields, liquidity, central-bank demand, geopolitical risk,
growth/recession, fiscal policy และ opportunity cost
ถ้าไม่มี macro/news evidence ให้เขียน UNKNOWN/NEUTRAL ตามหลักฐาน ห้ามเดา

MICROSTRUCTURE / PSYCHOLOGY
แยก LEVEL ≠ TRIGGER
พิจารณา liquidity, volume, absorption, imbalance, sweep, failed breakout,
price discovery, trapped traders, stop clustering, FOMO, hedging/chasing
แต่ห้ามกล่าวอ้าง microstructure/psychology ที่ไม่มี evidence รองรับ

REGIME
เลือก POSITIVE_GAMMA_MEAN_REVERSION, NEGATIVE_GAMMA_VOLATILITY_EXPANSION,
RANGE, BREAKOUT, BREAKDOWN หรือ TRANSITION_UNCERTAIN
ใช้ข้อมูลหลายชั้น ไม่ใช้ GEX เครื่องหมายเดียว

HISTORY
ต้องเปรียบเทียบ current กับ 3 horizon ทุกครั้ง:
1) hour_ago = การเปลี่ยนแปลงล่าสุดราว 1 ชั่วโมง
2) today = current เทียบกับ today_open + intraday range
3) yesterday = current เทียบกับวันก่อนหน้า/last available
ใน history_comparison ต้องกล่าวถึงทั้ง 1H, TODAY และ YESTERDAY แยกกันอย่างชัดเจน
และต้องระบุทั้ง price, IV/volatility, OI/ΔOI, churn และ Net GEX เมื่อข้อมูลมี
ถ้าข้อมูลตัวใดไม่มี baseline ให้เขียน UNKNOWN เฉพาะตัวนั้น ห้ามทำให้ทั้ง section เป็น UNKNOWN
ห้ามสร้าง delta ถ้าข้อมูลก่อนหน้าไม่มี

FUTURES → CFD
ราคาปัจจุบัน CFD = Futures - Basis
เมื่อมี basis_diff ให้ level จาก Futures แปลงเป็น CFD ด้วย:
CFD Level = Futures Level - basis_diff
แสดงราคาที่ผู้ใช้เทรดเป็น CFD และเก็บ Futures ไว้เป็น reference
ตัวเลขราคา/ค่าที่แสดงในข้อความให้ใช้ทศนิยม 2 ตำแหน่ง

GAMMA MAP
หา Gamma Mean/Pivot, Resistance, First Defense, Secondary Defense,
Gamma Flip, Acceleration Level, Major Liquidity และ Next Target
4200, 4195, 4190–4180, 4175, 4150 เป็นเพียง hypothesis
ต้องตรวจสอบจาก evidence ล่าสุดก่อนใช้

TRADE PLAN — ต้องมีทุกครั้ง
ไม่ต้องรอ confirmation เพิ่มเพื่อ “สร้างแผน”
แผนต้องถูกสร้างในรอบนี้ทันที และต้องมี LONG + SHORT conditional logic แม้ bias จะ WAIT
เมื่อ trigger ยังไม่เกิด ให้ใช้ status=CONDITIONAL แต่ห้ามตอบเพียง “รอ confirmation” หรือ “คำนวณเมื่อ trigger” หากมี deterministic level ที่ใช้กำหนดแผนได้
Entry / Stop / TP1 / TP2 ต้องอ้างอิง deterministic levels หรือ current CFD price เท่านั้น
ห้ามสร้างราคาใหม่และห้ามเดาตัวเลข
ถ้ามี level ที่ valid ให้ระบุราคา Entry/Stop/TP เป็นตัวเลข 2 ตำแหน่ง พร้อมบอกว่าเป็น CONDITIONAL ENTRY/STOP/TP
ห้ามใช้ข้อความ “คำนวณเมื่อ trigger” แทนตัวเลข หาก deterministic level ที่เหมาะกับ conditional plan มีอยู่แล้ว
Risk/Reward ให้คำนวณเมื่อมีตัวเลข Entry/Stop/TP ครบ; ถ้ายังไม่ครบให้ระบุ UNKNOWN อย่างตรงไปตรงมา

OUTPUT DISCIPLINE
แต่ละ narrative field ให้สรุป 1–3 ประโยคที่มีสาระจริง หลีกเลี่ยงการกล่าวซ้ำข้าม section
รวม Macro + GEX + Microstructure + Psychology เป็น causal chain เดียวกันเมื่อเหตุผลเชื่อมโยงกันได้
รวม OI + OI Change + Churn + IV + History เป็น flow/change story เดียวกัน
ห้ามใส่หัวข้อยาวหรือคำนำซ้ำ เพราะ Telegram renderer จะจัดรูปแบบให้เอง
ตัวเลขราคา/CFD/GEX/OI/Change/Churn/IV ที่ใส่ใน output ให้ปัดเป็นทศนิยม 2 ตำแหน่งเฉพาะค่าที่เป็น market price/ratio; ห้ามเปลี่ยนค่าหลักฐานสาระสำคัญ

OUTPUT JSON
ต้องมี fields:
analysis_status
market_overview
market_regime
macro
financial_engineering
market_microstructure
market_psychology
what
why
positioning
history_comparison
levels
scenarios
base_case
alternative_case
invalidation_case
bias
uncertainty
trade_plan
final_trade_idea
evidence_refs
data_limitations

RULES
- evidence > assumption
- confirmation > prediction
- level ≠ signal
- Gamma ≠ direction
- OI ≠ direction
- News ≠ entry
- ใช้เฉพาะ evidence_refs ที่ input ให้
- ห้ามอ้างข่าวถ้า input ไม่มี news evidence
- ภาษาไทยธรรมชาติแบบ trader อธิบายให้คนทั่วไปเข้าใจ
"""



def analyze_with_supabot(parsed: dict[str, Any], history: dict[str, Any] | None = None) -> dict[str, Any]:
    now = _utc_now()
    as_of = _iso(parsed.get("observed_at") or parsed.get("retrieved_at") or now)
    product = _product(parsed)
    payload = _summarize_input(parsed, history)

    input_refs = [
        "itb:oi:deterministic",
        "itb:oi:history",
    ]
    if payload["current"].get("news_context"):
        input_refs.append("itb:news:latest")
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
        **({
            "itb:news:latest": {
                "source": "governed_macro_news_feeds",
                "observed_at": as_of,
                "ingestion_time": as_of,
                "payload": {"items": payload["current"].get("news_context") or []},
            }
        } if payload["current"].get("news_context") else {}),
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
            dynamic={
                "format": "human_analyst_thai",
                "priority": ["WHAT","WHY","POSITIONING","LEVELS","SCENARIO","CONFIRMATION","INVALIDATION","WAIT"],
                "numeric_level_policy": "PRICE CLAIMS MAY USE ONLY VALUES PRESENT IN deterministic_levels OR current market snapshot. Do not invent, interpolate, calculate, or introduce any new price number.",
                "allowed_price_levels": payload["deterministic_levels"],
            },
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
