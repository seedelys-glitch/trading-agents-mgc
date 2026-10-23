# -*- coding: utf-8 -*-
import datetime as dt

import pytest

from mgc import calendrier_cme as cal

D = dt.date


def chicago(*args):
    return dt.datetime(*args, tzinfo=cal.CHICAGO)


def paris(*args):
    return dt.datetime(*args, tzinfo=cal.PARIS)


def test_paques():
    assert cal.paques(2026) == D(2026, 4, 5)
    assert cal.paques(2027) == D(2027, 3, 28)


def test_jours_feries():
    assert cal.ferie(D(2026, 4, 3)) == "Vendredi saint"
    assert cal.ferie(D(2026, 11, 26)) == "Thanksgiving"
    assert cal.ferie(D(2026, 5, 25)) == "Memorial Day"
    assert cal.ferie(D(2026, 9, 7)) == "Labor Day"
    assert cal.ferie(D(2027, 1, 18)) == "Martin Luther King Day"
    assert cal.ferie(D(2027, 12, 24)) == "Noël"          # 25/12/2027 est un samedi
    assert cal.ferie(D(2026, 7, 3)) == "Independence Day"  # 04/07/2026 est un samedi
    assert cal.ferie(D(2027, 1, 1)) == "Jour de l'an"
    assert cal.ferie(D(2027, 12, 31)) is None              # 01/01/2028 un samedi : pas de report
    assert cal.ferie(D(2026, 11, 27)) is None


def test_jours_ouvres():
    assert cal.est_jour_ouvre(D(2026, 10, 19))
    assert not cal.est_jour_ouvre(D(2026, 10, 17))  # samedi
    assert not cal.est_jour_ouvre(D(2026, 11, 26))  # Thanksgiving
    assert cal.decaler_jours_ouvres(D(2026, 11, 30), -2) == D(2026, 11, 25)
    assert cal.decaler_jours_ouvres(D(2026, 10, 16), 1) == D(2026, 10, 19)
    assert cal.jours_ouvres_entre(D(2026, 11, 18), D(2026, 11, 25)) == 5
    assert cal.jours_ouvres_entre(D(2026, 11, 25), D(2026, 11, 25)) == 0


def test_dernier_jour_ouvre_du_mois():
    assert cal.dernier_jour_ouvre_du_mois(2026, 11) == D(2026, 11, 30)
    assert cal.dernier_jour_ouvre_du_mois(2026, 12, rang=3) == D(2026, 12, 29)
    assert cal.dernier_jour_ouvre_du_mois(2027, 1) == D(2027, 1, 29)


@pytest.mark.parametrize("instant, etat", [
    (chicago(2026, 10, 20, 10, 0), "ouverte"),
    (chicago(2026, 10, 20, 15, 59), "ouverte"),
    (chicago(2026, 10, 20, 16, 0), "pause"),
    (chicago(2026, 10, 20, 16, 59), "pause"),
    (chicago(2026, 10, 20, 17, 0), "ouverte"),
    (chicago(2026, 10, 16, 16, 0), "fermée"),   # vendredi 16h
    (chicago(2026, 10, 17, 12, 0), "fermée"),   # samedi
    (chicago(2026, 10, 18, 16, 59), "fermée"),  # dimanche avant l'ouverture
    (chicago(2026, 10, 18, 17, 0), "ouverte"),  # dimanche 17h
    (chicago(2027, 3, 26, 10, 0), "fermée"),    # Vendredi saint
    (chicago(2027, 3, 25, 17, 30), "fermée"),   # jeudi soir : la séance compte pour le Vendredi saint
    (chicago(2026, 11, 26, 10, 0), "spéciale"),  # Thanksgiving
    (chicago(2026, 11, 25, 18, 0), "spéciale"),  # veille au soir : séance de Thanksgiving
])
def test_etat_seance(instant, etat):
    assert cal.etat_seance(instant)["etat"] == etat


def test_changements_d_heure_decales():
    # 20/10 : Paris UTC+2, Chicago UTC-5 (7 h d'écart) ; 27/10 : Paris déjà en hiver (6 h d'écart)
    assert cal.etat_seance(paris(2026, 10, 20, 23, 30))["etat"] == "pause"
    assert cal.etat_seance(paris(2026, 10, 27, 22, 30))["etat"] == "pause"
    assert cal.etat_seance(paris(2026, 10, 27, 23, 30))["etat"] == "ouverte"
    assert cal.etat_seance(paris(2026, 11, 3, 23, 30))["etat"] == "pause"  # les deux en hiver


def test_jour_de_negociation():
    assert cal.jour_de_negociation(chicago(2026, 10, 18, 17, 0)) == D(2026, 10, 19)
    assert cal.jour_de_negociation(chicago(2026, 10, 19, 9, 0)) == D(2026, 10, 19)


@pytest.mark.parametrize("instant, dedans", [
    (paris(2026, 10, 20, 15, 29), False),
    (paris(2026, 10, 20, 15, 30), True),
    (paris(2026, 10, 20, 19, 59), True),
    (paris(2026, 10, 20, 20, 0), False),
    (paris(2026, 10, 17, 16, 0), False),  # samedi
    (chicago(2026, 10, 20, 8, 45), True),  # 15h45 à Paris
])
def test_fenetre_paris(instant, dedans):
    assert cal.dans_fenetre(instant, ["15:30", "20:00"]) is dedans


def test_heure_sans_fuseau_refusee():
    with pytest.raises(ValueError):
        cal.etat_seance(dt.datetime(2026, 10, 20, 10, 0))
    with pytest.raises(ValueError):
        cal.dans_fenetre(dt.datetime(2026, 10, 20, 16, 0), ["15:30", "20:00"])
