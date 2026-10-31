# -*- coding: utf-8 -*-
"""
Agent 14 (directeur) — la réunion du soir (31/10, demandée par Jabran) : chaque jour de marché à 21h30 (heure de
Paris), 30 minutes de débrief de la journée dans la salle de réunion.

Déroulé (tout vient de la base, rien n'est inventé) :
  1. le mentor relit les erreurs du jour (leçons à jour) ;
  2. chaque agent fait son tour de table, avec sa personnalité : ce qu'il a vraiment fait aujourd'hui (missions,
     documents vérifiés ou rejetés, erreurs), son humeur, la leçon qu'il retient, son cours du jour, sa note
     d'entraînement si le programme d'entraînement est installé ;
  3. le directeur conclut : erreurs répétées, priorités de demain.
Le compte rendu est rédigé par l'IA (Groq via Jarvis, sinon LM Studio) sous forme de dialogue, à partir des seuls
faits et dans la charte ; sans IA, le dialogue est écrit à partir des faits. Pendant 30 minutes, le bureau 3D
montre les agents réunis autour de la table (table reunions : début et fin).
"""

import datetime as dt
import time
from zoneinfo import ZoneInfo

from .. import agents, personnalites
from . import retour_erreurs

TYPE = "reunion_debrief"
AGENT = 14
TITRE = "Réunion du soir : débrief de la journée"
PARAMS = {}
INTERNE = True
PARIS = ZoneInfo("Europe/Paris")
HEURE, MINUTE, DUREE_S = 21, 30, 30 * 60


def jour_de(t):
    return dt.datetime.fromtimestamp(t, PARIS).date().isoformat()


def en_cours(base, maintenant=None):
    """La réunion en cours (ou None) : sert au bureau 3D pour réunir les agents autour de la table."""
    maintenant = maintenant or time.time()
    return base.un("SELECT * FROM reunions WHERE debut<=? AND fin>? ORDER BY id DESC LIMIT 1", (maintenant, maintenant))


def _bulletin(n, depuis, base):
    try:
        from .. import entrainement

        return entrainement.bulletin(base, n, depuis)
    except (ImportError, AttributeError, TypeError):
        return None


def tour_de_table(base, debut_jour):
    """Une entrée par agent qui travaille : faits du jour + personnalité."""
    from . import TYPES

    branches = {m.AGENT for m in TYPES.values()}
    tour = []
    for a in agents.AGENTS:
        n = a["n"]
        if n not in branches:
            continue
        personnalites.evoluer(base, n)
        f = personnalites.fiche(base, n)
        j = f["aujourdhui"] or {}
        lecon = base.un("SELECT quoi, lecon, statut, fois FROM lecons WHERE agent=? AND maj>=? ORDER BY fois DESC, maj DESC"
                        " LIMIT 1", (n, debut_jour))
        cours = base.un("SELECT sujet FROM cours WHERE agent=? AND cree>=? ORDER BY id DESC LIMIT 1", (n, debut_jour))
        tour.append({"agent": n, "prenom": f["prenom"], "court": a["court"], "tic": f["tic"], "humeur": f["humeur"],
                     "niveau": f["niveau"], "missions": j.get("missions", 0), "verifies": j.get("verifies", 0),
                     "rejetes": j.get("rejetes", 0), "erreurs": j.get("erreurs", 0), "lecon": lecon,
                     "cours": cours["sujet"] if cours else None, "bulletin": _bulletin(n, debut_jour, base)})
    return tour


def ligne_faits(t):
    morceaux = [f"{t['missions']} mission(s) terminée(s)"]
    if t["verifies"] or t["rejetes"]:
        morceaux.append(f"{t['verifies']} document(s) vérifié(s), {t['rejetes']} rejeté(s)")
    if t["erreurs"]:
        morceaux.append(f"{t['erreurs']} erreur(s)")
    texte = f"{t['prenom']} ({t['court']}, niveau {t['niveau']}) : " + ", ".join(morceaux) + f". Humeur : {t['humeur']}."
    if t["lecon"]:
        texte += f" Leçon retenue : {t['lecon']['lecon']}"
    if t["cours"]:
        texte += f" Cours du jour : {t['cours']}."
    b = t.get("bulletin")
    if isinstance(b, dict) and b.get("moyenne") is not None:
        texte += f" Entraînement : moyenne {b['moyenne']}."
    return texte


def executer(ctx):
    maintenant = time.time()
    jour = jour_de(maintenant)
    if ctx.base.un("SELECT id FROM reunions WHERE jour=?", (jour,)):
        return {"jour": jour, "deja_faite": True}
    debut_jour = dt.datetime.fromtimestamp(maintenant, PARIS).replace(hour=0, minute=0, second=0,
                                                                         microsecond=0).timestamp()
    reunion = ctx.base.ecrire("INSERT INTO reunions(jour, debut, fin, mission, cree) VALUES (?,?,?,?,?)",
                              (jour, maintenant, maintenant + DUREE_S, ctx.id, maintenant))
    ctx.etape("documentaliste", "Ouvre la réunion du soir : tout le monde en salle de réunion", "reunion")
    for a in agents.AGENTS:
        if a["n"] != AGENT:
            ctx.message(a["n"], "reunion", "Réunion de débrief : salle de réunion, 30 minutes.")
    ctx.etape("chercheur", "Le mentor relit les erreurs du jour", "reunion")
    lecons = retour_erreurs.analyser(ctx.base, heures=max(1.0, (maintenant - debut_jour) / 3600))
    ctx.etape("chercheur", "Tour de table : chaque agent raconte sa journée", "reunion")
    tour = tour_de_table(ctx.base, debut_jour)
    repetees = ctx.base.lire("SELECT quoi, cause, fois, equipe FROM lecons WHERE statut='repetee' AND maj>=?"
                             " ORDER BY fois DESC LIMIT 5", (debut_jour,))
    a_suivre = sorted([t for t in tour if t["erreurs"] or t["rejetes"]], key=lambda t: -(t["erreurs"] + t["rejetes"]))
    faits = [f"Réunion du {jour}, 21h30, durée 30 minutes. Participants : {len(tour)} agents.", ""]
    faits += [ligne_faits(t) for t in tour]
    faits += ["", f"Leçons écrites ou revues aujourd'hui : {len(lecons)}."]
    faits += [f"Erreur répétée ({r['fois']} fois, {r['equipe']}) : {r['quoi']} ; cause : {r['cause']}." for r in repetees]
    if a_suivre:
        faits.append("À suivre demain : " + ", ".join(f"{t['prenom']} ({t['court']})" for t in a_suivre[:3]) + ".")
    else:
        faits.append("Aucune erreur aujourd'hui : on garde le rythme.")
    faits_texte = "\n".join(faits)

    ctx.etape("professeur", "Rédige le compte rendu (dialogue)", "reunion")
    presentations = "\n".join(personnalites.presentation(t["agent"]) for t in tour)
    consigne = ("Tu écris le compte rendu de la réunion du soir de l'université MGC, sous forme de dialogue court. "
                "Arthur, le directeur, ouvre la réunion ; chaque agent parle à son tour, une ou deux phrases, avec SA "
                "personnalité (voir les présentations) et uniquement à partir des faits donnés ; Margaux, le mentor, "
                "rappelle les leçons ; Arthur conclut avec les priorités de demain. Respect entre tous. N'ajoute aucun "
                "chiffre absent des faits.\n\nPrésentations :\n" + presentations)
    r = ctx.ia.rediger(consigne, faits_texte, mission=ctx.id, agent=AGENT, role="professeur", max_tokens=1500)
    if r:
        corps = r["texte"] + "\n\n---\nFaits utilisés :\n" + faits_texte
    else:
        dialogue = ["Arthur (directeur) : Bonsoir à tous, on fait le point de la journée. Qu'est-ce qu'on retient ?"]
        dialogue += [f"{ligne_faits(t)} « {t['tic']} »" for t in tour]
        dialogue.append("Margaux (mentor) : " + (f"{len(lecons)} leçon(s) écrite(s) ou revue(s) aujourd'hui. Chaque "
                                                 "erreur est un cours gratuit." if lecons else
                                                 "Pas d'erreur aujourd'hui, bravo. On continue d'apprendre demain."))
        dialogue.append("Arthur (directeur) : " + (faits[-1] if faits else "Merci à tous."))
        corps = "\n".join(dialogue) + "\n\n---\nFaits utilisés :\n" + faits_texte
    ctx.etape("connaissances", "Range le compte rendu", "verification")
    doc = ctx.document("reunion", f"Réunion du soir du {jour}", corps,
                       donnees={"jour": jour, "tour": [{k: v for k, v in t.items() if k != "bulletin"} for t in tour],
                                "lecons": [l["id"] for l in lecons], "ia": r["ia"] if r else None},
                       sources=[{"lecon": l["id"]} for l in lecons], role="professeur",
                       statut="brouillon" if r else "verifie")   # texte IA : brouillon, faits joints
    ctx.base.ecrire("UPDATE reunions SET document=? WHERE id=?", (doc, reunion))
    return {"jour": jour, "reunion": reunion, "document": doc, "participants": len(tour), "lecons": len(lecons),
            "ia": r["ia"] if r else None}
