# -*- coding: utf-8 -*-
"""
Serveur local de la « Salle des marchés ».

Ouvre une page dans le navigateur (http://127.0.0.1:8765) qui lance TradingAgents
avec plusieurs IA en parallèle (LM Studio, Gemini, DeepSeek) et compare leurs verdicts.
N'écoute que sur ce PC : rien n'est accessible depuis l'extérieur.
"""

import csv
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
from collections import Counter
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ICI = Path(__file__).resolve().parent
RACINE = ICI.parent
RAPPORTS = RACINE / "rapports" / "salle"
HISTORIQUE = RAPPORTS / "historique.json"
JOURNAL = RACINE / "Journal paper trading.xlsx"
FICHIER_CLES = RACINE / ".env"
# python.exe (et non pythonw.exe) pour les moteurs : leur sortie doit pouvoir être lue
PYTHON = Path(sys.executable).with_name("python.exe") if os.name == "nt" else Path(sys.executable)
if not PYTHON.exists():
    PYTHON = Path(sys.executable)
LMS = Path.home() / ".lmstudio" / "bin" / ("lms.exe" if os.name == "nt" else "lms")
URL_LMSTUDIO = os.environ.get("SALLE_LMSTUDIO_URL", "http://localhost:1234/v1")
LIMITE_S = 30 * 60  # une analyse est arrêtée au bout de 30 minutes, quoi qu'il arrive
LMSTUDIO_SANS_REFLEXION = {"refuse": False}  # LM Studio accepte-t-il reasoning_effort ?
# 8765 et 8766 sont pris par Jarvis : la salle utilise 8790 (ou le suivant libre)
PORT = int(os.environ.get("SALLE_PORT", "8790"))
SANS_FENETRE = 0x08000000 if os.name == "nt" else 0  # pas de fenêtre noire sous Windows

RAPPORTS.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=ICI / "serveur.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    encoding="utf-8",
)
try:  # aucune clé ni token en clair dans serveur.log, même dans un message d'erreur
    from mgc.journal_json import FiltreSecrets

    for _gestionnaire in logging.getLogger().handlers:
        _gestionnaire.addFilter(FiltreSecrets())
except ImportError:
    pass

NOMS ={"lmstudio": "LM Studio", "gemini": "Gemini", "groq": "Groq", "nvidia": "NVIDIA", "deepseek": "DeepSeek"}
CLES = {"gemini": "GOOGLE_API_KEY", "groq": "GROQ_API_KEY", "nvidia": "NVIDIA_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}
VERDICTS_FR = {"Buy": "Acheter", "Overweight": "Renforcer", "Hold": "Conserver", "Underweight": "Alléger", "Sell": "Vendre"}

# Les spécialistes du desk (mêmes clés que dans bureau.py)
SPECIALISTES = {
    "smc": "SMC / ICT",
    "fibo": "Fibonacci",
    "ichimoku": "Ichimoku",
    "tendance": "Tendance",
    "orderflow": "Order flow",
    "calendrier": "Macro & calendrier",
}

ANALYSES = {}  # analyses en mémoire, par identifiant
VERROU = threading.Lock()


# ---------------------------------------------------------------- outils


def lire_cles():
    """Lit le fichier .env (sans jamais renvoyer les valeurs à la page)."""
    valeurs = {}
    try:
        for ligne in FICHIER_CLES.read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if ligne and not ligne.startswith("#") and "=" in ligne:
                cle, _, valeur = ligne.partition("=")
                valeurs[cle.strip()] = valeur.strip().strip('"').strip("'")
    except OSError:
        pass
    return valeurs


def etat_lmstudio():
    """LM Studio répond-il, et quels modèles propose-t-il ?"""
    try:
        with urllib.request.urlopen(URL_LMSTUDIO + "/models", timeout=2) as reponse:
            donnees = json.loads(reponse.read().decode("utf-8"))
        modeles = [m["id"] for m in donnees.get("data", []) if "embed" not in m["id"]]
        return {"serveur": True, "modeles": modeles}
    except Exception:
        return {"serveur": False, "modeles": []}


def lancer_lms(*arguments, delai=300):
    """Lance l'outil lms de LM Studio et renvoie (réussi, sortie)."""
    if not LMS.exists():
        return False, "outil lms introuvable"
    try:
        resultat = subprocess.run(
            [str(LMS), *arguments],
            stdin=subprocess.DEVNULL,  # jamais de question interactive qui bloquerait
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=delai,
            creationflags=SANS_FENETRE,
        )
        logging.info("lms %s -> %s %s", arguments, resultat.returncode, (resultat.stdout + resultat.stderr)[-500:])
        return resultat.returncode == 0, (resultat.stdout + resultat.stderr)[-500:]
    except Exception as erreur:
        logging.exception("lms %s", arguments)
        return False, str(erreur)


def preparer_lmstudio(modele):
    """Démarre le serveur LM Studio et charge le modèle avec assez de mémoire de contexte."""
    if not etat_lmstudio()["serveur"]:
        lancer_lms("server", "start", delai=60)
        time.sleep(2)
    # On recharge seulement CE modèle (les autres, comme celui de Jarvis, ne sont pas touchés)
    lancer_lms("unload", modele, delai=60)
    for contexte in ("32768", "16384"):
        ok, _ = lancer_lms("load", modele, "--context-length", contexte)
        if ok:
            return True
    return False


def liberer_lmstudio(modele):
    """Décharge le modèle d'analyse pour rendre la mémoire de la carte graphique."""
    lancer_lms("unload", modele, delai=60)


def charger_historique():
    try:
        return json.loads(HISTORIQUE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def sauver_historique(entree):
    historique = [h for h in charger_historique() if h.get("id") != entree["id"]]
    historique.insert(0, entree)
    HISTORIQUE.write_text(json.dumps(historique[:200], ensure_ascii=False, indent=1), encoding="utf-8")


def calculer_consensus(moteurs):
    """Verdict partagé par au moins 2 IA (sinon pas de consensus)."""
    verdicts = [m["verdict"] for m in moteurs.values() if m.get("verdict") in VERDICTS_FR]
    if not verdicts:
        return {"verdict": None, "accord": 0, "reussies": 0, "total": len(moteurs)}
    verdict, nombre = Counter(verdicts).most_common(1)[0]
    if nombre < 2:
        verdict = None
    return {"verdict": verdict, "accord": nombre, "reussies": len(verdicts), "total": len(moteurs)}


def ecrire_journal(analyse):
    """Ajoute une ligne au journal Excel (ou dans un CSV si Excel est ouvert)."""
    consensus = analyse["consensus"]
    if consensus["verdict"]:
        texte_consensus = f"{consensus['verdict']} ({consensus['accord']}/{consensus['total']})"
    elif consensus.get("reussies", 0) < 2:
        texte_consensus = "Une seule IA a abouti"
    else:
        texte_consensus = "Pas d'accord"
    verdicts = " / ".join(f"{NOMS[k]} : {m.get('verdict') or 'erreur'}" for k, m in analyse["moteurs"].items())
    cle = (analyse.get("synthese") or {}).get("baissier_cle") or next(
        (m["resume"].get("baissier") for m in analyse["moteurs"].values() if m.get("resume")), ""
    )
    ligne = [analyse["date"], analyse["ticker"], verdicts, texte_consensus, None, None, None, cle]
    return ajouter_ligne_journal(ligne)


def ajouter_ligne_journal(ligne):
    """Écrit une ligne dans le journal Excel, ou dans un CSV de secours si Excel est ouvert."""
    try:
        from openpyxl import load_workbook

        classeur = load_workbook(JOURNAL)
        feuille = classeur["Journal"]
        rang = 2
        while feuille.cell(row=rang, column=1).value not in (None, ""):
            rang += 1
        for colonne, valeur in enumerate(ligne, start=1):
            if valeur is not None:
                feuille.cell(row=rang, column=colonne, value=valeur)
        classeur.save(JOURNAL)
        return "journal"
    except PermissionError:
        secours = RACINE / "journal_a_recopier.csv"
        nouveau = not secours.exists()
        with secours.open("a", newline="", encoding="utf-8-sig") as fichier:
            ecrivain = csv.writer(fichier, delimiter=";")
            if nouveau:
                ecrivain.writerow(["Date", "Ticker", "Verdicts", "Consensus", "5 séances", "1 mois", "Bon call ?", "Argument baissier clé"])
            ecrivain.writerow(["" if v is None else v for v in ligne])
        return "csv"
    except Exception:
        logging.exception("journal")
        return "erreur"


# ---------------------------------------------------------------- analyses


def env_moteurs():
    """Variables communes à tous les moteurs (clés relues à chaque fois, IA locale sans réflexion)."""
    env = os.environ.copy()
    env.update(lire_cles())
    env.update({
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        # LM Studio passe par la salle, qui lui demande de répondre sans « réfléchir » (bien plus rapide)
        "SALLE_LMSTUDIO_PROXY": f"http://127.0.0.1:{PORT}/lmstudio/v1",
        # moins d'allers-retours d'outils par analyste (20 par défaut)
        "TRADINGAGENTS_MAX_TOOL_ROUNDS": "6",
    })
    return env


def chien_de_garde(processus, suivi, limite_s=LIMITE_S):
    """Arrête le processus s'il dépasse la limite de temps."""
    def arreter():
        if processus.poll() is None:
            with VERROU:
                suivi["erreur"] = f"Arrêté : limite de {LIMITE_S // 60} minutes atteinte. Essaie Gemini, ou moins d'analystes."
                suivi["trop_long"] = True
            processus.kill()
    minuterie = threading.Timer(limite_s, arreter)
    minuterie.daemon = True
    minuterie.start()
    return minuterie


def executer_moteur(analyse, cle_moteur, modele_local):
    """Lance un processus moteur.py pour une IA et suit sa progression."""
    suivi = analyse["moteurs"][cle_moteur]
    dossier = RAPPORTS / analyse["id"] / cle_moteur
    dossier.mkdir(parents=True, exist_ok=True)
    with VERROU:
        suivi["etat"] = "en_cours"
        suivi["debut"] = time.time()

    if cle_moteur == "lmstudio":
        with VERROU:
            suivi["etape_texte"] = "Chargement du modèle local"
        pret = preparer_lmstudio(modele_local)
        with VERROU:
            suivi["etape_texte"] = ""
            if not pret:
                suivi["avertissement"] = "Modèle chargé par LM Studio avec ses réglages par défaut."

    env = env_moteurs()  # clés relues à chaque analyse : pas besoin de redémarrer
    env.update(
        {
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            # Chaque IA garde son propre cache et sa propre mémoire de décisions
            "TRADINGAGENTS_CACHE_DIR": str(Path.home() / ".tradingagents" / "salle" / cle_moteur / "cache"),
            "TRADINGAGENTS_MEMORY_LOG_PATH": str(Path.home() / ".tradingagents" / "salle" / cle_moteur / "trading_memory.md"),
            "TRADINGAGENTS_RESULTS_DIR": str(Path.home() / ".tradingagents" / "salle" / cle_moteur / "logs"),
        }
    )
    commande = [
        str(PYTHON), str(ICI / "moteur.py"),
        "--moteur", cle_moteur,
        "--ticker", analyse["ticker_saisi"],
        "--date", analyse["date"],
        "--analystes", ",".join(analyse["analystes"]),
        "--sortie", str(dossier),
    ]
    if cle_moteur == "lmstudio" and modele_local:
        commande += ["--modele", modele_local]

    with open(dossier / "moteur.log", "w", encoding="utf-8") as journal_erreurs:
        processus = subprocess.Popen(
            commande,
            cwd=RACINE,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=journal_erreurs,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=SANS_FENETRE,
        )
        analyse["_processus"].append(processus)
        garde = chien_de_garde(processus, suivi, max(60, int(analyse["limite"] - time.time())))
        for ligne in processus.stdout:
            try:
                evenement = json.loads(ligne)
            except ValueError:
                continue
            with VERROU:
                genre = evenement.pop("type", "")
                if genre == "debut":
                    analyse["ticker"] = evenement.get("ticker", analyse["ticker"])
                    suivi["modele"] = evenement.get("modele_quick")
                elif genre == "progression":
                    suivi.update(evenement)
                elif genre == "fin":
                    suivi.update(evenement)
                    suivi["etat"] = "fini"
                    suivi["rapport"] = f"/rapports/{analyse['id']}/{cle_moteur}/rapport/complete_report.html"
                    suivi["sections"] = f"/rapports/{analyse['id']}/{cle_moteur}/sections.json"
                elif genre == "erreur":
                    suivi["etat"] = "erreur"
                    suivi["erreur"] = evenement.get("message")
        processus.wait()
        garde.cancel()

    with VERROU:
        suivi["fin"] = time.time()
        if suivi["etat"] not in ("fini", "erreur"):
            suivi["etat"] = "erreur"
            suivi["erreur"] = suivi.get("erreur") or ("Analyse arrêtée." if analyse.get("annulee") else "Le moteur s'est arrêté sans réponse.")


def faire_synthese(analyse, modele_local):
    """Compare les IA qui ont réussi (avec l'IA gratuite disponible en priorité)."""
    reussis = {k: m for k, m in analyse["moteurs"].items() if m["etat"] == "fini"}
    if len(reussis) < 2:
        return
    donnees = {"ticker": analyse["ticker"], "date": analyse["date"], "moteurs": {}}
    for cle, suivi in reussis.items():
        try:
            sections = json.loads((RAPPORTS / analyse["id"] / cle / "sections.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            sections = {}
        donnees["moteurs"][NOMS[cle]] = {"verdict": suivi.get("verdict"), "sections": sections}
    fichier = RAPPORTS / analyse["id"] / "synthese_entree.json"
    fichier.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")

    for cle in [c for c in ("lmstudio", "gemini", "groq", "nvidia", "deepseek") if c in reussis]:
        analyse["synthese"] = {"etat": "en_cours", "par": NOMS[cle]}
        env = env_moteurs()
        commande = [str(PYTHON), str(ICI / "moteur.py"), "--moteur", cle, "--synthese", str(fichier)]
        if cle == "lmstudio" and modele_local:
            commande += ["--modele", modele_local]
        resultat = subprocess.run(
            commande, cwd=RACINE, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
            encoding="utf-8", errors="replace", creationflags=SANS_FENETRE,
            timeout=max(60, min(300, int(analyse["limite"] - time.time()))),
        )
        for ligne in resultat.stdout.splitlines():
            try:
                evenement = json.loads(ligne)
            except ValueError:
                continue
            if evenement.get("type") == "synthese":
                evenement.pop("type")
                evenement["etat"] = "fini"
                analyse["synthese"] = evenement
                return
        logging.warning("synthèse %s échouée : %s", cle, resultat.stderr[-800:])
    analyse["synthese"] = {"etat": "erreur"}


def executer_analyse(analyse, modele_local):
    """Lance toutes les IA en parallèle, puis compare et enregistre."""
    fils = [
        threading.Thread(target=executer_moteur, args=(analyse, cle, modele_local), daemon=True)
        for cle in analyse["moteurs"]
    ]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join()

    analyse["consensus"] = calculer_consensus(analyse["moteurs"])
    if not analyse.get("annulee") and analyse["limite"] - time.time() > 90:
        analyse["etat"] = "synthese"
        try:
            faire_synthese(analyse, modele_local)
        except Exception:
            logging.exception("synthèse")
            analyse["synthese"] = {"etat": "erreur"}
    if "lmstudio" in analyse["moteurs"]:
        liberer_lmstudio(modele_local)  # rend la mémoire de la carte graphique (Jarvis, jeux...)
    analyse["etat"] = "fini"
    analyse["fin"] = time.time()

    propre = public(analyse)
    (RAPPORTS / analyse["id"] / "comparaison.json").write_text(json.dumps(propre, ensure_ascii=False, indent=1), encoding="utf-8")
    if any(m["etat"] == "fini" for m in analyse["moteurs"].values()):
        analyse["journal"] = ecrire_journal(analyse)
        sauver_historique(
            {
                "id": analyse["id"],
                "type": "firme",
                "date": analyse["date"],
                "heure": datetime.fromtimestamp(analyse["debut"]).strftime("%H:%M"),
                "ticker": analyse["ticker"],
                "verdicts": {k: m.get("verdict") for k, m in analyse["moteurs"].items()},
                "consensus": analyse["consensus"],
            }
        )
        (RAPPORTS / analyse["id"] / "comparaison.json").write_text(
            json.dumps(public(analyse), ensure_ascii=False, indent=1), encoding="utf-8"
        )


def executer_bureau(analyse, modele_local):
    """Lance le desk des spécialistes (bureau.py) avec une seule IA et suit le débat."""
    cle_moteur = analyse["moteur"]
    dossier = RAPPORTS / analyse["id"]
    dossier.mkdir(parents=True, exist_ok=True)
    if cle_moteur == "lmstudio":
        analyse["etape"] = "Chargement du modèle local"
        if not preparer_lmstudio(modele_local):
            analyse["avertissement"] = "Modèle chargé par LM Studio avec ses réglages par défaut."
    analyse["etape"] = "Calcul des niveaux"
    env = env_moteurs()
    commande = [str(PYTHON), str(ICI / "bureau.py"), "--moteur", cle_moteur, "--ticker", analyse["ticker_saisi"]]
    if cle_moteur == "lmstudio" and modele_local:
        commande += ["--modele", modele_local]
    with open(dossier / "bureau.log", "w", encoding="utf-8") as journal_erreurs:
        processus = subprocess.Popen(
            commande, cwd=RACINE, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=journal_erreurs, text=True, encoding="utf-8", errors="replace", creationflags=SANS_FENETRE,
        )
        analyse["_processus"].append(processus)
        garde = chien_de_garde(processus, analyse, max(60, int(analyse["limite"] - time.time())))
        for ligne in processus.stdout:
            try:
                evenement = json.loads(ligne)
            except ValueError:
                continue
            genre = evenement.pop("type", "")
            with VERROU:
                analyse["appels"] = evenement.pop("appels", analyse.get("appels", 0))
                if genre == "etape":
                    analyse["ticker"] = evenement.get("ticker", analyse["ticker"])
                elif genre == "donnees":
                    analyse["donnees"] = evenement["donnees"]
                    analyse["etape"] = "Avis des spécialistes"
                elif genre == "debut":
                    analyse["modele"] = evenement.get("modele")
                elif genre == "avis":
                    suivi = analyse["specialistes"][evenement.pop("cle")]
                    tour = evenement.pop("tour")
                    if evenement.get("erreur"):
                        suivi["erreur"] = evenement["erreur"]
                        suivi["etat"] = "erreur"
                    else:
                        suivi[f"tour{tour}"] = evenement
                        suivi["etat"] = "debat" if tour == 1 else "fini"
                    if all(sp["etat"] != "attente" for sp in analyse["specialistes"].values()):
                        analyse["etape"] = "Débat" if tour == 1 else "Décision du chef de desk"
                elif genre == "decision":
                    analyse["decision"] = evenement
                elif genre == "llm_call":  # un appel d'IA mesuré (table llm_calls)
                    analyse.setdefault("llm_calls", []).append(evenement)
                elif genre == "erreur":
                    analyse["erreur"] = evenement.get("message")
        processus.wait()
        garde.cancel()

    if cle_moteur == "lmstudio":
        liberer_lmstudio(modele_local)
    analyse["etat"] = "fini"
    analyse["etape"] = ""
    analyse["fin"] = time.time()
    if analyse.get("annulee") and not analyse.get("erreur"):
        analyse["erreur"] = "Analyse arrêtée."
    (dossier / "comparaison.json").write_text(json.dumps(public(analyse), ensure_ascii=False, indent=1), encoding="utf-8")
    decision = analyse.get("decision")
    if decision:
        votes = decision.get("votes", {})
        texte_votes = f"{votes.get('haussier', 0)} haussier(s), {votes.get('baissier', 0)} baissier(s), {votes.get('neutre', 0)} neutre(s)"
        plan = decision.get("statut") or decision["decision"].upper()
        if decision.get("setup") and decision.get("statut") != "AUCUNE OPPORTUNITÉ":
            s = decision["setup"]
            plan += f" {s['sens']} {s['entree']} / SL {s['stop']} / TP1 {s['tp1']}"
        elif decision["decision"] != "pas de trade":
            plan += f" zone {decision.get('zone', '')} / SL {decision.get('sl', '')} / TP1 {decision.get('tp1', '')}"
        analyse["journal"] = ajouter_ligne_journal(
            [analyse["date"], analyse["ticker"], f"Desk ({NOMS[cle_moteur]}) : {texte_votes}", plan,
             None, None, None, decision.get("desaccord") or decision.get("raison", "")]
        )
        sauver_historique(
            {
                "id": analyse["id"], "type": "bureau", "date": analyse["date"],
                "heure": datetime.fromtimestamp(analyse["debut"]).strftime("%H:%M"),
                "ticker": analyse["ticker"], "moteur": cle_moteur,
                "decision": decision["decision"], "votes": votes, "statut": decision.get("statut"),
            }
        )
        (dossier / "comparaison.json").write_text(json.dumps(public(analyse), ensure_ascii=False, indent=1), encoding="utf-8")
    memoriser(analyse)


def memoriser(analyse):
    """Range l'analyse dans la base de l'analyste (rapports\\salle\\analyste.sqlite) ; une panne ici ne casse rien."""
    try:
        from mgc import base
        from mgc import config as cfg

        version_prompt = next((c.get("version_prompt") for c in analyse.get("llm_calls") or []), None)
        config = cfg.charger()
        conn = base.ouvrir()
        try:
            base.enregistrer_analyse(conn, public(analyse), config=config, version_prompt=version_prompt)
            base.evenement(conn, "analyse", f"{analyse['id']} : {(analyse.get('decision') or {}).get('statut') or analyse.get('erreur') or 'fini'}")
        finally:
            conn.close()
        base.sauvegarder()
        from mgc import journal_json

        d = analyse.get("decision") or {}
        journal_json.ecrire("analyse", d.get("statut") or analyse.get("erreur") or "fini", id=analyse["id"],
                            contrat=d.get("contrat") or analyse.get("ticker"), moteur=analyse.get("moteur"),
                            appels=analyse.get("appels"), duree_s=round((analyse.get("fin") or 0) - analyse["debut"], 1),
                            vetos=d.get("vetos"), limites=d.get("vetos_informatifs"),
                            appels_ia_en_erreur=sum(c.get("statut") == "erreur" for c in analyse.get("llm_calls") or []))
    except Exception:
        logging.exception("Base de l'analyste : enregistrement de %s impossible", analyse.get("id"))


def resume_mgc(a, d):
    """Message de l'analyste MGC : statut, contrat réel, niveaux du programme, risque, vetos, fraîcheur des données."""
    quand = datetime.fromtimestamp(a.get("debut") or time.time()).strftime("%d/%m %Hh%M")
    lignes = [f"{d['statut']} · {d.get('contrat') or a.get('ticker')} · {quand} (heure de Paris)"]
    r = d.get("regime") or {}
    if r:
        lignes.append(f"Régime : {r.get('regime')} (confiance {r.get('confiance')}). {r.get('justification', '')}")
    b = d.get("biais") or {}
    v = d.get("votes", {})
    if b.get("sens"):
        lignes.append(f"Biais du desk : {b['sens']} ({b.get('accord')}, confiance moyenne {b.get('confiance')}/5).")
    elif v:
        lignes.append(f"Desk : {v.get('haussier', 0)} haussier(s), {v.get('baissier', 0)} baissier(s), {v.get('neutre', 0)} neutre(s).")
    for arg in b.get("arguments") or []:
        lignes.append(f"• {arg}")
    s, rq = d.get("setup"), d.get("risque")
    if s:
        titre = "Niveaux à surveiller" if d["statut"] != f"{'ACHAT' if s['sens'] == 'achat' else 'VENTE'} ENVISAGEABLE" else "Configuration"
        lignes.append(f"{titre} ({s['sens']}) : entrée {s['entree']} (Fibo {s['niveau']}, FVG {s['fvg'][0]}-{s['fvg'][1]}), "
                      f"stop {s['stop']}, TP1 {s['tp1']} (25 %), TP2 {s['tp2']} (50 %), TP3 {s['tp3']}.")
        lignes.append(f"Confirmation : {s['confirmation']}. Invalidation : {s['invalidation']}.")
    if rq and rq.get("risque_net_par_contrat") is not None:
        lignes.append(f"Risque par contrat : {rq['risque_brut_par_contrat']:.2f} $ brut, {rq['risque_net_par_contrat']:.2f} $ net "
                      f"(frais + glissement). Contrats : {rq['contrats']} (calculés : {rq.get('contrats_calcules', 0)}). "
                      f"Ratio net TP1 : {rq['ratio_net_tp1']}. Break-even : {rq['break_even']}.")
    if d.get("vetos"):
        lignes.append("Vetos : " + " ".join(d["vetos"]))
    if d.get("vetos_informatifs"):
        lignes.append("Limites : " + " ".join(d["vetos_informatifs"]))
    if d.get("raison"):
        lignes.append(f"Chef de desk : {d['raison']}")
    if d.get("desaccord"):
        lignes.append(f"Désaccord : {d['desaccord']}")
    don = d.get("donnees") or {}
    if don:
        lignes.append(f"Données : {don.get('source')} ({'temps réel' if don.get('temps_reel') else 'DIFFÉRÉES'}), "
                      f"statut {don.get('statut')}, dernière bougie 5 min : {don.get('derniere_bougie_M5') or '–'}.")
    for inc in d.get("incertitudes") or []:
        lignes.append(f"Incertitude : {inc}")
    lignes.append(f"Analyse {a.get('id')} · réglages {don.get('config', '–')}")
    return "\n".join(lignes)


def resume_texte(analyse):
    """Résumé court, prêt à être envoyé tel quel sur le téléphone (Telegram de Jarvis)."""
    a = analyse
    if a.get("type") == "bureau":
        d = a.get("decision") or {}
        if d.get("statut"):
            return resume_mgc(a, d)
        titre = f"Desk {a.get('ticker_saisi') or a['ticker']} ({NOMS.get(a.get('moteur'), a.get('moteur'))})"
        if a.get("erreur") and not d:
            return f"{titre} : pas de résultat. {a['erreur']}"
        if not d:
            return f"{titre} : en cours ({a.get('etape') or 'préparation'})."
        v = d.get("votes", {})
        lignes = [
            f"{titre} : {d.get('decision', '?').upper()}",
            f"Vote après débat : {v.get('haussier', 0)} haussier(s), {v.get('baissier', 0)} baissier(s), {v.get('neutre', 0)} neutre(s).",
        ]
        if d.get("decision") != "pas de trade":
            lignes.append(f"Zone : {d.get('zone', '–')} | Stop : {d.get('sl', '–')}")
            lignes.append(f"TP1 : {d.get('tp1', '–')} | TP2 : {d.get('tp2', '–')} | TP3 : {d.get('tp3', '–')}")
            if d.get("confirmation"):
                lignes.append(f"À attendre : {d['confirmation']}")
        if d.get("regle_appliquee"):
            lignes.append(d["regle_appliquee"])
        elif d.get("decision") == "pas de trade" and d.get("blocages"):
            lignes.append("Pourquoi : " + " ".join(d["blocages"]))
        if d.get("raison"):
            lignes.append(d["raison"])
        if d.get("prix_non_verifies"):
            lignes.append("Prix à vérifier sur ton graphique : " + ", ".join(str(p) for p in d["prix_non_verifies"]))
        return "\n".join(lignes)
    # firme complète
    titre = f"Firme {a.get('ticker_saisi') or a['ticker']}"
    if a.get("etat") != "fini":
        return f"{titre} : en cours."
    morceaux = [f"{NOMS.get(k, k)} : {m.get('verdict') or 'erreur'}" for k, m in a.get("moteurs", {}).items()]
    c = a.get("consensus") or {}
    consensus = f"{c['verdict']} ({c['accord']}/{c['total']})" if c.get("verdict") else "pas de consensus"
    lignes = [f"{titre} : {consensus}", " | ".join(morceaux)]
    cle = (a.get("synthese") or {}).get("baissier_cle")
    if cle:
        lignes.append(f"Argument baissier clé : {cle}")
    return "\n".join(lignes)


def public(analyse):
    """Version de l'analyse envoyable à la page (sans objets internes)."""
    return {k: v for k, v in analyse.items() if not k.startswith("_")}


ALIAS_TICKERS = {"GOLD": "XAUUSD", "OR": "XAUUSD", "XAU": "XAUUSD", "BITCOIN": "BTC-USD", "BTC": "BTC-USD"}


def ia_automatique():
    """L'IA gratuite la plus pratique disponible : LM Studio, sinon Groq, sinon NVIDIA, sinon Gemini."""
    cles = lire_cles()
    if etat_lmstudio()["serveur"] or LMS.exists():
        return "lmstudio"
    for ia in ("groq", "nvidia", "gemini"):  # NVIDIA seulement si sa clé est collée
        if cles.get(CLES[ia]):
            return ia
    raise ValueError("Aucune IA disponible : ouvre LM Studio ou colle une clé Gemini, Groq ou NVIDIA.")


def nouvelle_analyse(demande):
    ticker = re.sub(r"[^A-Za-z0-9.=\-^/]", "", str(demande.get("ticker", ""))).upper()[:20]
    ticker = ALIAS_TICKERS.get(ticker, ticker)
    if not ticker:
        raise ValueError("Écris un ticker, par exemple NVDA.")
    with VERROU:
        if any(a["etat"] != "fini" for a in ANALYSES.values()):
            raise ValueError("Une analyse tourne déjà. Attends la fin ou arrête-la.")
    identifiant = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + ticker.replace("/", "-").replace("=", "-")
    modele_local = str(demande.get("modele_local") or "qwen3.5-9b")[:80]

    if demande.get("mode") == "bureau":
        cle_moteur = demande.get("moteur") or "auto"
        if cle_moteur == "auto":
            cle_moteur = ia_automatique()
        if cle_moteur not in NOMS:
            raise ValueError("Choisis l'IA qui fait parler le desk.")
        analyse = {
            "id": identifiant, "type": "bureau", "ticker": ticker, "ticker_saisi": ticker,
            "date": date.today().strftime("%Y-%m-%d"), "moteur": cle_moteur, "etat": "en_cours",
            "etape": "Préparation", "debut": time.time(), "limite": time.time() + LIMITE_S,
            "appels": 0, "donnees": None, "decision": None,
            "specialistes": {k: {"nom": n, "etat": "attente"} for k, n in SPECIALISTES.items()},
            "_processus": [],
        }
        ANALYSES[identifiant] = analyse
        threading.Thread(target=executer_bureau, args=(analyse, modele_local), daemon=True).start()
        logging.info("desk %s lancé avec %s", identifiant, cle_moteur)
        return identifiant

    moteurs = [m for m in demande.get("moteurs", []) if m in NOMS]
    if not moteurs:
        raise ValueError("Choisis au moins une IA.")
    analystes = [a for a in demande.get("analystes", []) if a in ("market", "social", "news", "fundamentals")]
    if not analystes:
        raise ValueError("Choisis au moins un analyste.")
    analyse = {
        "id": identifiant,
        "type": "firme",
        "ticker": ticker,
        "ticker_saisi": ticker,
        "date": date.today().strftime("%Y-%m-%d"),
        "analystes": analystes,
        "etat": "en_cours",
        "debut": time.time(),
        "limite": time.time() + LIMITE_S,
        "moteurs": {m: {"etat": "attente", "nom": NOMS[m], "faits": [], "rapports": [], "llm_calls": 0} for m in moteurs},
        "synthese": None,
        "consensus": None,
        "_processus": [],
    }
    ANALYSES[identifiant] = analyse
    threading.Thread(target=executer_analyse, args=(analyse, modele_local), daemon=True).start()
    logging.info("analyse %s lancée : %s", identifiant, moteurs)
    return identifiant


# ---------------------------------------------------------------- serveur web


class Gestionnaire(BaseHTTPRequestHandler):
    def log_message(self, *args):  # pas de bruit dans la console
        pass

    def envoyer(self, code, contenu, type_contenu="application/json; charset=utf-8"):
        if not isinstance(contenu, (bytes, bytearray)):
            contenu = json.dumps(contenu, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", type_contenu)
        self.send_header("Content-Length", str(len(contenu)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(contenu)

    def corps(self):
        longueur = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(longueur) or b"{}") if longueur else {}

    def origine_locale(self):
        """Refuse les requêtes envoyées par d'autres sites ouverts dans le navigateur."""
        origine = self.headers.get("Origin")
        return origine in (None, f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}")

    def relayer_lmstudio(self, methode):
        """Relais vers LM Studio : on lui demande de répondre SANS « réfléchir » (comme Jarvis),
        ce qui divise le temps de chaque réponse. Les moteurs passent par ici au lieu d'aller directement sur 1234."""
        suite = self.path[len("/lmstudio/v1"):]
        corps, donnees, effort = None, None, False
        if methode == "POST":
            corps = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            try:
                donnees = json.loads(corps or b"{}")
            except ValueError:
                donnees = None
            if isinstance(donnees, dict) and suite.startswith("/chat/completions"):
                donnees.setdefault("max_tokens", 3000)  # évite les réponses sans fin
                if "qwen" in str(donnees.get("model", "")).lower():
                    for message in reversed(donnees.get("messages") or []):
                        if message.get("role") == "user" and isinstance(message.get("content"), str):
                            if "/no_think" not in message["content"]:
                                message["content"] += " /no_think"
                            break
                if not LMSTUDIO_SANS_REFLEXION["refuse"]:
                    donnees["reasoning_effort"] = "none"
                    effort = True
                corps = json.dumps(donnees).encode("utf-8")

        def appeler(contenu):
            requete = urllib.request.Request(URL_LMSTUDIO + suite, data=contenu, method=methode,
                                             headers={"Content-Type": "application/json"})
            try:
                return urllib.request.urlopen(requete, timeout=900)
            except urllib.error.HTTPError as erreur:
                return erreur

        try:
            reponse = appeler(corps)
            if getattr(reponse, "code", 200) == 400 and effort:
                # LM Studio refuse « reasoning_effort » : on réessaie sans (le /no_think suffit pour Qwen)
                donnees.pop("reasoning_effort", None)
                nouvelle = appeler(json.dumps(donnees).encode("utf-8"))
                if getattr(nouvelle, "code", 200) < 400:
                    LMSTUDIO_SANS_REFLEXION["refuse"] = True
                    logging.info("LM Studio refuse reasoning_effort : on s'en passe.")
                reponse = nouvelle
        except Exception as erreur:
            return self.envoyer(502, {"error": {"message": f"LM Studio ne répond pas ({erreur})"}})
        self.send_response(getattr(reponse, "code", 200))
        self.send_header("Content-Type", reponse.headers.get("Content-Type", "application/json"))
        self.send_header("Connection", "close")
        self.end_headers()
        while True:
            morceau = reponse.read(8192)
            if not morceau:
                break
            self.wfile.write(morceau)
            self.wfile.flush()
        return None

    def do_GET(self):
        chemin = unquote(urlparse(self.path).path)
        if chemin.startswith("/lmstudio/v1/"):
            return self.relayer_lmstudio("GET")
        if chemin in ("/", "/index.html"):
            return self.envoyer(200, (ICI / "index.html").read_bytes(), "text/html; charset=utf-8")
        if chemin == "/favicon.ico":
            return self.envoyer(200, (ICI / "salle.ico").read_bytes(), "image/x-icon")
        if chemin.startswith("/static/"):
            cible = (ICI / "static" / Path(chemin).name).resolve()
            types = {".woff2": "font/woff2", ".js": "text/javascript; charset=utf-8"}
            if cible.is_file() and cible.suffix in types:
                return self.envoyer(200, cible.read_bytes(), types[cible.suffix])
            return self.envoyer(404, {"erreur": "Fichier introuvable."})
        if chemin == "/api/salle":  # permet de reconnaître la salle parmi les autres logiciels
            return self.envoyer(200, {"salle": True})
        if chemin == "/api/etat":
            cles = lire_cles()
            lm = etat_lmstudio()
            en_cours = next((a["id"] for a in ANALYSES.values() if a["etat"] != "fini"), None)
            return self.envoyer(
                200,
                {
                    "lmstudio": {**lm, "outil": LMS.exists()},
                    "gemini": {"cle": bool(cles.get(CLES["gemini"]))},
                    "groq": {"cle": bool(cles.get(CLES["groq"]))},
                    "nvidia": {"cle": bool(cles.get(CLES["nvidia"]))},
                    "deepseek": {"cle": bool(cles.get(CLES["deepseek"]))},
                    "en_cours": en_cours,
                },
            )
        if chemin == "/api/historique":
            return self.envoyer(200, charger_historique())
        if chemin.startswith("/api/resume/"):
            identifiant = chemin.rsplit("/", 1)[-1]
            analyse = ANALYSES.get(identifiant)
            if analyse is None:
                fichier = RAPPORTS / Path(identifiant).name / "comparaison.json"
                if not fichier.exists():
                    return self.envoyer(404, {"erreur": "Analyse introuvable."})
                analyse = json.loads(fichier.read_text(encoding="utf-8"))
            with VERROU:
                texte = resume_texte(analyse)
            return self.envoyer(200, {"id": identifiant, "fini": analyse.get("etat") == "fini", "texte": texte,
                                      "adresse": f"http://127.0.0.1:{PORT}/"})
        if chemin.startswith("/api/analyse/"):
            identifiant = chemin.rsplit("/", 1)[-1]
            analyse = ANALYSES.get(identifiant)
            if analyse:
                with VERROU:
                    contenu = json.dumps(public(analyse), ensure_ascii=False).encode("utf-8")
                return self.envoyer(200, contenu)
            fichier = RAPPORTS / Path(identifiant).name / "comparaison.json"
            if fichier.exists():
                return self.envoyer(200, fichier.read_bytes())
            return self.envoyer(404, {"erreur": "Analyse introuvable."})
        if chemin.startswith("/rapports/"):
            cible = (RAPPORTS / chemin[len("/rapports/"):]).resolve()
            if RAPPORTS.resolve() in cible.parents and cible.is_file():
                types = {".html": "text/html; charset=utf-8", ".json": "application/json; charset=utf-8", ".md": "text/plain; charset=utf-8"}
                return self.envoyer(200, cible.read_bytes(), types.get(cible.suffix, "application/octet-stream"))
            return self.envoyer(404, {"erreur": "Fichier introuvable."})
        return self.envoyer(404, {"erreur": "Page introuvable."})

    def do_POST(self):
        if not self.origine_locale():
            return self.envoyer(403, {"erreur": "Interdit."})
        chemin = urlparse(self.path).path
        if chemin.startswith("/lmstudio/v1/"):
            return self.relayer_lmstudio("POST")
        try:
            if chemin == "/api/lancer":
                return self.envoyer(200, {"id": nouvelle_analyse(self.corps())})
            if chemin == "/api/commande":  # commandes du téléphone relayées par Jarvis (/contrat, /pause...)
                import commandes

                demande = self.corps()
                texte = commandes.executer(str(demande.get("commande", ""))[:20], str(demande.get("args", ""))[:200])
                return self.envoyer(200, {"texte": texte})
            if chemin == "/api/arreter-analyse":
                for analyse in ANALYSES.values():
                    if analyse["etat"] != "fini":
                        analyse["annulee"] = True
                        for processus in analyse["_processus"]:
                            processus.kill()
                return self.envoyer(200, {"ok": True})
            if chemin == "/api/ouvrir-cles":
                if os.name == "nt":
                    subprocess.Popen(["notepad.exe", str(FICHIER_CLES)])
                return self.envoyer(200, {"ok": True})
            if chemin == "/api/ouvrir-dossier":
                if os.name == "nt":
                    os.startfile(str(RACINE))  # noqa: S606 (ouvre l'explorateur Windows)
                return self.envoyer(200, {"ok": True})
            if chemin == "/api/demarrer-lmstudio":
                modele = str(self.corps().get("modele") or "qwen3.5-9b")[:80]
                lancer_lms("server", "start", delai=60)
                return self.envoyer(200, {"ok": etat_lmstudio()["serveur"], "modele": modele})
            if chemin == "/api/eteindre":
                # on arrête aussi les analyses en cours (sinon elles continueraient à tourner sur la carte graphique)
                for analyse in ANALYSES.values():
                    for processus in analyse.get("_processus", []):
                        if processus.poll() is None:
                            processus.kill()
                self.envoyer(200, {"ok": True})
                threading.Timer(0.5, lambda: os._exit(0)).start()
                return None
        except ValueError as erreur:
            return self.envoyer(400, {"erreur": str(erreur)})
        except Exception as erreur:
            logging.exception("POST %s", chemin)
            return self.envoyer(500, {"erreur": str(erreur)})
        return self.envoyer(404, {"erreur": "Action inconnue."})


class ServeurExclusif(ThreadingHTTPServer):
    """Serveur qui refuse de partager son port avec un autre logiciel (comme Jarvis)."""

    # Windows : port exclusif (personne ne peut s'y greffer) ; ailleurs : réutilisation normale
    allow_reuse_address = os.name != "nt"

    def server_bind(self):
        import socket

        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def est_la_salle(port):
    """Vérifie que ce qui répond sur ce port est bien la salle (et pas Jarvis)."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/salle", timeout=2) as reponse:
            return json.loads(reponse.read().decode("utf-8")).get("salle") is True
    except Exception:
        return False


def personne_n_ecoute(port):
    """True si rien ne répond sur ce port (il est juste en train de se libérer après un arrêt)."""
    import socket

    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) != 0


def main():
    global PORT
    serveur = None
    for port in range(PORT, PORT + 10):
        try:
            try:
                serveur = ServeurExclusif(("127.0.0.1", port), Gestionnaire)
            except OSError:
                # Juste après « Éteindre la salle », Windows garde le port quelques instants :
                # on attend un peu pour garder la même adresse (utile pour le téléphone)
                if port != PORT or not personne_n_ecoute(port):
                    raise
                for _ in range(15):
                    time.sleep(2)
                    try:
                        serveur = ServeurExclusif(("127.0.0.1", port), Gestionnaire)
                        break
                    except OSError:
                        continue
                if serveur is None:
                    raise
            PORT = port
            break
        except OSError:
            if est_la_salle(port):  # la salle est déjà ouverte : on affiche juste la page
                webbrowser.open(f"http://127.0.0.1:{port}")
                return
            logging.info("Port %s occupé par un autre logiciel, on essaie le suivant", port)
    if serveur is None:
        logging.error("Aucun port libre entre %s et %s", PORT, PORT + 9)
        return
    adresse = f"http://127.0.0.1:{PORT}"
    logging.info("Salle des marchés ouverte sur %s", adresse)
    if "--sans-navigateur" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(adresse)).start()
    serveur.serve_forever()


if __name__ == "__main__":
    main()
