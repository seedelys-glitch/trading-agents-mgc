# -*- coding: utf-8 -*-
"""
Université MGC : le bureau de recherche des 14 agents spécialisés Micro Gold (MGC).

Programme séparé de la Salle des marchés et de Jarvis (python -m universite, port 8780).
Il réutilise les calculs de la Salle (calculs.py) et le paquet mgc, sans les modifier.

Recherche et simulation SEULEMENT : aucun courtier, aucun ordre. Aucun module de ce dossier n'importe
ordres.py, discipline.py ni une bibliothèque d'exécution (vérifié par tests/test_aucun_ordre.py).

  config.py      réglages (port, concurrence, délais, budgets IA) et emplacements
  base.py        base SQLite persistante, migrations versionnées (missions, étapes, documents, messages, jeux)
  agents.py      les 14 agents (le directeur est le n° 14) et leurs 4 fonctions de soutien (56 rôles)
  moteur.py      file de missions, ouvriers, délais, reprises, reprise après arrêt, boucles
  donnees.py     jeux de bougies (CSV TradingView / NinjaTrader, Yahoo) et fenêtre de replay sans look-ahead
  ia.py          IA locale LM Studio (commentaires seulement, jamais de chiffres), budget d'appels
  competences/   ce que les agents savent RÉELLEMENT faire
  serveur.py     API locale + bureau virtuel (ui/)
"""
