export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const symbol = (searchParams.get("symbol") || "BTCUSDT").toUpperCase();

    // 🔥 Fake dataset simple (on remplacera par du réel après)
    const prices = [
      100, 102, 101, 103, 105, 104, 106, 108, 107, 109,
      110, 108, 107, 106, 105, 104, 103, 102, 101, 100
    ];

    const trades = [];

    for (let i = 5; i < prices.length - 1; i++) {
      const entry = prices[i];
      const next = prices[i + 1];

      const isLong = entry < prices[i - 1];

      let result;
      let rr;

      if (isLong) {
        rr = next > entry ? 1.5 : -1;
      } else {
        rr = next < entry ? 1.5 : -1;
      }

      result = rr > 0 ? `+${rr}R` : "-1R";

      trades.push({
        entry,
        exit: next,
        side: isLong ? "LONG" : "SHORT",
        result
      });
    }

    const wins = trades.filter(t => t.result.startsWith("+")).length;
    const losses = trades.filter(t => t.result.startsWith("-")).length;

    const netR = trades.reduce((sum, t) => {
      if (t.result.startsWith("+")) {
        return sum + parseFloat(t.result.replace("+", "").replace("R", ""));
      }
      return sum - 1;
    }, 0);

    const totalTrades = trades.length;
    const winRate = totalTrades ? (wins / totalTrades) * 100 : 0;

    return Response.json({
      ok: true,
      symbol,
      summary: {
        totalTrades,
        wins,
        losses,
        winRate: Number(winRate.toFixed(1)),
        netR: Number(netR.toFixed(2))
      },
      trades
    });

  } catch (error) {
    return Response.json(
      { ok: false, error: error.message },
      { status: 500 }
    );
  }
}
