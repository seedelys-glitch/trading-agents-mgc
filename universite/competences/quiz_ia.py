"""
Quiz de l'IA locale sur le cours d'un agent (31/10) : l'IA qui rédige les commentaires doit connaître la spécialité.
Questions à choix, une seule lettre attendue, corrigées par comparaison (pas par une autre IA).
Sans LM Studio joignable (ou budget du jour atteint), le quiz n'a pas lieu et c'est noté : aucune note inventée.
"""

from .. import entrainement
from ..agents import agent as fiche_agent

TYPE = "quiz_ia"
AGENT = 9
TITRE = "Quiz de l'IA sur le cours d'un agent"
PARAMS = {"agent": "numéro de l'agent dont on interroge le cours"}
INTERNE = True


def executer(ctx):
    eleve = int(ctx.params.get("agent") or ctx.agent)
    nom = (fiche_agent(eleve) or {}).get("nom", eleve)
    if not entrainement.questions_quiz(eleve):
        return {"agent": eleve, "questions": 0}
    ctx.etape("professeur", f"Pose à l'IA locale les questions du cours de {nom}")
    reponses = entrainement.poser_quiz(ctx.ia, eleve, ctx.id)
    if not reponses:
        ctx.journal(f"Quiz de {nom} non passé : IA locale indisponible (LM Studio fermé ou budget du jour atteint).")
        return {"agent": eleve, "passe": False}
    ctx.etape("connaissances", "Corrige et note", "verification")
    justes = sum(r["reussi"] for r in reponses)
    note = round(20 * justes / len(reponses), 1)
    entrainement.enregistrer(ctx.base, eleve, "quiz_ia", "cours", note, {"reponses": reponses},
                             entrainement.graine_du_jour(), ctx.id)
    for r in reponses:
        if not r["reussi"]:
            entrainement.noter_lecon(ctx.base, eleve, entrainement.MISSION_AGENT.get(eleve, ""),
                                     f"L'IA s'est trompée au quiz : {r['question']}",
                                     f"Réponse {r['obtenu']} au lieu de {r['attendu']}.",
                                     f"Bonne réponse : {r['bonne_reponse']}. Relire le cours « {r['titre']} ».")
    lignes = [f"Quiz de l'IA locale sur le cours de {nom} : {justes}/{len(reponses)} = {note:g}/20.", ""]
    lignes += [f"   [{'juste' if r['reussi'] else 'FAUX'}] {r['question']} -> {r['obtenu']} (bonne : {r['attendu']})"
               for r in reponses]
    doc = ctx.document("examen", f"Quiz de l'IA — {nom} — {note:g}/20", "\n".join(lignes),
                       donnees={"agent": eleve, "reponses": reponses}, role="connaissances", statut="verifie")
    return {"agent": eleve, "passe": True, "note": note, "document": doc}
