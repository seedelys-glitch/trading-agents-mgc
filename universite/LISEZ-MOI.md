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
| 8. Risques | Évalue une idée de trade (sens, entrée, stop, TP1) : contrats MGC, risque net avec frais, ratio, vetos. Calcul seulement, aucun ordre |
| 5. Macro | Télécharge le calendrier USD de la semaine (Forex Factory, gratuit), garde chaque annonce dans l'historique, liste les 48 h à venir et dit ce qui bloque maintenant (FOMC, discours de la Fed, annonce forte) ; prévient le gestionnaire des risques |
| 6. VWAP & EMA 200 | VWAP de séance (depuis 17 h à Chicago) avec bandes, EMA 200 en 5 min, 15 min et 1 h, à un instant donné (direct ou replay) |
| 9. Secrétaire / auditeur | Recalcule de son côté les chiffres de l'agent 6, recompte les replays, le risque, les blocages d'annonces et les réactions (calcul indépendant) ; pour SMC, Fibonacci et Ichimoku il contrôle que le calcul est reproductible sur les mêmes bougies, sans bougie future. Le document passe « vérifié » ou « rejeté » |
| 12. Réactions | Mesure comment le gold a vraiment bougé après chaque annonce gardée (+5, +15, +60 min, plus haut / plus bas de l'heure), sur un jeu de bougies 1 à 5 min ; moins de 20 cas = aucune conclusion |
| 13. Chercheur quantitatif | Contrôle un jeu de bougies (nombre, période, trous) et rejoue ta stratégie V1 (1H / 12H) : entraînement / validation / test, Monte-Carlo, résultats par régime ; moins de 30 trades = aucune conclusion |
| 14. Directeur | Reçoit les demandes, les confie au bon agent, fait la synthèse de ce qui est vérifié |

Les 4 autres agents (4, 7, 10, 11) sont affichés **« en construction »** : ils ne font rien et le bureau ne fait pas semblant.

Astuce : une boucle « Calendrier » toutes les 6 heures (bouton Boucles) remplit l'historique des annonces semaine après
semaine ; le site ne donne que la semaine en cours, l'historique commence donc le jour du premier lancement.

## Bibliothèque
Bouton **Bibliothèque** : le secrétaire lit STRATEGIE.md (sans le modifier) et te propose chaque règle mot pour mot,
avec sa ligne d'origine. Tu valides, corriges ou rejettes ; chaque version est gardée. Une case permet de chercher.

## Données
Bouton **Données** : import d'un fichier CSV exporté de TradingView, des fichiers de l'indicateur NinjaTrader
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
