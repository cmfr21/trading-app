const STYLE_CONFIG = {
  short: {
    tradeTf: "15m",
    contextTf: "1h"
  },
  medium: {
    tradeTf: "1h",
    contextTf: "4h"
  },
  long: {
    tradeTf: "4h",
    contextTf: "1d"
  }
};

const RISK_CONFIG = {
  conservative: {
    rrMin: 2.0,
    stopAtr: 0.9,
    tpAtr: 2.2,
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
    tpAtr: 3.2,
    liquidationBuffer: 1.8
  }
};

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
  return map[timeframe] || 60;
}

async function fetchKlines(symbol, timeframe) {
  const pair = mapToKrakenPair(symbol);
  const interval = timeframeToKrakenInterval(timeframe);

  const res = await fetch(
    `https://api.kraken.com/0/public/OHLC?pair=${encodeURIComponent(pair)}&interval=${interval}`,
    { cache: "no-store" }
  );

  if (!res.ok) {
    throw new Error(`OHLC Kraken erreur ${res.status}`);
  }

  const data = await res.json();

  if (!data?.result || typeof data.result !== "object") {
    throw new Error("Réponse Kraken invalide");
  }

  const pairKey = Object.keys(data.result).find((key) => key !== "last");
  if (!pairKey || !Array.isArray(data.result[pairKey])) {
    throw new Error("Aucune bougie trouvée");
  }

  const rows = data.result[pairKey].map((row) => ({
    time: Number(row[0]),
    open: Number(row[1]),
    high: Number(row[2]),
    low: Number(row[3]),
    close: Number(row[4]),
    volume: Number(row[6])
  }));

  return rows.length > 1 ? rows.slice(0, -1) : rows;
}

function calcEma(values, period) {
  if (!values || values.length < period) return null;

  const k = 2 / (period + 1);
  let ema = values.slice(0, period).reduce((a, b) => a + b, 0) / period;

  for (let i = period; i < values.length; i += 1) {
    ema = values[i] * k + ema * (1 - k);
  }

  return ema;
}

function calcRsi(values, period = 14) {
  if (!values || values.length < period + 1) return null;

  let gains = 0;
  let losses = 0;

  for (let i = 1; i <= period; i += 1) {
    const diff = values[i] - values[i - 1];
    if (diff >= 0) gains += diff;
    else losses += Math.abs(diff);
  }

  let avgGain = gains / period;
  let avgLoss = losses / period;

  for (let i = period + 1; i < values.length; i += 1) {
    const diff = values[i] - values[i - 1];
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
  if (!candles || candles.length < period + 1) return null;

  const trs = [];

  for (let i = 1; i < candles.length; i += 1) {
    const high = candles[i].high;
    const low = candles[i].low;
    const prevClose = candles[i - 1].close;

    trs.push(
      Math.max(
        high - low,
        Math.abs(high - prevClose),
        Math.abs(low - prevClose)
      )
    );
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

function analyzeWindow(candles) {
  const closes = candles.map((c) => c.close);
  const ema20 = calcEma(closes, 20);
  const ema50 = calcEma(closes, 50);
  const rsi = calcRsi(closes, 14);
  const atr = calcAtr(candles, 14);
  const ichimoku = calcIchimoku(candles);
  const price = closes[closes.length - 1];

  if (!price || !ema20 || !ema50 || !rsi || !atr || !ichimoku) {
    return null;
  }

  const bullishEma = price > ema20 && ema20 > ema50;
  const bearishEma = price < ema20 && ema20 < ema50;

  const bullishIchimoku =
    price > ichimoku.cloudTop &&
    ichimoku.tenkan >= ichimoku.kijun;

  const bearishIchimoku =
    price < ichimoku.cloudBottom &&
    ichimoku.tenkan <= ichimoku.kijun;

  const distanceFromKijun = Math.abs(price - ichimoku.kijun);
  const flatIchi = Math.abs(ichimoku.tenkan - ichimoku.kijun) < atr * 0.1;

  let side = null;

  if (bullishEma && bullishIchimoku && rsi >= 48 && rsi <= 65) {
    side = "LONG";
  } else if (bearishEma && bearishIchimoku && rsi >= 35 && rsi <= 52) {
    side = "SHORT";
  }

  return {
    side,
    price,
    ema20,
    ema50,
    rsi,
    atr,
    ichimoku,
    distanceFromKijun,
    flatIchi
  };
}

function buildEntrySignal(tradeAnalysis, contextAnalysis, riskMode) {
  if (!tradeAnalysis || !contextAnalysis) return null;
  if (!tradeAnalysis.side || !contextAnalysis.side) return null;
  if (tradeAnalysis.side !== contextAnalysis.side) return null;

  if (tradeAnalysis.flatIchi) return null;
  if (tradeAnalysis.distanceFromKijun > tradeAnalysis.atr * 1.5) return null;

  if (tradeAnalysis.side === "SHORT" && tradeAnalysis.rsi < 35) return null;
  if (tradeAnalysis.side === "LONG" && tradeAnalysis.rsi > 65) return null;

  const risk = RISK_CONFIG[riskMode];
  const side = tradeAnalysis.side;
  const entry = tradeAnalysis.ichimoku.kijun;
  const atr = tradeAnalysis.atr;

  let stopLoss;
  let takeProfit;

  if (side === "LONG") {
    stopLoss = entry - atr * risk.stopAtr;
    takeProfit = entry + atr * risk.tpAtr;
  } else {
    stopLoss = entry + atr * risk.stopAtr;
    takeProfit = entry - atr * risk.tpAtr;
  }

  const rr =
    side === "LONG"
      ? (takeProfit - entry) / (entry - stopLoss)
      : (entry - takeProfit) / (stopLoss - entry);

  if (!Number.isFinite(rr) || rr < risk.rrMin) return null;

  return {
    side,
    entry,
    stopLoss,
    takeProfit,
    rr: Number(rr.toFixed(2))
  };
}

function findMatchingContextIndex(contextCandles, tradeTime) {
  let idx = -1;
  for (let i = 0; i < contextCandles.length; i += 1) {
    if (contextCandles[i].time <= tradeTime) idx = i;
    else break;
  }
  return idx;
}

function simulateTrade(side, entry, stopLoss, takeProfit, futureCandles) {
  for (const candle of futureCandles) {
    if (side === "LONG") {
      if (candle.low <= stopLoss) {
        return { exit: stopLoss, result: "-1R", outcome: "LOSS" };
      }
      if (candle.high >= takeProfit) {
        return { exit: takeProfit, result: `+${((takeProfit - entry) / (entry - stopLoss)).toFixed(2)}R`, outcome: "WIN" };
      }
    } else {
      if (candle.high >= stopLoss) {
        return { exit: stopLoss, result: "-1R", outcome: "LOSS" };
      }
      if (candle.low <= takeProfit) {
        return { exit: takeProfit, result: `+${((entry - takeProfit) / (stopLoss - entry)).toFixed(2)}R`, outcome: "WIN" };
      }
    }
  }

  const last = futureCandles[futureCandles.length - 1];
  if (!last) {
    return { exit: entry, result: "0R", outcome: "OPEN" };
  }

  const pnlR =
    side === "LONG"
      ? (last.close - entry) / (entry - stopLoss)
      : (entry - last.close) / (stopLoss - entry);

  return {
    exit: last.close,
    result: `${pnlR >= 0 ? "+" : ""}${pnlR.toFixed(2)}R`,
    outcome: "TIME_EXIT"
  };
}

export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const symbol = (searchParams.get("symbol") || "BTCUSDT").toUpperCase();
    const tradeStyle = searchParams.get("tradeStyle") || "medium";
    const riskMode = searchParams.get("riskMode") || "moderate";

    const style = STYLE_CONFIG[tradeStyle];
    if (!style) {
      return Response.json(
        { ok: false, error: "tradeStyle invalide" },
        { status: 400 }
      );
    }

    const tradeCandlesRaw = await fetchKlines(symbol, style.tradeTf);
    const contextCandlesRaw = await fetchKlines(symbol, style.contextTf);

    // Kraken limite l'historique, on prend le maximum dispo récent.
    // On garde une grosse fenêtre pour approcher 1 an selon timeframe.
    const tradeCandles = tradeCandlesRaw.slice(-720);
    const contextCandles = contextCandlesRaw.slice(-720);

    const trades = [];
    let lastSignalIndex = -9999;

    for (let i = 60; i < tradeCandles.length - 15; i += 1) {
      // évite de reprendre 10 trades collés
      if (i - lastSignalIndex < 8) continue;

      const tradeWindow = tradeCandles.slice(0, i + 1);
      const tradeAnalysis = analyzeWindow(tradeWindow);

      const contextIdx = findMatchingContextIndex(contextCandles, tradeCandles[i].time);
      if (contextIdx < 60) continue;

      const contextWindow = contextCandles.slice(0, contextIdx + 1);
      const contextAnalysis = analyzeWindow(contextWindow);

      const signal = buildEntrySignal(tradeAnalysis, contextAnalysis, riskMode);
      if (!signal) continue;

      const futureCandles = tradeCandles.slice(i + 1, i + 13);
      const sim = simulateTrade(
        signal.side,
        signal.entry,
        signal.stopLoss,
        signal.takeProfit,
        futureCandles
      );

      trades.push({
        time: tradeCandles[i].time,
        side: signal.side,
        tradeTf: style.tradeTf,
        contextTf: style.contextTf,
        entry: Number(signal.entry.toFixed(4)),
        stopLoss: Number(signal.stopLoss.toFixed(4)),
        takeProfit: Number(signal.takeProfit.toFixed(4)),
        rr: signal.rr,
        exit: Number(sim.exit.toFixed(4)),
        result: sim.result,
        outcome: sim.outcome
      });

      lastSignalIndex = i;
    }

    const wins = trades.filter((t) => t.result.startsWith("+")).length;
    const losses = trades.filter((t) => t.result === "-1R").length;
    const timeExits = trades.filter((t) => t.outcome === "TIME_EXIT").length;
    const totalTrades = trades.length;

    const netR = Number(
      trades
        .reduce((sum, t) => {
          const numeric = Number(String(t.result).replace("R", ""));
          return Number.isFinite(numeric) ? sum + numeric : sum;
        }, 0)
        .toFixed(2)
    );

    const winRate = totalTrades
      ? Number(((wins / totalTrades) * 100).toFixed(1))
      : 0;

    return Response.json({
      ok: true,
      symbol,
      tradeStyle,
      riskMode,
      summary: {
        totalTrades,
        wins,
        losses,
        timeExits,
        winRate,
        netR
      },
      trades
    });
  } catch (error) {
    return Response.json(
      {
        ok: false,
        error: error?.message || "Erreur backtest"
      },
      { status: 500 }
    );
  }
}
