"use client";

import { useState } from "react";

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

export default function BacktestPage() {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [tradeStyle, setTradeStyle] = useState("medium");
  const [riskMode, setRiskMode] = useState("moderate");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  async function runBacktest() {
    try {
      setLoading(true);
      setError("");
      setResult(null);

      const res = await fetch(
        `/api/backtest?symbol=${encodeURIComponent(symbol)}&tradeStyle=${encodeURIComponent(tradeStyle)}&riskMode=${encodeURIComponent(riskMode)}`,
        { cache: "no-store" }
      );

      const data = await res.json();

      if (!res.ok || !data.ok) {
        throw new Error(data?.error || "Erreur backtest");
      }

      setResult(data);
    } catch (e) {
      setError(e?.message || "Erreur inconnue");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page">
      <div className="container">
        <header className="hero">
          <div>
            <div className="pill">Backtest</div>
            <h1>Backtest séparé</h1>
            <p>
              Cette page est volontairement séparée de l’accueil.
            </p>
          </div>
        </header>

        <section className="panel" style={{ marginBottom: 24 }}>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
            <input
              className="input"
              style={{ maxWidth: 220 }}
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              placeholder="BTCUSDT"
            />

            <select
              className="select"
              style={{ maxWidth: 180 }}
              value={tradeStyle}
              onChange={(e) => setTradeStyle(e.target.value)}
            >
              {TRADE_STYLES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>

            <select
              className="select"
              style={{ maxWidth: 180 }}
              value={riskMode}
              onChange={(e) => setRiskMode(e.target.value)}
            >
              {RISK_MODES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>

            <button className="primary-btn" onClick={runBacktest}>
              {loading ? "Calcul..." : "Lancer le backtest"}
            </button>
          </div>
        </section>

        {error ? (
          <section className="panel" style={{ marginBottom: 24 }}>
            Erreur : {error}
          </section>
        ) : null}

        {result?.summary ? (
          <>
            <section className="stats-grid">
              <div className="stat-card">
                <div className="stat-label">Trades</div>
                <div className="stat-value">{result.summary.totalTrades ?? "-"}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Winrate</div>
                <div className="stat-value">{result.summary.winRate ?? "-"}%</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Gagnants</div>
                <div className="stat-value">{result.summary.wins ?? "-"}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">Perdants</div>
                <div className="stat-value">{result.summary.losses ?? "-"}</div>
              </div>
              <div className="stat-card">
                <div className="stat-label">PnL théorique</div>
                <div className="stat-value">{(result?.summary?.netR ?? "-") + "R"}</div>
              </div>
            </section>

            <section className="panel">
              <h2>Derniers trades simulés</h2>
              <div className="details-grid">
                {result.trades.slice(0, 8).map((t, idx) => (
                  <div className="detail-card" key={idx}>
                    <div className="small-label">{t.side}</div>
                    <div>{t.tradeTf} + {t.contextTf}</div>
                    <div className="small-label" style={{ marginTop: 8 }}>Entrée</div>
                    <div>{t.entry}</div>
                    <div className="small-label" style={{ marginTop: 8 }}>Sortie</div>
                    <div>{t.exit}</div>
                    <div className="small-label" style={{ marginTop: 8 }}>Résultat</div>
                    <div>{t.result}</div>
                  </div>
                ))}
              </div>
            </section>
          </>
        ) : null}
      </div>
    </main>
  );
}
