const TIMEFRAMES = {
  short: { tf: "15m", interval: 15 },
  medium: { tf: "1h", interval: 60 },
  long: { tf: "4h", interval: 240 }
};

const RISK = {
  conservative: { sl: 1.0, tp: 2.0 },
  moderate: { sl: 1.2, tp: 2.5 },
  aggressive: { sl: 1.5, tp: 3.0 }
};

function tfToKraken(interval) {
  return interval;
}

async function fetchKlines(symbol, interval) {
  const res = await fetch(
    `https://api.kraken.com/0/public/OHLC?pair=${symbol}&interval=${interval}`
  );
  const data = await res.json();
  const key = Object.keys(data.result).find(k => k !== "last");

  return data.result[key].map(c => ({
    open: +c[1],
    high: +c[2],
    low: +c[3],
    close: +c[4]
  }));
}

// EMA
function ema(values, period) {
  let k = 2 / (period + 1);
  let ema = values[0];
  for (let i = 1; i < values.length; i++) {
    ema = values[i] * k + ema * (1 - k);
  }
  return ema;
}

// RSI
function rsi(values, period = 14) {
  let gains = 0, losses = 0;
  for (let i = 1; i <= period; i++) {
    const diff = values[i] - values[i - 1];
    if (diff >= 0) gains += diff;
    else losses -= diff;
  }
  let rs = gains / losses;
  return 100 - 100 / (1 + rs);
}

// SIGNAL SIMPLE (base)
function detectSignal(price, ema20, ema50, rsiVal) {
  if (price > ema20 && ema20 > ema50 && rsiVal > 50) return "LONG";
  if (price < ema20 && ema20 < ema50 && rsiVal < 50) return "SHORT";
  return null;
}

export async function GET(req) {
  const { searchParams } = new URL(req.url);

  const symbol = (searchParams.get("symbol") || "BTCUSDT").toUpperCase();
  const style = searchParams.get("tradeStyle") || "medium";
  const riskMode = searchParams.get("riskMode") || "moderate";

  const tf = TIMEFRAMES[style];
  const risk = RISK[riskMode];

  const candles = await fetchKlines(symbol, tf.interval);

  // 🔥 on prend ~1 an (approx)
  const data = candles.slice(-1000);

  const trades = [];

  for (let i = 60; i < data.length - 10; i++) {
    const closes = data.slice(i - 50, i).map(c => c.close);

    const price = closes.at(-1);
    const ema20 = ema(closes.slice(-20), 20);
    const ema50 = ema(closes.slice(-50), 50);
    const rsiVal = rsi(closes);

    const signal = detectSignal(price, ema20, ema50, rsiVal);

    if (!signal) continue;

    const entry = price;
    const sl = signal === "LONG"
      ? entry - entry * 0.01 * risk.sl
      : entry + entry * 0.01 * risk.sl;

    const tp = signal === "LONG"
      ? entry + entry * 0.01 * risk.tp
      : entry - entry * 0.01 * risk.tp;

    // 🔥 simulation
    let result = "LOSS";

    for (let j = i + 1; j < i + 10; j++) {
      const c = data[j];

      if (signal === "LONG") {
        if (c.low <= sl) { result = "LOSS"; break; }
        if (c.high >= tp) { result = "WIN"; break; }
      } else {
        if (c.high >= sl) { result = "LOSS"; break; }
        if (c.low <= tp) { result = "WIN"; break; }
      }
    }

    trades.push({
      side: signal,
      entry,
      stopLoss: sl,
      takeProfit: tp,
      result: result === "WIN" ? `+${risk.tp}R` : "-1R"
    });
  }

  const wins = trades.filter(t => t.result.startsWith("+")).length;
  const losses = trades.length - wins;

  const netR = trades.reduce((sum, t) => {
    return t.result.startsWith("+")
      ? sum + risk.tp
      : sum - 1;
  }, 0);

  return Response.json({
    ok: true,
    summary: {
      totalTrades: trades.length,
      wins,
      losses,
      winRate: trades.length ? ((wins / trades.length) * 100).toFixed(1) : 0,
      netR: netR.toFixed(2)
    },
    trades
  });
}
