"use client";

import { useEffect, useMemo, useState, useRef } from "react";

const DEFAULT_ASSETS = [
  { symbol: "BTCUSDT", enabled: true },
  { symbol: "ETHUSDT", enabled: true },
  { symbol: "SOLUSDT", enabled: true },
  { symbol: "XRPUSDT", enabled: true }
];

const DISPLAY_TFS = ["15m", "1h", "4h", "1d", "1w"];

function buildEmptyAsset(symbol, enabled = true) {
  return {
    symbol,
    enabled,
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
    signalSignature: "",
    confluence: {
      longWeight: 0,
      shortWeight: 0,
      neutralWeight: 0
    },
    indicators: {
      ema20: 0,
      ema50: 0,
      atr: 0,
      rsi: 0,
      ichimoku: {}
    },
    timeframes: {}
  };
}

function formatPrice(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }

  const n = Number(value);

  return new Intl.NumberFormat("fr-FR", {
    maximumFractionDigits: n >= 100 ? 2 : n >= 1 ? 4 : 6
  }).format(n);
}

function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "-";
  }
  const n = Number(value);
  return `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;
}

function decisionLabel(decision) {
  if (decision === "LONG") return "Long";
  if (decision === "SHORT") return "Short";
  return "Neutre";
}

function tfDirectionLabel(direction) {
  if (direction === "LONG") return "Haussier";
  if (direction === "SHORT") return "Baissier";
  return "Neutre";
}

function safeAssetsFromStorage() {
  if (typeof window === "undefined") {
    return DEFAULT_ASSETS.map((a) => buildEmptyAsset(a.symbol, a.enabled));
  }

  try {
    const raw = window.localStorage.getItem("trading-app-assets");
    if (!raw) {
      return DEFAULT_ASSETS.map((a) => buildEmptyAsset(a.symbol, a.enabled));
    }

    const parsed = JSON.parse(raw);

    if (!Array.isArray(parsed) || !parsed.length) {
      return DEFAULT_ASSETS.map((a) => buildEmptyAsset(a.symbol, a.enabled));
    }

    return parsed.map((a) => buildEmptyAsset(a.symbol, a.enabled !== false));
  } catch {
    return DEFAULT_ASSETS.map((a) => buildEmptyAsset(a.symbol, a.enabled));
  }
}

function buildSignalSignature(item) {
  return [
    item.symbol,
    item.decision,
    item.timeframes?.["15m"]?.direction || "NEUTRAL",
    item.timeframes?.["1h"]?.direction || "NEUTRAL",
    item.timeframes?.["4h"]?.direction || "NEUTRAL",
    item.timeframes?.["1d"]?.direction || "NEUTRAL",
    item.timeframes?.["1w"]?.direction || "NEUTRAL"
  ].join("|");
}

export default function Page() {
  const [assets, setAssets] = useState([]);
  const [selected, setSelected] = useState("BTCUSDT");
  const [newAsset, setNewAsset] = useState("");
  const [search, setSearch] = useState("");
  const [alertsEnabled, setAlertsEnabled] = useState(true);
  const [marketLoading, setMarketLoading] = useState(false);
  const [marketError, setMarketError] = useState("");
  const [lastSync, setLastSync] = useState(null);
  const [sendingAlert, setSendingAlert] = useState(false);
  const [alertMessage, setAlertMessage] = useState("");
  const [mounted, setMounted] = useState(false);

  const alertCache = useRef({});

  useEffect(() => {
    const initial = safeAssetsFromStorage();
    setAssets(initial);
    setSelected(initial[0]?.symbol || "BTCUSDT");
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted) return;

    const slim = assets.map((a) => ({
      symbol: a.symbol,
      enabled: a.enabled
    }));

    window.localStorage.setItem("trading-app-assets", JSON.stringify(slim));
  }, [assets, mounted]);

  const filteredAssets = useMemo(() => {
    return assets.filter((a) =>
      a.symbol.toLowerCase().includes(search.toLowerCase())
    );
  }, [assets, search]);

  const selectedAsset = useMemo(() => {
    return assets.find((a) => a.symbol === selected) || assets[0] || null;
  }, [assets, selected]);

  const stats = useMemo(() => {
    const enabled = assets.filter((a) => a.enabled).length;
    const opportunities = assets.filter(
      (a) => a.enabled && a.decision !== "NO_TRADE"
    ).length;
    const longs = assets.filter((a) => a.enabled && a.decision === "LONG").length;
    const shorts = assets.filter((a) => a.enabled && a.decision === "SHORT").length;
    const neutral = assets.filter(
      (a) => a.enabled && a.decision === "NO_TRADE"
    ).length;

    return { enabled, opportunities, longs, shorts, neutral };
  }, [assets]);

  async function refreshMarket() {
    try {
      setMarketLoading(true);
      setMarketError("");
      setAlertMessage("");

      const enabledAssets = assets.filter((a) => a.enabled);

      if (!enabledAssets.length) {
        setMarketLoading(false);
        return;
      }

      const res = await fetch(
        `/api/market?symbols=${encodeURIComponent(
          enabledAssets.map((a) => a.symbol).join(",")
        )}`,
        { cache: "no-store" }
      );

      const data = await res.json();

      if (!res.ok || !data.ok) {
        throw new Error(data?.error || "Erreur market");
      }

      for (const item of data.items) {
        if (!item.ok) continue;
        if (item.decision === "NO_TRADE") continue;
        if (!alertsEnabled) continue;

        const signature = buildSignalSignature(item);
        const previous = alertCache.current[item.symbol];

        const changedSignal = !previous || previous.signature !== signature;
        const enoughTimePassed =
          !previous || Date.now() - previous.sentAt > 60 * 60 * 1000;

        if (!changedSignal && !enoughTimePassed) continue;

        await fetch("/api/alerts/test", {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            symbol: item.symbol,
            side: item.decision,
            entry: item.entry,
            stopLoss: item.stopLoss,
            takeProfit: item.takeProfit,
            leverage: item.leverage,
            rr: item.rr,
            reason: item.reason
          })
        });

        alertCache.current[item.symbol] = {
          signature,
          sentAt: Date.now()
        };
      }

      const map = new Map(data.items.map((item) => [item.symbol, item]));

      setAssets((prev) =>
        prev.map((asset) => {
          const live = map.get(asset.symbol);
          if (!live) return asset;

          if (!live.ok) {
            return {
              ...asset,
              reason: live.error || "Erreur de récupération",
              decision: "NO_TRADE"
            };
          }

          return {
            ...asset,
            price: live.price,
            change24h: live.change24h,
            decision: live.decision,
            score: live.score,
            confidence: live.confidence,
            entry: live.entry,
            stopLoss: live.stopLoss,
            takeProfit: live.takeProfit,
            leverage: live.leverage,
            rr: live.rr,
            reason: live.reason,
            indicators: live.indicators || asset.indicators,
            timeframes: live.timeframes || {},
            confluence: live.confluence || asset.confluence,
            signalSignature: buildSignalSignature(live)
          };
        })
      );

      setLastSync(Date.now());
    } catch (error) {
      setMarketError(error?.message || "Erreur inconnue");
    } finally {
      setMarketLoading(false);
    }
  }

  useEffect(() => {
    if (!mounted || !assets.length) return;
    refreshMarket();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mounted]);

  useEffect(() => {
    if (!mounted || !assets.length) return;

    const interval = setInterval(() => {
      refreshMarket();
    }, 30000);

    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mounted, assets.length, alertsEnabled]);

  function addAsset() {
    const symbol = newAsset.trim().toUpperCase();
    if (!symbol) return;

    if (!/^[A-Z0-9]{4,20}$/.test(symbol)) {
      setAlertMessage("Symbole invalide. Exemple : LINKUSDT");
      return;
    }

    if (assets.some((a) => a.symbol === symbol)) {
      setAlertMessage("Cet actif est déjà dans la watchlist.");
      setNewAsset("");
      return;
    }

    const asset = buildEmptyAsset(symbol, true);

    setAssets((prev) => [asset, ...prev]);
    setSelected(symbol);
    setNewAsset("");
    setAlertMessage("Actif ajouté. Clique sur Actualiser les prix.");
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
      if (!selectedAsset) return;

      setSendingAlert(true);
      setAlertMessage("");

      const res = await fetch("/api/alerts/test", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          symbol: selectedAsset.symbol,
          side: selectedAsset.decision,
          entry: selectedAsset.entry,
          stopLoss: selectedAsset.stopLoss,
          takeProfit: selectedAsset.takeProfit,
          leverage: selectedAsset.leverage,
          rr: selectedAsset.rr,
          reason: selectedAsset.reason
        })
      });

      const data = await res.json();

      if (!res.ok || !data.ok) {
        throw new Error(data?.error || "Échec alerte");
      }

      setAlertMessage("Alerte Telegram envoyée.");
      setAssets((prev) =>
        prev.map((a) =>
          a.symbol === selectedAsset.symbol
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

  if (!mounted) {
    return (
      <main className="page">
        <div className="container">
          <div className="panel">Chargement de l'application...</div>
        </div>
      </main>
    );
  }

  return (
    <main className="page">
      <div className="container">
        <header className="hero">
          <div>
            <div className="pill">Trading Signal Control Center</div>
            <h1>Scanner crypto à confluence multi-timeframe</h1>
            <p>
              Bougies clôturées uniquement, Ichimoku + EMA + RSI + ATR, et alertes
              automatiques uniquement en cas de changement réel du signal.
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
          <div className="stat-card">
            <div className="stat-label">Neutres</div>
            <div className="stat-value">{stats.neutral}</div>
          </div>
        </section>

        <section className="status-bar">
          <div className="status-card">
            <div className="small-label">Dernière synchro</div>
            <div className="status-text">
              {lastSync ? new Date(lastSync).toLocaleString("fr-FR") : "Aucune"}
            </div>
          </div>
          <div className="status-card">
            <div className="small-label">État</div>
            <div className="status-text">
              {marketError
                ? `Erreur : ${marketError}`
                : alertMessage || "Application prête."}
            </div>
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
                placeholder="Ex: LINKUSDT"
                value={newAsset}
                onChange={(e) => setNewAsset(e.target.value)}
              />
              <div />
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
                      <div className="asset-meta">Confluence multi-timeframe</div>
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
                      <div
                        className={
                          asset.change24h > 0
                            ? "up"
                            : asset.change24h < 0
                            ? "down"
                            : "neutral"
                        }
                      >
                        {formatPercent(asset.change24h)}
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
              Confluence 15m / 1h / 4h / 1d / 1w avec validation Ichimoku.
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

                <div className="metric-block">
                  <div className="small-label">Poids haussier</div>
                  <div>{selectedAsset?.confluence?.longWeight || 0}</div>
                </div>

                <div className="metric-block">
                  <div className="small-label">Poids baissier</div>
                  <div>{selectedAsset?.confluence?.shortWeight || 0}</div>
                </div>

                <div className="metric-block">
                  <div className="small-label">Poids neutre</div>
                  <div>{selectedAsset?.confluence?.neutralWeight || 0}</div>
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
                    {sendingAlert ? "Envoi..." : "Envoyer une alerte Telegram"}
                  </button>
                </div>

                <div style={{ marginTop: 12 }}>
                  <button
                    className="ghost-btn"
                    onClick={refreshMarket}
                    style={{ width: "100%" }}
                  >
                    Recalculer l'analyse
                  </button>
                </div>
              </div>
            </div>

            <div style={{ marginTop: 24 }}>
              <h3 style={{ marginBottom: 12 }}>Détail par timeframe</h3>
              <div className="details-grid">
                {DISPLAY_TFS.map((tf) => {
                  const tfData = selectedAsset?.timeframes?.[tf];
                  return (
                    <div className="detail-card" key={tf}>
                      <div className="small-label">{tf}</div>
                      <div
                        style={{
                          fontSize: 20,
                          fontWeight: 700,
                          marginTop: 6,
                          marginBottom: 8
                        }}
                      >
                        {tfDirectionLabel(tfData?.direction)}
                      </div>
                      <div className="small-label">EMA20</div>
                      <div>{formatPrice(tfData?.ema20)}</div>
                      <div className="small-label" style={{ marginTop: 8 }}>
                        EMA50
                      </div>
                      <div>{formatPrice(tfData?.ema50)}</div>
                      <div className="small-label" style={{ marginTop: 8 }}>
                        RSI
                      </div>
                      <div>{formatPrice(tfData?.rsi)}</div>
                      <div className="small-label" style={{ marginTop: 8 }}>
                        Tenkan
                      </div>
                      <div>{formatPrice(tfData?.ichimoku?.tenkan)}</div>
                      <div className="small-label" style={{ marginTop: 8 }}>
                        Kijun
                      </div>
                      <div>{formatPrice(tfData?.ichimoku?.kijun)}</div>
                      <div className="small-label" style={{ marginTop: 8 }}>
                        Cloud Top
                      </div>
                      <div>{formatPrice(tfData?.ichimoku?.cloudTop)}</div>
                      <div className="small-label" style={{ marginTop: 8 }}>
                        Cloud Bottom
                      </div>
                      <div>{formatPrice(tfData?.ichimoku?.cloudBottom)}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          </section>
        </section>
      </div>
    </main>
  );
}
