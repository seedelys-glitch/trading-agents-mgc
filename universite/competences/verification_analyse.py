# -*- coding: utf-8 -*-
"""
Agent 9 — le secrétaire-auditeur recalcule un document d'analyse VWAP & EMA 200, sans réutiliser le code de
l'agent vérifié : lecture SQL directe, regroupement, EMA et VWAP réécrits en Python pur.

Il contrôle aussi qu'aucune bougie postérieure à l'instant n'a été utilisée (look-ahead).
Verdict : « verifie » si tous les écarts sont sous la tolérance, sinon « rejete » (auteur et directeur prévenus).
"""

TYPE = "verification_analyse"
AGENT = 9
TITRE = "Vérification indépendante d'une analyse"
PARAMS = {"document": "numéro du document à vérifier"}
INTERNE = True

TOLERANCE = 0.01        # points : au-delà, le chiffre est faux
DUREES = {"M1": 60, "M3": 180, "M5": 300, "M15": 900, "H1": 3600, "D1": 86400}


def _bougies(base, jeu, unite, debut, fin):
    return [tuple(r) for r in base.cx().execute(
        "SELECT ts, o, h, l, c, v FROM bougies WHERE jeu=? AND unite=? AND ts>=? AND ts<=? ORDER BY ts",
        (jeu, unite, debut, fin)).fetchall()]


def _regrouper(lignes, pas):
    paquets = {}
    for ts, o, h, l, c, v in lignes:
        d = int(ts // pas * pas)
        if d not in paquets:
            paquets[d] = [d, o, h, l, c, v]
        else:
            p = paquets[d]
            p[2], p[3], p[4], p[5] = max(p[2], h), min(p[3], l), c, p[5] + v
    return [tuple(paquets[d]) for d in sorted(paquets)]


def ema_pure(closes, n):
    alpha = 2.0 / (n + 1)
    e = closes[0]
    serie = [e]
    for x in closes[1:]:
        e = alpha * x + (1 - alpha) * e
        serie.append(e)
    return serie


def executer(ctx):
    ident = int(ctx.params["document"])
    doc = ctx.base.un("SELECT * FROM documents WHERE id=?", (ident,))
    if not doc:
        raise ValueError(f"document {ident} introuvable")

    ctx.etape("documentaliste", f"Relit le document {ident} et les bougies qu'il cite")
    d = doc["donnees"]
    jeu, instant = d["jeu"], d["instant"]
    ecarts, problemes = [], []

    ctx.etape("chercheur", "Recalcule l'EMA 200 et le VWAP en Python pur, et cherche du look-ahead")
    for s in doc["sources"]:
        u, pas = s["unite"], DUREES[s["unite"]]
        if s.get("reconstruite_depuis"):
            petite = s["reconstruite_depuis"]
            brutes = _bougies(ctx.base, jeu, petite, s["debut"], s["fin"] + pas - DUREES[petite])
            if any(b[0] + DUREES[petite] > instant for b in brutes):
                problemes.append(f"{u} : bougie {petite} non fermée à l'instant (look-ahead)")
            lignes = _regrouper(brutes, pas)
        else:
            lignes = _bougies(ctx.base, jeu, u, s["debut"], s["fin"])
        if any(b[0] + pas > instant for b in lignes):
            problemes.append(f"{u} : bougie non fermée à l'instant analysé (look-ahead)")
        if len(lignes) != s["n"]:
            problemes.append(f"{u} : {len(lignes)} bougies retrouvées au lieu de {s['n']}")
            continue
        annonce = d["ema"].get(u, {})
        if annonce.get("disponible"):
            serie = ema_pure([b[4] for b in lignes], 200)
            ecarts.append({"quoi": f"EMA 200 {u}", "annonce": annonce["valeur"], "recalcul": round(serie[-1], 2),
                           "ecart": round(abs(serie[-1] - annonce["valeur"]), 4)})
            pente = "montante" if serie[-1] > serie[-21] else "descendante"
            if pente != annonce["pente"]:
                problemes.append(f"EMA 200 {u} : pente annoncée {annonce['pente']}, recalculée {pente}")

    vw = d["vwap"]
    if vw.get("disponible"):
        pas = DUREES[vw["unite"]]
        seance = [b for b in _bougies(ctx.base, jeu, vw["unite"], vw["debut_seance"], instant) if b[0] + pas <= instant]
        volume = sum(b[5] for b in seance)
        if len(seance) != vw["bougies"] or volume <= 0:
            problemes.append(f"VWAP : {len(seance)} bougies de séance retrouvées au lieu de {vw['bougies']}")
        else:
            typ = [((b[2] + b[3] + b[4]) / 3, b[5]) for b in seance]
            v = sum(t * q for t, q in typ) / volume
            e = (sum((t - v) ** 2 * q for t, q in typ) / volume) ** 0.5
            for quoi, recalcul in (("VWAP", v), ("bande_haute_1", v + e), ("bande_basse_1", v - e)):
                annonce = vw["valeur"] if quoi == "VWAP" else vw[quoi]
                ecarts.append({"quoi": quoi, "annonce": annonce, "recalcul": round(recalcul, 2),
                               "ecart": round(abs(recalcul - annonce), 4)})

    faux = [e for e in ecarts if e["ecart"] > TOLERANCE + 0.005]   # + demi-centime : arrondi à 2 décimales
    verdict = "verifie" if not faux and not problemes else "rejete"
    ctx.detail({"controles": len(ecarts), "faux": len(faux), "problemes": problemes})

    ctx.etape("professeur", "Rédige le procès-verbal de vérification")
    lignes = [f"Document vérifié : n° {ident} « {doc['titre']} » (agent {doc['agent']}).",
              f"Tolérance : {TOLERANCE} point (après arrondi au centime).", ""]
    lignes += [f"{e['quoi']} : annoncé {e['annonce']}, recalculé {e['recalcul']} -> "
               f"{'OK' if e['ecart'] <= TOLERANCE + 0.005 else 'FAUX'}" for e in ecarts]
    lignes += [f"Problème : {p}" for p in problemes]
    if not ecarts and not problemes:
        lignes.append("Aucun chiffre à vérifier dans ce document (indicateurs non disponibles).")
    lignes += ["", f"Verdict : {'VÉRIFIÉ' if verdict == 'verifie' else 'REJETÉ'}."]

    ctx.etape("connaissances", "Enregistre le verdict et prévient l'auteur", "verification")
    ctx.base.ecrire("UPDATE documents SET statut=?, verifie_par=? WHERE id=?", (verdict, ctx.agent, ident))
    pv = ctx.document("verification", f"Vérification du document {ident}", "\n".join(lignes),
                      donnees={"document": ident, "ecarts": ecarts, "problemes": problemes, "verdict": verdict},
                      sources=[{"document": ident}], role="professeur", statut="verifie")
    ctx.message(doc["agent"], "reponse", f"Document {ident} : {'vérifié' if verdict == 'verifie' else 'REJETÉ'}", pv)
    if verdict == "rejete":
        ctx.message(14, "alerte", f"Document {ident} rejeté : {len(faux)} chiffre(s) faux, {len(problemes)} problème(s).", pv)
    return {"document": ident, "verdict": verdict, "controles": len(ecarts), "faux": len(faux),
            "problemes": problemes, "proces_verbal": pv}
