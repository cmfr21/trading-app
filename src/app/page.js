"use client";

import { useEffect, useMemo, useState } from "react";

const initialAssets = [
  {
    symbol: "BTCUSDT",
    enabled: true,
    price: 0,
    change24h: 0,
    timeframe: "15m",
    decision: "NO_TRADE",
    score: 0,
    confidence: 0,
    entry: 0,
    stopLoss: 0,
    takeProfit: 0,
    leverage: "-",
    rr: 0,
    reason: "En attente d'analyse.",
    lastAlert: "Aucune"
  },
  {
    symbol: "ETHUSDT",
    enabled: true,
    price: 0,
    change24h: 0,
    timeframe: "15m",
    decision: "NO_TRADE",
    score: 0,
    confidence: 0,
    entry: 0,
    stopLoss: 0,
    takeProfit: 0,
    leverage: "-",
    rr: 0,
    reason: "En attente d'analyse.",
    lastAlert: "Aucune"
  },
  {
    symbol: "SOLUSDT",
    enabled: true,
    price: 0,
    change24h: 0,
    timeframe: "5m",
    decision: "NO_TRADE",
    score: 0,
    confidence: 0,
    entry: 0,
    stopLoss: 0,
    takeProfit: 0,
    leverage: "-",
    rr: 0,
    reason: "En attente d'analyse.",
    lastAlert: "Aucune"
  }
];

function formatPrice(value) {
  if (!value) return "-";
  return new Intl.NumberFormat("fr-FR", {
    maximumFractionDigits: value > 100 ? 2 : 4
  }).format(value);
}

function decisionLabel(decision) {
  if (decision === "LONG") return "Long";
  if (decision === "SHORT") return "Short";
  return "Neutre";
}

function computeSignal(asset) {
  const change = asset.change24h || 0;
  const price = asset.price || 0;

  if (!price) {
    return {
      decision: "NO_TRADE",
      score: 0,
      confidence: 0,
      entry: 0,
      stopLoss: 0,
      takeProfit: 0,
      leverage: "-",
      rr: 0,
      reason: "Pas encore de prix live."
    };
  }

  if (change >= 2) {
    const entry = price;
    const stopLoss = Number((price * 0.985).toFixed(4));
    const takeProfit = Number((price * 1.03).toFixed(4));
    return {
      decision: "LONG",
      score: 72,
      confidence: 68,
      entry,
      stopLoss,
      takeProfit,
      leverage: "x2",
      rr: 2,
      reason:
        "Momentum 24h haussier. Règle simple V2: biais long si variation >= 2%."
    };
  }

  if (change <= -2) {
    const entry = price;
    const stopLoss = Number((price * 1.015).toFixed(4));
    const takeProfit = Number((price * 0.97).toFixed(4));
    return {
      decision: "SHORT",
      score: 72,
      confidence: 68,
      entry,
      stopLoss,
      takeProfit,
      leverage: "x2",
      rr: 2,
      reason:
        "Momentum 24h baissier. Règle simple V2: biais short si variation <= -2%."
    };
  }

  return {
    decision: "NO_TRADE",
    score: 48,
    confidence: 44,
    entry: 0,
    stopLoss: 0,
    takeProfit: 0,
    leverage: "-",
    rr: 0,
    reason: "Pas de biais assez fort avec la règle simple actuelle."
  };
}

export default function Page() {
  const [assets, setAssets] = useState(initialAssets);
  const [selected, setSelected] = useState(initialAssets[0].symbol);
  const [newAsset, setNewAsset] = useState("");
  const [timeframe, setTimeframe] = useState("15m");
  const [search, setSearch] = useState("");
  const [alertsEnabled, setAlertsEnabled] = useState(true);
  const [marketLoading, setMarketLoading] = useState(false);
  const [marketError, setMarketError] = useState("");
  const [lastSync, setLastSync] = useState(null);
  const [sendingAlert, setSendingAlert] = useState(false);
  const [alertMessage, setAlertMessage] = useState("");

  const filteredAssets = useMemo(() => {
    return assets.filter((a) =>
      a.symbol.toLowerCase().includes(search.toLowerCase())
    );
  }, [assets, search]);

  const selectedAsset = useMemo(() => {
    return assets.find((a) => a.symbol === selected) || assets[0];
  }, [assets, selected]);

  const stats = useMemo(() => {
    const enabled = assets.filter((a) => a.enabled).length;
    const opportunities = assets.filter(
      (a) => a.enabled && a.decision !== "NO_TRADE"
    ).length;
    const longs = assets.filter((a) => a.enabled && a.decision === "LONG").length;
    const shorts = assets.filter((a) => a.enabled && a.decision === "SHORT").length;
    return { enabled, opportunities, longs, shorts };
  }, [assets]);

  async function refreshMarket() {
    try {
      setMarketLoading(true);
      setMarketError("");

      const symbols = assets
        .filter((a) => a.enabled)
        .map((a) => a.symbol)
        .join(",");

      if (!symbols) {
        setMarketLoading(false);
        return;
      }

      const res = await fetch(`/api/market?symbols=${encodeURIComponent(symbols)}`, {
        cache: "no-store"
      });

      const data = await res.json();

      if (!res.ok || !data.ok) {
        throw new Error(data?.error || "Erreur market");
      }

      const map = new Map(
        data.items
          .filter((item) => item.ok)
          .map((item) => [item.symbol, item])
      );

      setAssets((prev) =>
        prev.map((asset) => {
          const live = map.get(asset.symbol);

          if (!live) return asset;

          const signal = computeSignal({
            ...asset,
            price: live.price,
            change24h: live.change24h
          });

          return {
            ...asset,
            price: live.price,
            change24h: live.change24h,
            ...signal
          };
        })
      );

      setLastSync(data.updatedAt || Date.now());
    } catch (error) {
      setMarketError(error?.message || "Erreur inconnue");
    } finally {
      setMarketLoading(false);
    }
  }

  useEffect(() => {
    refreshMarket();
    const interval = setInterval(refreshMarket, 15000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function addAsset() {
    const symbol = newAsset.trim().toUpperCase();
    if (!symbol) return;
    if (assets.some((a) => a.symbol === symbol)) {
      setNewAsset("");
      return;
    }

    const asset = {
      symbol,
      enabled: true,
      price: 0,
      change24h: 0,
      timeframe,
      decision: "NO_TRADE",
      score: 0,
      confidence: 0,
      entry: 0,
      stopLoss: 0,
      takeProfit: 0,
      leverage: "-",
      rr: 0,
      reason: "En attente d'analyse.",
      lastAlert: "Aucune"
    };

    setAssets((prev) => [asset, ...prev]);
    setSelected(symbol);
    setNewAsset("");
  }

  function removeAsset(symbol) {
    const next = assets.filter((a) => a.symbol !== symbol);
    setAssets(next);
    if (selected === symbol && next.length) {
      setSelected(next[0].symbol);
    }
  }

  function toggleAsset(symbol) {
    setAssets((prev) =>
      prev.map((a) =>
        a.symbol === symbol ? { ...a, enabled: !a.enabled } : a
      )
    );
  }

  async function sendTestAlert() {
    try {
      setSendingAlert(true);
      setAlertMessage("");

      const asset = selectedAsset;
      const res = await fetch("/api/alerts/test", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          symbol: asset.symbol,
          side: asset.decision,
          entry: asset.entry,
          stopLoss: asset.stopLoss,
          takeProfit: asset.takeProfit,
          leverage: asset.leverage,
          rr: asset.rr
        })
      });

      const data = await res.json();

      if (!res.ok || !data.ok) {
        throw new Error(data?.error || "Échec alerte");
      }

      setAlertMessage("Alerte Telegram envoyée.");
      setAssets((prev) =>
        prev.map((a) =>
          a.symbol === asset.symbol
            ? { ...a, lastAlert: "À l'instant" }
            : a
        )
      );
    } catch (error) {
      setAlertMessage(error?.message || "Erreur envoi alerte");
    } finally {
      setSendingAlert(false);
    }
  }

  return (
    <main className="page">
      <div className="container">
        <header className="hero">
          <div>
            <div className="pill">Trading Signal Control Center</div>
            <h1>Scanner crypto temps réel</h1>
            <p>
              Version 2 : prix live via backend Next.js, calcul de signal simple,
              et test d’alerte Telegram.
            </p>
          </div>

          <div className="hero-actions">
            <label className="toggle">
              <span>Alertes</span>
              <input
                type="checkbox"
                checked={alertsEnabled}
                onChange={(e) => setAlertsEnabled(e.target.checked)}
              />
            </label>
            <button className="primary-btn" onClick={refreshMarket}>
              {marketLoading ? "Actualisation..." : "Actualiser les prix"}
            </button>
          </div>
        </header>

        <section className="stats-grid">
          <div className="stat-card">
            <div className="stat-label">Actifs surveillés</div>
            <div className="stat-value">{stats.enabled}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Opportunités actives</div>
            <div className="stat-value">{stats.opportunities}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Longs détectés</div>
            <div className="stat-value">{stats.longs}</div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Shorts détectés</div>
            <div className="stat-value">{stats.shorts}</div>
          </div>
        </section>

        <section className="panel" style={{ marginBottom: 24 }}>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center" }}>
            <div className="small-label">
              Dernière synchro :{" "}
              {lastSync ? new Date(lastSync).toLocaleString("fr-FR") : "Aucune"}
            </div>
            {marketError ? <div className="down">Erreur : {marketError}</div> : null}
            {alertMessage ? <div className="up">{alertMessage}</div> : null}
          </div>
        </section>

        <section className="main-grid">
          <aside className="panel">
            <h2>Watchlist</h2>

            <input
              className="input"
              placeholder="Rechercher un actif"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />

            <div className="add-row">
              <input
                className="input"
                placeholder="Ex: XRPUSDT"
                value={newAsset}
                onChange={(e) => setNewAsset(e.target.value)}
              />
              <select
                className="select"
                value={timeframe}
                onChange={(e) => setTimeframe(e.target.value)}
              >
                <option value="5m">5m</option>
                <option value="15m">15m</option>
                <option value="1h">1h</option>
                <option value="4h">4h</option>
              </select>
              <button className="secondary-btn" onClick={addAsset}>
                Ajouter
              </button>
            </div>

            <div className="asset-list">
              {filteredAssets.map((asset) => (
                <div
                  key={asset.symbol}
                  className={
                    selected === asset.symbol ? "asset-card selected" : "asset-card"
                  }
                  onClick={() => setSelected(asset.symbol)}
                >
                  <div className="asset-top">
                    <div>
                      <div className="asset-symbol">{asset.symbol}</div>
                      <div className="asset-meta">Timeframe {asset.timeframe}</div>
                    </div>
                    <span className={`badge ${asset.decision.toLowerCase()}`}>
                      {decisionLabel(asset.decision)}
                    </span>
                  </div>

                  <div className="asset-grid">
                    <div>
                      <div className="small-label">Prix</div>
                      <div>{formatPrice(asset.price)}</div>
                    </div>
                    <div>
                      <div className="small-label">24h</div>
                      <div className={asset.change24h >= 0 ? "up" : "down"}>
                        {asset.change24h >= 0 ? "+" : ""}
                        {asset.change24h.toFixed(2)}%
                      </div>
                    </div>
                  </div>

                  <div className="small-label">Score</div>
                  <div className="progress">
                    <div
                      className="progress-bar"
                      style={{ width: `${asset.score}%` }}
                    />
                  </div>

                  <div className="asset-actions">
                    <label className="mini-toggle">
                      <span>Actif</span>
                      <input
                        type="checkbox"
                        checked={asset.enabled}
                        onChange={(e) => {
                          e.stopPropagation();
                          toggleAsset(asset.symbol);
                        }}
                      />
                    </label>

                    <button
                      className="danger-link"
                      onClick={(e) => {
                        e.stopPropagation();
                        removeAsset(asset.symbol);
                      }}
                    >
                      Supprimer
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </aside>

          <section className="panel">
            <h2>{selectedAsset?.symbol || "Aucun actif"}</h2>
            <p className="muted">
              Analyse détaillée du setup, des niveaux techniques et du risque.
            </p>

            <div className="details-grid">
              <div className="detail-card">
                <div className="small-label">Prix actuel</div>
                <div className="detail-value">{formatPrice(selectedAsset?.price)}</div>
              </div>
              <div className="detail-card">
                <div className="small-label">Entrée</div>
                <div className="detail-value">{formatPrice(selectedAsset?.entry)}</div>
              </div>
              <div className="detail-card">
                <div className="small-label">Stop loss</div>
                <div className="detail-value">{formatPrice(selectedAsset?.stopLoss)}</div>
              </div>
              <div className="detail-card">
                <div className="small-label">Take profit</div>
                <div className="detail-value">{formatPrice(selectedAsset?.takeProfit)}</div>
              </div>
            </div>

            <div className="summary-grid">
              <div className="summary-card">
                <h3>Résumé stratégique</h3>
                <p>{selectedAsset?.reason}</p>

                <div className="metric-block">
                  <div className="small-label">
                    Score setup : {selectedAsset?.score || 0}/100
                  </div>
                  <div className="progress">
                    <div
                      className="progress-bar"
                      style={{ width: `${selectedAsset?.score || 0}%` }}
                    />
                  </div>
                </div>

                <div className="metric-block">
                  <div className="small-label">
                    Confiance : {selectedAsset?.confidence || 0}/100
                  </div>
                  <div className="progress">
                    <div
                      className="progress-bar"
                      style={{ width: `${selectedAsset?.confidence || 0}%` }}
                    />
                  </div>
                </div>
              </div>

              <div className="summary-card">
                <h3>Verdict</h3>
                <div className={`verdict ${selectedAsset?.decision.toLowerCase()}`}>
                  {decisionLabel(selectedAsset?.decision)}
                </div>

                <div className="info-row">
                  <span>Levier conseillé</span>
                  <strong>{selectedAsset?.leverage}</strong>
                </div>
                <div className="info-row">
                  <span>RR estimé</span>
                  <strong>{selectedAsset?.rr || 0}</strong>
                </div>
                <div className="info-row">
                  <span>Dernière alerte</span>
                  <strong>{selectedAsset?.lastAlert}</strong>
                </div>

                <div style={{ marginTop: 16 }}>
                  <button
                    className="primary-btn"
                    onClick={sendTestAlert}
                    disabled={!alertsEnabled || sendingAlert}
                    style={{
                      width: "100%",
                      opacity: !alertsEnabled || sendingAlert ? 0.6 : 1
                    }}
                  >
                    {sendingAlert ? "Envoi..." : "Envoyer une alerte test Telegram"}
                  </button>
                </div>
              </div>
            </div>
          </section>
        </section>
      </div>
    </main>
  );
}
