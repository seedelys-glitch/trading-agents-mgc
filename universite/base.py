# -*- coding: utf-8 -*-
"""
Base persistante de l'université : rapports\\universite\\universite.sqlite (séparée de analyste.sqlite de la Salle).

Tout ce que le bureau affiche vient d'ici : missions, étapes réellement exécutées (avec la fonction de soutien
mobilisée), documents produits, messages entre agents, journal, jeux de bougies, boucles, appels IA.
Après un redémarrage, tout est relu et les missions interrompues sont remises dans la file.
Migrations versionnées et réversibles, comme mgc/base.py.
"""

import datetime as dt
import json
import sqlite3
import threading
import time
from pathlib import Path

MIGRATIONS = [
    (1, "tables de départ", """
        CREATE TABLE missions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent INTEGER NOT NULL, type TEXT NOT NULL, titre TEXT NOT NULL, objectif TEXT NOT NULL DEFAULT '',
            params TEXT NOT NULL DEFAULT '{}', priorite INTEGER NOT NULL DEFAULT 5,
            statut TEXT NOT NULL DEFAULT 'en_attente',   -- en_attente, en_cours, terminee, erreur, annulee
            phase TEXT NOT NULL DEFAULT 'attente',       -- recherche, analyse, redaction, verification, reunion
            role TEXT NOT NULL DEFAULT '', etape TEXT NOT NULL DEFAULT '',
            etapes_faites INTEGER NOT NULL DEFAULT 0, etapes_total INTEGER NOT NULL DEFAULT 0,
            tentatives INTEGER NOT NULL DEFAULT 0, tentatives_max INTEGER NOT NULL DEFAULT 2,
            pas_avant REAL NOT NULL DEFAULT 0, demandeur TEXT NOT NULL DEFAULT 'jabran', parent INTEGER,
            boucle INTEGER, resultat TEXT, erreur TEXT, cree REAL NOT NULL, debut REAL, fin REAL, battement REAL);
        CREATE INDEX missions_statut ON missions(statut, priorite, id);
        CREATE INDEX missions_agent ON missions(agent, id);
        CREATE TABLE etapes (
            id INTEGER PRIMARY KEY AUTOINCREMENT, mission INTEGER NOT NULL, agent INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT '', phase TEXT NOT NULL, libelle TEXT NOT NULL,
            debut REAL NOT NULL, fin REAL, statut TEXT NOT NULL DEFAULT 'en_cours', detail TEXT);
        CREATE INDEX etapes_mission ON etapes(mission, id);
        CREATE TABLE evenements (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, agent INTEGER, mission INTEGER,
            niveau TEXT NOT NULL DEFAULT 'info', genre TEXT NOT NULL, message TEXT NOT NULL);
        CREATE INDEX evenements_agent ON evenements(agent, id);
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT, agent INTEGER NOT NULL, mission INTEGER, role TEXT NOT NULL DEFAULT '',
            genre TEXT NOT NULL, titre TEXT NOT NULL, contenu TEXT NOT NULL, donnees TEXT NOT NULL DEFAULT '{}',
            sources TEXT NOT NULL DEFAULT '[]',
            statut TEXT NOT NULL DEFAULT 'brouillon',    -- brouillon, a_verifier, verifie, rejete
            verifie_par INTEGER, cree REAL NOT NULL);
        CREATE INDEX documents_agent ON documents(agent, id);
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, de INTEGER NOT NULL, a INTEGER NOT NULL,
            mission INTEGER, document INTEGER, genre TEXT NOT NULL, contenu TEXT NOT NULL);
        CREATE TABLE jeux (
            id INTEGER PRIMARY KEY AUTOINCREMENT, nom TEXT NOT NULL, source TEXT NOT NULL, symbole TEXT NOT NULL,
            temps_reel INTEGER NOT NULL DEFAULT 0, licence TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
            cree REAL NOT NULL);
        CREATE TABLE bougies (
            jeu INTEGER NOT NULL, unite TEXT NOT NULL, ts REAL NOT NULL,
            o REAL NOT NULL, h REAL NOT NULL, l REAL NOT NULL, c REAL NOT NULL, v REAL NOT NULL,
            PRIMARY KEY (jeu, unite, ts)) WITHOUT ROWID;
        CREATE TABLE boucles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, genre TEXT NOT NULL, nom TEXT NOT NULL, responsable INTEGER NOT NULL,
            objectif TEXT NOT NULL, statut TEXT NOT NULL DEFAULT 'active',   -- active, pause, terminee, erreur
            etat TEXT NOT NULL DEFAULT '{}', params TEXT NOT NULL DEFAULT '{}',
            iterations INTEGER NOT NULL DEFAULT 0, iterations_max INTEGER NOT NULL DEFAULT 100,
            intervalle_s REAL NOT NULL DEFAULT 600, prochaine REAL NOT NULL DEFAULT 0,
            derniere_erreur TEXT, erreurs_de_suite INTEGER NOT NULL DEFAULT 0, cree REAL NOT NULL, maj REAL NOT NULL);
        CREATE TABLE ia_appels (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, mission INTEGER, agent INTEGER, role TEXT,
            modele TEXT, duree_s REAL, statut TEXT NOT NULL, erreur TEXT);
    """, """
        DROP TABLE ia_appels; DROP TABLE boucles; DROP TABLE bougies; DROP TABLE jeux; DROP TABLE messages;
        DROP TABLE documents; DROP TABLE evenements; DROP TABLE etapes; DROP TABLE missions;
    """),
    (2, "bibliothèque de connaissances", """
        CREATE TABLE regles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, cle TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
            titre TEXT NOT NULL, texte TEXT NOT NULL, theme TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '{}',              -- fichier, section, ligne, ou document
            statut TEXT NOT NULL DEFAULT 'proposee',        -- proposee, validee, rejetee, remplacee
            propose_par INTEGER, decide_par TEXT, decision_le REAL, note TEXT NOT NULL DEFAULT '',
            precedente INTEGER, cree REAL NOT NULL);
        CREATE INDEX regles_cle ON regles(cle, version);
        CREATE TABLE extraits (
            id INTEGER PRIMARY KEY AUTOINCREMENT, origine TEXT NOT NULL, titre TEXT NOT NULL, position INTEGER NOT NULL,
            texte TEXT NOT NULL, empreinte TEXT NOT NULL, vecteur TEXT, modele TEXT, cree REAL NOT NULL);
        CREATE INDEX extraits_origine ON extraits(origine, position);
    """, """
        DROP TABLE extraits; DROP TABLE regles;
    """),
    (3, "calendrier des annonces", """
        CREATE TABLE annonces (
            id INTEGER PRIMARY KEY AUTOINCREMENT, quand REAL NOT NULL, titre TEXT NOT NULL, pays TEXT NOT NULL,
            impact TEXT NOT NULL DEFAULT '', genre TEXT NOT NULL,      -- reunion_fomc, discours_fed, forte, autre
            prevision TEXT NOT NULL DEFAULT '', precedent TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL, recu_le REAL NOT NULL, maj REAL NOT NULL, UNIQUE(quand, titre, pays));
        CREATE INDEX annonces_quand ON annonces(quand);
    """, """
        DROP TABLE annonces;
    """),
    (4, "fichiers TradingView déjà importés", """
        CREATE TABLE fichiers_importes (
            empreinte TEXT PRIMARY KEY, chemin TEXT NOT NULL, jeu INTEGER NOT NULL, unite TEXT NOT NULL,
            lignes INTEGER NOT NULL, ajoutees INTEGER NOT NULL, importe_le REAL NOT NULL);
    """, """
        DROP TABLE fichiers_importes;
    """),
    (5, "conversation de Jabran (via Jarvis) avec le directeur", """
        CREATE TABLE conversation (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, de TEXT NOT NULL, texte TEXT NOT NULL,
            origine TEXT, mission INTEGER, intention TEXT);
    """, """
        DROP TABLE conversation;
    """),
    (6, "mémoire : blocs du Scribe et curseurs de lecture", """
        CREATE TABLE memoire_blocs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ref TEXT NOT NULL UNIQUE,   -- d'où vient le bloc (mission:12, claude:…)
            genre TEXT NOT NULL, source TEXT NOT NULL, session TEXT NOT NULL DEFAULT '', dossier TEXT NOT NULL,
            titre TEXT NOT NULL, texte TEXT NOT NULL, mots TEXT NOT NULL DEFAULT '', agents TEXT NOT NULL DEFAULT '[]',
            debut REAL NOT NULL, fin REAL NOT NULL, empreinte TEXT NOT NULL, cree REAL NOT NULL, maj REAL NOT NULL);
        CREATE INDEX memoire_blocs_dossier ON memoire_blocs(dossier, debut);
        CREATE INDEX memoire_blocs_fin ON memoire_blocs(fin);
        CREATE INDEX memoire_blocs_maj ON memoire_blocs(maj);
        CREATE TABLE memoire_curseurs (source TEXT PRIMARY KEY, position TEXT NOT NULL, maj REAL NOT NULL);
    """, """
        DROP TABLE IF EXISTS memoire_index; DROP TABLE memoire_curseurs; DROP TABLE memoire_blocs;
    """),
]

CHAMPS_JSON = ("params", "resultat", "donnees", "sources", "etat", "detail", "source")


def _ligne(r):
    if r is None:
        return None
    d = dict(r)
    for k in CHAMPS_JSON:
        if isinstance(d.get(k), str):
            try:
                d[k] = json.loads(d[k])
            except ValueError:
                pass
    return d


def _json(obj):
    return json.dumps(obj if obj is not None else {}, ensure_ascii=False, default=str)


class Base:
    def __init__(self, fichier):
        self.fichier = Path(fichier)
        self.fichier.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._ecriture = threading.RLock()
        self.migrer()

    # ------------------------------------------------------------------ connexion et migrations
    def cx(self):
        c = getattr(self._local, "cx", None)
        if c is None:
            c = sqlite3.connect(str(self.fichier), timeout=30, check_same_thread=False)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA synchronous=NORMAL")
            self._local.cx = c
        return c

    def fermer(self):
        c = getattr(self._local, "cx", None)
        if c is not None:
            c.close()
            self._local.cx = None

    def version(self):
        c = self.cx()
        c.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL, nom TEXT, le TEXT)")
        return c.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] or 0

    def migrer(self, cible=None):
        cible = MIGRATIONS[-1][0] if cible is None else cible
        with self._ecriture:
            c = self.cx()
            actuelle = self.version()
            for num, nom, montee, _ in MIGRATIONS:
                if actuelle < num <= cible:
                    c.executescript(montee)
                    c.execute("INSERT INTO schema_version VALUES (?, ?, ?)",
                              (num, nom, dt.datetime.now(dt.UTC).isoformat(timespec="seconds")))
            for num, _, _, descente in reversed(MIGRATIONS):
                if cible < num <= actuelle:
                    c.executescript(descente)
                    c.execute("DELETE FROM schema_version WHERE version = ?", (num,))
            c.commit()
        return self.version()

    # ------------------------------------------------------------------ accès génériques
    def lire(self, sql, args=()):
        return [_ligne(r) for r in self.cx().execute(sql, args).fetchall()]

    def un(self, sql, args=()):
        return _ligne(self.cx().execute(sql, args).fetchone())

    def ecrire(self, sql, args=()):
        with self._ecriture:
            c = self.cx()
            cur = c.execute(sql, args)
            c.commit()
            return cur.lastrowid if sql.lstrip().upper().startswith("INSERT") else cur.rowcount

    # ------------------------------------------------------------------ journal
    def evenement(self, genre, message, agent=None, mission=None, niveau="info"):
        return self.ecrire("INSERT INTO evenements(ts, agent, mission, niveau, genre, message) VALUES (?,?,?,?,?,?)",
                           (time.time(), agent, mission, niveau, genre, str(message)[:2000]))

    # ------------------------------------------------------------------ missions
    def nouvelle_mission(self, agent, genre, titre, params=None, objectif="", priorite=5, demandeur="jabran",
                         parent=None, boucle=None, tentatives_max=2):
        return self.ecrire(
            "INSERT INTO missions(agent, type, titre, objectif, params, priorite, demandeur, parent, boucle,"
            " tentatives_max, cree) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (agent, genre, str(titre)[:200], str(objectif)[:1000], _json(params), int(priorite), demandeur,
             parent, boucle, int(tentatives_max), time.time()))

    def mission(self, ident):
        return self.un("SELECT * FROM missions WHERE id=?", (ident,))

    def prendre_mission(self, types=None):
        """Réserve la prochaine mission prête. Atomique : deux ouvriers ne prennent jamais la même."""
        maintenant = time.time()
        with self._ecriture:
            c = self.cx()
            sql = "SELECT id FROM missions WHERE statut='en_attente' AND pas_avant<=?"
            args = [maintenant]
            if types is not None:
                if not types:
                    return None
                sql += f" AND type IN ({','.join('?' * len(types))})"
                args += list(types)
            r = c.execute(sql + " ORDER BY priorite, id LIMIT 1", args).fetchone()
            if r is None:
                return None
            c.execute("UPDATE missions SET statut='en_cours', debut=?, battement=?, tentatives=tentatives+1,"
                      " phase='attente', role='', etape='Prise en charge', erreur=NULL WHERE id=?",
                      (maintenant, maintenant, r["id"]))
            c.commit()
        return self.mission(r["id"])

    def terminer(self, ident, resultat):
        self.ecrire("UPDATE missions SET statut='terminee', phase='termine', role='', etape='Terminé', fin=?,"
                    " resultat=? WHERE id=?", (time.time(), _json(resultat), ident))

    def echouer(self, ident, erreur, reessayer_dans=None):
        erreur = str(erreur)
        if reessayer_dans is not None:
            self.ecrire("UPDATE missions SET statut='en_attente', phase='attente', role='', etape=?, erreur=?,"
                        " pas_avant=? WHERE id=?",
                        (f"Nouvel essai prévu ({erreur[:120]})", erreur[:2000], time.time() + reessayer_dans, ident))
        else:
            self.ecrire("UPDATE missions SET statut='erreur', phase='erreur', role='', etape=?, erreur=?, fin=?"
                        " WHERE id=?", (erreur[:300], erreur[:2000], time.time(), ident))

    def annuler(self, ident):
        return self.ecrire("UPDATE missions SET statut='annulee', phase='annule', etape='Annulée par Jabran', fin=?"
                           " WHERE id=? AND statut='en_attente'", (time.time(), ident)) > 0

    def reprendre_interrompues(self):
        """Au démarrage : une mission « en cours » a été coupée par un arrêt -> elle retourne dans la file."""
        ids = [r["id"] for r in self.lire("SELECT id FROM missions WHERE statut='en_cours'")]
        for i in ids:
            self.ecrire("UPDATE missions SET statut='en_attente', phase='attente', role='',"
                        " etape='Reprise après un arrêt du programme', pas_avant=0,"
                        " tentatives=MAX(tentatives-1, 0) WHERE id=?", (i,))
            self.ecrire("UPDATE etapes SET statut='interrompue', fin=? WHERE mission=? AND statut='en_cours'",
                        (time.time(), i))
        return ids

    # ------------------------------------------------------------------ étapes réellement exécutées
    def debut_etape(self, mission, agent, phase, libelle, role=""):
        maintenant = time.time()
        with self._ecriture:
            self.ecrire("UPDATE etapes SET statut='faite', fin=? WHERE mission=? AND statut='en_cours'",
                        (maintenant, mission))
            ident = self.ecrire("INSERT INTO etapes(mission, agent, role, phase, libelle, debut) VALUES (?,?,?,?,?,?)",
                                (mission, agent, role, phase, str(libelle)[:300], maintenant))
            self.ecrire("UPDATE missions SET phase=?, role=?, etape=?, battement=?, etapes_faites=etapes_faites+1"
                        " WHERE id=?", (phase, role, str(libelle)[:300], maintenant, mission))
        return ident

    def fin_etapes(self, mission, statut="faite"):
        self.ecrire("UPDATE etapes SET statut=?, fin=? WHERE mission=? AND statut='en_cours'",
                    (statut, time.time(), mission))

    # ------------------------------------------------------------------ documents et messages
    def document(self, agent, genre, titre, contenu, donnees=None, sources=None, mission=None, role="",
                 statut="brouillon"):
        return self.ecrire(
            "INSERT INTO documents(agent, mission, role, genre, titre, contenu, donnees, sources, statut, cree)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (agent, mission, role, genre, str(titre)[:200], contenu, _json(donnees), _json(sources or []),
             statut, time.time()))

    def message(self, de, a, genre, contenu, mission=None, document=None):
        return self.ecrire("INSERT INTO messages(ts, de, a, mission, document, genre, contenu) VALUES (?,?,?,?,?,?,?)",
                           (time.time(), de, a, mission, document, genre, str(contenu)[:2000]))
