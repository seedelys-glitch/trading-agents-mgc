"""
L'entraînement des agents (31/10/2026) : chaque agent apprend sa spécialité et le PROUVE.

Un agent de l'université est un calcul (Python) + une IA locale qui rédige. « Comprendre sa spécialité » veut donc
dire trois choses, chacune vérifiée par une épreuve notée sur 20 et enregistrée (table `examens`) :

1. Le cours (PROGRAMME) : pour chaque agent, les sujets de sa spécialité, avec la définition de référence.
2. Les examens « cas d'école » : des bougies FABRIQUÉES dont la bonne réponse est connue par construction
   (une impulsion de 2000 à 2100 a son 0.618 à 2038,2...). L'agent répond avec son vrai calcul, celui des analyses.
   Un examen raté = le calcul ne suit pas le cours = un défaut à corriger (leçon + alerte au directeur).
   Les chiffres changent chaque jour (graine du jour) : on ne peut pas réussir « par cœur ».
3. Les travaux pratiques en replay : sur les VRAIES bougies gardées, à des instants passés tirés au hasard,
   l'agent fait sa lecture avec les seules bougies fermées à cet instant (pas de look-ahead), puis on regarde
   ce que le gold a fait ensuite. On mesure si sa lecture a aidé, comparée au hasard, avec l'intervalle de Wilson.
   Moins de 30 cas = « échantillon insuffisant » : rien n'est conclu.
4. Le quiz de l'IA locale : des questions à choix sur le cours ; l'IA qui rédige les commentaires doit répondre
   juste (une seule lettre attendue). Sans LM Studio, le quiz est noté « non passé », jamais inventé.

Chaque erreur devient une leçon dans la table `lecons` du Mentor (si elle existe), relue avant les missions du
même type. Recherche et simulation seulement : aucun ordre, aucun courtier.
"""

import datetime as dt
import hashlib
import json
import math
import random
import re
import tempfile
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config

PARIS = ZoneInfo("Europe/Paris")
DEPART = 1_791_900_000.0 - (1_791_900_000.0 % 3600)   # un lundi d'octobre 2026, heure ronde (bougies fabriquées)
NOTE_REUSSITE = 14          # sur 20 : en dessous, l'examen est raté
MIN_CAS = 30                # travaux pratiques : en dessous, « échantillon insuffisant »

# ------------------------------------------------------------------ le programme (le cours de chaque agent)
# examen = fonction de cas d'école ci-dessous (None = cours seulement, pas encore d'épreuve automatique) ;
# quiz = question à choix pour l'IA (bonne lettre en premier champ).
PROGRAMME = {
    1: [
        {"cle": "pivots", "wikipedia": "Analyse technique", "titre": "Sommets et creux confirmés",
         "resume": "Un sommet (creux) est confirmé quand les 3 bougies de chaque côté ont un plus haut plus bas "
                   "(un plus bas plus haut). On ne le connaît donc que 3 bougies après.",
         "quiz": ("B", "Quand un sommet de structure est-il confirmé ?",
                  {"A": "Dès que la bougie ferme", "B": "Quand les bougies suivantes font des plus hauts plus bas",
                   "C": "Quand le volume augmente", "D": "Jamais, on le devine"})},
        {"cle": "bos", "wikipedia": "Analyse technique", "titre": "BOS : cassure dans le sens de la tendance", "examen": "smc_bos",
         "resume": "En tendance haussière, une CLÔTURE au-dessus du dernier sommet confirmé est un BOS haussier "
                   "(la tendance continue). Une mèche seule ne casse rien.",
         "quiz": ("C", "En tendance haussière, qu'est-ce qu'un BOS ?",
                  {"A": "Une mèche sous le dernier creux", "B": "Une clôture sous le dernier creux",
                   "C": "Une clôture au-dessus du dernier sommet", "D": "Un croisement de moyennes"})},
        {"cle": "choch", "wikipedia": "Analyse technique", "titre": "CHoCH : changement de caractère", "examen": "smc_choch",
         "resume": "En tendance haussière, une clôture SOUS le dernier creux confirmé est un CHoCH baissier : "
                   "la structure change de sens.",
         "quiz": ("A", "En tendance haussière, une clôture sous le dernier creux confirmé est :",
                  {"A": "Un CHoCH baissier", "B": "Un BOS haussier", "C": "Un order block", "D": "Rien du tout"})},
        {"cle": "fvg_ob", "wikipedia": "Liquidité (finance)", "titre": "FVG et order blocks",
         "resume": "FVG haussier : le plus bas de la bougie 3 est au-dessus du plus haut de la bougie 1. Order block "
                   "haussier : dernière bougie baissière avant l'impulsion qui a fait la cassure.",
         "quiz": ("D", "Un FVG haussier existe quand :",
                  {"A": "La bougie 2 est verte", "B": "Le volume double", "C": "Le prix touche l'EMA 200",
                   "D": "Le plus bas de la bougie 3 est au-dessus du plus haut de la bougie 1"})},
    ],
    2: [
        {"cle": "impulsion", "wikipedia": "Retracement de Fibonacci", "titre": "Choisir la bonne impulsion", "examen": "fibo_niveaux",
         "resume": "On trace sur la dernière impulsion nette H1 (au moins 2,5 ATR), du creux au sommet confirmés. "
                   "0 = fin de l'impulsion, 1 = départ.",
         "quiz": ("B", "Sur une impulsion haussière, où est le niveau 1 du Fibonacci ?",
                  {"A": "Au sommet", "B": "Au départ (le creux)", "C": "Au milieu", "D": "Au prix actuel"})},
        {"cle": "zones", "wikipedia": "Retracement de Fibonacci", "titre": "Zones d'entrée 0.618 à 0.893, jamais le 0.5", "examen": "fibo_zones",
         "resume": "Selon STRATEGIE.md, les entrées se cherchent entre 0.618 et 0.893 (0.618, 0.705, 0.786, 0.893). "
                   "Le 0.5 est une zone interdite pour entrer. Au-delà de 1, le Fibo est invalidé.",
         "quiz": ("A", "Dans la stratégie de Jabran, le niveau 0.5 est :",
                  {"A": "Une zone interdite pour entrer", "B": "La meilleure entrée", "C": "L'objectif", "D": "Le stop"})},
    ],
    3: [
        {"cle": "nuage", "wikipedia": "Ichimoku Kinko Hyo", "titre": "Le prix et le nuage", "examen": "ichimoku_tendance",
         "resume": "Le nuage sous le prix actuel est celui calculé il y a 26 bougies (Senkou A et B décalés). "
                   "Prix au-dessus = contexte haussier, dessous = baissier, dedans = indécis.",
         "quiz": ("C", "Le nuage d'Ichimoku visible sous la bougie actuelle a été calculé :",
                  {"A": "Sur la bougie actuelle", "B": "Sur les 9 dernières bougies", "C": "Il y a 26 bougies",
                   "D": "Sur le jour précédent"})},
        {"cle": "tenkan_kijun", "wikipedia": "Ichimoku Kinko Hyo", "titre": "Tenkan et Kijun", "examen": "ichimoku_tenkan",
         "resume": "Tenkan = milieu du plus haut et du plus bas des 9 dernières bougies ; Kijun = la même chose "
                   "sur 26 bougies. Une Kijun plate attire souvent le prix.",
         "quiz": ("B", "La Tenkan-sen se calcule comme :",
                  {"A": "La moyenne des 9 dernières clôtures", "B": "(plus haut 9 + plus bas 9) / 2",
                   "C": "La clôture d'il y a 26 bougies", "D": "Le volume moyen"})},
        {"cle": "chikou", "wikipedia": "Ichimoku Kinko Hyo", "titre": "La Chikou",
         "resume": "La Chikou est la clôture actuelle reportée 26 bougies en arrière : on la compare au prix "
                   "d'il y a 26 bougies.",
         "quiz": ("A", "La Chikou compare la clôture actuelle :",
                  {"A": "Au prix d'il y a 26 bougies", "B": "Au nuage futur", "C": "À la Kijun", "D": "Au VWAP"})},
    ],
    4: [
        {"cle": "carnet", "wikipedia": "Carnet d'ordres", "titre": "Lire une heatmap de liquidité",
         "resume": "Murs d'ordres, absorption, zones vidées : seulement avec un vrai carnet (Bookmap). On ne déduit "
                   "jamais un carnet d'ordres de simples bougies. L'agent reste en attente des données Bookmap.",
         "quiz": ("D", "Sans données Bookmap, l'agent heatmap doit :",
                  {"A": "Deviner les murs avec les bougies", "B": "Copier le DOM", "C": "Inventer une moyenne",
                   "D": "Dire qu'il attend les données"})},
    ],
    5: [
        {"cle": "heures", "wikipedia": "Heure d'été", "titre": "Heures des annonces en heure de Paris", "examen": "macro_heures",
         "resume": "Les annonces américaines tombent à 8h30 New York. L'Europe passe à l'heure d'hiver le dernier "
                   "dimanche d'octobre, les États-Unis le premier dimanche de novembre : pendant cette semaine-là, "
                   "8h30 New York = 13h30 à Paris (et non 14h30).",
         "quiz": ("B", "Le vendredi 30 octobre 2026, une annonce de 8h30 New York tombe à Paris à :",
                  {"A": "14h30", "B": "13h30", "C": "15h30", "D": "8h30"})},
        {"cle": "majeures", "wikipedia": "Federal Open Market Committee", "titre": "Les annonces qui bougent le gold",
         "resume": "CPI (inflation), NFP (emploi), FOMC (taux de la Fed), PCE : impact fort sur le dollar et l'or. "
                   "Le gestionnaire des risques est prévenu quand une annonce majeure arrive dans l'heure.",
         "quiz": ("C", "Laquelle de ces annonces a le plus d'impact sur le gold ?",
                  {"A": "Les ventes de voitures au Japon", "B": "La météo", "C": "Le NFP (emploi américain)",
                   "D": "Le prix du blé"})},
    ],
    6: [
        {"cle": "vwap", "wikipedia": "Prix moyen pondéré par le volume", "titre": "VWAP de séance", "examen": "vwap_exact",
         "resume": "VWAP = somme(prix typique x volume) / somme(volume), prix typique = (haut + bas + clôture) / 3, "
                   "depuis l'ouverture de séance CME (17 h Chicago = 18 h New York).",
         "quiz": ("A", "Le prix typique utilisé pour le VWAP est :",
                  {"A": "(haut + bas + clôture) / 3", "B": "L'ouverture", "C": "(haut + bas) / 2 seulement",
                   "D": "La clôture de la veille"})},
        {"cle": "ema200", "wikipedia": "Moyenne mobile", "titre": "EMA 200 : niveau et pente", "examen": "ema_retard",
         "resume": "L'EMA 200 suit le prix avec du retard : sur une hausse régulière de a points par bougie, elle "
                   "reste environ 99,5 x a points sous le prix. Il faut au moins 200 bougies fermées.",
         "quiz": ("D", "Combien de bougies fermées faut-il au minimum pour une EMA 200 sérieuse ?",
                  {"A": "20", "B": "50", "C": "100", "D": "200"})},
    ],
    7: [
        {"cle": "delta", "wikipedia": "Volume (finance)", "titre": "Delta estimé depuis les bougies", "examen": "flux_delta",
         "resume": "Sans vrai carnet, le delta est ESTIMÉ : une bougie qui ferme en haut de son range compte comme "
                   "acheteuse. Toujours écrire « estimé ».",
         "quiz": ("B", "Un delta calculé depuis des bougies de 5 minutes est :",
                  {"A": "Un vrai footprint", "B": "Une estimation", "C": "Le carnet d'ordres réel", "D": "Interdit"})},
        {"cle": "poc", "wikipedia": "Volume (finance)", "titre": "Profil de volume : POC et zone de valeur", "examen": "flux_poc",
         "resume": "Le POC est le prix où il s'est échangé le plus de volume ; la zone de valeur contient 70 % du "
                   "volume autour du POC.",
         "quiz": ("C", "Le POC d'un profil de volume est :",
                  {"A": "Le plus haut de la séance", "B": "Le prix d'ouverture", "C": "Le prix avec le plus de volume",
                   "D": "La moyenne des clôtures"})},
    ],
    8: [
        {"cle": "taille", "wikipedia": "Gestion des risques", "titre": "Taille de position en MGC", "examen": "risque_taille",
         "resume": "MGC : 1 tick = 0,10 point = 1 $, 1 point = 10 $ par contrat. Contrats = budget de risque / "
                   "(risque du stop + frais + glissement), arrondi vers le bas. Budget = 0,25 % du capital.",
         "quiz": ("A", "Sur le Micro Gold (MGC), 1 point vaut :",
                  {"A": "10 $ par contrat", "B": "1 $", "C": "100 $", "D": "0,10 $"})},
        {"cle": "vetos", "wikipedia": "Gestion des risques", "titre": "Les vetos", "examen": "risque_vetos",
         "resume": "Veto si le stop est du mauvais côté, si un prix n'est pas sur la grille de 0,10, si la limite de "
                   "perte du jour est atteinte ou si le ratio au TP1 est sous le minimum. Un veto est toujours expliqué.",
         "quiz": ("C", "À l'achat, où doit être le stop ?",
                  {"A": "Au-dessus de l'entrée", "B": "Au TP1", "C": "Sous l'entrée", "D": "N'importe où"})},
    ],
    9: [
        {"cle": "recalcul", "wikipedia": "Reproductibilité", "titre": "Recalcul indépendant",
         "resume": "Le secrétaire-auditeur refait chaque chiffre sans réutiliser le code de l'agent vérifié, avec "
                   "une tolérance écrite. Hors tolérance : rejet et message à l'auteur et au directeur.",
         "quiz": ("B", "Pour vérifier une analyse, l'auditeur doit :",
                  {"A": "Relire le texte et faire confiance", "B": "Refaire le calcul avec son propre code",
                   "C": "Demander à l'IA", "D": "Arrondir les chiffres"})},
        {"cle": "examinateur", "wikipedia": "Audit", "titre": "Faire passer les examens",
         "resume": "L'auditeur fait passer chaque jour les examens des autres agents et tient le bulletin de notes.",
         "quiz": None},
    ],
    10: [
        {"cle": "ton", "wikipedia": "Politique monétaire", "titre": "Ton d'un discours : faucon, colombe, neutre", "examen": "discours_ton",
         "resume": "Faucon = inquiet de l'inflation, prêt à resserrer (plutôt négatif pour l'or) ; colombe = parle "
                   "de baisses de taux (plutôt positif pour l'or). Lexique fixé à l'avance, citations exactes.",
         "quiz": ("A", "Un discours « faucon » de la Fed parle surtout de :",
                  {"A": "Inflation trop haute, resserrement", "B": "Baisses de taux", "C": "Météo",
                   "D": "Prix du pétrole"})},
    ],
    11: [
        {"cle": "precedents", "wikipedia": "Réserve fédérale des États-Unis", "titre": "Retrouver des précédents datés",
         "resume": "Chaque précédent a sa date et sa source ; un précédent incertain est marqué « à vérifier ».",
         "quiz": ("C", "Un précédent dont on n'a pas la source est :",
                  {"A": "Gardé tel quel", "B": "Effacé sans le dire", "C": "Marqué « à vérifier »", "D": "Inventé"})},
    ],
    12: [
        {"cle": "fenetre", "wikipedia": "Étude d'événement", "titre": "Mesurer une réaction sans look-ahead", "examen": "reaction_mesure",
         "resume": "La référence est la dernière bougie FERMÉE avant l'annonce ; la fenêtre de mesure (5, 15, 60 min) "
                   "est fixée avant de regarder. Moins de 20 cas = échantillon insuffisant.",
         "quiz": ("B", "Pour mesurer la réaction à une annonce de 14h30, la référence est :",
                  {"A": "La bougie de 14h35", "B": "La dernière bougie fermée avant 14h30",
                   "C": "Le plus haut du jour", "D": "La clôture de la veille"})},
    ],
    13: [
        {"cle": "look_ahead", "wikipedia": "Backtesting", "titre": "Pas de look-ahead", "examen": "donnees_look_ahead",
         "resume": "À l'instant t, une bougie n'est visible que si elle est FERMÉE (début + durée <= t). Une bougie H1 "
                   "reconstruite n'apparaît qu'une fois l'heure terminée.",
         "quiz": ("D", "À 10h20, la bougie H1 de 10h est-elle visible ?",
                  {"A": "Oui, entière", "B": "Oui, sans son plus haut", "C": "Oui si le volume est fort",
                   "D": "Non, elle n'est pas fermée"})},
        {"cle": "qualite", "wikipedia": "Qualité des données", "titre": "Contrôle des données", "examen": "donnees_trous",
         "resume": "Source, période et nombre de bougies toujours affichés ; trous et doublons signalés ; la pause "
                   "quotidienne et le week-end ne sont pas des trous.",
         "quiz": ("A", "Une absence de bougies le samedi sur le gold est :",
                  {"A": "Normale (marché fermé)", "B": "Un trou grave", "C": "Un doublon", "D": "Une erreur Yahoo"})},
    ],
    14: [
        {"cle": "aiguillage", "wikipedia": "Management", "titre": "Confier chaque demande au bon agent", "examen": "directeur_aiguillage",
         "resume": "« Analyse du gold » = les 5 techniciens ; « Fibo » = agent 2 ; « discours de Powell » = agent 10 ; "
                   "« calendrier » = agent 5. La synthèse ne reprend que des documents existants.",
         "quiz": ("C", "« Fais-moi une analyse du gold » doit être confiée à :",
                  {"A": "Le Scribe seul", "B": "Le gestionnaire des risques seul", "C": "Les 5 techniciens",
                   "D": "Personne"})},
    ],
    15: [
        {"cle": "secrets", "wikipedia": "Sécurité de l'information", "titre": "Masquer les secrets", "examen": "scribe_secrets",
         "resume": "Avant d'écrire un bloc, le Scribe masque clés, tokens, mots de passe et lignes CLE=valeur.",
         "quiz": ("B", "Le Scribe trouve « API_KEY=abc123 » dans une session. Il écrit :",
                  {"A": "Le texte tel quel", "B": "Le texte avec la valeur masquée", "C": "Rien et il plante",
                   "D": "La clé en majuscules"})},
    ],
    16: [
        {"cle": "citer", "wikipedia": "Recherche d'information", "titre": "Ne citer que des blocs existants",
         "resume": "L'Archiviste cite des blocs avec leur numéro, date et dossier ; si rien n'est trouvé, il le dit.",
         "quiz": ("A", "Si l'Archiviste ne trouve rien, il :",
                  {"A": "Le dit franchement", "B": "Répond de mémoire", "C": "Invente un bloc", "D": "Se tait"})},
    ],
}
PROGRAMME[17] = [
    {"cle": "enseigner", "wikipedia": "Pédagogie", "titre": "Enseigner avec des sources",
     "resume": "Le mentor n'enseigne que ce qui vient d'une source (programme, bibliothèque, Wikipédia) et le cite ; "
               "si rien n'est trouvé, le cours est reporté.",
     "quiz": ("B", "Le mentor ne trouve aucune source sur un sujet. Il :",
              {"A": "Invente un cours", "B": "Reporte le cours et le dit", "C": "Copie un autre agent", "D": "Se tait"})},
]
# type de mission que chaque leçon d'examen doit accompagner (relue avant ces missions-là)
MISSION_AGENT = {1: "analyse_smc", 2: "analyse_fibo", 3: "analyse_ichimoku", 5: "calendrier_macro",
                 6: "analyse_vwap_ema", 7: "analyse_flux", 8: "evaluation_risque", 10: "discours_fed",
                 12: "reaction_annonces", 13: "controle_donnees", 14: "demande_directeur", 15: "ecriture_memoire"}


def programme(agent):
    """Les sujets du cours d'un agent : [{cle, titre, resume, wikipedia, examen, quiz}] (liste vide si l'agent n'a pas de cours)."""
    return [{"cle": s["cle"], "titre": s["titre"], "resume": s["resume"], "wikipedia": s.get("wikipedia"),
             "examen": bool(s.get("examen")),
             "quiz": bool(s.get("quiz"))} for s in PROGRAMME.get(int(agent), [])]


def graine_du_jour(instant=None):
    return int(dt.datetime.fromtimestamp(instant or time.time(), PARIS).strftime("%Y%m%d"))


# ------------------------------------------------------------------ bougies fabriquées (cas d'école)
def chemin(depart, jambes):
    """Clôtures en ligne droite : jambes = [(nombre de bougies, pas par bougie)]."""
    c, res = depart, [depart]
    for n, pas in jambes:
        for _ in range(n):
            c = round(c + pas, 4)
            res.append(c)
    return res


def bougies(clotures, depart=DEPART, periode=3600, meche=0.3, volume=10.0):
    """[(ts, o, h, l, c, v)] : l'ouverture est proche de la clôture précédente, une mèche fixe de chaque côté.
    Ainsi le plus haut d'un sommet est unique (le pivot est net) et connu à l'avance : clôture + mèche."""
    lignes, prec = [], clotures[0]
    for i, c in enumerate(clotures):
        o = c if i == 0 else prec + 0.3 * (c - prec)
        lignes.append((depart + i * periode, round(o, 4), round(max(o, c) + meche, 4), round(min(o, c) - meche, 4),
                       round(c, 4), float(volume)))
        prec = c
    return lignes


def cadre(lignes):
    config.salle_importable()
    import pandas as pd

    return pd.DataFrame([r[1:] for r in lignes], columns=["o", "h", "l", "c", "v"],
                        index=pd.DatetimeIndex([pd.Timestamp(r[0], unit="s", tz="UTC") for r in lignes]))


def _q(question, attendu, obtenu, reussi=None, tolerance=None):
    if reussi is None:
        if tolerance is not None and isinstance(attendu, (int, float)) and isinstance(obtenu, (int, float)):
            reussi = abs(float(attendu) - float(obtenu)) <= tolerance
        else:
            reussi = attendu == obtenu
    return {"question": question, "attendu": attendu, "obtenu": obtenu, "reussi": bool(reussi),
            "tolerance": tolerance}


def _base_ephemere():
    """Une petite base jetable (les examens ne salissent jamais la vraie base avec des bougies fabriquées)."""
    from .base import Base

    dossier = tempfile.mkdtemp(prefix="examen-")
    return Base(Path(dossier) / "examen.sqlite")


# ------------------------------------------------------------------ examens « cas d'école »
def _zigzag_haussier(alea):
    p = round(alea.uniform(1900, 4200), 1)
    s = alea.choice((0.8, 1.0, 1.2, 1.5))
    jambes = [(8, s), (4, -s), (8, s), (4, -s), (8, s), (4, s)]
    c = chemin(p, jambes)
    # repères connus par construction : sommet 2 (fin de la 3e jambe), creux 2 (fin de la 4e)
    sommet2, creux2 = 8 + 4 + 8, 8 + 4 + 8 + 4
    return p, s, c, sommet2, creux2


def ex_smc_bos(alea):
    import calculs

    meche = 0.3
    p, s, c, sommet2, _ = _zigzag_haussier(alea)
    df = cadre(bougies(c, meche=meche))
    r = calculs.resume_smc(df, "H1", float(calculs.atr(df).iloc[-1]))
    dernier = r["derniers_evenements"][-1] if r["derniers_evenements"] else {}
    niveau = round(c[sommet2] + meche, 1)
    return [_q("Tendance après des sommets et creux de plus en plus hauts", "haussier", r["tendance"]),
            _q("Type de la dernière cassure", "BOS haussier", f"{dernier.get('type')} {dernier.get('sens')}"),
            _q("Niveau cassé (le plus haut du dernier sommet confirmé)", niveau, dernier.get("niveau"), tolerance=0.1)]


def ex_smc_choch(alea):
    import calculs

    meche = 0.3
    p, s, c, _, creux2 = _zigzag_haussier(alea)
    c = c + chemin(c[-1], [(4, s / 2), (16, -s)])[1:]
    df = cadre(bougies(c, meche=meche))
    r = calculs.resume_smc(df, "H1", float(calculs.atr(df).iloc[-1]))
    dernier = r["derniers_evenements"][-1] if r["derniers_evenements"] else {}
    niveau = round(c[creux2] - meche, 1)
    return [_q("Tendance après une clôture sous le dernier creux confirmé", "baissier", r["tendance"]),
            _q("Type de la dernière cassure", "CHoCH baissier", f"{dernier.get('type')} {dernier.get('sens')}"),
            _q("Niveau cassé (le plus bas du dernier creux confirmé)", niveau, dernier.get("niveau"), tolerance=0.1)]


def _impulsion(alea, ratio):
    """Une impulsion haussière nette de A à B puis un retracement jusqu'au ratio voulu."""
    meche = 0.3
    p = round(alea.uniform(1900, 4200), 1)
    s = alea.choice((1.0, 1.5, 2.0))
    debut = chemin(p, [(6, s / 2), (6, -s / 2), (20, s)])
    i_a, i_b = 12, len(debut) - 1
    a, b = debut[i_a] - meche, debut[i_b] + meche
    cible = b - ratio * (b - a)
    n = 6
    retour = [round(debut[-1] + (cible - debut[-1]) * k / n, 4) for k in range(1, n + 1)]
    c = debut + retour
    return c, a, b, meche


def ex_fibo_niveaux(alea):
    import calculs

    c, a, b, meche = _impulsion(alea, 0.70)
    df = cadre(bougies(c, meche=meche))
    r = calculs.fibo({"H1": df}, float(calculs.atr(df).iloc[-1]))
    if not r.get("disponible"):
        return [_q("Impulsion trouvée", "oui", f"non ({r.get('raison')})")]
    n = r["niveaux"]
    return [_q("Sens de l'impulsion", "haussière", r["impulsion"]),
            _q("Départ de l'impulsion (niveau 1)", round(a, 1), r["depart"]["prix"], tolerance=0.1),
            _q("Fin de l'impulsion (niveau 0)", round(b, 1), r["fin"]["prix"], tolerance=0.1),
            _q("Prix du niveau 0.618", round(b - 0.618 * (b - a), 1), n.get("0.618"), tolerance=0.15),
            _q("Prix du niveau 0.786", round(b - 0.786 * (b - a), 1), n.get("0.786"), tolerance=0.15)]


def ex_fibo_zones(alea):
    import calculs

    res = []
    for ratio, attendu in ((0.70, "le prix est dans les zones d'entrée 0.618-0.893"),
                           (0.50, "le prix est autour du 50 % : zone interdite pour entrer")):
        c, a, b, meche = _impulsion(alea, ratio)
        df = cadre(bougies(c, meche=meche))
        r = calculs.fibo({"H1": df}, float(calculs.atr(df).iloc[-1]))
        res.append(_q(f"Lecture quand le prix a retracé {ratio:g} de l'impulsion", attendu, r.get("lecture")))
        if ratio == 0.70:
            zones = [z["niveau"] for z in r.get("zones_entree", [])]
            res.append(_q("Le 0.5 ne fait jamais partie des zones d'entrée", True, "0.5" not in zones and bool(zones)))
    return res


def ex_ichimoku_tendance(alea):
    import calculs

    res = []
    for sens, position, chikou in ((1, "au-dessus du nuage", "au-dessus"), (-1, "sous le nuage", "sous")):
        p = round(alea.uniform(1900, 4200), 1)
        c = chemin(p, [(150, sens * alea.choice((0.4, 0.6, 0.8)))])
        r = calculs.ichimoku(cadre(bougies(c)), "H1")
        mot = "haussière" if sens > 0 else "baissière"
        res.append(_q(f"Position du prix après une tendance {mot} régulière", position, r.get("position_prix")))
        res.append(_q(f"Chikou après une tendance {mot}", chikou, (r.get("chikou") or "?").split()[0]))
    return res


def ex_ichimoku_tenkan(alea):
    import calculs

    p = round(alea.uniform(1900, 4200), 1)
    c = chemin(p, [(60, 0.5), (30, -0.7), (20, 0.4)])
    lignes = bougies(c)
    r = calculs.ichimoku(cadre(lignes), "H1")
    hauts, bas = [x[2] for x in lignes], [x[3] for x in lignes]
    tenkan = (max(hauts[-9:]) + min(bas[-9:])) / 2
    kijun = (max(hauts[-26:]) + min(bas[-26:])) / 2
    return [_q("Tenkan = (plus haut 9 + plus bas 9) / 2", round(tenkan, 1), r.get("tenkan"), tolerance=0.1),
            _q("Kijun = (plus haut 26 + plus bas 26) / 2", round(kijun, 1), r.get("kijun"), tolerance=0.1)]


def ex_vwap_exact(alea):
    from .competences import analyse_vwap_ema

    p = round(alea.uniform(1900, 4200), 1)
    d = alea.choice((2.0, 5.0, 10.0))
    vols = [alea.randint(1, 9) for _ in range(3)]
    # bougies plates : prix typique = le prix lui-même
    lignes = [(DEPART + 300 * i, x, x, x, x, float(v)) for i, (x, v) in enumerate(zip((p, p + d, p + 2 * d), vols))]
    attendu = (p * vols[0] + (p + d) * vols[1] + (p + 2 * d) * vols[2]) / sum(vols)
    r = analyse_vwap_ema.calculer_vwap(lignes)
    sans_volume = analyse_vwap_ema.calculer_vwap([(t, o, h, l, c, 0.0) for t, o, h, l, c, _ in lignes])
    return [_q(f"VWAP de 3 bougies (volumes {vols})", round(attendu, 2), round(r[0], 2) if r else None, tolerance=0.01),
            _q("Pas de VWAP quand la séance n'a pas de volume", None, sans_volume)]


def ex_ema_retard(alea):
    from .competences import analyse_vwap_ema

    a = alea.choice((0.1, 0.2, 0.5))
    p = round(alea.uniform(1900, 4200), 1)
    c = chemin(p, [(2000, a)])
    lignes = bougies(c)
    maintenant, avant = analyse_vwap_ema.calculer_ema(lignes)
    plat_ = analyse_vwap_ema.calculer_ema(bougies([p] * 400))[0]
    retard = c[-1] - maintenant
    return [_q(f"Retard de l'EMA 200 sur une hausse de {a:g} point par bougie (99,5 x pas)", round(99.5 * a, 2),
               round(retard, 2), tolerance=0.02 * 99.5 * a),
            _q("Pente de l'EMA sur une hausse régulière", "montante", "montante" if maintenant > avant else "descendante"),
            _q("EMA 200 d'un prix immobile = ce prix", p, round(plat_, 2), tolerance=0.01)]


def _seance_m5(n, prix, haut_ferme=True, volume=50.0, special=None):
    """Bougies 5 min à partir de 19 h New York (dans la séance CME) : fermeture en haut ou en bas du range."""
    ny = dt.datetime(2026, 10, 26, 19, 0, tzinfo=ZoneInfo("America/New_York")).timestamp()
    lignes = []
    for i in range(n):
        o = prix + (i % 3) * 0.2
        h, l = o + 1.0, o - 1.0
        c = h if haut_ferme else l
        v = volume
        if special and i == special[0]:
            h, l, c, v = special[1] + 0.2, special[1] - 0.2, special[1], special[2]
            o = special[1]
        lignes.append((ny + 300 * i, o, h, l, c, v))
    return lignes


def ex_flux_delta(alea):
    import calculs

    p = round(alea.uniform(1900, 4200), 1)
    res = []
    for haut, attendu in ((True, "positif"), (False, "négatif")):
        r = calculs.order_flow({"M5": cadre(_seance_m5(40, p, haut))}, "MGC=F")
        quoi = "en haut" if haut else "en bas"
        res.append(_q(f"Delta cumulé quand toutes les bougies ferment {quoi} de leur range", attendu,
                      r.get("delta_cumule_session")))
    r = calculs.order_flow({"M5": cadre(_seance_m5(40, p, True))}, "MGC=F")
    res.append(_q("Le delta depuis des bougies est annoncé comme estimé", True, "stim" in (r.get("avertissement") or "")))
    return res


def ex_flux_poc(alea):
    import calculs

    p = round(alea.uniform(1900, 4200), 1)
    pic = round(p + alea.choice((-0.6, 0.0, 0.6)), 1)
    lignes = _seance_m5(40, p, True, volume=10.0, special=(20, pic, 5000.0))
    r = calculs.order_flow({"M5": cadre(lignes)}, "MGC=F")
    # le très gros volume est réparti sur toute sa bougie (± 0,2) : le POC doit tomber dans cette bougie
    largeur = (max(x[2] for x in lignes) - min(x[3] for x in lignes)) / 60
    return [_q("POC = prix du très gros volume", pic, r.get("poc"), tolerance=0.2 + 1.5 * largeur)]


def ex_risque_taille(alea):
    config.salle_importable()
    from mgc import config as cfg, risque

    reglages = dict(cfg.DEFAUTS, limite_perte_jour_usd=1000.0)
    entree = round(alea.uniform(1900, 4200), 1)
    ticks = alea.randint(10, 60)
    stop = round(entree - ticks * 0.1, 1)
    tp1 = round(entree + 3 * ticks * 0.1, 1)
    couts = reglages["frais_aller_retour_usd"] + 2 * reglages["glissement_ticks_par_cote"] * 1.0
    budget = min(reglages["capital_usd"] * reglages["risque_pct"] / 100, reglages["limite_perte_jour_usd"])
    attendu = min(math.floor(budget / (ticks * 1.0 + couts) + 1e-9), reglages["max_contrats"])
    r = risque.evaluer("achat", entree, stop, tp1, reglages)
    return [_q(f"Risque brut d'un stop de {ticks} ticks (1 tick = 1 $)", float(ticks), r.get("risque_brut_par_contrat"),
               tolerance=0.001),
            _q(f"Contrats pour un budget de {budget:g} $ (stop {ticks} ticks + {couts:g} $ de coûts)", attendu,
               r.get("contrats"))]


def ex_risque_vetos(alea):
    config.salle_importable()
    from mgc import config as cfg, risque

    reglages = dict(cfg.DEFAUTS, limite_perte_jour_usd=1000.0)
    e = round(alea.uniform(1900, 4200), 1)
    cas = [("Stop au-dessus de l'entrée à l'achat", "stop incoh", ("achat", e, round(e + 2, 1), round(e + 6, 1), 0)),
           ("Prix hors de la grille de 0,10", "invalide", ("achat", round(e + 0.05, 2), round(e - 2, 1), round(e + 6, 1), 0)),
           ("Limite de perte du jour déjà atteinte", "limite de perte", ("achat", e, round(e - 2, 1), round(e + 6, 1), 1000.0)),
           ("Ratio au TP1 trop faible", "ratio", ("achat", e, round(e - 4, 1), round(e + 1, 1), 0))]
    res = []
    for quoi, mot, (sens, entree, stop, tp1, perte) in cas:
        r = risque.evaluer(sens, entree, stop, tp1, reglages, perte)
        explique = any(mot in v.lower() for v in r["vetos"])
        res.append(_q(f"Veto expliqué : {quoi}", True, (not r["exploitable"]) and explique))
    return res


def ex_macro_heures(alea):
    from .competences import calendrier_macro

    utc = dt.UTC
    cas = [("vendredi 30/10/2026 (USA encore à l'heure d'été)", dt.datetime(2026, 10, 30, 12, 30, tzinfo=utc), "13h30"),
           ("vendredi 06/11/2026 (les deux à l'heure d'hiver)", dt.datetime(2026, 11, 6, 13, 30, tzinfo=utc), "14h30"),
           ("jeudi 02/07/2026 (les deux à l'heure d'été)", dt.datetime(2026, 7, 2, 12, 30, tzinfo=utc), "14h30")]
    return [_q(f"8h30 New York le {quoi}, en heure de Paris", attendu,
               calendrier_macro.heure(quand.timestamp()).split()[-1]) for quoi, quand, attendu in cas]


def ex_discours_ton(alea):
    from .competences import discours_fed as d

    faucon = " ".join(f"We think {e} today." for e in alea.sample(list(d.FAUCON), 3))
    colombe = " ".join(f"We discussed {e} today." for e in alea.sample(list(d.COLOMBE), 3))
    neutre = "The committee met and reviewed the data. Labor markets were discussed."
    res = []
    for texte, attendu in ((faucon, "faucon"), (colombe, "colombe"), (neutre, "neutre ou partagé")):
        n = d.compter(texte)
        res.append(_q(f"Ton d'un texte {attendu.split()[0]}", attendu,
                      d.penchant(sum(n["faucon"].values()), sum(n["colombe"].values()))))
    n = d.compter(faucon)
    res.append(_q("Chaque passage utilisé est cité mot pour mot", True,
                  bool(n["citations"]) and all(c in faucon for c in n["citations"])))
    return res


def ex_reaction_mesure(alea):
    from .competences import reaction_annonces as ra

    p = round(alea.uniform(1900, 4200), 1)
    saut = alea.choice((-6.0, -3.0, 4.0, 8.0))
    quand = DEPART + 3600 * 3          # annonce à l'heure ronde
    lignes = []
    for i in range(-30, 90):
        t = quand + 60 * i
        c = p if t < quand else p + saut
        lignes.append((t, c, c + 0.2, c - 0.2, c, 10.0))
    m = ra.mesurer(lignes, 60, quand) or {}
    reference = [x for x in lignes if x[0] + 60 <= quand][-1]
    return [_q("Référence = dernière bougie fermée AVANT l'annonce", reference[0], m.get("reference_ts")),
            _q("Mouvement mesuré 15 minutes après", saut, m.get("mouvement_15"), tolerance=0.01),
            _q("Mouvement mesuré 60 minutes après", saut, m.get("mouvement_60"), tolerance=0.01)]


def ex_donnees_look_ahead(alea):
    from . import donnees

    base = _base_ephemere()
    try:
        jeu = donnees.creer_jeu(base, "examen", "fabriqué (examen)", "MGC")
        m5 = [(DEPART + 300 * i, 2000.0, 2001.0, 1999.0, 2000.5, 5.0) for i in range(48)]   # 4 heures
        donnees.ajouter_bougies(base, jeu, "M5", m5)
        minute = alea.choice((5, 20, 35, 50))
        instant = DEPART + 2 * 3600 + 60 * minute
        h1 = donnees.fenetre(base, jeu, "H1", instant)["bougies"]
        m5_vues = donnees.fenetre(base, jeu, "M5", instant)["bougies"]
        res = [_q(f"À {minute} min après l'heure, la dernière H1 visible est celle qui a commencé 1 h plus tôt",
                  DEPART + 3600, h1[-1][0] if h1 else None),
               _q("Aucune bougie 5 min visible n'est encore ouverte", True,
                  all(b[0] + 300 <= instant for b in m5_vues))]
    finally:
        base.fermer()
    return res


def ex_donnees_trous(alea):
    from . import donnees

    base = _base_ephemere()
    try:
        jeu = donnees.creer_jeu(base, "examen", "fabriqué (examen)", "MGC")
        mardi = dt.datetime(2026, 10, 27, 14, 0, tzinfo=dt.UTC).timestamp()
        trou = alea.randint(10, 30)
        lignes = [(mardi + 300 * i, 2000.0, 2001.0, 1999.0, 2000.5, 5.0) for i in range(60) if not trou <= i < trou + 4]
        donnees.ajouter_bougies(base, jeu, "M5", lignes)
        r = donnees.controle(base, jeu)["unites"]["M5"]
        res = [_q("Un trou de 20 minutes un mardi est signalé", True, r["petits_trous"] + r["longues_coupures"] >= 1),
               _q("Nombre de bougies affiché", len(lignes), r["n"])]
    finally:
        base.fermer()
    return res


def ex_directeur_aiguillage(alea):
    import re

    from . import directeur_chat as dc

    cas = [("fais moi une analyse du gold", "analyses"), ("lance une anlayse du marché", "analyses"),
           ("trace moi le fibo", "analyse_fibo"), ("analyse le discours de Powell", "discours_fed"),
           ("prépare le calendrier des annonces", "calendrier_macro"), ("vérifie la qualité des données", "controle_donnees"),
           ("lance le replay de la stratégie", "replay_strategie_v1"), ("calcule le risque de cette idée", "evaluation_risque")]
    res = []
    for phrase, attendu in alea.sample(cas, 6):
        t = dc.plat(phrase)
        sujet = next((typ for motif, typ in dc.SUJETS if re.search(rf"(?<![a-z])(?:{motif})", t)), None)
        compris = sujet if sujet and re.search(dc.VERBE, t) else None
        res.append(_q(f"« {phrase} » est confié à", attendu, compris))
    return res


def ex_scribe_secrets(alea):
    from . import memoire

    valeur = "".join(alea.choice("abcdefghijk0123456789") for _ in range(24))
    cas = [f"API_KEY={valeur}", f"mon token: {valeur}", f"GROQ_API_KEY = gsk_{valeur}", f"password={valeur}"]
    return [_q(f"Le secret de « {c.split(valeur)[0].strip()}… » est masqué", True, valeur not in memoire.masquer(c))
            for c in cas]


EXAMENS = {
    "smc_bos": ex_smc_bos, "smc_choch": ex_smc_choch, "fibo_niveaux": ex_fibo_niveaux, "fibo_zones": ex_fibo_zones,
    "ichimoku_tendance": ex_ichimoku_tendance, "ichimoku_tenkan": ex_ichimoku_tenkan, "vwap_exact": ex_vwap_exact,
    "ema_retard": ex_ema_retard, "flux_delta": ex_flux_delta, "flux_poc": ex_flux_poc,
    "risque_taille": ex_risque_taille, "risque_vetos": ex_risque_vetos, "macro_heures": ex_macro_heures,
    "discours_ton": ex_discours_ton, "reaction_mesure": ex_reaction_mesure,
    "donnees_look_ahead": ex_donnees_look_ahead, "donnees_trous": ex_donnees_trous,
    "directeur_aiguillage": ex_directeur_aiguillage, "scribe_secrets": ex_scribe_secrets,
}


def passer_examens(agent, graine):
    """Tous les cas d'école d'un agent. Renvoie [{sujet, titre, questions, note}] ; une erreur de calcul = question ratée."""
    config.salle_importable()
    resultats = []
    for s in PROGRAMME.get(int(agent), []):
        nom = s.get("examen")
        if not nom:
            continue
        alea = random.Random(f"{graine}-{agent}-{nom}")
        try:
            questions = EXAMENS[nom](alea)
        except Exception as e:  # noqa: BLE001 : un calcul qui plante est une réponse fausse, notée comme telle
            questions = [_q("Le calcul répond sans planter", "une réponse", f"erreur : {type(e).__name__} : {e}", False)]
        bonnes = sum(q["reussi"] for q in questions)
        resultats.append({"sujet": s["cle"], "titre": s["titre"], "resume": s["resume"], "examen": nom,
                          "questions": questions, "note": round(20 * bonnes / len(questions), 1) if questions else 0.0})
    return resultats


# ------------------------------------------------------------------ travaux pratiques en replay (vraies bougies)
HORIZON_H = 4               # on regarde la clôture H1 4 heures plus tard
SEUIL_ATR = 0.25            # un mouvement plus petit que 0,25 ATR H1 est « plat » : ni juste ni faux
LECTURES = {1: "SMC : tendance H1", 2: "Fibonacci : rebond depuis les zones d'entrée", 3: "Ichimoku : prix et nuage H1",
            6: "EMA 200 H1 : côté du prix", 7: "Flux estimé : delta de séance"}


def lecture(agent, cadres):
    """Ce que l'agent « dit » à cet instant : +1 (plutôt haussier), -1 (plutôt baissier) ou 0 (pas d'avis).
    Ce sont exactement les fonctions de la Salle utilisées par ses analyses."""
    import calculs

    h1 = cadres.get("H1")
    if agent == 1:
        t = calculs.structure(h1)["tendance"]
        return 1 if t == "haussier" else -1 if t == "baissier" else 0
    if agent == 2:
        r = calculs.fibo({"H1": h1}, float(calculs.atr(h1).iloc[-1]))
        if not r.get("disponible") or "zones d'entrée" not in r.get("lecture", ""):
            return 0
        return 1 if r["impulsion"] == "haussière" else -1
    if agent == 3:
        p = calculs.ichimoku(h1, "H1").get("position_prix")
        return 1 if p == "au-dessus du nuage" else -1 if p == "sous le nuage" else 0
    if agent == 6:
        if len(h1) < 210:
            return 0
        e = calculs.ema(h1["c"], 200).iloc[-1]
        return 1 if h1["c"].iloc[-1] > e else -1
    if agent == 7:
        m5 = cadres.get("M5")
        if m5 is None or len(m5) < 10:
            return 0
        r = calculs.order_flow({"M5": m5}, "MGC=F")
        if not r.get("disponible"):
            return 0
        return 1 if r["delta_cumule_session"] == "positif" else -1
    raise ValueError(f"l'agent {agent} n'a pas de lecture à tester en replay")


def _session(ts):
    h = dt.datetime.fromtimestamp(ts, PARIS).hour
    return "Asie" if h < 8 else "Londres" if h < 14 else "New York" if h < 22 else "Asie"


def travaux_pratiques(base, jeu, agent, n_max=80, graine=0, verifier=lambda: None):
    """Replay sans look-ahead : à chaque instant tiré, lecture de l'agent avec les bougies fermées, puis résultat
    HORIZON_H heures plus tard. Renvoie les cas et le bilan (taux, Wilson, comparaison au hasard)."""
    from . import donnees
    from .competences import _commun

    config.salle_importable()
    import calculs
    from mgc import stats

    h1_tout = donnees.fenetre(base, jeu, "H1", time.time() + 86400)["bougies"]
    if len(h1_tout) < 300:
        return {"cas": [], "bilan": {"n": 0, "verdict": f"pas assez de bougies H1 ({len(h1_tout)}, il en faut 300)"}}
    # instants possibles : fin d'une bougie H1, avec 250 bougies avant et HORIZON_H après, espacés d'au moins 4 h
    candidats = [b[0] + 3600 for b in h1_tout[250:-HORIZON_H]]
    if agent == 7:   # le flux lit des bougies 5 min : seulement les instants où il y en a (31/10 : 0 cas sur le PC)
        m5 = donnees.fenetre(base, jeu, "M5", time.time() + 86400)["bougies"]
        debut_m5 = m5[0][0] + 600 * 300 if len(m5) > 600 else None
        candidats = [t for t in candidats if debut_m5 and t >= debut_m5] or (
            [t for t in candidats if m5 and t >= m5[0][0] + 3 * 3600])
    alea = random.Random(f"tp-{graine}-{agent}-{jeu}")
    alea.shuffle(candidats)
    choisis, cas = [], []
    for t in candidats:
        if len(choisis) >= n_max:
            break
        if any(abs(t - x) < HORIZON_H * 3600 for x in choisis):
            continue
        choisis.append(t)
    for t in sorted(choisis):
        verifier()
        cadres = {"H1": _commun.cadre(donnees.fenetre(base, jeu, "H1", t, 300)["bougies"])}
        if agent == 7:
            m5 = donnees.fenetre(base, jeu, "M5", t, 600)["bougies"]
            if m5:
                cadres["M5"] = _commun.cadre(m5)
        try:
            avis = lecture(agent, cadres)
        except (ValueError, KeyError, IndexError):
            avis = 0
        apres = donnees.fenetre(base, jeu, "H1", t + HORIZON_H * 3600, 1)["bougies"]
        if not apres or apres[-1][0] < t:
            continue
        depart = cadres["H1"]["c"].iloc[-1]
        a = float(calculs.atr(cadres["H1"]).iloc[-1])
        mouvement = apres[-1][4] - depart
        resultat = 0 if abs(mouvement) < SEUIL_ATR * a else (1 if mouvement > 0 else -1)
        cas.append({"instant": t, "avis": avis, "mouvement": round(mouvement, 2), "resultat": resultat,
                    "session": _session(t)})
    return {"cas": cas, "bilan": bilan_tp(cas, stats.wilson)}


def bilan_tp(cas, wilson):
    """Taux de bonnes lectures, comparé à « toujours parier sur le sens le plus fréquent » (le hasard intelligent)."""
    comptes = [c for c in cas if c["avis"] and c["resultat"]]
    n = len(comptes)
    justes = sum(c["avis"] == c["resultat"] for c in comptes)
    hausses = sum(c["resultat"] == 1 for c in comptes)
    naif = max(hausses, n - hausses) / n if n else 0.0
    bas, haut = wilson(justes, n)
    taux = justes / n if n else 0.0
    if n < MIN_CAS:
        verdict = f"échantillon insuffisant ({n} cas, il en faut {MIN_CAS})"
    elif bas > 0.5 and taux > naif:
        verdict = "la lecture a aidé (mieux que le hasard, même dans le pire cas de l'intervalle)"
    elif haut < 0.5:
        verdict = "la lecture s'est trompée plus souvent qu'une pièce : à revoir"
    else:
        verdict = "pas de différence prouvée avec le hasard"
    par_session = {}
    for s in ("Asie", "Londres", "New York"):
        sc = [c for c in comptes if c["session"] == s]
        if sc:
            par_session[s] = {"n": len(sc), "taux": round(sum(c["avis"] == c["resultat"] for c in sc) / len(sc), 3)}
    return {"n": n, "justes": justes, "taux": round(taux, 3), "wilson": [bas, haut], "naif": round(naif, 3),
            "sans_avis": sum(1 for c in cas if not c["avis"]), "plats": sum(1 for c in cas if c["avis"] and not c["resultat"]),
            "par_session": par_session, "verdict": verdict}


def note_tp(bilan):
    """Note sur 20 : 10 = hasard ; on gagne (ou perd) des points selon la borne basse de Wilson. None si trop peu de cas."""
    if bilan.get("n", 0) < MIN_CAS:
        return None
    return round(max(0.0, min(20.0, 10 + 40 * (bilan["wilson"][0] - 0.5) + 20 * (bilan["taux"] - bilan["naif"]))), 1)


# ------------------------------------------------------------------ quiz de l'IA locale
DELAI_QUIZ_S = 170        # une question au plus 170 s ; le quiz s'arrête avant le délai de 300 s de la mission


def questions_quiz(agent):
    return [(s["cle"], s["titre"], s["quiz"]) for s in PROGRAMME.get(int(agent), []) if s.get("quiz")]


LETTRE = re.compile(r"(?<![A-Za-zÀ-ÿ])([ABCD])(?![A-Za-zÀ-ÿ])")


def lire_lettre(reponse):
    """La lettre choisie : une lettre seule (« D », « Réponse : D », « D) ... »), jamais le A de « La »."""
    reponse = re.sub(r"<think>.*?</think>", "", reponse or "", flags=re.S)
    m = LETTRE.search(reponse.strip())
    return m.group(1) if m else "?"


def poser_quiz(ia, agent, mission=None, temps_restant=None):
    """Chaque question à choix est posée à l'IA. None si l'IA n'est pas disponible (rien n'est inventé).
    temps_restant() -> secondes avant la fin du délai de la mission : on s'arrête avant (31/10 : 7 quiz coupés à 300 s
    sur le PC), les questions déjà répondues sont gardées, les autres attendent le quiz suivant."""
    if not ia or not ia.disponible():
        return None
    consigne = ("Tu passes un examen de trading sur le Micro Gold. Réponds UNIQUEMENT par la lettre de la bonne "
                "réponse (A, B, C ou D), sans rien d'autre, sans réfléchir à voix haute.")
    # Qwen 3.5 réfléchit longtemps avant de répondre (31/10 sur le PC : 150 s par question, la plupart coupées à 90 s) :
    # « /no_think » dans la QUESTION (pas la consigne) coupe cette réflexion ; on laisse aussi plus de temps au quiz
    delai_ia = DELAI_QUIZ_S
    res = []
    for cle, titre, (bonne, question, choix) in questions_quiz(agent):
        if temps_restant and temps_restant() < delai_ia + 15:
            break
        texte = question + "\n" + "\n".join(f"{k}) {v}" for k, v in choix.items())
        try:
            reponse = ia.completer(consigne, texte + "\n/no_think", mission, agent, "professeur", max_tokens=600,
                                   delai=DELAI_QUIZ_S)
        except TypeError:   # IA sans ces réglages (anciennes versions, tests)
            reponse = ia.completer(consigne, texte + "\n/no_think", mission, agent, "professeur")
        if reponse is None:
            return res or None
        lettre = lire_lettre(reponse)
        res.append({"sujet": cle, "titre": titre, "question": question, "attendu": bonne, "obtenu": lettre,
                    "reussi": lettre == bonne, "bonne_reponse": choix[bonne]})
    return res


# ------------------------------------------------------------------ enregistrement : examens, bulletin, leçons
def enregistrer(base, agent, genre, sujet, note, detail, graine, mission=None, reussi=None):
    reussi = (note is not None and note >= NOTE_REUSSITE) if reussi is None else reussi
    return base.ecrire("INSERT INTO examens(ts, agent, genre, sujet, note, reussi, detail, graine, mission)"
                       " VALUES (?,?,?,?,?,?,?,?,?)",
                       (time.time(), int(agent), genre, sujet, note, int(bool(reussi)),
                        json.dumps(detail, ensure_ascii=False, default=str), graine, mission))


def _table_lecons(base):
    return bool(base.un("SELECT name FROM sqlite_master WHERE type='table' AND name='lecons'"))


def noter_lecon(base, agent, type_, quoi, cause, lecon, exemple=""):
    """Une leçon dans la table du Mentor (une seule mémoire des erreurs). Même erreur qui revient = « répétée ».
    Sans table lecons (Mentor pas encore installé), la leçon reste dans le détail de l'examen."""
    if not _table_lecons(base):
        return None
    empreinte = hashlib.sha1(f"{agent}|{type_}|{quoi}".encode()).hexdigest()[:16]
    t = time.time()
    return base.ecrire(
        "INSERT INTO lecons(equipe, agent, type, empreinte, quoi, cause, lecon, exemple, statut, cree, maj)"
        " VALUES ('universite',?,?,?,?,?,?,?,'a_appliquer',?,?)"
        " ON CONFLICT(equipe, empreinte) DO UPDATE SET fois=fois+1, maj=excluded.maj, exemple=excluded.exemple,"
        " statut=CASE WHEN statut='appliquee' THEN 'repetee' ELSE statut END",
        (int(agent), type_, empreinte, quoi[:500], cause[:500], lecon[:800], exemple[:500], t, t))


def bulletin(base, agent, depuis=None):
    """Le bulletin d'un agent : dernière note par épreuve, moyenne, examens ratés, leçons ouvertes."""
    depuis = depuis or 0
    lignes = base.lire("SELECT * FROM examens WHERE agent=? AND ts>=? ORDER BY ts DESC", (int(agent), float(depuis)))
    dernieres = {}
    for r in lignes:
        dernieres.setdefault((r["genre"], r["sujet"]), r)
    notes = [{"genre": g, "sujet": s, "note": r["note"], "reussi": bool(r["reussi"]), "le": r["ts"]}
             for (g, s), r in dernieres.items()]
    # la moyenne = ce que l'agent SAIT (examens, quiz) ; le replay dit si sa lecture prédit le gold, c'est à part
    chiffrees = [n["note"] for n in notes if n["note"] is not None and n["genre"] != "replay"]
    replay = next((n for n in notes if n["genre"] == "replay"), None)
    lecons = []
    if _table_lecons(base):
        lecons = base.lire("SELECT quoi, lecon, statut, fois, maj FROM lecons WHERE equipe='universite' AND agent=?"
                           " AND type LIKE ? AND statut!='appliquee' ORDER BY maj DESC LIMIT 10",
                           (int(agent), "%"))
    return {"agent": int(agent), "notes": notes, "moyenne": round(sum(chiffrees) / len(chiffrees), 1) if chiffrees else None,
            "valeur_lecture": replay["note"] if replay else None,
            "examens": len(lignes), "rates": [n for n in notes if not n["reussi"]], "lecons": lecons,
            "programme": programme(agent)}


def bulletins(base, depuis=None):
    from .agents import AGENTS

    return [bulletin(base, a["n"], depuis) for a in AGENTS]
