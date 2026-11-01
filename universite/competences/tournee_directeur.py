# -*- coding: utf-8 -*-
"""
Agent 14 — la tournée du directeur (31/10) : l'emploi du temps des agents.

Avant, les agents ne travaillaient que si Jabran leur confiait une mission : en huit jours, deux vraies analyses.
Une boucle lance cette tournée toutes les 15 minutes ; le directeur regarde ce qui est en retard et le confie à
l'agent qui sait le faire (de vraies missions, avec de vrais messages, visibles dans le bureau) :
  - données : bougies Yahoo rafraîchies (différées, signalées comme telles) quand le marché est ouvert ;
  - analyse technique complète (SMC, Fibonacci, Ichimoku, VWAP / EMA 200, flux) toutes les heures, marché ouvert ;
  - calendrier des annonces toutes les 6 heures, discours de la Fed une fois par jour ;
  - réactions du gold aux annonces une fois par jour ;
  - synthèse du directeur chaque jour à partir de 15 h (avant la séance de New York) ;
  - replay de la stratégie V1 une fois par semaine ;
  - mentor (31/10) : cours du jour (quelques agents toutes les 8 h, donc chacun chaque jour), retour sur les
    erreurs une fois par jour ; réunion de débrief à 21h30 (heure de Paris) chaque jour de marché.
Marché fermé (week-end, pause) : pas d'analyse technique (les mêmes bougies donneraient le même résultat).
Une tâche déjà dans la file n'est jamais relancée. Recherche et simulation seulement : aucun ordre.
"""

import datetime as dt
import time
from zoneinfo import ZoneInfo

from .. import agents, config, donnees
from . import reunion_debrief

TYPE = "tournee_directeur"
AGENT = 14
TITRE = "Tournée du directeur (emploi du temps des agents)"
PARAMS = {}
INTERNE = True                       # lancée par la boucle, pas demandée à la main
PARIS = ZoneInfo("Europe/Paris")
INTERVALLE_S = 15 * 60
HEURE = 3600
ANALYSES = ["analyse_smc", "analyse_fibo", "analyse_ichimoku", "analyse_vwap_ema", "analyse_flux"]
# type -> (âge maximal du dernier travail en secondes, besoin de bougies, marché ouvert obligatoire)
PLANNING = {
    "calendrier_macro": (6 * HEURE, False, False),
    "discours_fed": (24 * HEURE, False, False),
    "reaction_annonces": (24 * HEURE, True, False),
    "replay_strategie_v1": (7 * 24 * HEURE, True, False),
    "cours_du_jour": (4 * HEURE, False, False),     # 3 élèves par cours (01/11) : chaque agent garde un cours par jour
    "retour_erreurs": (24 * HEURE, False, False),
    **{t: (HEURE, True, True) for t in ANALYSES},
}
HEURE_SYNTHESE = 15
maintenant = time.time               # remplacé dans les tests


def seance(instant):
    """« ouverte », « pause », « fermée » ou « spéciale » (calendrier CME de la Salle)."""
    config.salle_importable()
    from mgc import calendrier_cme

    return calendrier_cme.etat_seance(dt.datetime.fromtimestamp(instant, dt.UTC))["etat"]


def rafraichir_yahoo(base):
    """Remplacé dans les tests. Sur le PC : nouvelles bougies Yahoo du contrat actif, dans le même jeu."""
    config.salle_importable()
    from mgc import config as cfg_salle
    from mgc.contrats import ContractManager

    contrat = ContractManager(cfg_salle.charger()).etat(dt.datetime.now(dt.UTC))["contrat"]
    return donnees.importer_yahoo(base, contrat)


def _dernier(base, genre):
    """Heure du dernier travail de ce type (en file ou en cours = maintenant). Une erreur compte aussi : on ne relance
    pas toutes les 15 minutes une tâche qui échoue, on attend la période normale."""
    r = base.un("SELECT MAX(CASE WHEN statut IN ('en_attente','en_cours') THEN ? ELSE COALESCE(fin, cree) END) AS t"
                " FROM missions WHERE type=? AND statut IN ('en_attente','en_cours','terminee','erreur')", (1e18, genre))
    return (r or {}).get("t") or 0


def _jeu(base):
    """Le jeu de bougies le plus récent qui contient vraiment des bougies."""
    for j in donnees.liste_jeux(base):
        if j["unites"]:
            return j
    return None


def jour_de_reunion(jour, etat):
    """Réunion du soir : du lundi au vendredi, sauf si le marché est fermé (jour férié CME)."""
    return jour.weekday() < 5 and etat != "fermée"


def executer(ctx):
    from . import TYPES

    t = maintenant()
    etat = seance(t)
    ouvert = etat in ("ouverte", "spéciale")
    ctx.etape("documentaliste", f"Regarde l'emploi du temps (marché {etat})")
    rafraichi = None
    if ouvert:
        ctx.etape("chercheur", "Rafraîchit les bougies (Yahoo, différé)")
        try:
            rafraichi = rafraichir_yahoo(ctx.base)
        except Exception as e:  # noqa: BLE001 : sans Internet, on travaille avec les bougies déjà gardées
            ctx.journal(f"Bougies Yahoo non rafraîchies : {e}", "alerte")
    jeu = _jeu(ctx.base)
    confiees, sautees = [], []
    for genre, (age_max, besoin_jeu, marche) in PLANNING.items():
        if t - _dernier(ctx.base, genre) < age_max:
            continue
        if marche and not ouvert:
            sautees.append(f"{genre} (marché {etat})")
            continue
        if besoin_jeu and not jeu:
            sautees.append(f"{genre} (aucune bougie)")
            continue
        comp = TYPES[genre]
        params = {"jeu": jeu["id"]} if besoin_jeu else {}
        m = ctx.demander(comp.AGENT, genre, comp.TITRE, params, "Emploi du temps de l'université (tournée du directeur).")
        confiees.append({"mission": m, "type": genre, "agent": comp.AGENT})
    jour = dt.datetime.fromtimestamp(t, PARIS)
    if jour.hour >= HEURE_SYNTHESE:
        debut_jour = jour.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        if _dernier(ctx.base, "synthese_directeur") < debut_jour:
            m = ctx.base.nouvelle_mission(agents.DIRECTEUR, "synthese_directeur", "Synthèse du directeur", {"heures": 24},
                                          "Synthèse du jour (emploi du temps).", priorite=5, demandeur="tournée",
                                          parent=ctx.id, tentatives_max=ctx.moteur.reglages["tentatives_max"])
            confiees.append({"mission": m, "type": "synthese_directeur", "agent": agents.DIRECTEUR})
    if jour_de_reunion(jour, etat) and (jour.hour, jour.minute) >= (reunion_debrief.HEURE, reunion_debrief.MINUTE) \
            and not ctx.base.un("SELECT id FROM reunions WHERE jour=?", (jour.date().isoformat(),)) \
            and not ctx.base.un("SELECT id FROM missions WHERE type=? AND statut IN ('en_attente','en_cours')",
                                (reunion_debrief.TYPE,)):
        m = ctx.base.nouvelle_mission(agents.DIRECTEUR, reunion_debrief.TYPE, reunion_debrief.TITRE, {},
                                      "Débrief de la journée (21h30, 30 minutes).", priorite=3, demandeur="tournée",
                                      parent=ctx.id, tentatives_max=ctx.moteur.reglages["tentatives_max"])
        confiees.append({"mission": m, "type": reunion_debrief.TYPE, "agent": agents.DIRECTEUR})
    ctx.etape("connaissances", f"{len(confiees)} tâche(s) confiée(s)", "verification")
    if confiees:
        noms = sorted({agents.agent(c["agent"])["court"] for c in confiees})
        ctx.journal(f"Tournée : {len(confiees)} tâche(s) confiée(s) ({', '.join(noms)}).")
    return {"seance": etat, "confiees": confiees, "sautees": sautees,
            "bougies_ajoutees": (rafraichi or {}).get("ajoutees")}


def assurer_boucle(moteur):
    """La tournée est créée une seule fois (si Jabran la met en pause depuis le bouton Boucles, elle le reste)."""
    if moteur.base.un("SELECT id FROM boucles WHERE genre=?", (TYPE,)):
        return None
    b = moteur.nouvelle_boucle("Directeur : emploi du temps des agents", AGENT, TYPE,
                               "Confier aux agents le travail en retard (données, analyses, macro, synthèse, replay).",
                               {}, INTERVALLE_S, 1_000_000)
    moteur.base.ecrire("UPDATE boucles SET prochaine=? WHERE id=?", (time.time() + 90, b))
    return b
