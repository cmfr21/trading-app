"use client";

import { useMemo, useState } from "react";

const initialAssets = [
  {
    symbol: "BTCUSDT",
    enabled: true,
    price: 84250,
    change24h: 2.8,
    timeframe: "15m",
    decision: "LONG",
    score: 81,
    confidence: 78,
    entry: 83980,
    stopLoss: 82640,
    takeProfit: 86850,
    leverage: "x2",
    rr: 2.14,
    reason: "Tendance haussière propre, pullback correct, risque modéré.",
    lastAlert: "Il y a 4 min"
  },
  {
    symbol: "ETHUSDT",
    enabled: true,
    price: 4620,
    change24h: -1.2,
    timeframe: "15m",
    decision: "NO_TRADE",
    score: 49,
    confidence: 42,
    entry: 0,
    stopLoss: 0,
    takeProfit: 0,
    leverage: "-",
    rr: 0,
    reason: "Signaux contradictoires, aucun setup propre.",
    lastAlert: "Aucune"
  },
  {
    symbol: "SOLUSDT",
    enabled: true,
    price: 188.4,
    change24h: -3.7,
    timeframe: "5m",
    decision: "SHORT",
    score: 76,
    confidence: 73,
    entry: 187.9,
    stopLoss: 193.7,
    takeProfit: 176.1,
    leverage: "x2",
    rr: 2.03,
    reason: "Rejet sous résistance et pression vendeuse.",
    lastAlert: "Il y a 1 min"
  }
];

function formatPrice(value) {
  if (!value) return "-";
  return new Intl.NumberFormat("fr-FR", {
    maximumFractionDigits: 2
  }).format(value);
}

function decisionLabel(decision) {
  if (decision === "LONG") return "Long";
  if (decision === "SHORT") return "Short";
  return "Neutre";
}

export default function Page() {
  const [assets, setAssets] = useState(initialAssets);
  const [selected, setSelected] = useState(initialAssets[0].symbol);
  const [newAsset, setNewAsset] = useState("");
  const [timeframe, setTimeframe] = useState("15m");
  const [search, setSearch] = useState("");
  const [alertsEnabled, setAlertsEnabled] = useState(true);

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

  function runScan() {
    setAssets((prev) =>
      prev.map((asset) => {
        if (!asset.enabled) return asset;

        const random = Math.random();
        let decision = "NO_TRADE";
        if (random > 0.66) decision = "LONG";
        else if (random < 0.33) decision = "SHORT";

        const score = Math.floor(45 + Math.random() * 45);
        const confidence = Math.floor(40 + Math.random() * 50);
        const basePrice = asset.price || Number((100 + Math.random() * 1000).toFixed(2));
        const entry = Number((basePrice * (1 + (Math.random() - 0.5) * 0.01)).toFixed(2));

        const stopLoss =
          decision === "LONG"
            ? Number((entry * 0.985).toFixed(2))
            : decision === "SHORT"
            ? Number((entry * 1.015).toFixed(2))
            : 0;

        const takeProfit =
          decision === "LONG"
            ? Number((entry * 1.03).toFixed(2))
            : decision === "SHORT"
            ? Number((entry * 0.97).toFixed(2))
            : 0;

        const rr = decision === "NO_TRADE" ? 0 : Number((2 + Math.random() * 0.8).toFixed(2));

        return {
          ...asset,
          decision,
          score,
          confidence,
          entry,
          stopLoss,
          takeProfit,
          rr,
          leverage: decision === "NO_TRADE" ? "-" : score >= 75 ? "x2" : "x1",
          reason:
            decision === "LONG"
              ? "Signal haussier détecté avec risque maîtrisé."
              : decision === "SHORT"
              ? "Signal vendeur détecté avec invalidation claire."
              : "Pas de configuration assez propre pour entrer.",
          lastAlert: decision === "NO_TRADE" ? asset.lastAlert : "À l'instant"
        };
      })
    );
  }

  return (
    <main className="page">
      <div className="container">
        <header className="hero">
          <div>
            <div className="pill">Trading Signal Control Center</div>
            <h1>Scanner crypto temps réel</h1>
            <p>
              Maquette d’une web app de trading avec watchlist, signaux long/short,
              niveaux de trade et alertes.
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
            <button className="primary-btn" onClick={runScan}>
              Lancer un scan
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
                        {asset.change24h}%
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
              </div>
            </div>
          </section>
        </section>
      </div>
    </main>
  );
}
