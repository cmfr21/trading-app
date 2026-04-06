function calcEma(values, period) {
  if (!values.length) return null;
  const k = 2 / (period + 1);
  let ema = values[0];

  for (let i = 1; i < values.length; i += 1) {
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

function analyzeAsset({ price, change24h, candles }) {
  const closes = candles.map((c) => Number(c.close));
  const ema20 = calcEma(closes, 20);
  const ema50 = calcEma(closes, 50);
  const atr = calcAtr(candles, 14);
  const rsi = calcRsi(closes, 14);

  if (!ema20 || !ema50 || !atr || !rsi) {
    return {
      decision: "NO_TRADE",
      score: 0,
      confidence: 0,
      entry: 0,
      stopLoss: 0,
      takeProfit: 0,
      leverage: "-",
      rr: 0,
      reason: "Données insuffisantes pour l'analyse.",
      indicators: { ema20, ema50, atr, rsi }
    };
  }

  const bullishTrend = price > ema20 && ema20 > ema50;
  const bearishTrend = price < ema20 && ema20 < ema50;

  let decision = "NO_TRADE";
  let entry = price;
  let stopLoss = 0;
  let takeProfit = 0;
  let rr = 0;
  let reason = "Aucune configuration exploitable.";
  let score = 45;
  let confidence = 42;
  let leverage = "-";

  if (bullishTrend && rsi >= 52 && rsi <= 68) {
    stopLoss = price - atr * 1.2;
    takeProfit = price + atr * 2.4;
    rr = (takeProfit - entry) / (entry - stopLoss);
    decision = rr >= 1.8 ? "LONG" : "NO_TRADE";
    reason =
      decision === "LONG"
        ? "Tendance haussière alignée EMA20/EMA50 avec RSI sain."
        : "Biais haussier mais ratio risque/rendement insuffisant.";
    score = decision === "LONG" ? 78 : 54;
    confidence = decision === "LONG" ? 72 : 48;
    leverage = decision === "LONG" ? "x2" : "-";
  } else if (bearishTrend && rsi >= 32 && rsi <= 48) {
    stopLoss = price + atr * 1.2;
    takeProfit = price - atr * 2.4;
    rr = (entry - takeProfit) / (stopLoss - entry);
    decision = rr >= 1.8 ? "SHORT" : "NO_TRADE";
    reason =
      decision === "SHORT"
        ? "Tendance baissière alignée EMA20/EMA50 avec RSI compatible."
        : "Biais baissier mais ratio risque/rendement insuffisant.";
    score = decision === "SHORT" ? 78 : 54;
    confidence = decision === "SHORT" ? 72 : 48;
    leverage = decision === "SHORT" ? "x2" : "-";
  } else {
    if (Math.abs(change24h) < 1) {
      reason = "Marché trop neutre pour se positionner.";
    } else if (rsi > 68 || rsi < 32) {
      reason = "Actif trop étendu, meilleur de ne pas courir après le mouvement.";
    } else {
      reason = "Tendance et momentum non alignés.";
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
    indicators: {
      ema20: Number(ema20.toFixed(6)),
      ema50: Number(ema50.toFixed(6)),
      atr: Number(atr.toFixed(6)),
      rsi: Number(rsi.toFixed(2))
    }
  };
}

async function fetchTicker(symbol) {
  const res = await fetch(
    `https://fapi.binance.com/fapi/v1/ticker/24hr?symbol=${encodeURIComponent(symbol)}`,
    { cache: "no-store" }
  );

  if (!res.ok) {
    throw new Error(`Ticker Binance ${symbol} erreur ${res.status}`);
  }

  return res.json();
}

async function fetchKlines(symbol, interval = "15m", limit = 120) {
  const res = await fetch(
    `https://fapi.binance.com/fapi/v1/klines?symbol=${encodeURIComponent(
      symbol
    )}&interval=${interval}&limit=${limit}`,
    { cache: "no-store" }
  );

  if (!res.ok) {
    throw new Error(`Klines Binance ${symbol} erreur ${res.status}`);
  }

  const rows = await res.json();

  return rows.map((row) => ({
    openTime: row[0],
    open: Number(row[1]),
    high: Number(row[2]),
    low: Number(row[3]),
    close: Number(row[4]),
    volume: Number(row[5])
  }));
}

export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const symbolsParam = searchParams.get("symbols") || "";
    const timeframe = searchParams.get("timeframe") || "15m";

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
          const [ticker, candles] = await Promise.all([
            fetchTicker(symbol),
            fetchKlines(symbol, timeframe, 120)
          ]);

          const price = Number(ticker.lastPrice);
          const change24h = Number(ticker.priceChangePercent);
          const analysis = analyzeAsset({
            price,
            change24h,
            candles
          });

          return {
            symbol,
            ok: true,
            price,
            change24h,
            high24h: Number(ticker.highPrice),
            low24h: Number(ticker.lowPrice),
            volume: Number(ticker.volume),
            timeframe,
            ...analysis
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
      timeframe,
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
