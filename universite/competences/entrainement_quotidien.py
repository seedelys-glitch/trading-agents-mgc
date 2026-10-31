"""
L'entraînement quotidien (31/10) : une boucle (créée une fois, toutes les 24 h) où le secrétaire-auditeur fait
passer à chaque agent son examen de spécialité, lance les travaux pratiques en replay des 5 lectures techniques
(s'il y a des bougies) et le quiz de l'IA (si LM Studio répond). Ce sont de vraies missions, visibles dans le bureau.
"""

import time

from .. import entrainement
from ..agents import AGENTS

TYPE = "entrainement_quotidien"
AGENT = 9
TITRE = "Entraînement quotidien des agents (examens, replay, quiz)"
PARAMS = {}
INTERNE = True
INTERVALLE_S = 24 * 3600


def _jeu(base):
    from .tournee_directeur import _jeu as jeu_recent

    return jeu_recent(base)


def executer(ctx):
    ctx.etape("documentaliste", "Prépare la journée d'entraînement")
    confiees = []
    for a in AGENTS:
        if any(s.get("examen") for s in entrainement.PROGRAMME.get(a["n"], [])):
            m = ctx.demander(a["n"], "examen_ecole", f"Examen de spécialité de {a['nom']}", {"agent": a["n"]},
                             "Entraînement quotidien : prouver que le calcul suit le cours.")
            confiees.append(m)
    jeu = _jeu(ctx.base)
    if jeu:
        for n in entrainement.LECTURES:
            m = ctx.demander(n, "travaux_pratiques", "Travaux pratiques en replay", {"agent": n, "jeu": jeu["id"]},
                             "Entraînement quotidien : la lecture a-t-elle aidé dans le passé ?")
            confiees.append(m)
    else:
        ctx.journal("Pas de bougies : travaux pratiques en replay remis à demain.", "alerte")
    quiz = 0
    if ctx.ia and ctx.ia.disponible():
        for a in AGENTS:
            if entrainement.questions_quiz(a["n"]):
                confiees.append(ctx.demander(9, "quiz_ia", f"Quiz de l'IA sur le cours de {a['nom']}",
                                             {"agent": a["n"]}, "Entraînement quotidien : l'IA connaît-elle le cours ?"))
                quiz += 1
    ctx.etape("connaissances", f"{len(confiees)} épreuve(s) lancée(s)", "verification")
    return {"epreuves": len(confiees), "replay": bool(jeu), "quiz": quiz}


def assurer_boucle(moteur):
    """Créée une seule fois ; Jabran peut la mettre en pause depuis le bouton Boucles."""
    if moteur.base.un("SELECT id FROM boucles WHERE genre=?", (TYPE,)):
        return None
    b = moteur.nouvelle_boucle("Auditeur : entraînement quotidien des agents", AGENT, TYPE,
                               "Examens de spécialité, travaux pratiques en replay et quiz de l'IA, chaque jour.",
                               {}, INTERVALLE_S, 1_000_000)
    moteur.base.ecrire("UPDATE boucles SET prochaine=? WHERE id=?", (time.time() + 600, b))
    return b
