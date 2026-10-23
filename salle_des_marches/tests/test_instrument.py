# -*- coding: utf-8 -*-
import pytest

from mgc import instrument as ins


def test_valeurs_du_contrat():
    assert ins.ONCES == 10
    assert ins.TICK == 0.10
    assert ins.VALEUR_TICK == 1.0
    assert ins.VALEUR_POINT == 10.0


@pytest.mark.parametrize("points, ticks", [(1.0, 10), (0.1, 1), (1.3, 13), (4200.3 - 4199.0, 13), (-2.5, 25), (0.0, 0)])
def test_points_en_ticks(points, ticks):
    assert ins.points_en_ticks(points) == ticks


def test_points_en_ticks_arrondit_au_dessus():
    assert ins.points_en_ticks(0.15) == 2


def test_conversions_dollars():
    assert ins.points_en_usd(1.0) == 10.0
    assert ins.points_en_usd(5.0, contrats=3) == 150.0
    assert ins.ticks_en_usd(50) == 50.0
    assert ins.ticks_en_usd(50, contrats=2) == 100.0
    assert ins.usd_en_points(10.0) == 1.0
    assert ins.usd_en_points(150.0, contrats=3) == 5.0
    with pytest.raises(ValueError):
        ins.usd_en_points(10.0, contrats=0)


def test_grille_et_arrondi():
    assert ins.sur_grille(4200.1)
    assert ins.sur_grille(4200.0)
    assert not ins.sur_grille(4200.05)
    assert ins.arrondi_tick(4200.06) == 4200.1
    assert ins.arrondi_tick(4200.04) == 4200.0
    assert ins.arrondi_tick(4200.01, "haut") == 4200.1
    assert ins.arrondi_tick(4200.09, "bas") == 4200.0


def test_codes_des_12_mois():
    assert ins.code_contrat(2026, 12) == "MGCZ26"
    assert ins.lire_code("MGCZ26") == (2026, 12)
    assert ins.lire_code("mgcg27.cmx") == (2027, 2)
    for mois in range(1, 13):
        assert ins.lire_code(ins.code_contrat(2027, mois)) == (2027, mois)


@pytest.mark.parametrize("code", ["MGC1!", "GCZ26", "MGCA26", "MGCZ2", "MGCZXX"])
def test_codes_invalides(code):
    with pytest.raises(ValueError):
        ins.lire_code(code)


def test_mois_invalide():
    with pytest.raises(ValueError):
        ins.code_contrat(2026, 13)
