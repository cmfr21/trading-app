"""
Analyse de risque v5 — Cibles et SL strictement structurels (méthode Péloille).

Stop Loss — hiérarchie (ordre de priorité) :
  LONG  : sous Kijun 1d − ATR  →  sous Kumo bottom 1d − ATR  →  sous SSB 1d
  SHORT : au-dessus Kijun 1d + ATR  →  au-dessus Kumo top 1d + ATR  →  au-dessus SSB 1d

Take Profit — hiérarchie multi-cibles (du plus proche au plus loin) :
  nearest_obstacle_target   : premier obstacle Ichimoku dans la direction
  first_meaningful_target   : premier niveau significatif (Tenkan→Kijun→SSA/SSB)
  structural_target         : niveau structurel (Kijun hebdo / SSB hebdo)
  stretch_target            : cible étirée (MA200 / ATR×3.5)

R/R qualitatif :
  🔥 Excellent  ≥ 3.0
  ✅ Acceptable  2.0–2.9
  ❌ Insuffisant < 2.0  (trade refusé en amont par main.py)

Niveaux plats (flat_levels de indicators.py) :
  Utilisés en priorité comme cibles (supports/résistances naturels)
  ou comme obstacles à surveiller dans les SL.

Sorties :
  - stop_loss, stop_ref_name              : SL structurel
  - target_conservative, _name           : cible 1 (first_meaningful)
  - target_ambitious, _name              : cible 2 (structural)
  - rr_ratio, rr_quality                 : R/R sur cible conservatrice
  - ichimoku_targets                     : liste de toutes les cibles (max 4)
  - rr_to_nearest, rr_to_structural, rr_to_stretch  : R/R multiples (v5)
  - risk_flags                           : liste de warnings qualitatifs
  - setup_risk_comment                   : résumé narratif du profil de risque
"""

import math
from typing import Optional


SAFETY_BUFFER   = 0.80
MAX_LEV         = 10
LEVERAGE_LEVELS = [2, 3, 5, 7, 10, 15, 20]


def compute_risk(tf_analyses: dict, direction: str, entry_price: float) -> dict:
    """
    Calcule le profil de risque complet v5.
    tf_analyses : dict retourné par analyze_tf() pour chaque TF.
    """
    direction = direction.upper()
    is_long   = (direction == "LONG")

    daily  = tf_analyses.get("1d")  or {}
    weekly = tf_analyses.get("1wk") or {}

    ichi_1d   = daily.get("ichi",  {}) or {}
    ichi_1wk  = weekly.get("ichi", {}) or {}
    mas       = daily.get("mas",   {}) or {}
    atr       = daily.get("atr",   0)  or 0
    vol90     = daily.get("vol90", None)

    # Niveaux plats détectés (aimants de prix)
    flat_levels_1d  = daily.get("flat_levels",  []) or []
    flat_levels_1wk = weekly.get("flat_levels", []) or []
    all_flat_levels = flat_levels_1d + flat_levels_1wk

    # Niveaux Ichimoku journalier
    tenkan = ichi_1d.get("tenkan")
    kijun  = ichi_1d.get("kijun")
    ssa    = ichi_1d.get("ssa")
    ssb    = ichi_1d.get("ssb")

    cloud_top_1d    = ichi_1d.get("cloud_top")
    cloud_bottom_1d = ichi_1d.get("cloud_bottom")

    # Niveaux hebdomadaires (cibles plus ambitieuses)
    kijun_wk = ichi_1wk.get("kijun")
    ssa_wk   = ichi_1wk.get("ssa")
    ssb_wk   = ichi_1wk.get("ssb")

    # MA journalières
    ma50  = mas.get("ma50")
    ma200 = mas.get("ma200")

    # Setup family pour adapter le SL
    ta_1d = tf_analyses.get("1d", {}) or {}
    setup_family = None   # récupéré depuis scoring si disponible (passé dans tf_analyses)

    def _above(v): return v is not None and v > entry_price * 1.002
    def _below(v): return v is not None and v < entry_price * 0.998

    # ── CONSTRUCTION DES CIBLES ────────────────────────────────────────────────
    # Ordre hiérarchique strict (Péloille) : Tenkan → Kijun → SSA → SSB → hebdo → MAs
    # + niveaux plats intégrés en priorité si plus proches

    if is_long:
        candidate_targets = [
            ("Tenkan 1d",  tenkan),
            ("Kijun 1d",   kijun),
            ("SSA 1d",     ssa),
            ("SSB 1d",     ssb),
            ("Kijun 1wk",  kijun_wk),
            ("SSA 1wk",    ssa_wk),
            ("SSB 1wk",    ssb_wk),
            ("MA 50",      ma50),
            ("MA 200",     ma200),
        ]
        valid_targets = [(n, v) for n, v in candidate_targets if _above(v)]
        valid_targets.sort(key=lambda x: x[1])   # du plus proche au plus loin

        # Ajouter les niveaux plats résistance au-dessus du prix
        flat_resistances = [
            (f"Résistance plate {fl['type'].replace('_flat','')}", fl["level"])
            for fl in all_flat_levels
            if fl["role"] == "resistance" and _above(fl["level"])
        ]
        valid_targets = _merge_targets(valid_targets, flat_resistances)

    else:
        candidate_targets = [
            ("Tenkan 1d",  tenkan),
            ("Kijun 1d",   kijun),
            ("SSA 1d",     ssa),
            ("SSB 1d",     ssb),
            ("Kijun 1wk",  kijun_wk),
            ("SSA 1wk",    ssa_wk),
            ("SSB 1wk",    ssb_wk),
            ("MA 50",      ma50),
            ("MA 200",     ma200),
        ]
        valid_targets = [(n, v) for n, v in candidate_targets if _below(v)]
        valid_targets.sort(key=lambda x: x[1], reverse=True)   # du plus proche au plus loin

        # Ajouter les niveaux plats support en-dessous du prix
        flat_supports = [
            (f"Support plat {fl['type'].replace('_flat','')}", fl["level"])
            for fl in all_flat_levels
            if fl["role"] == "support" and _below(fl["level"])
        ]
        valid_targets = _merge_targets_short(valid_targets, flat_supports)

    # ── STOP LOSS ─────────────────────────────────────────────────────────────
    if is_long:
        if kijun and atr:
            stop_loss     = kijun - atr
            stop_ref_name = "Kijun 1d − ATR"
        elif cloud_bottom_1d and atr:
            stop_loss     = cloud_bottom_1d - atr
            stop_ref_name = "Kumo bottom 1d − ATR"
        elif ssb and _below(ssb):
            stop_loss     = ssb * 0.995
            stop_ref_name = "SSB 1d"
        elif kijun:
            stop_loss     = kijun * 0.990
            stop_ref_name = "Kijun 1d (sans ATR)"
        else:
            stop_loss     = entry_price * 0.970
            stop_ref_name = "Fallback −3%"

        key_lvl_price = kijun
        key_lvl_name  = stop_ref_name

    else:
        if kijun and atr:
            stop_loss     = kijun + atr
            stop_ref_name = "Kijun 1d + ATR"
        elif cloud_top_1d and atr:
            stop_loss     = cloud_top_1d + atr
            stop_ref_name = "Kumo top 1d + ATR"
        elif ssb and _above(ssb):
            stop_loss     = ssb * 1.005
            stop_ref_name = "SSB 1d"
        elif kijun:
            stop_loss     = kijun * 1.010
            stop_ref_name = "Kijun 1d (sans ATR)"
        else:
            stop_loss     = entry_price * 1.030
            stop_ref_name = "Fallback +3%"

        key_lvl_price = kijun
        key_lvl_name  = stop_ref_name

    # ── CIBLES NOMMÉES ────────────────────────────────────────────────────────
    # Cible conservatrice = premier niveau (nearest_obstacle_target)
    target_conservative      = None
    target_conservative_name = None
    if valid_targets:
        target_conservative_name, target_conservative = valid_targets[0]
    elif atr:
        # Fallback si aucun niveau Ichimoku dans la direction (prix à de nouveaux sommets/planchers)
        target_conservative      = (entry_price + 1.5 * atr) if is_long else (entry_price - 1.5 * atr)
        target_conservative_name = "ATR × 1.5 (fallback)"

    # Cible ambitieuse = deuxième niveau (structural_target)
    target_ambitious      = None
    target_ambitious_name = None
    if len(valid_targets) >= 2:
        target_ambitious_name, target_ambitious = valid_targets[1]
    elif atr:
        mult = 2.5
        target_ambitious      = (entry_price + mult * atr) if is_long else (entry_price - mult * atr)
        target_ambitious_name = f"ATR × {mult}"

    # ── CIBLES MULTIPLES V5 ───────────────────────────────────────────────────
    # nearest_obstacle : cible 1 (first_meaningful_target)
    # structural       : cible 2 (niveau Kijun 1wk ou SSB 1wk)
    # stretch          : cible 3 (MA200 ou ATR×3.5)

    nearest_target = target_conservative
    nearest_name   = target_conservative_name

    structural_target = None
    structural_name   = None
    if len(valid_targets) >= 2:
        structural_name, structural_target = valid_targets[1]
    elif valid_targets and atr:
        # Un seul niveau Ichimoku disponible → structural = ATR×2.5
        structural_target = (entry_price + 2.5 * atr) if is_long else (entry_price - 2.5 * atr)
        structural_name   = "ATR × 2.5"

    stretch_target = None
    stretch_name   = None
    if len(valid_targets) >= 3:
        stretch_name, stretch_target = valid_targets[2]
    elif atr:
        mult = 3.5
        stretch_target = (entry_price + mult * atr) if is_long else (entry_price - mult * atr)
        stretch_name   = f"ATR × {mult}"

    # ── R/R CALCULS ───────────────────────────────────────────────────────────
    risk_amt = abs(stop_loss - entry_price) if (stop_loss and entry_price) else None

    def _rr(target):
        if target is None or risk_amt is None or risk_amt == 0:
            return None
        return round(abs(target - entry_price) / risk_amt, 2)

    rr_ratio   = _rr(target_conservative)
    rr_quality = "⚠️ Non calculable"
    if rr_ratio is not None:
        if rr_ratio >= 3.0:
            rr_quality = "🔥 Excellent (≥3)"
        elif rr_ratio >= 2.0:
            rr_quality = "✅ Acceptable (2–3)"
        else:
            rr_quality = "❌ Insuffisant (<2)"

    rr_to_nearest    = rr_ratio
    rr_to_structural = _rr(structural_target)
    rr_to_stretch    = _rr(stretch_target)

    # ── LIQUIDATION PAR LEVIER ────────────────────────────────────────────────
    liq_table = {}
    safety    = {}
    for lev in LEVERAGE_LEVELS:
        if is_long:
            liq = round(entry_price * (1 - 1/lev), 6)
        else:
            liq = round(entry_price * (1 + 1/lev), 6)
        liq_table[lev] = liq
        if vol90:
            vf = vol90 / 100
            if is_long:
                safety[lev] = liq < entry_price * (1 - vf)
            else:
                safety[lev] = liq > entry_price * (1 + vf)
        else:
            safety[lev] = None

    # ── LEVIER SUGGÉRÉ ────────────────────────────────────────────────────────
    suggested_lev = _suggest_leverage(entry_price, key_lvl_price, vol90, direction)

    # ── PLAGE 90J (volatilité) ────────────────────────────────────────────────
    price_range_90 = None
    if vol90:
        vf = vol90 / 100
        price_range_90 = {
            "low":     round(entry_price * (1 - vf), 6),
            "high":    round(entry_price * (1 + vf), 6),
            "vol_pct": round(vol90, 1),
        }

    # ── NIVEAUX CLÉS POUR EMAIL ───────────────────────────────────────────────
    supports    = {}
    resistances = {}
    all_levels  = {
        "Tenkan 1d": tenkan, "Kijun 1d": kijun,
        "SSA 1d": ssa,       "SSB 1d": ssb,
        "Kijun 1wk": kijun_wk, "MA 50": ma50, "MA 200": ma200,
    }
    for name, val in all_levels.items():
        if val and val > 0:
            if val < entry_price * 0.998:
                supports[name] = val
            elif val > entry_price * 1.002:
                resistances[name] = val

    # Ajouter les niveaux plats
    for fl in all_flat_levels[:3]:   # max 3 pour ne pas surcharger
        lname = f"{fl['type'].replace('_flat', ' plat')} ({fl['role']})"
        lval  = fl["level"]
        if lval < entry_price * 0.998:
            supports[lname] = lval
        elif lval > entry_price * 1.002:
            resistances[lname] = lval

    # ── RISK FLAGS ET COMMENTAIRE ─────────────────────────────────────────────
    risk_flags = []

    # Vérifier si le SL est trop loin (risque élevé)
    if risk_amt and entry_price > 0:
        sl_pct = risk_amt / entry_price * 100
        if sl_pct > 15:
            risk_flags.append(f"⚠️ SL très éloigné ({sl_pct:.1f}%) — réduire la taille de position")
        elif sl_pct > 8:
            risk_flags.append(f"ℹ️ SL éloigné ({sl_pct:.1f}%) — position sizing important")

    # Vérifier twist imminent (fragilité nuage)
    if ichi_1d.get("future_twist"):
        risk_flags.append("⚠️ Twist Kumo imminent sur 1d — potentiel retournement")

    # Niveau plat proche comme risque
    for fl in all_flat_levels:
        if fl["dist_pct"] < 2.0 and fl["dist_atr"] < 1.0:
            risk_flags.append(f"⚠️ Niveau plat {fl['type']} très proche ({fl['dist_pct']:.1f}%) "
                              f"— aimant de prix potentiel")
            break

    # Commentaire narratif
    if rr_ratio is None:
        setup_risk_comment = "R/R non calculable — données insuffisantes"
    elif rr_ratio >= 3.0:
        setup_risk_comment = (f"Excellent profil R/R ({rr_ratio:.1f}) avec SL structurel "
                              f"sur {stop_ref_name}. ")
        if structural_target:
            setup_risk_comment += f"Cible structurelle à {structural_name}."
    elif rr_ratio >= 2.0:
        setup_risk_comment = (f"Profil R/R acceptable ({rr_ratio:.1f}). "
                              f"SL sur {stop_ref_name}. "
                              f"Surveiller les obstacles Chikou avant l'entrée.")
    else:
        setup_risk_comment = (f"R/R insuffisant ({rr_ratio:.1f}) — "
                              f"attendre un meilleur point d'entrée ou un pullback vers {stop_ref_name}.")

    warning = None
    if suggested_lev <= 2:
        warning = (
            f"⚠️ Volatilité élevée — levier recommandé ≤ {suggested_lev}x. "
            f"Réduire la taille de position ou attendre un meilleur point d'entrée."
        )

    return {
        "entry_price":                entry_price,
        "direction":                  direction,
        "stop_loss":                  round(stop_loss, 6)              if stop_loss else None,
        "stop_ref_name":              stop_ref_name,
        "target_conservative":        round(target_conservative, 6)    if target_conservative else None,
        "target_conservative_name":   target_conservative_name,
        "target_ambitious":           round(target_ambitious, 6)       if target_ambitious else None,
        "target_ambitious_name":      target_ambitious_name,
        "rr_ratio":                   rr_ratio,
        "rr_quality":                 rr_quality,
        # Cibles multiples v5
        "nearest_target":             round(nearest_target, 6)         if nearest_target else None,
        "nearest_target_name":        nearest_name,
        "structural_target":          round(structural_target, 6)      if structural_target else None,
        "structural_target_name":     structural_name,
        "stretch_target":             round(stretch_target, 6)         if stretch_target else None,
        "stretch_target_name":        stretch_name,
        "rr_to_nearest":              rr_to_nearest,
        "rr_to_structural":           rr_to_structural,
        "rr_to_stretch":              rr_to_stretch,
        # Levier et gestion du risque
        "key_level_name":             key_lvl_name,
        "key_level_price":            round(key_lvl_price, 6)          if key_lvl_price else None,
        "suggested_leverage":         suggested_lev,
        "liquidation_table":          liq_table,
        "safety_assessment":          safety,
        "price_range_90":             price_range_90,
        "warning":                    warning,
        "supports":                   {k: round(v, 6) for k, v in supports.items()},
        "resistances":                {k: round(v, 6) for k, v in resistances.items()},
        "ichimoku_targets":           [(n, round(v, 6)) for n, v in valid_targets[:4]],
        # v5 : flags et commentaire
        "risk_flags":                 risk_flags,
        "setup_risk_comment":         setup_risk_comment,
    }


def _merge_targets(ichimoku_targets: list, flat_targets: list) -> list:
    """
    Fusionne les cibles Ichimoku et les niveaux plats (LONG — tri ascendant).
    Déduplique les niveaux trop proches (< 1%).
    """
    combined = ichimoku_targets + flat_targets
    combined.sort(key=lambda x: x[1])
    deduped = []
    last_val = None
    for name, val in combined:
        if last_val is None or abs(val - last_val) / (abs(last_val) + 1e-10) > 0.01:
            deduped.append((name, val))
            last_val = val
    return deduped


def _merge_targets_short(ichimoku_targets: list, flat_targets: list) -> list:
    """
    Fusionne les cibles Ichimoku et les niveaux plats (SHORT — tri descendant).
    """
    combined = ichimoku_targets + flat_targets
    combined.sort(key=lambda x: x[1], reverse=True)
    deduped = []
    last_val = None
    for name, val in combined:
        if last_val is None or abs(val - last_val) / (abs(last_val) + 1e-10) > 0.01:
            deduped.append((name, val))
            last_val = val
    return deduped


def _suggest_leverage(entry: float, key_level: Optional[float],
                       vol90: Optional[float], direction: str) -> int:
    """Levier max pour tenir 90 jours sans liquidation sur le niveau Kijun."""
    limits = []

    if key_level and entry > 0:
        dist_pct = abs(entry - key_level) / entry
        if dist_pct > 0:
            lev = math.floor(SAFETY_BUFFER / dist_pct)
            limits.append(max(1, min(lev, MAX_LEV)))

    if vol90 and vol90 > 0:
        lev = math.floor(SAFETY_BUFFER * 100 / vol90)
        limits.append(max(1, min(lev, MAX_LEV)))

    return min(limits) if limits else 1
