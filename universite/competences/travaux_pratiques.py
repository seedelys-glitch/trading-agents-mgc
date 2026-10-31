"""
Travaux pratiques en replay (31/10) : sur les vraies bougies gardées, à des instants passés tirés au hasard, l'agent
fait sa lecture avec les seules bougies FERMÉES à cet instant, puis on regarde le gold 4 heures plus tard.

On ne cherche pas un signal miracle : on mesure honnêtement si la lecture de l'agent a aidé, comparée au hasard
(taux de bonnes lectures, intervalle de Wilson, comparaison à « toujours parier sur le sens le plus fréquent »).
Moins de 30 cas = échantillon insuffisant. Rien n'est optimisé sur ces cas : pas de surapprentissage possible.
"""

import datetime as dt

from .. import entrainement
from ..agents import agent as fiche_agent

TYPE = "travaux_pratiques"
AGENT = 1
TITRE = "Travaux pratiques en replay (sa lecture a-t-elle aidé ?)"
PARAMS = {"jeu": "numéro du jeu de bougies", "agent": "1 SMC, 2 Fibo, 3 Ichimoku, 6 EMA 200, 7 Flux",
          "cas": "nombre d'instants au plus (80 par défaut)"}
INTERNE = True


def executer(ctx):
    eleve = int(ctx.params.get("agent") or ctx.agent)
    jeu = int(ctx.params["jeu"])
    if eleve not in entrainement.LECTURES:
        raise ValueError(f"l'agent {eleve} n'a pas de lecture à tester en replay")
    nom = (fiche_agent(eleve) or {}).get("nom", eleve)
    infos = ctx.base.un("SELECT * FROM jeux WHERE id=?", (jeu,))
    if not infos:
        raise ValueError(f"jeu de bougies {jeu} introuvable")
    graine = entrainement.graine_du_jour()
    ctx.etape("documentaliste", f"Tire au hasard des instants passés dans « {infos['nom']} »")
    ctx.etape("chercheur", f"Rejoue : {entrainement.LECTURES[eleve]}, bougies fermées seulement, puis résultat à "
                           f"{entrainement.HORIZON_H} h")
    tp = entrainement.travaux_pratiques(ctx.base, jeu, eleve, int(ctx.params.get("cas") or 80), graine, ctx.verifier)
    b = tp["bilan"]
    ctx.detail({k: b.get(k) for k in ("n", "taux", "naif", "verdict")})
    ctx.etape("professeur", "Explique le résultat et ses limites")
    note = entrainement.note_tp(b)
    lignes = [f"Travaux pratiques de {nom} : {entrainement.LECTURES[eleve]}.",
              f"Données : {infos['source']} — {infos['nom']} ({'temps réel' if infos['temps_reel'] else 'différées ou historiques'}).",
              f"Méthode : {len(tp['cas'])} instants tirés au hasard ; à chacun, seules les bougies fermées sont lues ; "
              f"résultat = clôture H1 {entrainement.HORIZON_H} h plus tard (mouvement de moins de "
              f"{entrainement.SEUIL_ATR:g} ATR = plat, ni juste ni faux).", ""]
    if b.get("n"):
        lignes += [f"Cas comptés : {b['n']} (sans avis : {b['sans_avis']}, plats : {b['plats']}).",
                   f"Lectures justes : {b['justes']} sur {b['n']} = {round(100 * b['taux'])} % "
                   f"(intervalle de Wilson {round(100 * b['wilson'][0])} à {round(100 * b['wilson'][1])} %).",
                   f"Hasard intelligent (toujours le sens le plus fréquent) : {round(100 * b['naif'])} %."]
        for s, v in b["par_session"].items():
            lignes.append(f"   {s} : {v['n']} cas, {round(100 * v['taux'])} % justes")
    lignes += ["", f"Verdict : {b['verdict']}.", f"Note : {note:g}/20." if note is not None else "Note : pas de note "
               "(échantillon insuffisant).",
               "Limites : passé ≠ futur ; une seule lecture testée seule, sans le reste de la stratégie ; données "
               "Yahoo différées."]
    entrainement.enregistrer(ctx.base, eleve, "replay", "lecture", note, {"bilan": b, "jeu": jeu}, graine, ctx.id,
                             reussi=note is not None and note >= 10)
    pire = min(b.get("par_session", {}).items(), key=lambda kv: kv[1]["taux"], default=None)
    if note is not None and pire and pire[1]["n"] >= 10 and pire[1]["taux"] < 0.45:
        entrainement.noter_lecon(
            ctx.base, eleve, entrainement.MISSION_AGENT.get(eleve, ""),
            f"En replay, la lecture « {entrainement.LECTURES[eleve]} » se trompe souvent en session {pire[0]}",
            f"{pire[1]['n']} cas en {pire[0]}, {round(100 * pire[1]['taux'])} % justes.",
            f"Pendant la session {pire[0]}, présenter cette lecture comme peu fiable et demander d'autres avis.")
    if b.get("verdict", "").startswith("la lecture s'est trompée"):
        entrainement.noter_lecon(
            ctx.base, eleve, entrainement.MISSION_AGENT.get(eleve, ""),
            f"En replay, la lecture « {entrainement.LECTURES[eleve]} » a fait pire que le hasard",
            f"{b['justes']} justes sur {b['n']}.", "Ne jamais présenter cette lecture seule comme un signal.")
    doc = ctx.document("travaux_pratiques", f"Travaux pratiques de {nom} — {dt.date.today():%d/%m}", "\n".join(lignes),
                       donnees={"agent": eleve, "jeu": jeu, "bilan": b, "cas": tp["cas"]},
                       sources=[{"jeu": jeu, "unite": "H1"}], role="professeur", statut="verifie")
    return {"agent": eleve, "note": note, "bilan": b, "document": doc}
