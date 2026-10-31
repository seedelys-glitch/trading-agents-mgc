# -*- coding: utf-8 -*-
"""
Agent 17 (mentor) — le cours du jour (31/10) : chaque agent apprend quelque chose sur sa spécialité tous les jours.

Pour chaque agent (celui dont le dernier cours est le plus ancien d'abord, quelques-uns par mission) :
  1. le sujet suivant de son programme (programme du fil « entraînement » s'il existe, sinon PROGRAMME ci-dessous) ;
  2. des renseignements réels : extraits de la bibliothèque de l'université (STRATEGIE.md, règles validées) et le
     résumé public Wikipédia du sujet (source citée ; s'il n'y a pas d'Internet, on fait sans) ;
  3. le cours, écrit par l'IA (Groq via Jarvis, sinon LM Studio) À PARTIR de ces seuls renseignements, dans la
     charte ; sans IA, le cours reprend les renseignements tels quels, avec leurs sources ;
  4. les leçons encore à appliquer de l'agent sont rappelées à la fin du cours.
Rien n'est inventé : un cours sans aucun renseignement trouvé n'est pas écrit (le sujet est gardé pour demain).
"""

import json
import time
import urllib.parse
import urllib.request

from .. import agents, bibliotheque, personnalites

TYPE = "cours_du_jour"
AGENT = 17
TITRE = "Cours du jour (mentor)"
PARAMS = {"agents": "numéros des agents (vide = ceux dont le dernier cours est le plus ancien)"}
INTERNE = True
PAR_MISSION = 6
WIKI = "https://fr.wikipedia.org/api/rest_v1/page/summary/"

# agent -> [(sujet, page Wikipédia en français ou None)]
PROGRAMME = {
    1: [("Structure de marché : sommets et creux", "Analyse technique"), ("Order blocks et liquidité", "Liquidité (finance)"),
        ("Cassure (BOS) et changement de caractère (CHoCH)", "Tendance (finance)")],
    2: [("Suite de Fibonacci et retracements", "Retracement de Fibonacci"), ("Choisir la bonne impulsion", "Analyse technique"),
        ("Extensions de Fibonacci", "Suite de Fibonacci")],
    3: [("Ichimoku : les cinq lignes", "Ichimoku Kinko Hyo"), ("Le nuage (Kumo)", "Ichimoku Kinko Hyo"),
        ("Chikou et confirmation", "Ichimoku Kinko Hyo")],
    4: [("Carnet d'ordres et profondeur", "Carnet d'ordres"), ("Liquidité de marché", "Liquidité (finance)")],
    5: [("Le FOMC et les taux", "Federal Open Market Committee"), ("L'inflation (CPI)", "Indice des prix à la consommation"),
        ("L'emploi américain (NFP)", "Non-farm payrolls"), ("L'or comme valeur refuge", "Or (finance)")],
    6: [("Moyenne mobile exponentielle", "Moyenne mobile"), ("Le VWAP", "Prix moyen pondéré par le volume"),
        ("Tendance de fond et EMA 200", "Moyenne mobile")],
    7: [("Carnet d'ordres", "Carnet d'ordres"), ("Volume et delta", "Volume (finance)"),
        ("Teneur de marché", "Teneur de marché")],
    8: [("Gestion du risque", "Gestion des risques"), ("Taille de position", "Gestion de portefeuille"),
        ("Effet de levier", "Effet de levier")],
    9: [("Reproductibilité d'un calcul", "Reproductibilité"), ("Audit et contrôle", "Audit"),
        ("Erreurs d'arrondi", "Arrondi (mathématiques)")],
    10: [("Politique monétaire", "Politique monétaire"), ("La Réserve fédérale", "Réserve fédérale des États-Unis"),
         ("Faucons et colombes", "Politique monétaire")],
    11: [("Histoire de l'or", "Or"), ("Étalon-or", "Étalon-or"), ("Crise financière de 2008", "Crise financière mondiale de 2007-2008")],
    12: [("Étude d'événement", "Étude d'événement"), ("Volatilité", "Volatilité (finance)"),
         ("Échantillon et significativité", "Signification statistique")],
    13: [("Backtest", "Backtesting"), ("Surapprentissage", "Surapprentissage"), ("Biais d'anticipation (look-ahead)", "Biais de sélection")],
    14: [("Diriger une équipe", "Management"), ("Prendre une décision", "Prise de décision")],
    15: [("Prise de notes", "Prise de notes"), ("Archivage", "Archivage électronique")],
    16: [("Recherche d'information", "Recherche d'information"), ("Indexation", "Indexation automatique de documents")],
}


def programme(n):
    """Le programme du fil « entraînement » s'il est installé, sinon le programme par défaut."""
    try:
        from .. import entrainement

        sujets = entrainement.programme(n) or []
        if sujets:
            return [(s.get("titre") or s.get("cle"), None, s.get("resume") or "") for s in sujets]
    except (ImportError, AttributeError, TypeError):
        pass
    return [(s, w, "") for s, w in PROGRAMME.get(n, [])]


def wikipedia(page, delai=8):
    """Résumé public d'une page Wikipédia (titre, texte, lien) ou None."""
    if not page:
        return None
    try:
        req = urllib.request.Request(WIKI + urllib.parse.quote(page.replace(" ", "_")),
                                     headers={"User-Agent": "UniversiteMGC/1.0 (recherche personnelle)"})
        with urllib.request.urlopen(req, timeout=delai) as r:
            d = json.loads(r.read().decode("utf-8"))
        texte = (d.get("extract") or "").strip()
        if not texte:
            return None
        return {"titre": d.get("title") or page, "texte": texte[:1500],
                "lien": (d.get("content_urls") or {}).get("desktop", {}).get("page") or WIKI + page}
    except (OSError, ValueError):
        return None


def a_enseigner(base, n=PAR_MISSION):
    """Les agents dont le dernier cours est le plus ancien (jamais = d'abord)."""
    dernier = {r["agent"]: r["t"] for r in base.lire("SELECT agent, MAX(cree) AS t FROM cours GROUP BY agent")}
    eleves = [a["n"] for a in agents.AGENTS if a["n"] != AGENT and programme(a["n"])]
    return sorted(eleves, key=lambda x: (dernier.get(x, 0), x))[:n]


def un_cours(ctx, n):
    """Prépare et écrit le cours d'un agent. Renvoie l'id du document, ou None (rien trouvé)."""
    sujets = programme(n)
    deja = ctx.base.un("SELECT COUNT(*) AS c FROM cours WHERE agent=?", (n,))["c"]
    sujet, page, resume = sujets[deja % len(sujets)]
    p = personnalites.BASE[n]
    ctx.etape("chercheur", f"Cherche des renseignements pour {p['prenom']} : {sujet}")
    sources, faits = [], []
    if resume:
        faits.append(f"Programme d'entraînement : {resume}")
        sources.append({"programme": sujet})
    for e in bibliotheque.rechercher(ctx.base, sujet, n=2):
        faits.append(f"Bibliothèque ({e['titre']}) : {e['texte']}")
        sources.append({e["genre"]: e["id"], "titre": e["titre"]})
    w = wikipedia(page)
    if w:
        faits.append(f"Wikipédia ({w['titre']}) : {w['texte']}")
        sources.append({"wikipedia": w["titre"], "lien": w["lien"]})
    if not faits:
        ctx.journal(f"Cours « {sujet} » pour {p['prenom']} reporté : aucun renseignement trouvé.", "alerte")
        return None
    lecons = ctx.base.lire("SELECT quoi, lecon FROM lecons WHERE agent=? AND statut IN ('a_appliquer','repetee')"
                           " ORDER BY fois DESC, maj DESC LIMIT 3", (n,))
    ctx.etape("professeur", f"Donne le cours à {p['prenom']}")
    consigne = (f"Tu es Margaux, mentor de l'université MGC. Tu donnes un cours court (8 à 12 phrases) en français simple à "
                f"{personnalites.presentation(n)}. Sujet : {sujet}. Utilise UNIQUEMENT les renseignements fournis, "
                "relie-les à sa spécialité sur le Micro Gold, termine par un petit exercice à faire en replay. "
                "Si un renseignement manque, dis-le. Aucun conseil d'achat ou de vente.")
    texte = "\n\n".join(faits)
    r = ctx.ia.rediger(consigne, texte, mission=ctx.id, agent=AGENT, role="professeur", chiffres_libres=True)
    corps = r["texte"] if r else "Renseignements du jour (sans IA disponible) :\n\n" + texte
    if lecons:
        corps += "\n\nÀ ne pas oublier (tes leçons) :\n" + "\n".join(f"- {l['quoi']} : {l['lecon']}" for l in lecons)
    corps += "\n\nSources : " + "; ".join(s.get("lien") or s.get("titre") or str(s) for s in sources)
    doc = ctx.document("cours", f"Cours pour {p['prenom']} ({agents.agent(n)['court']}) : {sujet}", corps,
                       donnees={"eleve": n, "sujet": sujet, "ia": r["ia"] if r else None},
                       sources=sources, role="professeur", statut="verifie" if not r else "brouillon")
    ctx.base.ecrire("INSERT INTO cours(agent, sujet, document, sources, cree) VALUES (?,?,?,?,?)",
                    (n, sujet, doc, json.dumps(sources, ensure_ascii=False), time.time()))
    ctx.message(n, "cours", f"Cours du jour : {sujet}", doc)
    return doc


def executer(ctx):
    eleves = [int(x) for x in (ctx.params.get("agents") or []) if agents.agent(x)] or a_enseigner(ctx.base)
    ctx.etape("documentaliste", f"Prépare les cours de {len(eleves)} agent(s)")
    faits, reportes = [], []
    for n in eleves:
        if ctx.limite - time.time() < 60:        # on garde le reste pour la prochaine tournée
            reportes.append(n)
            continue
        doc = un_cours(ctx, n)
        (faits if doc else reportes).append(n)
    for n in faits:
        personnalites.evoluer(ctx.base, n)
    return {"cours": faits, "reportes": reportes}
