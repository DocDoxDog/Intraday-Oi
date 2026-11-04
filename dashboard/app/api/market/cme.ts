// Pure payload builder for the "CME Live" section. No I/O.
type Obj = Record<string, any>;

export const num = (v: unknown): number | null => {
  if (v === null || v === undefined || v === "") return null;
  const x = Number(v);
  return Number.isFinite(x) ? x : null;
};

const TRADING_HOURS_PER_DAY = 23;
const TRADING_DAYS_PER_YEAR = 252;

export function horizonSigma(price: number | null, ivPct: number | null, hours: number): number | null {
  if (price === null || ivPct === null || price <= 0 || ivPct < 0) return null;
  return price * (ivPct / 100) * Math.sqrt(hours / (TRADING_HOURS_PER_DAY * TRADING_DAYS_PER_YEAR));
}

export function maxPain(rows: { strike: number; oiCall: number | null; oiPut: number | null }[]): number | null {
  const pts = rows.filter((r) => r.oiCall !== null && r.oiPut !== null);
  if (pts.length < 3) return null;
  let best: { k: number; v: number } | null = null;
  for (const c of pts) {
    let total = 0;
    for (const r of pts) {
      total += (r.oiCall as number) * Math.max(c.strike - r.strike, 0) + (r.oiPut as number) * Math.max(r.strike - c.strike, 0);
    }
    if (best === null || total < best.v) best = { k: c.strike, v: total };
  }
  return best ? best.k : null;
}

function rank(rows: { strike: number; v: number | null }[], count: number) {
  return rows.filter((r) => r.v !== null && (r.v as number) > 0)
    .sort((a, b) => (b.v as number) - (a.v as number))
    .slice(0, count)
    .map((r, i) => ({ rank: i + 1, strike: r.strike, oi: r.v as number }));
}

export function buildCme(raw: Obj, row: Obj): Obj {
  const basis = num(row.basis_diff);
  const futures = num(row.future_price);
  const cfd = num(row.cfd_price);
  const dte = num(row.dte);
  const ms: Obj = raw.market_state ?? {};
  const vol: Obj = ms.volatility ?? {};
  const qv: Obj = (ms.quant_metrics ?? {}).volatility ?? {};
  const gexRaw: Obj = raw.gex ?? {};

  const rows = (Array.isArray(raw.strike_rows) ? raw.strike_rows : [])
    .map((r: Obj) => {
      const strike = num(r.strike);
      if (strike === null) return null;
      return {
        strike,
        strikeCfd: num(r.strike_cfd) ?? (basis !== null ? strike - basis : null),
        oiCall: num(r.oiCall ?? r.call_open_interest ?? r.call_oi),
        oiPut: num(r.oiPut ?? r.put_open_interest ?? r.put_oi),
        vol: num(r.vol),
        callDelta: num(r.callDelta),
        putDelta: num(r.putDelta),
        netGex: num(r.net_gex),
      };
    })
    .filter(Boolean)
    .sort((a: any, b: any) => a.strike - b.strike) as Obj[];

  const sum = (key: "oiCall" | "oiPut") => {
    const v = rows.map((r) => r[key]).filter((x): x is number => typeof x === "number");
    return v.length ? v.reduce((a, b) => a + b, 0) : null;
  };
  const oiCall = sum("oiCall");
  const oiPut = sum("oiPut");

  const ivAtm = num(vol.atm_iv) ?? num(qv.atm_iv);
  const iv = num(vol.iv) ?? ivAtm;
  const sigma = (h: number) => num((qv.horizon_sigma_points ?? {})[h === 1 ? "1h" : h === 0.25 ? "15m" : h === 4 ? "4h" : "1d"]);
  const ref = cfd ?? futures;
  const s1d = sigma(23) ?? horizonSigma(ref, iv, TRADING_HOURS_PER_DAY);
  const s1h = sigma(1) ?? horizonSigma(ref, iv, 1);
  const s15 = sigma(0.25) ?? horizonSigma(ref, iv, 0.25);
  const s4h = sigma(4) ?? horizonSigma(ref, iv, 4);
  const sWeek = s1d !== null ? s1d * Math.sqrt(5) : null;

  let expected: Obj[] = (Array.isArray(raw.expected_ranges) ? raw.expected_ranges : [])
    .map((x: Obj) => ({
      title: x.title ?? null,
      lower: num(x.lower),
      upper: num(x.upper),
      lowerCfd: num(x.lower_cfd),
      upperCfd: num(x.upper_cfd),
      percent: num(x.percent),
    }))
    .filter((x: Obj) => x.lower !== null && x.upper !== null);
  let expectedSource = "source";
  if (!expected.length && futures !== null && iv !== null && dte !== null && dte > 0) {
    const one = futures * (iv / 100) * Math.sqrt(dte / 365);
    expected = [1, 2, 3].map((k) => ({
      title: k + " SD",
      lower: futures - k * one,
      upper: futures + k * one,
      lowerCfd: basis !== null ? futures - k * one - basis : null,
      upperCfd: basis !== null ? futures + k * one - basis : null,
      percent: null,
    }));
    expectedSource = "atm_iv_black76_calendar_dte";
  }

  const walls = {
    calls: rank(rows.map((r) => ({ strike: r.strike, v: r.oiCall })), 3),
    puts: rank(rows.map((r) => ({ strike: r.strike, v: r.oiPut })), 3),
  };

  let concentration: Obj | null = null;
  if (sWeek !== null && futures !== null && ref !== null) {
    const lo = futures - sWeek;
    const hi = futures + sWeek;
    let inside = 0;
    let total = 0;
    for (const r of rows) {
      if (r.oiCall === null || r.oiPut === null) continue;
      const t = r.oiCall + r.oiPut;
      total += t;
      if (r.strike >= lo && r.strike <= hi) inside += t;
    }
    if (total > 0) concentration = { pct: (inside / total) * 100, low: lo, high: hi };
  }

  const profile: Obj = gexRaw.gamma_profile ?? {};
  const gammaBars = rows.filter((r) => r.netGex !== null).map((r) => ({ strike: r.strike, strikeCfd: r.strikeCfd, v: r.netGex }));

  return {
    basis, dte, futures, cfd,
    iv: {
      atm: ivAtm,
      used: iv,
      source: vol.iv_source ?? "unknown",
      meanChain: num(vol.mean_chain_iv),
      skew25: num(vol.skew_25d ?? qv.skew_25d_put_minus_call),
    },
    ivTerm: Array.isArray(vol.iv_term_structure)
      ? vol.iv_term_structure.map((t: Obj) => ({ code: t.code ?? null, dte: num(t.dte), iv: num(t.iv) }))
      : [],
    sigma: { m15: s15, h1: s1h, h4: s4h, d1: s1d, week: sWeek },
    realized: {
      rv: num((qv.realized_vol ?? {}).close_to_close_pct),
      parkinson: num((qv.realized_vol ?? {}).parkinson_pct),
      status: (qv.realized_vol ?? {}).status ?? "UNKNOWN",
      vrp: num(qv.variance_risk_premium_pts),
    },
    totals: { call: oiCall, put: oiPut, ratioPutCall: oiCall && oiPut !== null ? oiPut / oiCall : null },
    maxPain: maxPain(rows as any),
    expected, expectedSource, walls, concentration, rows,
    gamma: {
      net: num(gexRaw.net_gex),
      flip: num(gexRaw.gamma_flip),
      flipMethod: gexRaw.gamma_flip_method ?? null,
      callWall: num(gexRaw.call_wall),
      putWall: num(gexRaw.put_wall),
      bars: gammaBars,
      scenarios: profile.scenarios ?? {},
      signConsensus: typeof profile.sign_consensus === "boolean" ? profile.sign_consensus : null,
      curve: Array.isArray(profile.curve) ? profile.curve : [],
      profileStatus: profile.status ?? "unavailable",
    },
    ivRank: null,
  };
}