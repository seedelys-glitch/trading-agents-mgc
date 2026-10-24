"""Veille du desk : agents qui surveillent le marché en continu et écrivent des événements (aucun ordre).

Agents : cascade (Weekly -> 12H -> 48 min -> 12 min), stratégie 1H/12H (observation), journal des setups
(photos envoyées par Jarvis) et analyse des actus pour le gold (textes envoyés par Jarvis).
Lancement : pythonw -m salle_des_marches.veille (serveur local 127.0.0.1:8791, un seul à la fois).
Jarvis lit GET /api/evenements et annonce ; il ne fait plus lui-même l'analyse (24/10/2026).
"""
