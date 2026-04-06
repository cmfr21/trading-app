"use client";

import { useEffect, useMemo, useState, useRef } from "react";

const DEFAULT_ASSETS = [
  { symbol: "BTCUSDT", enabled: true, timeframe: "15m" },
  { symbol: "ETHUSDT", enabled: true, timeframe: "15m" },
  { symbol: "SOLUSDT", enabled: true, timeframe: "15m" },
  { symbol: "XRPUSDT", enabled: true, timeframe: "15m" }
];

function buildEmptyAsset(symbol, timeframe = "15m", enabled = true) {
  return {
    symbol,
    enabled,
    timeframe,
    price: 0,
    change24h: 0,
    decision: "NO_TRADE",
    score: 0,
    confidence: 0,
    entry: 0,
    stopLoss: 0,
    takeProfit: 0,
    leverage: "-",
    rr: 0,
    reason: "En attente d'analyse.",
    lastAlert: "Aucune",
    indicators: {
      ema20: 0,
      ema50: 0,
      atr: 0,
      rsi: 0
    }
  };
}

function formatPrice(value) {
  if (!value) return "-";
  return Number(value).toFixed(2);
}

function decisionLabel(decision) {
  if (decision === "LONG") return "Long";
  if (decision === "SHORT") return "Short";
  return "Neutre";
}

export default function Page() {
  const [assets, setAssets] = useState(
    DEFAULT_ASSETS.map((a) =>
      buildEmptyAsset(a.symbol, a.timeframe, a.enabled)
    )
  );

  const [alertsEnabled, setAlertsEnabled] = useState(true);
  const [marketLoading, setMarketLoading] = useState(false);
  const [selected, setSelected] = useState("BTCUSDT");

  // 🔥 cache anti-spam
  const alertCache = useRef({});

  async function refreshMarket() {
    try {
      setMarketLoading(true);

      const symbols = assets
        .filter((a) => a.enabled)
        .map((a) => a.symbol)
        .join(",");

      const res = await fetch(`/api/market?symbols=${symbols}`);
      const data = await res.json();

      if (!data.ok) throw new Error("Erreur market");

      const map = new Map(data.items.map((i) => [i.symbol, i]));

      // 🔥 ALERTES AUTO
      for (const item of data.items) {
        if (!item.ok) continue;
        if (item.decision === "NO_TRADE") continue;
        if (!alertsEnabled) continue;

        const now = Date.now();
        const last = alertCache.current[item.symbol];

        // cooldown 30 min
        if (last && now - last < 30 * 60 * 1000) continue;

        await fetch("/api/alerts/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(item)
        });

        alertCache.current[item.symbol] = now;
      }

      setAssets((prev) =>
        prev.map((a) => {
          const live = map.get(a.symbol);
          if (!live || !live.ok) return a;

          return {
            ...a,
            ...live
          };
        })
      );
    } catch (err) {
      console.error(err);
    } finally {
      setMarketLoading(false);
    }
  }

  useEffect(() => {
    refreshMarket();
    const interval = setInterval(refreshMarket, 20000);
    return () => clearInterval(interval);
  }, []);

  const selectedAsset =
    assets.find((a) => a.symbol === selected) || assets[0];

  return (
    <main style={{ padding: 20 }}>
      <h1>🔥 Trading Scanner</h1>

      <button onClick={refreshMarket}>
        {marketLoading ? "Chargement..." : "Refresh"}
      </button>

      <label style={{ marginLeft: 20 }}>
        Alerts
        <input
          type="checkbox"
          checked={alertsEnabled}
          onChange={(e) => setAlertsEnabled(e.target.checked)}
        />
      </label>

      <hr />

      <div style={{ display: "flex", gap: 20 }}>
        {/* LISTE */}
        <div style={{ width: 300 }}>
          {assets.map((a) => (
            <div
              key={a.symbol}
              onClick={() => setSelected(a.symbol)}
              style={{
                padding: 10,
                marginBottom: 10,
                border: "1px solid #333",
                cursor: "pointer"
              }}
            >
              <b>{a.symbol}</b>
              <div>{formatPrice(a.price)}</div>
              <div>{decisionLabel(a.decision)}</div>
            </div>
          ))}
        </div>

        {/* DETAIL */}
        <div>
          <h2>{selectedAsset.symbol}</h2>
          <p>Prix: {formatPrice(selectedAsset.price)}</p>
          <p>Decision: {decisionLabel(selectedAsset.decision)}</p>
          <p>Entry: {formatPrice(selectedAsset.entry)}</p>
          <p>SL: {formatPrice(selectedAsset.stopLoss)}</p>
          <p>TP: {formatPrice(selectedAsset.takeProfit)}</p>
          <p>RR: {selectedAsset.rr}</p>
          <p>RSI: {selectedAsset.indicators?.rsi}</p>
        </div>
      </div>
    </main>
  );
}
