"""
Examen « cas d'école » d'un agent (31/10) : l'agent répond avec son VRAI calcul sur des bougies fabriquées dont la
bonne réponse est connue par construction (voir entrainement.py). L'agent 9 (secrétaire-auditeur) corrige.

Note sur 20 par sujet, enregistrée dans la table examens. Une question ratée = le calcul ne suit pas le cours :
leçon écrite (relue avant les missions de ce type) et alerte au directeur, car c'est un défaut à corriger.
"""

from .. import entrainement
from ..agents import DIRECTEUR, agent as fiche_agent

TYPE = "examen_ecole"
AGENT = 9
TITRE = "Examen de spécialité (cas d'école)"
PARAMS = {"agent": "numéro de l'agent qui passe l'examen (par défaut celui de la mission)",
          "graine": "graine des exercices (par défaut : la date du jour)"}
INTERNE = True


def executer(ctx):
    eleve = int(ctx.params.get("agent") or ctx.agent)
    graine = int(ctx.params.get("graine") or entrainement.graine_du_jour())
    nom = (fiche_agent(eleve) or {}).get("nom", eleve)
    sujets = [s for s in entrainement.PROGRAMME.get(eleve, []) if s.get("examen")]
    if not sujets:
        return {"agent": eleve, "sujets": 0, "raison": "pas encore d'épreuve automatique pour cette spécialité"}
    ctx.etape("documentaliste", f"Relit le cours de {nom} ({len(sujets)} sujet(s) avec épreuve)")
    ctx.etape("chercheur", "Fabrique les exercices du jour et les fait résoudre par le vrai calcul de l'agent")
    resultats = entrainement.passer_examens(eleve, graine)
    ctx.etape("connaissances", "Corrige, note sur 20 et écrit les leçons des erreurs", "verification")
    lignes, rates = [f"Examen de {nom} (exercices du {graine}, différents chaque jour).", ""], []
    for r in resultats:
        entrainement.enregistrer(ctx.base, eleve, "cas_ecole", r["sujet"], r["note"],
                                 {"titre": r["titre"], "questions": r["questions"]}, graine, ctx.id)
        lignes.append(f"{r['titre']} : {r['note']:g}/20")
        for q in r["questions"]:
            marque = "juste" if q["reussi"] else "FAUX"
            lignes.append(f"   [{marque}] {q['question']} : attendu {q['attendu']}, réponse {q['obtenu']}")
            if not q["reussi"]:
                rates.append((r, q))
                entrainement.noter_lecon(
                    ctx.base, eleve, entrainement.MISSION_AGENT.get(eleve, ""),
                    f"Examen « {r['titre']} » raté : {q['question']}",
                    "Le calcul de l'agent ne donne pas la réponse du cours sur un cas d'école.",
                    f"Cours : {r['resume']} Tant que ce n'est pas corrigé, dire que ce point est peu fiable.",
                    f"attendu {q['attendu']}, réponse {q['obtenu']}")
    moyenne = round(sum(r["note"] for r in resultats) / len(resultats), 1)
    lignes += ["", f"Moyenne : {moyenne:g}/20 ({'réussi' if moyenne >= entrainement.NOTE_REUSSITE else 'raté'}).",
               "Un exercice raté veut dire que le calcul ne suit pas la définition : c'est à corriger dans le code, "
               "pas à cacher."]
    doc = ctx.document("examen", f"Examen de {nom} — {moyenne:g}/20", "\n".join(lignes),
                       donnees={"agent": eleve, "graine": graine, "resultats": resultats}, role="connaissances",
                       statut="verifie" if not rates else "rejete")
    if rates:
        ctx.base.message(AGENT, DIRECTEUR, "alerte",
                         f"{nom} a raté {len(rates)} question(s) de son examen (document {doc}) : défaut de calcul "
                         "à corriger.", ctx.id, doc)
        if eleve != AGENT:
            ctx.base.message(AGENT, eleve, "examen", f"Tu as raté {len(rates)} question(s) : relis le document {doc}.",
                             ctx.id, doc)
    return {"agent": eleve, "moyenne": moyenne, "rates": len(rates), "document": doc}
