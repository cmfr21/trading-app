"""Configuration centrale — v5 dynamique (top cryptos CoinGecko)."""

import os

# ─── Nombre de cryptos à analyser (top N par market cap) ─────────────────────
TOP_N_CRYPTOS = 20

# ─── Overrides Yahoo Finance ──────────────────────────────────────────────────
# Certains symboles n'ont pas de ticker standard {SYMBOL}-USD sur Yahoo Finance.
# Les valeurs ici remplacent la déduction automatique.
YAHOO_TICKER_OVERRIDES = {
    "TONUSDT": "TON11419-USD",   # Toncoin — ticker Yahoo non standard
}

# ─── 5 Timeframes d'analyse ───────────────────────────────────────────────────
TIMEFRAMES = {
    "1wk": {"label": "Hebdo",     "interval": "1wk", "period": "5y",  "min_candles": 100},
    "1d":  {"label": "Journalier","interval": "1d",  "period": "2y",  "min_candles": 200},
    "4h":  {"label": "4 Heures",  "interval": "1h",  "period": "60d", "min_candles": 100, "resample": "4h"},
    "1h":  {"label": "1 Heure",   "interval": "1h",  "period": "60d", "min_candles": 80},
    "15m": {"label": "15 Min",    "interval": "15m", "period": "30d", "min_candles": 80},
}

# ─── Poids par timeframe dans le score Ichimoku ───────────────────────────────
TF_WEIGHTS = {
    "1wk": 0.30,
    "1d":  0.25,
    "4h":  0.20,
    "1h":  0.15,
    "15m": 0.10,
}

# ─── Seuils de déclenchement ──────────────────────────────────────────────────
SCORE_THRESHOLD      = 70       # Score minimum pour alerter (relevé de 60 → 70)
MIN_TF_AGREE         = 3        # Nombre minimum de TF en accord
REQUIRE_WEEKLY_DAILY = True     # Exige au moins 1wk ou 1d aligné

# ─── Filtres de qualité ────────────────────────────────────────────────────────
MIN_RR_RATIO             = 2.0  # Ratio rendement/risque minimum — refus si < 2
MAX_KIJUN_EXTENSION_ATR  = 4.0  # Distance max prix/Kijun en unités ATR (entrée tardive)
RANGE_BLOCK_THRESHOLD    = 3    # Score range ≥ N sur 1d ET 4h → trade refusé
BTC_FILTER_ENABLED       = True # Filtre contexte BTC pour les altcoins

# ─── Seuils v5 (analyse hiérarchique) ────────────────────────────────────────
# Clearance Chikou minimum pour valider la direction (0-100)
CHIKOU_CLEARANCE_MIN     = 30   # En dessous → pénalité forte (bloquant si < 20)

# Score structure minimum (Phase 1, sur 40 pts) avant d'entrer en Phase 2
# Non utilisé comme filtre dur — informatif pour le logging
STRUCTURE_SCORE_MIN      = 15

# Score timing minimum (Phase 2, sur 30 pts)
# Non utilisé comme filtre dur — informatif pour le logging
TIMING_SCORE_MIN         = 8

# Slope threshold pour définir un niveau "plat" (fraction, pas %)
# 0.007 = moins de 0.7% de pente sur 20 périodes
FLAT_LEVEL_SLOPE_THRESH  = 0.007

# ─── Anti-doublon ─────────────────────────────────────────────────────────────
ALERT_COOLDOWN_HOURS   = 6      # cooldown de sécurité (fallback)
ALERT_MIN_SCORE_DELTA  = 10     # re-alerte si score amélioré d'au moins X pts
ALERT_PRICE_DELTA_PCT  = 5.0    # re-alerte si prix bougé d'au moins X% depuis dernière alerte
STATE_FILE             = "state/alerts.json"

# ─── Paramètres Ichimoku (Hosoda originaux) ───────────────────────────────────
TENKAN_PERIOD   = 9
KIJUN_PERIOD    = 26
SENKOU_B_PERIOD = 52
DISPLACEMENT    = 26

# ─── Moyennes mobiles ─────────────────────────────────────────────────────────
MA_SHORT = 50
MA_LONG  = 200

# ─── RSI / ATR ────────────────────────────────────────────────────────────────
RSI_PERIOD = 14
ATR_PERIOD = 14

# ─── Email ───────────────────────────────────────────────────────────────────
EMAIL_SENDER       = os.environ.get("EMAIL_SENDER", "")
EMAIL_PASSWORD     = os.environ.get("EMAIL_PASSWORD", "")
EMAIL_RECIPIENT    = os.environ.get("EMAIL_RECIPIENT", "")
MAX_OPPS_PER_EMAIL = 6

# ─── APIs ─────────────────────────────────────────────────────────────────────
COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"
