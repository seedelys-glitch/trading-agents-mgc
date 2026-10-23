# -*- coding: utf-8 -*-
import json

from mgc import config as cfg


def test_limite_lue_dans_les_regles_de_jarvis(tmp_path):
    regles = tmp_path / "prop-firm.txt"
    regles.write_text("# commentaire\nLIMITE_PERTE_JOUR=1000\nOBJECTIF_JOUR=\n", encoding="utf-8")
    assert cfg.limite_jarvis(regles) == 1000.0
    regles.write_text("LIMITE_PERTE_JOUR=\n", encoding="utf-8")
    assert cfg.limite_jarvis(regles) is None
    assert cfg.limite_jarvis(tmp_path / "absent.txt") is None


def test_charger_defauts_et_fichier_perso(tmp_path):
    regles = tmp_path / "prop-firm.txt"
    regles.write_text("LIMITE_PERTE_JOUR=750\n", encoding="utf-8")
    c = cfg.charger(tmp_path / "absent.json", regles)
    assert c["risque_pct"] == 1.0
    assert c["limite_perte_jour_usd"] == 750.0
    perso = tmp_path / "config_mgc.json"
    perso.write_text(json.dumps({"risque_pct": 0.5, "inconnu": 1}), encoding="utf-8")
    c = cfg.charger(perso, regles)
    assert c["risque_pct"] == 0.5
    assert "inconnu" not in c


def test_repli_a_1000_dollars(tmp_path):
    c = cfg.charger(tmp_path / "absent.json", tmp_path / "absent.txt")
    assert c["limite_perte_jour_usd"] == 1000.0


def test_empreinte_stable(config):
    assert cfg.empreinte(config) == cfg.empreinte(dict(config))
    autre = dict(config, risque_pct=0.5)
    assert cfg.empreinte(autre) != cfg.empreinte(config)
