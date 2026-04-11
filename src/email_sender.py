"""
Email d'alerte v3 — Méthode Péloille, multi-timeframe.
Conçu pour rester sous 80KB (limite Gmail ~102KB).
Un email par batch, max MAX_OPPS_PER_EMAIL opportunités.

Sections par opportunité :
  1. En-tête : symbole, direction, score, durée suggérée
  2. Prix horodaté (critique)
  3. Confluence Ichimoku multi-TF (5 TF + Lagging Span status)
  4. Cibles Ichimoku + Stop Kijun + R/R
  5. Patterns chandelier
  6. Analyse de risque & levier
  7. Sentiment (Alt Season + BTC.D)
"""

import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.config import (
    EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT,
    MAX_OPPS_PER_EMAIL, TIMEFRAMES,
)

logger = logging.getLogger(__name__)

TF_LABELS = {k: v["label"] for k, v in TIMEFRAMES.items()}
LEV_SHOW  = [2, 3, 5, 7, 10]


def _score_color(s: int) -> str:
    return "#166534" if s >= 85 else ("#1d4ed8" if s >= 75 else ("#ca8a04" if s >= 65 else "#dc2626"))

def _dir_badge(d: str) -> str:
    bg    = "#16a34a" if d == "LONG" else "#dc2626"
    arrow = "▲" if d == "LONG" else "▼"
    return (f'<span style="background:{bg};color:#fff;padding:2px 9px;'
            f'border-radius:4px;font-weight:bold;">{arrow} {d}</span>')

def _score_label(s: int) -> str:
    """Qualité qualitative — sans probabilité statistique."""
    if s >= 85: return "🔥 FORT"
    if s >= 75: return "✅ CORRECT"
    if s >= 65: return "⚠️ FAIBLE"
    return "❌ INSUFFISANT"

def _market_status_badge(status: str) -> str:
    """Badge coloré pour le statut du marché."""
    colors = {
        "tendance propre":          ("#dcfce7", "#166534", "✅"),
        "range 1d":                 ("#fef3c7", "#92400e", "⚠️"),
        "momentum avancé":          ("#fef3c7", "#92400e", "⏩"),
        "contexte BTC défavorable": ("#fee2e2", "#991b1b", "🚨"),
        "chikou_invalide":          ("#fee2e2", "#991b1b", "🚫"),
        "inside_kumo":              ("#fee2e2", "#991b1b", "🚫"),
    }
    bg, fg, icon = colors.get(status, ("#f3f4f6", "#374151", "ℹ️"))
    label = status.replace("_", " ").upper()
    return (f'<span style="background:{bg};color:{fg};padding:2px 7px;border-radius:3px;'
            f'font-size:11px;font-weight:bold;">{icon} {label}</span>')


def _tf_table(tf_detail: dict, all_tfs: list) -> str:
    """
    Tableau des 5 TF avec statut Ichimoku + Lagging Span.
    tf_detail : dict issu de scoring["detail"]["Ichimoku multi-TF"][1]
    """
    rows = ""
    for tf in all_tfs:
        label = TF_LABELS.get(tf, tf)
        d     = tf_detail.get(tf)
        if d is None:
            rows += (f'<tr><td style="padding:3px 8px;color:#9ca3af;">{label}</td>'
                     f'<td style="padding:3px 8px;color:#9ca3af;">—</td>'
                     f'<td style="padding:3px 8px;color:#9ca3af;">—</td></tr>')
            continue

        aligned = d.get("aligned", False)
        blocked = d.get("blocked", False)
        raw     = d.get("raw", 0)
        max_raw = d.get("max", 80)

        if blocked:
            status = "🚫"
            color  = "#dc2626"
        elif aligned:
            status = "✅"
            color  = "#16a34a"
        else:
            status = "❌"
            color  = "#dc2626"

        pct  = int(raw / max_raw * 100) if max_raw else 0
        bar  = f'<div style="background:#e5e7eb;border-radius:3px;width:60px;display:inline-block;">' \
               f'<div style="background:{color};width:{pct}%;height:6px;border-radius:3px;"></div></div>'

        # Extraire les lignes Lagging Span des infos
        chikou_lines = [l for l in d.get("info", []) if "Lagging" in l or "Chikou" in l or "obstacle" in l.lower()]
        chikou_txt   = chikou_lines[0] if chikou_lines else ""

        rows += (f'<tr><td style="padding:3px 8px;font-weight:500;">{label}</td>'
                 f'<td style="padding:3px 8px;">{status} {pct}% {bar}</td>'
                 f'<td style="padding:3px 8px;font-size:11px;color:#6b7280;">{chikou_txt}</td></tr>')
    return (f'<table style="font-size:12px;border-collapse:collapse;width:100%;">'
            f'<tr style="background:#f3f4f6;">'
            f'<th style="padding:3px 8px;text-align:left;">TF</th>'
            f'<th style="padding:3px 8px;text-align:left;">Ichimoku</th>'
            f'<th style="padding:3px 8px;text-align:left;">Lagging Span</th></tr>'
            f'{rows}</table>')


def _candle_block(tf_analyses: dict, direction: str) -> str:
    """
    Bloc patterns chandelier. Format candles : list of {"name", "direction", "strength"}.
    """
    lines       = []
    expected    = "bullish" if direction == "LONG" else "bearish"
    opposite    = "bearish" if direction == "LONG" else "bullish"

    for tf in ["1d", "4h", "1h"]:
        ta = tf_analyses.get(tf)
        if not ta:
            continue
        candles  = ta.get("candles", [])
        lbl      = TF_LABELS.get(tf, tf)

        aligned  = [p for p in candles if p.get("direction") == expected]
        opp_list = [p for p in candles if p.get("direction") == opposite]

        if aligned:
            names = ", ".join(p["name"] for p in aligned)
            best  = max(aligned, key=lambda p: {"strong":3,"medium":2,"weak":1}.get(p.get("strength","weak"),0))
            color = "#16a34a"
            lines.append(f'<span style="color:{color};">✅ {lbl}: {names} [{best["strength"]}]</span>')
        elif opp_list:
            names = ", ".join(p["name"] for p in opp_list)
            lines.append(f'<span style="color:#ca8a04;">⚠️ {lbl}: pattern contraire ({names})</span>')

    return "<br>".join(lines) if lines else '<span style="color:#9ca3af;">Aucun pattern significatif</span>'


def _ichimoku_targets_block(risk: dict) -> str:
    """Affiche les cibles Ichimoku sous forme de liste compacte."""
    targets = risk.get("ichimoku_targets", [])
    if not targets:
        return ""
    items = ""
    for i, (name, val) in enumerate(targets):
        marker = "🎯" if i == 0 else ("🏹" if i == 1 else "⭐")
        lbl    = "Conservatrice" if i == 0 else ("Ambitieuse" if i == 1 else f"Niveau {i+1}")
        items += f'<span style="margin-right:12px;">{marker} <strong>{lbl}</strong> ({name}): ${val:,.4g}</span>'
    return f'<div style="margin:4px 0;">{items}</div>'


def _lev_rows(liq_table: dict, safety: dict, suggested: int, entry: float, direction: str) -> str:
    rows = ""
    for lev in LEV_SHOW:
        if lev not in liq_table:
            continue
        liq  = liq_table[lev]
        safe = safety.get(lev)
        sf   = "✅" if safe else ("❌" if safe is False else "—")
        move = abs(entry - liq) / entry * 100
        sign = "−" if direction == "LONG" else "+"
        bold = "font-weight:bold;color:#2563eb;" if lev == suggested else ""
        mark = " ← SUGGÉRÉ" if lev == suggested else ""
        bg   = "#eff6ff" if lev == suggested else "#fff"
        rows += (f'<tr style="background:{bg};">'
                 f'<td style="padding:3px 8px;{bold}">{lev}x{mark}</td>'
                 f'<td style="padding:3px 8px;font-family:monospace;">${liq:,.4g}</td>'
                 f'<td style="padding:3px 8px;color:#6b7280;">{sign}{move:.1f}%</td>'
                 f'<td style="padding:3px 8px;">{sf}</td></tr>')
    return rows


def _build_block(opp: dict) -> str:
    sym       = opp["symbol"]
    ticker    = sym.replace("USDT", "")
    price     = opp["price"]
    ts        = opp["timestamp"]
    scoring   = opp["scoring"]
    risk      = opp["risk"]
    sentiment = opp.get("sentiment", {})
    tf_a      = opp.get("tf_analyses", {})

    direction     = scoring["direction"]
    score         = scoring["score"]
    detail        = scoring["detail"]
    tf_agree      = scoring.get("tf_agree", [])
    duration      = scoring.get("duration", "—")
    market_status = scoring.get("market_status", "tendance propre")
    setup_quality = scoring.get("setup_quality", _score_label(score))

    # Détail Ichimoku par TF
    ichi_detail_tuple = detail.get("Ichimoku multi-TF", (0, {}))
    tf_detail  = ichi_detail_tuple[1] if isinstance(ichi_detail_tuple[1], dict) else {}

    # Sentiment
    sent_info  = detail.get("Sentiment", (0, "—"))
    sent_pts   = sent_info[0]
    sent_txt   = sent_info[1] if isinstance(sent_info[1], str) else "—"

    # RSI
    rsi_info  = detail.get("RSI", (0, []))
    rsi_lines = rsi_info[1] if isinstance(rsi_info[1], list) else []

    # Contexte BTC
    btc_info  = detail.get("Contexte BTC", (0, ""))
    btc_pts   = btc_info[0] if isinstance(btc_info[0], (int, float)) else 0
    btc_txt   = btc_info[1] if isinstance(btc_info[1], str) else ""

    # Pénalités
    pen_info  = detail.get("Pénalités", (0, []))
    pen_pts   = pen_info[0] if isinstance(pen_info[0], (int, float)) else 0
    pen_msgs  = pen_info[1] if isinstance(pen_info[1], list) else []

    # Momentum
    mom_info  = detail.get("Momentum", (0, []))
    mom_msgs  = mom_info[1] if isinstance(mom_info[1], list) else []

    # Alt season detail
    alt_detail = sentiment.get("alt_season_detail", [])
    alt_mini   = " ".join(
        f'<span style="color:{"#16a34a" if c["chg_vs_btc_pct"]>0 else "#dc2626"};">'
        f'{"▲" if c["chg_vs_btc_pct"]>0 else "▼"}{c["symbol"]} {c["chg_vs_btc_pct"]:+.1f}%</span>'
        for c in alt_detail[:6]
    )

    # Prix cible
    tgt_c      = risk.get("target_conservative")
    tgt_c_name = risk.get("target_conservative_name", "")
    tgt_a      = risk.get("target_ambitious")
    tgt_a_name = risk.get("target_ambitious_name", "")
    sl         = risk.get("stop_loss")
    sl_name    = risk.get("stop_ref_name", "Kijun 1d")
    rr         = risk.get("rr_ratio")
    rr_quality = risk.get("rr_quality", "—")

    def fmt(v): return f"${v:,.4g}" if v else "—"
    def rr_fmt(r): return f"{r:.2f}" if r is not None else "N/A"

    binance_url = f"https://www.binance.com/fr/futures/{ticker}USDT"

    # Pénalités HTML
    pen_html = ""
    if pen_msgs:
        pen_lines = "".join(f"<div>• {m}</div>" for m in pen_msgs)
        pen_html  = (f'<div style="background:#fef3c7;border-left:3px solid #ca8a04;'
                     f'padding:6px 10px;margin:6px 0;font-size:11px;color:#78350f;">'
                     f'<strong>⚠️ Dégradations de score (total : {abs(pen_pts):.0f} pts)</strong>'
                     f'{pen_lines}</div>')

    # Momentum HTML
    mom_html = ""
    if mom_msgs:
        mom_lines = " &nbsp;|&nbsp; ".join(mom_msgs)
        mom_html  = (f'<div style="font-size:11px;color:#6b7280;margin:4px 0;">'
                     f'📐 {mom_lines}</div>')

    return f"""
<div style="background:#fff;border-radius:8px;border:1px solid #e5e7eb;
            margin:14px 0;overflow:hidden;font-family:-apple-system,sans-serif;">

  <!-- En-tête -->
  <div style="background:{_score_color(score)};padding:10px 16px;color:#fff;">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;">
      <div>
        <strong style="font-size:20px;">{ticker}</strong> &nbsp;{_dir_badge(direction)}
        <div style="font-size:12px;opacity:.85;margin-top:3px;">{duration}</div>
      </div>
      <div style="text-align:right;">
        <div style="font-size:22px;font-weight:bold;">{score}/100</div>
        <div style="font-size:13px;font-weight:bold;opacity:.95;">{setup_quality}</div>
        <div style="font-size:11px;opacity:.75;">{len(tf_agree)}/5 TF en accord</div>
      </div>
    </div>
  </div>

  <!-- Statut marché + R/R résumé -->
  <div style="background:#1e293b;color:#e2e8f0;padding:6px 16px;
              font-size:12px;display:flex;justify-content:space-between;align-items:center;">
    <div>
      Statut : &nbsp;{_market_status_badge(market_status)}
    </div>
    <div style="font-weight:bold;">
      R/R : <span style="color:{'#86efac' if rr and rr>=2 else '#fca5a5'};">{rr_fmt(rr)}</span>
      &nbsp; {rr_quality}
    </div>
  </div>

  <!-- Prix horodaté -->
  <div style="background:#fef3c7;border-bottom:1px solid #fde68a;
              padding:6px 16px;font-size:12px;color:#78350f;">
    ⏰ <strong>PRIX ANALYSE : ${price:,.6g}</strong> &nbsp;·&nbsp; {ts}
    <span style="color:#92400e;margin-left:6px;">⚠️ Vérifier le prix actuel avant d'entrer</span>
  </div>

  <div style="padding:12px 16px;font-size:13px;">

    <!-- Dégradations éventuelles -->
    {pen_html}

    <!-- Contexte BTC -->
    {f'<div style="background:#f0f9ff;border-left:3px solid #0ea5e9;padding:6px 10px;margin:6px 0;font-size:12px;color:#0c4a6e;"><strong>🌐 Contexte BTC</strong> — {btc_txt}</div>' if btc_txt else ""}

    <!-- Confluence Ichimoku multi-TF -->
    <strong>📊 Confluence Ichimoku — méthode Péloille</strong>
    <div style="margin:6px 0 10px;">
      {_tf_table(tf_detail, list(TIMEFRAMES.keys()))}
    </div>

    <!-- Cibles Ichimoku + Stop structurel -->
    <div style="background:#f0fdf4;border-radius:6px;padding:8px 12px;margin:8px 0;">
      <strong>🎯 Cibles structurelles Ichimoku</strong>
      {_ichimoku_targets_block(risk)}
      <div style="margin-top:6px;font-size:12px;">
        <table style="border-collapse:collapse;width:100%;">
          <tr>
            <td style="padding:3px 8px;"><strong>Entrée</strong></td>
            <td style="padding:3px 8px;font-family:monospace;">{fmt(price)}</td>
            <td style="padding:3px 8px;"><strong>Cible 1</strong> <em style="color:#6b7280;font-size:11px;">({tgt_c_name})</em></td>
            <td style="padding:3px 8px;font-family:monospace;color:#16a34a;"><strong>{fmt(tgt_c)}</strong></td>
          </tr>
          <tr>
            <td style="padding:3px 8px;"><strong>Stop</strong> <em style="color:#6b7280;font-size:11px;">({sl_name})</em></td>
            <td style="padding:3px 8px;font-family:monospace;color:#dc2626;"><strong>{fmt(sl)}</strong></td>
            <td style="padding:3px 8px;"><strong>Cible 2</strong> <em style="color:#6b7280;font-size:11px;">({tgt_a_name})</em></td>
            <td style="padding:3px 8px;font-family:monospace;color:#2563eb;"><strong>{fmt(tgt_a)}</strong></td>
          </tr>
          <tr style="background:#f9fafb;">
            <td style="padding:3px 8px;" colspan="2">
              <strong>Ratio R/R :</strong> {rr_fmt(rr)} &nbsp; {rr_quality}
            </td>
            <td style="padding:3px 8px;" colspan="2">
              <em style="font-size:11px;color:#6b7280;">SL structurel basé sur {sl_name}</em>
            </td>
          </tr>
        </table>
      </div>
    </div>

    <!-- Momentum -->
    {mom_html}

    <!-- Patterns chandelier -->
    <div style="margin:8px 0;">
      <strong>🕯️ Patterns chandelier</strong><br>
      <div style="margin-top:4px;">{_candle_block(tf_a, direction)}</div>
    </div>

    <!-- RSI multi-TF (compact) -->
    <div style="margin:8px 0;font-size:12px;color:#374151;">
      <strong>RSI</strong> — {" &nbsp;|&nbsp; ".join(rsi_lines) if rsi_lines else "Données indisponibles"}
    </div>

    <!-- Analyse risque & levier -->
    <strong>⚡ Risque & Levier</strong>
    <div style="margin:4px 0;color:#374151;font-size:12px;">
      Stop : <strong>{sl_name}</strong> → <strong style="color:#dc2626;">{fmt(sl)}</strong>
      &nbsp;·&nbsp; Levier suggéré (90j) :
      <strong style="color:#2563eb;font-size:15px;">{risk.get("suggested_leverage","—")}x</strong>
    </div>

    {"<div style='background:#fef9c3;border-left:3px solid #ca8a04;padding:6px 10px;margin:6px 0;font-size:12px;color:#92400e;'>" + risk["warning"] + "</div>" if risk.get("warning") else ""}

    <table style="width:100%;border-collapse:collapse;font-size:12px;margin-top:6px;">
      <tr style="background:#f3f4f6;">
        <th style="padding:4px 8px;text-align:left;">Levier</th>
        <th style="padding:4px 8px;text-align:left;">Prix liquidation</th>
        <th style="padding:4px 8px;text-align:left;">Distance</th>
        <th style="padding:4px 8px;text-align:left;">Sécurité 90j</th>
      </tr>
      {_lev_rows(risk["liquidation_table"], risk["safety_assessment"], risk["suggested_leverage"], price, direction)}
    </table>

    {"<div style='margin-top:6px;font-size:12px;'><strong>Plage 90j (1σ) :</strong> " + f"${risk['price_range_90']['low']:,.4g} → ${risk['price_range_90']['high']:,.4g} (±{risk['price_range_90']['vol_pct']}%)</div>" if risk.get("price_range_90") else ""}

    <!-- Sentiment marché -->
    <div style="margin-top:8px;font-size:12px;background:#f9fafb;
                padding:6px 10px;border-radius:4px;">
      <strong>📈 Structure marché</strong><br>
      {sent_txt}<br>
      {f"<div style='margin-top:3px;'>{alt_mini}</div>" if alt_mini else ""}
    </div>

    <div style="margin-top:10px;text-align:center;">
      <a href="{binance_url}"
         style="background:#f59e0b;color:#fff;padding:7px 20px;border-radius:5px;
                text-decoration:none;font-weight:bold;font-size:13px;">
        Voir {ticker}/USDT Futures →
      </a>
    </div>

  </div>
</div>"""


def build_html_email(opportunities: list, analysis_time: str, total_analyzed: int) -> str:
    long_c  = sum(1 for o in opportunities if o["scoring"]["direction"] == "LONG")
    short_c = sum(1 for o in opportunities if o["scoring"]["direction"] == "SHORT")
    body    = "".join(_build_block(o) for o in opportunities) if opportunities else (
        '<p style="text-align:center;color:#6b7280;">Aucune opportunité détectée.</p>'
    )

    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f3f4f6;">
<div style="max-width:700px;margin:0 auto;padding:16px;">

  <div style="background:linear-gradient(135deg,#1e3a5f,#2563eb);color:#fff;
              border-radius:10px 10px 0 0;padding:18px 24px;text-align:center;">
    <h1 style="margin:0;font-size:20px;">📈 Crypto Trading Alerts — Ichimoku Péloille</h1>
    <p style="margin:4px 0 0;opacity:.8;font-size:13px;">Analyse multi-timeframe 15min/1h/4h/1j/1sem · {analysis_time}</p>
  </div>

  <div style="background:#1e40af;color:#fff;padding:10px 24px;
              display:flex;justify-content:space-around;text-align:center;">
    <div><div style="font-size:20px;font-weight:bold;">{total_analyzed}</div>
         <div style="font-size:10px;opacity:.8;">Analysées</div></div>
    <div><div style="font-size:20px;font-weight:bold;color:#86efac;">{long_c}</div>
         <div style="font-size:10px;opacity:.8;">LONG</div></div>
    <div><div style="font-size:20px;font-weight:bold;color:#fca5a5;">{short_c}</div>
         <div style="font-size:10px;opacity:.8;">SHORT</div></div>
  </div>

  <div style="background:#fef2f2;border:1px solid #fecaca;padding:7px 16px;
              margin-bottom:12px;font-size:11px;color:#991b1b;border-radius:0 0 6px 6px;">
    ⚠️ Prix au moment de l'analyse — vérifiez le cours actuel avant toute entrée.
    Ichimoku Péloille : Kumo → Kijun → Lagging Span → Tenkan. Analyse toutes les 15min.
  </div>

  {body}

  <div style="text-align:center;padding:14px;color:#9ca3af;font-size:11px;">
    Ichimoku Péloille · RSI · Chandelier · Alt Season · BTC Dominance<br>
    Données Yahoo Finance · CoinGecko · Méthode : Trading with Ichimoku (Karen Péloille)
  </div>
</div>
</body></html>"""


def send_no_opportunity_report(analysis_time: str, total_analyzed: int,
                                btc_context: dict = None) -> bool:
    """
    Envoie un email de synthèse quand aucune opportunité n'est détectée.
    Permet de confirmer que le bot tourne correctement.
    """
    if not EMAIL_SENDER or not EMAIL_PASSWORD or not EMAIL_RECIPIENT:
        logger.warning("Secrets email manquants — rapport de synthèse non envoyé")
        return False

    btc_trend   = btc_context.get("trend", "inconnu") if btc_context else "inconnu"
    btc_msg     = btc_context.get("message", "")      if btc_context else ""
    btc_color   = {"bullish": "#16a34a", "bearish": "#dc2626",
                   "range": "#ca8a04", "uncertain": "#ca8a04"}.get(btc_trend, "#6b7280")
    btc_label   = btc_trend.upper()

    html = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f3f4f6;">
<div style="max-width:600px;margin:0 auto;padding:16px;font-family:-apple-system,sans-serif;">

  <div style="background:linear-gradient(135deg,#1e3a5f,#374151);color:#fff;
              border-radius:10px 10px 0 0;padding:18px 24px;text-align:center;">
    <h1 style="margin:0;font-size:18px;">📊 Rapport de scan — Aucune opportunité</h1>
    <p style="margin:6px 0 0;opacity:.8;font-size:13px;">{analysis_time}</p>
  </div>

  <div style="background:#fff;border:1px solid #e5e7eb;border-top:none;
              border-radius:0 0 8px 8px;padding:20px 24px;">

    <div style="background:#f0fdf4;border-left:4px solid #16a34a;padding:10px 14px;
                border-radius:0 6px 6px 0;margin-bottom:16px;">
      ✅ <strong>Le bot a bien tourné et analysé {total_analyzed} cryptos.</strong><br>
      <span style="font-size:12px;color:#6b7280;">Aucun setup ne répond aux critères Ichimoku stricts du moment.</span>
    </div>

    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <tr style="background:#f9fafb;">
        <td style="padding:8px 12px;font-weight:bold;">🔍 Cryptos analysées</td>
        <td style="padding:8px 12px;">{total_analyzed}</td>
      </tr>
      <tr>
        <td style="padding:8px 12px;font-weight:bold;">📈 Opportunités retenues</td>
        <td style="padding:8px 12px;color:#dc2626;">0</td>
      </tr>
      <tr style="background:#f9fafb;">
        <td style="padding:8px 12px;font-weight:bold;">🌐 Contexte BTC</td>
        <td style="padding:8px 12px;">
          <span style="background:{btc_color};color:#fff;padding:2px 8px;
                border-radius:3px;font-size:11px;font-weight:bold;">{btc_label}</span>
          &nbsp; <span style="color:#6b7280;font-size:12px;">{btc_msg}</span>
        </td>
      </tr>
    </table>

    <div style="margin-top:16px;padding:12px;background:#fef3c7;border-radius:6px;
                font-size:12px;color:#78350f;">
      <strong>Pourquoi aucune alerte ?</strong><br>
      Les filtres stricts Ichimoku v4 bloquent les signaux si :<br>
      • Chikou Span du mauvais côté sur 1j<br>
      • Prix dans le nuage (Kumo) sur 1j ou 1sem<br>
      • Marché en range sur 1j + 4h<br>
      • Entrée trop tardive (prix &gt; 4× ATR du Kijun)<br>
      • Contexte BTC défavorable (−15 pts)<br>
      • Ratio R/R &lt; 2.0 même si le score Ichimoku est bon
    </div>

    <p style="margin-top:14px;font-size:11px;color:#9ca3af;text-align:center;">
      Prochain scan dans ~15 min · Ichimoku Péloille · Score min = 70/100 · R/R min = 2.0
    </p>
  </div>
</div>
</body></html>"""

    subject = f"📊 Crypto Scan — Aucune opportunité — {analysis_time}"
    msg     = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = EMAIL_RECIPIENT
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as srv:
            srv.ehlo(); srv.starttls()
            srv.login(EMAIL_SENDER, EMAIL_PASSWORD)
            srv.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
        logger.info("✅ Rapport de synthèse envoyé (0 opportunité)")
        return True
    except smtplib.SMTPException as e:
        logger.error(f"Échec envoi rapport : {e}")
        return False


def send_email(opportunities: list, analysis_time: str, total_analyzed: int) -> bool:
    if not EMAIL_SENDER or not EMAIL_PASSWORD or not EMAIL_RECIPIENT:
        logger.error("Secrets email manquants (EMAIL_SENDER / EMAIL_PASSWORD / EMAIL_RECIPIENT)")
        return False

    opps    = opportunities[:MAX_OPPS_PER_EMAIL]
    html    = build_html_email(opps, analysis_time, total_analyzed)
    long_c  = sum(1 for o in opps if o["scoring"]["direction"] == "LONG")
    short_c = sum(1 for o in opps if o["scoring"]["direction"] == "SHORT")

    subject = f"🚨 Crypto Alert — {long_c} LONG · {short_c} SHORT — {analysis_time}"
    if len(opportunities) > MAX_OPPS_PER_EMAIL:
        subject += f" (+{len(opportunities) - MAX_OPPS_PER_EMAIL} autres)"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = EMAIL_RECIPIENT
    msg.attach(MIMEText(html, "html"))

    estimated_kb = len(html.encode()) / 1024
    logger.info(f"Email HTML : ~{estimated_kb:.0f} KB")
    if estimated_kb > 90:
        logger.warning(f"Email volumineux ({estimated_kb:.0f} KB) — risque de coupure Gmail")

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as srv:
            srv.ehlo()
            srv.starttls()
            srv.login(EMAIL_SENDER, EMAIL_PASSWORD)
            srv.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_string())
        logger.info(f"✅ Email envoyé ({len(opps)} opportunités)")
        return True
    except smtplib.SMTPException as e:
        logger.error(f"Échec email : {e}")
        return False
