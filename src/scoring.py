"""
Scoring multi-timeframe v5 — Méthode Karen Péloille hiérarchique.

Architecture du score (100 pts) :
  ┌─ Phase 1 · Structure      40 pts  (1wk + 1d : régime, Chikou, extension)
  │   ├─ 1wk : régime + Chikou clearance + cloud          0–17 pts
  │   └─ 1d  : régime + Chikou clearance + cloud          0–23 pts
  ├─ Phase 2 · Timing         30 pts  (4h + 1h + 15m : signal Kijun, biais)
  │   ├─ 4h : signal Kijun × biais structurel             0–15 pts
  │   ├─ 1h : signal Kijun × biais structurel             0–10 pts
  │   └─ 15m : signal Kijun × biais (entry precision)     0–5  pts
  ├─ Phase 3 · Contexte       15 pts  (BTC + Alt Season)
  │   ├─ Alignement BTC                                   0–10 pts
  │   └─ Alt Season                                       0–5  pts
  └─ Phase 4 · Exécution      15 pts  (RSI + chandelier)
      ├─ RSI multi-TF                                      0–8  pts
      └─ Patterns chandelier                               0–7  pts

Conditions BLOQUANTES :
  1. Prix dans le nuage (Kumo) sur 1d ou 1wk
  2. Chikou Span du mauvais côté sur 1d (validateur absolu Péloille)
  3. Range sur 1d ET 4h simultanément
  4. Extension > MAX_KIJUN_EXTENSION_ATR (entrée tardive structurelle)

Filtres PÉNALISANTS :
  - Chikou obstacles (1d) : −5 à −15 pts
  - Range sur 1d seulement : −10 pts
  - Extension modérée 1d (2.5–4 ATR) : −5 pts
  - BTC défavorable : −5 à −15 pts
  - Signal Kijun tardif / échoué : déjà capturé en Phase 2

Labels qualitatifs (sans probabilité) :
  🔥 FORT        ≥ 85 pts
  ✅ CORRECT     ≥ 70 pts
  ⚠️ FAIBLE      ≥ 60 pts
  ❌ INSUFFISANT  < 60 pts

Trade readiness :
  ready     — score ≥ seuil ET signal timing frais
  wait      — score ≥ seuil mais timing non optimal
  degraded  — score < seuil ou pénalités importantes
  blocked   — condition bloquante déclenchée

Setup family :
  trend_continuation  — prix dans la tendance 1d (régime trending)
  breakout            — cassure récente (régime breakout)
  pullback            — repli dans la tendance 1d (régime pullback)
  counter_trend       — biais 1d opposé à la direction
  undefined           — données insuffisantes
"""

from src.config import (
    TF_WEIGHTS, REQUIRE_WEEKLY_DAILY, MIN_TF_AGREE,
    MAX_KIJUN_EXTENSION_ATR, BTC_FILTER_ENABLED,
)

# Poids legacy pour affichage email (80 pts) — maintien compatibilité
_ICHI_TOTAL = 80


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS INTERNES
# ──────────────────────────────────────────────────────────────────────────────

def _regime_score(regime: str, direction: str, max_pts: float) -> tuple:
    """
    Score basé sur le régime de marché détecté.
    Retourne (pts, label).
    """
    is_long = (direction == "LONG")

    regime_pts_map = {
        # Régimes haussiers (LONG) / baissiers (SHORT)
        "trending_up":       (1.00, "✅ Tendance haussière saine"),
        "trending_down":     (1.00, "✅ Tendance baissière saine"),
        "breakout_bullish":  (0.85, "✅ Cassure haussière en cours"),
        "breakout_bearish":  (0.85, "✅ Cassure baissière en cours"),
        "pullback_bullish":  (0.65, "⚠️ Pullback haussier (repli dans tendance)"),
        "pullback_bearish":  (0.65, "⚠️ Pullback baissier (repli dans tendance)"),
        "transition":        (0.30, "⚠️ Transition — tendance incertaine"),
        "conflicted":        (0.15, "❌ Signaux contradictoires"),
        "overextended":      (0.20, "⚠️ Prix surextensioné — retour à la moyenne probable"),
        "range":             (0.00, "❌ Marché en range — Ichimoku peu fiable"),
    }

    regime_pair = regime_pts_map.get(regime, (0.10, f"⚠️ Régime inconnu ({regime})"))
    pct, base_label = regime_pair

    # Vérifier l'alignement direction / régime
    bullish_regimes = {"trending_up", "breakout_bullish", "pullback_bullish"}
    bearish_regimes = {"trending_down", "breakout_bearish", "pullback_bearish"}

    if regime in bullish_regimes and not is_long:
        # Régime haussier mais direction SHORT → opposé
        pct = max(0.0, pct * 0.2)
        label = f"❌ Régime haussier vs SHORT — {base_label}"
    elif regime in bearish_regimes and is_long:
        # Régime baissier mais direction LONG → opposé
        pct = max(0.0, pct * 0.2)
        label = f"❌ Régime baissier vs LONG — {base_label}"
    else:
        label = base_label

    return round(pct * max_pts, 1), label


def _chikou_clearance_score_to_pts(clearance_score: float, bias: str,
                                   direction: str, max_pts: float) -> tuple:
    """
    Traduit le clearance_score Chikou (0-100) en points de scoring.
    """
    is_long   = (direction == "LONG")
    exp_bias  = "bullish" if is_long else "bearish"

    # Pénalité si biais opposé
    if bias in ("bullish", "bearish") and bias != exp_bias:
        label = f"❌ Chikou biais {bias} — invalide pour {direction}"
        return 0.0, label

    # Conversion clearance_score → pts
    if clearance_score >= 80:
        pct = 1.00
        icon = "✅"
    elif clearance_score >= 60:
        pct = 0.70
        icon = "⚠️"
    elif clearance_score >= 40:
        pct = 0.40
        icon = "⚠️"
    else:
        pct = 0.15
        icon = "❌"

    pts   = round(pct * max_pts, 1)
    label = (f"{icon} Chikou clearance {clearance_score:.0f}/100 — "
             f"{'espace libre' if clearance_score >= 70 else 'obstacles détectés'}")
    return pts, label


def _cloud_position_pts(ichi: dict, direction: str, max_pts: float) -> tuple:
    """Score basé sur la position prix/nuage + couleur du nuage."""
    is_long      = (direction == "LONG")
    pvcloud      = ichi.get("price_vs_cloud", "unknown")
    cloud_color  = ichi.get("cloud_color", "neutral")
    future_twist = ichi.get("future_twist", False)
    cloud_thick  = ichi.get("cloud_thickness_pct", 0.0)

    pts  = 0.0
    info = []

    # Position vs nuage
    if pvcloud == "inside":
        # Bloquant — capturé par filtre global, ici on donne 0
        info.append("🚫 Prix dans le nuage — zone d'incertitude")
    elif (pvcloud == "above" and is_long) or (pvcloud == "below" and not is_long):
        pts += max_pts * 0.60
        side = "au-dessus" if is_long else "en-dessous"
        info.append(f"✅ Prix {side} du nuage")
    else:
        info.append("❌ Prix du mauvais côté du nuage")

    # Couleur du nuage
    exp_color  = "bullish" if is_long else "bearish"
    if cloud_color == exp_color:
        pts += max_pts * 0.30
        name = "vert haussier" if is_long else "rouge baissier"
        info.append(f"✅ Nuage {name}")
    elif cloud_color == "neutral":
        pts += max_pts * 0.10
        info.append("⚠️ Nuage en transition")
    else:
        info.append("❌ Nuage couleur opposée")

    # Twist
    if future_twist:
        pts = max(0, pts - max_pts * 0.05)
        info.append("⚠️ Twist imminent — fragilité potentielle")

    # Épaisseur nuage
    if cloud_thick < 2.0 and pvcloud != "inside":
        pts += max_pts * 0.10
        info.append(f"✅ Nuage très fin ({cloud_thick:.1f}%)")
    elif cloud_thick > 12.0:
        info.append(f"⚠️ Nuage épais ({cloud_thick:.1f}%) — résistance solide")

    return min(round(pts, 1), max_pts), " | ".join(info)


def _structure_tf_score(ta: dict, direction: str,
                        max_regime: float, max_chikou: float, max_cloud: float) -> tuple:
    """
    Score de structure pour un TF macro (1wk ou 1d).

    Retourne : (total_pts, max_pts, info_list, is_aligned, is_blocked)
    """
    if not ta:
        return 0.0, max_regime + max_chikou + max_cloud, ["⚠️ Données indisponibles"], False, False

    ichi            = ta.get("ichi", {}) or {}
    market_regime   = ta.get("market_regime", "conflicted")
    chikou_analysis = ta.get("chikou_analysis", {}) or {}
    extension_state = ta.get("extension_state", {}) or {}
    is_long         = (direction == "LONG")
    is_blocked      = False
    info            = []

    # ── Régime de marché ──────────────────────────────────────────────────────
    r_pts, r_label = _regime_score(market_regime, direction, max_regime)
    info.append(r_label)

    # ── Chikou clearance ──────────────────────────────────────────────────────
    clearance_score = chikou_analysis.get("clearance_score", 50)
    chikou_bias     = chikou_analysis.get("bias", "neutral")
    c_pts, c_label  = _chikou_clearance_score_to_pts(
        clearance_score, chikou_bias, direction, max_chikou)
    info.append(c_label)

    # Obstacle Chikou → info supplémentaire
    n_obs = chikou_analysis.get("obstacles_count", 0)
    if n_obs > 0:
        nearest_type = chikou_analysis.get("nearest_obstacle_type", "")
        nearest_dist = chikou_analysis.get("nearest_obstacle_dist_pct")
        dist_txt = f" à {nearest_dist:.1f}%" if nearest_dist is not None else ""
        info.append(f"  Lagging Span : {n_obs} obstacle(s) — {nearest_type}{dist_txt}")

    # ── Position vs nuage ─────────────────────────────────────────────────────
    pvcloud = ichi.get("price_vs_cloud", "unknown")
    if pvcloud == "inside":
        is_blocked = True
        info.append("🚫 Prix dans le nuage (BLOQUANT Péloille)")
        cl_pts = 0.0
        cl_label = ""
    else:
        cl_pts, cl_label = _cloud_position_pts(ichi, direction, max_cloud)
        if cl_label:
            info.append(cl_label)

    # ── Extension ─────────────────────────────────────────────────────────────
    ext_state = extension_state.get("state", "healthy")
    kda       = extension_state.get("kijun_dist_atr")
    if ext_state in ("overextended", "euphoric"):
        info.append(f"⚠️ Extension {ext_state} ({kda:.1f}× ATR) — entrée risquée")
    elif ext_state == "extended":
        info.append(f"⚠️ Extension élevée ({kda:.1f}× ATR) — pullback conseillé")
    elif ext_state == "mild_extension" and kda:
        info.append(f"➡️ Extension modérée ({kda:.1f}× ATR)")

    total_pts = r_pts + c_pts + (cl_pts if not is_blocked else 0.0)
    max_pts   = max_regime + max_chikou + max_cloud
    is_aligned = (total_pts >= max_pts * 0.50) and not is_blocked

    return round(total_pts, 1), max_pts, info, is_aligned, is_blocked


def _timing_tf_score(ta: dict, direction: str, max_pts: float) -> tuple:
    """
    Score de timing pour un TF intermédiaire (4h, 1h, 15m).

    Basé sur : signal Kijun + biais structurel + momentum
    Retourne : (pts, max_pts, info_list, is_aligned, is_blocked)
    """
    if not ta:
        return 0.0, max_pts, ["⚠️ Données indisponibles"], False, False

    kijun_signal    = ta.get("kijun_signal",    "none")
    structural_bias = ta.get("structural_bias", "neutral")
    extension_state = ta.get("extension_state", {}) or {}
    ichi            = ta.get("ichi",            {}) or {}
    is_long         = (direction == "LONG")
    is_blocked      = False
    info            = []

    exp_bias = "bullish" if is_long else "bearish"

    # ── Kijun signal quality ──────────────────────────────────────────────────
    signal_quality = {
        "fresh_break":              1.00,
        "reclaim_after_pullback":   0.80,
        "none":                     0.45,   # prix sur le bon côté sans signal
        "late_extension":           0.20,
        "weak_cross_equilibrium":   0.15,
        "failed_break":             0.00,
    }.get(kijun_signal, 0.30)

    signal_labels = {
        "fresh_break":              "✅ Break Kijun frais — signal optimal",
        "reclaim_after_pullback":   "✅ Reprise après pullback — signal de qualité",
        "none":                     "➡️ Pas de break Kijun actif",
        "late_extension":           "⚠️ Entrée tardive (extension > 3 ATR)",
        "weak_cross_equilibrium":   "⚠️ Kijun plat / range — signal faible",
        "failed_break":             "❌ Break Kijun raté — prix revenu en zone",
    }
    info.append(signal_labels.get(kijun_signal, f"Kijun signal: {kijun_signal}"))

    # ── Biais structurel ─────────────────────────────────────────────────────
    if structural_bias == exp_bias:
        bias_mult = 1.00
        info.append(f"✅ Biais structurel {exp_bias}")
    elif structural_bias == "neutral":
        bias_mult = 0.70
        info.append("⚠️ Biais structurel neutre")
    elif structural_bias == "conflicted":
        bias_mult = 0.50
        info.append("⚠️ Biais structurel contradictoire")
    else:
        bias_mult = 0.15
        info.append(f"❌ Biais structurel opposé ({structural_bias})")

    # ── Momentum / extension ──────────────────────────────────────────────────
    ext_state = extension_state.get("state", "healthy")
    ext_bonus = {"healthy": 1.00, "mild_extension": 0.90, "extended": 0.70,
                 "overextended": 0.40, "euphoric": 0.20}.get(ext_state, 1.00)

    if ext_state in ("overextended", "euphoric"):
        kda = extension_state.get("kijun_dist_atr", 0)
        info.append(f"⚠️ Extension {ext_state} ({kda:.1f}× ATR)")
    elif ext_state == "healthy":
        info.append("✅ Extension saine — bon point d'entrée")

    # ── Prix dans le nuage sur TF intermédiaire = bloquant ────────────────────
    pvcloud = ichi.get("price_vs_cloud", "unknown")
    if pvcloud == "inside":
        is_blocked = True
        info.append("🚫 Prix dans le nuage — signal dégradé")
        return 0.0, max_pts, info, False, True

    pts = round(max_pts * signal_quality * bias_mult * ext_bonus, 1)
    is_aligned = (pts >= max_pts * 0.45)

    return min(pts, max_pts), max_pts, info, is_aligned, False


# ──────────────────────────────────────────────────────────────────────────────
# CONTEXTE BTC
# ──────────────────────────────────────────────────────────────────────────────

def build_btc_context(btc_tf_analyses: dict) -> dict:
    """
    Extrait le contexte BTC à partir de son analyse multi-TF.

    trend :
      "bullish"   — BTC au-dessus du Kumo sur 1d ET 1wk
      "bearish"   — BTC en-dessous du Kumo sur 1d ET 1wk
      "range"     — BTC détecté en range sur 1d
      "uncertain" — BTC dans le Kumo ou signaux contradictoires
      "mixed"     — 1d et 1wk divergents
    """
    if not btc_tf_analyses:
        return {"trend": "unknown"}

    ichi_1d  = btc_tf_analyses.get("1d",  {}).get("ichi",           {}) or {}
    ichi_1wk = btc_tf_analyses.get("1wk", {}).get("ichi",           {}) or {}
    range_1d = btc_tf_analyses.get("1d",  {}).get("range_analysis", {}) or {}
    regime_1d = btc_tf_analyses.get("1d", {}).get("market_regime", "unknown")

    pvc_1d  = ichi_1d.get("price_vs_cloud",  "unknown")
    pvc_1wk = ichi_1wk.get("price_vs_cloud", "unknown")

    if range_1d.get("is_range", False):
        return {
            "trend":   "range",
            "message": f"BTC en range 1d — {', '.join(range_1d.get('reasons', [])[:2])}",
        }
    if pvc_1d == "inside" or pvc_1wk == "inside":
        return {"trend": "uncertain", "message": "BTC dans le Kumo — contexte incertain"}
    if pvc_1d == "above" and pvc_1wk == "above":
        return {"trend": "bullish",   "message": f"BTC au-dessus du Kumo 1d+1wk [{regime_1d}]"}
    if pvc_1d == "below" and pvc_1wk == "below":
        return {"trend": "bearish",   "message": f"BTC en-dessous du Kumo 1d+1wk [{regime_1d}]"}
    if pvc_1d != "unknown" and pvc_1wk != "unknown":
        return {"trend": "mixed",     "message": f"BTC contradictoire (1d:{pvc_1d} / 1wk:{pvc_1wk})"}
    return {"trend": "unknown", "message": "Données BTC insuffisantes"}


# ──────────────────────────────────────────────────────────────────────────────
# QUALITÉ DU SETUP ET SETUP FAMILY
# ──────────────────────────────────────────────────────────────────────────────

def compute_setup_quality(score: float) -> str:
    if score >= 85: return "🔥 FORT"
    if score >= 75: return "✅ CORRECT"
    if score >= 65: return "⚠️ FAIBLE"
    return "❌ INSUFFISANT"


def _derive_setup_family(tf_analyses: dict, direction: str) -> str:
    """
    Identifie la famille du setup basée sur le régime 1d.
    """
    ta_1d = tf_analyses.get("1d", {}) or {}
    regime_1d = ta_1d.get("market_regime", "")
    bias_1d   = ta_1d.get("structural_bias", "neutral")
    is_long   = (direction == "LONG")
    exp_bias  = "bullish" if is_long else "bearish"

    if regime_1d in ("trending_up", "trending_down"):
        if bias_1d == exp_bias:
            return "trend_continuation"
        return "counter_trend"
    if regime_1d in ("breakout_bullish", "breakout_bearish"):
        if bias_1d == exp_bias:
            return "breakout"
        return "counter_trend"
    if regime_1d in ("pullback_bullish", "pullback_bearish"):
        if bias_1d == exp_bias:
            return "pullback"
        return "counter_trend"
    if bias_1d and bias_1d not in ("neutral", "conflicted"):
        if bias_1d != exp_bias:
            return "counter_trend"
    return "undefined"


def _derive_trade_readiness(score: float, score_threshold: float,
                             kijun_signals: dict, penalties_total: float) -> str:
    """
    Trade readiness basé sur le score, les signaux de timing et les pénalités.
    """
    fresh_signals = {"fresh_break", "reclaim_after_pullback"}
    primary_tf_signals = [
        kijun_signals.get("4h", "none"),
        kijun_signals.get("1h", "none"),
    ]
    has_fresh_timing = any(s in fresh_signals for s in primary_tf_signals)

    if score >= score_threshold:
        if has_fresh_timing and penalties_total < 10:
            return "ready"
        return "wait"
    if score >= score_threshold * 0.85:
        return "wait"
    return "degraded"


def suggest_trade_duration(tf_agree: list) -> str:
    has_wk  = "1wk" in tf_agree
    has_1d  = "1d"  in tf_agree
    has_4h  = "4h"  in tf_agree
    has_1h  = "1h"  in tf_agree
    has_15m = "15m" in tf_agree

    if has_wk and has_1d and has_4h:
        return "📅 Position trade — plusieurs semaines"
    if has_1d and has_4h:
        return "📊 Swing trade — 3 à 10 jours"
    if has_4h and has_1h:
        return "⏱️ Trade court — 1 à 3 jours"
    if has_1h or has_15m:
        return "⚡ Scalp / intraday — quelques heures"
    return "🔍 Signal faible — surveiller"


# ──────────────────────────────────────────────────────────────────────────────
# INDICATEURS COMPLÉMENTAIRES (Phase 4 — Exécution)
# ──────────────────────────────────────────────────────────────────────────────

def _rsi_score(rsi: float, direction: str, max_pts: float) -> tuple:
    if direction == "LONG":
        if 40 <= rsi <= 65:  return max_pts,        f"✅ RSI {rsi:.1f} — zone haussière saine"
        if 30 <= rsi <  40:  return max_pts * 0.60, f"⚠️ RSI {rsi:.1f} — proche survente"
        if 65 < rsi <= 70:   return max_pts * 0.60, f"⚠️ RSI {rsi:.1f} — légèrement suracheté"
        if rsi < 30:         return max_pts * 0.30, f"⚠️ RSI {rsi:.1f} — survente extrême"
        return 0.0,                                  f"❌ RSI {rsi:.1f} — suracheté > 70"
    else:
        if 35 <= rsi <= 60:  return max_pts,        f"✅ RSI {rsi:.1f} — marge de baisse"
        if rsi > 70:         return max_pts,        f"✅ RSI {rsi:.1f} — suracheté, contexte short"
        if 60 < rsi <= 70:   return max_pts * 0.60, f"⚠️ RSI {rsi:.1f} — légèrement suracheté"
        if 25 <= rsi <  35:  return max_pts * 0.40, f"⚠️ RSI {rsi:.1f} — proche survente"
        return 0.0,                                  f"❌ RSI {rsi:.1f} — survente extrême"


def _candle_score(tf_analyses: dict, direction: str) -> tuple:
    MAX_CANDLE   = 7.0   # réduit de 8 à 7 (Phase 4)
    strength_pts = {"strong": MAX_CANDLE, "medium": 4.5, "weak": 2.0}
    expected_dir = "bullish" if direction == "LONG" else "bearish"
    opposite_dir = "bearish" if direction == "LONG" else "bullish"

    best_pts = 0.0
    info     = []

    for tf_key in ["1d", "4h", "1h"]:
        ta = tf_analyses.get(tf_key)
        if not ta: continue
        candles  = ta.get("candles", [])
        tf_label = {"1d": "Journalier", "4h": "4H", "1h": "1H"}.get(tf_key, tf_key)
        aligned  = [p for p in candles if p.get("direction") == expected_dir]
        opposite = [p for p in candles if p.get("direction") == opposite_dir]

        if aligned:
            best     = max(aligned, key=lambda p: strength_pts.get(p.get("strength","weak"), 0))
            pts      = strength_pts.get(best.get("strength","weak"), 0)
            best_pts = max(best_pts, pts)
            names    = ", ".join(p["name"] for p in aligned)
            info.append(f"✅ {tf_label}: {names} [{best.get('strength','?')}]")
        elif opposite:
            names = ", ".join(p["name"] for p in opposite)
            info.append(f"⚠️ {tf_label}: pattern contraire — {names}")
        else:
            info.append(f"➡️ {tf_label}: aucun pattern significatif")

    if not info:
        info = ["➡️ Aucun pattern chandelier détecté"]
    return min(best_pts, MAX_CANDLE), info


def _sentiment_score(sentiment: dict, direction: str) -> tuple:
    """
    Phase 3 — Alt Season (0-5 pts).
    BTC alignment géré séparément via _btc_context_score.
    """
    MAX_ALT = 5.0
    if not sentiment:
        return 0.0, "⚠️ Données sentiment indisponibles"

    pts    = 0.0
    labels = []
    is_btc  = sentiment.get("is_btc", False)
    alt_pct = sentiment.get("alt_season_pct")
    alt_lbl = sentiment.get("alt_season_label", "")

    if direction == "LONG":
        if alt_pct is not None:
            if alt_pct >= 75:
                pts += MAX_ALT; labels.append(f"✅ {alt_lbl} ({alt_pct:.0f}% alts > BTC/30j)")
            elif alt_pct >= 50:
                pts += MAX_ALT * 0.50; labels.append(f"⚠️ {alt_lbl} ({alt_pct:.0f}%)")
            else:
                labels.append(f"❌ {alt_lbl} ({alt_pct:.0f}%) — saison BTC")
    else:
        if alt_pct is not None:
            if alt_pct < 25:
                pts += MAX_ALT; labels.append(f"✅ {alt_lbl} — alts sous pression ({alt_pct:.0f}%)")
            elif alt_pct < 50:
                pts += MAX_ALT * 0.50; labels.append(f"⚠️ {alt_lbl} ({alt_pct:.0f}%)")
            else:
                labels.append(f"❌ {alt_lbl} — alt season forte, risqué pour SHORT")

    return min(pts, MAX_ALT), " | ".join(labels) if labels else "Sentiment neutre"


def _btc_context_score(btc_context: dict, direction: str,
                       is_btc: bool) -> tuple:
    """
    Phase 3 — Alignement BTC (0-10 pts) + pénalité si défavorable.
    Retourne (pts_earned, penalty_additional, label)
    """
    MAX_BTC   = 10.0
    if not btc_context or is_btc:
        return MAX_BTC * 0.5, 0.0, "N/A (BTC lui-même)" if is_btc else "BTC non disponible"

    btc_trend = btc_context.get("trend", "unknown")

    if direction == "LONG":
        if btc_trend == "bullish":
            return MAX_BTC, 0.0, "✅ BTC haussier → contexte favorable au LONG (+10 pts)"
        if btc_trend == "range":
            return MAX_BTC * 0.50, 8.0, "⚠️ BTC en range → signal dégradé (−8 pts)"
        if btc_trend in ("uncertain", "mixed"):
            return MAX_BTC * 0.50, 5.0, "⚠️ BTC incertain → signal dégradé (−5 pts)"
        if btc_trend == "bearish":
            return 0.0, 15.0, "🚨 BTC baissier → LONG altcoin très risqué (−15 pts)"
    else:  # SHORT
        if btc_trend == "bearish":
            return MAX_BTC, 0.0, "✅ BTC baissier → contexte favorable au SHORT (+10 pts)"
        if btc_trend == "range":
            return MAX_BTC * 0.50, 5.0, "⚠️ BTC en range → signal dégradé (−5 pts)"
        if btc_trend in ("uncertain", "mixed"):
            return MAX_BTC * 0.50, 3.0, "⚠️ BTC incertain → signal dégradé (−3 pts)"
        if btc_trend == "bullish":
            return 0.0, 15.0, "🚨 BTC haussier → SHORT altcoin très risqué (−15 pts)"

    return MAX_BTC * 0.50, 0.0, f"BTC trend={btc_trend}"


# ──────────────────────────────────────────────────────────────────────────────
# HELPER INTERNE — RÉSULTAT BLOQUÉ
# ──────────────────────────────────────────────────────────────────────────────

def _blocked_result(direction: str, reason: str, tf_agree: list,
                    market_status: str = "bloqué", detail: dict = None) -> dict:
    return {
        "direction":     direction,
        "score":         0,
        "blocked":       reason,
        "market_status": market_status,
        "tf_agree":      tf_agree,
        "duration":      "—",
        "detail":        detail or {},
        "setup_quality": "❌ REFUSÉ",
        "setup_family":  "undefined",
        "trade_readiness": "blocked",
        "confidence_label": "❌ REFUSÉ",
    }


# ──────────────────────────────────────────────────────────────────────────────
# FONCTION PRINCIPALE
# ──────────────────────────────────────────────────────────────────────────────

def compute_score(tf_analyses: dict, sentiment: dict, direction: str,
                  btc_context: dict = None) -> dict:
    """
    Score complet LONG ou SHORT — méthode Péloille hiérarchique v5.

    tf_analyses : {tf_key: résultat de analyze_tf()} pour chaque TF disponible
    direction   : "LONG" | "SHORT"
    btc_context : dict retourné par build_btc_context() — None pour BTC lui-même

    4 phases : Structure (40) + Timing (30) + Contexte (15) + Exécution (15) = 100 pts
    """
    is_long    = (direction == "LONG")
    tf_agree   = []
    tf_detail  = {}        # compatibilité email_sender
    penalties  = []        # [(pts, message)]
    market_status = "tendance propre"

    # ════════════════════════════════════════════════════════════════════════════
    # FILTRES BLOQUANTS (pré-scoring)
    # ════════════════════════════════════════════════════════════════════════════

    # ── Filtre 1 : Range sur 1d ET 4h ─────────────────────────────────────────
    range_1d = (tf_analyses.get("1d",  {}) or {}).get("range_analysis", {}) or {}
    range_4h = (tf_analyses.get("4h",  {}) or {}).get("range_analysis", {}) or {}

    if range_1d.get("is_range", False) and range_4h.get("is_range", False):
        reasons_txt = " / ".join(range_1d.get("reasons", [])[:2])
        return _blocked_result(direction,
            f"Marché en range sur 1d ET 4h — Ichimoku peu fiable ({reasons_txt})",
            tf_agree, "range")

    if range_1d.get("is_range", False):
        r_score = range_1d.get("score", 0)
        penalties.append((10.0, f"⚠️ Range détecté sur 1d ({r_score}/6 critères) — signal dégradé"))
        market_status = "range 1d"

    # ── Filtre 2 : Chikou Span 1d (validateur absolu Péloille) ────────────────
    ta_1d   = tf_analyses.get("1d", {}) or {}
    ichi_1d = ta_1d.get("ichi", {}) or {}
    chikou_analysis_1d = ta_1d.get("chikou_analysis", {}) or {}

    if ichi_1d:
        chikou_vs   = ichi_1d.get("chikou_vs_prices", "unknown")
        chikou_bias = chikou_analysis_1d.get("bias", "neutral")
        exp_chikou  = "above" if is_long else "below"
        exp_bias    = "bullish" if is_long else "bearish"

        # Chikou clairement du mauvais côté = blocage
        if chikou_vs not in ("unknown", None) and chikou_vs not in (exp_chikou, "inside_cloud"):
            side_bad = "sous" if is_long else "au-dessus"
            return _blocked_result(direction,
                f"Chikou Span {side_bad} des prix sur 1d — signal invalidé (validateur absolu Péloille)",
                tf_agree, "chikou_invalide")

        # Chikou biais clairement opposé dans la nouvelle analyse
        if chikou_bias not in ("neutral", "unknown", "conflicted", exp_bias):
            return _blocked_result(direction,
                f"Chikou biais {chikou_bias} incompatible avec {direction} (1d)",
                tf_agree, "chikou_invalide")

        # Pénalités Chikou
        clearance_1d = chikou_analysis_1d.get("clearance_score", 70)
        n_obs_1d     = chikou_analysis_1d.get("obstacles_count", 0)
        if chikou_vs == "inside_cloud" or clearance_1d < 30:
            penalties.append((15.0, "🚫 Chikou Span très bloquée sur 1d (clearance < 30)"))
        elif n_obs_1d >= 3 or clearance_1d < 50:
            penalties.append((10.0, f"⚠️ Chikou Span bloquée sur 1d ({n_obs_1d} obstacles, clearance {clearance_1d:.0f})"))
        elif n_obs_1d >= 2 or clearance_1d < 65:
            penalties.append((5.0,  f"⚠️ Chikou Span modérément bloquée sur 1d ({n_obs_1d} obstacle(s))"))

    # ── Filtre 3 : Extension tardive sur 1d ───────────────────────────────────
    ext_1d = ta_1d.get("extension_state", {}) or {}
    kijun_dist_atr_1d = ext_1d.get("kijun_dist_atr")

    if kijun_dist_atr_1d is not None and kijun_dist_atr_1d > MAX_KIJUN_EXTENSION_ATR:
        return _blocked_result(direction,
            f"Entrée tardive — prix {kijun_dist_atr_1d:.1f}× ATR au-delà du Kijun 1d "
            f"(max autorisé : {MAX_KIJUN_EXTENSION_ATR}×)",
            tf_agree, "momentum_tardif")

    if kijun_dist_atr_1d is not None and kijun_dist_atr_1d > 2.5:
        penalties.append((5.0, f"⚠️ Prix étendu du Kijun 1d ({kijun_dist_atr_1d:.1f}× ATR) — momentum avancé"))
        if market_status == "tendance propre":
            market_status = "momentum avancé"

    # ════════════════════════════════════════════════════════════════════════════
    # PHASE 1 — STRUCTURE (0-40 pts) : 1wk (0-17) + 1d (0-23)
    # ════════════════════════════════════════════════════════════════════════════
    global_blocked = False
    structure_score = 0.0

    # 1wk : régime(10) + chikou(4) + cloud(3) = 17
    ta_1wk = tf_analyses.get("1wk", {}) or {}
    s1wk, max1wk, info1wk, aligned1wk, blocked1wk = _structure_tf_score(
        ta_1wk, direction, max_regime=10, max_chikou=4, max_cloud=3)
    if blocked1wk:
        global_blocked = True
    structure_score += s1wk
    is_aligned_1wk = aligned1wk and not blocked1wk
    if is_aligned_1wk:
        tf_agree.append("1wk")
    # Pour email_sender compat : normaliser sur 80
    tf_detail["1wk"] = {
        "raw":     round(s1wk / max1wk * 80, 1) if max1wk else 0,
        "max":     80,
        "scaled":  round(s1wk / max1wk * 80 * TF_WEIGHTS.get("1wk", 0.30), 1) if max1wk else 0,
        "max_scaled": round(80 * TF_WEIGHTS.get("1wk", 0.30), 1),
        "info":    info1wk,
        "aligned": is_aligned_1wk,
        "blocked": blocked1wk,
    }

    # 1d : régime(14) + chikou(6) + cloud(3) = 23
    s1d, max1d, info1d, aligned1d, blocked1d = _structure_tf_score(
        ta_1d, direction, max_regime=14, max_chikou=6, max_cloud=3)
    if blocked1d:
        global_blocked = True
    structure_score += s1d
    is_aligned_1d = aligned1d and not blocked1d
    if is_aligned_1d:
        tf_agree.append("1d")
    tf_detail["1d"] = {
        "raw":      round(s1d / max1d * 80, 1) if max1d else 0,
        "max":      80,
        "scaled":   round(s1d / max1d * 80 * TF_WEIGHTS.get("1d", 0.25), 1) if max1d else 0,
        "max_scaled": round(80 * TF_WEIGHTS.get("1d", 0.25), 1),
        "info":     info1d,
        "aligned":  is_aligned_1d,
        "blocked":  blocked1d,
    }

    # ── Blocage global (prix dans nuage 1d/1wk) ───────────────────────────────
    detail_so_far = {"Ichimoku multi-TF": (round(structure_score, 1), tf_detail)}

    if global_blocked:
        return _blocked_result(direction,
            "Prix dans le nuage sur 1d ou 1wk — zone d'incertitude Péloille",
            tf_agree, "inside_kumo", detail_so_far)

    if REQUIRE_WEEKLY_DAILY:
        if not ("1wk" in tf_agree or "1d" in tf_agree):
            return _blocked_result(direction,
                "Ni 1wk ni 1d ne confirment la direction — structure insuffisante",
                tf_agree, "sans_confirmation_macro", detail_so_far)

    # ════════════════════════════════════════════════════════════════════════════
    # PHASE 2 — TIMING (0-30 pts) : 4h (0-15) + 1h (0-10) + 15m (0-5)
    # ════════════════════════════════════════════════════════════════════════════
    timing_score    = 0.0
    kijun_signals   = {}   # pour trade_readiness

    for tf_key, max_pts in [("4h", 15), ("1h", 10), ("15m", 5)]:
        ta = tf_analyses.get(tf_key, {}) or {}
        t_pts, t_max, t_info, t_aligned, t_blocked = _timing_tf_score(ta, direction, max_pts)
        timing_score += t_pts
        if ta:
            tf_agree_flag = t_aligned and not t_blocked
            if tf_agree_flag:
                tf_agree.append(tf_key)
            kijun_signals[tf_key] = ta.get("kijun_signal", "none")
        else:
            tf_agree_flag = False
            kijun_signals[tf_key] = "none"
        # Normaliser sur 80 pour email_sender
        tf_detail[tf_key] = {
            "raw":      round(t_pts / max_pts * 80, 1) if max_pts else 0,
            "max":      80,
            "scaled":   round(t_pts / max_pts * 80 * TF_WEIGHTS.get(tf_key, 0.10), 1) if max_pts else 0,
            "max_scaled": round(80 * TF_WEIGHTS.get(tf_key, 0.10), 1),
            "info":     t_info,
            "aligned":  tf_agree_flag,
            "blocked":  t_blocked,
        }

    # ── Filtre MIN_TF_AGREE ───────────────────────────────────────────────────
    if len(tf_agree) < MIN_TF_AGREE:
        return _blocked_result(direction,
            f"Seulement {len(tf_agree)}/{len(TF_WEIGHTS)} TFs en accord (min {MIN_TF_AGREE})",
            tf_agree, "tf_insuffisants",
            {"Ichimoku multi-TF": (round(structure_score + timing_score, 1), tf_detail)})

    score = structure_score + timing_score

    # ════════════════════════════════════════════════════════════════════════════
    # PHASE 3 — CONTEXTE (0-15 pts) : BTC (0-10) + Alt Season (0-5)
    # ════════════════════════════════════════════════════════════════════════════
    is_btc = sentiment.get("is_btc", False)

    # BTC alignment (0-10 pts) + pénalité éventuelle
    btc_pts, btc_extra_penalty, btc_msg = _btc_context_score(
        btc_context if BTC_FILTER_ENABLED else None,
        direction, is_btc)

    if btc_extra_penalty > 0:
        penalties.append((btc_extra_penalty, btc_msg))
        if "défavorable" not in market_status and "range" not in market_status:
            market_status = "contexte BTC défavorable"
    btc_net = btc_pts - btc_extra_penalty   # peut être négatif, géré via pénalités
    score  += btc_pts

    # Alt season (0-5 pts)
    sent_pts, sent_txt = _sentiment_score(sentiment, direction)
    score += sent_pts

    detail = {
        "Ichimoku multi-TF": (round(structure_score + timing_score, 1), tf_detail),
        "RSI":               (0, []),   # rempli ci-dessous
        "Patterns chandelier": (0, []),
        "Sentiment":         (round(sent_pts, 1), sent_txt),
        "Contexte BTC":      (round(-btc_extra_penalty, 1), btc_msg),
    }

    # ════════════════════════════════════════════════════════════════════════════
    # PHASE 4 — EXÉCUTION (0-15 pts) : RSI (0-8) + Chandelier (0-7)
    # ════════════════════════════════════════════════════════════════════════════
    RSI_ALLOC = {"1d": 4.0, "4h": 2.5, "1h": 1.5}
    rsi_score = 0.0
    rsi_info  = []
    for tf_key, rsi_max in RSI_ALLOC.items():
        ta = tf_analyses.get(tf_key)
        if ta and "rsi" in ta:
            r_pts, r_label = _rsi_score(ta["rsi"], direction, rsi_max)
            rsi_score += r_pts
            tf_lbl = {"1d": "Journalier", "4h": "4H", "1h": "1H"}.get(tf_key, tf_key)
            rsi_info.append(f"{tf_lbl}: {r_label}")
    detail["RSI"] = (round(rsi_score, 1), rsi_info)
    score += rsi_score

    candle_pts, candle_info = _candle_score(tf_analyses, direction)
    detail["Patterns chandelier"] = (round(candle_pts, 1), candle_info)
    score += candle_pts

    # ════════════════════════════════════════════════════════════════════════════
    # APPLICATION DES PÉNALITÉS
    # ════════════════════════════════════════════════════════════════════════════
    total_penalty = sum(p for p, _ in penalties)
    penalty_msgs  = [m for _, m in penalties if m]
    score         = max(0.0, score - total_penalty)

    if penalty_msgs:
        detail["Pénalités"] = (round(-total_penalty, 1), penalty_msgs)

    # ── Momentum info dans le détail (pour email) ─────────────────────────────
    mom_1d = ta_1d.get("momentum", {}) or {}
    ext_info_list = []
    if ext_1d:
        kda = ext_1d.get("kijun_dist_atr")
        kpct = mom_1d.get("kijun_distance_pct")
        accel = mom_1d.get("price_accel_3")
        state = ext_1d.get("state", "")
        if kpct is not None:
            ext_info_list.append(f"Distance Kijun 1d : {kpct:.1f}%")
        if kda is not None:
            ext_info_list.append(f"Extension ATR 1d : {kda:.1f}× [{state}]")
        if accel is not None:
            ext_info_list.append(f"Accélération prix 3 bougies : {accel:+.2f}%")
    if ext_info_list:
        detail["Momentum"] = (0, ext_info_list)

    # ── Régimes TF dans le détail ─────────────────────────────────────────────
    regime_info = []
    for tf_key in ["1wk", "1d", "4h", "1h"]:
        ta = tf_analyses.get(tf_key, {}) or {}
        r = ta.get("market_regime")
        b = ta.get("structural_bias")
        ks = ta.get("kijun_signal")
        if r:
            regime_info.append(f"{tf_key}: {r} [{b or '?'}] signal={ks or 'none'}")
    if regime_info:
        detail["Régimes TF"] = (0, regime_info)

    # ════════════════════════════════════════════════════════════════════════════
    # ENRICHISSEMENTS FINAUX
    # ════════════════════════════════════════════════════════════════════════════
    final_score    = min(round(score), 100)
    setup_quality  = compute_setup_quality(final_score)
    setup_family   = _derive_setup_family(tf_analyses, direction)

    # Score threshold depuis config (import tardif pour éviter circularité)
    try:
        from src.config import SCORE_THRESHOLD
        s_thresh = SCORE_THRESHOLD
    except ImportError:
        s_thresh = 70

    trade_readiness = _derive_trade_readiness(
        final_score, s_thresh, kijun_signals, total_penalty)

    return {
        "direction":        direction,
        "score":            final_score,
        "setup_quality":    setup_quality,
        "confidence_label": setup_quality,   # alias
        "tf_agree":         tf_agree,
        "duration":         suggest_trade_duration(tf_agree),
        "market_status":    market_status,
        "detail":           detail,
        "blocked":          None,
        "setup_family":     setup_family,
        "trade_readiness":  trade_readiness,
    }
