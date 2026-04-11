import { GET as marketGet } from "../market/route";

function buildMockTradesFromOpportunities(items) {
  const trades = [];

  for (const item of items) {
    if (!item?.bestSetup) continue;

    const s = item.bestSetup;
    const won = s.rr >= 1.8;
    trades.push({
      symbol: item.symbol,
      side: s.decision,
      tradeTf: s.tradeTf,
      contextTf: s.contextTf,
      entry: s.entry,
      exit: won ? s.takeProfit : s.stopLoss,
      result: won ? `+${s.rr}R` : "-1R"
    });
  }

  return trades;
}

export async function GET(request) {
  try {
    const url = new URL(request.url);
    const symbol = url.searchParams.get("symbol") || "BTCUSDT";
    const tradeStyle = url.searchParams.get("tradeStyle") || "medium";
    const riskMode = url.searchParams.get("riskMode") || "moderate";

    const marketUrl = new URL(request.url);
    marketUrl.searchParams.set("symbols", symbol);
    marketUrl.searchParams.set("tradeStyle", tradeStyle);
    marketUrl.searchParams.set("riskMode", riskMode);

    const marketResponse = await marketGet({
      url: marketUrl.toString()
    });

    const marketData = await marketResponse.json();

    if (!marketData?.ok) {
      return Response.json(
        { ok: false, error: marketData?.error || "Erreur market backtest" },
        { status: 500 }
      );
    }

    const trades = buildMockTradesFromOpportunities(marketData.items);

    const wins = trades.filter((t) => t.result.startsWith("+")).length;
    const losses = trades.filter((t) => t.result.startsWith("-")).length;
    const totalTrades = trades.length;
    const winRate = totalTrades ? Number(((wins / totalTrades) * 100).toFixed(1)) : 0;
    const netR = Number(
      trades.reduce((sum, t) => {
        if (t.result.startsWith("+")) return sum + Number(t.result.replace("+", "").replace("R", ""));
        return sum - 1;
      }, 0).toFixed(2)
    );

    return Response.json({
      ok: true,
      symbol,
      tradeStyle,
      riskMode,
      summary: {
        totalTrades,
        wins,
        losses,
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
