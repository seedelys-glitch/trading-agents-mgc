"""
Journal des setups du dossier « bot trad » (Bureau\\bot trad\\journal_setups.csv), tenu par la veille du desk
(déménagé de Jarvis le 24/10/2026, étape 3 du plan « Jarvis connecteur »). Jarvis reçoit la photo ou la capture
et pose les questions, puis l'envoie ici (POST /api/setups/noter) ; le desk lit le graphique et écrit la ligne :
  - « Jarvis, note ce setup » : capture de l'écran TradingView, 2 questions (résultat, date et heure
    d'entrée), lecture du graphique par l'IA locale, puis une ligne ajoutée au journal.
  - une photo envoyée sur Telegram, dans l'appli ou collée dans la case de l'écran Jarvis, avec
    « note ce setup » (ou « setup … journal ») dans le message : pareil, sans questions ; ce que tu
    écris avec la photo complète (résultat, date…).
  - « Jarvis, analyse mes setups » : points communs (jours, sessions, niveaux de Fibo, résultats).

Format exact du journal (CLAUDE.md du dossier bot trad) : 29 colonnes, séparateur « ; », UTF-8 avec
BOM, fins de ligne LF, virgule décimale, dates JJ/MM/AAAA, heures de Paris, « ? » quand l'info est
inconnue, jamais de valeur inventée. Le desk AJOUTE une ligne à la fin, il ne modifie jamais les
lignes existantes. La capture est copiée dans captures\\NNN_AAAA-MM-JJ_sens.png (ou .jpg).
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import threading
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Callable

log = logging.getLogger("veille")

HOME = Path(os.environ.get("USERPROFILE", str(Path.home())))
BOT_DIRS = [HOME / "Desktop" / "bot trad", HOME / "OneDrive" / "Desktop" / "bot trad",
            HOME / "OneDrive" / "Bureau" / "bot trad"]
JOURNAL = "journal_setups.csv"
COLUMNS = ["N", "Date entree", "Jour", "Heure entree (Paris)", "Date sortie", "Heure sortie (Paris)", "Duree",
           "Session", "Unite de temps", "Sens", "Fibo haut", "Fibo bas", "Niveau entree", "FVG sur la zone",
           "Entree", "Stop", "TP1 (0)", "TP2 (-0.618)", "TP3", "Resultat", "Ratio R", "Biais 12H",
           "Position vs EMA", "RSI", "Volume", "News", "Confluences", "Notes", "Capture"]
JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MOIS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout", "septembre", "octobre",
        "novembre", "decembre"]
NIVEAUX_OK = ("0.618", "0.705", "0.786", "0.893")

# « note ce setup », « ajoute ce setup au journal », « setup pour le journal »… (pas « vérifie mon setup »)
NOTE_RE = re.compile(r"(?<![a-z])(note|noter|notes|ajoute|ajouter|enregistre|enregistrer|garde|garder|sauvegarde|"
                     r"mets|met|range)(?![a-z]).{0,30}(?<![a-z])setups?(?![a-z])"
                     r"|(?<![a-z])setups?(?![a-z]).{0,30}(?<![a-z])(journal|au journal|dans le journal)(?![a-z])"
                     r"|journal des setups")
STATS_RE = re.compile(r"(?<![a-z])(analyse|stats?|statistiques|points communs|bilan|resume)(?![a-z]).{0,25}"
                      r"(?<![a-z])(mes|des|de mes)\s+setups(?![a-z])")

PROMPT = """Lis ce graphique de trading pour remplir le journal de setups de Jabran (gold / Micro Gold).
Réponds UNIQUEMENT avec un objet JSON, sans aucun texte autour, avec exactement ces clés :
{"unite": "unité de temps du graphique (1H, 12H, 48 min, 15 min...) ou ?",
 "sens": "Long ou Short ou ?",
 "fibo_haut": "prix du haut du Fibo ou ?", "fibo_bas": "prix du bas du Fibo ou ?",
 "niveau": "niveau de Fibo de l'entrée : 0.618, 0.705, 0.786, 0.893, 0.5 ou ?",
 "prix_niveau": "prix de ce niveau ou ?",
 "fvg": "Oui s'il y a un FVG (gap) sur la zone d'entrée, Non, ou ?",
 "entree": "prix d'entrée ou ?", "stop": "prix du stop ou ?",
 "tp1": "prix du niveau 0 du Fibo ou ?", "tp2": "prix du niveau -0.618 ou ?", "tp3": "prix du TP3 ou ?",
 "date_entree": "JJ/MM/AAAA lue sur l'axe du bas ou ?", "heure_entree": "HH:MM ou ?",
 "biais_12h": "Haussier, Baissier ou ?", "ema": "Au-dessus ou Sous (prix par rapport à l'EMA 200) ou ?",
 "rsi": "valeur ou ?", "volume": "quelques mots ou ?",
 "confluences": "trendlines, BOS, order block... en quelques mots, ou ?",
 "notes": "une phrase sur ce qui est visible"}
Règle stricte : mets "?" pour tout ce qui ne se LIT pas clairement sur l'image. N'invente aucun chiffre."""


# ---------------------------------------------------------------------------
# Petits outils de texte et de nombres
# ---------------------------------------------------------------------------
def plain(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").replace("’", "'").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def wants_journal(text: str) -> bool:
    """Le message demande de NOTER un setup dans le journal (pas seulement de le vérifier) ?"""
    return bool(NOTE_RE.search(plain(text)))


def wants_stats(text: str) -> bool:
    return bool(STATS_RE.search(plain(text)))


def bot_dir() -> Path | None:
    for d in BOT_DIRS:
        if (d / JOURNAL).is_file() or (d / "STRATEGIE.md").is_file():
            return d
    return None


def to_num(s) -> float | None:
    """« 4 504,10 », « 4,504.10 », « 4504.1 » -> 4504.1 ; None si ce n'est pas un prix lisible."""
    if s is None:
        return None
    t = str(s).strip().replace(" ", "").replace("\xa0", "").replace(" ", "").replace("$", "")
    m = re.search(r"-?\d[\d.,]*", t)
    if not m:
        return None
    t = m.group(0)
    if "," in t and "." in t:  # 4,504.10 (anglais) ou 4.504,10 (français)
        t = t.replace(",", "") if t.rfind(".") > t.rfind(",") else t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def fmt(x: float | None) -> str:
    if x is None:
        return "?"
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    return f"{x:.2f}".replace(".", ",")


def clean(v, default: str = "?") -> str:
    """Une case du journal : jamais de « ; » ni de retour à la ligne (ça casserait les colonnes)."""
    s = " ".join(str(v if v is not None else "").split()).replace(";", ",").strip()
    return s if s and s.lower() not in ("none", "null", "n/a", "na", "inconnu") else default


def price(v) -> str:
    x = to_num(v)
    return fmt(x) if x is not None else "?"


def level_of(v) -> str:
    t = plain(str(v or ""))
    m = re.search(r"0[.,](\d{1,3})", t)
    if m:
        lv = "0." + m.group(1)
    else:  # « 61,8 % », « 70.5 »
        m = re.search(r"(?<!\d)(50|61|62|70|78|79|89)(?:[.,](\d))?\s*%?", t)
        if not m:
            return "?"
        lv = "0." + m.group(1) + (m.group(2) or "")
    return {"0.5": "0.5", "0.50": "0.5", "0.500": "0.5", "0.62": "0.618", "0.68": "0.618", "0.7": "0.705",
            "0.71": "0.705", "0.79": "0.786", "0.89": "0.893"}.get(lv, lv)


def parse_json(text: str) -> dict:
    """L'IA renvoie (normalement) un objet JSON ; on est tolérant avec ce qu'il y a autour."""
    if not text:
        return {}
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        return {}
    blob = text[a:b + 1]
    for attempt in (blob, re.sub(r",\s*}", "}", blob).replace("'", '"')):
        try:
            d = json.loads(attempt)
            return d if isinstance(d, dict) else {}
        except Exception:
            continue
    return {}


# ---------------------------------------------------------------------------
# Dates, heures, sessions (heure de Paris)
# ---------------------------------------------------------------------------
def _nth_sunday(year: int, month: int, n: int) -> dt.date:
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(6 - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def _last_sunday(year: int, month: int) -> dt.date:
    d = dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() + 1) % 7)


def ny_open(day: dt.date) -> float:
    """Ouverture de New York en heure de Paris : 15h30, ou 14h30 les semaines où les changements
    d'heure américain et européen sont décalés (mars et fin octobre)."""
    us = _nth_sunday(day.year, 3, 2) <= day < _nth_sunday(day.year, 11, 1)
    eu = _last_sunday(day.year, 3) <= day < _last_sunday(day.year, 10)
    return 14.5 if us and not eu else 15.5


def session_of(day: dt.date | None, hour: float | None) -> str:
    if hour is None:
        return "?"
    nyo = ny_open(day) if day else 15.5
    if 1 <= hour < 9:
        return "Asie"
    if 9 <= hour < nyo:
        return "Londres"
    if nyo <= hour < 22:
        return "New York"
    return "Hors session"


def parse_date(text: str, today: dt.date) -> dt.date | None:
    """« 04/09/2026 », « 4/9 », « le 4 septembre », « hier », « aujourd'hui » (dates passées)."""
    t = plain(text)
    if "avant-hier" in t or "avant hier" in t:
        return today - dt.timedelta(days=2)
    if re.search(r"(?<![a-z])hier(?![a-z])", t):
        return today - dt.timedelta(days=1)
    if "aujourd" in t or "ce matin" in t or "cet apres" in t or "tout a l'heure" in t:
        return today
    m = re.search(r"(?<!\d)(\d{1,2})[/.\-](\d{1,2})(?:[/.\-](\d{2,4}))?(?!\d)", t)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else None
    else:
        m = re.search(r"(?<!\d)(\d{1,2}|1er|premier)\s+(" + "|".join(MOIS) + r")(?:\s+(\d{4}))?", t)
        if not m:
            return None
        d = 1 if m.group(1) in ("1er", "premier") else int(m.group(1))
        mo = MOIS.index(m.group(2)) + 1
        y = int(m.group(3)) if m.group(3) else None
    if y is not None and y < 100:
        y += 2000
    try:
        out = dt.date(y or today.year, mo, d)
    except ValueError:
        return None
    if y is None and out > today:  # « le 4 décembre » dit en octobre = l'an dernier
        out = out.replace(year=out.year - 1)
    return out


def parse_hour(text: str, strict: bool = False) -> tuple[int, int] | None:
    """strict=True (message écrit avec une photo) : « à 14h », « 14h30 », « 14:30 » seulement,
    pas « 1h » tout seul (c'est souvent l'unité de temps du graphique)."""
    t = plain(text)
    m = None
    for m in re.finditer(r"(?<![\d.,])(\d{1,2})\s*(?:h|:|heures?)\s*(\d{2})?(?![\d])", t):
        before = t[max(0, m.start() - 5):m.start()]
        if not strict or m.group(2) or re.search(r"(?<![a-z])(a|vers|de)\s*$", before):
            break
    else:
        m = None
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if "apres-midi" in t or "apres midi" in t or "du soir" in t:
        h = h + 12 if h < 12 else h
    return (h, mi) if 0 <= h < 24 and 0 <= mi < 60 else None


def read_date(s: str) -> dt.date | None:
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})", s or "")
    if not m:
        return None
    try:
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def read_hour(s: str) -> float | None:
    m = re.match(r"\s*(\d{1,2})[:h](\d{2})", s or "")
    return int(m.group(1)) + int(m.group(2)) / 60 if m else None


# ---------------------------------------------------------------------------
class SetupJournal:
    def __init__(self, brain, notify: Callable[[str, str], None] | None = None, base: Path | None = None):
        self.brain = brain
        self.notify = notify or (lambda t, k="reponse": None)
        self.base = base            # dossier « bot trad » (trouvé tout seul si None)
        self.lock = threading.Lock()

    # ------------------------------------------------------------------ fichier
    def folder(self) -> Path | None:
        return self.base if self.base is not None else bot_dir()

    def rows(self) -> list[list[str]]:
        d = self.folder()
        if d is None or not (d / JOURNAL).is_file():
            return []
        text = (d / JOURNAL).read_text(encoding="utf-8-sig", errors="replace")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        return [ln.split(";") for ln in lines[1:]]

    def next_number(self) -> int:
        n = 0
        for r in self.rows():
            m = re.match(r"\s*(\d+)", r[0] if r else "")
            if m:
                n = max(n, int(m.group(1)))
        return n + 1

    def _append(self, cells: list[str]) -> None:
        d = self.folder()
        path = d / JOURNAL
        if not path.is_file():  # 1re fois : l'en-tête, en UTF-8 avec BOM
            path.write_bytes("﻿".encode("utf-8") + (";".join(COLUMNS) + "\n").encode("utf-8"))
        raw = path.read_bytes()
        prefix = b"" if raw.endswith(b"\n") else b"\n"
        with open(path, "ab") as f:  # on AJOUTE à la fin, sans réécrire le reste
            f.write(prefix + (";".join(cells) + "\n").encode("utf-8"))

    def _save_capture(self, image: bytes, n: int, day: dt.date | None, sens: str) -> str:
        d = self.folder() / "captures"
        d.mkdir(parents=True, exist_ok=True)
        ext = ".jpg" if image[:2] == b"\xff\xd8" else ".png"
        stem = f"{n:03d}_{day.isoformat() if day else 'date-inconnue'}_{sens.lower() if sens in ('Long', 'Short') else 'sens-inconnu'}"
        name, k = stem + ext, 2
        while (d / name).exists():
            name, k = f"{stem}_{k}{ext}", k + 1
        (d / name).write_bytes(image)
        return name

    # ------------------------------------------------------------------ lecture du graphique
    def read_chart(self, image: bytes, extra: str = "") -> dict:
        from .ia import mime_of

        p = PROMPT + (f"\nInfos données par Jabran : {extra}" if extra.strip() else "")
        out = self.brain.see(image, p, mime_of(image), max_tokens=700) if self.brain else None
        data = parse_json(out or "")
        if not data:
            log.info("Journal des setups : lecture automatique du graphique impossible (%s).",
                     (out or getattr(self.brain, "vision_error", "pas de réponse"))[:120])
        return data

    # ------------------------------------------------------------------ une ligne
    def build(self, n: int, f: dict, result: str = "", when_text: str = "", today: dt.date | None = None,
              capture: str = "", source: str = "", strict_when: bool = False) -> tuple[list[str], dict]:
        today = today or dt.date.today()
        day = read_date(clean(f.get("date_entree"), ""))
        hm = read_hour(clean(f.get("heure_entree"), ""))
        if when_text.strip():  # ce que Jabran a dit passe avant ce que l'IA a lu
            d2, h2 = parse_date(when_text, today), parse_hour(when_text, strict=strict_when)
            day = d2 or day
            if h2:
                hm = h2[0] + h2[1] / 60
        sens = clean(f.get("sens")).capitalize()
        sens = sens if sens in ("Long", "Short") else "?"
        level = level_of(f.get("niveau"))
        lvl_price = to_num(f.get("prix_niveau"))
        entree, stop = to_num(f.get("entree")), to_num(f.get("stop"))
        tps = [to_num(f.get(k)) for k in ("tp1", "tp2", "tp3")]
        fvg = clean(f.get("fvg")).capitalize()
        fvg = fvg if fvg in ("Oui", "Non") else "?"
        ema = clean(f.get("ema"))
        ema = "Sous EMA" if plain(ema).startswith("sous") else ("Au-dessus EMA" if "dessus" in plain(ema) else "?")
        biais = clean(f.get("biais_12h")).capitalize()
        biais = biais if biais in ("Haussier", "Baissier") else "?"
        res = clean(result)
        ratio = "?"
        r = plain(res)
        if entree is not None and stop is not None and abs(entree - stop) > 0:
            risk = abs(entree - stop)
            if re.search(r"(?<![a-z])(stop|sl)(?![a-z])", r) and "break" not in r:
                ratio = "-1"
            else:
                for i, tp in ((3, tps[2]), (2, tps[1]), (1, tps[0])):
                    if tp is not None and re.search(rf"tp\s*{i}(?!\d)", r):
                        ratio = "1:" + f"{abs(tp - entree) / risk:.1f}".replace(".", ",")
                        break
        niveau_txt = level if level == "?" or lvl_price is None else f"{level} ({fmt(lvl_price)})"
        notes = clean(f.get("notes"), "")
        notes = (notes + " " if notes else "") + f"(noté par le desk{', ' + source if source else ''})"
        cells = {
            "N": str(n), "Date entree": day.strftime("%d/%m/%Y") if day else "?",
            "Jour": JOURS[day.weekday()] if day else "?",
            "Heure entree (Paris)": f"{int(hm):02d}:{round((hm % 1) * 60):02d}" if hm is not None else "?",
            "Date sortie": "?", "Heure sortie (Paris)": "?", "Duree": "?",
            "Session": session_of(day, hm), "Unite de temps": clean(f.get("unite")), "Sens": sens,
            "Fibo haut": price(f.get("fibo_haut")), "Fibo bas": price(f.get("fibo_bas")),
            "Niveau entree": niveau_txt, "FVG sur la zone": fvg, "Entree": fmt(entree), "Stop": fmt(stop),
            "TP1 (0)": fmt(tps[0]), "TP2 (-0.618)": fmt(tps[1]), "TP3": fmt(tps[2]), "Resultat": res,
            "Ratio R": ratio, "Biais 12H": biais, "Position vs EMA": ema, "RSI": clean(f.get("rsi")),
            "Volume": clean(f.get("volume")), "News": "?", "Confluences": clean(f.get("confluences")),
            "Notes": notes, "Capture": capture or "?"}
        row = [clean(cells[c]) for c in COLUMNS]
        info = {"n": n, "day": day, "hour": hm, "sens": sens, "level": level, "fvg": fvg, "ema": ema,
                "biais": biais, "unite": cells["Unite de temps"], "result": res}
        return row, info

    @staticmethod
    def check(info: dict) -> tuple[list[str], list[str]]:
        """Règles de STRATEGIE.md : (écarts, choses à vérifier car pas lisibles)."""
        bad, unsure = [], []
        lv = info["level"]
        if lv == "0.5":
            bad.append("entrée sur le 0.5, interdit par ta règle absolue")
        elif lv != "?" and lv not in NIVEAUX_OK:
            bad.append(f"niveau {lv}, pas dans tes zones 0.618, 0.705, 0.786, 0.893")
        elif lv == "?":
            unsure.append("le niveau de Fibo")
        if info["fvg"] == "Non":
            bad.append("pas de FVG sur la zone")
        elif info["fvg"] == "?":
            unsure.append("le FVG sur la zone")
        h = info["hour"]
        if h is not None and not (2 <= h < 20):
            bad.append("entrée hors de ta fenêtre 2h-20h")
        sens, ema, biais = info["sens"], info["ema"], info["biais"]
        v1 = re.search(r"(?<!\d)(1|12)\s*h", plain(info["unite"])) is not None
        if v1 and sens != "?":
            if (sens == "Short" and ema.startswith("Au-dessus")) or (sens == "Long" and ema.startswith("Sous")):
                bad.append("contre l'EMA 200")
            if (sens == "Short" and biais == "Haussier") or (sens == "Long" and biais == "Baissier"):
                bad.append("contre le biais 12H")
        return bad, unsure

    def summary(self, info: dict, capture: str) -> str:
        bad, unsure = self.check(info)
        day = info["day"].strftime("%d/%m/%Y") if info["day"] else "date inconnue"
        res = info["result"] if info["result"] != "?" else "résultat inconnu"
        out = f"Setup n°{info['n']} ajouté au journal : {day}, {info['sens'] if info['sens'] != '?' else 'sens inconnu'}, {res}."
        if bad:
            out += " Écarts avec ta stratégie : " + ", ".join(bad) + "."
        elif not unsure:
            out += " Conforme à ta stratégie."
        if unsure:
            out += " Pas lisible sur la capture : " + ", ".join(unsure) + ", à compléter dans le fichier."
        if info["n"] % 10 == 0:
            out += f" Tu as {info['n']} setups : dis « Jarvis, analyse mes setups » pour voir les points communs."
        return out

    # ------------------------------------------------------------------ les 2 façons de noter
    def add(self, image: bytes, extra: str = "", result: str = "", when_text: str = "", source: str = "") -> str:
        if self.folder() is None:
            return "Je ne trouve pas ton dossier bot trad sur le Bureau."
        with self.lock:  # une ligne à la fois (numéros sans doublon)
            fields = self.read_chart(image, extra)
            if not result and extra:  # photo + message : l'IA a peut-être repéré le résultat dans le texte
                result = self._result_from_text(extra)
            strict = False
            if not when_text and extra:  # message écrit avec la photo : on lit la date et l'heure prudemment
                when_text, strict = extra, True
            n = self.next_number()
            try:
                day = parse_date(when_text, dt.date.today()) or read_date(clean(fields.get("date_entree"), ""))
                sens = clean(fields.get("sens")).capitalize()
                cap = self._save_capture(image, n, day, sens)
                row, info = self.build(n, fields, result, when_text, capture=cap, source=source, strict_when=strict)
                self._append(row)
            except PermissionError:
                return ("Je n'arrive pas à écrire dans journal_setups.csv : il est sûrement ouvert dans Excel. "
                        "Ferme-le et redemande-moi.")
            except OSError as e:
                log.warning("Journal des setups : %s", e)
                return "Je n'ai pas réussi à écrire dans ton journal des setups."
        log.info("Journal des setups : n°%d ajouté (%s).", n, source or "?")
        return self.summary(info, cap)

    @staticmethod
    def _result_from_text(t: str) -> str:
        p = plain(t)
        m = re.search(r"(tp\s*\d[^,.;]*|stop[^,.;]*|break[- ]?even[^,.;]*|be(?![a-z])[^,.;]*|"
                      r"[+-]\s*\d+(?:[.,]\d+)?\s*r(?![a-z])[^,.;]*|pas (?:encore )?fini[^,.;]*|en cours)", p)
        if not m:
            return ""
        orig = t.replace("’", "'")  # même longueur que le texte sans accents : on garde les accents
        return (orig[m.start():m.end()] if len(orig) == len(p) else m.group(0)).strip()

    # ------------------------------------------------------------------ points communs
    def stats(self) -> str:
        rows = [r for r in self.rows() if len(r) >= 20]
        if not rows:
            return "Ton journal des setups est encore vide."
        col = {c: i for i, c in enumerate(COLUMNS)}

        def top(name: str, k: int = 2) -> str:
            vals = [r[col[name]].strip() for r in rows if r[col[name]].strip() not in ("", "?")]
            if not vals:
                return ""
            c = Counter(v.split(" (")[0] for v in vals).most_common(k)
            return ", ".join(f"{v} ({n})" for v, n in c)

        wins = sum(1 for r in rows if re.search(r"tp|gagn", plain(r[col["Resultat"]])))
        losses = sum(1 for r in rows if re.search(r"(?<![a-z])(stop|sl|perdu|perte)(?![a-z])", plain(r[col["Resultat"]])))
        parts = [f"{len(rows)} setup{'s' if len(rows) > 1 else ''} dans ton journal"]
        if wins or losses:
            parts.append(f"{wins} gagnant{'s' if wins > 1 else ''} et {losses} au stop")
        for label, name in (("Jours", "Jour"), ("Sessions", "Session"), ("Niveaux de Fibo", "Niveau entree"),
                            ("Sens", "Sens"), ("Unités de temps", "Unite de temps")):
            t = top(name)
            if t:
                parts.append(f"{label} : {t}")
        out = ". ".join(parts) + "."
        if len(rows) < 10:
            out += " Il en faut une dizaine pour que les points communs veuillent vraiment dire quelque chose."
        return out
