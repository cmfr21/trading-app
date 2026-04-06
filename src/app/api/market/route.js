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
          const tickerRes = await fetch(
            `https://fapi.binance.com/fapi/v1/ticker/24hr?symbol=${encodeURIComponent(symbol)}`,
            { cache: "no-store" }
          );

          if (!tickerRes.ok) {
            throw new Error(`Ticker HTTP ${tickerRes.status}`);
          }

          const ticker = await tickerRes.json();

          if (!ticker || typeof ticker !== "object" || !ticker.lastPrice) {
            throw new Error("Réponse ticker invalide");
          }

          const price = Number(ticker.lastPrice);
          const change24h = Number(ticker.priceChangePercent);

          const klinesRes = await fetch(
            `https://fapi.binance.com/fapi/v1/klines?symbol=${encodeURIComponent(
              symbol
            )}&interval=${encodeURIComponent(timeframe)}&limit=100`,
            { cache: "no-store" }
          );

          if (!klinesRes.ok) {
            throw new Error(`Klines HTTP ${klinesRes.status}`);
          }

          const klines = await klinesRes.json();

          if (!Array.isArray(klines)) {
            throw new Error(
              `Klines invalides: ${typeof klines} ${JSON.stringify(klines).slice(0, 200)}`
            );
          }

          if (klines.length < 50) {
            throw new Error("Pas assez de bougies pour analyser");
          }

          const closes = klines.map((k) => Number(k[4])).filter((v) => Number.isFinite(v));

          if (closes.length < 50) {
            throw new Error("Clôtures invalides");
          }

          function ema(period) {
            const slice = closes.slice(0, period);
            if (slice.length < period) return null;

            let value = slice.reduce((a, b) => a + b, 0) / period;
            const k = 2 / (period + 1);

            for (let i = period; i < closes.length; i += 1) {
              value = closes[i] * k + value * (1 - k);
            }

            return value;
          }

          function calcRsi(period = 14) {
            if (closes.length < period + 1) return null;

            let gains = 0;
            let losses = 0;

            for (let i = closes.length - period; i < closes.length; i += 1) {
              const prev = closes[i - 1];
              const curr = closes[i];
              const diff = curr - prev;

              if (diff >= 0) gains += diff;
              else losses += Math.abs(diff);
            }

            const avgGain = gains / period;
            const avgLoss = losses / period;

            if (avgLoss === 0) return 100;

            const rs = avgGain / avgLoss;
            return 100 - 100 / (1 + rs);
          }

          const ema20 = ema(20);
          const ema50 = ema(50);
          const rsi = calcRsi(14);

          if (!ema20 || !ema50 || !rsi) {
            throw new Error("Indicateurs impossibles à calculer");
          }

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
              reason = "Tendance haussière EMA20/EMA50 + RSI correct";
            }
          } else if (price < ema20 && ema20 < ema50 && rsi > 30) {
            stopLoss = price * 1.015;
            takeProfit = price * 0.97;
            rr = (price - takeProfit) / (stopLoss - price);

            if (rr >= 1.5) {
              decision = "SHORT";
              leverage = "x2";
              reason = "Tendance baissière EMA20/EMA50 + RSI correct";
            }
          }

          return {
            symbol,
            ok: true,
            price,
            change24h,
            decision,
            entry: Number(entry.toFixed(4)),
            stopLoss: Number(stopLoss.toFixed(4)),
            takeProfit: Number(takeProfit.toFixed(4)),
            rr: Number(rr.toFixed(2)),
            leverage,
            reason,
            indicators: {
              ema20: Number(ema20.toFixed(4)),
              ema50: Number(ema50.toFixed(4)),
              rsi: Number(rsi.toFixed(2))
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
