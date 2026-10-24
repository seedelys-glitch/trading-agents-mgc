# -*- coding: utf-8 -*-
"""
Bougies et outils communs de la veille du desk (repris tels quels de Jarvis, alertes_strategie.py, le 24/10/2026) :
bougie, heure de New York (séances CME), prix écrit à la française, EMA, ATR, cassures de structure (BOS).
Sans réseau : testable.
"""

from __future__ import annotations

import datetime as dt
import unicodedata
from dataclasses import dataclass

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/130.0 Safari/537.36"}


@dataclass
class Bar:
    t: float   # début de la bougie (secondes UTC)
    o: float
    h: float
    l: float
    c: float


# ---------------------------------------------------------------------------
# Heures : Paris (heure du PC) et New York (séances CME)
# ---------------------------------------------------------------------------
def _nth_sunday(year: int, month: int, n: int) -> dt.date:
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(6 - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def ny_offset_s(t: float) -> int:
    """Décalage de New York par rapport à UTC (heure d'été US : 2e dimanche de mars -> 1er dimanche de novembre)."""
    d = dt.datetime.fromtimestamp(t, dt.timezone.utc).date()
    summer = _nth_sunday(d.year, 3, 2) <= d < _nth_sunday(d.year, 11, 1)
    return (-4 if summer else -5) * 3600


def paris(t: float) -> dt.datetime:
    return dt.datetime.fromtimestamp(t)  # le PC est à l'heure de Paris


def fmt_price(x: float) -> str:
    s = f"{x:,.1f}".replace(",", " ").replace(".", ",")
    return s[:-2] if s.endswith(",0") else s


def plain(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


# ---------------------------------------------------------------------------
# Indicateurs
# ---------------------------------------------------------------------------
def ema(values: list[float], n: int) -> list[float]:
    if not values:
        return []
    k = 2 / (n + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(out[-1] + k * (v - out[-1]))
    return out


def atr(bars: list[Bar], n: int = 14) -> list[float]:
    out, a = [], None
    for i, b in enumerate(bars):
        tr = b.h - b.l if i == 0 else max(b.h - b.l, abs(b.h - bars[i - 1].c), abs(b.l - bars[i - 1].c))
        a = tr if a is None else a + (tr - a) / n
        out.append(a)
    return out


def to_12h(bars: list[Bar]) -> list[Bar]:
    """Bougies 12H alignées sur l'ouverture CME (18h New York) : 18h-6h et 6h-18h."""
    out: list[Bar] = []
    key = None
    for b in bars:
        k = int((b.t + ny_offset_s(b.t) - 18 * 3600) // 43200)
        if k != key:
            out.append(Bar(b.t, b.o, b.h, b.l, b.c))
            key = k
        else:
            x = out[-1]
            x.h, x.l, x.c = max(x.h, b.h), min(x.l, b.l), b.c
    return out


def structure(bars: list[Bar], k: int) -> list[tuple[str, int, int, float]]:
    """Cassures de structure (BOS) : (sens, bougie de la cassure, sommet/creux cassé, niveau).
    Un sommet (creux) n'est connu que k bougies après lui : pas de regard vers le futur."""
    hs, ls, cs = [b.h for b in bars], [b.l for b in bars], [b.c for b in bars]
    sh = sl = None
    events = []
    for i in range(len(bars)):
        j = i - k
        if j >= k:
            if hs[j] == max(hs[j - k:j + k + 1]) and hs[j] > max(hs[j - k:j]):
                sh = (j, hs[j])
            if ls[j] == min(ls[j - k:j + k + 1]) and ls[j] < min(ls[j - k:j]):
                sl = (j, ls[j])
        if sh and cs[i] > sh[1]:
            events.append(("haussier", i, sh[0], sh[1]))
            sh = None
        if sl and cs[i] < sl[1]:
            events.append(("baissier", i, sl[0], sl[1]))
            sl = None
    return events
