# -*- coding: utf-8 -*-
"""
La mémoire de l'université : le Scribe (agent 15) note tout en blocs, l'Archiviste (agent 16) les retrouve.

Le Scribe relit, depuis son dernier passage, tout ce qui s'est réellement passé :
  - les missions terminées des agents (étapes, documents, messages, erreurs) ;
  - la conversation de Jabran avec le directeur (via Jarvis) ;
  - le chat du desk de Jarvis (Documents\\Jarvis\\.cache\\desk-chat.json), ce que Jarvis retient
    (memoire-jarvis.txt) et les notes dictées (notes-jarvis.txt) ;
  - les sessions Claude Code du PC (~\\.claude\\projects\\…\\*.jsonl) : seulement ce que Jabran a écrit et ce que
    Claude a répondu, jamais le contenu des fichiers lus ni les sorties des commandes ;
  - les règles validées ou rejetées par Jabran, les alertes et erreurs du journal ;
  - PROJECT_STATUS.md (une section = un bloc, mis à jour quand elle change) ;
  - les notes déposées dans rapports\\universite\\memoire\\a_ranger (par exemple le résumé d'une session Claude
    faite dans l'application) ou envoyées par POST /api/memoire/noter (Jarvis, une autre session…).
Chaque bloc est rangé dans UN dossier de sujet (Jarvis, Université, Stratégie…) pour ne rien mélanger, et
recopié en Markdown dans rapports\\universite\\memoire\\<dossier>\\<mois>.md, avec un INDEX.md général.

L'index de recherche est une table FTS5 de SQLite (accents ignorés) : une recherche prend quelques millisecondes.
Rien n'est inventé ni résumé par une IA : un bloc ne contient que du texte réellement écrit ou enregistré.
Les secrets (clés API, tokens, mots de passe, lignes CLE=valeur) sont masqués avant d'être écrits.
"""

import datetime as dt
import hashlib
import html
import json
import re
import shutil
import time
import unicodedata
from pathlib import Path
from zoneinfo import ZoneInfo

from . import agents

SCRIBE, ARCHIVISTE = 15, 16
PARIS = ZoneInfo("Europe/Paris")
TEXTE_MAX = 6000            # caractères au plus par bloc
MESSAGE_MAX = 1500          # caractères au plus par message dans un bloc
INTERVALLE_SCRIBE_S = 300   # le Scribe repasse toutes les 5 minutes
LECTURE_MAX = 8_000_000     # octets lus au plus par fichier de session et par passage

# ------------------------------------------------------------------ dossiers de sujet
DOSSIERS = [
    ("Jarvis", r"jarvis|telegram|android|apk|appli\b|voix|whisper|gardien|chef d'orchestre|clap"),
    ("Université", r"universite|directeur|agent \d+|bureau 3d|bureau immersif|scribe|archiviste|bibliotheque|boucles?"),
    ("Analyse technique", r"smc|bos|choch|fibo\w*|ichimoku|vwap|ema ?200|order ?blocks?|fvg|delta|heatmap|bookmap"),
    ("Macro et discours", r"fed\b|powell|fomc|cpi|nfp|discours|calendrier|annonces?|macro|taux"),
    ("Risque", r"risques?|vetos?|perte du jour|drawdown|stop loss"),
    ("Données et replays", r"tradingview|yahoo|ninjatrader|bougies|csv|imports?\b|replay|backtest|monte.?carlo"),
    ("Stratégie", r"strategie|cascade|weekly|48 ?min|12 ?min|objectifs?|compte [ab]\b|break.?even|prop ?firm|topstep"),
    ("Salle des marchés", r"salle des marches|desk|specialistes?"),
    ("PC et installation", r"install\w*|\bpc\b|windows|lm ?studio|gpu|carte graphique|github|\bgit\b|pytest|redemarr\w*|\.bat\b"),
]
DIVERS = "Divers"
NOMS_DOSSIERS = [d for d, _ in DOSSIERS] + [DIVERS]
_MOTIFS_DOSSIERS = [(d, re.compile(rf"(?<![a-z])(?:{m})")) for d, m in DOSSIERS]
# Dossier des missions de chaque agent
AGENT_DOSSIER = {1: "Analyse technique", 2: "Analyse technique", 3: "Analyse technique", 4: "Analyse technique",
                 6: "Analyse technique", 7: "Analyse technique", 5: "Macro et discours", 10: "Macro et discours",
                 11: "Macro et discours", 12: "Macro et discours", 8: "Risque", 13: "Données et replays"}
TYPES_IGNORES = ("ecriture_memoire", "verification_memoire")   # le Scribe ne se note pas lui-même

# ------------------------------------------------------------------ secrets
_SECRETS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"gsk_[0-9A-Za-z]{20,}"),
    re.compile(r"(?:sk|pk|rk)-[0-9A-Za-z_\-]{16,}"),
    re.compile(r"gh[pousr]_[0-9A-Za-z]{20,}|github_pat_[0-9A-Za-z_]{20,}"),
    re.compile(r"xox[abpr]-[0-9A-Za-z\-]{10,}"),
    re.compile(r"\b\d{6,12}:[0-9A-Za-z_\-]{30,}\b"),                      # token de bot Telegram
    re.compile(r"(?i)bearer\s+[0-9A-Za-z._\-]{10,}"),
    re.compile(r"\b(?=[0-9A-Za-z_\-]*\d)(?=[0-9A-Za-z_\-]*[A-Za-z])[0-9A-Za-z_\-]{40,}\b"),   # longue chaîne aléatoire
]
_CLE_VALEUR = re.compile(r"(?i)\b(api[_-]?key|token|password|passwd|mot[_ ]de[_ ]passe|secret|pwd|client[_-]?secret)"
                         r"\b(\s*[=:]\s*)\S+")
_LIGNE_ENV = re.compile(r"(?m)^(\s*[A-Z][A-Z0-9_]{2,}\s*=\s*)\S.*$")   # lignes du style CLE=valeur (.env, reglages.txt)


def masquer(texte):
    """Masque les secrets d'un texte avant de l'écrire dans la mémoire."""
    texte = str(texte or "")
    for motif in _SECRETS:
        texte = motif.sub("[masqué]", texte)
    texte = _CLE_VALEUR.sub(lambda m: f"{m.group(1)}{m.group(2)}[masqué]", texte)
    return _LIGNE_ENV.sub(lambda m: f"{m.group(1)}[masqué]", texte)


# ------------------------------------------------------------------ outils
def plat(texte):
    t = unicodedata.normalize("NFD", str(texte or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in t if unicodedata.category(c) != "Mn")).strip()


def court(texte, n):
    texte = " ".join(str(texte or "").split())
    return texte if len(texte) <= n else texte[: n - 1].rstrip() + "…"


def date_paris(ts, format_="%d/%m/%Y %Hh%M"):
    return dt.datetime.fromtimestamp(float(ts), dt.UTC).astimezone(PARIS).strftime(format_) if ts else "?"


def _ts_iso(texte):
    try:
        return dt.datetime.fromisoformat(str(texte).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _nom_agent(n):
    a = agents.agent(n) if isinstance(n, int) or str(n).isdigit() else None
    return a["nom"] if a else str(n)


def dossier_nomme(nom):
    """« universite », « Université » -> « Université » ; None si ce n'est pas un dossier connu."""
    return next((d for d in NOMS_DOSSIERS if plat(d) == plat(nom)), None) if nom else None


def classer(texte, indice=None):
    """Le dossier de sujet d'un texte : le plus de mots-clés trouvés (un indice, comme le dossier de travail, compte triple)."""
    t = plat(texte)
    scores = {d: len(m.findall(t)) for d, m in _MOTIFS_DOSSIERS}
    if indice in scores:
        scores[indice] += 3
    meilleur = max(scores, key=lambda d: scores[d])   # à égalité : l'ordre de DOSSIERS
    return meilleur if scores[meilleur] else (indice if indice in NOMS_DOSSIERS else DIVERS)


def nom_fichier(dossier):
    """Nom de dossier sur le disque (sans accents, pour éviter les surprises sous Windows)."""
    return re.sub(r"[^A-Za-z0-9 _-]", "", unicodedata.normalize("NFKD", dossier).encode("ascii", "ignore").decode()) or DIVERS


def dossier_memoire(base):
    return Path(base.fichier).parent / "memoire"


# ------------------------------------------------------------------ index FTS5
def preparer(base):
    """Crée l'index de recherche (FTS5) s'il manque et le remplit. Renvoie True si FTS5 est disponible."""
    if getattr(base, "_memoire_fts", None) is not None:
        return base._memoire_fts
    try:
        with base._ecriture:
            c = base.cx()
            neuf = not c.execute("SELECT name FROM sqlite_master WHERE name='memoire_index'").fetchone()
            c.executescript("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memoire_index USING fts5(
                    titre, texte, dossier, session, mots, content='memoire_blocs', content_rowid='id',
                    tokenize='unicode61 remove_diacritics 2');
                CREATE TRIGGER IF NOT EXISTS memoire_blocs_ai AFTER INSERT ON memoire_blocs BEGIN
                    INSERT INTO memoire_index(rowid, titre, texte, dossier, session, mots)
                    VALUES (new.id, new.titre, new.texte, new.dossier, new.session, new.mots); END;
                CREATE TRIGGER IF NOT EXISTS memoire_blocs_ad AFTER DELETE ON memoire_blocs BEGIN
                    INSERT INTO memoire_index(memoire_index, rowid, titre, texte, dossier, session, mots)
                    VALUES ('delete', old.id, old.titre, old.texte, old.dossier, old.session, old.mots); END;
                CREATE TRIGGER IF NOT EXISTS memoire_blocs_au AFTER UPDATE ON memoire_blocs BEGIN
                    INSERT INTO memoire_index(memoire_index, rowid, titre, texte, dossier, session, mots)
                    VALUES ('delete', old.id, old.titre, old.texte, old.dossier, old.session, old.mots);
                    INSERT INTO memoire_index(rowid, titre, texte, dossier, session, mots)
                    VALUES (new.id, new.titre, new.texte, new.dossier, new.session, new.mots); END;
            """)
            if neuf:
                c.execute("INSERT INTO memoire_index(memoire_index) VALUES ('rebuild')")
            c.commit()
        base._memoire_fts = True
    except Exception:  # noqa: BLE001 : SQLite sans FTS5 -> recherche simple par LIKE
        base._memoire_fts = False
    return base._memoire_fts


# ------------------------------------------------------------------ écriture des blocs
def curseur(base, source, defaut=None):
    r = base.un("SELECT position FROM memoire_curseurs WHERE source=?", (source,))
    return r["position"] if r else defaut


def avancer(base, source, position):
    base.ecrire("INSERT INTO memoire_curseurs(source, position, maj) VALUES (?,?,?)"
                " ON CONFLICT(source) DO UPDATE SET position=excluded.position, maj=excluded.maj",
                (source, str(position), time.time()))


def enregistrer_bloc(base, ref, genre, source, titre, texte, session="", debut=None, fin=None, agents_=(),
                     dossier=None, indice=None):
    """Écrit (ou met à jour) un bloc. Renvoie (id, changement) ; changement = None si le bloc était déjà identique."""
    preparer(base)
    titre = court(masquer(titre), 200) or "(sans titre)"
    texte = masquer(texte)
    if len(texte) > TEXTE_MAX:
        texte = texte[: TEXTE_MAX - 1].rstrip() + "…"
    session = court(masquer(session), 160)
    dossier = dossier if dossier in NOMS_DOSSIERS else classer(f"{titre}\n{texte}", indice)
    noms = [_nom_agent(a) for a in agents_ if a not in (None, "")]
    mots = " ".join(dict.fromkeys(plat(" ".join([genre, source, dossier] + noms)).split()))
    debut = float(debut or time.time())
    fin = float(fin or debut)
    empreinte = hashlib.sha1(f"{titre}\n{texte}\n{session}\n{dossier}".encode("utf-8")).hexdigest()
    ancien = base.un("SELECT id, empreinte FROM memoire_blocs WHERE ref=?", (ref,))
    if ancien and ancien["empreinte"] == empreinte:
        return ancien["id"], None
    agents_json = json.dumps([a for a in agents_ if a not in (None, "")], ensure_ascii=False)
    if ancien:
        base.ecrire("UPDATE memoire_blocs SET genre=?, source=?, session=?, dossier=?, titre=?, texte=?, mots=?, agents=?,"
                    " debut=?, fin=?, empreinte=?, maj=? WHERE id=?",
                    (genre, source, session, dossier, titre, texte, mots, agents_json, debut, fin, empreinte,
                     time.time(), ancien["id"]))
        return ancien["id"], "maj"
    ident = base.ecrire("INSERT INTO memoire_blocs(ref, genre, source, session, dossier, titre, texte, mots, agents,"
                        " debut, fin, empreinte, cree, maj) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (ref, genre, source, session, dossier, titre, texte, mots, agents_json, debut, fin,
                         empreinte, time.time(), time.time()))
    return ident, "nouveau"


def noter(base, texte, titre="", source="note", session="", dossier=None, quand=None, agents_=()):
    """Une note envoyée par Jarvis, une session Claude ou le bureau (POST /api/memoire/noter)."""
    texte = str(texte or "").strip()
    if not texte:
        raise ValueError("texte vide")
    source = re.sub(r"[^a-z0-9_-]", "", plat(source))[:30] or "note"
    cle = hashlib.sha1(f"{source}\n{session}\n{titre}\n{texte}".encode("utf-8")).hexdigest()[:20]
    ident, changement = enregistrer_bloc(base, f"note:{source}:{cle}", "note", source, titre or court(texte, 80), texte,
                                         session=session, debut=quand, agents_=agents_,
                                         dossier=dossier_nomme(dossier))
    return {"bloc": ident, "nouveau": changement == "nouveau", "dossier": bloc(base, ident)["dossier"]}


# ------------------------------------------------------------------ sources du Scribe
def _source_missions(base, compteur):
    depuis = float(curseur(base, "missions", 0))
    missions = base.lire("SELECT * FROM missions WHERE statut IN ('terminee','erreur','annulee') AND fin>?"
                         " ORDER BY fin LIMIT 500", (depuis,))
    for m in missions:
        if m["type"] not in TYPES_IGNORES:
            _bloc_mission(base, m, compteur)
        depuis = max(depuis, m["fin"] or 0)
    avancer(base, "missions", depuis)


def _dossier_mission(base, m):
    params = m["params"] if isinstance(m["params"], dict) else {}
    n = m["agent"]
    if n == agents.DIRECTEUR and params.get("type"):
        from . import competences
        comp = competences.TYPES.get(params["type"])
        n = comp.AGENT if comp else n
    if n == 9 and params.get("document"):
        d = base.un("SELECT agent FROM documents WHERE id=?", (int(params["document"]),))
        n = d["agent"] if d else n
    return AGENT_DOSSIER.get(n)


def _bloc_mission(base, m, compteur):
    etat = {"terminee": "terminée", "erreur": "en erreur", "annulee": "annulée"}.get(m["statut"], m["statut"])
    lignes = [f"Mission n° {m['id']} « {m['titre']} » confiée à {_nom_agent(m['agent'])} (agent {m['agent']}) "
              f"par {m['demandeur']} : {etat}."]
    if m["objectif"]:
        lignes.append(f"Consigne : {court(m['objectif'], 600)}")
    if m["parent"]:
        lignes.append(f"Demandée pendant la mission n° {m['parent']}.")
    etapes = base.lire("SELECT role, libelle, statut FROM etapes WHERE mission=? ORDER BY id", (m["id"],))
    if etapes:
        lignes.append("Étapes : " + " ; ".join(f"{e['role'] or '-'} : {e['libelle']}" for e in etapes[:20]))
    for d in base.lire("SELECT id, titre, statut, contenu FROM documents WHERE mission=? ORDER BY id", (m["id"],)):
        lignes.append(f"Document n° {d['id']} « {d['titre']} » ({d['statut']}) : {court(d['contenu'], 900)}")
    messages = base.lire("SELECT de, a, genre, contenu FROM messages WHERE mission=? ORDER BY id", (m["id"],))
    for x in messages[:10]:
        lignes.append(f"Message {_nom_agent(x['de'])} → {_nom_agent(x['a'])} ({x['genre']}) : {court(x['contenu'], 300)}")
    if m["erreur"]:
        lignes.append(f"Erreur : {court(m['erreur'], 400)}")
    participants = [m["agent"]] + [x["de"] for x in messages] + [x["a"] for x in messages]
    racine = m["parent"] or m["id"]
    _, ch = enregistrer_bloc(base, f"mission:{m['id']}", "mission", "universite", f"{m['titre']} ({etat})",
                             "\n".join(lignes), session=f"Université · mission n° {racine}", debut=m["debut"] or m["cree"],
                             fin=m["fin"], agents_=list(dict.fromkeys(participants)),
                             dossier=_dossier_mission(base, m), indice="Université")
    compteur(ch)


def _paires(lignes, est_jabran, ident):
    """Regroupe une question de Jabran avec les réponses qui la suivent. Renvoie (paires complètes, dernier id sûr)."""
    paires, courante, sur = [], None, None
    for x in lignes:
        if est_jabran(x):
            if courante:          # question suivante : la précédente est finie (même sans réponse)
                paires.append(courante)
                sur = ident(courante[1][-1] if courante[1] else courante[0])
            courante = (x, [])
        elif courante is not None:
            courante[1].append(x)
        else:
            sur = ident(x)
    if courante and courante[1]:
        paires.append(courante)
        sur = ident(courante[1][-1])
    return paires, sur


def _source_directeur(base, compteur):
    depuis = int(curseur(base, "directeur", 0))
    lignes = base.lire("SELECT * FROM conversation WHERE id>? ORDER BY id LIMIT 1000", (depuis,))
    paires, sur = _paires(lignes, lambda x: x["de"] == "jabran", lambda x: x["id"])
    for q, reps in paires:
        texte = f"Jabran ({q['origine'] or 'jarvis'}) : {court(q['texte'], MESSAGE_MAX)}\n" + "\n".join(
            f"Directeur : {court(r['texte'], MESSAGE_MAX)}" for r in reps)
        missions = [r["mission"] for r in reps if r["mission"]]
        if missions:
            texte += f"\nMission lancée : n° {missions[-1]}."
        _, ch = enregistrer_bloc(base, f"directeur:{q['id']}", "conversation", "directeur",
                                 f"Jabran au directeur : {court(q['texte'], 120)}", texte,
                                 session=f"Directeur (via Jarvis) · {date_paris(q['ts'], '%d/%m/%Y')}",
                                 debut=q["ts"], fin=(reps or [q])[-1]["ts"], agents_=[agents.DIRECTEUR], indice="Université")
        compteur(ch)
    if sur is not None:
        avancer(base, "directeur", sur)


def _source_desk_jarvis(base, compteur, dossier_jarvis):
    if not dossier_jarvis:
        return
    f = Path(dossier_jarvis) / ".cache" / "desk-chat.json"
    try:
        messages = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(messages, list):
        return
    depuis = int(curseur(base, "jarvis_desk", 0))
    lignes = sorted((m for m in messages if isinstance(m, dict) and int(m.get("id") or 0) > depuis
                     and not m.get("attente")), key=lambda m: int(m["id"]))
    paires, sur = _paires(lignes, lambda x: x.get("de") == "jabran", lambda x: int(x["id"]))
    for q, reps in paires:
        noms = ", ".join(dict.fromkeys(r.get("nom") or r.get("de") for r in reps)) or "Jarvis"
        texte = f"Jabran ({q.get('origine') or 'jarvis'}) : {court(q.get('texte'), MESSAGE_MAX)}\n" + "\n".join(
            f"{r.get('nom') or r.get('de')} : {court(r.get('texte'), MESSAGE_MAX)}" for r in reps)
        directeur = any(r.get("de") == "directeur" for r in reps)
        _, ch = enregistrer_bloc(base, f"desk:{q['id']}", "conversation", "jarvis",
                                 f"Jabran à {noms} : {court(q.get('texte'), 110)}", texte,
                                 session=f"Chat du desk (Jarvis) · {date_paris(q.get('heure'), '%d/%m/%Y')}",
                                 debut=q.get("heure"), fin=(reps or [q])[-1].get("heure"),
                                 indice="Université" if directeur else "Salle des marchés")
        compteur(ch)
    if sur is not None:
        avancer(base, "jarvis_desk", sur)


def _source_fichiers_jarvis(base, compteur, dossier_jarvis):
    """Ce que Jarvis retient (« Jarvis, retiens que… ») et les notes dictées : une ligne = un bloc."""
    if not dossier_jarvis:
        return
    for nom, genre, titre in (("memoire-jarvis.txt", "souvenir", "Jarvis retient"), ("notes-jarvis.txt", "note", "Note dictée")):
        f = Path(dossier_jarvis) / nom
        try:
            lignes = [x.strip() for x in f.read_text(encoding="utf-8").splitlines() if x.strip() and not x.lstrip().startswith("#")]
            quand_fichier = f.stat().st_mtime
        except OSError:
            continue
        for x in lignes:
            m = re.match(r"^-?\s*(\d{2})/(\d{2})/(\d{4})\s*:\s*(.*)$", x)
            texte = (m.group(4) if m else x.lstrip("- ")).strip()
            quand = dt.datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)), 12, tzinfo=PARIS).timestamp() if m else quand_fichier
            cle = hashlib.sha1(x.encode("utf-8")).hexdigest()[:16]
            _, ch = enregistrer_bloc(base, f"jarvis:{nom}:{cle}", genre, "jarvis", f"{titre} : {court(texte, 110)}", texte,
                                     session=f"Jarvis · {nom}", debut=quand, indice="Jarvis")
            compteur(ch)


def _source_regles(base, compteur):
    depuis = float(curseur(base, "regles", 0))
    for r in base.lire("SELECT * FROM regles WHERE decision_le>? ORDER BY decision_le LIMIT 500", (depuis,)):
        mot = {"validee": "validée", "rejetee": "rejetée", "remplacee": "remplacée"}.get(r["statut"], r["statut"])
        texte = f"Règle « {r['titre']} » (thème {r['theme'] or '-'}, version {r['version']}) {mot} par {r['decide_par'] or 'Jabran'}.\n{r['texte']}"
        if r["note"]:
            texte += f"\nNote : {r['note']}"
        _, ch = enregistrer_bloc(base, f"regle:{r['id']}:{r['statut']}", "decision", "bibliotheque",
                                 f"Règle {mot} : {r['titre']}", texte, session="Bibliothèque des règles",
                                 debut=r["decision_le"], agents_=[9], dossier="Stratégie")
        compteur(ch)
        depuis = max(depuis, r["decision_le"])
    avancer(base, "regles", depuis)


def _source_journal(base, compteur):
    depuis = int(curseur(base, "journal", 0))
    for e in base.lire("SELECT * FROM evenements WHERE id>? AND mission IS NULL AND niveau IN ('alerte','erreur')"
                       " ORDER BY id LIMIT 500", (depuis,)):
        _, ch = enregistrer_bloc(base, f"evenement:{e['id']}", "journal", "universite",
                                 f"{'Erreur' if e['niveau'] == 'erreur' else 'Alerte'} : {court(e['message'], 120)}",
                                 e["message"], session=f"Journal de l'université · {date_paris(e['ts'], '%d/%m/%Y')}",
                                 debut=e["ts"], agents_=[e["agent"]] if e["agent"] else (), indice="Université")
        compteur(ch)
        depuis = e["id"]
    avancer(base, "journal", depuis)


def _sections(texte):
    """Découpe un Markdown en sections « ## » (le début avant la première section garde le titre « # »)."""
    titre, morceaux, courant, nom = "", [], [], "Début"
    for ligne in texte.splitlines():
        if ligne.startswith("# ") and not titre:
            titre = ligne[2:].strip()
        elif ligne.startswith("## "):
            if "".join(courant).strip():
                morceaux.append((nom, "\n".join(courant).strip()))
            nom, courant = ligne[3:].strip(), []
        else:
            courant.append(ligne)
    if "".join(courant).strip():
        morceaux.append((nom, "\n".join(courant).strip()))
    return titre, morceaux


def _source_etat_projet(base, compteur, fichiers):
    for chemin, indice in fichiers:
        try:
            texte = Path(chemin).read_text(encoding="utf-8")
        except OSError:
            continue
        titre, sections = _sections(texte)
        quand = Path(chemin).stat().st_mtime
        projet = Path(chemin).parent.name
        for nom, contenu in sections:
            _, ch = enregistrer_bloc(base, f"fichier:{projet}/{Path(chemin).name}#{nom}", "etat_projet", "fichier",
                                     f"{projet} — {nom}", contenu, session=f"{Path(chemin).name} ({titre or projet})",
                                     debut=quand, indice=indice)
            compteur(ch)


def _source_a_ranger(base, compteur):
    dossier = dossier_memoire(base) / "a_ranger"
    if not dossier.is_dir():
        return
    ranges = dossier / "ranges"
    for f in sorted(dossier.iterdir()):
        if not f.is_file() or f.suffix.lower() not in (".md", ".txt", ".json"):
            continue
        try:
            brut = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        notes = []
        if f.suffix.lower() == ".json":
            try:
                d = json.loads(brut)
            except ValueError:
                continue
            notes = [x for x in (d if isinstance(d, list) else [d]) if isinstance(x, dict) and x.get("texte")]
        else:
            entete, corps = {}, brut.splitlines()
            while corps and re.match(r"^(dossier|session|source|quand)\s*:", corps[0], re.I):
                k, v = corps.pop(0).split(":", 1)
                entete[k.strip().lower()] = v.strip()
            titre, sections = _sections("\n".join(corps))
            for nom, contenu in sections or [("Début", "\n".join(corps))]:
                notes.append({**entete, "titre": f"{titre} — {nom}" if titre and nom != "Début" else (titre or nom or f.stem),
                              "texte": contenu})
        for i, n in enumerate(notes):
            quand = n.get("quand")
            quand = _ts_iso(quand) if isinstance(quand, str) else quand
            _, ch = enregistrer_bloc(base, f"depot:{f.name}#{i}", "note", re.sub(r"[^a-z0-9_-]", "", plat(n.get("source") or "depot"))[:30] or "depot",
                                     n.get("titre") or f.stem, str(n["texte"]), session=n.get("session") or f.stem,
                                     debut=quand or f.stat().st_mtime, dossier=dossier_nomme(n.get("dossier")))
            compteur(ch)
        ranges.mkdir(exist_ok=True)
        cible = ranges / f.name
        if cible.exists():
            cible = ranges / f"{f.stem}-{int(time.time())}{f.suffix}"
        shutil.move(str(f), str(cible))


# --- sessions Claude Code (fichiers .jsonl)
_BRUIT = re.compile(r"<(system-reminder|session-context|command-[a-z-]+|local-command-[a-z-]+|persisted-output|"
                    r"system-note|functions|antml:[a-z_]+)\b[^>]*>.*?</\1[^>]*>", re.S)
_HUMAIN = re.compile(r"<(?:message|cited)\b[^>]*(?:from=\"human\"|author=\"user\")[^>]*>(.*?)</(?:message|cited)>", re.S)


def _texte_humain(contenu, exiger_humain=False):
    if isinstance(contenu, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in contenu):
            return ""
        contenu = "\n".join(b.get("text", "") for b in contenu if isinstance(b, dict) and b.get("type") == "text")
    texte = _BRUIT.sub(" ", html.unescape(str(contenu or "")))
    humains = _HUMAIN.findall(texte)
    if humains:
        texte = "\n".join(humains)
    elif exiger_humain:
        return ""
    elif re.match(r"\s*<(wake|coordinator-relay|task-notification)\b", texte):
        return ""
    texte = html.unescape(re.sub(r"<[^>]{1,200}>", " ", texte)).strip()
    if texte.startswith(("Caveat:", "[Request interrupted")):
        return ""
    return texte


def _texte_claude(contenu):
    if isinstance(contenu, str):
        return contenu.strip()
    morceaux = []
    for b in contenu or []:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text":
            morceaux.append(b.get("text", ""))
        elif b.get("type") == "tool_use" and str(b.get("name", "")).endswith("post_message"):
            morceaux.append(str((b.get("input") or {}).get("text", "")))   # réponse envoyée dans un fil de projet
    return "\n".join(m for m in morceaux if m.strip()).strip()


def _indice_projet(cwd):
    c = plat(cwd)
    if "jarvis" in c:
        return "Jarvis"
    if "tradingagents" in c or "trading-agents" in c:
        return "Université"
    if "bot trad" in c:
        return "Stratégie"
    return None


def _source_claude(base, compteur, racine):
    if not racine or not Path(racine).is_dir():
        return
    for f in sorted(Path(racine).rglob("*.jsonl")):
        if "subagents" in f.parts:
            continue
        cle = f"claude:{f.relative_to(racine).as_posix()}"
        depart = int(curseur(base, cle, 0))
        try:
            taille = f.stat().st_size
            if taille < depart:          # fichier recréé : on relit depuis le début
                depart = 0
            if taille == depart:
                continue
            with open(f, "rb") as h:
                h.seek(depart)
                brut = h.read(LECTURE_MAX)
        except OSError:
            continue
        fin_complete = brut.rfind(b"\n") + 1
        tours, position, reprise = [], depart, None
        for ligne in brut[:fin_complete].split(b"\n")[:-1]:
            debut_ligne, position = position, position + len(ligne) + 1
            try:
                d = json.loads(ligne)
            except ValueError:
                continue
            if not isinstance(d, dict) or d.get("isSidechain"):
                continue
            message = d.get("message") or {}
            piece = d.get("attachment") if d.get("type") == "attachment" else None
            if piece and isinstance(piece, dict) and piece.get("type") == "queued_command":
                message = {"content": piece.get("prompt")}   # message envoyé pendant que Claude travaillait
            if d.get("type") == "user" or message.get("content") is not None and piece:
                texte = _texte_humain(message.get("content"), exiger_humain=bool(d.get("isMeta")))
                if texte:
                    tours.append({"debut_octet": debut_ligne, "uuid": d.get("uuid") or str(debut_ligne),
                                  "session": d.get("sessionId") or f.stem, "cwd": d.get("cwd") or "",
                                  "ts": _ts_iso(d.get("timestamp")), "jabran": texte, "claude": [], "fin": None})
            elif d.get("type") == "assistant" and tours:
                texte = _texte_claude(message.get("content"))
                if texte:
                    tours[-1]["claude"].append(texte)
                    tours[-1]["fin"] = _ts_iso(d.get("timestamp"))
            if tours and not tours[-1]["cwd"] and d.get("cwd"):
                tours[-1]["cwd"] = d["cwd"]
        for t in tours:
            if not t["claude"] and t is tours[-1]:
                continue
            projet = Path(str(t["cwd"]).replace("\\", "/")).name or "?"
            texte = f"Jabran : {court(t['jabran'], MESSAGE_MAX)}\n" + "\n".join(
                f"Claude : {court(c, MESSAGE_MAX)}" for c in t["claude"][-4:])
            _, ch = enregistrer_bloc(base, f"claude:{t['session']}:{t['uuid']}", "session_claude", "claude",
                                     f"Session Claude : {court(t['jabran'], 110)}", texte,
                                     session=f"Claude · {projet} · {str(t['session'])[:8]}", debut=t["ts"],
                                     fin=t["fin"] or t["ts"], indice=_indice_projet(t["cwd"]))
            compteur(ch)
        # le dernier tour peut encore recevoir des réponses : on le relira au prochain passage
        # (sauf si la lecture a été coupée à LECTURE_MAX : on avance alors quoi qu'il arrive)
        tout_lu = taille - depart == len(brut)
        avancer(base, cle, tours[-1]["debut_octet"] if tours and tout_lu else depart + fin_complete)


# ------------------------------------------------------------------ le passage du Scribe
def ecrire_tout(base, reglages=None, etape=lambda libelle: None):
    """Un passage du Scribe sur toutes les sources. Renvoie les comptes (nouveaux, mis à jour, par dossier)."""
    from . import config
    reglages = reglages or {}
    preparer(base)
    comptes = {"nouveaux": 0, "mis_a_jour": 0}
    touches = set()
    avant = (base.un("SELECT MAX(maj) AS m FROM memoire_blocs") or {}).get("m") or 0

    def compteur(changement):
        if changement == "nouveau":
            comptes["nouveaux"] += 1
        elif changement == "maj":
            comptes["mis_a_jour"] += 1

    jarvis = reglages.get("memoire_jarvis", config.DEFAUTS.get("memoire_jarvis", ""))
    etape("Relit les missions terminées des agents")
    _source_missions(base, compteur)
    etape("Relit la conversation avec le directeur et le chat du desk de Jarvis")
    _source_directeur(base, compteur)
    _source_desk_jarvis(base, compteur, jarvis)
    _source_fichiers_jarvis(base, compteur, jarvis)
    etape("Relit les sessions Claude du PC")
    _source_claude(base, compteur, reglages.get("memoire_claude", config.DEFAUTS.get("memoire_claude", "")))
    etape("Relit les règles décidées, le journal, PROJECT_STATUS.md et les notes déposées")
    _source_regles(base, compteur)
    _source_journal(base, compteur)
    fichiers = [(config.RACINE / "PROJECT_STATUS.md", "Université")]
    if jarvis:
        fichiers.append((Path(jarvis) / "PROJECT_STATUS.md", "Jarvis"))
    if reglages.get("memoire_etat_projet", True):
        _source_etat_projet(base, compteur, fichiers)
    _source_a_ranger(base, compteur)
    for r in base.lire("SELECT DISTINCT dossier, strftime('%Y-%m', debut, 'unixepoch') AS mois FROM memoire_blocs"
                       " WHERE maj>?", (avant,)):
        touches.add((r["dossier"], r["mois"]))
    etape("Range les blocs dans leurs dossiers et met l'index à jour")
    exporter(base, touches)
    comptes["dossiers_touches"] = sorted({d for d, _ in touches})
    comptes["total"] = base.un("SELECT COUNT(*) AS n FROM memoire_blocs")["n"]
    return comptes


def exporter(base, touches=None):
    """Recopie les blocs en Markdown : memoire\\<dossier>\\<AAAA-MM>.md, et l'index général memoire\\INDEX.md."""
    racine = dossier_memoire(base)
    racine.mkdir(parents=True, exist_ok=True)
    if touches is None:
        touches = {(r["dossier"], r["mois"]) for r in base.lire(
            "SELECT DISTINCT dossier, strftime('%Y-%m', debut, 'unixepoch') AS mois FROM memoire_blocs")}
    for dossier, mois in touches:
        blocs = base.lire("SELECT * FROM memoire_blocs WHERE dossier=? AND strftime('%Y-%m', debut, 'unixepoch')=?"
                          " ORDER BY debut, id", (dossier, mois))
        d = racine / nom_fichier(dossier)
        d.mkdir(exist_ok=True)
        lignes = [f"# {dossier} — {mois}", "", f"{len(blocs)} bloc(s), écrits par le Scribe (agent 15). "
                  "Ne pas modifier : ce fichier est refait à chaque passage.", ""]
        for b in blocs:
            lignes += [f"## {date_paris(b['debut'])} — {b['titre']}", "",
                       f"*Bloc n° {b['id']} · {b['genre']} · {b['session']}*", "", b["texte"], ""]
        _ecrire(d / f"{mois}.md", "\n".join(lignes))
    _ecrire(racine / "INDEX.md", index_markdown(base))


def _ecrire(f, texte):
    tmp = f.with_suffix(".tmp")
    tmp.write_text(texte, encoding="utf-8")
    tmp.replace(f)


def index_markdown(base):
    stats = index(base)
    lignes = ["# Mémoire de l'université — index", "",
              f"Mis à jour le {date_paris(time.time())}. {stats['total']} bloc(s) dans {len(stats['dossiers'])} dossier(s).",
              "", "Chercher : `python -m universite.memoire cherche \"ta question\"` (depuis Documents\\TradingAgents),",
              "ou dans le bureau de l'université (bouton « Mémoire »), ou demander à Jarvis « archiviste, … ».", ""]
    for d in stats["dossiers"]:
        lignes += [f"## {d['dossier']} ({d['blocs']} blocs, du {date_paris(d['debut'], '%d/%m/%Y')} au "
                   f"{date_paris(d['fin'], '%d/%m/%Y')})", "", f"Fichiers : `{nom_fichier(d['dossier'])}\\`", ""]
        for s in base.lire("SELECT session, COUNT(*) AS n, MIN(debut) AS debut, MAX(fin) AS fin, MAX(id) AS dernier"
                           " FROM memoire_blocs WHERE dossier=? GROUP BY session ORDER BY MAX(fin) DESC LIMIT 15",
                           (d["dossier"],)):
            lignes.append(f"- {s['session']} : {s['n']} bloc(s), {date_paris(s['debut'], '%d/%m %Hh%M')} → "
                          f"{date_paris(s['fin'], '%d/%m %Hh%M')} (dernier bloc n° {s['dernier']})")
        lignes.append("")
    return "\n".join(lignes)


# ------------------------------------------------------------------ l'Archiviste : retrouver
MOTS_VIDES = set("""le la les l de des du d un une et ou a au aux en on qu que qui quoi est sur pour dans ce cet cette ces
mon ma mes ton ta tes son sa ses nous vous il elle ils elles je j tu t avec pas plus se s y ne n me m moi toi lui leur
quel quelle quels quelles comment quand pourquoi combien est-ce c ca etait ete fait dit decide rappelle rappeler souviens
souvenir memoire archiviste retrouve retrouver cherche chercher dis donne avait avons ont as ai sais savoir infos info
information informations tout tous toutes parle parler propos sujet""".split())


def mots_question(question):
    return [m for m in re.findall(r"[a-z0-9][a-z0-9.]*[a-z0-9]|[a-z0-9]", plat(question).replace("'", " "))
            if m not in MOTS_VIDES and len(m) >= 2][:12]


def chercher(base, question="", dossier=None, genre=None, source=None, depuis=None, jusqua=None, n=10):
    """Les blocs les plus pertinents pour une question (index FTS5), avec un extrait autour des mots trouvés."""
    n = max(1, min(100, int(n or 10)))
    filtres, args = [], []
    for col, val in (("dossier", dossier), ("genre", genre), ("source", source)):
        if val:
            filtres.append(f"b.{col}=?")
            args.append(val)
    if depuis:
        filtres.append("b.fin>=?")
        args.append(float(depuis))
    if jusqua:
        filtres.append("b.debut<=?")
        args.append(float(jusqua))
    mots = mots_question(question)
    champs = "b.id, b.ref, b.genre, b.source, b.session, b.dossier, b.titre, b.debut, b.fin, b.agents"
    if not mots:
        where = (" WHERE " + " AND ".join(filtres)) if filtres else ""
        lignes = base.lire(f"SELECT {champs}, substr(b.texte, 1, 300) AS extrait FROM memoire_blocs b{where}"
                           " ORDER BY b.fin DESC LIMIT ?", (*args, n))
        return lignes
    if preparer(base):
        requete = " OR ".join(f'"{m}"*' for m in mots)
        where = "".join(f" AND {f}" for f in filtres)
        try:
            return base.lire(f"SELECT {champs}, snippet(memoire_index, 1, '«', '»', ' … ', 28) AS extrait,"
                             " bm25(memoire_index, 6.0, 1.0, 2.0, 1.0, 2.0) AS score FROM memoire_index"
                             f" JOIN memoire_blocs b ON b.id = memoire_index.rowid WHERE memoire_index MATCH ?{where}"
                             " ORDER BY score, b.fin DESC LIMIT ?", (requete, *args, n))
        except Exception:  # noqa: BLE001 : requête refusée par FTS5 -> recherche simple
            pass
    score = " + ".join("(instr(lower(b.titre || ' ' || b.texte || ' ' || b.mots), ?) > 0)" for _ in mots)
    where = " AND ".join(filtres + [f"({score}) > 0"])
    lignes = base.lire(f"SELECT {champs}, substr(b.texte, 1, 300) AS extrait, -({score}) AS score FROM memoire_blocs b"
                       f" WHERE {where} ORDER BY score, b.fin DESC LIMIT ?", (*mots, *args, *mots, n))
    return lignes


def bloc(base, ident):
    return base.un("SELECT * FROM memoire_blocs WHERE id=?", (int(ident),))


def contexte(base, question, n=6, max_car=3000, dossier=None):
    """Ce que la mémoire sait sur une question, en texte compact (pour Jarvis, le directeur, une session Claude)."""
    blocs = chercher(base, question, dossier=dossier, n=n)
    lignes, total = [], 0
    for b in blocs:
        extrait = court(re.sub(r"[«»]", "", b.get("extrait") or ""), 400)
        ligne = f"[{b['dossier']} · {date_paris(b['debut'], '%d/%m/%Y %Hh%M')} · {b['session']}] {b['titre']} : {extrait} (bloc n° {b['id']})"
        if total + len(ligne) > max_car:
            break
        lignes.append(ligne)
        total += len(ligne)
    return {"question": question, "texte": "\n".join(lignes), "blocs": blocs[: len(lignes)]}


def reponse_courte(base, question, n=3):
    """Réponse orale de l'Archiviste : uniquement des blocs existants, avec leur date et leur dossier."""
    blocs = chercher(base, question, n=n)
    if not blocs:
        if not base.un("SELECT id FROM memoire_blocs LIMIT 1"):
            return "La mémoire est encore vide : le Scribe n'a rien noté pour l'instant."
        return "Je n'ai rien trouvé dans la mémoire sur ce sujet. Essaie avec d'autres mots."
    premier = blocs[0]
    txt = (f"J'ai trouvé {len(blocs)} bloc(s). Le plus proche, le {date_paris(premier['debut'], '%d/%m à %Hh%M')} "
           f"(dossier {premier['dossier']}) : {premier['titre']}. {court(re.sub(r'[«»]', '', premier.get('extrait') or ''), 320)}")
    if len(blocs) > 1:
        txt += " Aussi : " + " ; ".join(f"{court(b['titre'], 90)} ({date_paris(b['debut'], '%d/%m')})" for b in blocs[1:]) + "."
    return txt


def index(base):
    """L'index de la mémoire : dossiers, sources, sessions récentes, dernier passage du Scribe."""
    preparer(base)
    return {"total": base.un("SELECT COUNT(*) AS n FROM memoire_blocs")["n"],
            "recherche_rapide": bool(getattr(base, "_memoire_fts", False)),
            "dossiers": base.lire("SELECT dossier, COUNT(*) AS blocs, MIN(debut) AS debut, MAX(fin) AS fin"
                                  " FROM memoire_blocs GROUP BY dossier ORDER BY MAX(fin) DESC"),
            "sources": base.lire("SELECT source, COUNT(*) AS blocs FROM memoire_blocs GROUP BY source ORDER BY blocs DESC"),
            "sessions": base.lire("SELECT session, dossier, COUNT(*) AS blocs, MIN(debut) AS debut, MAX(fin) AS fin"
                                  " FROM memoire_blocs GROUP BY session, dossier ORDER BY MAX(fin) DESC LIMIT 30"),
            "dernier_passage": (base.un("SELECT MAX(fin) AS fin FROM missions WHERE type='ecriture_memoire'"
                                        " AND statut='terminee'") or {}).get("fin"),
            "dossier_fichiers": str(dossier_memoire(base))}


def assurer_boucle(moteur):
    """Le Scribe tourne en continu : sa boucle est créée une seule fois (si Jabran la met en pause, elle le reste)."""
    if moteur.base.un("SELECT id FROM boucles WHERE genre='ecriture_memoire'"):
        return None
    b = moteur.nouvelle_boucle("Scribe : tout noter", SCRIBE, "ecriture_memoire",
                               "Noter en blocs tout ce qui se passe (agents, Jarvis, sessions Claude) et tenir l'index.",
                               {}, INTERVALLE_SCRIBE_S, 1_000_000)
    # premier passage une minute après le démarrage (le temps que tout soit prêt)
    moteur.base.ecrire("UPDATE boucles SET prochaine=? WHERE id=?", (time.time() + 60, b))
    return b


# ------------------------------------------------------------------ en ligne de commande (pour une session Claude)
def main(argv=None):
    import argparse
    import sys

    from . import config
    from .base import Base

    p = argparse.ArgumentParser(prog="python -m universite.memoire",
                                description="Mémoire de l'université : chercher, noter, ranger (lecture directe de la base).")
    sous = p.add_subparsers(dest="action", required=True)
    c = sous.add_parser("cherche", help="chercher dans la mémoire")
    c.add_argument("question", nargs="+")
    c.add_argument("--dossier", choices=NOMS_DOSSIERS)
    c.add_argument("-n", type=int, default=8)
    c.add_argument("--complet", action="store_true", help="afficher le texte entier des blocs")
    b = sous.add_parser("bloc", help="afficher un bloc")
    b.add_argument("id", type=int)
    nt = sous.add_parser("note", help="ajouter une note (ex. le résumé d'une session Claude)")
    nt.add_argument("texte")
    nt.add_argument("--titre", default="")
    nt.add_argument("--session", default="")
    nt.add_argument("--dossier", choices=NOMS_DOSSIERS)
    nt.add_argument("--source", default="claude")
    sous.add_parser("index", help="les dossiers et les sessions")
    sous.add_parser("ranger", help="faire un passage du Scribe maintenant")
    a = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    base = Base(config.DONNEES / "universite.sqlite")
    if a.action == "cherche":
        for x in chercher(base, " ".join(a.question), dossier=a.dossier, n=a.n):
            print(f"#{x['id']} [{x['dossier']}] {date_paris(x['debut'])} — {x['titre']}\n   {x['session']}")
            print("   " + (bloc(base, x["id"])["texte"].replace("\n", "\n   ") if a.complet else court(x.get("extrait"), 400)))
    elif a.action == "bloc":
        x = bloc(base, a.id)
        print(json.dumps(x, ensure_ascii=False, indent=1) if x else "bloc introuvable")
    elif a.action == "note":
        print(noter(base, a.texte, a.titre, a.source, a.session, a.dossier))
    elif a.action == "index":
        print(index_markdown(base))
    elif a.action == "ranger":
        print(ecrire_tout(base, config.charger(), etape=lambda libelle: print("-", libelle)))
    base.fermer()


if __name__ == "__main__":
    main()
