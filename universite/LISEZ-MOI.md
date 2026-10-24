# Université MGC

Le bureau de recherche des 14 agents spécialisés Micro Gold. **Recherche et simulation seulement** : aucun
courtier, aucun ordre, aucune clé. Tout tourne sur le PC (adresse `http://127.0.0.1:8780`, invisible depuis
Internet et depuis le téléphone).

## Lancer
Double-clic sur **« Universite MGC.bat »** dans `Documents\TradingAgents`. La page s'ouvre dans le navigateur.
Un deuxième double-clic rouvre simplement la page.

## Ce qui marche aujourd'hui (réellement)
| Agent | Ce qu'il fait |
|---|---|
| 1. SMC | Structure en D1, H1 et 15 min : tendance, dernières cassures (BOS / CHoCH), FVG et order blocks proches |
| 2. Fibonacci | Dernière belle impulsion H1, retracement actuel, zones 0.618 à 0.893 valables seulement avec un FVG (jamais le 0.5) |
| 3. Ichimoku | Nuage, Tenkan / Kijun, Chikou en D1, H1 et 15 min |
| 7. Flux (estimé) | Profil de volume, POC, zone de valeur, delta ESTIMÉ et gros volumes, depuis les bougies 5 min ; toujours écrit « estimation » (pas un carnet d'ordres) |
| 8. Risques | Évalue une idée de trade (sens, entrée, stop, TP1) : contrats MGC, risque net avec frais, ratio, vetos. Calcul seulement, aucun ordre |
| 5. Macro | Télécharge le calendrier USD de la semaine (Forex Factory, gratuit), garde chaque annonce dans l'historique, liste les 48 h à venir et dit ce qui bloque maintenant (FOMC, discours de la Fed, annonce forte) ; prévient le gestionnaire des risques |
| 6. VWAP & EMA 200 | VWAP de séance (depuis 17 h à Chicago) avec bandes, EMA 200 en 5 min, 15 min et 1 h, à un instant donné (direct ou replay) |
| 9. Secrétaire / auditeur | Recalcule de son côté les chiffres de l'agent 6, recompte les replays, le risque, les blocages d'annonces, les réactions et les discours (calcul indépendant), vérifie chaque citation ; pour SMC, Fibonacci, Ichimoku et le flux il contrôle que le calcul est reproductible sur les mêmes bougies, sans bougie future. Le document passe « vérifié » ou « rejeté » |
| 10. Discours | Lit les discours officiels de la Fed (federalreserve.gov, gratuit), garde le texte, compte les expressions « faucon » / « colombe » d'un lexique fixé à l'avance et cite les phrases exactes |
| 11. Historien | Retrouve les précédents d'un thème dans ce qui a été gardé (discours, annonces, bibliothèque), avec date et source ; rien de mémoire |
| 12. Réactions | Mesure comment le gold a vraiment bougé après chaque annonce gardée (+5, +15, +60 min, plus haut / plus bas de l'heure), sur un jeu de bougies 1 à 5 min ; moins de 20 cas = aucune conclusion |
| 13. Chercheur quantitatif | Contrôle un jeu de bougies (nombre, période, trous) et rejoue ta stratégie V1 (1H / 12H) : entraînement / validation / test, Monte-Carlo, résultats par régime ; moins de 30 trades = aucune conclusion |
| 14. Directeur | Reçoit les demandes, les confie au bon agent, fait la synthèse de ce qui est vérifié |

Seul l'agent 4 (heatmap Bookmap) reste **« en construction »** : il attend Bookmap, et le bureau ne fait pas semblant.

Astuce : une boucle « Calendrier » toutes les 6 heures et une boucle « Discours de la Fed » une fois par jour (bouton Boucles) remplit l'historique des annonces semaine après
semaine ; le site ne donne que la semaine en cours, l'historique commence donc le jour du premier lancement.

## Le bureau
La page s'ouvre sur le **bureau en 3D** (comme un jeu vidéo : grand hall, marbre, mezzanine, lustres ; souris :
clic gauche glissé = tourner, molette = avancer, clic droit glissé = se déplacer ; au téléphone : un doigt pour tourner,
deux pour zoomer). Sans carte graphique compatible, la vue 2,5D s'affiche à la place (`?vue=plan` pour la forcer).
Comme dans la vue d'en haut : bureau du directeur au centre, salle d'analyse technique,
pôle macro et discours, salle de réunion, bibliothèque et vérification, labo quant, contrôle des risques,
salle des données. Chaque agent est assis à son poste ; sa couleur dit ce qu'il fait **réellement**
(vert disponible, bleu au travail, orange file d'attente, rouge erreur, gris en construction). Les flèches
sont de vrais messages entre agents.
- Molette ou boutons + / − pour s'approcher : un petit écran apparaît au-dessus de chaque poste avec son
  dernier document (vérifié, à vérifier, rejeté) et la courbe des bougies qu'il a réellement lues.
- Clic sur un agent : **son espace** (document en cours, graphique des bougies lues avec l'instant analysé,
  sources citées, « Confier une tâche », missions, échanges).
- Clic sur une pièce (sol ou nom) : ce qu'elle contient vraiment (réunion = derniers échanges, bibliothèque =
  règles et extraits, données = jeux et imports, directeur = synthèse, demandes, alertes...).
- Bouton ◯ : l'ancien hall en cercle (bouton ▦ pour revenir au bureau).

## Parler au directeur depuis Jarvis
Jarvis est la tête de tous les agents : il parle au **directeur** (agent 14), qui commande l'université.
À la voix, dans l'appli ou sur Telegram : « directeur, où en est l'université ? », « dis au directeur de lancer une
analyse Fibonacci », « directeur, fais-moi la synthèse », « où en est la mission ? », « des alertes ? »… ou la puce
« Directeur » du chat des chefs d'agents. Le directeur répond seulement avec ce que contient la base ; il confie les
missions à l'agent qui sait les faire (jamais sans bougies importées) ; une réponse de l'IA qui contient un chiffre
absent de la base est refusée. API : `POST /api/directeur {"texte": …}`, historique `GET /api/directeur`.
La caméra de Jarvis (écran du PC, appli) montre ce bureau en 3D : `?camera=1` (vue qui tourne lentement).

## Mémoire (Scribe et Archiviste)
Le **Scribe** (agent 15) note tout seul, toutes les 5 minutes, ce qui s'est passé : missions des agents, conversation
avec le directeur, chat du desk de Jarvis, ce que Jarvis retient, notes dictées, sessions Claude du PC, règles
décidées, alertes, PROJECT_STATUS.md. Chaque chose devient un **bloc** rangé dans un **dossier de sujet** (Jarvis,
Université, Stratégie…). Copie lisible : `rapports\universite\memoire\` (un dossier par sujet + `INDEX.md`).
L'**Archiviste** (agent 16) retrouve les blocs : bouton « Mémoire » du bureau, « archiviste, … » à Jarvis,
« rappelle-moi… » au directeur, ou `python -m universite.memoire cherche "…"`. Les secrets sont masqués ; le
contenu des fichiers lus par Claude n'est jamais copié. Pour ajouter le résumé d'une session faite ailleurs :
déposer un fichier `.md` dans `rapports\universite\memoire\a_ranger\` (première ligne possible : `dossier: Jarvis`).

## Bibliothèque
Bouton **Bibliothèque** : le secrétaire lit STRATEGIE.md (sans le modifier) et te propose chaque règle mot pour mot,
avec sa ligne d'origine. Tu valides, corriges ou rejettes ; chaque version est gardée. Une case permet de chercher.

## Données
Bouton **Données** : « Lire le dossier TradingView » importe tous les exports déposés dans
`donnees_tradingview` (et les exports MGC des Téléchargements), une seule fois chacun ; ou import d'un fichier CSV exporté de TradingView, des fichiers de l'indicateur NinjaTrader
(temps réel), ou de Yahoo (différé, signalé comme tel). Aucune donnée n'est jamais inventée.

## Garde-fous
- À un instant donné, seules les bougies **fermées** sont lues (pas de look-ahead) ; c'est testé automatiquement.
- L'IA locale (LM Studio) écrit au plus un commentaire pédagogique **sans aucun chiffre** ; sinon il est refusé.
- Missions : délai maximal, nouveaux essais après une panne passagère, reprise après un redémarrage du PC.
- Boucles : nombre maximal d'itérations, pause automatique après 3 erreurs de suite.

## Où sont les fichiers
- Base de l'université : `rapports\universite\universite.sqlite` (jamais envoyée sur GitHub).
- Journal technique : `rapports\universite\universite.log`.
- Réglages : `rapports\universite\reglages-universite.json` (modifiables depuis le bouton Réglages).
