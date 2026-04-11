const ANALYSIS_TFS = ["15m", "1h", "4h", "1d", "1w"];

const STYLE_CONFIG = {
  short: {
    label: "Court terme",
    allowedPairs: [
      { tradeTf: "15m", contextTf: "1h", label: "Scalp / intraday" },
      { tradeTf: "1h", contextTf: "4h", label: "Intraday / swing court" }
    ]
  },
  medium: {
    label: "Moyen terme",
    allowedPairs: [
      { tradeTf: "1h", contextTf: "4h", label: "Intraday / swing court" },
      { tradeTf: "4h", contextTf: "1d", label: "Swing" }
    ]
  },
  long: {
    label: "Long terme",
    allowedPairs: [
      { tradeTf: "4h", contextTf: "1d", label: "Swing" },
      { tradeTf: "1d", contextTf: "1w", label: "Position" }
    ]
  }
};

const RISK_CONFIG = {
  conservative: {
    rrMin: 2.0,
    stopAtr: 0.9,
    tpAtr: 2.4,
    liquidationBuffer: 3.5
  },
  moderate: {
    rrMin: 1.6,
    stopAtr: 1.15,
    tpAtr: 2.8,
    liquidationBuffer: 2.5
  },
  aggressive: {
    rrMin: 1.25,
    stopAtr: 1.45,
    tpAtr: 3.1,
    liquidationBuffer: 1.8
  }
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

function highestHigh(candles, period, endIndex) {
  const start = Math.max(0, endIndex - period + 1);
  let max = -Infinity;
  for (let i = start; i <= endIndex; i += 1) {
    if (candles[i].high > max) max = candles[i].high;
  }
  return max;
}

function lowestLow(candles, period, endIndex) {
  const start = Math.max(0, endIndex - period + 1);
  let min = Infinity;
  for (let i = start; i <= endIndex; i += 1) {
    if (candles[i].low < min) min = candles[i].low;
  }
  return min;
}

function calcIchimoku(candles) {
  if (!candles || candles.length < 52) return null;

  const endIndex = candles.length - 1;

  const tenkanHigh = highestHigh(candles, 9, endIndex);
  const tenkanLow = lowestLow(candles, 9, endIndex);
  const tenkan = (tenkanHigh + tenkanLow) / 2;

  const kijunHigh = highestHigh(candles, 26, endIndex);
  const kijunLow = lowestLow(candles, 26, endIndex);
  const kijun = (kijunHigh + kijunLow) / 2;

  const spanBHigh = highestHigh(candles, 52, endIndex);
  const spanBLow = lowestLow(candles, 52, endIndex);
  const senkouB = (spanBHigh + spanBLow) / 2;

  const senkouA = (tenkan + kijun) / 2;

  return {
    tenkan,
    kijun,
    senkouA,
    senkouB,
    cloudTop: Math.max(senkouA, senkouB),
    cloudBottom: Math.min(senkouA, senkouB)
  };
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

  const rows = data.result[pairKey].map((row) => ({
    openTime: row[0],
    open: Number(row[1]),
    high: Number(row[2]),
    low: Number(row[3]),
    close: Number(row[4]),
    volume: Number(row[6])
  }));

  return rows.length > 1 ? rows.slice(0, -1) : rows;
}

function analyzeSingleTimeframe(candles) {
  const closes = candles.map((c) => Number(c.close));
  const ema20 = calcEma(closes, 20);
  const ema50 = calcEma(closes, 50);
  const atr = calcAtr(candles, 14);
  const rsi = calcRsi(closes, 14);
  const ichimoku = calcIchimoku(candles);
  const price = closes[closes.length - 1];

  if (!price || !ema20 || !ema50 || !atr) {
    return {
      direction: "NEUTRAL",
      price: price || 0,
      ema20: ema20 || 0,
      ema50: ema50 || 0,
      atr: atr || 0,
      rsi: rsi || 0,
      ichimoku: null,
      score: 0
    };
  }

  const bullishEma = price > ema20 && ema20 > ema50;
  const bearishEma = price < ema20 && ema20 < ema50;

  const bullishIchimoku =
    ichimoku &&
    price > ichimoku.cloudTop &&
    ichimoku.tenkan >= ichimoku.kijun;

  const bearishIchimoku =
    ichimoku &&
    price < ichimoku.cloudBottom &&
    ichimoku.tenkan <= ichimoku.kijun;

  let longVotes = 0;
  let shortVotes = 0;

  if (bullishEma) longVotes += 1;
  if (bearishEma) shortVotes += 1;

  if (bullishIchimoku) longVotes += 1;
  if (bearishIchimoku) shortVotes += 1;

  if (rsi >= 48 && rsi <= 72) longVotes += 1;
  if (rsi >= 28 && rsi <= 52) shortVotes += 1;

  let direction = "NEUTRAL";
  if (longVotes >= 2 && shortVotes === 0) direction = "LONG";
  else if (shortVotes >= 2 && longVotes === 0) direction = "SHORT";

  const score = Math.min(90, 45 + Math.max(longVotes, shortVotes) * 14);

  return {
    direction,
    price,
    ema20,
    ema50,
    atr,
    rsi,
    ichimoku,
    score
  };
}

function estimateLiquidationPrice(side, entry, leverage) {
  if (!entry || !leverage || leverage <= 0) return 0;
  if (side === "LONG") return entry * (1 - 1 / leverage);
  return entry * (1 + 1 / leverage);
}

function maxLeverageFromStop(side, entry, stopLoss, riskMode) {
  if (!entry || !stopLoss) return 0;

  const stopDistancePct =
    side === "LONG"
      ? (entry - stopLoss) / entry
      : (stopLoss - entry) / entry;

  if (stopDistancePct <= 0) return 0;

  const buffer = RISK_CONFIG[riskMode].liquidationBuffer;
  const leverage = 1 / (stopDistancePct * buffer);

  return Math.max(1, Math.min(10, leverage));
}

function buildSetupFromPair(pair, byTf, currentPrice, riskMode) {
  const trade = byTf[pair.tradeTf];
  const context = byTf[pair.contextTf];
  const risk = RISK_CONFIG[riskMode];

  if (!trade || !context) return null;
  if (trade.direction === "NEUTRAL" || context.direction === "NEUTRAL") return null;
  if (trade.direction !== context.direction) return null;

  const side = trade.direction;
  const tradeAtr = trade.atr || currentPrice * 0.01;
  const tradeIchi = trade.ichimoku;
  const contextIchi = context.ichimoku;

  let entry = currentPrice;
  let entryMin = currentPrice;
  let entryMax = currentPrice;
  let stopLoss = 0;
  let takeProfit = 0;

  if (side === "LONG") {
    const zoneCandidates = [
      trade.ema20,
      tradeIchi?.kijun,
      context.ema20,
      currentPrice - tradeAtr * 0.35
    ].filter((v) => Number.isFinite(v));

    entryMin = Math.min(...zoneCandidates);
    entryMax = Math.max(
      Math.min(currentPrice, trade.ema20 || currentPrice),
      entryMin
    );

    const stopCandidates = [
      tradeIchi?.cloudBottom,
      contextIchi?.cloudBottom,
      tradeIchi?.kijun ? tradeIchi.kijun - tradeAtr * 0.25 : null,
      currentPrice - tradeAtr * risk.stopAtr
    ].filter((v) => Number.isFinite(v));

    stopLoss = Math.min(...stopCandidates);
    takeProfit = currentPrice + tradeAtr * risk.tpAtr;
  } else {
    const zoneCandidates = [
      trade.ema20,
      tradeIchi?.kijun,
      context.ema20,
      currentPrice + tradeAtr * 0.35
    ].filter((v) => Number.isFinite(v));

    entryMin = Math.min(
      Math.max(currentPrice, trade.ema20 || currentPrice),
      Math.max(...zoneCandidates)
    );
    entryMax = Math.max(...zoneCandidates);

    const stopCandidates = [
      tradeIchi?.cloudTop,
      contextIchi?.cloudTop,
      tradeIchi?.kijun ? tradeIchi.kijun + tradeAtr * 0.25 : null,
      currentPrice + tradeAtr * risk.stopAtr
    ].filter((v) => Number.isFinite(v));

    stopLoss = Math.max(...stopCandidates);
    takeProfit = currentPrice - tradeAtr * risk.tpAtr;
  }

  if (!Number.isFinite(entryMin) || !Number.isFinite(entryMax)) return null;
  if (!Number.isFinite(stopLoss) || !Number.isFinite(takeProfit)) return null;
  if (entryMin === entryMax) {
    if (side === "LONG") entryMin = entryMin * 0.9975;
    else entryMax = entryMax * 1.0025;
  }

  const rr =
    side === "LONG"
      ? (takeProfit - entry) / (entry - stopLoss)
      : (entry - takeProfit) / (stopLoss - entry);

  if (!Number.isFinite(rr) || rr < risk.rrMin) return null;

  const leverageMax = maxLeverageFromStop(side, entry, stopLoss, riskMode);
  const leverage = Math.max(1, Math.floor(leverageMax));
  const liquidationPrice = estimateLiquidationPrice(side, entry, leverage);

  if (!liquidationPrice) return null;

  const scoreBase = Math.round((trade.score + context.score) / 2);
  const score = Math.min(
    96,
    scoreBase +
      (trade.ichimoku ? 4 : 0) +
      (context.ichimoku ? 4 : 0) +
      (rr >= 2 ? 4 : 0)
  );

  const reason =
    side === "LONG"
      ? `${pair.tradeTf} et ${pair.contextTf} concordent à l'achat avec Ichimoku + EMA + RSI + ATR.`
      : `${pair.tradeTf} et ${pair.contextTf} concordent à la vente avec Ichimoku + EMA + RSI + ATR.`;

  return {
    setupId: `${pair.tradeTf}-${pair.contextTf}-${side}-${riskMode}`,
    label: pair.label,
    tradeTf: pair.tradeTf,
    contextTf: pair.contextTf,
    decision: side,
    score,
    confidence: Math.min(94, score - 2),
    entry: Number(entry.toFixed(6)),
    entryMin: Number(entryMin.toFixed(6)),
    entryMax: Number(entryMax.toFixed(6)),
    stopLoss: Number(stopLoss.toFixed(6)),
    takeProfit: Number(takeProfit.toFixed(6)),
    rr: Number(rr.toFixed(2)),
    leverage: `x${leverage}`,
    leverageValue: leverage,
    liquidationPrice: Number(liquidationPrice.toFixed(6)),
    reason,
    riskMode
  };
}

function buildAssetDecision(price, change24h, byTf, tradeStyle, riskMode) {
  const style = STYLE_CONFIG[tradeStyle] || STYLE_CONFIG.medium;

  const setups = style.allowedPairs
    .map((pair) => buildSetupFromPair(pair, byTf, price, riskMode))
    .filter(Boolean)
    .sort((a, b) => b.score - a.score || b.rr - a.rr);

  if (!setups.length) {
    return {
      decision: "NO_TRADE",
      score: 42,
      confidence: 40,
      entry: 0,
      entryMin: 0,
      entryMax: 0,
      stopLoss: 0,
      takeProfit: 0,
      leverage: "-",
      leverageValue: 0,
      liquidationPrice: 0,
      rr: 0,
      reason:
        Math.abs(change24h) < 1
          ? "Pas de trade : marché trop neutre pour le style choisi."
          : "Pas de trade : aucun setup cohérent sur les timeframes sélectionnés.",
      bestSetup: null,
      setups: []
    };
  }

  const best = setups[0];

  return {
    decision: best.decision,
    score: best.score,
    confidence: best.confidence,
    entry: best.entry,
    entryMin: best.entryMin,
    entryMax: best.entryMax,
    stopLoss: best.stopLoss,
    takeProfit: best.takeProfit,
    leverage: best.leverage,
    leverageValue: best.leverageValue,
    liquidationPrice: best.liquidationPrice,
    rr: best.rr,
    reason: best.reason,
    bestSetup: best,
    setups
  };
}

export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const symbolsParam = searchParams.get("symbols") || "";
    const tradeStyle = searchParams.get("tradeStyle") || "medium";
    const riskMode = searchParams.get("riskMode") || "moderate";

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

          const assetDecision = buildAssetDecision(
            price,
            change24h,
            byTf,
            tradeStyle,
            riskMode
          );

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
              rsi: byTf["1h"]?.rsi || 0,
              ichimoku: byTf["1h"]?.ichimoku || null
            },
            tradeStyle,
            riskMode,
            ...assetDecision
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
      tradeStyle,
      riskMode,
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
