# -*- coding: utf-8 -*-
"""Bibliothèque : règles lues mot pour mot, validation par Jabran, versions gardées, recherche."""

import pytest
from conftest import executer_tout

from universite import bibliotheque
from universite.base import MIGRATIONS, Base

STRATEGIE = """# Stratégie
## Marche et horaires
- Prise de position : de 15h30 a 20h (heure de Paris)
- Plateforme : MT5

## Gestion des trades
- Compte A : 25 % fermes a chaque objectif
  1. 25 % au 0
  2. 25 % au -0.272
Texte libre qui n'est pas une règle.
- Stop = haut du FVG + 20 % de sa hauteur
"""


def test_lecture_mot_pour_mot_avec_source():
    regles = bibliotheque.lire_regles(STRATEGIE, "STRATEGIE.md")
    assert [r["theme"] for r in regles] == ["Marche et horaires"] * 2 + ["Gestion des trades"] * 2
    assert regles[2]["texte"] == "Compte A : 25 % fermes a chaque objectif\n1. 25 % au 0\n2. 25 % au -0.272"
    assert regles[3]["source"] == {"fichier": "STRATEGIE.md", "section": "Gestion des trades", "ligne": 11}


def test_versions_et_validation(base):
    r = bibliotheque.lire_regles(STRATEGIE, "S.md")[0]
    assert bibliotheque.proposer(base, r, 9) == "nouvelle"
    assert bibliotheque.proposer(base, r, 9) is None                    # inchangée : rien de neuf
    v1 = bibliotheque.derniere(base, r["cle"])
    bibliotheque.decider(base, v1["id"], "validee")
    r2 = dict(r, texte="Prise de position : de 15h30 a 21h (heure de Paris)")
    assert bibliotheque.proposer(base, r2, 9) == "version"
    v2 = bibliotheque.derniere(base, r["cle"])
    assert v2["version"] == 2 and v2["precedente"] == v1["id"]
    assert base.un("SELECT statut FROM regles WHERE id=?", (v1["id"],))["statut"] == "validee"   # reste valable
    bibliotheque.decider(base, v2["id"], "validee")
    assert base.un("SELECT statut FROM regles WHERE id=?", (v1["id"],))["statut"] == "remplacee"
    with pytest.raises(ValueError):
        bibliotheque.decider(base, v2["id"], "rejetee")                  # déjà décidée


def test_correction_par_jabran_cree_une_version(base):
    r = bibliotheque.lire_regles(STRATEGIE, "S.md")[1]
    bibliotheque.proposer(base, r, 9)
    v1 = bibliotheque.derniere(base, r["cle"])
    v2 = bibliotheque.modifier(base, v1["id"], "Plateforme : MT5, compte islamique")
    assert v2["version"] == 2 and v2["source"]["modifiee_par"] == "jabran"
    assert base.un("SELECT COUNT(*) AS n FROM regles")["n"] == 2


def test_extraction_par_l_agent_9(moteur, tmp_path):
    f = tmp_path / "STRATEGIE.md"
    f.write_text(STRATEGIE, encoding="utf-8")
    m = moteur.base.nouvelle_mission(9, "extraction_regles", "x", {"fichiers": [str(f)]})
    executer_tout(moteur)
    r = moteur.base.mission(m)["resultat"]
    assert (r["nouvelles"], r["inchangees"]) == (4, 0) and r["extraits"] >= 1
    m2 = moteur.base.nouvelle_mission(9, "extraction_regles", "x", {"fichiers": [str(f)]})
    executer_tout(moteur)
    assert moteur.base.mission(m2)["resultat"]["inchangees"] == 4
    assert f.read_text(encoding="utf-8") == STRATEGIE                     # fichier de Jabran intact


def test_fichier_absent_est_une_erreur(moteur, tmp_path):
    m = moteur.base.nouvelle_mission(9, "extraction_regles", "x", {"fichiers": [str(tmp_path / "rien.md")]})
    executer_tout(moteur)
    assert moteur.base.mission(m)["statut"] == "erreur"


def test_recherche_par_mots(base):
    for r in bibliotheque.lire_regles(STRATEGIE, "S.md"):
        bibliotheque.proposer(base, r, 9)
    bibliotheque.indexer_texte(base, "fichier:S.md", "S.md", STRATEGIE)
    res = bibliotheque.rechercher(base, "stop FVG hauteur")
    assert res and "FVG" in res[0]["texte"]
    assert bibliotheque.rechercher(base, "bitcoin") == []


def test_indexation_sans_modele_d_embeddings(moteur):
    moteur.base.document(6, "analyse", "Doc", "Le VWAP de séance est au-dessus de l'EMA.", statut="verifie")
    m = moteur.base.nouvelle_mission(9, "indexation_bibliotheque", "x", {})
    executer_tout(moteur)
    r = moteur.base.mission(m)["resultat"]
    assert r["extraits_ecrits"] == 1 and r["vecteurs_ajoutes"] == 0 and "désactivée" in r["remarque"]


def test_migration_2_reversible(tmp_path):
    b = Base(tmp_path / "m.sqlite")
    assert b.version() == MIGRATIONS[-1][0] == 2
    b.migrer(1)
    assert not b.lire("SELECT name FROM sqlite_master WHERE name='regles'")
    assert b.migrer() == 2
