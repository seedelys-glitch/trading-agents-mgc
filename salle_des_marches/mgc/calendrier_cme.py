# -*- coding: utf-8 -*-
"""
Calendrier CME : jours fériés, jours ouvrés, état de la séance Globex et fenêtre de trading de Paris.

Approximation assumée (à comparer chaque année au calendrier officiel « CME Globex Holiday ») :
  - fermés toute la journée : Jour de l'an, Vendredi saint, Noël ;
  - séance réduite (ouverte mais sans séance normale) : Martin Luther King, Presidents' Day, Memorial Day,
    Juneteenth, 4 juillet, Labor Day, Thanksgiving. Ces jours-là, rien n'est présenté comme exploitable.
Les fermetures anticipées des veilles de fête (24/12, 31/12...) ne sont pas modélisées.
"""

import datetime as dt
from functools import lru_cache
from zoneinfo import ZoneInfo

CHICAGO = ZoneInfo("America/Chicago")
PARIS = ZoneInfo("Europe/Paris")
OUVERTURE = dt.time(17, 0)   # heure de Chicago
FERMETURE = dt.time(16, 0)   # heure de Chicago (début de la pause quotidienne)


def paques(annee):
    """Dimanche de Pâques (calendrier grégorien)."""
    a, b, c = annee % 19, annee // 100, annee % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741 (nom de l'algorithme d'origine)
    m = (a + 11 * h + 22 * l) // 451
    mois = (h + l - 7 * m + 114) // 31
    jour = (h + l - 7 * m + 114) % 31 + 1
    return dt.date(annee, mois, jour)


def _nieme(annee, mois, jour_semaine, n):
    """n-ième jour_semaine (0 = lundi) du mois ; n = -1 pour le dernier."""
    if n > 0:
        premier = dt.date(annee, mois, 1)
        return premier + dt.timedelta(days=(jour_semaine - premier.weekday()) % 7 + 7 * (n - 1))
    suivant = dt.date(annee + mois // 12, mois % 12 + 1, 1)
    dernier = suivant - dt.timedelta(days=1)
    return dernier - dt.timedelta(days=(dernier.weekday() - jour_semaine) % 7)


def _observe(jour):
    """Fête un samedi -> vendredi ; un dimanche -> lundi."""
    if jour.weekday() == 5:
        return jour - dt.timedelta(days=1)
    if jour.weekday() == 6:
        return jour + dt.timedelta(days=1)
    return jour


@lru_cache(maxsize=32)
def feries_fermes(annee):
    jours = {paques(annee) - dt.timedelta(days=2): "Vendredi saint", _observe(dt.date(annee, 12, 25)): "Noël"}
    nouvel_an = dt.date(annee, 1, 1)
    if nouvel_an.weekday() != 5:  # un samedi : pas de jour férié reporté
        jours[_observe(nouvel_an)] = "Jour de l'an"
    return jours


@lru_cache(maxsize=32)
def feries_reduits(annee):
    return {
        _nieme(annee, 1, 0, 3): "Martin Luther King Day",
        _nieme(annee, 2, 0, 3): "Presidents' Day",
        _nieme(annee, 5, 0, -1): "Memorial Day",
        _observe(dt.date(annee, 6, 19)): "Juneteenth",
        _observe(dt.date(annee, 7, 4)): "Independence Day",
        _nieme(annee, 9, 0, 1): "Labor Day",
        _nieme(annee, 11, 3, 4): "Thanksgiving",
    }


def ferie(jour):
    """Nom du jour férié CME, ou None."""
    return feries_fermes(jour.year).get(jour) or feries_reduits(jour.year).get(jour)


def est_jour_ouvre(jour):
    return jour.weekday() < 5 and ferie(jour) is None


def decaler_jours_ouvres(jour, n):
    """Avance (n > 0) ou recule (n < 0) de n jours ouvrés."""
    pas = 1 if n >= 0 else -1
    while n:
        jour += dt.timedelta(days=pas)
        if est_jour_ouvre(jour):
            n -= pas
    return jour


def dernier_jour_ouvre_du_mois(annee, mois, rang=1):
    """rang = 1 : dernier jour ouvré ; rang = 3 : 3e dernier jour ouvré."""
    jour = dt.date(annee + mois // 12, mois % 12 + 1, 1)
    while rang:
        jour -= dt.timedelta(days=1)
        if est_jour_ouvre(jour):
            rang -= 1
    return jour


def jours_ouvres_entre(debut, fin):
    """Nombre de jours ouvrés après `debut`, jusqu'à `fin` inclus (0 si fin <= debut)."""
    n, jour = 0, debut
    while jour < fin:
        jour += dt.timedelta(days=1)
        n += est_jour_ouvre(jour)
    return n


def _chicago(instant):
    if instant.tzinfo is None:
        raise ValueError("L'heure doit avoir un fuseau horaire.")
    return instant.astimezone(CHICAGO)


def jour_de_negociation(instant):
    """Après 17h à Chicago, la séance compte déjà pour le jour suivant (règle du CME)."""
    t = _chicago(instant)
    return t.date() + dt.timedelta(days=1) if t.time() >= OUVERTURE else t.date()


def etat_seance(instant):
    """État de la séance Globex : « ouverte », « pause », « fermée » ou « spéciale », avec le motif."""
    t = _chicago(instant)
    heure, js = t.time(), t.weekday()
    if js == 5 or (js == 6 and heure < OUVERTURE) or (js == 4 and heure >= FERMETURE):
        return {"etat": "fermée", "motif": "Marché fermé (week-end)."}
    if FERMETURE <= heure < OUVERTURE:
        return {"etat": "pause", "motif": "Pause quotidienne du CME (16h-17h à Chicago)."}
    seance = jour_de_negociation(instant)
    nom = feries_fermes(seance.year).get(seance)
    if nom:
        return {"etat": "fermée", "motif": f"Marché fermé ({nom})."}
    nom = feries_reduits(seance.year).get(seance)
    if nom:
        return {"etat": "spéciale", "motif": f"Séance réduite ({nom}) : liquidité anormale."}
    return {"etat": "ouverte", "motif": "", "jour_de_negociation": seance.isoformat()}


def dans_fenetre(instant, fenetre):
    """True si l'heure de Paris est dans la fenêtre de trading (du lundi au vendredi)."""
    if instant.tzinfo is None:
        raise ValueError("L'heure doit avoir un fuseau horaire.")
    t = instant.astimezone(PARIS)
    debut, fin = (dt.time.fromisoformat(h) for h in fenetre)
    return t.weekday() < 5 and debut <= t.time() < fin
