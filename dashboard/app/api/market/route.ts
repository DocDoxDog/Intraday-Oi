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
  const execution = parseJson(tradePlan.execution_plan);

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
      s1: num(marketMap.S1),
      s2: num(marketMap.S2),
      s3: num(marketMap.S3),
      pivot: num(marketMap.pivot),
      longTrigger: num(marketMap.long_trigger),
      shortTrigger: num(marketMap.short_trigger),
      longSupportTrigger: num(marketMap.long_support_trigger),
      longInvalidation: num(marketMap.long_invalidation),
      longSupportInvalidation: num(marketMap.long_support_invalidation),
      shortInvalidation: num(marketMap.short_invalidation),
      location: marketMap.location_state ?? "UNKNOWN",
    },
    trade: {
      status: tradePlan.status ?? execution.state ?? "UNKNOWN",
      direction: tradePlan.direction ?? "WAIT",
      long: execution.long ?? null,
      longSupport: execution.long_support ?? null,
      short: execution.short ?? null,
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
