# -*- coding: utf-8 -*-
"""
Agent 17 (mentor) — retour sur les erreurs (31/10, règle de Jabran : « toujours s'améliorer, chercher ce qui a fait
qu'il y a eu des problèmes, des erreurs ou des ratés », pour l'université, le desk et Jarvis).

Une fois par jour (et juste avant la réunion de 21h30), le mentor relit les VRAIES erreurs :
  - université : missions en erreur, documents rejetés par l'auditeur (avec ses écarts), textes IA refusés ;
  - desk : lignes d'erreur des journaux rapports\\salle\\*.log (lecture seule) ;
  - Jarvis : lignes d'erreur de Jarvis\\jarvis.log (lecture seule).
Chaque erreur est rangée par cause ; une leçon est écrite (table lecons). L'agent concerné la relit avant sa
prochaine mission du même type (étape visible « relit ses leçons »). Si la mission réussit ensuite, la leçon passe
« appliquée » ; si la même erreur revient, elle passe « répétée », et à la 3e fois le directeur est prévenu.
Rien n'est corrigé dans le code ni chez Jarvis : les erreurs de programmation sont signalées (pour Claude) dans la
mémoire, dossier « a_ranger ».
"""

import datetime as dt
import hashlib
import re
import time
from pathlib import Path

from .. import agents, config, memoire

TYPE = "retour_erreurs"
AGENT = 17
TITRE = "Retour sur les erreurs du jour (leçons)"
PARAMS = {"heures": "période relue (24 par défaut)"}
INTERNE = True
LIRE_OCTETS = 1_500_000          # fin des journaux seulement (ils peuvent être gros)

# (motif sur le texte en minuscules, cause, leçon)
CAUSES = [
    (r"délai|timeout|timed out|delaidepasse", "le travail a pris trop de temps",
     "Découper le travail ou réduire la période, et vérifier que la source répond avant de lancer."),
    (r"urlerror|connection|getaddrinfo|réseau|reseau|injoignable|http error 5\d\d|429|ssl|winerror 100\d\d",
     "une source en ligne ne répondait pas (ou limite atteinte)",
     "Utiliser les données déjà gardées, réessayer plus tard, et ne jamais inventer à la place."),
    (r"pas assez|aucune bougie|0 bougie|insuffisant|trou|données manquantes|donnees manquantes|vide",
     "données manquantes ou trop courtes",
     "Contrôler les données avant d'analyser (agent 13) et écrire « pas assez de données » plutôt que de forcer."),
    (r"faux|écart|ecart|tolérance|tolerance|rejet", "un chiffre ne correspond pas au recalcul de l'auditeur",
     "Recalculer sur les mêmes bougies fermées avant d'envoyer, et citer la bougie et l'heure de chaque chiffre."),
    (r"charte|chiffres non vérifiés|chiffres non verifies", "un texte d'IA a été refusé",
     "Écrire seulement à partir des faits calculés, sans chiffre libre, en respectant la charte."),
    (r"unicode|encod|decode", "problème d'encodage des caractères",
     "Lire et écrire en UTF-8 en précisant l'encodage (et oem/replace pour les commandes Windows)."),
    (r"locked|occupé|occupe|permission|access is denied|accès refusé|winerror 32", "fichier ou base occupés",
     "Réessayer après une courte pause et ne pas écrire au même endroit en même temps."),
    (r"valueerror|typeerror|keyerror|attributeerror|indexerror|nameerror|zerodivision|traceback|access violation",
     "erreur de programmation", "À corriger dans le code : signalé à Claude (mémoire, dossier a_ranger)."),
]
_CAUSES = [(re.compile(m), c, l) for m, c, l in CAUSES]
_LIGNE_ERREUR = re.compile(r"\b(ERROR|CRITICAL|Traceback|PLANTAGE|Exception)\b")
_DATE = re.compile(r"^(\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d)")


def cause_et_lecon(texte):
    t = str(texte or "").lower()
    for motif, cause, lecon in _CAUSES:
        if motif.search(t):
            return cause, lecon
    return "cause encore inconnue", "Le mentor la met à l'ordre du jour de la réunion du soir pour en trouver la cause."


def normaliser(texte):
    """Même erreur = même empreinte, quels que soient les numéros, heures, chemins ou identifiants."""
    t = str(texte or "").lower()
    t = re.sub(r"[a-z]:\\[^\s'\"]+|/[\w./-]+", "<chemin>", t)
    t = re.sub(r"0x[0-9a-f]+|\d+([.,]\d+)?", "#", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()[:160]


def noter(base, equipe, agent, genre, quoi, exemple, maintenant=None):
    """Ajoute ou met à jour une leçon. Renvoie (id, nouvelle, fois)."""
    maintenant = maintenant or time.time()
    cause, lecon = cause_et_lecon(f"{quoi} {exemple}")
    empreinte = hashlib.sha1(f"{equipe}|{agent}|{genre}|{normaliser(exemple or quoi)}".encode("utf-8")).hexdigest()[:16]
    ex = memoire.masquer(str(exemple or ""))[:300]
    ligne = base.un("SELECT id, statut, fois, maj FROM lecons WHERE equipe=? AND empreinte=?", (equipe, empreinte))
    if ligne is None:
        ident = base.ecrire("INSERT INTO lecons(equipe, agent, type, empreinte, quoi, cause, lecon, exemple, cree, maj)"
                            " VALUES (?,?,?,?,?,?,?,?,?,?)",
                            (equipe, agent, genre or "", empreinte, quoi[:200], cause, lecon, ex, maintenant, maintenant))
        return ident, True, 1
    if maintenant - ligne["maj"] < 6 * 3600:     # déjà comptée aujourd'hui
        return ligne["id"], False, ligne["fois"]
    # revue un autre jour : l'erreur est revenue malgré la leçon
    base.ecrire("UPDATE lecons SET fois=fois+1, statut='repetee', exemple=?, maj=? WHERE id=?",
                (ex, maintenant, ligne["id"]))
    return ligne["id"], False, ligne["fois"] + 1


def _erreurs_universite(base, depuis):
    vues = []
    for m in base.lire("SELECT id, agent, type, titre, erreur FROM missions WHERE statut='erreur' AND COALESCE(fin, cree)>=?",
                       (depuis,)):
        vues.append(("universite", m["agent"], m["type"], f"Mission « {m['titre']} » en erreur", m["erreur"] or ""))
    for d in base.lire("SELECT d.id, d.agent, d.titre, m.type FROM documents d LEFT JOIN missions m ON m.id=d.mission"
                       " WHERE d.statut='rejete' AND d.cree>=?", (depuis - 6 * 3600,)):
        pv = base.un("SELECT donnees FROM documents WHERE genre='verification' AND titre=? ORDER BY id DESC LIMIT 1",
                     (f"Vérification du document {d['id']}",))
        info = (pv or {}).get("donnees") or {}
        faux = [e.get("quoi") for e in info.get("ecarts", []) if isinstance(e, dict)
                and e.get("ecart", 0) > 0.015]
        detail = "rejet : " + "; ".join([f"chiffre faux ({q})" for q in faux] + list(info.get("problemes", [])))
        vues.append(("universite", d["agent"], d["type"] or "", f"Document « {d['titre']} » rejeté par l'auditeur",
                     detail))
    for e in base.lire("SELECT agent, message FROM evenements WHERE genre='ia' AND niveau IN ('alerte','erreur')"
                       " AND ts>=?", (depuis,)):
        vues.append(("universite", e["agent"], "", "Texte d'IA refusé", e["message"]))   # type vide : relue avant toute mission
    return vues


def lignes_d_erreur(fichier, depuis):
    """Lignes d'erreur récentes d'un journal (lecture seule, fin du fichier)."""
    p = Path(fichier)
    try:
        if not p.is_file() or p.stat().st_mtime < depuis:
            return []
        with open(p, "rb") as f:
            f.seek(max(0, p.stat().st_size - LIRE_OCTETS))
            texte = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    sortie = []
    for ligne in texte.splitlines():
        if not _LIGNE_ERREUR.search(ligne):
            continue
        m = _DATE.match(ligne)
        if m:
            try:
                if dt.datetime.fromisoformat(m.group(1).replace(" ", "T")).timestamp() < depuis:
                    continue
            except ValueError:
                pass
        sortie.append(ligne.strip()[:300])
    return sortie


def _erreurs_externes(base, depuis):
    reg = config.charger(Path(base.fichier).parent)
    vues = []
    for f in sorted((config.RACINE / "rapports" / "salle").glob("*.log")):
        for ligne in lignes_d_erreur(f, depuis):
            vues.append(("desk", None, f.stem, f"Erreur du desk ({f.name})", ligne))
    jarvis = reg.get("memoire_jarvis") or ""
    if jarvis:
        for ligne in lignes_d_erreur(Path(jarvis) / "jarvis.log", depuis):
            vues.append(("jarvis", None, "jarvis", "Erreur de Jarvis", ligne))
    return vues


def analyser(base, heures=24.0, maintenant=None, externes=True):
    """Relit les erreurs de la période et écrit les leçons. Renvoie la liste des leçons touchées."""
    maintenant = maintenant or time.time()
    depuis = maintenant - heures * 3600
    vues = _erreurs_universite(base, depuis) + (_erreurs_externes(base, depuis) if externes else [])
    touchees, deja = [], set()
    for equipe, agent, genre, quoi, exemple in vues:
        ident, nouvelle, fois = noter(base, equipe, agent, genre, quoi, exemple, maintenant)
        if ident in deja:
            continue
        deja.add(ident)
        touchees.append({"id": ident, "nouvelle": nouvelle, "fois": fois, "equipe": equipe, "agent": agent})
    return touchees


def executer(ctx):
    heures = float(ctx.params.get("heures") or 24)
    ctx.etape("chercheur", f"Relit les erreurs et ratés des {heures:g} dernières heures (université, desk, Jarvis)")
    touchees = analyser(ctx.base, heures)
    ids = [t["id"] for t in touchees]
    lecons = ctx.base.lire(f"SELECT * FROM lecons WHERE id IN ({','.join('?' * len(ids))}) ORDER BY equipe, agent",
                           tuple(ids)) if ids else []
    ctx.etape("professeur", "Cherche la cause de chaque erreur et écrit la leçon")
    lignes = [f"Erreurs et ratés relus sur {heures:g} h : {len(lecons)} sujet(s).", ""]
    if not lecons:
        lignes.append("Aucune erreur enregistrée sur la période. On garde le même sérieux demain.")
    for l in lecons:
        qui = agents.agent(l["agent"])["court"] if l["agent"] else l["equipe"]
        etat = {"a_appliquer": "nouvelle", "repetee": f"RÉPÉTÉE ({l['fois']} fois)", "appliquee": "appliquée"}[l["statut"]]
        lignes += [f"[{qui}] {l['quoi']} ({etat})", f"   Cause : {l['cause']}.", f"   Leçon : {l['lecon']}"]
    ctx.etape("connaissances", "Prévient les agents et le directeur", "verification")
    for agent in sorted({l["agent"] for l in lecons if l["agent"]}):
        n = sum(1 for l in lecons if l["agent"] == agent)
        ctx.message(agent, "lecon", f"{n} leçon(s) à relire avant ta prochaine mission.")
    for l in lecons:
        if l["fois"] >= 3:
            ctx.message(agents.DIRECTEUR, "alerte", f"Erreur répétée {l['fois']} fois : {l['quoi']} ({l['cause']}).")
    bugs = [l for l in lecons if l["cause"] == "erreur de programmation"]
    if bugs:
        _signaler_bugs(ctx.base, bugs)
    doc = ctx.document("lecons", "Retour sur les erreurs du jour", "\n".join(lignes),
                       donnees={"lecons": ids}, sources=[{"lecon": i} for i in ids], role="professeur", statut="verifie")
    return {"document": doc, "lecons": len(lecons), "nouvelles": sum(1 for t in touchees if t["nouvelle"]),
            "bugs_signales": len(bugs)}


def _signaler_bugs(base, bugs):
    """Note pour Claude : rangée par le Scribe dans la mémoire (rien n'est corrigé automatiquement)."""
    try:
        dossier = memoire.dossier_memoire(base) / "a_ranger"
        dossier.mkdir(parents=True, exist_ok=True)
        jour = dt.date.today().isoformat()
        lignes = [f"# Erreurs de programmation à corriger ({jour})", "",
                  "Relevées par le mentor (agent 17). À corriger par Claude, avec l'accord de Jabran.", ""]
        lignes += [f"- [{b['equipe']}] {b['quoi']} : {b['exemple']}" for b in bugs]
        (dossier / f"bugs-a-corriger-{jour}.md").write_text("\n".join(lignes) + "\n", encoding="utf-8")
    except OSError:
        pass
