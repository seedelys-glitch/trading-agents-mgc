# MGC AI Trading Desk — état du projet

Dernière mise à jour : 23/10/2026 (étape 6, vague 1 terminée). Ce fichier est la mémoire du projet : on le lit
avant de reprendre le travail, on le met à jour après chaque étape.

## 1. Vision
Un bureau de recherche sur le Micro Gold (MGC) : 14 agents spécialisés (le directeur est le n° 14), chacun avec
4 fonctions de soutien (chercheur, professeur, documentaliste, gestionnaire des connaissances), qui analysent,
se vérifient entre eux et alimentent une bibliothèque de règles validées par Jabran.
**Recherche et simulation seulement** : aucun courtier, aucun ordre, réel ou simulé, envoyé automatiquement.
Jamais de données, de résultats ou de statistiques inventés ; pas de look-ahead ; pas de conclusion sur un
échantillon trop petit (moins de 30 trades).

## 2. Architecture (dossier `Documents\TradingAgents`)
| Partie | Rôle | Port |
|---|---|---|
| `tradingagents/`, `cli/`, `tests/` | Projet open source d'origine (TauricResearch), non modifié | – |
| `salle_des_marches/` | La Salle des marchés : desk de 6 spécialistes IA, calculs exacts (`calculs.py`), paquet `mgc/` (risque, vetos, calendrier CME, contrats, qualité des données, backtest V1, statistiques) | 8790 |
| `universite/` | **L'université** (ce projet) : programme séparé qui réutilise `calculs.py` et `mgc/` sans les modifier | 8780 |
| `ninjatrader/ExportBougiesMGC.cs` | Indicateur NinjaTrader (lecture seule, aucun ordre) qui écrira les bougies temps réel | – |
| `rapports/` | Données et résultats (jamais sur GitHub) ; base de l'université : `rapports\universite\universite.sqlite` | – |

Université, fichier par fichier :
- `base.py` : base SQLite (missions, étapes, documents, messages, jeux de bougies, boucles, appels IA, règles,
  extraits), migrations versionnées et réversibles (version 2).
- `moteur.py` : file de missions, ouvriers, délai maximal, nouveaux essais, reprise après arrêt, boucles avec budget.
- `donnees.py` : import CSV (TradingView, NinjaTrader), Yahoo (différé), fenêtre de replay sans look-ahead.
- `ia.py` : LM Studio en local, seulement pour un commentaire sans chiffre ; budget d'appels par jour.
- `bibliotheque.py` : règles (proposées, validées, rejetées, remplacées, avec versions) et recherche.
- `competences/` : ce que les agents savent réellement faire (voir 4).
- `serveur.py` + `ui/` : API locale (127.0.0.1 seulement) et bureau virtuel (grand hall SVG).

## 3. Technologies
Python 3.13 (venv `.venv`), pandas, numpy, SQLite, serveur HTTP de la bibliothèque standard, pytest.
Interface : HTML + CSS + JavaScript sans framework ni dépendance externe. IA : LM Studio (API locale, gratuite).
Aucun service payant.

## 4. Fonctionnalités terminées
| Agent | Compétence réelle | Vérifiée par |
|---|---|---|
| 1. SMC | Structure D1 / H1 / M15 (tendance, BOS / CHoCH, FVG, order blocks) avec `calculs.resume_smc` | agent 9 (reproductibilité) |
| 2. Fibonacci | Impulsion H1, retracement, zones 0.618–0.893 avec FVG (`calculs.fibo`) | agent 9 (reproductibilité) |
| 3. Ichimoku | Nuage, Tenkan / Kijun, Chikou D1 / H1 / M15 (`calculs.ichimoku`) | agent 9 (reproductibilité) |
| 8. Risques | Idée de trade → contrats, risque net, ratio, vetos (`mgc.risque`) ; veto = alerte au directeur | agent 9 (recalcul indépendant en ticks) |
| 6. VWAP & EMA 200 | VWAP de séance (depuis 17 h Chicago) + bandes, EMA 200 en M5/M15/H1, à un instant donné | agent 9 (recalcul indépendant) |
| 9. Secrétaire / auditeur | Vérifie les analyses et les replays ; lit STRATEGIE.md et propose les règles ; range les documents dans la bibliothèque | – |
| 13. Chercheur quantitatif | Contrôle qualité d'un jeu de bougies ; replay de la stratégie V1 (60/20/20, Monte-Carlo, régimes) | agent 9 |
| 14. Directeur | Confie une demande au bon agent ; synthèse des documents vérifiés | – |
Les agents 4, 5, 7, 10, 11, 12 sont affichés « en construction » (aucune activité simulée).
D1 est reconstruite par séance CME (17 h Chicago) à partir des petites unités, seulement quand la séance est finie.

Bureau virtuel : hall des 14 agents avec leur état réel (disponible, au travail, file d'attente, erreur, en
construction), fonctions de soutien allumées seulement pendant leur étape, liens seulement pour de vrais messages,
panneau par agent (mission, tâches, documents, soutiens, historique), demandes au directeur, données, boucles,
documents, bibliothèque, réglages. Zoom et déplacement. Vérifié sur écran PC et au format téléphone (360 px).

## 5. En cours / à faire (par priorité)
1. Étape 6, vague 2 : 5 macro (calendrier), 12 réactions aux annonces, 7 flux (estimé, dit comme tel).
2. Étape 7 : TradingView (import des exports CSV déjà possible).
3. Étape 8 : lien avec Jarvis. Étape 9 : fiabilité et docs.
4. Ensuite : bureau immersif (espaces, salle de réunion, labo, bibliothèque, bureau du directeur), en
   expliquant d'abord comment il s'intègre à l'architecture.

## 6. Problèmes connus et limites
- **Pas de données temps réel** : NinjaTrader 8 n'est pas installé (le dossier `donnees_ninja` n'existe pas).
  En attendant : Yahoo (différé d'environ 10 min, historique 1 min de 5 jours) ou exports TradingView.
- **Bookmap** reporté (pas de données de carnet d'ordres) : l'agent 4 reste en construction.
- Carte graphique 8 Go : un seul modèle d'IA chargé à la fois (`concurrence_ia` = 1).
- Bibliothèque : la clé d'une règle dépend de sa place dans sa section ; insérer un point au milieu d'une section
  de STRATEGIE.md fait proposer de nouvelles versions pour les points suivants (rien n'est perdu, à valider).
- Recherche « par le sens » seulement si un modèle d'embeddings est choisi dans les réglages (sinon par mots).
- SMC, Fibonacci, Ichimoku : l'agent 9 contrôle la REPRODUCTIBILITÉ (mêmes bougies, même fonction, aucune
  bougie future), pas un recalcul indépendant ; c'est écrit sur chaque procès-verbal.
- Le dossier git du PC n'a pas de lien vers GitHub : la sauvegarde GitHub est une copie (voir 9).

## 7. Tests (23/10/2026)
- Conteneur de développement : 179 tests de la Salle + 64 de l'université = **243 réussis** (étape 6, vague 1).
- Sur le PC de Jabran (Python 3.13.16) : 217 réussis avant l'ajout du replay et de la bibliothèque
  (les tests ajoutés depuis n'y ont pas encore été lancés).
- Couverture : aucun ordre possible (analyse du code), anti look-ahead (mêmes résultats avec ou sans les bougies
  futures), reprise après arrêt, nouvel essai, délai, budget des boucles, vérification indépendante, rejet d'un
  chiffre faux, de bout en bout par le serveur ; SMC / Fibo / Ichimoku identiques avec ou sans bougies
  futures ; risque recompté et concordant avec le moteur de la Salle ; veto et limite du jour.

## 8. Décisions techniques
- L'université est construite dans TradingAgents, à côté de la Salle, car tout le calcul MGC fiable y est déjà
  (`mgc/`, `calculs.py`) ; programme séparé pour ne rien casser de la Salle.
- Pas de framework web : le projet n'en utilise pas ; tout fonctionne hors ligne, sans installation.
- Un agent n'existe à l'écran que par ce qu'il fait réellement (compétence branchée) : sinon « en construction ».
- L'IA ne fournit jamais un chiffre : les chiffres viennent du calcul, l'IA ne commente que (refus sinon).
- Chaque chiffre important est recalculé par un autre agent avec un code différent (agent 9).

## 9. Commandes
- Lancer l'université : double-clic sur `Universite MGC.bat` (ou `.venv\Scripts\python.exe -m universite`).
- Lancer la Salle des marchés : `Salle des marches.bat`.
- Tester : `.venv\Scripts\python.exe -m pytest -q salle_des_marches\tests universite\tests`
- Sauvegarde GitHub : dépôt privé `seedelys-glitch/trading-agents-mgc` (code seulement : jamais `.env`,
  `rapports\`, journaux Excel).

## 10. Matériel, API, licences
PC Windows : RTX 5060 8 Go, 32 Go de RAM, Ryzen 5 5500. LM Studio : gemma-4-e4b (chargé), qwen3.5-9b (installé).
Aucune API payante. NinjaTrader 8 et Bookmap : non installés pour l'instant.
