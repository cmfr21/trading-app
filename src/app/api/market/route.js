export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const symbolsParam = searchParams.get("symbols") || "";
    const symbols = symbolsParam
      .split(",")
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);

    if (!symbols.length) {
      return Response.json(
        { ok: false, error: "Aucun symbole fourni." },
        { status: 400 }
      );
    }

    const results = await Promise.all(
      symbols.map(async (symbol) => {
        const url = `https://fapi.binance.com/fapi/v1/ticker/24hr?symbol=${encodeURIComponent(
          symbol
        )}`;

        const res = await fetch(url, {
          cache: "no-store"
        });

        if (!res.ok) {
          return {
            symbol,
            ok: false,
            error: `Erreur Binance ${res.status}`
          };
        }

        const data = await res.json();

        return {
          symbol: data.symbol,
          ok: true,
          price: Number(data.lastPrice),
          change24h: Number(data.priceChangePercent),
          high24h: Number(data.highPrice),
          low24h: Number(data.lowPrice),
          volume: Number(data.volume)
        };
      })
    );

    return Response.json({
      ok: true,
      updatedAt: Date.now(),
      items: results
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
