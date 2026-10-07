import { NextResponse } from "next/server";
import { createClient } from "@supabase/supabase-js";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function num(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function parseJson(value: unknown): Record<string, any> {
  if (value && typeof value === "object") return value as Record<string, any>;
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch {
      return {};
    }
  }
  return {};
}

function clean(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(clean);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([k, v]) => [k, clean(v)])
    );
  }
  return value;
}

function routeFromLegacy(
  tradePlan: Record<string, any>,
  prefix: string,
  title: string,
  route: string,
  side: string,
  strategy: string,
  action: string,
): Record<string, any> {
  const trigger = num(tradePlan[prefix + "_trigger"]);
  const stop = num(tradePlan[prefix + "_stop"]);
  const targets = [1, 2, 3, 4, 5]
    .map((i) => num(tradePlan[prefix + "_tp" + i]))
    .filter((v): v is number => v !== null);
  return {
    route,
    title,
    side,
    strategy,
    state: tradePlan[prefix + "_state"] ?? (trigger !== null && stop !== null ? "ARMED" : "DATA_INSUFFICIENT"),
    trigger,
    entry_reference: trigger,
    stop,
    targets,
    action,
    risk: {},
    execution_authority: "NONE",
    legacy_fallback: true,
  };
}

function unavailableRoute(
  title: string,
  route: string,
  side: string,
  strategy: string,
  action: string,
): Record<string, any> {
  return {
    route,
    title,
    side,
    strategy,
    state: "DATA_INSUFFICIENT",
    trigger: null,
    entry_reference: null,
    stop: null,
    targets: [],
    action,
    risk: { status: "NO_TRADE", reason: "WAIT_FOR_NEW_DETERMINISTIC_SNAPSHOT" },
    execution_authority: "NONE",
    legacy_fallback: true,
  };
}

export async function GET() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;

  if (!url || !key) {
    return NextResponse.json(
      { status: "ERROR", error: "SUPABASE_SERVER_ENV_MISSING" },
      { status: 500 }
    );
  }

  const supabase = createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  const query = await supabase
    .from("options_flow_snapshots")
    .select([
      "id",
      "captured_at",
      "contract",
      "dte",
      "future_price",
      "spot_price",
      "basis_diff",
      "cfd_price",
      "raw_series",
      "technical_context",
      "ai_summary",
      "gamma_table_url",
      "gamma_table_full_url",
    ].join(","))
    .order("captured_at", { ascending: false })
    .limit(1);

  const rows = query.data as Array<Record<string, any>> | null;
  const error = query.error as { message: string } | null;

  if (error) {
    return NextResponse.json({ status: "ERROR", error: error.message }, { status: 500 });
  }

  const row = rows?.[0];
  if (!row) {
    return NextResponse.json({ status: "NO_DATA" }, { status: 200 });
  }

  const raw = parseJson(row.raw_series);
  const ai = parseJson(row.ai_summary);
  const technical = parseJson(row.technical_context);
  const marketMap = parseJson(ai.market_map);
  const tradePlan = parseJson(ai.trade_plan);
  const rawExecution = parseJson(tradePlan.execution_plan);

  // Older DB snapshots may predate the four-route engine. Normalize them at
  // the API boundary so the customer UI never loses a route silently.
  const execution = { ...rawExecution };
  if (!execution.long_reclaim) {
    execution.long_reclaim = execution.long ?? routeFromLegacy(
      tradePlan, "long", "BUY — เบรกต้าน", "BUY_BREAKOUT", "LONG",
      "BREAKOUT_RETEST", "เบรกและยืนเหนือโซน → รีเทสต์ไม่หลุด → BUY"
    );
  }
  if (!execution.long_support) {
    execution.long_support = unavailableRoute(
      "BUY — รับด้านล่าง", "BUY_SUPPORT", "LONG_SUPPORT",
      "REVERSAL", "แตะโซนรับ → reaction → M5 BOS ขึ้น → BUY"
    );
  }
  if (!execution.short_rejection) {
    execution.short_rejection = execution.short ?? routeFromLegacy(
      tradePlan, "short", "SELL — ต้านไม่ผ่าน", "SELL_REJECTION", "SHORT",
      "REVERSAL / FAILED_RETEST", "เด้งกลับต้าน → rejection → M5 BOS ลง → SELL"
    );
  }
  if (!execution.short_breakdown) {
    execution.short_breakdown = unavailableRoute(
      "SELL — หลุดแนวรับ", "SELL_BREAKDOWN", "SHORT",
      "BREAKOUT_RETEST", "หลุดแนวรับ → รีเทสต์ไม่ผ่าน → SELL"
    );
  }

  if (!execution.preferred_setup) {
    const bias = String(ai.bias ?? tradePlan.direction ?? "WAIT").toUpperCase();
    execution.preferred_setup =
      bias === "SELL" ? execution.short_rejection?.route :
      bias === "BUY" ? execution.long_reclaim?.route : null;
    execution.preferred_action =
      bias === "SELL" ? execution.short_rejection?.action :
      bias === "BUY" ? execution.long_reclaim?.action :
      "รอให้เกิด Action ที่โซน";
  }

  const gamma = parseJson(raw.multi_expiry_gamma);
  const gammaZones = parseJson(raw.multi_expiry_gamma_zones);
  const primaryRows = Array.isArray(raw.strike_rows) ? raw.strike_rows : [];

  const matrix = Array.isArray(gamma.matrix)
    ? gamma.matrix.map((r: Record<string, unknown>) => {
        const out: Record<string, unknown> = { strike: num(r.strike) };
        for (const col of Array.isArray(gamma.columns) ? gamma.columns : []) {
          const code = String(col?.code ?? "");
          if (code) out[code] = num(r[code]);
        }
        return out;
      })
    : [];

  const primaryGamma = primaryRows
    .filter((r: Record<string, unknown>) => num(r.strike) !== null)
    .map((r: Record<string, unknown>) => ({
      strike: num(r.strike),
      call_oi: num(r.call_open_interest ?? r.call_oi),
      put_oi: num(r.put_open_interest ?? r.put_oi),
      call_gex: num(r.call_gex),
      put_gex: num(r.put_gex),
      net_gex: num(r.net_gex),
      call_iv: num(r.call_iv),
      put_iv: num(r.put_iv),
    }))
    .sort((a: any, b: any) => (b.strike ?? 0) - (a.strike ?? 0));

  const confirmation = parseJson(technical.confirmation);

  return NextResponse.json(clean({
    status: "OK",
    observedAt: row.captured_at,
    snapshotId: row.id,
    market: {
      contract: row.contract,
      dte: num(row.dte),
      futures: num(row.future_price),
      spot: num(row.spot_price),
      basis: num(row.basis_diff),
      cfd: num(row.cfd_price),
    },
    regime: {
      bias: ai.bias ?? tradePlan.direction ?? "WAIT",
      status: ai.analysis_status ?? tradePlan.status ?? "UNKNOWN",
      marketRegime: ai.market_regime ?? tradePlan.market_condition ?? "UNKNOWN",
      overview: ai.market_overview ?? "",
      what: ai.what ?? "",
      why: ai.why ?? "",
      financialEngineering: ai.financial_engineering ?? "",
      macro: ai.macro ?? "",
      microstructure: ai.market_microstructure ?? "",
    },
    technical: {
      htf: confirmation.bias ?? confirmation.htf_aligned ?? "UNKNOWN",
      m15: technical.m15 ?? {},
      m5: technical.m5 ?? {},
      confirmation,
    },
    levels: {
      r1: num(marketMap.R1),
      r2: num(marketMap.R2),
      r3: num(marketMap.R3),
      r4: num(marketMap.R4),
      r5: num(marketMap.R5),
      s1: num(marketMap.S1),
      s2: num(marketMap.S2),
      s3: num(marketMap.S3),
      s4: num(marketMap.S4),
      s5: num(marketMap.S5),
      pivot: num(marketMap.pivot),
      callWall: num(marketMap.call_wall),
      putWall: num(marketMap.put_wall),
      longTrigger: num(marketMap.long_trigger),
      shortTrigger: num(marketMap.short_trigger),
      longSupportTrigger: num(marketMap.long_support_trigger),
      longReclaimTrigger: num(marketMap.long_reclaim_trigger),
      shortRejectionTrigger: num(marketMap.short_rejection_trigger),
      shortBreakdownTrigger: num(marketMap.short_breakdown_trigger),
      longInvalidation: num(marketMap.long_invalidation),
      longSupportInvalidation: num(marketMap.long_support_invalidation),
      shortInvalidation: num(marketMap.short_invalidation),
      location: marketMap.location_state ?? "UNKNOWN",
    },
    trade: {
      status: execution.state ?? tradePlan.status ?? "UNKNOWN",
      direction: tradePlan.direction ?? "WAIT",
      preferredSetup: execution.preferred_setup ?? null,
      preferredAction: execution.preferred_action ?? null,
      long: execution.long ?? null,
      longSupport: execution.long_support ?? null,
      short: execution.short ?? null,
      buyBreakout: execution.long_reclaim ?? null,
      buySupport: execution.long_support ?? null,
      sellRejection: execution.short_rejection ?? null,
      sellBreakdown: execution.short_breakdown ?? null,
    },
    gamma: {
      status: gamma.status ?? "UNKNOWN",
      currentPrice: num(gamma.current_price),
      columns: Array.isArray(gamma.columns) ? gamma.columns : [],
      displayColumns: Array.isArray(gamma.display_columns) ? gamma.display_columns : [],
      matrix,
      primary: primaryGamma,
      zones: gammaZones,
    },
    media: {
      gammaTableUrl: row.gamma_table_url ?? null,
      gammaTableFullUrl: row.gamma_table_full_url ?? null,
    },
  }));
}
