# -*- coding: utf-8 -*-
"""
Vetos de contexte, vérifiés AVANT tout appel à une IA (si l'un tombe, aucune IA n'est appelée).

Les vetos liés au desk (accord des spécialistes, zone Fibo avec FVG, prix cités) restent dans bureau.py ;
ceux du risque sont dans risque.py.
"""

from . import annonces as ann
from . import calendrier_cme as cal


def niveau1(instant, config, etat_contrat, liste_annonces, pause, statut_donnees, motifs_donnees=(), calendrier_ok=True):
    """Vetos vérifiés avant toute IA, en deux familles :

    bloquants   -> « ANALYSE BLOQUÉE » tout de suite, AUCUN appel IA (pause, annonces, données inutilisables...) ;
    informatifs -> l'analyse se fait, mais le statut ne dépasse pas « ATTENDRE » (différé, hors fenêtre, séance
                   fermée, rollover).
    """
    bloquants, informatifs = [], []
    if pause:
        bloquants.append("Pause d'urgence active (/pause) : aucune configuration exploitable.")
    if etat_contrat is None:
        bloquants.append("Contrat MGC non identifié.")
    if statut_donnees in ("invalide", "perimee"):
        bloquants.append("Données " + ("inutilisables" if statut_donnees == "invalide" else "périmées") + " : "
                         + (" ; ".join(motifs_donnees[:3]) or "voir le détail des contrôles") + ".")
    if not calendrier_ok:
        bloquants.append("Calendrier des annonces indisponible : impossible de vérifier FOMC et annonces fortes.")
    bloquants += ann.blocages(instant, liste_annonces, config)
    seance = cal.etat_seance(instant)
    if seance["etat"] != "ouverte":
        informatifs.append(seance["motif"])
    if not cal.dans_fenetre(instant, config["fenetre_paris"]):
        debut, fin = config["fenetre_paris"]
        informatifs.append(f"Hors de ta fenêtre de trading ({debut.replace(':', 'h')}-{fin.replace(':', 'h')}, heure de Paris).")
    if etat_contrat and etat_contrat.get("restriction_rollover"):
        informatifs.append(etat_contrat["motif_restriction"])
    if statut_donnees == "differee":
        informatifs.append("Données différées (Yahoo) : au mieux « ATTENDRE », avec les niveaux à surveiller.")
    return {"bloquants": bloquants, "informatifs": informatifs}


def contexte(instant, config, etat_contrat=None, liste_annonces=(), pause=False, donnees_temps_reel=False):
    """Liste des motifs qui interdisent toute configuration exploitable à cet instant (vide = rien ne bloque)."""
    motifs = []
    if pause:
        motifs.append("Pause d'urgence active (/pause) : aucune configuration exploitable.")
    seance = cal.etat_seance(instant)
    if seance["etat"] != "ouverte":
        motifs.append(seance["motif"])
    if not cal.dans_fenetre(instant, config["fenetre_paris"]):
        debut, fin = config["fenetre_paris"]
        motifs.append(f"Hors de ta fenêtre de trading ({debut.replace(':', 'h')}-{fin.replace(':', 'h')}, heure de Paris).")
    if etat_contrat is None:
        motifs.append("Contrat MGC non identifié.")
    elif etat_contrat.get("restriction_rollover"):
        motifs.append(etat_contrat["motif_restriction"])
    motifs += ann.blocages(instant, liste_annonces, config)
    if not donnees_temps_reel:
        motifs.append("Données différées : au mieux « ATTENDRE », avec les niveaux à surveiller.")
    return motifs
