export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const symbolsParam = searchParams.get("symbols") || "";
    const timeframe = searchParams.get("timeframe") || "15m";

    const symbols = symbolsParam
      .split(",")
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);

    if (!symbols.length) {
      return Response.json({ ok: false, error: "No symbols" }, { status: 400 });
    }

    const results = await Promise.all(
      symbols.map(async (symbol) => {
        try {
          // 🔹 Prix + variation
          const tickerRes = await fetch(
            `https://fapi.binance.com/fapi/v1/ticker/24hr?symbol=${symbol}`,
            { cache: "no-store" }
          );

          const ticker = await tickerRes.json();

          const price = Number(ticker.lastPrice);
          const change24h = Number(ticker.priceChangePercent);

          // 🔹 Bougies
          const klinesRes = await fetch(
            `https://fapi.binance.com/fapi/v1/klines?symbol=${symbol}&interval=${timeframe}&limit=100`,
            { cache: "no-store" }
          );

          const klines = await klinesRes.json();

          const closes = klines.map((k) => Number(k[4]));

          // 🔹 EMA simple
          const ema = (period) => {
            let k = 2 / (period + 1);
            let ema = closes[0];
            for (let i = 1; i < closes.length; i++) {
              ema = closes[i] * k + ema * (1 - k);
            }
            return ema;
          };

          const ema20 = ema(20);
          const ema50 = ema(50);

          // 🔹 RSI simple
          let gains = 0;
          let losses = 0;

          for (let i = 1; i < closes.length; i++) {
            const diff = closes[i] - closes[i - 1];
            if (diff >= 0) gains += diff;
            else losses += Math.abs(diff);
          }

          const rs = gains / (losses || 1);
          const rsi = 100 - 100 / (1 + rs);

          // 🔹 Analyse SIMPLE mais réelle
          let decision = "NO_TRADE";
          let entry = price;
          let stopLoss = 0;
          let takeProfit = 0;
          let rr = 0;
          let leverage = "-";
          let reason = "Marché neutre";

          if (price > ema20 && ema20 > ema50 && rsi < 70) {
            stopLoss = price * 0.985;
            takeProfit = price * 1.03;
            rr = (takeProfit - price) / (price - stopLoss);

            if (rr >= 1.5) {
              decision = "LONG";
              leverage = "x2";
              reason = "Tendance haussière EMA + RSI correct";
            }
          }

          if (price < ema20 && ema20 < ema50 && rsi > 30) {
            stopLoss = price * 1.015;
            takeProfit = price * 0.97;
            rr = (price - takeProfit) / (stopLoss - price);

            if (rr >= 1.5) {
              decision = "SHORT";
              leverage = "x2";
              reason = "Tendance baissière EMA + RSI correct";
            }
          }

          return {
            symbol,
            ok: true,
            price,
            change24h,
            decision,
            entry,
            stopLoss,
            takeProfit,
            rr: Number(rr.toFixed(2)),
            leverage,
            reason,
            indicators: {
              ema20,
              ema50,
              rsi
            }
          };
        } catch (err) {
          return {
            symbol,
            ok: false,
            error: err.message
          };
        }
      })
    );

    return Response.json({
      ok: true,
      updatedAt: Date.now(),
      items: results
    });
  } catch (err) {
    return Response.json(
      { ok: false, error: err.message },
      { status: 500 }
    );
  }
}
