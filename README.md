# 📈 Crypto Trading Alerts

Système d'alerte automatique qui scanne en continu le **Top 20 cryptos** (par capitalisation boursière, stablecoins et wrapped tokens exclus) et envoie un email HTML dès qu'une opportunité **LONG ou SHORT** est détectée via la méthode **Ichimoku de Karen Péloille**.

Le scan tourne toutes les **5 minutes** via GitHub Actions (gratuit).

---

## ✨ Fonctionnalités

- **Méthode Ichimoku Péloille stricte** sur 5 timeframes (15m / 1h / 4h / 1j / 1sem)
- **Analyse hiérarchique v5** : Structure → Timing → Contexte → Exécution
- **Régimes de marché** par TF : trending, breakout, pullback, transition, range, overextended
- **Chikou enrichi** : clearance_score 0-100, type d'obstacle, densité
- **Niveaux plats détectés** : Kijun/SSB/SSA plats = aimants de prix prioritaires
- **Signaux Kijun typés** : fresh_break / reclaim_after_pullback / late_extension / weak_cross / failed_break
- **Extension normalisée** : healthy → mild → extended → overextended → euphoric
- **R/R multiples** : nearest / structural / stretch
- **Contexte BTC** : tendance BTC penalise/booste les alts automatiquement
- **Alt Season Index** : % d'alts surperformant BTC sur 30 jours (CoinGecko)
- **Anti-doublon intelligent** : 4 critères de re-alerte (nouveau break Kijun, score amélioré, prix bougé, cooldown 6h)
- **Prix horodaté** : chaque alerte affiche le prix exact au moment de l'analyse
- **Trade readiness** : `ready` / `wait` / `degraded` / `blocked`

---

## 🚀 Installation en 4 étapes

### Étape 1 — Dupliquer le dépôt sur GitHub

1. Crée un compte sur [github.com](https://github.com) si tu n'en as pas
2. Clique sur **"+"** → **"New repository"**
3. Donne-lui un nom (ex: `crypto-alerts`)
4. Laisse en **privé** (Private) — tes secrets ne seront pas visibles
5. Upload tous les fichiers de ce projet dans ce dépôt

### Étape 2 — Créer un mot de passe d'application Gmail

> Nécessaire pour que le script puisse envoyer des emails via ton compte Gmail.

1. Va sur [myaccount.google.com](https://myaccount.google.com)
2. **Sécurité** → active la **Validation en 2 étapes** (si pas déjà fait)
3. **Sécurité** → **Mots de passe des applications**
4. Sélectionne **"Autre"** → tape `crypto-alerts` → **Générer**
5. Copie le mot de passe à 16 caractères affiché (tu ne le reverras plus)

### Étape 3 — Configurer les secrets GitHub

Dans ton dépôt GitHub : **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Nom du secret     | Valeur                                                        |
|-------------------|---------------------------------------------------------------|
| `EMAIL_SENDER`    | ton adresse Gmail (ex: `samuel@gmail.com`)                    |
| `EMAIL_PASSWORD`  | le mot de passe d'application à 16 caractères                 |
| `EMAIL_RECIPIENT` | l'adresse qui reçoit les alertes (peut être la même)          |

### Étape 4 — Tester manuellement

1. Dans ton dépôt → onglet **Actions**
2. Clique sur **"Crypto Trading Alerts"** dans la liste à gauche
3. Clique sur **"Run workflow"** → **"Run workflow"**
4. Attends ~2 minutes → vérifie ta boîte mail si une opportunité est détectée

---

## ⏰ Fréquence d'exécution

Le scan tourne **toutes les 5 minutes** (minimum GitHub Actions) :

```yaml
- cron: "*/5 * * * *"
```

Les marchés crypto étant ouverts 24h/24, le scan permanent détecte les opportunités en temps réel. En l'absence d'opportunité, aucun email n'est envoyé. Le cooldown anti-doublon de **6 heures** évite les alertes répétitives pour le même setup.

---

## 📊 Architecture du scoring (100 pts)

### 4 phases hiérarchiques

```
Phase 1 — Structure   (0-40 pts)  ← 1wk + 1d : régime, Chikou, nuage
Phase 2 — Timing      (0-30 pts)  ← 4h + 1h + 15m : signal Kijun, biais
Phase 3 — Contexte    (0-15 pts)  ← BTC trend + Alt Season
Phase 4 — Exécution   (0-15 pts)  ← RSI + patterns chandelier
```

### Phase 1 — Structure

Le biais structurel est établi sur les TF longs (1wk et 1d) via le **régime de marché** :

| Régime           | Score max | Description                         |
|------------------|-----------|-------------------------------------|
| trending_up/down | 100%      | Tendance saine, alignement complet  |
| breakout         | 85%       | Cassure Kijun récente valide        |
| pullback         | 65%       | Repli dans la tendance (entry point)|
| transition       | 30%       | Changement de tendance en cours     |
| conflicted       | 15%       | Signaux contradictoires             |
| range            | 0%        | Ichimoku peu fiable (BLOQUANT)      |
| overextended     | 20%       | Prix trop loin du Kijun             |

Le **Chikou clearance_score** (0-100) mesure la liberté d'espace du Lagging Span et contribue jusqu'à 7 pts sur le journalier.

### Phase 2 — Timing

Le type de signal Kijun sur 4h/1h détermine la qualité du timing :

| Signal Kijun             | Multiplicateur | Interprétation                       |
|--------------------------|----------------|--------------------------------------|
| `fresh_break`            | 1.00           | Cassure propre dans les 3 bougies    |
| `reclaim_after_pullback` | 0.80           | Retour bullish après repli           |
| `none` (bon côté)        | 0.45           | Prix positionné sans signal actif    |
| `late_extension`         | 0.20           | Distance > 3 ATR du Kijun           |
| `weak_cross_equilibrium` | 0.15           | Kijun plat / range                   |
| `failed_break`           | 0.00           | Break raté, prix revenu en zone      |

### Conditions BLOQUANTES

1. Prix dans le nuage (Kumo) sur 1d ou 1wk
2. Chikou Span du mauvais côté sur 1d (validateur absolu Péloille)
3. Range détecté sur 1d ET 4h simultanément
4. Extension > 4× ATR du Kijun sur 1d (entrée tardive)
5. Moins de 3 TF en accord

### Seuil d'alerte

**Score ≥ 70/100** ET **R/R ≥ 2.0** sont requis pour qu'une alerte soit envoyée.

---

## 🎯 R/R multiples

Chaque alerte fournit 3 niveaux de cible :

| Cible              | Description                                      |
|--------------------|--------------------------------------------------|
| `nearest_target`   | Premier obstacle Ichimoku dans la direction      |
| `structural_target`| Niveau structurel (Kijun 1wk, SSB 1wk)          |
| `stretch_target`   | Cible étirée (MA200, ATR × 3.5)                 |

Le R/R est calculé sur la cible conservatrice (`nearest_target`). Les flat_levels (Kijun/SSB plats) sont intégrés comme cibles prioritaires.

---

## 🔧 Personnalisation

Tous les paramètres sont centralisés dans `src/config.py` :

| Paramètre               | Défaut | Description                                 |
|-------------------------|--------|---------------------------------------------|
| `TOP_N_CRYPTOS`         | 20     | Nombre de cryptos analysées                 |
| `SCORE_THRESHOLD`       | 70     | Score minimum pour déclencher une alerte    |
| `MIN_RR_RATIO`          | 2.0    | R/R minimum requis                          |
| `MAX_KIJUN_EXTENSION_ATR` | 4.0  | Extension max avant refus (entrée tardive)  |
| `ALERT_COOLDOWN_HOURS`  | 6      | Cooldown anti-doublon                       |
| `BTC_FILTER_ENABLED`    | True   | Contexte BTC pour les altcoins              |
| `MIN_TF_AGREE`          | 3      | Nombre minimum de TF en accord              |

---

## 📐 Sources de données

| Donnée              | Source                 | Fréquence   |
|---------------------|------------------------|-------------|
| Top N cryptos       | CoinGecko API publique | À chaque run|
| Prix OHLCV (5 TFs)  | Yahoo Finance (yfinance)| À chaque run|
| Prix temps réel     | CoinGecko API publique | À chaque run|
| Alt Season Index    | CoinGecko API publique | À chaque run|
| BTC Dominance       | CoinGecko API publique | À chaque run|

Aucune clé API payante requise.

---

## ⚠️ Avertissement

Ce système est un **outil d'aide à la décision**, pas un conseil en investissement. Les signaux sont générés à un instant T — vérifiez toujours le prix actuel avant d'entrer en position. Le trading avec levier comporte des risques de perte supérieure au capital investi.
