"""
Récupération multi-timeframe via yfinance + prix réel via CoinGecko.

Fonctionnement dynamique :
  1. fetch_top_cryptos(n)     → top N cryptos par market cap (filtre stablecoins)
  2. fetch_coingecko_prices() → prix batch depuis le coin_map
  3. fetch_all_timeframes()   → OHLCV 5 TFs via yfinance (yahoo ticker dans coin_map)
"""

import time
import logging
from datetime import datetime, timezone
from typing import Optional

import requests
import pandas as pd
import yfinance as yf

from src.config import TIMEFRAMES, COINGECKO_BASE_URL, YAHOO_TICKER_OVERRIDES

logger = logging.getLogger(__name__)

# ─── Rate limiting CoinGecko ───────────────────────────────────────────────────
_CG_MIN_INTERVAL = 2.0
_last_cg_call    = 0.0

# ─── Tokens à exclure du top (stablecoins + wrapped) ─────────────────────────
_STABLECOINS = {
    # USD-pegged
    "usdt", "usdc", "busd", "dai", "tusd", "usds", "frax", "usde",
    "pyusd", "gusd", "susd", "lusd", "fdusd", "usdp", "usd0",
    "crvusd", "usdd", "usdx", "eurs", "usdb", "usdy", "usdm",
    # EUR-pegged
    "eurc", "eure", "eurt",
    # Autres
    "xaut", "paxg",   # stablecoins or or argent
}
_WRAPPED = {
    "wbtc", "weth", "wbnb", "weeth", "ezeth", "reth", "steth",
    "cbbtc", "bbtc", "wsteth", "solvbtc", "tbtc", "hbtc",
}

# Mots-clés dans le nom CoinGecko indiquant un stablecoin (filet de sécurité)
_STABLE_NAME_KEYWORDS = {"usd coin", "tether", "stablecoin", "peg", " usd"}

def _is_likely_stablecoin(symbol: str, name: str) -> bool:
    """Détecte les stablecoins non listés par heuristique sur le symbole / nom."""
    s = symbol.lower()
    n = name.lower()
    if s in _STABLECOINS or s in _WRAPPED:
        return True
    # Symbole contient "usd" ou "eur" + ne ressemble pas à une vraie crypto
    if ("usd" in s or "eur" in s) and len(s) <= 6:
        return True
    # Nom contient des mots-clés stablecoin
    for kw in _STABLE_NAME_KEYWORDS:
        if kw in n:
            return True
    return False


def _cg_get(url: str, params: dict, max_retries: int = 4) -> Optional[dict]:
    """
    Appel HTTP vers CoinGecko avec rate-limit et retry exponentiel sur 429.
    """
    global _last_cg_call

    elapsed = time.time() - _last_cg_call
    if elapsed < _CG_MIN_INTERVAL:
        time.sleep(_CG_MIN_INTERVAL - elapsed)

    wait = 2.0
    for attempt in range(1, max_retries + 1):
        try:
            _last_cg_call = time.time()
            resp = requests.get(url, params=params, timeout=20)
            if resp.status_code == 429:
                logger.warning(
                    f"CoinGecko 429 — tentative {attempt}/{max_retries}, "
                    f"attente {wait:.0f}s"
                )
                time.sleep(wait)
                wait *= 2
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            logger.warning(f"CoinGecko timeout tentative {attempt}/{max_retries}")
            time.sleep(wait)
            wait *= 2
        except requests.exceptions.RequestException as e:
            logger.warning(f"CoinGecko erreur réseau tentative {attempt}/{max_retries} : {e}")
            time.sleep(wait)
            wait *= 2

    return None


def fetch_top_cryptos(n: int = 20) -> dict:
    """
    Récupère exactement N cryptos (hors stablecoins et wrapped tokens)
    classées par market cap depuis CoinGecko /coins/markets.

    Stratégie : pages de 50 jusqu'à avoir n tokens valides.
    Retourne un coin_map :
    {
        "BTCUSDT": {"cg_id": "bitcoin",   "yahoo": "BTC-USD",  "ticker": "BTC",  "name": "Bitcoin"},
        "ETHUSDT": {"cg_id": "ethereum",  "yahoo": "ETH-USD",  "ticker": "ETH",  "name": "Ethereum"},
        ...
    }
    """
    coin_map = {}
    page     = 1
    seen_ids = set()

    while len(coin_map) < n and page <= 5:   # max 5 pages de 50 = 250 coins scannés
        data = _cg_get(
            f"{COINGECKO_BASE_URL}/coins/markets",
            params={
                "vs_currency": "usd",
                "order":       "market_cap_desc",
                "per_page":    50,
                "page":        page,
            },
        )
        if not data:
            logger.error(f"fetch_top_cryptos : échec page {page}")
            break

        for coin in data:
            cg_id  = coin.get("id", "")
            symbol = (coin.get("symbol") or "").lower().strip()
            name   = coin.get("name", "")

            if not symbol or not cg_id or cg_id in seen_ids:
                continue
            seen_ids.add(cg_id)

            # Filtrer stablecoins et wrapped (set + heuristique)
            if _is_likely_stablecoin(symbol, name):
                logger.debug(f"fetch_top_cryptos : {symbol} ({name}) filtré (stable/wrapped)")
                continue

            sym_usdt = f"{symbol.upper()}USDT"
            yahoo    = YAHOO_TICKER_OVERRIDES.get(sym_usdt, f"{symbol.upper()}-USD")

            coin_map[sym_usdt] = {
                "cg_id":  cg_id,
                "yahoo":  yahoo,
                "ticker": symbol.upper(),
                "name":   name,
            }

            if len(coin_map) >= n:
                break

        page += 1

    if len(coin_map) < n:
        logger.warning(
            f"fetch_top_cryptos : seulement {len(coin_map)}/{n} cryptos trouvées "
            f"après filtrage stablecoins sur {page-1} pages"
        )

    tickers = ", ".join(coin_map.keys())
    logger.info(f"Top {len(coin_map)} cryptos (hors stables) : {tickers}")
    return coin_map


def fetch_coingecko_prices(coin_map: dict) -> dict:
    """
    Récupère les prix USD pour tous les symboles du coin_map en UN SEUL appel batch.
    coin_map : dict retourné par fetch_top_cryptos()
    """
    ids = ",".join(v["cg_id"] for v in coin_map.values() if v.get("cg_id"))
    if not ids:
        return {}

    data = _cg_get(
        f"{COINGECKO_BASE_URL}/simple/price",
        params={"ids": ids, "vs_currencies": "usd"},
    )
    if not data:
        logger.error("CoinGecko prix batch : impossible de récupérer les prix")
        return {}

    result = {}
    for sym, info in coin_map.items():
        cg_id = info.get("cg_id", "")
        if cg_id and cg_id in data:
            entry = data[cg_id]
            if isinstance(entry, dict) and "usd" in entry:
                result[sym] = float(entry["usd"])
            else:
                logger.warning(
                    f"CoinGecko prix {sym} ({cg_id}) : réponse inattendue → {entry}"
                )
    return result


def fetch_btc_dominance_raw() -> Optional[dict]:
    """Récupère les données globales (BTC dominance, market cap) depuis CoinGecko."""
    return _cg_get(f"{COINGECKO_BASE_URL}/global", params={})


def fetch_coingecko_top_markets(vs_currency: str = "usd", per_page: int = 20) -> Optional[list]:
    """
    Récupère les données de marché (prix, variation 30j) pour le top des cryptos.
    Utilisé pour calculer l'Alt Season Index.
    """
    return _cg_get(
        f"{COINGECKO_BASE_URL}/coins/markets",
        params={
            "vs_currency":           vs_currency,
            "order":                 "market_cap_desc",
            "per_page":              per_page,
            "page":                  1,
            "price_change_percentage": "30d",
        },
    )


def fetch_ohlcv_tf(symbol: str, tf_key: str, yahoo_ticker: str) -> Optional[pd.DataFrame]:
    """
    Télécharge les bougies pour UN timeframe donné via yfinance.
    Gère le resampling 1h → 4h si nécessaire.
    """
    if not yahoo_ticker:
        return None

    cfg      = TIMEFRAMES[tf_key]
    interval = cfg["interval"]
    period   = cfg["period"]

    try:
        df = yf.download(
            yahoo_ticker, period=period, interval=interval,
            auto_adjust=True, progress=False, threads=False,
        )
    except Exception as e:
        logger.warning(f"{symbol} [{tf_key}] yfinance erreur : {e}")
        return None

    if df is None or df.empty:
        return None

    # Normaliser colonnes (MultiIndex possible avec yfinance >= 0.2.x)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0].lower() for c in df.columns]
    else:
        df.columns = [c.lower() for c in df.columns]

    df = df[["open", "high", "low", "close", "volume"]].copy()
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.dropna()

    # Resampling 1h → 4h
    if cfg.get("resample"):
        df = df.resample(cfg["resample"]).agg({
            "open":   "first",
            "high":   "max",
            "low":    "min",
            "close":  "last",
            "volume": "sum",
        }).dropna()

    min_c = cfg.get("min_candles", 52)
    if len(df) < min_c:
        logger.warning(
            f"{symbol} [{tf_key}] données insuffisantes : {len(df)} < {min_c}"
        )
        return None

    return df


def _validate_price(symbol: str, df: pd.DataFrame, cg_price: Optional[float]) -> bool:
    """
    Vérifie la cohérence prix Yahoo vs CoinGecko.
    Rejette si l'écart dépasse 70% (données Yahoo corrompues).
    """
    if cg_price is None or cg_price <= 0:
        return True

    last_close = float(df["close"].iloc[-1])
    if last_close <= 0:
        return False

    ratio = abs(last_close - cg_price) / cg_price
    if ratio > 0.70:
        logger.warning(
            f"{symbol} : prix Yahoo ({last_close:.6f}) incohérent "
            f"avec CoinGecko ({cg_price:.6f}) — écart {ratio*100:.0f}% → ignoré"
        )
        return False
    return True


def fetch_all_timeframes(symbol: str, cg_prices: dict, yahoo_ticker: str) -> Optional[dict]:
    """
    Récupère les données OHLCV pour les 5 timeframes d'un symbole.
    yahoo_ticker : ticker Yahoo Finance (ex: 'BTC-USD')
    """
    cg_price = cg_prices.get(symbol)
    tfs = {}

    for tf_key in TIMEFRAMES:
        df = fetch_ohlcv_tf(symbol, tf_key, yahoo_ticker)
        if df is None:
            logger.warning(f"{symbol} [{tf_key}] indisponible — TF ignoré")
            continue

        if tf_key == "1d" and not _validate_price(symbol, df, cg_price):
            logger.error(f"{symbol} : données corrompues sur Yahoo Finance → symbole ignoré")
            return None

        tfs[tf_key] = df
        time.sleep(0.2)

    if "1d" not in tfs:
        logger.warning(f"{symbol} : TF journalier manquant → symbole ignoré")
        return None

    price = cg_price if (cg_price and cg_price > 0) else float(tfs["1d"]["close"].iloc[-1])

    return {
        "symbol":    symbol,
        "price":     price,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "tfs":       tfs,
    }
