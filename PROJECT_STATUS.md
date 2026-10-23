# MGC AI Trading Desk — état du projet

Dernière mise à jour : 23/10/2026 (bureau immersif E1 à E6 terminés et testés ; reste E7 : livraison sur le PC et essai par Jabran). Ce fichier est la mémoire du projet : on le lit
avant de reprendre le travail, on le met à jour après chaque étape.

## 0. Audit du 23/10/2026 (soir, sur le PC de Jabran) : à lire en premier
- Tests sur le PC : **263 réussis, 0 échec** (`pytest -q salle_des_marches\tests universite\tests`, 65 s).
- Testé en réel sur le PC (et non plus seulement avec de faux flux) : calendrier Forex Factory (86 annonces) et
  flux des discours de la Fed (15 discours). Le lexique faucon / colombe fonctionne sur un discours de politique
  monétaire (Waller, 08/10/2026 : 2 + 2 expressions, 4 citations exactes) ; rien sur un discours de réglementation
  bancaire, ce qui est normal.
- Jarvis voit l'université. L'université qui tournait avait été lancée AVANT la mise à jour (4 agents prêts sur 14) :
  **à redémarrer par Jabran** (fermer, puis double-clic sur « Universite MGC.bat »).
- FAIT : tout est enregistré dans le git du PC (commit 8e9d179 « avant : règles du 23/10 (salle) + université MGC +
  PROJECT_STATUS ») et copié sur GitHub (trading-agents-mgc).
- FAIT : `mgc/backtest.py` et `mgc/risque.py` suivent les règles du 23/10 (4 objectifs 0 / -0.272 / -1.272 / -2.618,
  comptes A 25/25/25/25 et B 50/0/25/25, stop au point d'entrée si la bougie d'entrée clôture en gain, au 0.5 après
  le -0.272, au 0 après le -1.272 ; plus de break-even à 35 %). Le replay de l'agent 13 prend le compte A ou B.
  Limite écrite : l'entrée est simulée sur la confirmation H1, la cascade 48 min / 12 min n'est pas rejouée.

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
  extraits), migrations versionnées et réversibles (version 4).
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
| 5. Macro | Calendrier USD de la semaine (Forex Factory, public), historique des annonces (table `annonces`), 48 h à venir, blocages (`mgc.annonces`) | agent 9 (blocages refaits par un autre code) |
| 7. Flux (estimé) | Profil de volume, POC, zone de valeur, delta estimé (`calculs.order_flow`), toujours dit « estimation » | agent 9 (reproductibilité) |
| 8. Risques | Idée de trade → contrats, risque net, ratio, vetos (`mgc.risque`) ; veto = alerte au directeur | agent 9 (recalcul indépendant en ticks) |
| 6. VWAP & EMA 200 | VWAP de séance (depuis 17 h Chicago) + bandes, EMA 200 en M5/M15/H1, à un instant donné | agent 9 (recalcul indépendant) |
| 9. Secrétaire / auditeur | Vérifie les analyses et les replays ; lit STRATEGIE.md et propose les règles ; range les documents dans la bibliothèque | – |
| 13. Chercheur quantitatif | Lit le dossier d'exports TradingView (une fois par fichier, toutes les unités dans un jeu) ; contrôle qualité d'un jeu de bougies ; replay de la stratégie V1 (60/20/20, Monte-Carlo, régimes) | agent 9 |
| 14. Directeur | Confie une demande au bon agent ; synthèse des documents vérifiés | – |
| 10. Discours | Flux officiel federalreserve.gov, texte gardé dans la bibliothèque, lexique « faucon / colombe » fixé à l'avance, citations exactes | agent 9 (recompte mot à mot, citations retrouvées) |
| 11. Historien | Précédents d'un thème dans les textes gardés et l'historique des annonces, avec date et source | agent 9 (chaque citation existe telle quelle) |
| 12. Réactions | Mouvement du gold à +5 / +15 / +60 min et excursions sur 1 h après chaque annonce gardée ; < 20 cas = pas de conclusion | agent 9 (requêtes directes sur les bougies) |

Seul l'agent 4 (heatmap) est affiché « en construction » : il attend Bookmap (aucune activité simulée).
D1 est reconstruite par séance CME (17 h Chicago) à partir des petites unités, seulement quand la séance est finie.

Bureau virtuel : hall des 14 agents avec leur état réel (disponible, au travail, file d'attente, erreur, en
construction), fonctions de soutien allumées seulement pendant leur étape, liens seulement pour de vrais messages,
panneau par agent (mission, tâches, documents, soutiens, historique), demandes au directeur, données, boucles,
documents, bibliothèque, réglages. Zoom et déplacement. Vérifié sur écran PC et au format téléphone (360 px).

Lien avec Jarvis (`Documents\Jarvis\universite_lien.py` + `chef.py` + `desk_chat.py`) : ligne « Université MGC »
dans le chef d'orchestre, bouton « lancer », voix / appli / Telegram « état de l'université » et « ouvre
l'université ». Depuis le 24/10 : **Jarvis parle au directeur** (« directeur, … », puce « Directeur » du chat) via
`POST /api/directeur` (`universite/directeur_chat.py`, table `conversation`, migration 5), et **la caméra de Jarvis
montre l'université en 3D** (`?camera=1`, relayée par Jarvis sur `/universite/…`, jeton de 12 h pour l'appli).
Aucun lien avec `ordres.py`.

## 5. En cours / à faire (par priorité)
1. Redémarrer l'université, puis premières missions réelles (calendrier, discours, import TradingView, replay A et B).
2. **Bureau immersif (en cours)**. Explication de l'intégration : document « Bureau immersif de l'université —
   comment il s'intègre » (https://claude.ai/artifact/Lm3BeP6WvUxnFbYeUvcDK4). Principe : plan en données
   (`universite/scene.py`, x/y/z en mètres, prêt pour un futur moteur 3D/VR) + état réel de la base + moteur
   d'affichage isométrique SVG ; l'ancien hall reste.
   - E1 FAIT : `scene.py` (8 zones, 14 postes, `verifier()`), `/api/scene`, `/api/agent/N/espace` (statut, poste,
     missions, documents, dernier document, sources, échanges, tâches lançables, graphique = jeu/instant/unité
     réellement lus), `/api/bougies?jeu&unite&instant&n` (bougies fermées seulement, 1000 max).
   - E2 FAIT : `ui/bureau.js` dessine le plateau isométrique (zones, postes, mobilier fixe, étiquettes, liens =
     vrais messages) dans le même SVG que le hall ; bouton ◯/▦ pour passer de l'un à l'autre (choix retenu dans le
     navigateur, `?vue=hall` force l'ancien hall). Poste en construction = bureau éteint, personne assise.
   - E3 FAIT : en s'approchant (zoom), un écran au-dessus de chaque poste montre son dernier document réel (genre,
     statut de vérification, titre, heure) et la courbe des clôtures des bougies que l'agent a réellement lues
     (`/api/bougies`, fermées à l'instant analysé). `/api/etat` donne maintenant `dernier_document` par agent.
   - E4 FAIT : onglet « Son espace » (ouvert d'office en cliquant un poste) : travail en cours, file, dernier
     document avec son statut, graphique en chandeliers des bougies réellement lues (trait = instant analysé, rien
     après), sources citées (jeu, unité, période, document, lien, fichier), « Confier une tâche » = vraie mission,
     dernières missions, échanges. `/api/agent/N/espace` donne aussi les noms des jeux ; une source garde sa propre
     référence (`document`) et dit où elle est citée (`cite_dans`).
   - E5 FAIT : clic sur une pièce (sol ou nom) = ce qu'elle contient vraiment (`/api/zone/<cle>`) : réunion =
     derniers messages entre agents ; bibliothèque = règles par statut, extraits gardés, contrôles de l'agent 9 ;
     pôle macro = annonces des 48 h ; données = jeux et fichiers TradingView lus ; labo = replay / contrôle à lancer ;
     les autres = agents de la pièce et leurs derniers documents.
   - E6 FAIT : bureau du directeur = file de travail, dernière synthèse (texte), demandes reçues, alertes reçues,
     bouton « Demander une synthèse ».
   - 3D (23/10, demande de Jabran « comme un vrai jeu ») : `ui/bureau3d.js` (three.js r170 en copie locale dans
     `ui/vendor/three`, licence MIT, aucun téléchargement) relit la même scène et le même état : grand hall (marbre,
     colonnes, fenêtres, mezzanine, lustres), bureaux bois et or, écran de chaque poste = vrai document ou mission en
     cours, agents (seuls ceux au travail bougent), anneau au sol = état réel, arcs lumineux = vrais messages, ombres et
     halo lumineux. Clic = espace de l'agent ou pièce. Sans WebGL 2 ou avec `?vue=plan` : vue 2,5D SVG. Le serveur
     force le type « text/javascript » (sous Windows le registre peut casser les modules).
   - E7 : livrer sur le PC (fichiers de `universite/`), Jabran relance l'université et regarde ; ensuite seulement,
     idées possibles : moteur 3D (Three.js) qui relirait la même scène, VR plus tard.
3. Quand NinjaTrader 8 / Bookmap seront installés : temps réel et agent 4 (heatmap).

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
- Calendrier : le flux gratuit ne donne que la semaine en cours et pas le chiffre publié ; l'historique des annonces
  commence au premier lancement de l'agent 5 (boucle conseillée toutes les 6 h). Pas joignable depuis le conteneur
  de développement (testé avec un faux flux), utilisé chaque jour par la Salle sur le PC.
- TradingView : pas d'API de données gratuite ni officielle ; on lit les exports CSV (historiques, pas temps réel).
  Les alertes (webhooks) demandent un abonnement payant : non utilisées.
- Discours de la Fed : le lexique est un simple comptage d'expressions anglaises (une négation n'est pas comprise).
  Le flux officiel n'est pas joignable depuis le conteneur de développement : testé avec de faux textes, à tester
  sur le PC (étape 9).
- Le dossier git du PC n'a pas de lien vers GitHub : la sauvegarde GitHub est une copie (voir 9).

## 7. Tests (23/10/2026)
- Conteneur de développement : 182 tests de la Salle + 117 de l'université = **299 réussis** (directeur via Jarvis),
  avec la commande ci-dessous (les deux dossiers ensemble fonctionnent maintenant).
- Sur le PC de Jabran (Python 3.13.16) : 217 réussis avant l'ajout du replay et de la bibliothèque
  (les tests ajoutés depuis n'y ont pas encore été lancés).
- Couverture : aucun ordre possible (analyse du code), anti look-ahead (mêmes résultats avec ou sans les bougies
  futures), reprise après arrêt, nouvel essai, délai, budget des boucles, vérification indépendante, rejet d'un
  chiffre faux, de bout en bout par le serveur ; SMC / Fibo / Ichimoku identiques avec ou sans bougies
  futures ; risque recompté et concordant avec le moteur de la Salle ; veto et limite du jour ; calendrier gardé
  sans doublon, blocages FOMC / discours, panne de la source = aucun document ; réactions recomptées, sans look-ahead,
  trou de données refusé ; migrations 1 → 3 réversibles ; discours : expressions entières seulement, citation inventée
  rejetée, flux en panne = aucun document ; historien : rien cité de mémoire ; TradingView : nom des exports, import unique, Téléchargements filtrés.

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
