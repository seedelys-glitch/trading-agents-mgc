# -*- coding: utf-8 -*-
"""
Moteur d'une analyse TradingAgents pour UNE IA (LM Studio, Gemini, Groq, NVIDIA ou DeepSeek).

Lancé par serveur.py, un processus par IA, pour que les 3 tournent en parallèle
sans se marcher dessus. Il écrit sa progression sur la sortie standard, une ligne
JSON par événement, que le serveur relaie à l'interface.

Deux modes :
  python moteur.py --moteur gemini --ticker NVDA --date 2026-10-14 --analystes market,news --sortie DOSSIER
  python moteur.py --synthese FICHIER.json --moteur lmstudio [--modele qwen3.5-9b]
"""

import argparse
import json
import os
import sys
import time
import traceback
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
os.chdir(RACINE)  # le fichier .env de TradingAgents est lu depuis ce dossier

# Réglages de chaque IA : modèle « quick » (fait 90 % du travail) et « deep » (les 2 managers)
MOTEURS = {
    "lmstudio": {
        "nom": "LM Studio",
        "fournisseur": "openai_compatible",
        # la salle relaie LM Studio pour couper la « réflexion » (bien plus rapide) ; sinon accès direct
        "url": os.environ.get("SALLE_LMSTUDIO_PROXY") or "http://localhost:1234/v1",
        "quick": "qwen3.5-9b",
        "deep": "qwen3.5-9b",
        "cle": None,
        "essais": 2,
    },
    "gemini": {
        "nom": "Gemini",
        "fournisseur": "google",
        "url": None,
        "quick": "gemini-3.5-flash-lite",
        "deep": "gemini-3.8-flash",
        "cle": "GOOGLE_API_KEY",
        "essais": 8,  # le quota gratuit limite les appels par minute : on réessaie
    },
    "groq": {
        "nom": "Groq",
        "fournisseur": "groq",
        "url": None,
        "quick": "openai/gpt-oss-20b",
        "deep": "openai/gpt-oss-120b",
        "cle": "GROQ_API_KEY",
        "essais": 6,  # gratuit : environ 1 000 appels par jour, on réessaie si la minute est pleine
    },
    "nvidia": {
        "nom": "NVIDIA",
        # fournisseur « nvidia » de TradingAgents : même format OpenAI, lit NVIDIA_API_KEY (LM Studio n'est pas concerné)
        "fournisseur": "nvidia",
        "url": "https://integrate.api.nvidia.com/v1",
        # vitesses mesurées le 19/10 : gpt-oss-20b < 1 s ; Nemotron 3 Super ≈ 10 s ; DeepSeek / Gemma saturés
        "quick": "openai/gpt-oss-20b",
        "deep": "nvidia/nemotron-3-super-120b-a12b",
        "cle": "NVIDIA_API_KEY",
        "essais": 6,  # gratuit : environ 1 000 crédits et 40 appels par minute, on réessaie si la minute est pleine
    },
    "deepseek": {
        "nom": "DeepSeek",
        "fournisseur": "deepseek",
        "url": None,
        "quick": "deepseek-flash",
        "deep": "deepseek-flash",
        "cle": "DEEPSEEK_API_KEY",
        "essais": 3,
    },
}

# Les 5 étages de la firme, dans l'ordre
ETAGES = ["analystes", "debat", "trader", "risque", "gerant"]


def emettre(**evenement):
    """Envoie un événement au serveur (une ligne JSON)."""
    sys.stdout.write(json.dumps(evenement, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def message_clair(erreur):
    """Traduit une erreur technique en phrase compréhensible."""
    if type(erreur) is RuntimeError:  # nos propres messages, déjà écrits en français clair
        return str(erreur)
    texte = f"{type(erreur).__name__}: {erreur}"
    bas = texte.lower()
    if "resource_exhausted" in bas or "429" in bas or "rate limit" in bas or "quota" in bas:
        return "Quota gratuit atteint (trop d'appels par minute ou par jour). Réessaie plus tard."
    if "insufficient balance" in bas or "402" in bas:
        return "Solde vide chez ce fournisseur : il faut recharger le compte."
    if "api key" in bas or "api_key" in bas or "401" in bas or "unauthenticated" in bas or "permission_denied" in bas:
        return "Clé refusée par le fournisseur : vérifie-la dans le fichier des clés."
    if "context" in bas and ("length" in bas or "size" in bas or "exceed" in bas):
        return "Le modèle local manque de mémoire de contexte. Relance : la salle le recharge avec plus de contexte."
    if "connection" in bas and ("refused" in bas or "error" in bas):
        return "Le fournisseur ne répond pas (LM Studio éteint ou pas d'internet)."
    if "not found" in bas and "model" in bas:
        return "Modèle introuvable chez ce fournisseur."
    return texte[:300]


def texte_du_message(msg):
    """Récupère le texte d'une réponse de modèle, quel que soit son format."""
    contenu = getattr(msg, "content", msg)
    if isinstance(contenu, str):
        return contenu
    if isinstance(contenu, list):
        return "\n".join(
            b if isinstance(b, str) else b.get("text", "")
            for b in contenu
            if isinstance(b, str) or (isinstance(b, dict) and b.get("type") == "text")
        )
    return str(contenu)


def lire_lignes(reponse, cles):
    """Lit des lignes « CLE: texte » ; une clé peut revenir plusieurs fois."""
    resultat = {c: [] for c in cles}
    for ligne in reponse.splitlines():
        tete, sep, reste = ligne.partition(":")
        if not sep:
            continue
        tete = tete.strip().strip("*#- ").upper().replace("É", "E").replace("À", "A")
        reste = reste.strip().strip("*").strip()
        if tete in resultat and reste:
            resultat[tete].append(reste)
    return resultat


def construire_config(moteur, modele_local=None):
    """Configuration TradingAgents pour une IA donnée."""
    from tradingagents.default_config import build_default_config

    reglage = MOTEURS[moteur]
    config = build_default_config()
    config["llm_provider"] = reglage["fournisseur"]
    config["backend_url"] = reglage["url"]
    config["quick_think_llm"] = reglage["quick"]
    config["deep_think_llm"] = reglage["deep"]
    if moteur == "lmstudio" and modele_local:  # modèle choisi dans l'interface
        config["quick_think_llm"] = config["deep_think_llm"] = modele_local
    config["max_debate_rounds"] = 1
    config["max_risk_discuss_rounds"] = 1
    config["llm_max_retries"] = reglage["essais"]
    config["output_language"] = os.environ.get("TRADINGAGENTS_OUTPUT_LANGUAGE") or "French"
    return config


def verifier_acces(moteur):
    """Vérifie la clé ou le serveur local avant de dépenser quoi que ce soit."""
    reglage = MOTEURS[moteur]
    if reglage["cle"] and not os.environ.get(reglage["cle"]):
        raise RuntimeError(f"Clé {reglage['cle']} absente : ouvre le fichier des clés et colle-la.")
    if moteur == "lmstudio":
        try:
            urllib.request.urlopen(reglage["url"] + "/models", timeout=5).read()
        except Exception:
            raise RuntimeError("LM Studio ne répond pas sur ce PC : ouvre LM Studio puis relance.")


def etages_faits(etat):
    """Liste des étages terminés d'après l'état de la firme."""
    faits = []
    rapports = [k for k in ("market_report", "sentiment_report", "news_report", "fundamentals_report") if etat.get(k)]
    debat = etat.get("investment_debate_state") or {}
    if etat.get("investment_plan") or debat.get("bull_history") or debat.get("bear_history"):
        faits.append("analystes")
    if etat.get("investment_plan"):
        faits.append("debat")
    if etat.get("trader_investment_plan"):
        faits.append("trader")
    if etat.get("final_trade_decision"):
        faits += ["risque", "gerant"]
    return faits, rapports


def extraire_sections(etat):
    """Les textes de chaque étage, pour la comparaison côte à côte."""
    debat = etat.get("investment_debate_state") or {}
    risque = etat.get("risk_debate_state") or {}
    parties_risque = [
        ("Profil agressif", risque.get("aggressive_history", "")),
        ("Profil prudent", risque.get("conservative_history", "")),
        ("Profil neutre", risque.get("neutral_history", "")),
    ]
    return {
        "technique": etat.get("market_report", ""),
        "sentiment": etat.get("sentiment_report", ""),
        "news": etat.get("news_report", ""),
        "fondamental": etat.get("fundamentals_report", ""),
        "haussier": debat.get("bull_history", ""),
        "baissier": debat.get("bear_history", ""),
        "arbitre": etat.get("investment_plan", ""),
        "trader": etat.get("trader_investment_plan", ""),
        "risque": "\n\n".join(f"### {titre}\n{texte}" for titre, texte in parties_risque if texte),
        "decision": etat.get("final_trade_decision", ""),
    }


def resumer(llm, sections):
    """Un seul appel : thèse haussière, thèse baissière et raison de la décision, en une phrase chacune."""
    consigne = (
        "Résume en français, une phrase courte par ligne, uniquement ces 3 lignes :\n"
        "HAUSSIER: <le meilleur argument pour acheter>\n"
        "BAISSIER: <le meilleur argument contre>\n"
        "RAISON: <pourquoi le gérant a pris sa décision finale>\n\n"
        f"=== ARGUMENT HAUSSIER ===\n{sections['haussier'][:5000]}\n\n"
        f"=== ARGUMENT BAISSIER ===\n{sections['baissier'][:5000]}\n\n"
        f"=== DÉCISION DU GÉRANT ===\n{sections['decision'][:4000]}"
    )
    lignes = lire_lignes(texte_du_message(llm.invoke(consigne)), ["HAUSSIER", "BAISSIER", "RAISON"])
    return {k.lower(): (v[0] if v else "") for k, v in lignes.items()}


def analyser(args):
    """Une analyse complète pour une IA, avec progression en direct."""
    from cli.prompts import detect_asset_type, normalize_ticker_symbol
    from cli.stats_handler import StatsCallbackHandler
    from tradingagents.agents.rating import run_rating
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    moteur = args.moteur
    verifier_acces(moteur)
    config = construire_config(moteur, args.modele)
    ticker = normalize_ticker_symbol(args.ticker)
    type_actif = str(detect_asset_type(ticker))
    analystes = [a for a in args.analystes.split(",") if a]
    if type_actif == "crypto":
        analystes = [a for a in analystes if a != "fundamentals"] or ["market"]

    stats = StatsCallbackHandler()
    emettre(type="debut", ticker=ticker, modele_quick=config["quick_think_llm"], modele_deep=config["deep_think_llm"])

    graphe = TradingAgentsGraph(selected_analysts=analystes, debug=False, config=config, callbacks=[stats])
    etat_initial = graphe.create_run_state(ticker, args.date, type_actif)
    params = graphe.propagator.get_graph_args(callbacks=[stats])

    etat_final, derniers, dernier_envoi = {}, None, 0.0
    for _messages, morceau in graphe.stream_run(etat_initial, **params):
        if morceau:
            etat_final.update(morceau)
        faits, rapports = etages_faits(etat_final)
        signature = (tuple(faits), tuple(rapports))
        maintenant = time.time()
        if signature != derniers or maintenant - dernier_envoi > 2:
            derniers, dernier_envoi = signature, maintenant
            emettre(type="progression", faits=faits, rapports=rapports, **stats.get_stats())

    graphe.record_decision(ticker, args.date, etat_final)
    verdict = run_rating(etat_final)

    sortie = Path(args.sortie)
    sortie.mkdir(parents=True, exist_ok=True)
    graphe.save_reports(etat_final, ticker, sortie / "rapport", html=True)
    sections = extraire_sections(etat_final)
    (sortie / "sections.json").write_text(json.dumps(sections, ensure_ascii=False), encoding="utf-8")

    try:
        resume = resumer(graphe.quick_thinking_llm, sections)
    except Exception as erreur:  # le résumé est un bonus : l'analyse reste valable sans
        print(traceback.format_exc(), file=sys.stderr)
        resume = {"haussier": "", "baissier": "", "raison": f"Résumé indisponible : {message_clair(erreur)}"}

    emettre(
        type="fin",
        verdict=verdict,
        resume=resume,
        faits=ETAGES,
        **stats.get_stats(),
    )


def synthese(args):
    """Compare les IA entre elles : points communs, divergences, chiffres à vérifier."""
    from tradingagents.llm_clients.factory import create_tier_client

    donnees = json.loads(Path(args.synthese).read_text(encoding="utf-8"))
    verifier_acces(args.moteur)
    config = construire_config(args.moteur, args.modele)
    llm = create_tier_client(config, "quick").get_llm()

    blocs = []
    for nom, info in donnees["moteurs"].items():
        sections = info.get("sections") or {}
        blocs.append(
            f"=== {nom} : verdict {info.get('verdict')} ===\n"
            f"Pour : {sections.get('haussier', '')[:2500]}\n"
            f"Contre : {sections.get('baissier', '')[:2500]}\n"
            f"Décision : {sections.get('decision', '')[:2500]}"
        )
    consigne = (
        f"Plusieurs IA ont analysé {donnees['ticker']} le {donnees['date']}. Compare leurs analyses. "
        "Réponds en français, phrases courtes, uniquement avec des lignes de ce format :\n"
        "COMMUN: <un point sur lequel elles sont d'accord> (3 lignes maximum)\n"
        "DIVERGENCE: <un point où elles ne sont pas d'accord, en nommant les IA> (3 lignes maximum)\n"
        "VERIFIER: <un chiffre ou un fait cité à vérifier à la source> (3 lignes maximum)\n"
        "CLE: <l'argument baissier le plus important, toutes IA confondues, en une phrase>\n\n"
        + "\n\n".join(blocs)
    )
    lignes = lire_lignes(texte_du_message(llm.invoke(consigne)), ["COMMUN", "DIVERGENCE", "VERIFIER", "CLE"])
    emettre(
        type="synthese",
        communs=lignes["COMMUN"][:3],
        divergences=lignes["DIVERGENCE"][:3],
        a_verifier=lignes["VERIFIER"][:3],
        baissier_cle=(lignes["CLE"] or [""])[0],
        par=MOTEURS[args.moteur]["nom"],
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--moteur", required=True, choices=sorted(MOTEURS))
    parser.add_argument("--ticker")
    parser.add_argument("--date")
    parser.add_argument("--analystes", default="market,social,news,fundamentals")
    parser.add_argument("--sortie")
    parser.add_argument("--modele")
    parser.add_argument("--synthese")
    args = parser.parse_args()
    try:
        if args.synthese:
            synthese(args)
        else:
            analyser(args)
    except Exception as erreur:
        print(traceback.format_exc(), file=sys.stderr)
        emettre(type="erreur", message=message_clair(erreur))
        sys.exit(1)


if __name__ == "__main__":
    main()
