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
PROMPT_VERSION = "intraday-oi-market-analyst-v6"
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
        # QuikStrike source fields. Keep separate from EOD-baseline ΔOI.
        "oi_change_put": current_totals.get("oi_change_put"),
        "oi_change_call": current_totals.get("oi_change_call"),
        "oi_change_total": current_totals.get("oi_change_total"),
        "delta_oi_eod_put": current_totals.get("oi_delta_put"),
        "delta_oi_eod_call": current_totals.get("oi_delta_call"),
        "delta_oi_eod_total": current_totals.get("oi_delta_total"),
        "churn": current_totals.get("churn"),
        "quikstrike_churn_put": current_totals.get("quikstrike_churn_put"),
        "quikstrike_churn_call": current_totals.get("quikstrike_churn_call"),
        "eod_oi_put": ((current_raw.get("market_state") or {}).get("flow") or {}).get("eod_oi_put"),
        "eod_oi_call": ((current_raw.get("market_state") or {}).get("flow") or {}).get("eod_oi_call"),
        "eod_oi_total": ((current_raw.get("market_state") or {}).get("flow") or {}).get("eod_oi_total"),
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
                "churnCall": row.get("churnCall"),
                "churnPut": row.get("churnPut"),
                "eod_oi_call": row.get("eod_oi_call"),
                "eod_oi_put": row.get("eod_oi_put"),
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
            "market_channels": item.get("market_channels") or [],
            "freshness": item.get("freshness") or "UNKNOWN",
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
ทำหน้าที่เป็น Institutional Market Intelligence Analyst โดยใช้ข้อมูลที่มีจริงจาก
Options/GEX, OI/ΔOI, Volatility, Futures/CFD, History, Technical, Macro/News,
Market Microstructure, Liquidity, Dealer Hedging และ Market Psychology

สำคัญ:
- Output schema เดิมต้องคงเดิม
- ห้ามเพิ่ม fields เพื่อรองรับ reasoning
- ห้ามสร้างตัวเลขใหม่
- UNKNOWN คือข้อมูลที่ไม่มี ไม่ใช่เหตุผลที่จะหยุดวิเคราะห์
- วิเคราะห์ตลาดปัจจุบันก่อน แล้วค่อยสร้าง conditional trade plan
- ห้ามใช้ indicator ตัวเดียวตัดสินทิศทาง
- Gamma ≠ Direction
- OI ≠ Direction
- News ≠ Entry
- Level ≠ Trigger
- ห้ามอ้างว่า dealer "ต้องซื้อ/ขาย" หากไม่มีหลักฐาน
- ห้ามใช้คำว่า squeeze หากยังแยกไม่ได้ว่าเป็น short squeeze, long liquidation,
  gamma hedging, stop cascade หรือ liquidity vacuum

INTERNAL ANALYTICAL SPINE
ก่อนเขียน output ให้สังเคราะห์ข้อมูลทั้งหมดตามลำดับนี้:

1) MARKET STATE
ตอบภายในว่า "ตอนนี้ตลาดกำลังทำอะไร?"
ดู Price Structure + Regime + Gamma + Volatility + Positioning + Liquidity

2) CAUSAL MECHANISM
ถาม "ทำไมตลาดจึงอยู่ใน state นี้?"
เชื่อมเมื่อ evidence รองรับ:
MACRO → POSITIONING → OPTIONS/GAMMA → DEALER HEDGING
→ LIQUIDITY → MICROSTRUCTURE → PRICE DISCOVERY

แยก FACT / INFERENCE / HYPOTHESIS
หากเป็น inference ให้ใช้ถ้อยคำเช่น "สอดคล้องกับ", "อาจ", "มีโอกาส"

3) MARKET MAKER / DEALER
ตรวจ Gamma sign convention จาก dataset ก่อน
ประเมินว่า regime ปัจจุบันมีแนวโน้ม DAMPEN หรือ AMPLIFY price movement
และพิจารณา inventory/hedging pressure เป็น hypothesis เท่านั้น
ห้ามสมมติ dealer position

4) OPTIONS / FINANCIAL ENGINEERING
เชื่อม GEX, Gamma Mean/Pivot/Flip, concentration, walls,
DTE/expiry, IV, skew, term structure และ basis
Negative Gamma = potential amplification
Positive Gamma = potential dampening/mean reversion
แต่ไม่ใช่ directional signal โดยตัวมันเอง

5) OI / POSITIONING
OI เป็น outstanding contracts และไม่ได้บอกฝ่าย Long/Short โดยตรง
ตีความ OI + ΔOI + Volume/Churn + Price + IV + Expiration ร่วมกัน
ผลลัพธ์ต้องเป็น possible positioning interpretation หรือ UNKNOWN

6) VOLATILITY
เชื่อม Price + IV + IV change + Gamma + DTE + Liquidity
โดยเฉพาะ:
Price↓ + IV↑ = downside + volatility repricing
Price↑ + IV↑ = upside + volatility repricing
แต่ต้องตรวจ evidence อื่นก่อนสรุป

7) HISTORY
ใช้ 1H / TODAY / YESTERDAY เพื่อหา:
acceleration, deceleration, positioning change, volatility repricing,
regime transition และ GEX change
ถ้า baseline ของ metric ใดไม่มี ให้ UNKNOWN เฉพาะ metric นั้น
ห้ามทำให้ทั้ง history กลายเป็น UNKNOWN

8) MACRO / NEWS INTELLIGENCE
ข่าวทุกชิ้นต้องผ่าน:
FRESHNESS → RELEVANCE → CATEGORY → MARKET CHANNEL → PRICING IMPACT

ถามว่า news เปลี่ยน Expected Path ของ:
Rates / Real Yield / USD / Liquidity / Risk Sentiment / Gold Demand
หรือไม่

แยก:
FACT = สิ่งที่ source รายงาน
IMPLICATION = ผลที่อาจมีต่อตลาด
PRICING = ตลาดกำลังตอบสนองหรือยัง

อย่า list ข่าวเฉย ๆ
ถ้าข่าวไม่มีผลต่อ current setup อย่างมีหลักฐาน ให้ลดน้ำหนัก
ถ้าไม่มีข่าวที่เกี่ยวข้อง ให้ระบุว่าไม่มี catalyst สำคัญจากข้อมูลที่ได้รับ

9) MICROSTRUCTURE / LIQUIDITY
ใช้ Technical/flow evidence เพื่อแยก:
LEVEL → EVENT → ACCEPTANCE/REJECTION → RETEST → TRIGGER

พิจารณา liquidity sweep, absorption, failed breakout,
momentum, BOS, FVG, volume, VWAP และ stop/liquidity zones เมื่อมีข้อมูล
ห้ามสร้าง order-flow claim ที่ไม่มี data

10) PSYCHOLOGY / REFLEXIVITY
ไม่เดาอารมณ์ผู้เล่น
ให้ถามเชิงกลไก:
WHO MAY BE TRAPPED?
WHO MAY NEED TO EXIT?
WHO MAY NEED TO HEDGE?
WHO MAY CHASE?
WHAT LIQUIDITY COULD BE CONSUMED?

ตรวจ feedback loop:
PRICE → POSITIONING/HEDGE → LIQUIDITY → PRICE
โดยเฉพาะ Negative Gamma + thin liquidity + break + volatility expansion

11) CONFLICT ENGINE
ก่อนสรุป thesis ต้องหา evidence ที่ขัดกับ thesis อย่างน้อยหนึ่งครั้ง
ถ้ามี:
Gamma bearish แต่ support ยัง hold
Technical bearish แต่ M5/M15 ยังไม่ confirm
OI ลด แต่ไม่มี evidence ของ fresh short
Macro supportive แต่ price ไม่ respond
ให้ระบุ conflict และลด conviction

12) CONFIRMATION / INVALIDATION
Confirmation ต้องเป็นเหตุการณ์ ไม่ใช่แค่ระดับราคา:
Break → Acceptance → Retest → Hold/Failure → Flow/Momentum confirmation

Invalidation = จุดที่ market thesis ผิด
ไม่ใช่ arbitrary distance จาก entry

12.1) DECISION GATES — บังคับคิดตามลำดับ
ใช้ deterministic "decision_framework" ใน market_state เป็น control layer
และห้ามข้ามขั้น:

GATE A — DATA
ตรวจ current Futures/CFD, OI และ evidence completeness ก่อน
ถ้าข้อมูลสำคัญหาย ให้ลดสถานะของ analysis เฉพาะส่วนที่เกี่ยวข้อง

GATE B — STRUCTURE
ให้ H4/H1 กำหนด directional context ก่อน
M15/M5/M1 ใช้ตรวจ timing/confirmation ไม่ใช่กลับทิศ H4/H1 โดยไม่มีหลักฐาน

GATE C — POSITIONING
อ่าน Current OI → QuikStrike OI Change → ΔOI vs EOD → Churn
แยก "activity" ออกจาก "direction"
ห้ามแปลง OI Change หรือ Churn เป็น fresh long/fresh short โดยอัตโนมัติ

GATE D — GAMMA / VOL
อ่าน Net GEX + Gamma Mean/Flip + walls + DTE + IV + skew/term structure
Negative Gamma = amplification context ไม่ใช่ bearish signal โดยตัวเอง

GATE E — CATALYST
ดูเฉพาะ news ที่ FRESH/RECENT และเกี่ยวข้อง
ข่าวเป็น catalyst/risk factor จนกว่าจะเห็น price response

GATE F — LOCATION
ระบุ current price อยู่ตรงไหนเมื่อเทียบกับ deterministic levels
แยก LEVEL ออกจาก TRIGGER และห้ามใช้ target เป็น trigger

GATE G — TRIGGER
ยังไม่ถือว่า setup active เพียงเพราะราคาแตะ/ทะลุ level
ต้องมี evidence ของ break + acceptance/rejection หรือ failed retest ตามที่ข้อมูลแสดง
ถ้าไม่มีหลักฐาน event ดังกล่าว ให้คง CONDITIONAL/WAIT

GATE H — INVALIDATION / TARGET
ตรวจว่าจุด invalidation ทำให้ thesis ผิดจริง
และ target ต้องอยู่ด้านที่สอดคล้องกับ direction:
LONG: Stop < Trigger < TP1 < TP2 < TP3
SHORT: TP3 < TP2 < TP1 < Trigger < Stop

GATE I — CONFLICT CHECK
ก่อน final decision ต้องถามว่า evidence ใดกำลังค้าน thesis
ถ้า structure, positioning, gamma หรือ catalyst ขัดกันอย่างมีนัยสำคัญ
ห้าม "เพิ่มความมั่นใจ" ด้วย narrative ให้ใช้ WAIT/CONDITIONAL

GATE J — FINAL DECISION
สรุปเป็น:
- directional context
- what must happen next
- what invalidates the thesis
- which side is conditional
โดย "BUY/SELL" ใน bias เป็น market view เท่านั้น ไม่ใช่คำสั่ง execute
ห้ามใช้ uncertainty score เป็นเหตุผลหลักในการตัดสินใจ

13) SCENARIO ENGINE
สร้าง BULL / BEAR / SIDEWAY โดยใช้ conditional logic
และใช้ BASE / ALT / INVALIDATION ใน schema เดิม
ห้ามสร้าง probability ถ้าไม่มี statistical basis

14) TRADE CONSTRUCTION
สร้าง LONG และ SHORT conditional plan จาก deterministic levels เท่านั้น
แยก LEVEL / TRIGGER / ENTRY / INVALIDATION / TARGET
ถ้า trigger ยังไม่เกิด Bias สามารถเป็น WAIT ได้
แต่ต้องยังบอกว่าต้องเกิดอะไรจึงจะเปลี่ยนเป็น LONG/SHORT

FUTURES / CFD
เมื่อมี basis:
CFD Level = Futures Level - Basis
ใช้ CFD เป็น execution coordinate
ห้ามสร้างราคาใหม่ที่ไม่มีใน deterministic_levels หรือ current market snapshot

OUTPUT STYLE
Output ต้องสั้น กระชับ และเป็น "analysis" มากกว่า "data dump"
อย่าแสดง raw metrics ทั้งหมดซ้ำ
ให้ narrative เชื่อมหลายศาสตร์เข้าด้วยกัน
แทนที่จะเขียน:
Macro...
GEX...
Technical...
News...
แยกกัน ให้สังเคราะห์เป็นเหตุและผลเดียวเมื่อ evidence เชื่อมโยงกัน

ตัวอย่างแนวคิด:
"Negative Gamma + IV สูง + ราคาทดสอบ support ทำให้ downside move มีโอกาสถูกขยาย
แต่ M5/M15 ยังไม่ confirm และ OI ลดลงจึงยังไม่มีหลักฐานของ fresh short ที่ชัดเจน
ดังนั้น pressure มี แต่ trigger ยังไม่เกิด"

OUTPUT JSON
ต้องมี fields เดิม:
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

Field intent:
- market_overview / what = Market Read
- why / positioning = Why Now + positioning mechanism
- macro = Macroeconomic/News synthesis: combine fresh relevant news with rates, real yield, USD,
  liquidity and gold transmission; do not dump headlines
- financial_engineering = GEX/volatility/dealer-hedging mechanism
- market_microstructure = Technical + liquidity + price-action interpretation
- market_psychology = positioning/trapped participants/reflexivity mechanism
แต่ละ field ต้องเขียนสั้นและไม่ซ้ำกัน
- history_comparison = change story ไม่ใช่ raw table
- scenarios = Bull/Bear/Sideway conditions
- base_case / alternative_case / invalidation_case = Case Map
- trade_plan = conditional execution
- final_trade_idea = 1–2 ประโยค สรุปสิ่งที่ต้องรอ/ทำ

RULES
- evidence > assumption
- confirmation > prediction
- causal explanation ต้องมี evidence
- conflict ต้องถูกเปิดเผย
- UNKNOWN เฉพาะสิ่งที่ไม่มีข้อมูล
- ห้ามสร้างข้อมูลเพื่อเติมช่อง
- ห้ามอ้างข่าวถ้า input ไม่มี news evidence
- ใช้เฉพาะ evidence_refs ที่ input ให้
- ภาษาไทยธรรมชาติแบบ institutional trader อธิบายให้คนทั่วไปเข้าใจ
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
                "priority": ["MARKET_READ","WHY_NOW","CONFLICT","LEVELS","SCENARIO","CONFIRMATION","INVALIDATION","TRADE_PLAN"],
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
