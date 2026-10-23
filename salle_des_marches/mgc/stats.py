# -*- coding: utf-8 -*-
"""
Statistiques des scénarios suivis (résultats notés avec /resultat), par setup et par version.

Taux de réussite avec intervalle de Wilson à 95 %, profit factor, espérance (en R et en $), gain et perte
moyens, drawdown maximal (en R, dans l'ordre chronologique). En dessous de 30 résultats : aucune conclusion.
"""

import math

MIN_ECHANTILLON = 30


def wilson(gagnants, total, z=1.96):
    """Intervalle de confiance du taux de réussite (borne basse, borne haute), entre 0 et 1."""
    if total == 0:
        return (0.0, 0.0)
    p = gagnants / total
    centre = (p + z * z / (2 * total)) / (1 + z * z / total)
    marge = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return (round(max(0.0, centre - marge), 4), round(min(1.0, centre + marge), 4))


def drawdown_max(valeurs):
    """Plus forte baisse depuis un sommet de la courbe cumulée (nombre positif, 0 si aucune baisse)."""
    cumul = sommet = pire = 0.0
    for v in valeurs:
        cumul += v
        sommet = max(sommet, cumul)
        pire = max(pire, sommet - cumul)
    return round(pire, 2)


def resumer(resultats):
    """resultats : liste de dicts {issue, r_multiple, pnl_usd_net} dans l'ordre chronologique."""
    n = len(resultats)
    if n == 0:
        return {"nombre": 0, "conclusion": "Aucun résultat noté."}
    gagnants = sum(r["issue"] == "win" for r in resultats)
    r_vals = [r["r_multiple"] for r in resultats if r.get("r_multiple") is not None]
    usd = [r["pnl_usd_net"] for r in resultats if r.get("pnl_usd_net") is not None]
    gains = [v for v in r_vals if v > 0]
    pertes = [v for v in r_vals if v < 0]
    bas, haut = wilson(gagnants, n)
    res = {
        "nombre": n,
        "gagnants": gagnants,
        "taux_reussite": round(gagnants / n, 4),
        "wilson_95": [bas, haut],
        "profit_factor": round(sum(gains) / -sum(pertes), 2) if pertes else None,
        "esperance_R": round(sum(r_vals) / len(r_vals), 3) if r_vals else None,
        "esperance_usd": round(sum(usd) / len(usd), 2) if usd else None,
        "gain_moyen_R": round(sum(gains) / len(gains), 3) if gains else None,
        "perte_moyenne_R": round(sum(pertes) / len(pertes), 3) if pertes else None,
        "drawdown_max_R": drawdown_max(r_vals),
        "total_usd": round(sum(usd), 2) if usd else None,
    }
    res["conclusion"] = (f"Échantillon trop petit ({n} < {MIN_ECHANTILLON}) : aucune conclusion possible."
                         if n < MIN_ECHANTILLON else
                         f"Taux de réussite entre {bas:.0%} et {haut:.0%} (95 %).")
    return res


def par_groupe(conn, cle="setup"):
    """Statistiques groupées : « setup » (sens + niveau Fibo), « config » (version des réglages) ou « prompt »."""
    colonne = {"setup": "a.sens || ' ' || COALESCE(a.niveau_fibo, '?')", "config": "a.config_hash",
               "prompt": "a.version_prompt"}[cle]
    lignes = conn.execute(f"SELECT {colonne} AS groupe, r.issue, r.r_multiple, r.pnl_usd_net FROM resultats r "  # noqa: S608
                          "JOIN analyses a ON a.id = r.analyse_id ORDER BY r.note_le").fetchall()
    groupes = {}
    for ligne in lignes:
        groupes.setdefault(ligne["groupe"] or "sans setup", []).append(dict(ligne))
    return {g: resumer(v) for g, v in groupes.items()}


def texte(conn):
    """Résumé pour /stats : analyses par statut, scénarios suivis, statistiques par setup."""
    statuts = conn.execute("SELECT statut, COUNT(*) AS n FROM analyses GROUP BY statut ORDER BY n DESC").fetchall()
    total = sum(s["n"] for s in statuts)
    if not total:
        return "Aucune analyse enregistrée pour l'instant."
    lignes = [f"{total} analyse(s) : " + ", ".join(f"{s['n']} {s['statut']}" for s in statuts) + "."]
    tous = [dict(r) for r in conn.execute("SELECT issue, r_multiple, pnl_usd_net FROM resultats ORDER BY note_le")]
    g = resumer(tous)
    if not g["nombre"]:
        lignes.append("Scénarios suivis : aucun résultat noté (/resultat <id> <win|loss> <prix>).")
        return "\n".join(lignes)
    lignes.append(f"Scénarios suivis : {g['nombre']} ({g['gagnants']} gagnant(s)), espérance "
                  f"{g['esperance_R'] if g['esperance_R'] is not None else '–'} R, profit factor "
                  f"{g['profit_factor'] if g['profit_factor'] is not None else '–'}, drawdown max {g['drawdown_max_R']} R.")
    lignes.append(g["conclusion"])
    for nom, s in par_groupe(conn, "setup").items():
        lignes.append(f"• {nom} : {s['nombre']} résultat(s), {s['gagnants']} gagnant(s), espérance "
                      f"{s['esperance_R'] if s['esperance_R'] is not None else '–'} R")
    return "\n".join(lignes)
