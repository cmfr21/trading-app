const ANALYSIS_TFS = ["15m", "1h", "4h", "1d", "1w"];

const TF_WEIGHTS = {
  "15m": 1,
  "1h": 2,
  "4h": 3,
  "1d": 4,
  "1w": 5
};

function calcEma(values, period) {
  if (!values.length || values.length < period) return null;

  const k = 2 / (period + 1);
  let ema = values.slice(0, period).reduce((a, b) => a + b, 0) / period;

  for (let i = period; i < values.length; i += 1) {
    ema = values[i] * k + ema * (1 - k);
  }

  return ema;
}

function calcRsi(closes, period = 14) {
  if (closes.length < period + 1) return null;

  let gains = 0;
  let losses = 0;

  for (let i = 1; i <= period; i += 1) {
    const diff = closes[i] - closes[i - 1];
    if (diff >= 0) gains += diff;
    else losses += Math.abs(diff);
  }

  let avgGain = gains / period;
  let avgLoss = losses / period;

  for (let i = period + 1; i < closes.length; i += 1) {
    const diff = closes[i] - closes[i - 1];
    const gain = diff > 0 ? diff : 0;
    const loss = diff < 0 ? Math.abs(diff) : 0;

    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;
  }

  if (avgLoss === 0) return 100;

  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}

function calcAtr(candles, period = 14) {
  if (candles.length < period + 1) return null;

  const trs = [];

  for (let i = 1; i < candles.length; i += 1) {
    const high = Number(candles[i].high);
    const low = Number(candles[i].low);
    const prevClose = Number(candles[i - 1].close);

    const tr = Math.max(
      high - low,
      Math.abs(high - prevClose),
      Math.abs(low - prevClose)
    );

    trs.push(tr);
  }

  if (trs.length < period) return null;

  let atr = trs.slice(0, period).reduce((a, b) => a + b, 0) / period;

  for (let i = period; i < trs.length; i += 1) {
    atr = (atr * (period - 1) + trs[i]) / period;
  }

  return atr;
}

function mapToKrakenPair(symbol) {
  const clean = symbol.toUpperCase();

  const directMap = {
    BTCUSDT: "XBTUSDT",
    ETHUSDT: "ETHUSDT",
    SOLUSDT: "SOLUSDT",
    XRPUSDT: "XRPUSDT",
    ADAUSDT: "ADAUSDT",
    DOGEUSDT: "DOGEUSDT",
    LINKUSDT: "LINKUSDT",
    BNBUSDT: "BNBUSDT",
    AVAXUSDT: "AVAXUSDT",
    DOTUSDT: "DOTUSDT",
    LTCUSDT: "LTCUSDT",
    BCHUSDT: "BCHUSDT",
    TRXUSDT: "TRXUSDT",
    UNIUSDT: "UNIUSDT",
    AAVEUSDT: "AAVEUSDT",
    ETCUSDT: "ETCUSDT",
    XLMUSDT: "XLMUSDT",
    ATOMUSDT: "ATOMUSDT"
  };

  if (directMap[clean]) return directMap[clean];

  if (clean.endsWith("USDT")) {
    const base = clean.slice(0, -4);
    return `${base}USDT`;
  }

  if (clean.endsWith("USD")) {
    const base = clean.slice(0, -3);
    return base === "BTC" ? "XBTUSD" : `${base}USD`;
  }

  return clean;
}

function timeframeToKrakenInterval(timeframe) {
  const map = {
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
    "1w": 10080
  };

  return map[timeframe] || 15;
}

async function fetchTicker(krakenPair) {
  const res = await fetch(
    `https://api.kraken.com/0/public/Ticker?pair=${encodeURIComponent(krakenPair)}`,
    { cache: "no-store" }
  );

  if (!res.ok) {
    throw new Error(`Ticker Kraken erreur ${res.status}`);
  }

  const data = await res.json();

  if (!data?.result || typeof data.result !== "object") {
    throw new Error("Réponse ticker Kraken invalide");
  }

  const firstKey = Object.keys(data.result)[0];
  if (!firstKey) {
    throw new Error("Aucun ticker Kraken trouvé");
  }

  return data.result[firstKey];
}

async function fetchKlines(krakenPair, timeframe) {
  const interval = timeframeToKrakenInterval(timeframe);

  const res = await fetch(
    `https://api.kraken.com/0/public/OHLC?pair=${encodeURIComponent(krakenPair)}&interval=${interval}`,
    { cache: "no-store" }
  );

  if (!res.ok) {
    throw new Error(`OHLC Kraken erreur ${res.status}`);
  }

  const data = await res.json();

  if (!data?.result || typeof data.result !== "object") {
    throw new Error("Réponse OHLC Kraken invalide");
  }

  const pairKey = Object.keys(data.result).find((key) => key !== "last");
  if (!pairKey || !Array.isArray(data.result[pairKey])) {
    throw new Error("Aucune bougie Kraken trouvée");
  }

  return data.result[pairKey].map((row) => ({
    openTime: row[0],
    open: Number(row[1]),
    high: Number(row[2]),
    low: Number(row[3]),
    close: Number(row[4]),
    volume: Number(row[6])
  }));
}

function analyzeSingleTimeframe(candles) {
  const closes = candles.map((c) => Number(c.close));
  const ema20 = calcEma(closes, 20);
  const ema50 = calcEma(closes, 50);
  const atr = calcAtr(candles, 14);
  const rsi = calcRsi(closes, 14);
  const price = closes[closes.length - 1];

  if (!price || !ema20 || !ema50 || !atr || !rsi) {
    return {
      direction: "NEUTRAL",
      price: price || 0,
      ema20: ema20 || 0,
      ema50: ema50 || 0,
      atr: atr || 0,
      rsi: rsi || 0,
      score: 0
    };
  }

  const bullish = price > ema20 && ema20 > ema50;
  const bearish = price < ema20 && ema20 < ema50;

  let direction = "NEUTRAL";
  let score = 40;

  if (bullish && rsi >= 50 && rsi <= 70) {
    direction = "LONG";
    score = 70;
    if (rsi >= 54 && rsi <= 64) score += 8;
  } else if (bearish && rsi >= 30 && rsi <= 50) {
    direction = "SHORT";
    score = 70;
    if (rsi >= 36 && rsi <= 46) score += 8;
  } else {
    if (rsi > 70 || rsi < 30) score = 35;
    else score = 45;
  }

  return {
    direction,
    price,
    ema20,
    ema50,
    atr,
    rsi,
    score
  };
}

function buildConfluenceDecision(price, change24h, byTf) {
  const longWeight = ANALYSIS_TFS
    .filter((tf) => byTf[tf]?.direction === "LONG")
    .reduce((sum, tf) => sum + TF_WEIGHTS[tf], 0);

  const shortWeight = ANALYSIS_TFS
    .filter((tf) => byTf[tf]?.direction === "SHORT")
    .reduce((sum, tf) => sum + TF_WEIGHTS[tf], 0);

  const neutralWeight = ANALYSIS_TFS
    .filter((tf) => byTf[tf]?.direction === "NEUTRAL")
    .reduce((sum, tf) => sum + TF_WEIGHTS[tf], 0);

  const h1 = byTf["1h"]?.direction;
  const h4 = byTf["4h"]?.direction;
  const d1 = byTf["1d"]?.direction;
  const w1 = byTf["1w"]?.direction;
  const m15 = byTf["15m"]?.direction;

  const atrRef = byTf["1h"]?.atr || byTf["4h"]?.atr || price * 0.01;

  let decision = "NO_TRADE";
  let reason = "Confluence insuffisante entre les timeframes.";
  let score = Math.max(longWeight, shortWeight) * 6;
  let confidence = Math.max(longWeight, shortWeight) * 5;
  let leverage = "-";
  let entry = price;
  let stopLoss = 0;
  let takeProfit = 0;
  let rr = 0;

  const strongLong =
    h1 === "LONG" &&
    h4 === "LONG" &&
    d1 === "LONG" &&
    w1 !== "SHORT" &&
    m15 !== "SHORT" &&
    longWeight >= 10 &&
    shortWeight <= 1;

  const strongShort =
    h1 === "SHORT" &&
    h4 === "SHORT" &&
    d1 === "SHORT" &&
    w1 !== "LONG" &&
    m15 !== "LONG" &&
    shortWeight >= 10 &&
    longWeight <= 1;

  if (strongLong) {
    decision = "LONG";
    stopLoss = price - atrRef * 1.2;
    takeProfit = price + atrRef * 2.4;
    rr = (takeProfit - entry) / (entry - stopLoss);
    reason =
      "Confluence haussière validée sur 1h, 4h et 1d, avec 15m non contradictoire.";
    score = Math.min(92, 72 + longWeight * 2);
    confidence = Math.min(90, 68 + longWeight * 2);
    leverage = w1 === "LONG" ? "x2" : "x1";
  } else if (strongShort) {
    decision = "SHORT";
    stopLoss = price + atrRef * 1.2;
    takeProfit = price - atrRef * 2.4;
    rr = (entry - takeProfit) / (stopLoss - entry);
    reason =
      "Confluence baissière validée sur 1h, 4h et 1d, avec 15m non contradictoire.";
    score = Math.min(92, 72 + shortWeight * 2);
    confidence = Math.min(90, 68 + shortWeight * 2);
    leverage = w1 === "SHORT" ? "x2" : "x1";
  } else {
    if (longWeight > shortWeight && shortWeight >= 3) {
      reason = "Biais haussier, mais des timeframes importants restent contradictoires.";
    } else if (shortWeight > longWeight && longWeight >= 3) {
      reason = "Biais baissier, mais des timeframes importants restent contradictoires.";
    } else if (neutralWeight >= 6) {
      reason = "Marché trop neutre sur plusieurs horizons.";
    } else if (Math.abs(change24h) < 1) {
      reason = "Variation journalière trop faible pour un setup convaincant.";
    }
  }

  return {
    decision,
    score,
    confidence,
    entry: Number(entry.toFixed(6)),
    stopLoss: Number(stopLoss.toFixed(6)),
    takeProfit: Number(takeProfit.toFixed(6)),
    leverage,
    rr: Number(rr.toFixed(2)),
    reason,
    confluence: {
      longWeight,
      shortWeight,
      neutralWeight
    }
  };
}

export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const symbolsParam = searchParams.get("symbols") || "";

    const symbols = symbolsParam
      .split(",")
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean)
      .slice(0, 20);

    if (!symbols.length) {
      return Response.json(
        { ok: false, error: "Aucun symbole fourni." },
        { status: 400 }
      );
    }

    const items = await Promise.all(
      symbols.map(async (symbol) => {
        try {
          const krakenPair = mapToKrakenPair(symbol);

          const [ticker, tfResults] = await Promise.all([
            fetchTicker(krakenPair),
            Promise.all(
              ANALYSIS_TFS.map(async (tf) => {
                const candles = await fetchKlines(krakenPair, tf);
                return [tf, analyzeSingleTimeframe(candles)];
              })
            )
          ]);

          const byTf = Object.fromEntries(tfResults);

          const price = Number(ticker.c?.[0]);
          const openToday = Number(ticker.o);
          const change24h =
            openToday && price ? ((price - openToday) / openToday) * 100 : 0;

          const confluenceDecision = buildConfluenceDecision(price, change24h, byTf);

          return {
            symbol,
            sourcePair: krakenPair,
            ok: true,
            price,
            change24h,
            high24h: Number(ticker.h?.[1] || 0),
            low24h: Number(ticker.l?.[1] || 0),
            volume: Number(ticker.v?.[1] || 0),
            timeframes: byTf,
            indicators: {
              ema20: byTf["1h"]?.ema20 || 0,
              ema50: byTf["1h"]?.ema50 || 0,
              atr: byTf["1h"]?.atr || 0,
              rsi: byTf["1h"]?.rsi || 0
            },
            ...confluenceDecision
          };
        } catch (error) {
          return {
            symbol,
            ok: false,
            error: error?.message || "Erreur inconnue"
          };
        }
      })
    );

    return Response.json({
      ok: true,
      updatedAt: Date.now(),
      analysisTimeframes: ANALYSIS_TFS,
      items
    });
  } catch (error) {
    return Response.json(
      {
        ok: false,
        error: "Erreur serveur market.",
        details: error?.message || "unknown"
      },
      { status: 500 }
    );
  }
}
