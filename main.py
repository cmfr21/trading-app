"""
Crypto Trading Alerts v3 — Top N cryptos dynamique.

Flux :
  1. Récupère le top N cryptos par market cap depuis CoinGecko (filtre stablecoins)
  2. Récupère les prix CoinGecko en batch (1 seul appel)
  3. Pour chaque symbole :
     a. Télécharge les 5 TFs via yfinance (ticker Yahoo dans le coin_map)
     b. Calcule les indicateurs (Ichimoku Péloille, RSI, ATR, chandelier)
     c. Score LONG et SHORT (80pts Ichimoku + 20pts complémentaires)
     d. Si score >= seuil → calcule le risque (cibles Ichimoku, stop Kijun, levier)
  4. Filtre les doublons (cooldown 4h via state/alerts.json)
  5. Envoie l'email si au moins une opportunité
"""

import os
import json
import logging
import time
from datetime import datetime, timezone, timedelta

from src.config import (
    TOP_N_CRYPTOS, SCORE_THRESHOLD, MIN_RR_RATIO,
    ALERT_COOLDOWN_HOURS, ALERT_MIN_SCORE_DELTA, ALERT_PRICE_DELTA_PCT,
    STATE_FILE,
)
from src.data_fetcher import (
    fetch_top_cryptos, fetch_coingecko_prices, fetch_all_timeframes,
)
from src.indicators   import analyze_tf
from src.scoring      import compute_score, build_btc_context
from src.risk         import compute_risk
from src.sentiment    import fetch_btc_dominance, compute_alt_season_index
from src.email_sender import send_email

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# GESTION DU COOLDOWN (anti-doublon entre runs)
# ──────────────────────────────────────────────────────────────────────────────

def load_state() -> dict:
    os.makedirs("state", exist_ok=True)
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state: dict):
    os.makedirs("state", exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _kijun_break_tfs(tf_analyses: dict, direction: str) -> list:
    """
    Retourne la liste des TF où un break Kijun valide vient d'être détecté
    pour la direction donnée (bull_break ↔ LONG, bear_break ↔ SHORT).
    """
    break_type = "bull_break" if direction == "LONG" else "bear_break"
    return [
        tf for tf, ana in tf_analyses.items()
        if ana.get("ichi", {}).get("kijun_break") == break_type   # clé correcte : "ichi"
    ]


def is_duplicate(state: dict, symbol: str, direction: str,
                 current_score: float, current_price: float,
                 current_kijun_tfs: list) -> bool:
    """
    Détermine si l'opportunité est un doublon ou une vraie nouvelle entrée.

    4 critères pour re-alerter AVANT expiration du cooldown :
      1. Nouveau break Kijun sur TF primaire (1wk/1d/4h) — signal Péloille frais
      2. Score amélioré significativement (≥ ALERT_MIN_SCORE_DELTA pts)
      3. Prix bougé d'au moins ALERT_PRICE_DELTA_PCT % depuis la dernière alerte
      4. Fallback : cooldown expiré (≥ ALERT_COOLDOWN_HOURS h)
    """
    key = f"{symbol}_{direction}"
    if key not in state:
        return False   # jamais alerté → pas un doublon

    last = state[key]

    # Rétro-compatibilité : ancien format = simple string ISO
    if isinstance(last, str):
        age = datetime.now(timezone.utc) - datetime.fromisoformat(last)
        return age < timedelta(hours=ALERT_COOLDOWN_HOURS)

    last_sent = datetime.fromisoformat(last["timestamp"])
    age       = datetime.now(timezone.utc) - last_sent

    # ── Critère 4 : cooldown expiré (fallback inconditionnel) ─────────────────
    if age >= timedelta(hours=ALERT_COOLDOWN_HOURS):
        logger.info(f"  {symbol} {direction} : cooldown {ALERT_COOLDOWN_HOURS}h expiré → re-alerte")
        return False

    # ── Critère 1 : nouveau break Kijun sur TF primaire ───────────────────────
    last_kijun_tfs = set(last.get("kijun_tfs", []))
    new_breaks     = set(current_kijun_tfs) - last_kijun_tfs
    primary_new    = new_breaks & {"1wk", "1d", "4h"}
    if primary_new:
        logger.info(
            f"  {symbol} {direction} : nouveau break Kijun sur "
            f"{sorted(primary_new)} → re-alerte (signal Péloille frais)"
        )
        return False

    # ── Critère 2 : score amélioré significativement ──────────────────────────
    last_score = last.get("score", 0.0)
    delta_score = current_score - last_score
    if delta_score >= ALERT_MIN_SCORE_DELTA:
        logger.info(
            f"  {symbol} {direction} : score {last_score:.0f}→{current_score:.0f} "
            f"(+{delta_score:.0f}pts) → re-alerte (signal renforcé)"
        )
        return False

    # ── Critère 3 : prix bougé significativement ──────────────────────────────
    last_price = last.get("price", 0.0)
    if last_price > 0:
        price_delta_pct = abs(current_price - last_price) / last_price * 100
        if price_delta_pct >= ALERT_PRICE_DELTA_PCT:
            logger.info(
                f"  {symbol} {direction} : prix bougé {price_delta_pct:.1f}% "
                f"depuis alerte → re-alerte (nouvelle zone d'entrée)"
            )
            return False

    return True   # aucun critère déclenché → doublon, on ignore


def mark_sent(state: dict, symbol: str, direction: str,
              score: float, price: float, kijun_tfs: list):
    """Enregistre l'alerte avec son contexte pour la déduplication intelligente."""
    state[f"{symbol}_{direction}"] = {
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "score":      round(score, 1),
        "price":      price,
        "kijun_tfs":  kijun_tfs,
    }


# ──────────────────────────────────────────────────────────────────────────────
# ANALYSE D'UN SYMBOLE
# ──────────────────────────────────────────────────────────────────────────────

def analyze_symbol(symbol: str, yahoo_ticker: str,
                   cg_prices: dict, sentiment: dict,
                   btc_context: dict = None) -> list:
    """Analyse un symbole sur 5 TFs et retourne les opportunités validées."""
    opportunities = []

    # 1. Données multi-TF
    data = fetch_all_timeframes(symbol, cg_prices, yahoo_ticker)
    if data is None:
        logger.warning(f"  {symbol} : données indisponibles")
        return []

    price     = data["price"]
    timestamp = data["timestamp"]
    tfs       = data["tfs"]

    # 2. Indicateurs par TF (inclut range_analysis et momentum v4)
    tf_analyses = {}
    for tf_key, df in tfs.items():
        try:
            tf_analyses[tf_key] = analyze_tf(df, tf_key)
        except Exception as e:
            logger.warning(f"  {symbol} [{tf_key}] indicateurs : {e}")

    if "1d" not in tf_analyses:
        return []

    # 3. Score LONG et SHORT
    for direction in ["LONG", "SHORT"]:
        result = compute_score(tf_analyses, sentiment, direction, btc_context)

        if result.get("blocked"):
            logger.info(
                f"  {symbol} {direction} bloqué [{result.get('market_status','?')}] "
                f": {result['blocked']}"
            )
            continue

        score     = result["score"]
        quality   = result.get("setup_quality", "")
        n_tf      = len(result.get("tf_agree", []))
        mstatus   = result.get("market_status", "")
        family    = result.get("setup_family", "")
        readiness = result.get("trade_readiness", "")
        logger.info(
            f"  {symbol} {direction} : {score}/100 {quality} "
            f"({n_tf}/5 TF) [{mstatus}] [{family}] [{readiness}] — {result.get('duration','')}"
        )

        if score < SCORE_THRESHOLD:
            continue

        # ── Filtre R/R minimum (MIN_RR_RATIO) ─────────────────────────────────
        risk = compute_risk(tf_analyses, direction, price)
        rr   = risk.get("rr_ratio")

        if rr is None or rr < MIN_RR_RATIO:
            rr_str = f"{rr:.2f}" if rr is not None else "N/A"
            logger.info(
                f"  {symbol} {direction} : R/R {rr_str} < {MIN_RR_RATIO} "
                f"→ rejeté (setup non rentable malgré score {score})"
            )
            continue

        rr_structural = risk.get("rr_to_structural")
        rr_str_txt = f" | structural {rr_structural:.2f}" if rr_structural else ""
        logger.info(
            f"  ✅ {symbol} {direction} retenu — score {score}, "
            f"R/R nearest {rr:.2f}{rr_str_txt} ({risk.get('rr_quality','')})"
        )
        # Log flags de risque si présents
        for flag in risk.get("risk_flags", []):
            logger.info(f"     {flag}")

        opportunities.append({
            "symbol":      symbol,
            "price":       price,
            "timestamp":   timestamp,
            "scoring":     result,
            "risk":        risk,
            "sentiment":   sentiment,
            "tf_analyses": tf_analyses,
        })

    return opportunities


# ──────────────────────────────────────────────────────────────────────────────
# ENTRÉE PRINCIPALE
# ──────────────────────────────────────────────────────────────────────────────

def run():
    analysis_time = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    logger.info(f"══ Démarrage — {analysis_time} ══")

    # ── 1. Top N cryptos dynamique ─────────────────────────────────────────────
    logger.info(f"Récupération du top {TOP_N_CRYPTOS} cryptos CoinGecko…")
    coin_map = fetch_top_cryptos(TOP_N_CRYPTOS)
    if not coin_map:
        logger.error("Impossible de récupérer le top cryptos — abandon")
        return []

    symbols = list(coin_map.keys())
    time.sleep(1.0)

    # ── 2. Prix batch CoinGecko ────────────────────────────────────────────────
    logger.info(f"Prix CoinGecko pour {len(symbols)} symboles…")
    cg_prices = fetch_coingecko_prices(coin_map)
    time.sleep(1.0)

    # ── 3. Données macro (BTC.D + Alt Season) ─────────────────────────────────
    logger.info("Récupération BTC Dominance + Alt Season…")
    btc_dom   = fetch_btc_dominance()
    time.sleep(0.5)
    alt_index = compute_alt_season_index()
    time.sleep(0.5)

    if btc_dom:
        mkt_chg = btc_dom.get('market_cap_change_24h_pct') or 0.0
        logger.info(
            f"BTC.D : {btc_dom.get('btc_dominance')}% "
            f"(marché crypto {mkt_chg:+.2f}% 24h)"
        )
    if alt_index:
        logger.info(f"Alt Season : {alt_index.get('alt_season_pct')}% — {alt_index.get('label')}")

    sentiment_base = {
        "btc_dominance":             btc_dom.get("btc_dominance")             if btc_dom else None,
        "market_cap_change_24h_pct": btc_dom.get("market_cap_change_24h_pct") if btc_dom else None,
        "btc_dominance_24h_pct":     None,   # déprécié — utiliser market_cap_change_24h_pct
        "alt_season_pct":        alt_index.get("alt_season_pct")      if alt_index else None,
        "alt_season_label":      alt_index.get("label")               if alt_index else None,
        "alt_season_detail":     alt_index.get("detail", [])          if alt_index else [],
        "bullish_ratio":         None,
    }

    # ── 4. Contexte BTC — analysé en premier pour filtrer les altcoins ─────────
    btc_context      = None
    btc_tf_analyses  = {}

    if "BTCUSDT" in coin_map:
        logger.info("Analyse BTC pour le contexte global…")
        btc_data = fetch_all_timeframes("BTCUSDT", cg_prices, coin_map["BTCUSDT"]["yahoo"])
        if btc_data:
            for tf_key, df in btc_data["tfs"].items():
                try:
                    btc_tf_analyses[tf_key] = analyze_tf(df, tf_key)
                except Exception as e:
                    logger.warning(f"  BTC [{tf_key}] : {e}")
            btc_context = build_btc_context(btc_tf_analyses)
            logger.info(
                f"Contexte BTC : {btc_context.get('trend','?').upper()} "
                f"— {btc_context.get('message','')}"
            )
        time.sleep(0.5)

    # ── 5. Anti-doublon ────────────────────────────────────────────────────────
    state = load_state()

    # ── 6. Analyse par symbole ─────────────────────────────────────────────────
    all_opportunities = []
    total_analyzed    = 0

    for symbol, info in coin_map.items():
        yahoo_ticker = info["yahoo"]
        name         = info.get("name", symbol)
        logger.info(f"── {symbol} ({name})")

        sentiment   = {**sentiment_base, "is_btc": symbol == "BTCUSDT"}
        # BTC se filtre lui-même (pas de pénalité BTC sur BTC)
        ctx = None if symbol == "BTCUSDT" else btc_context

        try:
            opps = analyze_symbol(symbol, yahoo_ticker, cg_prices, sentiment, ctx)
        except Exception as e:
            logger.error(f"  {symbol} erreur : {e}")
            continue

        total_analyzed += 1

        for opp in opps:
            direction = opp["scoring"]["direction"]
            score     = opp["scoring"]["score"]
            price     = opp["price"]
            k_tfs     = _kijun_break_tfs(opp["tf_analyses"], direction)

            if is_duplicate(state, symbol, direction, score, price, k_tfs):
                logger.info(
                    f"  {symbol} {direction} doublon "
                    f"(score={score:.0f}, aucun critère de re-alerte) → ignoré"
                )
                continue
            all_opportunities.append(opp)

        time.sleep(0.5)

    # ── 7. Résumé + envoi email ────────────────────────────────────────────────
    long_c  = sum(1 for o in all_opportunities if o["scoring"]["direction"] == "LONG")
    short_c = sum(1 for o in all_opportunities if o["scoring"]["direction"] == "SHORT")
    logger.info(f"══ {len(all_opportunities)} opportunité(s) : {long_c} LONG, {short_c} SHORT ══")

    if all_opportunities:
        all_opportunities.sort(key=lambda o: o["scoring"]["score"], reverse=True)
        success = send_email(all_opportunities, analysis_time, total_analyzed)
        if success:
            for opp in all_opportunities:
                mark_sent(
                    state,
                    opp["symbol"],
                    opp["scoring"]["direction"],
                    opp["scoring"]["score"],
                    opp["price"],
                    _kijun_break_tfs(opp["tf_analyses"], opp["scoring"]["direction"]),
                )
            save_state(state)
            logger.info("✅ Email envoyé — état sauvegardé")
        else:
            logger.error("❌ Échec envoi email")
    else:
        logger.info("Aucune opportunité — pas d'email (scan suivant dans ~5 min)")

    return all_opportunities


if __name__ == "__main__":
    run()
