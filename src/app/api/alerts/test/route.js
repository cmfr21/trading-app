export async function POST(request) {
  try {
    const token = process.env.TELEGRAM_BOT_TOKEN;
    const chatId = process.env.TELEGRAM_CHAT_ID;

    if (!token || !chatId) {
      return Response.json(
        {
          ok: false,
          error: "Variables TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID manquantes."
        },
        { status: 400 }
      );
    }

    const body = await request.json().catch(() => ({}));

    const symbol = body.symbol || "BTCUSDT";
    const side = body.side || "NO_TRADE";
    const entry = body.entry ?? "-";
    const stopLoss = body.stopLoss ?? "-";
    const takeProfit = body.takeProfit ?? "-";
    const leverage = body.leverage ?? "-";
    const rr = body.rr ?? "-";
    const reason = body.reason || "Signal généré depuis l'application.";

    const text =
      `🚨 Signal trading\n\n` +
      `Actif: ${symbol}\n` +
      `Sens: ${side}\n` +
      `Entrée: ${entry}\n` +
      `Stop loss: ${stopLoss}\n` +
      `Take profit: ${takeProfit}\n` +
      `Levier: ${leverage}\n` +
      `RR: ${rr}\n` +
      `Raison: ${reason}`;

    const telegramRes = await fetch(
      `https://api.telegram.org/bot${token}/sendMessage`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          chat_id: chatId,
          text
        })
      }
    );

    const telegramData = await telegramRes.json();

    if (!telegramRes.ok || !telegramData.ok) {
      return Response.json(
        {
          ok: false,
          error: "Échec envoi Telegram",
          telegram: telegramData
        },
        { status: 500 }
      );
    }

    return Response.json({
      ok: true,
      message: "Alerte envoyée."
    });
  } catch (error) {
    return Response.json(
      {
        ok: false,
        error: "Erreur serveur alertes.",
        details: error?.message || "unknown"
      },
      { status: 500 }
    );
  }
}
