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
| 6. VWAP & EMA 200 | VWAP de séance (depuis 17 h à Chicago) avec bandes, EMA 200 en 5 min, 15 min et 1 h, à un instant donné (direct ou replay) |
| 9. Secrétaire / auditeur | Recalcule tous les chiffres de l'agent 6 de son côté ; le document passe « vérifié » ou « rejeté » |
| 13. Chercheur quantitatif | Contrôle un jeu de bougies : nombre, période, trous, coupures |
| 14. Directeur | Reçoit les demandes, les confie au bon agent, fait la synthèse de ce qui est vérifié |

Les 10 autres agents sont affichés **« en construction »** : ils ne font rien et le bureau ne fait pas semblant.

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
