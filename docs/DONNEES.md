# Données de l'analyste MGC

La fiabilité des données passe avant l'avis des agents. Code : `salle_des_marches/mgc/sources.py`,
`qualite.py`, `source_ninja.py` ; indicateur : `ninjatrader/ExportBougiesMGC.cs`.

## Sources, dans l'ordre

| Source | Temps réel | Contrat | Statut maximal |
|---|---|---|---|
| NinjaTrader 8 (indicateur `ExportBougiesMGC`, données CME du compte) | oui | réel (ex. `MGC 12-26` → `MGCZ26`) | configuration exploitable possible |
| Yahoo Finance (`MGCZ26.CMX`) | **non, différé** | réel | « ATTENDRE » |

Le contrat actif vient de `contrats.py` (bascule estimée N jours ouvrés avant le premier jour d'avis).
NinjaTrader n'est utilisé que s'il donne signe de vie (`battement.json` de moins de 120 s), sur le bon
contrat et avec des bougies 1 min ; sinon repli automatique sur Yahoo, avec le motif.

## Contrôles (chaque unité de temps)

1. horodatage avec fuseau (tout est converti en UTC ; index = début de bougie) ;
2. doublons retirés ; bougie en cours retirée (on n'analyse que des bougies fermées) ;
3. prix possibles (haut ≥ corps ≥ bas, > 0) et sur l'échelon de 0,10 ;
4. trous **en séance ouverte** seulement (week-end, pause 16h-17h Chicago et jours fériés ne comptent pas) :
   signalés, et données invalides au-delà de 15 min d'affilée ;
5. fraîcheur, marché ouvert : dernière bougie fermée en retard de plus de 2 min → « périmée » ;
6. contrat de la source = contrat actif ;
7. NinjaTrader en direct : la dernière bougie 1 min commune est recoupée avec Yahoo ;
   écart > 2 points → données « invalides » (on ne choisit pas une source au hasard).

H4 et H12 sont reconstruits à partir du H1, calés sur l'ouverture CME (17h à Chicago). Le D1 vient de
NinjaTrader s'il a au moins 210 jours, sinon de Yahoo (journalier, sans enjeu de minute).

## Constats réels (17-18/10/2026)

- Yahoo cote bien les contrats réels : `MGCV26`, `MGCZ26`, `MGCG27`, `MGCJ27`, `MGCM27`, `MGCQ27`,
  `MGCV27`, `MGCZ27` (mois pairs seulement). Volume sur 10 jours : `MGCZ26` 2,49 M, `MGCG27` 46 000.
- Yahoo stocke ses prix en précision réduite (4181,1 → 4181,10009765625) : arrondis au centime.
- Chargement Yahoo complet : 1,3 à 4,2 s. Retard de Yahoo **non mesuré** (marché fermé le week-end).
- Order flow : toujours ESTIMÉ à partir des bougies (pas d'export ATAS pour l'instant).

## Installer l'indicateur NinjaTrader (une seule fois)

1. Copier `ninjatrader\ExportBougiesMGC.cs` dans `Documents\NinjaTrader 8\bin\Custom\Indicators\`.
2. NinjaTrader → New → NinjaScript Editor → touche **F5** (compilation). Aucune erreur attendue.
3. Ouvrir un graphique **MGC, 1 minute**, « Days to load » = 90, ajouter l'indicateur `ExportBougiesMGC`.
4. Un seul graphique avec l'indicateur. Les fichiers apparaissent dans `Documents\TradingAgents\donnees_ninja\`.
