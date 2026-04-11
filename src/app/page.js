"use client";

import { useEffect, useMemo, useState, useRef } from "react";

const DEFAULT_ASSETS = [
  { symbol: "BTCUSDT", enabled: true },
  { symbol: "ETHUSDT", enabled: true },
  { symbol: "SOLUSDT", enabled: true },
  { symbol: "XRPUSDT", enabled: true }
];

const DISPLAY_TFS = ["15m", "1h", "4h", "1d", "1w"];

const TRADE_STYLES = [
  { value: "short", label: "Court terme" },
  { value: "medium", label: "Moyen terme" },
  { value: "long", label: "Long terme" }
];

const RISK_MODES = [
  { value: "conservative", label: "Conservateur" },
  { value: "moderate", label: "Modéré" },
  { value: "aggressive", label: "Agressif" }
];

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
    entryMin: 0,
    entryMax: 0,
    stopLoss: 0,
    takeProfit: 0,
    leverage: "-",
    leverageValue: 0,
    liquidationPrice: 0,
    rr: 0,
    reason: "En attente d'analyse.",
    lastAlert: "Aucune",
    signalSignature: "",
    indicators: {
      ema20: 0,
      ema50: 0,
      atr: 0,
      rsi: 0,
      ichimoku: {}
    },
    timeframes: {},
    setups: [],
    bestSetup: null
  };
}

function formatPrice(value) {
  if (
    value === null ||
    value === undefined ||
    Number.isNaN(Number(value))
  ) {
    return "-";
  }

  const n = Number(value);

  return new Intl.NumberFormat("fr-FR", {
    maximumFractionDigits: n >= 100 ? 2 : n >= 1 ? 4 : 6
  }).format(n);
}

function formatPercent(value) {
  if (
    value === null ||
    value === undefined ||
    Number.isNaN(Number(value))
  ) {
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
  const best = item.bestSetup;
  if (!best) return `${item.symbol}|NO_TRADE`;
  return [
    item.symbol,
    best.decision,
    best.tradeTf,
    best.contextTf,
    best.riskMode,
    best.entryMin,
    best.entryMax
  ].join("|");
}

function hasIchimoku(tfData) {
  return Boolean(
    tfData?.ichimoku &&
      (
        tfData.ichimoku.tenkan !== undefined ||
        tfData.ichimoku.kijun !== undefined ||
        tfData.ichimoku.cloudTop !== undefined ||
        tfData.ichimoku.cloudBottom !== undefined
      )
  );
}

export default function Page() {
  const [assets, setAssets] = useState([]);
  const [selected, setSelected] = useState("BTCUSDT");
  const [newAsset, setNewAsset] = useState("");
  const [search, setSearch] = useState("");
  const [alertsEnabled, setAlertsEnabled] = useState(true);
  const [tradeStyle, setTradeStyle] = useState("medium");
  const [riskMode, setRiskMode] = useState("moderate");
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
        )}&tradeStyle=${encodeURIComponent(tradeStyle)}&riskMode=${encodeURIComponent(riskMode)}`,
        { cache: "no-store" }
      );

      const data = await res.json();

      if (!res.ok || !data.ok) {
        throw new Error(data?.error || "Erreur market");
      }

      for (const item of data.items) {
        if (!item.ok) continue;
        if (item.decision === "NO_TRADE") continue;
        if (!item.bestSetup) continue;
        if (!alertsEnabled) continue;

        const signature = buildSignalSignature(item);
        const previous = alertCache.current[item.symbol];

        const changedSignal = !previous || previous.signature !== signature;
        const enoughTimePassed =
          !previous || Date.now() - previous.sentAt > 60 * 60 * 1000;

        if (!changedSignal && !enoughTimePassed) continue;

        const s = item.bestSetup;

        await fetch("/api/alerts/test", {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          body: JSON.stringify({
            symbol: item.symbol,
            side: s.decision,
            entry: s.entry,
            stopLoss: s.stopLoss,
            takeProfit: s.takeProfit,
            leverage: s.leverage,
            rr: s.rr,
            reason: `${s.label} — ${s.tradeTf} + ${s.contextTf} — ${s.reason}`
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
            entryMin: live.entryMin,
            entryMax: live.entryMax,
            stopLoss: live.stopLoss,
            takeProfit: live.takeProfit,
            leverage: live.leverage,
            leverageValue: live.leverageValue,
            liquidationPrice: live.liquidationPrice,
            rr: live.rr,
            reason: live.reason,
            indicators: live.indicators || asset.indicators,
            timeframes: live.timeframes || {},
            setups: live.setups || [],
            bestSetup: live.bestSetup || null,
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
  }, [mounted]);

  useEffect(() => {
    if (!mounted || !assets.length) return;

    const interval = setInterval(() => {
      refreshMarket();
    }, 30000);

    return () => clearInterval(interval);
  }, [mounted, assets.length, alertsEnabled, tradeStyle, riskMode]);

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
      if (!selectedAsset || !selectedAsset.bestSetup) return;

      setSendingAlert(true);
      setAlertMessage("");

      const s = selectedAsset.bestSetup;

      const res = await fetch("/api/alerts/test", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          symbol: selectedAsset.symbol,
          side: s.decision,
          entry: s.entry,
          stopLoss: s.stopLoss,
          takeProfit: s.takeProfit,
          leverage: s.leverage,
          rr: s.rr,
          reason: `${s.label} — ${s.tradeTf} + ${s.contextTf} — ${s.reason}`
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
            <h1>Scanner crypto à setups multi-timeframe</h1>
            <p>
              Choisis ton horizon de trade et ton niveau de risque. Le setup
              s’affiche seulement s’il respecte la stratégie.
            </p>
          </div>

          <div className="hero-actions">
            <select
              className="select"
              value={tradeStyle}
              onChange={(e) => setTradeStyle(e.target.value)}
              style={{ width: 180 }}
            >
              {TRADE_STYLES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>

            <select
              className="select"
              value={riskMode}
              onChange={(e) => setRiskMode(e.target.value)}
              style={{ width: 160 }}
            >
              {RISK_MODES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>

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
                      <div className="asset-meta">
                        {asset.bestSetup
                          ? `${asset.bestSetup.tradeTf} + ${asset.bestSetup.contextTf}`
                          : "Pas de trade"}
                      </div>
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
              Le setup n’apparaît que s’il respecte la stratégie sélectionnée.
            </p>

            <div className="details-grid">
              <div className="detail-card">
                <div className="small-label">Prix actuel</div>
                <div className="detail-value">{formatPrice(selectedAsset?.price)}</div>
              </div>
              <div className="detail-card">
                <div className="small-label">Entrée min</div>
                <div className="detail-value">{formatPrice(selectedAsset?.entryMin)}</div>
              </div>
              <div className="detail-card">
                <div className="small-label">Entrée max</div>
                <div className="detail-value">{formatPrice(selectedAsset?.entryMax)}</div>
              </div>
              <div className="detail-card">
                <div className="small-label">Liquidation estimée</div>
                <div className="detail-value">{formatPrice(selectedAsset?.liquidationPrice)}</div>
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

                {selectedAsset?.bestSetup ? (
                  <>
                    <div className="metric-block">
                      <div className="small-label">Setup retenu</div>
                      <div>
                        {selectedAsset.bestSetup.label} — {selectedAsset.bestSetup.tradeTf} + {selectedAsset.bestSetup.contextTf}
                      </div>
                    </div>

                    <div className="metric-block">
                      <div className="small-label">Stop loss</div>
                      <div>{formatPrice(selectedAsset.bestSetup.stopLoss)}</div>
                    </div>

                    <div className="metric-block">
                      <div className="small-label">Take profit</div>
                      <div>{formatPrice(selectedAsset.bestSetup.takeProfit)}</div>
                    </div>

                    <div className="metric-block">
                      <div className="small-label">RR</div>
                      <div>{selectedAsset.bestSetup.rr}</div>
                    </div>
                  </>
                ) : (
                  <div className="metric-block">
                    <div className="small-label">Setup retenu</div>
                    <div>Pas de trade</div>
                  </div>
                )}
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
                  <span>Liquidation estimée</span>
                  <strong>{formatPrice(selectedAsset?.liquidationPrice)}</strong>
                </div>
                <div className="info-row">
                  <span>Dernière alerte</span>
                  <strong>{selectedAsset?.lastAlert}</strong>
                </div>

                <div style={{ marginTop: 16 }}>
                  <button
                    className="primary-btn"
                    onClick={sendTestAlert}
                    disabled={!alertsEnabled || sendingAlert || !selectedAsset?.bestSetup}
                    style={{
                      width: "100%",
                      opacity: !alertsEnabled || sendingAlert || !selectedAsset?.bestSetup ? 0.6 : 1
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
              <h3 style={{ marginBottom: 12 }}>Setups détectés</h3>
              {selectedAsset?.setups?.length ? (
                <div className="details-grid">
                  {selectedAsset.setups.map((setup) => (
                    <div className="detail-card" key={setup.setupId}>
                      <div className="small-label">{setup.label}</div>
                      <div
                        style={{
                          fontSize: 20,
                          fontWeight: 700,
                          marginTop: 6,
                          marginBottom: 8
                        }}
                      >
                        {decisionLabel(setup.decision)}
                      </div>

                      <div className="small-label">Timeframes</div>
                      <div>{setup.tradeTf} + {setup.contextTf}</div>

                      <div className="small-label" style={{ marginTop: 8 }}>
                        Entrée min
                      </div>
                      <div>{formatPrice(setup.entryMin)}</div>

                      <div className="small-label" style={{ marginTop: 8 }}>
                        Entrée max
                      </div>
                      <div>{formatPrice(setup.entryMax)}</div>

                      <div className="small-label" style={{ marginTop: 8 }}>
                        Stop
                      </div>
                      <div>{formatPrice(setup.stopLoss)}</div>

                      <div className="small-label" style={{ marginTop: 8 }}>
                        TP
                      </div>
                      <div>{formatPrice(setup.takeProfit)}</div>

                      <div className="small-label" style={{ marginTop: 8 }}>
                        RR
                      </div>
                      <div>{setup.rr}</div>

                      <div className="small-label" style={{ marginTop: 8 }}>
                        Levier max conseillé
                      </div>
                      <div>{setup.leverage}</div>

                      <div className="small-label" style={{ marginTop: 8 }}>
                        Liquidation estimée
                      </div>
                      <div>{formatPrice(setup.liquidationPrice)}</div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="panel" style={{ padding: 16 }}>
                  Pas de trade sur le style / risque sélectionné.
                </div>
              )}
            </div>

            <div style={{ marginTop: 24 }}>
              <h3 style={{ marginBottom: 12 }}>Détail par timeframe</h3>
              <div className="details-grid">
                {DISPLAY_TFS.map((tf) => {
                  const tfData = selectedAsset?.timeframes?.[tf];
                  const ichiExists = hasIchimoku(tfData);

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

                      {ichiExists ? (
                        <>
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
                        </>
                      ) : (
                        <div style={{ marginTop: 10, color: "#94a3b8", fontSize: 12 }}>
                          Ichimoku indisponible sur ce timeframe
                        </div>
                      )}
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
