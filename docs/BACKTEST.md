# Backtest de la stratégie V1 (1H / 12H)

Généré le 18/10/2026 par `salle_des_marches/lancer_backtest.py` en 97 s. **Aucune promesse de rentabilité** : c'est un rejeu prudent de règles fixées à l'avance, pas une prévision.

- Données : Yahoo GC=F (contrat continu, différé), 13745 bougies H1, du 2024-05-26 au 2026-10-16.
- Découpage chronologique : première partie jusqu'au 2025-11-01 (60 %), puis hors échantillon (40 %). Aucun paramètre n'a été réglé sur ces résultats : les règles viennent de STRATEGIE.md et des réglages du 17/10.
- Signaux refusés : 1 par le moteur de risque, 44 hors fenêtre 15h30-20h ou séance fermée, 9 près du rollover.
- Sorties : stop (6), sortie forcée (fin de séance) (2), TP1 (1), break-even (1).

## Résultats (R = risque initial jusqu'au stop)

| | trades | réussite | Wilson 95 % | espérance | profit factor | drawdown max | total |
|---|---|---|---|---|---|---|---|
| Tout, brut | 9 | 33% | 12%–65% | -0.284 R | 0.57 | 3.45 R | -1104.25 $ |
| Tout, net (frais + glissement) | 9 | 33% | 12%–65% | -0.346 R | 0.52 | 3.77 R | -1345.75 $ |
| Première partie, net | 3 | 33% | 6%–79% | -0.13 R | 0.82 | 1.17 R | -163.5 $ |
| Hors échantillon, net | 6 | 33% | 10%–70% | -0.454 R | 0.36 | 2.72 R | -1182.25 $ |

Conclusion statistique : Échantillon trop petit (9 < 30) : aucune conclusion possible.

## Walk-forward (par trimestre, net)

| | trades | réussite | Wilson 95 % | espérance | profit factor | drawdown max | total |
|---|---|---|---|---|---|---|---|
| 2024Q3 | 1 | 0% | 0%–79% | -1.167 R | 0 | 1.17 R | -490 $ |
| 2024Q4 | 1 | 100% | 21%–100% | 1.83 R | – | 0 R | 820 $ |
| 2025Q4 | 2 | 0% | 0%–66% | -1.056 R | 0 | 2.11 R | -977.5 $ |
| 2026Q1 | 3 | 67% | 21%–94% | 0.166 R | 1.49 | 1.02 R | 259.75 $ |
| 2026Q2 | 1 | 0% | 0%–79% | -1.061 R | 0 | 1.06 R | -484 $ |
| 2026Q4 | 1 | 0% | 0%–79% | -1.097 R | 0 | 1.1 R | -474 $ |

## Par setup (net)

| | trades | réussite | Wilson 95 % | espérance | profit factor | drawdown max | total |
|---|---|---|---|---|---|---|---|
| achat 0.618 | 5 | 20% | 4%–62% | -0.685 R | 0.21 | 3.43 R | -1526 $ |
| achat 0.705 | 1 | 0% | 0%–79% | -1.097 R | 0 | 1.1 R | -474 $ |
| vente 0.618 | 2 | 100% | 34%–100% | 1.215 R | – | 0 R | 1059.25 $ |
| vente 0.705 | 1 | 0% | 0%–79% | -1.018 R | 0 | 1.02 R | -405 $ |

## Biais contrôlés et limites

- Pas de regard vers le futur : à chaque bougie, seules les bougies passées sont lues ; entrée à l'ouverture suivante ; un test automatique vérifie que des bougies futures ne changent aucune décision passée.
- Prudence : stop compté avant l'objectif dans une même bougie ; break-even effectif à la bougie suivante.
- Pas de sélection : tous les signaux sont pris ; une impulsion ne sert qu'une fois.
- **Non modélisé** : annonces (FOMC, NFP…) faute de calendrier historique ; sauts de rollover du contrat continu ; sorties partielles en fractions de contrat ; frais et glissement estimés (1,50 $ + 2 ticks par contrat).
- Sortie forcée à 15h00 (Chicago), avant la limite Topstep de 15h10 (à vérifier dans tes règles Topstep).
- Échantillon : en dessous de 30 trades, aucune conclusion n'est possible.
