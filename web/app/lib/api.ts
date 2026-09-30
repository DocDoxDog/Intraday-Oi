export type MarketStatePayload = {
  symbol: string;
  as_of: string;
  data_age_seconds: number | null;
  data_quality: number;
  data_status: string;
  dataset_version: string;
  calculation_version: string;
  data: { market_state: {
    symbol: string; price: number | null; oi: number | null; oi_change: number | null; gex: number | null; dex: number | null;
    iv: number | null; realized_vol: number | null; gamma_flip: number | null; call_wall: number | null; put_wall: number | null;
    positioning_regime: string; volatility_regime: string; data_quality: number; data_age_seconds: number | null;
    data_status: string; dataset_version: string; calculation_version: string; sign_convention?: string | null; gamma_source?: string | null;
    assumptions: string[]; evidence: string[];
  }; positioning?: Record<string, unknown>; };
};

export async function getMarketState(symbol = "GC"): Promise<MarketStatePayload | null> {
  const base = process.env.CANONICAL_MARKET_STATE_URL;
  if (!base) return null;
  const url = base.replace(/\/$/, "") + "/market/" + encodeURIComponent(symbol);
  const headers: HeadersInit = { Accept: "application/json" };
  if (process.env.CANONICAL_MARKET_STATE_TOKEN) {
    headers.Authorization = "Bearer " + process.env.CANONICAL_MARKET_STATE_TOKEN;
  }
  try {
    const response = await fetch(url, { headers, cache: "no-store" });
    if (!response.ok) return null;
    return await response.json() as MarketStatePayload;
  } catch { return null; }
}