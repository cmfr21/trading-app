"""
Module sentiment — sans aucune clé API ni inscription.

Deux indicateurs structurels uniquement :
  1. BTC Dominance (%) + variation 24h  →  via CoinGecko API publique
  2. Alt Season Index maison            →  % d'alts du top 10 surperformant BTC sur 30j

Logique :
  - Dominance BTC en baisse + majorité des alts surperformant BTC
    → les altcoins ont de la place pour monter → favorable aux LONG alts
  - Dominance BTC en hausse + alts sous-performant BTC
    → l'argent retourne vers BTC → défavorable aux LONG alts, favorable aux SHORT alts

NOTE : ces fonctions doivent être appelées UNE SEULE FOIS depuis main.py,
       puis le résultat réutilisé pour tous les symboles.
       Ne jamais appeler fetch_btc_dominance / compute_alt_season_index par symbole.
"""

import logging
from typing import Optional

from src.config import COINGECKO_BASE_URL
from src.data_fetcher import _cg_get   # rate-limiter centralisé

logger = logging.getLogger(__name__)


def fetch_btc_dominance() -> Optional[dict]:
    """
    Récupère la dominance BTC actuelle.
    Source : CoinGecko /global (1 appel, sans clé API).

    Note : L'API CoinGecko publique ne fournit pas directement la variation 24h de la
    dominance BTC. `market_cap_change_percentage_24h_usd` reflète la variation 24h
    de la capitalisation TOTALE du marché (pas spécifiquement la dominance BTC).
    On retourne ce champ sous le nom `market_cap_change_24h_pct` pour éviter toute
    confusion dans le scoring. La variation de dominance n'est pas utilisée dans la
    logique de score — seule la dominance absolue (btc_dominance) est conservée.
    """
    data = _cg_get(f"{COINGECKO_BASE_URL}/global", params={})
    if not data:
        logger.warning("BTC Dominance : données indisponibles")
        return None

    g = data.get("data", {})
    btc_dom = round(g.get("market_cap_percentage", {}).get("btc", 0.0), 2)
    # Variation totale du marché crypto (pas la dominance BTC spécifiquement)
    market_chg = round(g.get("market_cap_change_percentage_24h_usd", 0.0), 2)

    return {
        "btc_dominance":             btc_dom,
        # Renommé de btc_dominance_24h_pct → market_cap_change_24h_pct (plus précis)
        "market_cap_change_24h_pct": market_chg,
        # Alias conservé pour compatibilité descendante (ne pas utiliser dans le scoring)
        "btc_dominance_24h_pct":     None,
    }


def compute_alt_season_index() -> Optional[dict]:
    """
    Calcule l'Alt Season Index sur les 10 premières alts (hors BTC).

    Méthode :
      - Récupère la performance 30j de chaque alt exprimée en BTC
        (performance positive = surperforme BTC)
      - Compte le % d'alts positives

    Interprétation :
      ≥ 75%  → Alt Season       : les alts dominent, favorable aux LONG alts
      50–75% → Marché mixte     : sélectivité requise
      25–50% → BTC Season       : l'argent préfère BTC, prudence sur les alts
      < 25%  → BTC Season forte : alts sous forte pression, favorable aux SHORT alts

    Retourne aussi le détail par crypto pour affichage dans l'email.
    """
    # Top 10 alts par market cap (hors BTC), récupérées dynamiquement
    data = _cg_get(
        f"{COINGECKO_BASE_URL}/coins/markets",
        params={
            "vs_currency":             "btc",
            "order":                   "market_cap_desc",
            "per_page":                11,          # 11 pour exclure BTC (souvent #1)
            "page":                    1,
            "price_change_percentage": "30d",
            "sparkline":               "false",
        },
    )
    # Exclure BTC lui-même
    if data:
        data = [c for c in data if c.get("id") != "bitcoin"][:10]

    if not data:
        logger.warning("Alt Season Index : données indisponibles")
        return None

    results    = []
    outperform = 0
    for coin in data:
        chg = coin.get("price_change_percentage_30d_in_currency")
        if chg is None:
            continue
        results.append({
            "symbol":         coin.get("symbol", "").upper(),
            "chg_vs_btc_pct": round(chg, 2),
        })
        if chg > 0:
            outperform += 1

    if not results:
        return None

    pct = round((outperform / len(results)) * 100, 1)

    if pct >= 75:
        label = "🟢 Alt Season"
    elif pct >= 50:
        label = "🟡 Marché mixte"
    elif pct >= 25:
        label = "🟠 BTC Season"
    else:
        label = "🔴 BTC Season forte"

    return {
        "alt_season_pct": pct,
        "label":          label,
        "detail":         results,   # [{symbol, chg_vs_btc_pct}, …]
        "outperforming":  outperform,
        "total":          len(results),
    }
