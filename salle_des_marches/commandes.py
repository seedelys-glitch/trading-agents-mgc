# -*- coding: utf-8 -*-
"""
Commandes du téléphone (Telegram, relayées par Jarvis -> POST /api/commande) : réponses courtes, sans IA.

  /contrat   contrat MGC actif, suivant, bascule, restriction de rollover
  /news      annonces USD des 48 h et blocages en cours
  /regime    régime de marché de l'or (calcul déterministe, 2 s environ)
  /stats     nombre d'analyses par statut, résultats notés
  /memoire   les dernières analyses
  /resultat  /resultat <id> <win|loss> <prix> : note le résultat d'une analyse suivie
  /pause     coupe immédiatement toute nouvelle configuration exploitable ; /resume la rétablit
  /bulletin  bulletin de notes des agents (ce que le gold a fait 4 h après chaque desk)
  /liquidite plus hauts / plus bas d'Asie, de Londres et de la veille : intacts, balayés ou cassés
  /topstep   règles du compte Topstep : marge avant la perte max, objectif, consistance
  /solde     /solde 50340 : note le solde du compte Topstep (le dernier du jour = fin de journée)
/analyse et /express sont gérés par Jarvis (il lance le desk et envoie le plan à la fin).
"""

import datetime as dt
import json
from pathlib import Path

from mgc import config as cfg
from mgc.contrats import ContractManager
from mgc.instrument import sur_grille

RAPPORTS = Path(__file__).resolve().parent.parent / "rapports" / "salle"
BASE = None  # None = rapports\salle\analyste.sqlite (les tests en donnent une autre)
AIDE = ("Commandes : /analyse (lance le desk gold), /express (desk express ~5 min), /contrat, /news, /regime, "
        "/stats, /memoire, /bulletin, /liquidite, /topstep, /solde <montant>, /resultat <id> <win|loss> <prix>, "
        "/pause, /resume.")


def _historique():
    try:
        return json.loads((RAPPORTS / "historique.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def contrat(config, maintenant):
    e = ContractManager(config).etat(maintenant)
    texte = (f"Contrat actif : {e['contrat']} (suivant : {e['suivant']}). Dernier jour de négociation : "
             f"{e['dernier_jour_negociation']} ({e['jours_ouvres_avant_fin']} jours ouvrés). Bascule estimée : "
             f"{e['bascule_estimee']} (dans {e['jours_ouvres_avant_bascule']} jours ouvrés).")
    return texte + (f" {e['motif_restriction']}" if e["restriction_rollover"] else " Pas de restriction de rollover.")


def news(config, maintenant):
    import calculs

    c = calculs.calendrier(maintenant, config)
    if not c.get("disponible"):
        return f"Calendrier indisponible : {c.get('raison')}"
    lignes = [f"• {a['quand']} : {a['titre']} ({a['impact']}{', réunion FOMC' if a['genre'] == 'reunion_fomc' else ''})"
              for a in c["annonces_48h"]] or ["Aucune annonce USD forte ou moyenne dans les 48 h."]
    lignes.append("Bloqué maintenant : " + " ".join(c["blocages"]) if c["blocages"] else "Rien ne bloque en ce moment.")
    if c["fomc_aujourdhui"]:
        lignes.append("Aujourd'hui : jour de réunion du FOMC, journée bloquée (règle personnelle).")
    return "\n".join(lignes)


def regime_actuel(config, maintenant):
    import calculs
    from mgc import regime, sources

    code = ContractManager(config).etat(maintenant)["contrat"]
    d1 = sources.depuis_yahoo(sources.yahoo_brut(f"{code}.CMX", "2y", "1d"), quotidien=True)
    tendance = {}
    if len(d1) >= 210:
        e = calculs.ema(d1["c"], 200)
        tendance = {"ema200_D1": {"prix": "au-dessus" if d1["c"].iloc[-1] > e.iloc[-1] else "en dessous",
                                  "pente": "montante" if e.iloc[-1] > e.iloc[-21] else "descendante"}}
    r = regime.detecter({"macro": calculs.macro("MGC=F"), "tendance": tendance}, maintenant)
    return f"Régime : {r['regime']} (confiance {r['confiance']}). {r['justification']}"


def _base():
    from mgc import base

    return base.ouvrir(BASE) if BASE else base.ouvrir()


def stats():
    from mgc import journal_jarvis
    from mgc import stats as st

    conn = _base()
    try:
        texte = st.texte(conn)
    finally:
        conn.close()
    return texte + "\n" + journal_jarvis.resume()


def memoire(nombre=5):
    conn = _base()
    try:
        lignes = conn.execute("SELECT a.id, a.debut, a.contrat, a.statut, r.issue FROM analyses a LEFT JOIN resultats r "
                              "ON r.analyse_id = a.id ORDER BY a.debut DESC LIMIT ?", (nombre,)).fetchall()
    finally:
        conn.close()
    if not lignes:
        hist = [h for h in _historique() if h.get("type") == "bureau"][:nombre]
        if not hist:
            return "Aucune analyse enregistrée pour l'instant."
        return "\n".join(f"• {h['date']} {h.get('heure', '')} · {h.get('ticker')} · {h.get('statut') or h.get('decision')} · {h['id']}"
                         for h in hist)
    return "\n".join(f"• {(l['debut'] or '')[:16].replace('T', ' ')} UTC · {l['contrat']} · {l['statut']}"
                     f"{' · résultat ' + l['issue'] if l['issue'] else ''} · {l['id']}" for l in lignes)


def resultat(args, maintenant, config):
    from mgc import base

    morceaux = args.split()
    if len(morceaux) != 3 or morceaux[1].lower() not in ("win", "loss"):
        return "Format : /resultat <id> <win|loss> <prix>, par exemple /resultat 20261020-152000-XAUUSD win 4215.3"
    ident, issue, prix = Path(morceaux[0]).name, morceaux[1].lower(), morceaux[2].replace(",", ".")
    fichier = RAPPORTS / ident / "comparaison.json"
    if not fichier.exists():
        return f"Analyse {ident} introuvable : vérifie l'identifiant (voir /memoire)."
    try:
        prix = float(prix)
    except ValueError:
        return f"Prix illisible : {morceaux[2]}"
    if prix <= 0 or not sur_grille(prix):
        return f"Prix {prix} impossible pour le MGC (échelon de 0,10)."
    conn = _base()
    try:
        if conn.execute("SELECT 1 FROM analyses WHERE id = ?", (ident,)).fetchone() is None:
            # analyse antérieure à la base : on la range d'abord depuis son rapport
            base.enregistrer_analyse(conn, json.loads(fichier.read_text(encoding="utf-8")))
        calcul = base.enregistrer_resultat(conn, ident, issue, prix, config)
    finally:
        conn.close()
    texte = f"Noté : analyse {ident}, {'gagnant' if issue == 'win' else 'perdant'}, sortie à {prix}."
    if calcul["r_multiple"] is not None:
        texte += f" Soit {calcul['pnl_points']:+g} points, {calcul['r_multiple']:+g} R, {calcul['pnl_usd_net']:+.2f} $ net."
    return texte


def bulletin_agents():
    from mgc import bulletin

    return bulletin.resume(bulletin.lire())


def liquidite_actuelle(config, maintenant):
    """Agent Liquidité sans IA : niveaux d'Asie, de Londres et de la veille sur le contrat actif (Yahoo)."""
    import calculs
    from mgc import sources

    code = ContractManager(config).etat(maintenant)["contrat"]
    m5 = sources.depuis_yahoo(sources.yahoo_brut(f"{code}.CMX", "5d", "5m"))
    d1 = sources.depuis_yahoo(sources.yahoo_brut(f"{code}.CMX", "1mo", "1d"), quotidien=True)
    h1 = sources.depuis_yahoo(sources.yahoo_brut(f"{code}.CMX", "1mo", "1h"))
    a = float(calculs.atr(h1).iloc[-1]) if len(h1) > 20 else None
    liq = calculs.liquidite_sessions({"M5": m5, "D1": d1}, a)
    return texte_liquidite(liq)


def texte_liquidite(liq):
    if not liq.get("disponible"):
        return f"Liquidité : {liq.get('raison')}"
    lignes = [f"Liquidité (prix {liq['prix']}, sessions {liq['sessions_paris']}) :"]
    for p in liq["niveaux"]:
        lignes.append(f"• {p['nom']} {p['prix']} : {p['etat']}" + (f" ({p['quand']})" if p.get("quand") else ""))
    for cle, mot in (("liquidite_intacte_au_dessus", "au-dessus"), ("liquidite_intacte_en_dessous", "en dessous")):
        p = liq.get(cle)
        if p:
            lignes.append(f"Plus proche liquidité intacte {mot} : {p['nom']} {p['prix']}.")
    d = liq.get("derniere_liquidite_prise")
    if d:
        lignes.append(f"Dernière liquidité prise : {d['nom']} {d['prix']} ({d['quand']}).")
    return "\n".join(lignes)


def pause(active):
    fichier = cfg.FICHIER_PAUSE
    if active:
        fichier.parent.mkdir(parents=True, exist_ok=True)
        fichier.write_text(dt.datetime.now().isoformat(timespec="seconds"), encoding="utf-8")
        return "Pause d'urgence ACTIVE : plus aucune configuration exploitable, et le desk s'arrête avant l'IA. /resume pour reprendre."
    fichier.unlink(missing_ok=True)
    return "Pause levée : le desk analyse de nouveau normalement."


def executer(commande, args="", maintenant=None, config=None):
    """Réponse texte à une commande. Les erreurs sont dites simplement, jamais de trace technique."""
    maintenant = maintenant or dt.datetime.now(dt.UTC)
    config = config or cfg.charger()
    commande = (commande or "").strip().lower().split("@")[0]
    try:
        if commande == "/contrat":
            return contrat(config, maintenant)
        if commande == "/news":
            return news(config, maintenant)
        if commande == "/regime":
            return regime_actuel(config, maintenant)
        if commande == "/stats":
            return stats()
        if commande == "/memoire":
            return memoire()
        if commande == "/resultat":
            return resultat(args, maintenant, config)
        if commande == "/bulletin":
            return bulletin_agents()
        if commande in ("/liquidite", "/liquidité"):
            return liquidite_actuelle(config, maintenant)
        if commande == "/topstep":
            from mgc import topstep

            return topstep.resume(config=config)
        if commande == "/solde":
            from mgc import topstep

            if not args.strip():
                return "Format : /solde 50340 (le solde actuel de ton compte Topstep)."
            import re

            nombre = re.search(r"\d[\d \u00a0\u202f.,]*", args)
            try:
                if not nombre:
                    raise ValueError(args)
                montant = re.sub(r"[ \u00a0\u202f]", "", nombre.group(0)).rstrip(".,")
                if re.fullmatch(r"\d{1,3}([.,]\d{3})+", montant):  # « 50.340 » ou « 50,340 » = cinquante mille
                    montant = re.sub(r"[.,]", "", montant)
                topstep.noter_solde(montant, solde_depart=config["capital_usd"])
            except ValueError:
                return f"Solde illisible : {args.strip()}. Exemple : /solde 50340"
            return "Solde noté. " + topstep.resume(config=config)
        if commande == "/pause":
            return pause(True)
        if commande == "/resume":
            return pause(False)
        return AIDE
    except Exception as erreur:  # réseau coupé, Yahoo indisponible...
        return f"La commande {commande} n'a pas abouti ({type(erreur).__name__}). Réessaie dans un moment."
