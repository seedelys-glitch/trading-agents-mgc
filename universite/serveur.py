# -*- coding: utf-8 -*-
"""
API locale de l'université + bureau virtuel (ui/). Écoute seulement sur 127.0.0.1 (le PC lui-même).

Toutes les réponses viennent de la base : le bureau n'affiche jamais une activité qui n'a pas eu lieu.
Les requêtes qui modifient quelque chose (POST) exigent l'en-tête X-Universite, qu'une page d'un autre site
ne peut pas envoyer sans autorisation : un site malveillant ouvert dans le navigateur ne peut rien lancer.
"""

import json
import logging
import mimetypes
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import agents, bibliotheque, competences, config, donnees, scene
from .base import Base
from .ia import IALocale
from .moteur import Moteur

UI = Path(__file__).resolve().parent / "ui"
ACTIF_S = 120          # un lien entre deux agents reste affiché 2 min après leur dernier message réel
TYPES_FORCES = {".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css", ".html": "text/html",
                ".svg": "image/svg+xml", ".json": "application/json"}
BOUGIES_MAX = 1000     # bougies renvoyées au plus par /api/bougies
UNITES_GRAPHIQUE = ("H1", "M15", "M5", "D1", "M1")   # unité préférée pour le petit graphique d'un poste
log = logging.getLogger("universite")


class Universite:
    def __init__(self, dossier=None, demarrer_moteur=True):
        self.dossier = Path(dossier or config.DONNEES)
        self.reglages = config.charger(self.dossier)
        self.base = Base(self.dossier / "universite.sqlite")
        self.ia = IALocale(self.base, self.reglages)
        self.moteur = Moteur(self.base, self.reglages, self.ia)
        if demarrer_moteur:
            self.moteur.demarrer()

    # ------------------------------------------------------------------ lecture
    def etat(self):
        maintenant = time.time()
        connues = set(competences.TYPES)
        en_cours = {m["agent"]: m for m in self.base.lire("SELECT * FROM missions WHERE statut='en_cours'")}
        attente = {r["agent"]: r["n"] for r in self.base.lire(
            "SELECT agent, COUNT(*) AS n FROM missions WHERE statut='en_attente' GROUP BY agent")}
        erreurs = {r["agent"]: r for r in self.base.lire(
            "SELECT agent, MAX(fin) AS fin, COUNT(*) AS n FROM missions WHERE statut='erreur' AND fin>=? GROUP BY agent",
            (maintenant - 3600,))}
        derniers = {r["agent"]: r for r in self.base.lire(
            "SELECT agent, MAX(fin) AS fin FROM missions WHERE statut='terminee' GROUP BY agent")}
        docs = {r["agent"]: r["n"] for r in self.base.lire("SELECT agent, COUNT(*) AS n FROM documents GROUP BY agent")}
        derniers_docs = {r["agent"]: r for r in self.base.lire(
            "SELECT id, agent, genre, titre, statut, cree FROM documents WHERE id IN"
            " (SELECT MAX(id) FROM documents GROUP BY agent)")}
        liste = []
        for a in agents.AGENTS:
            fiche = agents.fiche(a, connues)
            m = en_cours.get(a["n"])
            if fiche["en_construction"]:
                statut = "construction"
            elif m:
                statut = "travail"
            elif a["n"] in erreurs and (derniers.get(a["n"], {}).get("fin") or 0) < erreurs[a["n"]]["fin"]:
                statut = "erreur"
            elif attente.get(a["n"]):
                statut = "attente"
            else:
                statut = "disponible"
            liste.append({"n": a["n"], "cle": a["cle"], "nom": a["nom"], "court": a["court"], "statut": statut,
                          "competences": fiche["competences_branchees"], "file": attente.get(a["n"], 0),
                          "documents": docs.get(a["n"], 0), "dernier_document": derniers_docs.get(a["n"]),
                          "mission": None if not m else {k: m[k] for k in (
                              "id", "titre", "phase", "role", "etape", "etapes_faites", "debut", "battement")}})
        liens = self.base.lire("SELECT de, a, genre, MAX(ts) AS ts, COUNT(*) AS n FROM messages WHERE ts>=?"
                               " GROUP BY de, a, genre", (maintenant - ACTIF_S,))
        return {"maintenant": maintenant, "agents": liste, "liens": liens, "moteur": self.moteur.etat(),
                "ia": {**self.ia.etat(), "appels_du_jour": self.ia.appels_du_jour(),
                       "budget": self.reglages["ia_appels_max_jour"], "active": self.reglages["ia_commentaires"]},
                "compteurs": self.base.un(
                    "SELECT (SELECT COUNT(*) FROM missions WHERE statut='en_attente') AS attente,"
                    " (SELECT COUNT(*) FROM missions WHERE statut='en_cours') AS en_cours,"
                    " (SELECT COUNT(*) FROM documents) AS documents,"
                    " (SELECT COUNT(*) FROM jeux) AS jeux,"
                    " (SELECT COUNT(*) FROM boucles WHERE statut='active') AS boucles"),
                "dernier_evenement": (self.base.un("SELECT MAX(id) AS id FROM evenements") or {}).get("id") or 0}

    def fiche_agent(self, n):
        a = agents.agent(n)
        if not a:
            return None
        f = agents.fiche(a, set(competences.TYPES))
        f["catalogue"] = [c for c in competences.catalogue() if c["agent"] == a["n"]]
        f["missions"] = self.base.lire("SELECT id, type, titre, statut, phase, role, etape, tentatives, erreur, cree,"
                                       " debut, fin, demandeur, parent, boucle FROM missions WHERE agent=?"
                                       " ORDER BY id DESC LIMIT 40", (a["n"],))
        f["etapes"] = self.base.lire("SELECT * FROM etapes WHERE agent=? ORDER BY id DESC LIMIT 60", (a["n"],))
        f["documents"] = self.base.lire("SELECT id, genre, titre, statut, verifie_par, cree, mission FROM documents"
                                        " WHERE agent=? ORDER BY id DESC LIMIT 30", (a["n"],))
        f["messages"] = self.base.lire("SELECT * FROM messages WHERE de=? OR a=? ORDER BY id DESC LIMIT 30",
                                       (a["n"], a["n"]))
        f["evenements"] = self.base.lire("SELECT * FROM evenements WHERE agent=? ORDER BY id DESC LIMIT 30", (a["n"],))
        f["boucles"] = self.base.lire("SELECT * FROM boucles WHERE responsable=? ORDER BY id DESC", (a["n"],))
        # Dernière étape de chaque fonction de soutien : ce qu'elle a réellement fait, et quand
        f["soutiens_etat"] = {r["role"]: r for r in self.base.lire(
            "SELECT role, libelle, statut, debut, fin, mission FROM etapes WHERE id IN"
            " (SELECT MAX(id) FROM etapes WHERE agent=? GROUP BY role)", (a["n"],))}
        return f

    def espace_agent(self, n):
        """L'espace de travail d'un agent dans le bureau immersif : uniquement ce que la base contient."""
        a = agents.agent(n)
        if not a:
            return None
        f = agents.fiche(a, set(competences.TYPES))
        vivant = next(x for x in self.etat()["agents"] if x["n"] == a["n"])
        documents = self.base.lire("SELECT id, genre, titre, statut, verifie_par, cree, mission, sources FROM documents"
                                   " WHERE agent=? ORDER BY id DESC LIMIT 10", (a["n"],))
        dernier = self.base.un("SELECT * FROM documents WHERE agent=? ORDER BY id DESC LIMIT 1", (a["n"],))
        sources, vues = [], set()
        for d in documents:
            for s in d.pop("sources") or []:
                cle = json_cle(s)
                if cle not in vues and len(sources) < 20:
                    vues.add(cle)
                    sources.append({**s, "cite_dans": d["id"]} if isinstance(s, dict) else {"texte": s, "cite_dans": d["id"]})
        return {"agent": {k: f[k] for k in ("n", "cle", "nom", "court", "mission", "outils", "qualite", "escalade",
                                             "competences_branchees", "en_construction", "soutiens")},
                "statut": vivant["statut"], "mission_en_cours": vivant["mission"], "file": vivant["file"],
                "poste": scene.poste(a["n"]),
                "missions": self.base.lire("SELECT id, type, titre, statut, erreur, cree, debut, fin, demandeur"
                                           " FROM missions WHERE agent=? ORDER BY id DESC LIMIT 15", (a["n"],)),
                "documents": documents, "dernier_document": dernier, "graphique": graphique(dernier),
                "sources": sources,
                "jeux": {j["id"]: j for j in self.base.lire("SELECT id, nom, source, temps_reel FROM jeux")},
                "echanges": self.base.lire("SELECT * FROM messages WHERE de=? OR a=? ORDER BY id DESC LIMIT 20",
                                           (a["n"], a["n"])),
                "taches": [c for c in competences.catalogue() if c["agent"] == a["n"] and not c["interne"]]}

    def zone(self, cle):
        """Ce qu'une zone du bureau montre : seulement des lignes de la base (rien de décoratif)."""
        z = scene.PAR_CLE.get(cle)
        if not z:
            return None
        e = self.etat()
        numeros = scene.OCCUPANTS.get(cle, [])
        r = {"zone": z, "maintenant": e["maintenant"], "agents": [a for a in e["agents"] if a["n"] in numeros]}
        docs = ("SELECT id, agent, genre, titre, statut, verifie_par, cree FROM documents")
        if numeros:
            r["documents"] = self.base.lire(docs + f" WHERE agent IN ({','.join('?' * len(numeros))}) ORDER BY id DESC LIMIT 12",
                                            tuple(numeros))
        if cle == "directeur":
            r["syntheses"] = self.base.lire(docs + " WHERE genre='synthese' ORDER BY id DESC LIMIT 5")
            r["derniere_synthese"] = self.base.un("SELECT id, titre, statut, cree, contenu FROM documents"
                                                  " WHERE genre='synthese' ORDER BY id DESC LIMIT 1")
            r["demandes"] = self.base.lire("SELECT id, type, titre, statut, cree, fin, erreur FROM missions WHERE agent=?"
                                           " ORDER BY id DESC LIMIT 10", (agents.DIRECTEUR,))
            r["alertes"] = self.base.lire("SELECT * FROM messages WHERE a=? AND genre='alerte' ORDER BY id DESC LIMIT 10",
                                          (agents.DIRECTEUR,))
            r["compteurs"] = e["compteurs"]
        elif cle == "reunion":
            r["messages"] = self.base.lire("SELECT id, ts, de, a, genre, substr(contenu, 1, 240) AS contenu, mission, document"
                                           " FROM messages ORDER BY id DESC LIMIT 30")
            r["messages_24h"] = self.base.un("SELECT COUNT(*) AS n FROM messages WHERE ts>=?", (e["maintenant"] - 86400,))["n"]
        elif cle == "bibliotheque":
            r["regles"] = {x["statut"]: x["n"] for x in self.base.lire("SELECT statut, COUNT(*) AS n FROM regles GROUP BY statut")}
            r["regles_recentes"] = self.base.lire("SELECT id, titre, statut, version, theme, cree FROM regles"
                                                  " ORDER BY id DESC LIMIT 6")
            r["extraits"] = self.base.lire("SELECT CASE WHEN instr(origine, ':') > 0 THEN substr(origine, 1, instr(origine, ':') - 1)"
                                           " ELSE 'fichier' END AS genre, COUNT(*) AS n, COUNT(DISTINCT origine) AS origines"
                                           " FROM extraits GROUP BY genre")
            r["verifications"] = self.base.lire(docs + " WHERE genre='verification' ORDER BY id DESC LIMIT 6")
        elif cle == "macro":
            r["annonces"] = self.base.lire("SELECT quand, titre, pays, impact, genre, source FROM annonces WHERE quand>=?"
                                           " AND quand<=? ORDER BY quand LIMIT 30", (e["maintenant"], e["maintenant"] + 48 * 3600))
            r["annonces_gardees"] = self.base.un("SELECT COUNT(*) AS n FROM annonces")["n"]
        elif cle == "donnees":
            r["jeux"] = donnees.liste_jeux(self.base)
            r["fichiers"] = self.base.lire("SELECT chemin, jeu, unite, lignes, ajoutees, importe_le FROM fichiers_importes"
                                           " ORDER BY importe_le DESC LIMIT 10")
        return r

    def bougies(self, q):
        """Vraies bougies FERMÉES d'un jeu à un instant (jamais de bougie future)."""
        jeu = int(q["jeu"])
        infos = self.base.un("SELECT id, nom, source, symbole, temps_reel FROM jeux WHERE id=?", (jeu,))
        if not infos:
            raise ValueError("jeu de bougies inconnu")
        instant = float(q.get("instant") or time.time())
        n = max(1, min(BOUGIES_MAX, int(q.get("n", 200))))
        f = donnees.fenetre(self.base, jeu, q.get("unite", "H1"), instant, n)
        return {"jeu": infos, "unite": f["unite"], "instant": instant, "fermees_seulement": True,
                "reconstruite_depuis": f["reconstruite_depuis"], "bougies": f["bougies"]}

    # ------------------------------------------------------------------ actions
    def creer_mission(self, corps):
        genre = corps.get("type", "")
        comp = competences.TYPES.get(genre)
        if comp is None:
            raise ValueError(f"type de mission inconnu : {genre}")
        params = corps.get("params") or {}
        if corps.get("par_directeur") and comp.AGENT != agents.DIRECTEUR:
            return self.base.nouvelle_mission(agents.DIRECTEUR, "demande_directeur", f"Demande : {comp.TITRE}",
                                              {"type": genre, "params": params, "consigne": corps.get("consigne", "")},
                                              corps.get("consigne", ""), priorite=3,
                                              tentatives_max=self.reglages["tentatives_max"])
        return self.base.nouvelle_mission(comp.AGENT, genre, corps.get("titre") or comp.TITRE, params,
                                          corps.get("consigne", ""), priorite=int(corps.get("priorite", 5)),
                                          tentatives_max=self.reglages["tentatives_max"])

    def rechercher(self, question):
        question = str(question).strip()[:300]
        if not question:
            return {"resultats": [], "sens": False}
        vecteur = None
        if self.reglages.get("ia_embeddings"):
            try:
                vecteur = bibliotheque.embeddings(self.reglages["ia_url"], self.reglages["ia_embeddings"], [question], 15)[0]
            except (OSError, IndexError):
                vecteur = None
        return {"resultats": bibliotheque.rechercher(self.base, question, vecteur_question=vecteur), "sens": vecteur is not None}

    def arreter(self):
        self.moteur.arreter()


def json_cle(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)


def graphique(doc):
    """De quoi tracer le petit graphique d'un document : son jeu, son instant et une unité qu'il a réellement lue."""
    if not doc or not isinstance(doc.get("donnees"), dict):
        return None
    d = doc["donnees"]
    unites = [s.get("unite") for s in doc.get("sources") or [] if isinstance(s, dict) and s.get("jeu") == d.get("jeu")]
    unite = next((u for u in UNITES_GRAPHIQUE if u in unites), None)
    if d.get("jeu") is None or not d.get("instant") or not unite:
        return None
    return {"jeu": int(d["jeu"]), "instant": float(d["instant"]), "unite": unite}


def _json_bytes(obj):
    return json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")


def fabriquer_handler(univ):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Universite/1"

        def log_message(self, fmt, *args):
            log.debug(fmt, *args)

        def _envoyer(self, code, corps, type_="application/json; charset=utf-8"):
            if not isinstance(corps, bytes):
                corps = _json_bytes(corps)
            self.send_response(code)
            self.send_header("Content-Type", type_)
            self.send_header("Content-Length", str(len(corps)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(corps)

        def _corps(self, limite=20_000_000):
            n = int(self.headers.get("Content-Length") or 0)
            if n > limite:
                raise ValueError("envoi trop gros")
            brut = self.rfile.read(n) if n else b""
            return brut

        def do_GET(self):
            u = urlparse(self.path)
            q = {k: v[-1] for k, v in parse_qs(u.query).items()}
            morceaux = [m for m in u.path.split("/") if m]
            try:
                if u.path == "/api/etat":
                    return self._envoyer(200, univ.etat())
                if u.path == "/api/agents":
                    connues = set(competences.TYPES)
                    return self._envoyer(200, {"agents": [agents.fiche(a, connues) for a in agents.AGENTS],
                                               "roles": len(agents.roles()), "catalogue": competences.catalogue()})
                if len(morceaux) == 3 and morceaux[:2] == ["api", "agent"]:
                    f = univ.fiche_agent(morceaux[2])
                    return self._envoyer(200 if f else 404, f or {"erreur": "agent inconnu"})
                if u.path == "/api/scene":
                    return self._envoyer(200, scene.scene())
                if len(morceaux) == 4 and morceaux[:2] == ["api", "agent"] and morceaux[3] == "espace":
                    e = univ.espace_agent(morceaux[2])
                    return self._envoyer(200 if e else 404, e or {"erreur": "agent inconnu"})
                if len(morceaux) == 3 and morceaux[:2] == ["api", "zone"]:
                    z = univ.zone(morceaux[2])
                    return self._envoyer(200 if z else 404, z or {"erreur": "zone inconnue"})
                if u.path == "/api/bougies":
                    return self._envoyer(200, univ.bougies(q))
                if u.path == "/api/missions":
                    return self._envoyer(200, univ.base.lire("SELECT * FROM missions ORDER BY id DESC LIMIT ?",
                                                             (min(500, int(q.get("n", 100))),)))
                if len(morceaux) == 3 and morceaux[:2] == ["api", "mission"]:
                    m = univ.base.mission(int(morceaux[2]))
                    if m:
                        m["etapes"] = univ.base.lire("SELECT * FROM etapes WHERE mission=? ORDER BY id", (m["id"],))
                    return self._envoyer(200 if m else 404, m or {"erreur": "mission inconnue"})
                if u.path == "/api/documents":
                    return self._envoyer(200, univ.base.lire(
                        "SELECT id, agent, genre, titre, statut, verifie_par, cree, mission FROM documents"
                        " ORDER BY id DESC LIMIT ?", (min(500, int(q.get("n", 100))),)))
                if len(morceaux) == 3 and morceaux[:2] == ["api", "document"]:
                    d = univ.base.un("SELECT * FROM documents WHERE id=?", (int(morceaux[2]),))
                    return self._envoyer(200 if d else 404, d or {"erreur": "document inconnu"})
                if u.path == "/api/evenements":
                    return self._envoyer(200, univ.base.lire(
                        "SELECT * FROM evenements WHERE id>? ORDER BY id DESC LIMIT 200", (int(q.get("apres", 0)),)))
                if u.path == "/api/messages":
                    return self._envoyer(200, univ.base.lire("SELECT * FROM messages ORDER BY id DESC LIMIT 100"))
                if u.path == "/api/jeux":
                    return self._envoyer(200, donnees.liste_jeux(univ.base))
                if u.path == "/api/boucles":
                    return self._envoyer(200, univ.base.lire("SELECT * FROM boucles ORDER BY id DESC"))
                if u.path == "/api/reglages":
                    return self._envoyer(200, univ.reglages)
                if u.path == "/api/regles":
                    statut = q.get("statut")
                    sql = "SELECT * FROM regles" + (" WHERE statut=?" if statut else "") + " ORDER BY theme, cle, version DESC"
                    return self._envoyer(200, univ.base.lire(sql, (statut,) if statut else ()))
                if u.path == "/api/recherche":
                    return self._envoyer(200, univ.rechercher(q.get("q", "")))
                return self._fichier(u.path)
            except (ValueError, KeyError) as e:
                return self._envoyer(400, {"erreur": str(e)})

        def _fichier(self, chemin):
            if chemin in ("", "/"):
                chemin = "/index.html"
            f = (UI / chemin.lstrip("/")).resolve()
            if UI.resolve() not in f.parents or not f.is_file():
                return self._envoyer(404, {"erreur": "introuvable"})
            # Sous Windows, le registre peut associer .js à text/plain : les modules du bureau 3D seraient refusés
            type_ = TYPES_FORCES.get(f.suffix.lower()) or mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            if type_.startswith("text/") or type_ in ("application/javascript", "application/json", "image/svg+xml"):
                type_ += "; charset=utf-8"
            return self._envoyer(200, f.read_bytes(), type_)

        def do_POST(self):
            if self.headers.get("X-Universite") != "1":
                return self._envoyer(403, {"erreur": "en-tête X-Universite manquant"})
            u = urlparse(self.path)
            morceaux = [m for m in u.path.split("/") if m]
            try:
                brut = self._corps()
                if u.path == "/api/jeux/import":
                    nom = self.headers.get("X-Nom-Jeu") or "Import"
                    from urllib.parse import unquote
                    r = donnees.importer_csv(univ.base, brut.decode("utf-8-sig", errors="replace"), unquote(nom),
                                             unite=self.headers.get("X-Unite") or None)
                    return self._envoyer(200, r)
                corps = json.loads(brut.decode("utf-8") or "{}") if brut else {}
                if u.path == "/api/missions":
                    return self._envoyer(200, {"mission": univ.creer_mission(corps)})
                if len(morceaux) == 4 and morceaux[:2] == ["api", "mission"] and morceaux[3] == "annuler":
                    return self._envoyer(200, {"annulee": univ.base.annuler(int(morceaux[2]))})
                if u.path == "/api/jeux/ninja":
                    config.salle_importable()
                    from mgc import config as cfg_salle, source_ninja
                    dossier = corps.get("dossier") or source_ninja.dossier_par_defaut(cfg_salle.charger())
                    return self._envoyer(200, donnees.importer_ninja(univ.base, dossier))
                if u.path == "/api/jeux/yahoo":
                    config.salle_importable()
                    from mgc import config as cfg_salle
                    from mgc.contrats import ContractManager
                    import datetime as dt
                    contrat = corps.get("contrat") or ContractManager(cfg_salle.charger()).etat(
                        dt.datetime.now(dt.UTC))["contrat"]
                    return self._envoyer(200, donnees.importer_yahoo(univ.base, contrat))
                if u.path == "/api/boucles":
                    b = univ.moteur.nouvelle_boucle(corps["nom"], int(corps["responsable"]), corps["type"],
                                                    corps.get("objectif", ""), corps.get("params"),
                                                    corps.get("intervalle_s", 600), corps.get("iterations_max", 100))
                    return self._envoyer(200, {"boucle": b})
                if len(morceaux) == 4 and morceaux[:2] == ["api", "boucle"]:
                    return self._envoyer(200, {"ok": univ.moteur.changer_boucle(int(morceaux[2]), morceaux[3])})
                if len(morceaux) == 4 and morceaux[:2] == ["api", "regle"]:
                    ident, action = int(morceaux[2]), morceaux[3]
                    if action == "modifier":
                        return self._envoyer(200, bibliotheque.modifier(univ.base, ident, corps.get("texte", "")))
                    decision = {"valider": "validee", "rejeter": "rejetee"}.get(action, "")
                    return self._envoyer(200, bibliotheque.decider(univ.base, ident, decision, corps.get("note", "")))
                if u.path == "/api/reglages":
                    univ.reglages.update(config.enregistrer(corps, univ.dossier))
                    return self._envoyer(200, univ.reglages)
                return self._envoyer(404, {"erreur": "introuvable"})
            except (ValueError, KeyError, TypeError) as e:
                return self._envoyer(400, {"erreur": str(e)})
            except OSError as e:
                return self._envoyer(503, {"erreur": f"{type(e).__name__} : {e}"})

    return Handler


class ServeurExclusif(ThreadingHTTPServer):
    """Un seul serveur par port. Sous Windows, SO_REUSEADDR (mis par défaut) laisse une 2e université écouter sur le
    même port que la première : la page tombait alors au hasard sur l'ancienne version. Ici le port est exclusif,
    une 2e université reçoit OSError et se contente d'ouvrir la page de celle qui tourne."""
    allow_reuse_address = not hasattr(socket, "SO_EXCLUSIVEADDRUSE")
    daemon_threads = True

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def lancer(univ, port=None, hote="127.0.0.1"):
    serveur = ServeurExclusif((hote, port if port is not None else univ.reglages["port"]), fabriquer_handler(univ))
    fil = threading.Thread(target=serveur.serve_forever, name="http", daemon=True)
    fil.start()
    return serveur
