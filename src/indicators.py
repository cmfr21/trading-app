"""
Indicateurs techniques — Méthode Péloille v5 (Trading with Ichimoku).

Hiérarchie des signaux (du plus au moins important) :
  1. Nuage (Kumo)       — tendance de fond, zones de support/résistance
  2. Kijun Sen          — signal d'entrée principal (rupture du Kijun)
  3. Lagging Span       — validateur absolu (doit être libre d'obstacles)
  4. Senkou Span B/A    — qualité du nuage, twist à venir
  5. Tenkan Sen         — momentum court terme, alerte uniquement

Paramètres Hosoda originaux : Tenkan=9, Kijun=26, Senkou B=52, déplacement=26.

Nouveautés v5 :
  - _detect_flat_levels         : niveaux plats Kijun/SSB/SSA (aimants de prix)
  - _analyze_chikou_detail      : analyse riche Chikou (clearance_score 0-100, obstacles)
  - _classify_market_regime     : régime de marché par TF (8 états)
  - _classify_kijun_signal      : type de signal Kijun (5 types)
  - _compute_extension_state    : état d'extension normalisé (5 états)
  - _compute_structural_bias    : biais directionnel structurel
  Toutes ces analyses enrichissent analyze_ichimoku() → analyze_tf().
"""

import logging
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

TENKAN_PERIOD   = 9
KIJUN_PERIOD    = 26
SENKOU_B_PERIOD = 52
DISPLACEMENT    = 26


# ──────────────────────────────────────────────────────────────────────────────
# CALCULS ICHIMOKU DE BASE
# ──────────────────────────────────────────────────────────────────────────────

def _mid(df, period):
    return (df["high"].rolling(period).max() + df["low"].rolling(period).min()) / 2


def compute_ichimoku(df):
    df = df.copy()
    df["tenkan"] = _mid(df, TENKAN_PERIOD)
    df["kijun"]  = _mid(df, KIJUN_PERIOD)
    df["ssa"]    = ((df["tenkan"] + df["kijun"]) / 2).shift(DISPLACEMENT)
    df["ssb"]    = _mid(df, SENKOU_B_PERIOD).shift(DISPLACEMENT)
    df["chikou"] = df["close"].shift(-DISPLACEMENT)
    return df


def _slope_pct(series: pd.Series, lookback: int = 20) -> float:
    """Pente relative d'une série sur N périodes (fraction, pas %)."""
    vals = series.dropna().iloc[-lookback:]
    if len(vals) < 2:
        return 0.0
    v0, v1 = float(vals.iloc[0]), float(vals.iloc[-1])
    return (v1 - v0) / (abs(v0) + 1e-10)


def _slope_label(slope_frac: float, threshold: float = 0.005) -> str:
    """Transforme une pente relative en label directionnel."""
    if abs(slope_frac) < threshold:
        return "flat"
    return "up" if slope_frac > 0 else "down"


def _vs(val, ref, tol=0.002) -> str:
    if ref is None or ref == 0:
        return "unknown"
    t = ref * tol
    if val > ref + t:   return "above"
    if val < ref - t:   return "below"
    return "at"


# ──────────────────────────────────────────────────────────────────────────────
# DÉTECTION DES NIVEAUX PLATS SIGNIFICATIFS
# ──────────────────────────────────────────────────────────────────────────────

def _detect_flat_levels(df: pd.DataFrame, price: float, atr: float) -> list:
    """
    Identifie les niveaux Ichimoku plats (Kijun, SSB, SSA) qui agissent
    comme aimants de prix ou obstacles structurels.

    Un niveau est "plat" si sa pente sur 20 périodes est < 0.5%.
    Retourne une liste ordonnée par proximité au prix courant.
    """
    df_i = compute_ichimoku(df)
    flat_levels = []
    atr_val = atr if atr and atr > 0 else (price * 0.01)

    def _check_series(series, name):
        slope = _slope_pct(series, 20)
        if abs(slope) >= 0.007:   # > 0.7% → pas plat
            return
        vals = series.dropna()
        if vals.empty:
            return
        level = float(vals.iloc[-1])
        if level <= 0:
            return
        dist_pct = abs(price - level) / level * 100
        dist_atr = abs(price - level) / atr_val
        role = "support" if level < price else "resistance"
        if abs(price - level) / level < 0.002:
            role = "equilibrium"   # prix quasiment sur le niveau
        flat_levels.append({
            "type":     name,
            "level":    round(level, 8),
            "slope":    round(slope * 100, 3),   # en % pour lisibilité
            "dist_pct": round(dist_pct, 2),
            "dist_atr": round(dist_atr, 2),
            "role":     role,
        })

    _check_series(df_i["kijun"], "kijun_flat")
    ssb_raw = _mid(df, SENKOU_B_PERIOD)
    _check_series(ssb_raw, "ssb_flat")
    ssa_raw = (df_i["tenkan"] + df_i["kijun"]) / 2
    _check_series(ssa_raw, "ssa_flat")

    flat_levels.sort(key=lambda x: x["dist_pct"])
    return flat_levels


# ──────────────────────────────────────────────────────────────────────────────
# ANALYSE CHIKOU ENRICHIE
# ──────────────────────────────────────────────────────────────────────────────

def _analyze_chikou_detail(df: pd.DataFrame, price: float, atr: float) -> dict:
    """
    Analyse détaillée du Lagging Span (Chikou Span).

    Le Chikou est la clôture actuelle reportée 26 périodes en arrière.
    Pour qu'une entrée soit valide (méthode Péloille), il doit être LIBRE
    d'obstacles dans la direction du trade.

    clearance_score (0–100) :
      100 = espace totalement libre (configuration idéale)
       70 = un obstacle mineur loin (> 5% de distance)
       40 = obstacles modérés ou obstacle proche
        0 = inside cloud ou plusieurs obstacles proches

    Obstacles scorés :
      - inside_cloud       : -40pts (bloquant majeur)
      - cloud_edge proche  : -20pts (< 3% de distance)
      - kijun_past proche  : -15pts (< 3%)
      - price_cluster      : -10pts par cluster dense
      - cloud_edge lointain: -10pts (3–8%)
      - kijun_past lointain: -8pts  (3–8%)
    """
    atr_val = atr if atr and atr > 0 else (price * 0.01)
    df_i = compute_ichimoku(df)

    obstacles     = []
    score_penalty = 0

    if len(df_i) < DISPLACEMENT + 5:
        return {
            "bias": "unknown", "clearance_score": 50, "is_free": False,
            "is_conflicted": False, "nearest_obstacle_type": None,
            "nearest_obstacle_dist_pct": None, "obstacle_density": "inconnue",
            "margin_before_obstacle_atr": None, "obstacles_count": 0,
            "obstacles": [],
        }

    # Chikou = clôture actuelle positionnée 26 bougies en arrière
    chikou_val = price
    idx = -DISPLACEMENT

    try:
        past_close = float(df_i["close"].iloc[idx])
        past_kijun = df_i["kijun"].iloc[idx]
        past_ssa   = df_i["ssa"].iloc[idx]
        past_ssb   = df_i["ssb"].iloc[idx]

        past_kijun = float(past_kijun) if pd.notna(past_kijun) else None
        past_ssa   = float(past_ssa)   if pd.notna(past_ssa)   else None
        past_ssb   = float(past_ssb)   if pd.notna(past_ssb)   else None

        # ── Biais de base : Chikou vs. prix passé ────────────────────────────
        tol = past_close * 0.003
        if   chikou_val > past_close + tol:    bias = "bullish"
        elif chikou_val < past_close - tol:    bias = "bearish"
        else:                                  bias = "neutral"

        # ── Obstacle 1 : inside cloud ou cloud edge ───────────────────────────
        if past_ssa is not None and past_ssb is not None:
            cloud_top    = max(past_ssa, past_ssb)
            cloud_bottom = min(past_ssa, past_ssb)
            cloud_mid    = (cloud_top + cloud_bottom) / 2

            if cloud_bottom < chikou_val < cloud_top:
                obstacles.append({
                    "type": "inside_cloud",
                    "level": round(cloud_mid, 8),
                    "dist_pct": 0.0,
                    "severity": "major",
                })
                score_penalty += 40
                bias = "conflicted"
            else:
                dist_top    = abs(chikou_val - cloud_top)    / (abs(chikou_val) + 1e-10) * 100
                dist_bottom = abs(chikou_val - cloud_bottom) / (abs(chikou_val) + 1e-10) * 100

                # Bord proche (< 3%) ou lointain (3–8%)
                for dist, level, label in [
                    (dist_top, cloud_top, "cloud_top"),
                    (dist_bottom, cloud_bottom, "cloud_bottom"),
                ]:
                    if dist < 3.0:
                        obstacles.append({
                            "type": "cloud_edge", "level": round(level, 8),
                            "dist_pct": round(dist, 2), "severity": "major",
                        })
                        score_penalty += 20
                    elif dist < 8.0:
                        obstacles.append({
                            "type": "cloud_edge", "level": round(level, 8),
                            "dist_pct": round(dist, 2), "severity": "minor",
                        })
                        score_penalty += 10

        # ── Obstacle 2 : Kijun du passé ──────────────────────────────────────
        if past_kijun is not None:
            dist_kijun = abs(chikou_val - past_kijun) / (abs(chikou_val) + 1e-10) * 100
            if dist_kijun < 3.0:
                obstacles.append({
                    "type": "kijun_past", "level": round(past_kijun, 8),
                    "dist_pct": round(dist_kijun, 2), "severity": "major",
                })
                score_penalty += 15
            elif dist_kijun < 8.0:
                obstacles.append({
                    "type": "kijun_past", "level": round(past_kijun, 8),
                    "dist_pct": round(dist_kijun, 2), "severity": "minor",
                })
                score_penalty += 8

        # ── Obstacle 3 : clusters de prix sur les 5–26 dernières bougies ─────
        # On regarde les highs/lows proches du niveau chikou dans la fenêtre passée
        window_start = max(0, len(df_i) + idx - 10)
        window_end   = len(df_i) + idx
        if window_end > window_start:
            h_arr = df_i["high"].values[window_start:window_end]
            l_arr = df_i["low"].values[window_start:window_end]
            price_arr = np.concatenate([h_arr, l_arr])
            price_arr = price_arr[~np.isnan(price_arr)]
            tol_cluster = chikou_val * 0.015   # 1.5% de tolerance
            clusters = [p for p in price_arr if abs(p - chikou_val) < tol_cluster]
            if len(clusters) >= 4:
                obstacles.append({
                    "type": "price_cluster", "level": round(float(np.mean(clusters)), 8),
                    "dist_pct": 0.5, "severity": "minor",
                })
                score_penalty += 10

    except Exception as e:
        logger.debug(f"  _analyze_chikou_detail : {e}")
        bias = "unknown"

    # ── Score final ───────────────────────────────────────────────────────────
    clearance_score = max(0, min(100, 100 - score_penalty))
    n_obstacles     = len(obstacles)
    is_free         = (clearance_score >= 70 and n_obstacles == 0)
    is_conflicted   = (clearance_score < 40 or any(o["severity"] == "major" for o in obstacles))

    if n_obstacles == 0:
        density = "faible"
    elif n_obstacles <= 2:
        density = "modérée"
    else:
        density = "élevée"

    # Obstacle le plus proche
    nearest     = None
    nearest_atr = None
    if obstacles:
        nearest = min(obstacles, key=lambda o: o.get("dist_pct", 999))
        if atr_val > 0 and nearest.get("dist_pct") is not None:
            nearest_atr = round(
                nearest["dist_pct"] / 100 * abs(chikou_val) / atr_val, 2
            )

    return {
        "bias":                       bias,
        "clearance_score":            clearance_score,
        "is_free":                    is_free,
        "is_conflicted":              is_conflicted,
        "nearest_obstacle_type":      nearest["type"]     if nearest else None,
        "nearest_obstacle_dist_pct":  nearest["dist_pct"] if nearest else None,
        "obstacle_density":           density,
        "margin_before_obstacle_atr": nearest_atr,
        "obstacles_count":            n_obstacles,
        "obstacles":                  obstacles,
    }


# ──────────────────────────────────────────────────────────────────────────────
# CLASSIFICATION DU RÉGIME DE MARCHÉ
# ──────────────────────────────────────────────────────────────────────────────

def _classify_market_regime(
    ichi: dict,
    range_analysis: dict,
    momentum: dict,
    kijun_dist_atr: float | None,
) -> str:
    """
    Identifie le régime de marché sur ce timeframe.

    Régimes (par ordre de priorité) :
      range              — range/consolidation détecté (score ≥ 3)
      overextended       — prix trop loin du Kijun (> 5 ATR)
      trending_up        — tendance haussière saine
      trending_down      — tendance baissière saine
      breakout_bullish   — cassure haussière récente (kijun_break + above cloud)
      breakout_bearish   — cassure baissière récente
      pullback_bullish   — repli bullish (inside cloud mais cloud bullish)
      pullback_bearish   — repli bearish
      transition         — changement de tendance en cours
      conflicted         — signaux contradictoires
    """
    if range_analysis.get("is_range"):
        return "range"

    price_vs_cloud  = ichi.get("price_vs_cloud", "inside")
    cloud_color     = ichi.get("cloud_color", "neutral")
    kijun_break     = ichi.get("kijun_break")
    kijun_slope     = ichi.get("kijun_slope", "flat")
    tenkan_slope    = ichi.get("tenkan_slope", "flat")
    price_vs_kijun  = ichi.get("price_vs_kijun", "at")
    future_twist    = ichi.get("future_twist", False)

    # Surextension
    if kijun_dist_atr is not None and kijun_dist_atr > 5:
        return "overextended"

    # Breakout récent (break Kijun dans les 5 dernières bougies)
    if kijun_break == "bull_break" and price_vs_cloud in ("above", "inside"):
        return "breakout_bullish"
    if kijun_break == "bear_break" and price_vs_cloud in ("below", "inside"):
        return "breakout_bearish"

    # Tendance saine
    if (price_vs_cloud == "above" and cloud_color == "bullish"
            and kijun_slope == "up" and tenkan_slope == "up"
            and price_vs_kijun == "above"):
        return "trending_up"

    if (price_vs_cloud == "below" and cloud_color == "bearish"
            and kijun_slope == "down" and tenkan_slope == "down"
            and price_vs_kijun == "below"):
        return "trending_down"

    # Pullback dans la tendance
    if price_vs_cloud == "inside":
        if cloud_color == "bullish":
            return "pullback_bullish"
        if cloud_color == "bearish":
            return "pullback_bearish"
        return "transition"

    # Transition / twist imminent
    if future_twist:
        return "transition"

    # Directions contradictoires
    bullish_signals = sum([
        price_vs_cloud == "above",
        cloud_color == "bullish",
        kijun_slope == "up",
        tenkan_slope == "up",
        price_vs_kijun == "above",
    ])
    if 2 <= bullish_signals <= 3:
        return "conflicted"

    # Tendances moins pures
    if bullish_signals >= 4:
        return "trending_up"
    if bullish_signals <= 1:
        return "trending_down"

    return "transition"


# ──────────────────────────────────────────────────────────────────────────────
# CLASSIFICATION DU SIGNAL KIJUN
# ──────────────────────────────────────────────────────────────────────────────

def _classify_kijun_signal(
    df: pd.DataFrame,
    ichi: dict,
    momentum: dict,
    regime: str,
) -> str:
    """
    Distingue les différents types de signal Kijun.

    Types :
      fresh_break           — rupture nette dans les 3 dernières bougies
      reclaim_after_pullback — retour bullish/bearish après pullback propre
      late_extension        — prix déjà très étendu (> 3 ATR du Kijun)
      weak_cross_equilibrium — croisement dans une zone de compression/range
      failed_break          — rupture avortée (prix revenu de l'autre côté)
      none                  — aucun signal Kijun actif
    """
    kijun_break    = ichi.get("kijun_break")
    kijun_dist_atr = momentum.get("kijun_atr_distance")
    kijun_slope    = ichi.get("kijun_slope", "flat")

    # Pas de signal Kijun actif
    if not kijun_break:
        if kijun_dist_atr and kijun_dist_atr > 3:
            return "late_extension"
        return "none"

    # Vérifier si le break est frais (≤ 3 bougies) ou plus ancien
    df_i = compute_ichimoku(df)
    recent_break = False
    if len(df_i) >= 4:
        rc = df_i["close"].values[-3:]
        rk = df_i["kijun"].values[-3:]
        for i in range(1, len(rc)):
            if np.isnan(rk[i]) or np.isnan(rk[i-1]):
                continue
            if rc[i-1] < rk[i-1] and rc[i] > rk[i]:
                recent_break = (kijun_break == "bull_break")
                break
            if rc[i-1] > rk[i-1] and rc[i] < rk[i]:
                recent_break = (kijun_break == "bear_break")
                break

    # Range → signal faible quel que soit le type
    if regime == "range":
        return "weak_cross_equilibrium"

    # Kijun plat → signal faible (Kijun horizontal = zone d'équilibre)
    if kijun_slope == "flat":
        return "weak_cross_equilibrium"

    # Break mais prix déjà trop étendu → entrée tardive
    if kijun_dist_atr and kijun_dist_atr > 3:
        return "late_extension"

    # Vérifier si le break est une reprise après pullback
    # (le prix a oscillé autour du Kijun récemment avant de casser)
    if len(df_i) >= 10:
        c_arr = df_i["close"].values[-10:]
        k_arr = df_i["kijun"].values[-10:]
        n_cross_10 = 0
        for i in range(1, len(c_arr)):
            if np.isnan(k_arr[i]) or np.isnan(k_arr[i-1]):
                continue
            if (c_arr[i] - k_arr[i]) * (c_arr[i-1] - k_arr[i-1]) < 0:
                n_cross_10 += 1
        if n_cross_10 >= 2 and recent_break:
            return "reclaim_after_pullback"

    # Vérifier si le break a échoué (prix est revenu de l'autre côté)
    if kijun_break == "bull_break":
        price_vs_kijun = ichi.get("price_vs_kijun")
        if price_vs_kijun == "below":
            return "failed_break"
    if kijun_break == "bear_break":
        price_vs_kijun = ichi.get("price_vs_kijun")
        if price_vs_kijun == "above":
            return "failed_break"

    if recent_break:
        return "fresh_break"

    return "none"


# ──────────────────────────────────────────────────────────────────────────────
# ÉTAT D'EXTENSION
# ──────────────────────────────────────────────────────────────────────────────

def _compute_extension_state(ichi: dict, momentum: dict, price: float) -> dict:
    """
    Mesure l'extension du prix par rapport à ses niveaux d'équilibre Ichimoku.

    États (basés sur la distance Kijun en unités ATR) :
      healthy        — < 2 ATR  : zone d'entrée normale
      mild_extension — 2–3 ATR  : acceptable, surveillance accrue
      extended       — 3–4 ATR  : attendre pullback idéalement
      overextended   — 4–6 ATR  : entrée très risquée
      euphoric       — > 6 ATR  : éviter toute entrée

    normalized_extension (0–100) : 0 = au Kijun, 100 = extrême
    """
    kijun_dist_atr = momentum.get("kijun_atr_distance")
    kijun          = ichi.get("kijun")
    cloud_top      = ichi.get("cloud_top")
    cloud_bottom   = ichi.get("cloud_bottom")

    # Distance au milieu du nuage
    cloud_midpoint_dist_pct = None
    if cloud_top and cloud_bottom and price > 0:
        mid = (cloud_top + cloud_bottom) / 2
        cloud_midpoint_dist_pct = round(abs(price - mid) / mid * 100, 2)

    if kijun_dist_atr is None:
        return {
            "state": "healthy",
            "normalized_extension": 0,
            "kijun_dist_atr": None,
            "cloud_midpoint_dist_pct": cloud_midpoint_dist_pct,
        }

    # État qualitatif
    if kijun_dist_atr < 2:
        state = "healthy"
        norm  = round(kijun_dist_atr / 2 * 30, 1)      # 0–30
    elif kijun_dist_atr < 3:
        state = "mild_extension"
        norm  = round(30 + (kijun_dist_atr - 2) * 20, 1)  # 30–50
    elif kijun_dist_atr < 4:
        state = "extended"
        norm  = round(50 + (kijun_dist_atr - 3) * 20, 1)  # 50–70
    elif kijun_dist_atr < 6:
        state = "overextended"
        norm  = round(70 + (kijun_dist_atr - 4) / 2 * 20, 1)  # 70–90
    else:
        state = "euphoric"
        norm  = min(100, round(90 + (kijun_dist_atr - 6) * 2.5, 1))

    return {
        "state":                   state,
        "normalized_extension":    min(100, norm),
        "kijun_dist_atr":          round(kijun_dist_atr, 2),
        "cloud_midpoint_dist_pct": cloud_midpoint_dist_pct,
    }


# ──────────────────────────────────────────────────────────────────────────────
# BIAIS STRUCTUREL
# ──────────────────────────────────────────────────────────────────────────────

def _compute_structural_bias(ichi: dict, regime: str, extension: dict) -> str:
    """
    Biais directionnel structurel combinant nuage, régime et extension.
    bullish / bearish / neutral / conflicted
    """
    price_vs_cloud = ichi.get("price_vs_cloud", "inside")
    cloud_color    = ichi.get("cloud_color", "neutral")
    ext_state      = extension.get("state", "healthy")

    # Surextension → biais dégradé (retour à la moyenne probable)
    if ext_state in ("overextended", "euphoric"):
        if price_vs_cloud == "above":
            return "conflicted"   # bullish mais suracheté
        if price_vs_cloud == "below":
            return "conflicted"   # bearish mais survendu

    # Range → neutre
    if regime == "range":
        return "neutral"

    # Tendance claire
    if regime in ("trending_up", "breakout_bullish"):
        return "bullish"
    if regime in ("trending_down", "breakout_bearish"):
        return "bearish"

    # Pullback dans tendance
    if regime == "pullback_bullish" and cloud_color == "bullish":
        return "bullish"
    if regime == "pullback_bearish" and cloud_color == "bearish":
        return "bearish"

    # Transition / conflicted
    if price_vs_cloud == "inside":
        return "conflicted"

    # Heuristique composite
    bullish_pts = sum([
        price_vs_cloud == "above",
        cloud_color == "bullish",
        ichi.get("kijun_slope") == "up",
        ichi.get("tenkan_slope") == "up",
    ])
    if bullish_pts >= 3:
        return "bullish"
    if bullish_pts <= 1:
        return "bearish"
    return "neutral"


# ──────────────────────────────────────────────────────────────────────────────
# ANALYSE ICHIMOKU PRINCIPALE
# ──────────────────────────────────────────────────────────────────────────────

def analyze_ichimoku(df):
    """
    Analyse Ichimoku complète enrichie (v5).

    En plus des champs classiques, retourne :
      market_regime     — régime de marché (8 états)
      kijun_signal_type — type de signal Kijun (5 types)
      structural_bias   — biais structurel (bullish/bearish/neutral/conflicted)
      extension_state   — état d'extension (dict complet)
      chikou_analysis   — analyse Chikou enrichie (clearance_score, obstacles…)
      flat_levels       — niveaux plats détectés (liste ordonnée par proximité)
    """
    df = compute_ichimoku(df)
    if len(df) < SENKOU_B_PERIOD + DISPLACEMENT + 5:
        return {}

    last  = df.iloc[-1]
    price = float(last["close"])
    tenkan = float(last["tenkan"]) if pd.notna(last["tenkan"]) else None
    kijun  = float(last["kijun"])  if pd.notna(last["kijun"])  else None
    ssa    = float(last["ssa"])    if pd.notna(last["ssa"])    else None
    ssb    = float(last["ssb"])    if pd.notna(last["ssb"])    else None

    if kijun is None or ssa is None or ssb is None:
        return {}

    cloud_top    = max(ssa, ssb)
    cloud_bottom = min(ssa, ssb)

    if price > cloud_top:       price_vs_cloud = "above"
    elif price < cloud_bottom:  price_vs_cloud = "below"
    else:                       price_vs_cloud = "inside"

    cloud_color = "bullish" if ssa > ssb else ("bearish" if ssb > ssa else "neutral")
    mid_cloud   = (cloud_top + cloud_bottom) / 2 if (cloud_top + cloud_bottom) > 0 else 1
    cloud_thickness_pct = round(abs(cloud_top - cloud_bottom) / mid_cloud * 100, 2)

    # Twist à venir
    future_twist = False
    try:
        ssa_raw = (df["tenkan"] + df["kijun"]) / 2
        ssb_raw = _mid(df, SENKOU_B_PERIOD)
        for i in range(-26, -1):
            if len(ssa_raw) > abs(i) + 1:
                a1, b1 = float(ssa_raw.iloc[i]), float(ssb_raw.iloc[i])
                a2, b2 = float(ssa_raw.iloc[i+1]), float(ssb_raw.iloc[i+1])
                if not any(np.isnan([a1,b1,a2,b2])) and (a1>b1) != (a2>b2):
                    future_twist = True
                    break
    except Exception:
        pass

    kijun_slope_raw  = _slope_pct(df["kijun"], 20)
    tenkan_slope_raw = _slope_pct(df["tenkan"], 10)
    kijun_slope      = _slope_label(kijun_slope_raw, threshold=0.005)
    tenkan_slope     = _slope_label(tenkan_slope_raw, threshold=0.005)

    price_vs_kijun  = _vs(price, kijun)
    price_vs_tenkan = _vs(price, tenkan) if tenkan else "unknown"
    kijun_distance_pct = round(abs(price - kijun) / kijun * 100, 2) if kijun else 0

    # Rupture Kijun récente (5 dernières bougies)
    kijun_break = None
    if len(df) >= 5:
        rc = df["close"].values[-5:]
        rk = df["kijun"].values[-5:]
        for i in range(1, len(rc)):
            if np.isnan(rk[i]) or np.isnan(rk[i-1]):
                continue
            if rc[i-1] < rk[i-1] and rc[i] > rk[i]:
                kijun_break = "bull_break"
            elif rc[i-1] > rk[i-1] and rc[i] < rk[i]:
                kijun_break = "bear_break"

    # Analyse Chikou basique (conservée pour compatibilité)
    chikou_vs_prices = "unknown"
    chikou_vs_kijun  = "unknown"
    chikou_free_basic = False

    if len(df) >= DISPLACEMENT + 3:
        idx = -DISPLACEMENT
        past_close = float(df["close"].iloc[idx])
        past_kijun = df["kijun"].iloc[idx]
        past_ssa   = df["ssa"].iloc[idx]
        past_ssb   = df["ssb"].iloc[idx]

        past_kijun = float(past_kijun) if pd.notna(past_kijun) else None
        past_ssa   = float(past_ssa)   if pd.notna(past_ssa)   else None
        past_ssb   = float(past_ssb)   if pd.notna(past_ssb)   else None

        tol = past_close * 0.002
        if   price > past_close + tol: chikou_vs_prices = "above"
        elif price < past_close - tol: chikou_vs_prices = "below"
        else:                          chikou_vs_prices = "at"

        if past_kijun:
            tk = past_kijun * 0.002
            if   price > past_kijun + tk: chikou_vs_kijun = "above"
            elif price < past_kijun - tk: chikou_vs_kijun = "below"
            else:                         chikou_vs_kijun = "at"

        obs = 0
        if past_kijun and abs(price - past_kijun) / (abs(price) + 1e-10) < 0.03:
            obs += 1
        if past_ssa and past_ssb:
            p_top = max(past_ssa, past_ssb)
            p_bot = min(past_ssa, past_ssb)
            if p_bot < price < p_top:
                chikou_vs_prices = "inside_cloud"
                obs += 2
            elif abs(price - p_top) / (abs(price) + 1e-10) < 0.03: obs += 1
            elif abs(price - p_bot) / (abs(price) + 1e-10) < 0.03: obs += 1
        chikou_free_basic = (obs == 0)

    key_levels = {}
    if tenkan: key_levels["tenkan"] = round(tenkan, 8)
    if kijun:  key_levels["kijun"]  = round(kijun,  8)
    if ssa:    key_levels["ssa"]    = round(ssa,    8)
    if ssb:    key_levels["ssb"]    = round(ssb,    8)

    # ── Construction du dict de base ──────────────────────────────────────────
    ichi_base = {
        "price_vs_cloud":      price_vs_cloud,
        "cloud_color":         cloud_color,
        "cloud_thickness_pct": cloud_thickness_pct,
        "future_twist":        future_twist,
        "kijun_break":         kijun_break,
        "kijun_distance_pct":  kijun_distance_pct,
        "kijun_slope":         kijun_slope,
        "tenkan_slope":        tenkan_slope,
        "price_vs_tenkan":     price_vs_tenkan,
        "price_vs_kijun":      price_vs_kijun,
        "chikou_vs_prices":    chikou_vs_prices,
        "chikou_vs_kijun":     chikou_vs_kijun,
        "chikou_free":         chikou_free_basic,
        "chikou_obstacles":    0,                  # rempli par chikou_analysis
        "key_levels":          key_levels,
        "tenkan":       tenkan,
        "kijun":        kijun,
        "ssa":          ssa,
        "ssb":          ssb,
        "price":        price,
        "cloud_top":    round(cloud_top,    8),
        "cloud_bottom": round(cloud_bottom, 8),
    }

    return ichi_base


# ──────────────────────────────────────────────────────────────────────────────
# INDICATEURS COMPLÉMENTAIRES
# ──────────────────────────────────────────────────────────────────────────────

def compute_rsi(close, period=14):
    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(com=period-1, min_periods=period).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=period-1, min_periods=period).mean()
    rsi   = 100 - (100 / (1 + gain / (loss + 1e-10)))
    return round(float(rsi.iloc[-1]), 2)


def compute_atr(df, period=14):
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
    return round(float(tr.rolling(period).mean().iloc[-1]), 8)


def compute_volatility_90d(df):
    closes = df["close"].dropna()
    if len(closes) < 10:
        return 50.0
    return round(float(closes.pct_change().dropna().tail(90).std()) * 100, 4)


def compute_moving_averages(df):
    c = df["close"]
    return {f"ma{p}": round(float(c.rolling(p).mean().iloc[-1]), 8)
            for p in [20, 50, 200] if len(c) >= p}


def detect_candlestick_patterns(df):
    if len(df) < 3: return []
    patterns = []
    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    n = len(df) - 1

    def body(i):  return abs(c[i] - o[i])
    def upper(i): return h[i] - max(c[i], o[i])
    def lower(i): return min(c[i], o[i]) - l[i]
    def rng(i):   return h[i] - l[i]
    def bull(i):  return c[i] > o[i]
    def bear(i):  return c[i] < o[i]
    avg = np.mean([body(i) for i in range(max(0, n-10), n+1)]) + 1e-10

    # Singles
    if lower(n) >= 2*body(n) and upper(n) < body(n) and body(n) < avg:
        patterns.append({"name":"Hammer","direction":"bullish","strength":"medium"})
    if upper(n) >= 2*body(n) and lower(n) < body(n)*0.5 and bear(n) and body(n) < avg:
        patterns.append({"name":"Shooting Star","direction":"bearish","strength":"medium"})
    if lower(n) >= 2*body(n) and upper(n) < body(n)*0.5 and bear(n):
        patterns.append({"name":"Hanging Man","direction":"bearish","strength":"medium"})
    if body(n) < avg*0.1 and rng(n) > 0:
        patterns.append({"name":"Doji","direction":"neutral","strength":"weak"})
    if body(n) < avg*0.1 and lower(n) >= rng(n)*0.7:
        patterns.append({"name":"Dragonfly Doji","direction":"bullish","strength":"medium"})
    if body(n) < avg*0.1 and upper(n) >= rng(n)*0.7:
        patterns.append({"name":"Tombstone Doji","direction":"bearish","strength":"medium"})
    if bull(n) and body(n) >= avg*1.5 and upper(n) < body(n)*0.05 and lower(n) < body(n)*0.05:
        patterns.append({"name":"Bullish Marubozu","direction":"bullish","strength":"strong"})
    if bear(n) and body(n) >= avg*1.5 and upper(n) < body(n)*0.05 and lower(n) < body(n)*0.05:
        patterns.append({"name":"Bearish Marubozu","direction":"bearish","strength":"strong"})

    # Doubles
    if n >= 1:
        p = n - 1
        if bear(p) and bull(n) and o[n]<=c[p] and c[n]>=o[p] and body(n)>body(p):
            patterns.append({"name":"Bullish Engulfing","direction":"bullish","strength":"strong"})
        if bull(p) and bear(n) and o[n]>=c[p] and c[n]<=o[p] and body(n)>body(p):
            patterns.append({"name":"Bearish Engulfing","direction":"bearish","strength":"strong"})
        if bear(p) and bull(n) and c[n]<o[p] and o[n]>c[p] and body(n)<body(p)*0.6:
            patterns.append({"name":"Bullish Harami","direction":"bullish","strength":"medium"})
        if bull(p) and bear(n) and c[n]>o[p] and o[n]<c[p] and body(n)<body(p)*0.6:
            patterns.append({"name":"Bearish Harami","direction":"bearish","strength":"medium"})
        if bear(p) and bull(n) and o[n]<l[p] and c[n]>(o[p]+c[p])/2 and c[n]<o[p]:
            patterns.append({"name":"Piercing Line","direction":"bullish","strength":"medium"})
        if bull(p) and bear(n) and o[n]>h[p] and c[n]<(o[p]+c[p])/2 and c[n]>o[p]:
            patterns.append({"name":"Dark Cloud Cover","direction":"bearish","strength":"medium"})
        if bear(p) and bull(n) and o[n]>o[p] and body(n)>=avg*1.2:
            patterns.append({"name":"Bullish Kicker","direction":"bullish","strength":"strong"})
        if bull(p) and bear(n) and o[n]<o[p] and body(n)>=avg*1.2:
            patterns.append({"name":"Bearish Kicker","direction":"bearish","strength":"strong"})

    # Triples
    if n >= 2:
        p1, p2 = n-2, n-1
        if bear(p1) and body(p2)<avg*0.5 and bull(n) and c[n]>(o[p1]+c[p1])/2:
            patterns.append({"name":"Morning Star","direction":"bullish","strength":"strong"})
        if bull(p1) and body(p2)<avg*0.5 and bear(n) and c[n]<(o[p1]+c[p1])/2:
            patterns.append({"name":"Evening Star","direction":"bearish","strength":"strong"})
        if (bull(p1) and bull(p2) and bull(n) and c[p2]>c[p1] and c[n]>c[p2]
                and body(p1)>=avg*0.8 and body(p2)>=avg*0.8 and body(n)>=avg*0.8):
            patterns.append({"name":"Three White Soldiers","direction":"bullish","strength":"strong"})
        if (bear(p1) and bear(p2) and bear(n) and c[p2]<c[p1] and c[n]<c[p2]
                and body(p1)>=avg*0.8 and body(p2)>=avg*0.8 and body(n)>=avg*0.8):
            patterns.append({"name":"Three Black Crows","direction":"bearish","strength":"strong"})
        if bear(p1) and bull(p2) and bull(n) and body(p2)<body(p1) and c[n]>o[p1]:
            patterns.append({"name":"Three Inside Up","direction":"bullish","strength":"medium"})
        if bull(p1) and bear(p2) and bear(n) and body(p2)<body(p1) and c[n]<o[p1]:
            patterns.append({"name":"Three Inside Down","direction":"bearish","strength":"medium"})

    return patterns


# ──────────────────────────────────────────────────────────────────────────────
# DÉTECTION RANGE / MOMENTUM
# ──────────────────────────────────────────────────────────────────────────────

def detect_range_market(df: pd.DataFrame) -> dict:
    """
    Détecte un marché en range / consolidation où Ichimoku est peu fiable.

    6 critères (score 0-6) :
      1. Kijun plate sur 20 périodes (< 0.5%)
      2. SSB plate sur 20 périodes (Kumo sans direction, < 0.3%)
      3. Prix croise le Kijun ≥ 3 fois sur les 20 dernières bougies
      4. ATR < 1.5% du prix — actif trop plat
      5. Tenkan plate sur 10 périodes (< 0.5%)
      6. Tenkan ≈ Kijun — compression extrême (< 0.5% d'écart)

    is_range = True si score ≥ 3
    """
    df_i    = compute_ichimoku(df)
    reasons = []
    score   = 0

    close_arr = df_i["close"].values
    kijun_arr = df_i["kijun"].values

    kijun_slope = _slope_pct(df_i["kijun"], 20)
    if abs(kijun_slope) < 0.005:
        reasons.append(f"Kijun plate ({kijun_slope*100:+.2f}%/20 bougies)")
        score += 1

    ssb_raw   = _mid(df, SENKOU_B_PERIOD)
    ssb_slope = _slope_pct(ssb_raw, 20)
    if abs(ssb_slope) < 0.003:
        reasons.append(f"SSB plate ({ssb_slope*100:+.2f}%/20) — Kumo sans direction")
        score += 1

    lookback = min(20, len(df_i) - 1)
    n_cross  = 0
    for i in range(1, lookback):
        ci, ki = close_arr[-i],   kijun_arr[-i]
        cp, kp = close_arr[-i-1], kijun_arr[-i-1]
        if not any(np.isnan(v) for v in [ci, ki, cp, kp]):
            if (ci - ki) * (cp - kp) < 0:
                n_cross += 1
    if n_cross >= 3:
        reasons.append(f"Prix croise Kijun {n_cross}× (20 dernières bougies)")
        score += 1

    try:
        atr_val    = compute_atr(df)
        last_close = float(df_i["close"].iloc[-1])
        if last_close > 0 and atr_val / last_close < 0.015:
            reasons.append(f"ATR faible ({atr_val/last_close*100:.2f}% du prix)")
            score += 1
    except Exception:
        pass

    tenkan_slope = _slope_pct(df_i["tenkan"], 10)
    if abs(tenkan_slope) < 0.005:
        reasons.append(f"Tenkan plate ({tenkan_slope*100:+.2f}%/10 bougies)")
        score += 1

    try:
        tk = float(df_i["tenkan"].dropna().iloc[-1])
        kj = float(df_i["kijun"].dropna().iloc[-1])
        if abs(tk - kj) / (abs(kj) + 1e-10) < 0.005:
            reasons.append("Tenkan ≈ Kijun (compression — écart < 0.5%)")
            score += 1
    except Exception:
        pass

    return {"score": score, "is_range": score >= 3, "reasons": reasons}


def compute_momentum_metrics(df: pd.DataFrame) -> dict:
    """
    Métriques de momentum — détection des entrées tardives.

    Retourne :
      kijun_distance_pct  : distance prix / Kijun en %
      kijun_atr_distance  : distance prix / Kijun exprimée en unités ATR
      tenkan_speed_pct    : pente Tenkan sur 5 bougies en %
      price_accel_3       : variation prix sur 3 bougies en %
    """
    df_i  = compute_ichimoku(df)
    price = float(df_i["close"].iloc[-1])

    kijun = None
    if not df_i["kijun"].dropna().empty:
        kijun = float(df_i["kijun"].dropna().iloc[-1])

    kijun_dist_pct = None
    kijun_atr_dist = None
    if kijun and kijun > 0:
        kijun_dist_pct = abs(price - kijun) / kijun * 100
        try:
            atr_val = compute_atr(df)
            if atr_val and atr_val > 0:
                kijun_atr_dist = abs(price - kijun) / atr_val
        except Exception:
            pass

    tenkan_speed = _slope_pct(df_i["tenkan"], 5) * 100

    closes      = df["close"].values
    price_accel = 0.0
    if len(closes) >= 4:
        price_accel = (closes[-1] - closes[-4]) / (abs(closes[-4]) + 1e-10) * 100

    return {
        "kijun_distance_pct": round(kijun_dist_pct, 2) if kijun_dist_pct is not None else None,
        "kijun_atr_distance": round(kijun_atr_dist, 2) if kijun_atr_dist is not None else None,
        "tenkan_speed_pct":   round(float(tenkan_speed), 3),
        "price_accel_3":      round(float(price_accel), 2),
    }


# ──────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE PRINCIPAL
# ──────────────────────────────────────────────────────────────────────────────

def analyze_tf(df, tf_key):
    """
    Analyse complète d'un timeframe — point d'entrée principal.

    Retourne un dict enrichi avec :
      ichi            : analyse Ichimoku de base + enrichissements v5
      rsi, atr, vol90 : indicateurs classiques
      mas             : moyennes mobiles (1d uniquement)
      candles         : patterns chandelier
      range_analysis  : détection range (6 critères)
      momentum        : métriques d'extension/momentum
      market_regime   : régime de marché (8 états)
      kijun_signal    : type de signal Kijun (5 types)
      extension_state : état d'extension (dict complet)
      structural_bias : biais directionnel structurel
      chikou_analysis : analyse Chikou enrichie (clearance_score 0-100)
      flat_levels     : niveaux plats détectés (aimants de prix)
    """
    if df is None or len(df) < SENKOU_B_PERIOD + DISPLACEMENT + 5:
        return {}

    # ── Calculs de base ───────────────────────────────────────────────────────
    ichi           = analyze_ichimoku(df)
    if not ichi:
        return {}

    atr_val        = compute_atr(df)
    range_analysis = detect_range_market(df)
    momentum       = compute_momentum_metrics(df)
    price          = float(df["close"].iloc[-1])

    # ── Analyses enrichies v5 ─────────────────────────────────────────────────
    kijun_dist_atr = momentum.get("kijun_atr_distance")

    market_regime  = _classify_market_regime(ichi, range_analysis, momentum, kijun_dist_atr)
    extension      = _compute_extension_state(ichi, momentum, price)
    kijun_signal   = _classify_kijun_signal(df, ichi, momentum, market_regime)
    structural_bias = _compute_structural_bias(ichi, market_regime, extension)
    chikou_analysis = _analyze_chikou_detail(df, price, atr_val)
    flat_levels    = _detect_flat_levels(df, price, atr_val)

    # Mise à jour des champs Chikou dans ichi pour compatibilité
    ichi["chikou_obstacles"] = chikou_analysis.get("obstacles_count", 0)
    ichi["chikou_free"]      = chikou_analysis.get("is_free", False)

    return {
        "tf":               tf_key,
        "ichi":             ichi,
        "rsi":              compute_rsi(df["close"]),
        "atr":              atr_val,
        "vol90":            compute_volatility_90d(df),
        "mas":              compute_moving_averages(df) if tf_key == "1d" else {},
        "candles":          detect_candlestick_patterns(df),
        "n_candles":        len(df),
        "range_analysis":   range_analysis,
        "momentum":         momentum,
        "market_regime":    market_regime,
        "kijun_signal":     kijun_signal,
        "extension_state":  extension,
        "structural_bias":  structural_bias,
        "chikou_analysis":  chikou_analysis,
        "flat_levels":      flat_levels,
    }
