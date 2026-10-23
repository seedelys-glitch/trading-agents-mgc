# -*- coding: utf-8 -*-
"""
Mémoire de l'analyste : base SQLite (rapports\\salle\\analyste.sqlite), migrations versionnées et réversibles,
sauvegarde automatique quotidienne (rapports\\salle\\sauvegardes, 30 jours gardés).

Trois choses bien distinctes :
  analyses   ce que le desk a conclu (une ligne par analyse, avec son instantané de données)
  resultats  les scénarios SUIVIS que Jabran a notés avec /resultat (paper trading)
  trades réels : restent dans le journal de Jarvis (journal\\trades.jsonl), lu en lecture seule (journal_jarvis.py)
"""

import datetime as dt
import json
import sqlite3
from contextlib import closing
from pathlib import Path

RAPPORTS = Path(__file__).resolve().parent.parent.parent / "rapports" / "salle"
FICHIER = RAPPORTS / "analyste.sqlite"
SAUVEGARDES = RAPPORTS / "sauvegardes"

# (version, nom, montée, descente) : chaque migration se défait par sa descente
MIGRATIONS = [
    (1, "tables de départ", """
        CREATE TABLE configs (hash TEXT PRIMARY KEY, contenu TEXT NOT NULL, vue_le TEXT NOT NULL);
        CREATE TABLE analyses (
            id TEXT PRIMARY KEY, debut TEXT, fin TEXT, duree_s REAL, contrat TEXT, moteur TEXT, modele TEXT,
            appels INTEGER, source_donnees TEXT, statut_donnees TEXT, statut TEXT, sens TEXT, niveau_fibo TEXT,
            entree REAL, stop REAL, tp1 REAL, tp2 REAL, tp3 REAL, contrats INTEGER, risque_net_contrat REAL,
            ratio_net_tp1 REAL, regime TEXT, config_hash TEXT REFERENCES configs(hash), version_prompt TEXT, erreur TEXT);
        CREATE TABLE instantanes (analyse_id TEXT PRIMARY KEY REFERENCES analyses(id), donnees TEXT NOT NULL);
        CREATE TABLE avis_agents (analyse_id TEXT REFERENCES analyses(id), agent TEXT, tour INTEGER, biais TEXT,
            confiance INTEGER, texte TEXT, erreur TEXT);
        CREATE TABLE vetos (analyse_id TEXT REFERENCES analyses(id), famille TEXT, motif TEXT);
        CREATE TABLE resultats (analyse_id TEXT PRIMARY KEY REFERENCES analyses(id), issue TEXT NOT NULL,
            prix_sortie REAL, pnl_points REAL, r_multiple REAL, pnl_usd_net REAL, note_le TEXT, source TEXT);
        CREATE TABLE llm_calls (id INTEGER PRIMARY KEY AUTOINCREMENT, analyse_id TEXT, agent TEXT, fournisseur TEXT,
            modele TEXT, debut TEXT, fin TEXT, duree_s REAL, jetons_entree INTEGER, jetons_sortie INTEGER,
            cout_usd REAL, statut TEXT, erreur TEXT, tentatives INTEGER, version_prompt TEXT);
        CREATE TABLE evenements (id INTEGER PRIMARY KEY AUTOINCREMENT, quand TEXT, niveau TEXT, genre TEXT, message TEXT);
        CREATE INDEX analyses_debut ON analyses(debut);
        CREATE INDEX llm_calls_analyse ON llm_calls(analyse_id);
    """, """
        DROP TABLE evenements; DROP TABLE llm_calls; DROP TABLE resultats; DROP TABLE vetos;
        DROP TABLE avis_agents; DROP TABLE instantanes; DROP TABLE analyses; DROP TABLE configs;
    """),
]


COLONNES = ["id", "debut", "fin", "duree_s", "contrat", "moteur", "modele", "appels", "source_donnees", "statut_donnees",
            "statut", "sens", "niveau_fibo", "entree", "stop", "tp1", "tp2", "tp3", "contrats", "risque_net_contrat",
            "ratio_net_tp1", "regime", "config_hash", "version_prompt", "erreur"]


def version(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL, nom TEXT, le TEXT)")
    ligne = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return ligne[0] or 0


def migrer(conn, cible=None):
    """Monte (ou redescend) le schéma jusqu'à la version `cible` (par défaut : la dernière)."""
    cible = MIGRATIONS[-1][0] if cible is None else cible
    actuelle = version(conn)
    with conn:
        for num, nom, montee, _ in MIGRATIONS:
            if actuelle < num <= cible:
                conn.executescript(montee)
                conn.execute("INSERT INTO schema_version VALUES (?, ?, ?)", (num, nom, maintenant()))
        for num, _, _, descente in reversed(MIGRATIONS):
            if cible < num <= actuelle:
                conn.executescript(descente)
                conn.execute("DELETE FROM schema_version WHERE version = ?", (num,))
    return version(conn)


def maintenant():
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def ouvrir(fichier=FICHIER):
    Path(fichier).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(fichier, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    migrer(conn)
    return conn


def sauvegarder(fichier=FICHIER, dossier=SAUVEGARDES, garder=30, jour=None):
    """Copie du jour (une seule par jour), faite par SQLite lui-même (sûre même base ouverte)."""
    jour = jour or dt.date.today().isoformat()
    cible = Path(dossier) / f"analyste-{jour}.sqlite"
    if cible.exists() or not Path(fichier).exists():
        return None
    cible.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(fichier)) as source, closing(sqlite3.connect(cible)) as copie:
        source.backup(copie)
    for vieux in sorted(Path(dossier).glob("analyste-*.sqlite"))[:-garder]:
        vieux.unlink()
    return cible


def _iso(horodatage):
    return dt.datetime.fromtimestamp(horodatage, dt.UTC).isoformat(timespec="seconds") if horodatage else None


def enregistrer_analyse(conn, a, config=None, config_hash=None, version_prompt=None):
    """Range une analyse du desk (dictionnaire de serveur.py) ; la refaire remplace l'ancienne version."""
    d = a.get("decision") or {}
    s = d.get("setup") or {}
    r = d.get("risque") or {}
    reg = d.get("regime") or {}
    don = d.get("donnees") or {}
    config_hash = config_hash or don.get("config")
    with conn:
        if config is not None and config_hash:
            conn.execute("INSERT OR IGNORE INTO configs VALUES (?, ?, ?)",
                         (config_hash, json.dumps(config, ensure_ascii=False, sort_keys=True, default=str), maintenant()))
        elif config_hash:
            conn.execute("INSERT OR IGNORE INTO configs VALUES (?, ?, ?)", (config_hash, "{}", maintenant()))
        for table in ("vetos", "avis_agents", "instantanes", "llm_calls"):
            conn.execute(f"DELETE FROM {table} WHERE analyse_id = ?", (a["id"],))  # noqa: S608 (nom fixe)
        # mise à jour sur place (pas de REPLACE : il effacerait la ligne et casserait le lien avec un résultat déjà noté)
        conn.execute(f"INSERT INTO analyses VALUES ({','.join('?' * len(COLONNES))}) ON CONFLICT(id) DO UPDATE SET "
                     + ", ".join(f"{c} = excluded.{c}" for c in COLONNES[1:]), (
            a["id"], _iso(a.get("debut")), _iso(a.get("fin")),
            round(a["fin"] - a["debut"], 1) if a.get("fin") and a.get("debut") else None,
            d.get("contrat") or a.get("ticker"), a.get("moteur"), a.get("modele"), a.get("appels"),
            don.get("source"), don.get("statut"), d.get("statut") or d.get("decision"), s.get("sens"), s.get("niveau"),
            s.get("entree"), s.get("stop"), s.get("tp1"), s.get("tp2"), s.get("tp3"),
            r.get("contrats"), r.get("risque_net_par_contrat"), r.get("ratio_net_tp1"), reg.get("regime"),
            config_hash, version_prompt, a.get("erreur")))
        if a.get("donnees") is not None:
            conn.execute("INSERT INTO instantanes VALUES (?, ?)",
                         (a["id"], json.dumps(a["donnees"], ensure_ascii=False, default=str)))
        for famille, cle in (("structurel", "vetos"), ("informatif", "vetos_informatifs")):
            conn.executemany("INSERT INTO vetos VALUES (?, ?, ?)", [(a["id"], famille, m) for m in d.get(cle) or []])
        for agent, suivi in (a.get("specialistes") or {}).items():
            for tour in (1, 2):
                avis = suivi.get(f"tour{tour}")
                if avis:
                    conn.execute("INSERT INTO avis_agents VALUES (?, ?, ?, ?, ?, ?, ?)", (
                        a["id"], agent, tour, avis.get("biais"), avis.get("confiance"),
                        avis.get("argument") or avis.get("reponse"), None))
            if suivi.get("erreur"):
                conn.execute("INSERT INTO avis_agents VALUES (?, ?, 1, NULL, NULL, NULL, ?)", (a["id"], agent, suivi["erreur"]))
        conn.executemany(
            "INSERT INTO llm_calls (analyse_id, agent, fournisseur, modele, debut, fin, duree_s, jetons_entree, "
            "jetons_sortie, cout_usd, statut, erreur, tentatives, version_prompt) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(a["id"], c.get("agent"), c.get("fournisseur"), c.get("modele"), c.get("debut"), c.get("fin"),
              c.get("duree_s"), c.get("jetons_entree"), c.get("jetons_sortie"), c.get("cout_usd", 0.0), c.get("statut"),
              c.get("erreur"), c.get("tentatives", 1), c.get("version_prompt")) for c in a.get("llm_calls") or []])


def enregistrer_resultat(conn, analyse_id, issue, prix_sortie, config, source="telegram"):
    """Résultat d'un scénario suivi. P&L calculé à partir de l'entrée et du stop de l'analyse (si elle en avait)."""
    from .instrument import points_en_usd

    ligne = conn.execute("SELECT sens, entree, stop, contrats FROM analyses WHERE id = ?", (analyse_id,)).fetchone()
    if ligne is None:
        raise KeyError(analyse_id)
    pnl_points = r_multiple = pnl_usd = None
    if ligne["entree"] and ligne["stop"] and ligne["sens"]:
        sens = 1 if ligne["sens"] == "achat" else -1
        pnl_points = round(sens * (prix_sortie - ligne["entree"]), 2)
        r_multiple = round(pnl_points / abs(ligne["entree"] - ligne["stop"]), 2)
        contrats = ligne["contrats"] or 1
        couts = config["frais_aller_retour_usd"] + 2 * config["glissement_ticks_par_cote"]
        pnl_usd = round(points_en_usd(pnl_points, contrats) - couts * contrats, 2)
    with conn:
        conn.execute("INSERT OR REPLACE INTO resultats VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (analyse_id, issue, prix_sortie, pnl_points, r_multiple, pnl_usd, maintenant(), source))
    return {"pnl_points": pnl_points, "r_multiple": r_multiple, "pnl_usd_net": pnl_usd}


def evenement(conn, genre, message, niveau="info"):
    with conn:
        conn.execute("INSERT INTO evenements (quand, niveau, genre, message) VALUES (?, ?, ?, ?)",
                     (maintenant(), niveau, genre, message))
