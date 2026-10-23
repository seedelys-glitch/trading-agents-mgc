# -*- coding: utf-8 -*-
"""Base persistante, import de fichiers et fenêtre de replay sans look-ahead."""

import threading

import pytest
from conftest import DEBUT, bougies_m1

from universite import donnees
from universite.base import MIGRATIONS, Base


def test_migrations_montent_et_descendent(tmp_path):
    b = Base(tmp_path / "m.sqlite")
    assert b.version() == MIGRATIONS[-1][0]
    assert b.migrer(0) == 0
    assert not b.lire("SELECT name FROM sqlite_master WHERE name='missions'")
    assert b.migrer() == MIGRATIONS[-1][0]


def test_deux_ouvriers_ne_prennent_jamais_la_meme_mission(base):
    for i in range(30):
        base.nouvelle_mission(6, "analyse_vwap_ema", f"m{i}", {})
    pris, verrou = [], threading.Lock()

    def ouvrier():
        while (m := base.prendre_mission()) is not None:
            with verrou:
                pris.append(m["id"])

    fils = [threading.Thread(target=ouvrier) for _ in range(4)]
    [f.start() for f in fils]
    [f.join() for f in fils]
    assert sorted(pris) == list(range(1, 31))


def test_reprise_apres_arret(tmp_path):
    b = Base(tmp_path / "r.sqlite")
    m = b.nouvelle_mission(6, "analyse_vwap_ema", "coupée", {})
    b.prendre_mission()
    b.debut_etape(m, 6, "recherche", "travail en cours", "chercheur")
    b.fermer()
    b2 = Base(tmp_path / "r.sqlite")           # « redémarrage »
    assert b2.reprendre_interrompues() == [m]
    assert b2.mission(m)["statut"] == "en_attente"
    assert b2.lire("SELECT statut FROM etapes")[0]["statut"] == "interrompue"


def test_lecture_csv_tradingview():
    texte = "time,open,high,low,close,Volume\n" \
            "1792360800,4000,4001,3999,4000.5,12\n" \
            "1792360860,4000.5,4002,4000,4001,8\n" \
            "1792360920,4001,3990,4002,4001,5\n" \
            "pas une date,1,2,3,4,5\n"
    lignes, rapport = donnees.lire_csv(texte)
    assert len(lignes) == 2 and rapport["incoherentes"] == 1 and rapport["abimees"] == 1
    assert donnees.deviner_unite(lignes) == "M1"


def test_lecture_csv_ninjatrader_et_dates_iso():
    texte = "debut_utc,o,h,l,c,v\n2026-10-19T22:00:00Z,4000,4001,3999,4000,1\n2026-10-19T22:05:00Z,4000,4001,3999,4000,1\n"
    lignes, _ = donnees.lire_csv(texte)
    assert lignes[0][0] == 1792447200.0 and donnees.deviner_unite(lignes) == "M5"


def test_colonnes_manquantes_refusees():
    with pytest.raises(donnees.ErreurDonnees):
        donnees.lire_csv("date,prix\n1,2\n")


def test_une_bougie_non_fermee_est_invisible(base, jeu):
    instant = DEBUT + 60 * 100 + 30          # en plein milieu de la 101e bougie
    f = donnees.fenetre(base, jeu, "M1", instant)["bougies"]
    assert len(f) == 100 and f[-1][0] + 60 <= instant


def test_regroupement_seulement_des_creneaux_termines(base, jeu):
    instant = DEBUT + 3600 * 5 + 60 * 59     # 5 h 59 après le début : la 6e heure n'est pas finie
    h1 = donnees.fenetre(base, jeu, "H1", instant)
    assert h1["reconstruite_depuis"] == "M1"
    assert len(h1["bougies"]) == 5 and all(b[0] + 3600 <= instant for b in h1["bougies"])
    m1 = bougies_m1(60)
    premiere = h1["bougies"][0]
    assert premiere[1] == m1[0][1] and premiere[4] == m1[-1][4]
    assert premiere[2] == max(b[2] for b in m1) and premiere[5] == sum(b[5] for b in m1)


def test_les_bougies_futures_ne_changent_rien(base, tmp_path):
    """Même fenêtre avec ou sans les bougies postérieures à l'instant dans la base."""
    tout = bougies_m1(3000)
    instant = DEBUT + 60 * 2000 + 17
    j1 = donnees.creer_jeu(base, "complet", "test", "MGC")
    donnees.ajouter_bougies(base, j1, "M1", tout)
    j2 = donnees.creer_jeu(base, "tronqué", "test", "MGC")
    donnees.ajouter_bougies(base, j2, "M1", [b for b in tout if b[0] + 60 <= instant])
    for u in ("M1", "M5", "M15", "H1"):
        assert donnees.fenetre(base, j1, u, instant, 300) == donnees.fenetre(base, j2, u, instant, 300)


def test_debut_de_seance_cme():
    assert donnees.debut_seance(DEBUT + 5400) == DEBUT          # 18 h 30 à Chicago -> ouverte à 17 h
    assert donnees.debut_seance(DEBUT - 60) == DEBUT - 86400     # 16 h 59 -> séance de la veille


def test_controle_ignore_pause_et_week_end(base):
    j = donnees.creer_jeu(base, "c", "test", "MGC")
    lignes = bougies_m1(60) + [(b[0] + 3600 * 3, *b[1:]) for b in bougies_m1(10)]
    donnees.ajouter_bougies(base, j, "M1", lignes)
    r = donnees.controle(base, j)["unites"]["M1"]
    assert r["n"] == 70 and r["longues_coupures"] == 1
