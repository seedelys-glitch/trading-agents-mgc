# -*- coding: utf-8 -*-
"""
Jeux de bougies de l'université et fenêtre de replay SANS look-ahead.

Convention (la même que mgc/) : ts = DÉBUT de la bougie, en secondes UTC ; colonnes o, h, l, c, v.
Pour le D1, ts = minuit UTC du jour de séance.

Règle anti look-ahead : à l'instant t, une bougie n'est visible que si ts + durée <= t (elle est fermée).
Les unités plus grandes sont reconstruites à partir des bougies visibles seulement, et une bougie
regroupée n'existe que si son créneau entier est terminé.

Sources acceptées (rien n'est jamais inventé) :
  - fichier CSV exporté de TradingView (time, open, high, low, close[, Volume]) ;
  - fichiers de l'indicateur NinjaTrader ExportBougiesMGC (debut_utc,o,h,l,c,v / date_seance,...) ;
  - Yahoo sur le contrat réel via mgc.sources (sur le PC seulement, données différées).
"""

import csv
import datetime as dt
import io
import time
from pathlib import Path
from zoneinfo import ZoneInfo

PERIODES = {"M1": 60, "M3": 180, "M5": 300, "M15": 900, "H1": 3600, "D1": 86400}
CHICAGO = ZoneInfo("America/Chicago")

ALIAS = {
    "ts": ("time", "timestamp", "date", "datetime", "debut_utc", "date_seance", "debut"),
    "o": ("open", "o", "ouverture"),
    "h": ("high", "h", "haut"),
    "l": ("low", "l", "bas"),
    "c": ("close", "c", "cloture", "clôture"),
    "v": ("volume", "v", "vol"),
}


class ErreurDonnees(ValueError):
    pass


# ---------------------------------------------------------------- lecture de fichiers
def _horodatage(valeur):
    """Texte -> secondes UTC. Accepte les secondes/millisecondes Unix et les dates ISO (sans fuseau = UTC)."""
    v = str(valeur).strip().strip('"')
    try:
        x = float(v)
        return x / 1000 if x > 1e11 else x
    except ValueError:
        pass
    v = v.replace("Z", "+00:00")
    try:
        d = dt.datetime.fromisoformat(v)
    except ValueError:
        try:
            d = dt.datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
        except ValueError as e:
            raise ErreurDonnees(f"date illisible : {v[:40]}") from e
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.UTC)
    return d.timestamp()


def lire_csv(texte):
    """CSV -> (lignes [(ts, o, h, l, c, v)], rapport). Les lignes abîmées ou incohérentes sont comptées, jamais corrigées."""
    lecteur = csv.reader(io.StringIO(texte.lstrip("﻿")))
    try:
        entete = [x.strip().lower() for x in next(lecteur)]
    except StopIteration as e:
        raise ErreurDonnees("fichier vide") from e
    colonnes = {}
    for cle, noms in ALIAS.items():
        for i, nom in enumerate(entete):
            if nom in noms and cle not in colonnes:
                colonnes[cle] = i
    manquantes = [k for k in ("ts", "o", "h", "l", "c") if k not in colonnes]
    if manquantes:
        raise ErreurDonnees(f"colonnes introuvables : {', '.join(manquantes)} (en-tête lu : {', '.join(entete)[:200]})")
    lignes, abimees, incoherentes = {}, 0, 0
    for brut in lecteur:
        if not brut or all(not x.strip() for x in brut):
            continue
        try:
            ts = _horodatage(brut[colonnes["ts"]])
            o, h, l, c = (float(brut[colonnes[k]]) for k in "ohlc")
            v = float(brut[colonnes["v"]]) if "v" in colonnes and brut[colonnes["v"]].strip() else 0.0
        except (IndexError, ValueError):
            abimees += 1
            continue
        if not (h >= max(o, c) and l <= min(o, c) and l > 0):
            incoherentes += 1
            continue
        lignes[ts] = (ts, o, h, l, c, v)
    triees = [lignes[k] for k in sorted(lignes)]
    return triees, {"lues": len(triees), "abimees": abimees, "incoherentes": incoherentes,
                    "sans_volume": "v" not in colonnes}


def deviner_unite(lignes):
    """Unité la plus probable d'après l'écart le plus fréquent entre deux bougies."""
    ecarts = {}
    for a, b in zip(lignes, lignes[1:], strict=False):
        e = round(b[0] - a[0])
        ecarts[e] = ecarts.get(e, 0) + 1
    if not ecarts:
        raise ErreurDonnees("pas assez de bougies pour reconnaître l'unité de temps")
    courant = max(ecarts, key=ecarts.get)
    for nom, s in PERIODES.items():
        if courant == s:
            return nom
    if 86400 <= courant <= 3 * 86400:
        return "D1"
    raise ErreurDonnees(f"unité de temps non prise en charge (écart habituel {courant} s)")


# ---------------------------------------------------------------- import dans la base
def creer_jeu(base, nom, source, symbole, temps_reel=False, licence="", note=""):
    return base.ecrire("INSERT INTO jeux(nom, source, symbole, temps_reel, licence, note, cree) VALUES (?,?,?,?,?,?,?)",
                       (nom, source, symbole, int(bool(temps_reel)), licence, note, time.time()))


def ajouter_bougies(base, jeu, unite, lignes):
    if unite not in PERIODES:
        raise ErreurDonnees(f"unité inconnue : {unite}")
    with base._ecriture:
        c = base.cx()
        avant = c.total_changes
        c.executemany("INSERT OR IGNORE INTO bougies(jeu, unite, ts, o, h, l, c, v) VALUES (?,?,?,?,?,?,?,?)",
                      [(jeu, unite, *ligne) for ligne in lignes])
        c.commit()
        return c.total_changes - avant


def importer_csv(base, texte, nom, source="TradingView (fichier)", symbole="MGC", unite=None, note=""):
    lignes, rapport = lire_csv(texte)
    if not lignes:
        raise ErreurDonnees("aucune bougie valide dans le fichier")
    unite = unite or deviner_unite(lignes)
    jeu = creer_jeu(base, nom, source, symbole, temps_reel=False,
                    note=note or "Import manuel : données réelles exportées par Jabran.")
    rapport.update(jeu=jeu, unite=unite, ajoutees=ajouter_bougies(base, jeu, unite, lignes),
                   debut=lignes[0][0], fin=lignes[-1][0])
    base.evenement("donnees", f"Jeu « {nom} » importé : {rapport['ajoutees']} bougies {unite} "
                              f"({rapport['abimees']} abîmées, {rapport['incoherentes']} incohérentes ignorées).")
    return rapport


def importer_ninja(base, dossier, nom="NinjaTrader MGC"):
    """Copie les fichiers de l'indicateur ExportBougiesMGC (lecture seule) dans un jeu (réutilisé s'il existe)."""
    dossier = Path(dossier)
    fichiers = {u: dossier / f"MGC_{u}.csv" for u in ("M1", "M5", "M15", "H1", "D1")}
    if not any(f.exists() for f in fichiers.values()):
        raise ErreurDonnees(f"aucun fichier MGC_*.csv dans {dossier} : l'indicateur NinjaTrader ne tourne pas encore")
    existant = base.un("SELECT id FROM jeux WHERE source='NinjaTrader' AND nom=?", (nom,))
    jeu = existant["id"] if existant else creer_jeu(base, nom, "NinjaTrader", "MGC", temps_reel=True,
                                                    note="Indicateur ExportBougiesMGC (bougies fermées).")
    rapport = {"jeu": jeu, "unites": {}}
    for unite, f in fichiers.items():
        if f.exists():
            lignes, r = lire_csv(f.read_text(encoding="utf-8-sig"))
            r["ajoutees"] = ajouter_bougies(base, jeu, unite, lignes)
            rapport["unites"][unite] = r
    base.evenement("donnees", f"NinjaTrader : {sum(r['ajoutees'] for r in rapport['unites'].values())} nouvelles bougies.")
    return rapport


def importer_yahoo(base, contrat, chargeur=None):
    """Bougies Yahoo du contrat réel (ex. MGCZ26), DIFFÉRÉES. Sur le PC seulement (accès Internet)."""
    from . import config
    config.salle_importable()
    from mgc import sources

    bougies = sources.charger_yahoo(contrat, chargeur or sources.yahoo_brut)
    jeu = creer_jeu(base, f"Yahoo {contrat}", "Yahoo (différé)", contrat, temps_reel=False,
                    note="Données différées d'environ 10 minutes ; historique court en 1 min (5 jours).")
    total = 0
    for unite, df in bougies.items():
        if unite in PERIODES and df is not None and not df.empty:
            lignes = [(t.timestamp(), float(r.o), float(r.h), float(r.l), float(r.c), float(r.v))
                      for t, r in df.iterrows()]
            total += ajouter_bougies(base, jeu, unite, lignes)
    if not total:
        raise ErreurDonnees(f"Yahoo n'a renvoyé aucune bougie pour {contrat}")
    base.evenement("donnees", f"Yahoo {contrat} : {total} bougies importées (différées).")
    return {"jeu": jeu, "ajoutees": total}


# ---------------------------------------------------------------- lecture sans look-ahead
def disponibles(base, jeu):
    return {r["unite"]: r for r in base.lire(
        "SELECT unite, COUNT(*) AS n, MIN(ts) AS debut, MAX(ts) AS fin FROM bougies WHERE jeu=? GROUP BY unite", (jeu,))}


def _brutes(base, jeu, unite, instant, limite=None):
    sql = "SELECT ts, o, h, l, c, v FROM bougies WHERE jeu=? AND unite=? AND ts + ? <= ? ORDER BY ts DESC"
    args = [jeu, unite, PERIODES[unite], instant]
    if limite:
        sql += " LIMIT ?"
        args.append(int(limite))
    lignes = [tuple(r) for r in base.cx().execute(sql, args).fetchall()]
    lignes.reverse()
    return lignes


def regrouper(lignes, petite, grande, instant):
    """Regroupe des bougies fermées en une unité plus grande ; seuls les créneaux TERMINÉS à l'instant sont gardés."""
    pas = PERIODES[grande]
    if pas % PERIODES[petite]:
        raise ErreurDonnees(f"{grande} ne se reconstruit pas à partir de {petite}")
    paquets = {}
    for ts, o, h, l, c, v in lignes:
        # D1 = séance CME (depuis 17 h à Chicago), gardée seulement 24 h après son ouverture (prudent)
        debut = debut_seance(ts) if grande == "D1" else ts - ts % pas
        p = paquets.get(debut)
        paquets[debut] = (debut, o, h, l, c, v) if p is None else (debut, p[1], max(p[2], h), min(p[3], l), c, p[5] + v)
    return [p for d, p in sorted(paquets.items()) if d + pas <= instant]


def fenetre(base, jeu, unite, instant, n=None):
    """Les n dernières bougies FERMÉES à l'instant (secondes UTC). Reconstruit l'unité si elle n'est pas stockée."""
    if unite not in PERIODES:
        raise ErreurDonnees(f"unité inconnue : {unite}")
    stock = disponibles(base, jeu)
    if unite in stock:
        return {"bougies": _brutes(base, jeu, unite, instant, n), "unite": unite, "reconstruite_depuis": None}
    for petite in ("M1", "M3", "M5", "M15"):
        if petite in stock and PERIODES[petite] < PERIODES[unite] and PERIODES[unite] % PERIODES[petite] == 0:
            besoin = None if n is None else (n + 1) * PERIODES[unite] // PERIODES[petite]
            lignes = regrouper(_brutes(base, jeu, petite, instant, besoin), petite, unite, instant)
            return {"bougies": lignes[-n:] if n else lignes, "unite": unite, "reconstruite_depuis": petite}
    return {"bougies": [], "unite": unite, "reconstruite_depuis": None}


def debut_seance(instant):
    """Début de la séance CME en cours : dernier 17 h à Chicago (= 18 h à New York) avant l'instant."""
    local = dt.datetime.fromtimestamp(instant, CHICAGO)
    debut = local.replace(hour=17, minute=0, second=0, microsecond=0)
    if local < debut:
        debut -= dt.timedelta(days=1)
    return debut.timestamp()


# ---------------------------------------------------------------- contrôle qualité
def controle(base, jeu):
    """Ce que contient un jeu, unité par unité : nombre, période couverte, trous (écarts plus grands que prévu)."""
    infos = base.un("SELECT * FROM jeux WHERE id=?", (jeu,))
    if not infos:
        raise ErreurDonnees(f"jeu {jeu} introuvable")
    resultat = {"jeu": infos, "unites": {}}
    for unite, d in disponibles(base, jeu).items():
        ts = [r[0] for r in base.cx().execute("SELECT ts FROM bougies WHERE jeu=? AND unite=? ORDER BY ts",
                                              (jeu, unite)).fetchall()]
        pas = PERIODES[unite]
        # Pause quotidienne et week-end exclus ; au-delà de 2 h (4 jours en D1) l'écart est une « longue coupure »
        tolere = 4 * 86400 if unite == "D1" else max(2 * 3600, 2 * pas)
        normal = _lundi if unite == "D1" else _week_end
        trous = [(a, b) for a, b in zip(ts, ts[1:], strict=False) if b - a > pas and b - a <= tolere and not normal(a, b)]
        longs = [(a, b) for a, b in zip(ts, ts[1:], strict=False) if b - a > tolere and not normal(a, b)]
        resultat["unites"][unite] = {"n": d["n"], "debut": d["debut"], "fin": d["fin"],
                                     "petits_trous": len(trous), "longues_coupures": len(longs),
                                     "plus_longue_coupure_h": round(max((b - a for a, b in longs), default=0) / 3600, 1)}
    return resultat


def _week_end(a, b):
    """Vrai si l'écart s'arrête à une réouverture normale (17 h à Chicago : pause quotidienne ou week-end)."""
    db = dt.datetime.fromtimestamp(b, CHICAGO)
    return b - a <= 3 * 86400 and (db.hour, db.minute) == (17, 0)


def _lundi(a, b):
    """D1 : le saut du vendredi au lundi est normal."""
    return b - a == 3 * 86400 and dt.datetime.fromtimestamp(b, dt.UTC).weekday() == 0


def liste_jeux(base):
    jeux = base.lire("SELECT * FROM jeux ORDER BY id DESC")
    for j in jeux:
        j["unites"] = {u: {k: r[k] for k in ("n", "debut", "fin")} for u, r in disponibles(base, j["id"]).items()}
    return jeux
