export type ApiEnvelope<T = unknown> = {
  symbol: string;
  as_of: string | null;
  data_age_seconds: number | null;
  data_age: number | null;
  data_quality: number;
  data_status: string;
  source: string;
  dataset_version: string;
  calculation_version: string;
  data: T;
};

async function getInternal<T>(path: string): Promise<ApiEnvelope<T> | null> {
  if (process.env.WEB_TERMINAL_ENABLED !== "true") return null;
  const base = process.env.CANONICAL_MARKET_STATE_URL;
  if (!base) return null;
  const headers: HeadersInit = { Accept: "application/json" };
  if (process.env.CANONICAL_MARKET_STATE_TOKEN) {
    headers.Authorization = "Bearer " + process.env.CANONICAL_MARKET_STATE_TOKEN;
  }
  try {
    const response = await fetch(
      base.replace(/\/$/, "") + path,
      { headers, cache: "no-store" }
    );
    if (!response.ok) return null;
    return (await response.json()) as ApiEnvelope<T>;
  } catch {
    return null;
  }
}

export type MarketStateData = {
  market_state: {
    symbol: string;
    price: number | null;
    oi: number | null;
    oi_change: number | null;
    gex: number | null;
    dex: number | null;
    iv: number | null;
    realized_vol: number | null;
    gamma_flip: number | null;
    call_wall: number | null;
    put_wall: number | null;
    positioning_regime: string;
    volatility_regime: string;
    data_quality: number;
    data_age_seconds: number | null;
    data_status: string;
    dataset_version: string;
    calculation_version: string;
    sign_convention?: string | null;
    gamma_source?: string | null;
    assumptions: string[];
    evidence: string[];
  };
  positioning: Record<string, unknown>;
};

export async function getTerminalMarket(symbol = "GC") {
  return getInternal<MarketStateData>("/market/" + encodeURIComponent(symbol));
}

export async function getTerminalPositioning(symbol = "GC") {
  return getInternal<Record<string, unknown>>(
    "/market/" + encodeURIComponent(symbol) + "/positioning"
  );
}

export async function getTerminalOi(symbol = "GC") {
  return getInternal<Record<string, unknown>>(
    "/market/" + encodeURIComponent(symbol) + "/oi"
  );
}

export async function getTerminalGex(symbol = "GC") {
  return getInternal<Record<string, unknown>>(
    "/market/" + encodeURIComponent(symbol) + "/gex"
  );
}

export async function getTerminalExpiry(symbol = "GC") {
  return getInternal<Record<string, unknown>>(
    "/market/" + encodeURIComponent(symbol) + "/expiry"
  );
}

export async function getTerminalNews(symbol = "GC") {
  return getInternal<unknown>("/market/" + encodeURIComponent(symbol) + "/news");
}

export async function getTerminalAnalysis(symbol = "GC") {
  return getInternal<unknown>("/market/" + encodeURIComponent(symbol) + "/analysis");
}

export async function getTerminalPlan(symbol = "GC") {
  return getInternal<unknown>("/market/" + encodeURIComponent(symbol) + "/plan");
}
