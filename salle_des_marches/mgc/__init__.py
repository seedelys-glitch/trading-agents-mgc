# -*- coding: utf-8 -*-
"""
Socle de l'analyste Micro Gold (MGC, CME Globex).

Tout ici est déterministe (aucune IA) et testé :
  config.py         réglages (capital, risque, frais, fenêtre...) + fichier config_mgc.json facultatif
  instrument.py     spécifications du contrat, conversions points / ticks / dollars, codes de mois
  calendrier_cme.py jours fériés, jours ouvrés, état de la séance Globex, fenêtre de trading de Paris
  contrats.py       contrat actif et suivant, dernier jour de négociation, restriction de rollover
  annonces.py       classement des annonces (réunion FOMC, discours du président de la Fed...)
  risque.py         moteur de risque : nombre de contrats, risque net, ratio, break-even, vetos
  vetos.py          vetos de contexte (séance, fenêtre, rollover, pause, données différées)

Analyste uniquement : aucun module ne passe, ne modifie ni n'annule d'ordre.
"""
