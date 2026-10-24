# -*- coding: utf-8 -*-
"""
Bulletin de notes des spécialistes du desk (calcul, aucune IA).

Après chaque desk, on regarde ce que le gold a VRAIMENT fait 4 heures plus tard et on note chaque spécialiste :

  mouvement = clôture H1 à +4 h - prix au moment de l'analyse ; seuil = 0,5 x ATR H1 du moment
  haussier juste si mouvement >= +seuil ; baissier juste si <= -seuil ; neutre juste si |mouvement| < seuil

Note d'un agent = part de justes sur ses 30 dernières analyses notées. Poids de vote = 1 tant qu'il a moins de
10 notes, puis 0,5 + note (entre 0,5 et 1,5) : les bons élèves pèsent plus dans le vote, les mauvais moins.
Une analyse dont les 4 h tombent marché fermé (week-end, pause) n'est pas notée.

Fichier : rapports\\salle\\bulletin.json (notes par analyse, poids, date de mise à jour).
"""

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ICI = Path(__file__).resolve().parent.parent
RAPPORTS = ICI.parent / "rapports" / "salle"
FICHIER = RAPPORTS / "bulletin.json"
HORIZON_H = 4
SEUIL_ATR = 0.5
NOTES_MIN = 10
DERNIERES = 30
NOMS = {"smc": "SMC / ICT", "fibo": "Fibonacci", "ichimoku": "Ichimoku", "tendance": "Tendance",
        "orderflow": "Order flow", "calendrier": "Calendrier", "liquidite": "Liquidité", "dollar": "Dollar & taux"}


def lire(fichier=FICHIER):
    try:
        return json.loads(Path(fichier).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"notes": {}, "poids": {}, "maj": None}


def poids(fichier=FICHIER):
    return dict(lire(fichier).get("poids") or {})


def prix_yahoo(debut, fin):
    """Clôtures H1 du gold (GC=F) entre deux dates UTC : liste [(datetime UTC de clôture, clôture)]."""
    import yfinance as yf

    df = yf.Ticker("GC=F").history(start=(debut - timedelta(days=1)).date().isoformat(),
                                   end=(fin + timedelta(days=2)).date().isoformat(), interval="1h", auto_adjust=False)
    if df is None or df.empty:
        return []
    return [(t.to_pydatetime().astimezone(timezone.utc) + timedelta(hours=1), float(c)) for t, c in df["Close"].dropna().items()]


def analyses_du_desk(rapports=RAPPORTS):
    """Les desks terminés (comparaison.json) avec : id, instant UTC, prix, ATR H1, biais finaux par spécialiste."""
    res = []
    for f in sorted(Path(rapports).glob("*/comparaison.json")):
        try:
            a = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if a.get("type") != "bureau" or not a.get("debut"):
            continue
        marche = (a.get("donnees") or {}).get("marche") or {}
        biais = {}
        for cle, s in (a.get("specialistes") or {}).items():
            tour = s.get("tour2") or s.get("tour1") or {}
            if cle in NOMS and tour.get("biais") in ("haussier", "baissier", "neutre"):
                biais[cle] = tour["biais"]
        if not biais or not marche.get("prix"):
            continue
        res.append({"id": a["id"], "instant": datetime.fromtimestamp(a["debut"], tz=timezone.utc),
                    "prix": float(marche["prix"]), "atr": float(marche.get("atr_H1") or 0) or float(marche["prix"]) * 0.002,
                    "biais": biais})
    return res


def juger(biais, mouvement, seuil):
    if biais == "haussier":
        return mouvement >= seuil
    if biais == "baissier":
        return mouvement <= -seuil
    return abs(mouvement) < seuil


def noter(rapports=RAPPORTS, fichier=FICHIER, charger_prix=prix_yahoo, maintenant=None):
    """Note les desks qui ont au moins 4 h et ne sont pas encore notés, puis recalcule les poids. Renvoie le bulletin."""
    maintenant = maintenant or datetime.now(timezone.utc)
    bulletin = lire(fichier)
    notes = bulletin.setdefault("notes", {})
    a_noter = [a for a in analyses_du_desk(rapports)
               if a["id"] not in notes and a["instant"] + timedelta(hours=HORIZON_H + 1) <= maintenant]
    if a_noter:
        prix = charger_prix(min(a["instant"] for a in a_noter), maintenant)
        for a in a_noter:
            cible = a["instant"] + timedelta(hours=HORIZON_H)
            apres = [(t, c) for t, c in prix if cible <= t <= cible + timedelta(hours=2)]
            if not apres:  # marché fermé à l'horizon : pas de note (sauf si les données manquent encore)
                if a["instant"] + timedelta(days=4) <= maintenant:
                    notes[a["id"]] = {"instant": a["instant"].isoformat(), "non_note": "marché fermé ou pas de prix"}
                continue
            mouvement = apres[0][1] - a["prix"]
            seuil = SEUIL_ATR * a["atr"]
            notes[a["id"]] = {"instant": a["instant"].isoformat(), "prix": a["prix"], "prix_4h": round(apres[0][1], 1),
                              "mouvement": round(mouvement, 1), "seuil": round(seuil, 1),
                              "agents": {c: {"biais": b, "juste": juger(b, mouvement, seuil)} for c, b in a["biais"].items()}}
    bulletin["eleves"] = classement(notes)
    bulletin["poids"] = {c: e["poids"] for c, e in bulletin["eleves"].items()}
    bulletin["maj"] = maintenant.isoformat(timespec="seconds")
    Path(fichier).parent.mkdir(parents=True, exist_ok=True)
    temporaire = Path(fichier).with_suffix(".tmp")
    temporaire.write_text(json.dumps(bulletin, ensure_ascii=False, indent=1), encoding="utf-8")
    temporaire.replace(fichier)
    return bulletin


def classement(notes):
    """Par agent : nombre de notes, justes, note (%), poids de vote, sur les DERNIERES analyses notées."""
    par_agent = {}
    for _, n in sorted(notes.items(), key=lambda kv: kv[1].get("instant", "")):
        for cle, r in (n.get("agents") or {}).items():
            par_agent.setdefault(cle, []).append(bool(r["juste"]))
    eleves = {}
    for cle, resultats in par_agent.items():
        recents = resultats[-DERNIERES:]
        justes = sum(recents)
        note = justes / len(recents) if recents else 0.0
        eleves[cle] = {"nom": NOMS.get(cle, cle), "notes": len(recents), "justes": justes,
                       "note_pct": round(100 * note), "poids": 1.0 if len(recents) < NOTES_MIN
                       else round(min(1.5, max(0.5, 0.5 + note)), 2)}
    return eleves


def resume(bulletin=None):
    """Texte court pour Jarvis (voix, Telegram) et le rêve du dimanche."""
    bulletin = bulletin or lire()
    eleves = bulletin.get("eleves") or {}
    notees = sum(1 for n in (bulletin.get("notes") or {}).values() if n.get("agents"))
    if not eleves:
        return ("Bulletin des agents : pas encore de note. Chaque desk est noté 4 heures après, selon ce que le gold "
                "a vraiment fait.")
    lignes = [f"Bulletin des agents ({notees} desk(s) noté(s), mouvement du gold 4 h après) :"]
    for e in sorted(eleves.values(), key=lambda e: (-e["note_pct"], -e["notes"])):
        poids_txt = f"poids {e['poids']}" if e["notes"] >= NOTES_MIN else f"poids 1 (encore {NOTES_MIN - e['notes']} note(s) avant d'ajuster)"
        lignes.append(f"• {e['nom']} : {e['justes']}/{e['notes']} juste(s) ({e['note_pct']} %), {poids_txt}")
    return "\n".join(lignes)


def noter_en_arriere_plan(intervalle_s=3600):
    """Boucle douce pour le serveur de la salle : note toutes les heures, une panne ne casse rien."""
    import threading

    def boucle():
        while True:
            try:
                noter()
            except Exception:
                logging.exception("Bulletin des agents : notation impossible")
            time.sleep(intervalle_s)

    threading.Thread(target=boucle, name="bulletin", daemon=True).start()
