# -*- coding: utf-8 -*-
"""
Le desk des spécialistes : chacun sa spécialité, puis ils débattent, puis le chef tranche.

  1. calculs.py calcule les niveaux exacts (aucun chiffre inventé par l'IA)
  2. Tour 1 : chaque spécialiste donne son avis sur SA partie des données
  3. Tour 2 : chacun lit les avis des autres et répond (d'accord / pas d'accord)
  4. Le chef de desk décide avec les règles de Jabran : long, short ou pas de trade

Lancé par serveur.py :
  python bureau.py --moteur lmstudio --ticker XAUUSD [--modele qwen3.5-9b]
"""

import argparse
import json
import re
import sys
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import moteur  # outils communs (configuration des IA, lecture des réponses)
from moteur import emettre, lire_lignes, message_clair, texte_du_message

SPECIALISTES = [
    {
        "cle": "smc",
        "nom": "SMC / ICT",
        "role": "spécialiste Smart Money Concepts : structure de marché (BOS, CHoCH), Fair Value Gaps, "
                "order blocks et liquidité, en lecture descendante D1 → H4 → H1 → M15",
        "donnees": ["marche", "smc"],
    },
    {
        "cle": "fibo",
        "nom": "Fibonacci",
        "role": "spécialiste Fibonacci qui applique strictement la méthode de Jabran (règles ci-dessous)",
        "donnees": ["marche", "fibo"],
    },
    {
        "cle": "ichimoku",
        "nom": "Ichimoku",
        "role": "spécialiste Ichimoku Kinko Hyo : Tenkan, Kijun, nuage (Kumo), Chikou, en D1, H4 et H1",
        "donnees": ["marche", "ichimoku"],
    },
    {
        "cle": "tendance",
        "nom": "Tendance",
        "role": "spécialiste de la tendance : EMA 200 (biais en H1), VWAP de session (confirmation intraday) "
                "et bougies Heikin Ashi (lecture de structure)",
        "donnees": ["marche", "tendance"],
    },
    {
        "cle": "orderflow",
        "nom": "Order flow",
        "role": "spécialiste order flow : profil de volume (POC, zone de valeur), delta cumulé et gros volumes. "
                "Attention : tes données sont ESTIMÉES à partir de bougies, pas un vrai footprint ; "
                "dis-le et reste prudent dans ta confiance",
        "donnees": ["marche", "orderflow"],
    },
    {
        "cle": "calendrier",
        "nom": "Macro & calendrier",
        "role": "spécialiste macro et calendrier : dollar (DXY) et taux 10 ans US, annonces économiques américaines "
                "et règles de la prop firm. Ton rôle principal : dire s'il est raisonnable de trader maintenant ou s'il faut attendre",
        "donnees": ["marche", "calendrier", "macro"],
    },
]

REGLES_JABRAN = """Règles de trading de Jabran (à respecter strictement) :
- Méthode en cascade : un setup Fibo + FVG en Weekly, puis on cherche le suivant en 12H, puis en 48 min, puis l'entrée en 12 min.
  On ne descend d'un étage que si l'étage du dessus a donné un setup. Le desk ne voit que D1, H12, H4, H1 et M15 :
  il donne le biais et la zone ; l'entrée se prend sur la bougie de confirmation 12 min (suivie par Jarvis).
- Biais : tendance de fond donnée par les BOS en 12H et en 1H, plus la direction de l'EMA 200.
- Entrée uniquement sur une zone de Fibo 0.618, 0.705, 0.786 ou 0.893 de la dernière belle impulsion, et seulement s'il y a un FVG sur la zone.
- Jamais d'entrée sur le niveau 0.5 (pour lui ce n'est qu'un range avant une manipulation).
- Le marché connaît déjà la news : avant son vrai mouvement il va chercher la liquidité (plus hauts/bas des sessions Asie et Londres, zone 0.893, order blocks).
- Stop : bord du FVG de la zone d'entrée + 20 % de la hauteur du FVG (évite les mèches de liquidité) ; sans FVG, 20 % de l'écart jusqu'à la zone Fibo suivante.
- Objectifs : niveau 0, puis -0.272, -1.272 et -2.618. Compte A : 25 % à chaque objectif. Compte B : 50 % au 0, 25 % au -1.272, 25 % au -2.618.
- Gestion : stop au point d'entrée dès que la bougie qui suit l'entrée clôture en gain ; stop au 0.5 après le -0.272, au 0 après le -1.272.
- Prop firm : Topstep. Règle personnelle : pas de trade un jour de réunion du FOMC ; discours du président de la Fed : rien 30 min avant et après ; annonce USD forte : rien 90 min avant et 30 min après.
- Fenêtre de trading : 15h30-20h heure de Paris. Risque : 1 % du capital par trade, calculé par le programme."""

FORMAT_TOUR_1 = """Réponds en français, uniquement avec ces 5 lignes :
BIAIS: haussier ou baissier ou neutre
CONFIANCE: un chiffre de 1 à 5
NIVEAUX: les 2 ou 3 prix clés de ta lecture
INVALIDATION: le prix qui invaliderait ton avis
ARGUMENT: 2 ou 3 phrases courtes qui justifient ton avis"""

FORMAT_TOUR_2 = """Réponds en français, uniquement avec ces 3 lignes :
BIAIS: ton biais final, haussier ou baissier ou neutre
CONFIANCE: un chiffre de 1 à 5
REPONSE: 2 phrases. Nomme le ou les spécialistes avec qui tu es d'accord, celui que tu contredis, et pourquoi. Change d'avis seulement si un argument chiffré t'a convaincu."""

FORMAT_CHEF = """Réponds en français, uniquement avec ces lignes :
DECISION: long ou short ou pas de trade
ZONE: la zone d'entrée (prix), ou « aucune »
SL: le prix du stop, ou « aucun »
TP1: prix (niveau 0)
TP2: prix (-0.272)
TP3: prix (-1.272)
TP4: prix (-2.618)
CONFIRMATION: ce qu'il faut voir sur le graphique avant d'entrer
RAISON: 2 ou 3 phrases
DESACCORD: le désaccord principal entre les spécialistes, en une phrase"""


def version_prompts():
    """Empreinte des consignes données aux IA : une stat ne mélange pas deux versions des prompts."""
    import hashlib

    texte = json.dumps([SPECIALISTES, REGLES_JABRAN, FORMAT_TOUR_1, FORMAT_TOUR_2, FORMAT_CHEF], ensure_ascii=False)
    return hashlib.sha256(texte.encode("utf-8")).hexdigest()[:10]


def appeler(llm, consigne, agent, compteur):
    """Un appel d'IA, mesuré (durée, jetons, erreur) et signalé au serveur pour la table llm_calls."""
    import datetime as dt
    import time

    compteur["appels"] += 1
    debut, horloge = dt.datetime.now(dt.UTC), time.perf_counter()
    trace = {"agent": agent, "fournisseur": compteur.get("fournisseur"), "modele": compteur.get("modele"),
             "debut": debut.isoformat(timespec="seconds"), "version_prompt": compteur.get("version_prompt"),
             "cout_usd": 0.0 if compteur.get("fournisseur") in ("lmstudio", "groq", "nvidia", "gemini") else None}
    try:
        reponse = llm.invoke(consigne)
        usage = getattr(reponse, "usage_metadata", None) or {}
        trace.update(statut="ok", jetons_entree=usage.get("input_tokens"), jetons_sortie=usage.get("output_tokens"))
        return texte_du_message(reponse)
    except Exception as erreur:
        trace.update(statut="erreur", erreur=message_clair(erreur))
        raise
    finally:
        trace.update(fin=dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                     duree_s=round(time.perf_counter() - horloge, 2))
        emettre(type="llm_call", **trace)


def normaliser_biais(texte):
    texte = (texte or "").lower()
    if "haussi" in texte or "bull" in texte or "achat" in texte:
        return "haussier"
    if "baissi" in texte or "bear" in texte or "vente" in texte:
        return "baissier"
    return "neutre"


def normaliser_decision(texte):
    texte = (texte or "").lower()
    if "pas de trade" in texte or "aucun" in texte or "attendre" in texte:
        return "pas de trade"
    if "long" in texte or "achat" in texte or "acheter" in texte:
        return "long"
    if "short" in texte or "vente" in texte or "vendre" in texte:
        return "short"
    return "pas de trade"


def confiance(texte):
    chiffres = [int(c) for c in str(texte) if c.isdigit()]
    return min(5, max(1, chiffres[0])) if chiffres else 3


def bloc_donnees(calculs_faits, cles):
    return "\n".join(f"### {c}\n{json.dumps(calculs_faits[c], ensure_ascii=False, indent=1, default=str)}" for c in cles)


def tour_1(llm, specialiste, calculs_faits, compteur):
    consigne = (
        f"Tu es le {specialiste['role']}, dans un desk de trading qui analyse {calculs_faits['marche']['ticker']}.\n"
        f"{REGLES_JABRAN if specialiste['cle'] == 'fibo' else ''}\n"
        "Voici les données calculées par programme (elles sont exactes, n'utilise QUE ces chiffres, n'en invente aucun) :\n"
        f"{bloc_donnees(calculs_faits, specialiste['donnees'])}\n\n{FORMAT_TOUR_1}"
    )
    lignes = lire_lignes(appeler(llm, consigne, f"{specialiste['cle']} (tour 1)", compteur),
                         ["BIAIS", "CONFIANCE", "NIVEAUX", "INVALIDATION", "ARGUMENT"])
    premier = lambda k: lignes[k][0] if lignes[k] else ""
    return {
        "biais": normaliser_biais(premier("BIAIS")),
        "confiance": confiance(premier("CONFIANCE")),
        "niveaux": premier("NIVEAUX"),
        "invalidation": premier("INVALIDATION"),
        "argument": " ".join(lignes["ARGUMENT"]),
    }


def tour_2(llm, specialiste, avis, calculs_faits, compteur):
    autres = "\n".join(
        f"- {s['nom']} : {avis[s['cle']]['biais']} (confiance {avis[s['cle']]['confiance']}/5). {avis[s['cle']]['argument']}"
        for s in SPECIALISTES if s["cle"] != specialiste["cle"] and s["cle"] in avis
    )
    moi = avis[specialiste["cle"]]
    consigne = (
        f"Tu es le {specialiste['role']}, dans un desk de trading qui analyse {calculs_faits['marche']['ticker']}.\n"
        f"Ton avis au premier tour : {moi['biais']} (confiance {moi['confiance']}/5). {moi['argument']}\n\n"
        f"Voici les avis des autres spécialistes :\n{autres}\n\n"
        "C'est le débat : défends ta lecture ou ajuste-la.\n\n" + FORMAT_TOUR_2
    )
    lignes = lire_lignes(appeler(llm, consigne, f"{specialiste['cle']} (tour 2)", compteur), ["BIAIS", "CONFIANCE", "REPONSE"])
    return {
        "biais": normaliser_biais(lignes["BIAIS"][0] if lignes["BIAIS"] else moi["biais"]),
        "confiance": confiance(lignes["CONFIANCE"][0] if lignes["CONFIANCE"] else moi["confiance"]),
        "reponse": " ".join(lignes["REPONSE"]),
    }


def chef(llm, avis, debat, calculs_faits, compteur):
    votes = Counter(d["biais"] for d in debat.values())
    resume = "\n".join(
        f"- {s['nom']} : tour 1 {avis[s['cle']]['biais']}, après débat {debat[s['cle']]['biais']} "
        f"(confiance {debat[s['cle']]['confiance']}/5). Niveaux : {avis[s['cle']]['niveaux']}. "
        f"Invalidation : {avis[s['cle']]['invalidation']}. {avis[s['cle']]['argument']} Débat : {debat[s['cle']]['reponse']}"
        for s in SPECIALISTES if s["cle"] in debat
    )
    consigne = (
        f"Tu es le chef d'un desk de trading. Tu dois décider pour {calculs_faits['marche']['ticker']} "
        f"(prix actuel {calculs_faits['marche']['prix']}, {calculs_faits['marche']['heure_paris']} heure de Paris).\n\n"
        f"{REGLES_JABRAN}\n\n"
        "Règles du desk : « pas de trade » si moins de 4 spécialistes sur 6 vont dans le même sens après le débat, "
        "si c'est un jour de réunion du FOMC, ou si aucune zone de Fibo valide (avec FVG) n'existe dans le sens du biais. "
        "Utilise UNIQUEMENT les prix des données calculées ci-dessous pour la zone, le stop et les objectifs.\n\n"
        f"Votes après débat : {votes.get('haussier', 0)} haussier(s), {votes.get('baissier', 0)} baissier(s), "
        f"{votes.get('neutre', 0)} neutre(s).\n\n"
        f"Le débat :\n{resume}\n\n"
        f"Données Fibo calculées :\n{json.dumps(calculs_faits['fibo'], ensure_ascii=False, default=str)}\n"
        f"Calendrier : {json.dumps(calculs_faits['calendrier'], ensure_ascii=False, default=str)}\n\n{FORMAT_CHEF}"
    )
    cles = ["DECISION", "ZONE", "SL", "TP1", "TP2", "TP3", "TP4", "CONFIRMATION", "RAISON", "DESACCORD"]
    lignes = lire_lignes(appeler(llm, consigne, "chef", compteur), cles)
    resultat = {k.lower(): " ".join(v) for k, v in lignes.items()}
    resultat["decision"] = normaliser_decision(resultat.get("decision"))
    resultat["votes"] = dict(votes)
    return resultat


def tous_les_prix(objet, trouves=None):
    """Tous les nombres calculés, pour vérifier que le chef ne cite pas de prix inventé."""
    trouves = set() if trouves is None else trouves
    if isinstance(objet, dict):
        for v in objet.values():
            tous_les_prix(v, trouves)
    elif isinstance(objet, (list, tuple)):
        for v in objet:
            tous_les_prix(v, trouves)
    elif isinstance(objet, (int, float)) and not isinstance(objet, bool):
        trouves.add(float(objet))
    return trouves


def prix_cites(texte):
    texte = re.sub(r"(?<=\d)[ \u00a0\u202f](?=\d{3}\b)", "", texte or "")  # « 4 593,5 » -> « 4593,5 »
    return [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", texte)]


def controler(decision, calculs_faits):
    """Règles appliquées par le programme (pas seulement demandées à l'IA) + contrôle des prix cités."""
    votes = decision["votes"]
    majorite = next((sens for sens in ("haussier", "baissier") if votes.get(sens, 0) >= 4), None)
    cal = calculs_faits.get("calendrier") or {}
    blocages = []
    if cal.get("fomc_aujourdhui"):
        blocages.append("Jour de réunion du FOMC : règle personnelle, pas de trade aujourd'hui.")
    blocages += cal.get("annonce_forte_dans_90_min") or []
    if not majorite:
        blocages.append("Desk divisé : il faut au moins 4 spécialistes sur 6 dans le même sens.")
    fibo = calculs_faits.get("fibo") or {}
    sens_fibo = {"haussière": "haussier", "baissière": "baissier"}.get(fibo.get("impulsion"))
    if not any(z.get("fvg_dessus") for z in fibo.get("zones_entree", [])):
        blocages.append("Aucune zone Fibo 0.618 à 0.893 avec un FVG dessus.")
    elif majorite and sens_fibo and sens_fibo != majorite:
        blocages.append(f"La dernière impulsion H1 est {fibo['impulsion']}, à l'inverse du desk : pas de zone Fibo dans le bon sens.")
    decision["blocages"] = blocages
    decision["regle_appliquee"] = ""
    if decision["decision"] != "pas de trade":
        attendu = "long" if majorite == "haussier" else "short" if majorite == "baissier" else None
        if blocages:
            decision["regle_appliquee"] = "Le chef voulait « " + decision["decision"] + " » : ramené à « pas de trade ». " + " ".join(blocages)
            decision["decision"] = "pas de trade"
        elif decision["decision"] != attendu:
            decision["regle_appliquee"] = "Le chef allait contre la majorité du desk : ramené à « pas de trade »."
            decision["decision"] = "pas de trade"

    # Les prix de la zone, du stop et des objectifs doivent venir des calculs
    marche = calculs_faits["marche"]
    prix, tolerance = float(marche["prix"]), max(float(marche["prix"]) * 0.0004, float(marche.get("atr_H1") or 0) * 0.05)
    catalogue = tous_les_prix(calculs_faits)
    douteux = set()
    for champ in ("zone", "sl", "tp1", "tp2", "tp3", "tp4"):
        for p in prix_cites(decision.get(champ)):
            if 0.5 * prix <= p <= 1.5 * prix and not any(abs(p - c) <= tolerance for c in catalogue):
                douteux.add(p)
    decision["prix_non_verifies"] = sorted(douteux)
    # Règle absolue de Jabran : jamais d'entrée sur le 0.5
    demi = (fibo.get("niveaux") or {}).get("0.5")
    if demi and decision["decision"] != "pas de trade" and any(abs(p - demi) <= tolerance * 2 for p in prix_cites(decision.get("zone"))):
        decision["regle_appliquee"] = "Le chef proposait une entrée sur le 0.5 du Fibo : interdit, ramené à « pas de trade »."
        decision["decision"] = "pas de trade"
    return decision


TICKERS_OR = {"XAUUSD", "XAU", "GOLD", "OR", "GC=F", "MGC", "MGC=F", "MGC1!"}
STATUTS = ("ACHAT ENVISAGEABLE", "VENTE ENVISAGEABLE", "ATTENDRE", "AUCUNE OPPORTUNITÉ", "ANALYSE BLOQUÉE")


def desaccord_reel(avis):
    """Le débat n'a lieu que si au moins un spécialiste est haussier ET un autre baissier."""
    biais = {a["biais"] for a in avis.values()}
    return {"haussier", "baissier"} <= biais


def debattre(args, calculs_faits, compteur, economiser=False):
    """Tour 1, tour 2 (sauf si economiser et aucun vrai désaccord), puis le chef. Renvoie la décision contrôlée."""
    from tradingagents.llm_clients.factory import create_tier_client

    moteur.verifier_acces(args.moteur)
    config = moteur.construire_config(args.moteur, args.modele)
    llm = create_tier_client(config, "quick").get_llm()
    llm_chef = create_tier_client(config, "deep").get_llm()
    compteur.update(fournisseur=args.moteur, modele=config["quick_think_llm"], version_prompt=version_prompts())
    emettre(type="debut", ticker=calculs_faits["marche"]["ticker"], modele=config["quick_think_llm"])

    # Groq gratuit : 8 000 jetons par minute -> un spécialiste à la fois ; Gemini gratuit : 2 à la fois
    paralleles = {"groq": 1, "gemini": 2}.get(args.moteur, 3)

    # Tour 1 : chacun sa spécialité
    avis = {}
    with ThreadPoolExecutor(max_workers=paralleles) as equipe:
        futurs = {s["cle"]: equipe.submit(tour_1, llm, s, calculs_faits, compteur) for s in SPECIALISTES}
        for cle, futur in futurs.items():
            try:
                avis[cle] = futur.result()
                emettre(type="avis", cle=cle, tour=1, appels=compteur["appels"], **avis[cle])
            except Exception as erreur:
                print(traceback.format_exc(), file=sys.stderr)
                emettre(type="avis", cle=cle, tour=1, erreur=message_clair(erreur), appels=compteur["appels"])
    if len(avis) < 2:
        raise RuntimeError("Trop peu de spécialistes ont répondu pour débattre.")

    # Tour 2 : le débat (sur le même instantané de données), seulement s'il y a un vrai désaccord
    debat = {}
    if economiser and not desaccord_reel(avis):
        for cle, a in avis.items():
            debat[cle] = {"biais": a["biais"], "confiance": a["confiance"],
                          "reponse": "(pas de débat : aucun spécialiste n'était dans le sens opposé)"}
            emettre(type="avis", cle=cle, tour=2, appels=compteur["appels"], **debat[cle])
    else:
        with ThreadPoolExecutor(max_workers=paralleles) as equipe:
            futurs = {s["cle"]: equipe.submit(tour_2, llm, s, avis, calculs_faits, compteur) for s in SPECIALISTES if s["cle"] in avis}
            for cle, futur in futurs.items():
                try:
                    debat[cle] = futur.result()
                except Exception as erreur:
                    print(traceback.format_exc(), file=sys.stderr)
                    debat[cle] = {"biais": avis[cle]["biais"], "confiance": avis[cle]["confiance"],
                                  "reponse": f"(pas de réponse au débat : {message_clair(erreur)})"}
                emettre(type="avis", cle=cle, tour=2, appels=compteur["appels"], **debat[cle])

    # Le chef de desk tranche
    decision = controler(chef(llm_chef, avis, debat, calculs_faits, compteur), calculs_faits)
    decision["debat_fait"] = not (economiser and not desaccord_reel(avis))
    return avis, debat, decision


def biais_du_desk(avis, debat):
    """Sens majoritaire (au moins 4 sur 6) et confiance moyenne de cette majorité, avec ses arguments."""
    votes = Counter(d["biais"] for d in debat.values())
    sens = next((s for s in ("haussier", "baissier") if votes.get(s, 0) >= 4), None)
    if not sens:
        return {"sens": None, "confiance": None, "arguments": []}
    membres = [c for c, d in debat.items() if d["biais"] == sens]
    moyenne = round(sum(debat[c]["confiance"] for c in membres) / len(membres), 1)
    noms = {s["cle"]: s["nom"] for s in SPECIALISTES}
    arguments = [f"{noms.get(c, c)} : {avis[c]['argument']}" for c in membres if avis.get(c, {}).get("argument")]
    return {"sens": sens, "confiance": moyenne, "accord": f"{len(membres)}/{len(debat)}", "arguments": arguments[:3]}


def finaliser_mgc(decision, avis, debat, calculs_faits, informatifs, config, perte_du_jour_usd=0.0):
    """Statut analytique final : configuration calculée par le programme, risque, vetos. Aucune IA ici."""
    from mgc import risque, setup

    biais = biais_du_desk(avis, debat)
    structurels = list(decision.get("blocages") or [])
    prix = float(calculs_faits["marche"]["prix"])
    config_trade, evaluation = None, None
    if biais["sens"]:
        sens = "achat" if biais["sens"] == "haussier" else "vente"
        config_trade, motif = setup.construire(calculs_faits.get("fibo"), sens, prix)
        if motif and not any(motif[:25] in b for b in structurels):
            structurels.append(motif)
        if config_trade:
            evaluation = risque.evaluer(sens, config_trade["entree"], config_trade["stop"], config_trade["tp1"],
                                        config, perte_du_jour_usd=perte_du_jour_usd)
            structurels += evaluation["vetos"]
    informatifs = list(informatifs)
    if decision.get("prix_non_verifies"):
        informatifs.append("Le chef a cité des prix absents des calculs : " +
                           ", ".join(str(p) for p in decision["prix_non_verifies"]) + ".")
    if structurels:
        statut = "AUCUNE OPPORTUNITÉ"
    elif informatifs:
        statut = "ATTENDRE"
    else:
        statut = "ACHAT ENVISAGEABLE" if config_trade["sens"] == "achat" else "VENTE ENVISAGEABLE"

    decision.update({
        "statut": statut,
        "biais": biais,
        "setup": config_trade,
        "risque": evaluation,
        "vetos": structurels,
        "vetos_informatifs": informatifs,
        "regime": calculs_faits.get("regime"),
        "contrat": calculs_faits["marche"]["ticker"],
        "donnees": calculs_faits.get("donnees"),
        "incertitudes": incertitudes(calculs_faits, perte_du_jour_usd),
    })
    # champs historiques (page, journal) : les niveaux affichés sont ceux du programme, jamais ceux de l'IA
    decision["blocages"] = structurels + informatifs
    decision["decision"] = {"ACHAT ENVISAGEABLE": "long", "VENTE ENVISAGEABLE": "short"}.get(statut, "pas de trade")
    if config_trade:
        decision.update(zone=f"{config_trade['entree']} (Fibo {config_trade['niveau']}, FVG {config_trade['fvg'][0]}-"
                             f"{config_trade['fvg'][1]})", sl=str(config_trade["stop"]), tp1=str(config_trade["tp1"]),
                        tp2=str(config_trade["tp2"]), tp3=str(config_trade["tp3"]), tp4=str(config_trade.get("tp4", "–")),
                        confirmation=config_trade["confirmation"])
    else:
        decision.update(zone="aucune", sl="aucun", tp1="–", tp2="–", tp3="–", tp4="–")
    return decision


def incertitudes(calculs_faits, perte_du_jour_usd):
    res = ["Order flow ESTIMÉ à partir des bougies (pas de vraies données ATAS)."]
    d = calculs_faits.get("donnees") or {}
    if not d.get("temps_reel"):
        res.append("Prix différés (Yahoo) : à recouper sur ton graphique.")
    res.append(calculs_faits.get("journal_jour") or
               "Perte du jour non lue : le risque suppose une journée à zéro.")
    res.append("Frais et glissement estimés (1,50 $ + 2 ticks par contrat) : à confirmer sur un relevé.")
    return res


def bloquer(calculs_faits, bloquants, informatifs):
    """Décision immédiate quand un veto tombe avant l'analyse : aucune IA n'est appelée."""
    return {
        "statut": "ANALYSE BLOQUÉE", "decision": "pas de trade", "zone": "aucune", "sl": "aucun",
        "tp1": "–", "tp2": "–", "tp3": "–", "tp4": "–", "votes": {}, "vetos": bloquants, "vetos_informatifs": informatifs,
        "blocages": bloquants + informatifs, "regle_appliquee": "", "prix_non_verifies": [],
        "raison": "Veto avant l'analyse : aucune IA n'a été appelée.",
        "contrat": (calculs_faits.get("marche") or {}).get("ticker"), "regime": calculs_faits.get("regime"),
        "donnees": calculs_faits.get("donnees"), "setup": None, "risque": None, "biais": {"sens": None},
    }


def analyse_mgc(args, compteur):
    """Le desk en analyste Micro Gold : contrat réel, données contrôlées, vetos AVANT les IA, statut analytique."""
    import datetime as dt

    import calculs
    from mgc import config as cfg
    from mgc import journal_jarvis, regime, sources, vetos

    config = cfg.charger()
    perte_du_jour, message_journal = journal_jarvis.perte_du_jour()
    maintenant = dt.datetime.now(dt.UTC)
    emettre(type="etape", etape="calculs", ticker="MGC")
    lot = sources.charger_mgc(maintenant, config)
    emettre(type="etape", etape="calculs", ticker=lot["contrat"])
    infos_donnees = {
        "source": lot["source"], "statut": lot["statut"], "temps_reel": lot["temps_reel"], "motifs": lot["motifs"][:8],
        "derniere_bougie_M5": lot["controles"]["M5"].get("derniere_bougie"), "age_M5_min": lot["controles"]["M5"].get("age_min"),
        "config": cfg.empreinte(config),
    }
    calculs_faits = {"marche": {"ticker": lot["contrat"]}, "donnees": infos_donnees}
    if lot["statut"] not in ("invalide", "perimee"):
        calculs_faits = calculs.preparer("MGC=F", lot["bougies"])
        calculs_faits["marche"].update(ticker=lot["contrat"], source=lot["source"],
                                       note=f"Contrat réel {lot['contrat']}, source {lot['source']}"
                                            f"{'' if lot['temps_reel'] else ' (DIFFÉRÉE)'}.")
        calculs_faits["donnees"] = infos_donnees
        calculs_faits["contrat"] = lot["etat_contrat"]
        calculs_faits["regime"] = regime.detecter(calculs_faits, maintenant)
        calculs_faits["journal_jour"] = message_journal
    cal_ = calculs_faits.get("calendrier") or {}
    niveau1 = vetos.niveau1(maintenant, config, lot["etat_contrat"], calculs_faits.pop("annonces_brutes", []),
                            cfg.pause_active(), lot["statut"], lot["motifs"],
                            calendrier_ok=cal_.get("disponible", lot["statut"] in ("invalide", "perimee")))
    emettre(type="donnees", donnees=calculs_faits)
    if niveau1["bloquants"]:
        emettre(type="decision", appels=compteur["appels"], **bloquer(calculs_faits, niveau1["bloquants"], niveau1["informatifs"]))
        return
    avis, debat, decision = debattre(args, calculs_faits, compteur, economiser=True)
    emettre(type="decision", appels=compteur["appels"],
            **finaliser_mgc(decision, avis, debat, calculs_faits, niveau1["informatifs"], config,
                            perte_du_jour_usd=perte_du_jour))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--moteur", required=True, choices=sorted(moteur.MOTEURS))
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--modele")
    args = parser.parse_args()
    compteur = {"appels": 0}
    try:
        if args.ticker.strip().upper() in TICKERS_OR:
            analyse_mgc(args, compteur)
        else:  # autres marchés : le desk d'origine, inchangé
            import calculs
            from cli.prompts import normalize_ticker_symbol

            moteur.verifier_acces(args.moteur)
            ticker = normalize_ticker_symbol(args.ticker)
            emettre(type="etape", etape="calculs", ticker=ticker)
            calculs_faits = calculs.preparer(ticker)
            calculs_faits.pop("annonces_brutes", None)
            emettre(type="donnees", donnees=calculs_faits)
            _, _, decision = debattre(args, calculs_faits, compteur)
            emettre(type="decision", appels=compteur["appels"], **decision)
        emettre(type="fin", appels=compteur["appels"])
    except Exception as erreur:
        print(traceback.format_exc(), file=sys.stderr)
        emettre(type="erreur", message=message_clair(erreur), appels=compteur["appels"])
        sys.exit(1)


if __name__ == "__main__":
    main()
