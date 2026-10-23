# Brancher la Salle des marchés sur Jarvis (appli + voix + Telegram)

## Ce que veut Jabran
Depuis l'appli Jarvis du téléphone (un bouton, ou une phrase écrite / dite), lancer le **desk des
spécialistes** de la Salle des marchés sur le PC, puis recevoir le **plan du chef de desk sur Telegram**
dès qu'il est prêt (3 à 10 minutes), sans être devant le PC.

## Déjà prêt et testé (côté Salle, rien à toucher)
- La Salle : `C:\Users\admin\Documents\TradingAgents\salle_des_marches\serveur.py`
  (venv `C:\Users\admin\Documents\TradingAgents\.venv`). Elle écoute seulement sur 127.0.0.1,
  port 8790 (ou le suivant libre jusqu'à 8799). Elle s'arrête d'elle-même au bout de 30 minutes.
- Son API :
  - `GET /api/salle` → `{"salle": true}` (pour la reconnaître)
  - `POST /api/lancer` avec `{"mode": "bureau", "ticker": "XAUUSD", "moteur": "auto"}` → `{"id": "..."}`,
    ou erreur 400 `{"erreur": "phrase à dire telle quelle"}` (ex. une analyse tourne déjà)
  - `GET /api/resume/<id>` → `{"fini": true/false, "texte": "résumé prêt pour Telegram"}`
- **Le module pour Jarvis est écrit et testé** : `pour-jarvis\salle.py` (dans ce dossier).
  - `SalleDesMarches(notify)` : `notify` = la fonction `notify(texte, kind)` de jarvis.py.
  - `lancer_desk(texte)` : trouve le ticker dans la phrase (gold par défaut, bitcoin, nasdaq, NVDA,
    « sur TSLA »…), démarre la Salle sans fenêtre si elle est fermée (jusqu'à 40 s), lance le desk,
    répond tout de suite par une phrase courte, puis surveille la fin dans un fil à part et envoie
    le résumé avec `notify(texte, "brief")`.
  - `etat_phrase()` : « Le desk sur le gold tourne depuis 3 minutes. » ou le dernier résumé.
  - Aucun appel réseau sous verrou. Logs sur le logger « jarvis ».

## À faire dans Jarvis (routine `/maj-jarvis`, avec les commits « avant » / « fait »)
1. Copier `pour-jarvis\salle.py` dans le dossier Jarvis.
2. `jarvis.py` :
   - importer `salle` avec les autres modules maison ;
   - créer `SALLE = salle.SalleDesMarches(notify)` au démarrage, après la création de `NOTIF` ;
   - ajouter deux actions dans le dictionnaire passé à `voix.VoiceCommands` (`remote_command` le
     recopie, donc l'appli et la case « Écrire à Jarvis » les auront aussi) :
     `"salle_desk"` → `SALLE.lancer_desk(phrase)` et `"salle_etat"` → `SALLE.etat_phrase()`.
     `lancer_desk` peut prendre jusqu'à 40 s si la Salle doit démarrer : pour la voix, passer par
     la même méthode que les autres actions longues (say_async).
3. `voix.py` : nouvelles commandes, avec `has()` / `word()` (jamais `"mot" in phrase`) :
   - « lance le desk », « réunis le desk », « desk sur le gold / le bitcoin / NVDA… »,
     « salle des marchés » → `salle_desk` avec la phrase entière ;
   - « où en est le desk », « résultat du desk » → `salle_etat`.
   - Rejouer les phrases pièges pour que « desk » ne se déclenche pas à tort.
4. `ui/app.html` : un bouton **« Desk gold »** (même style que les boutons rapides existants) qui
   envoie « lance le desk sur le gold » par `/api/cmd`. Vérifier le rendu au format S24 (360 × 780).
5. Proposer à Jabran (oui / non) : lancer le desk tout seul les jours de semaine à 14h50, pour avoir
   le plan sur Telegram avant le brief de 15h.
6. Redémarrer Jarvis (`.cache\redemarrage.demande`), contrôler les logs, commit « fait : … », push.

## Test final
Dans l'appli : bouton « Desk gold » → « C'est parti, le desk analyse le gold… » → 3 à 10 minutes
plus tard, un message 📋 sur Telegram : décision (LONG / SHORT / PAS DE TRADE), vote du desk,
zone, stop, TP1/TP2/TP3, confirmation à attendre.

Si la Salle tournait déjà avant le 14/10 à 14h, cliquer « Éteindre la salle » en bas de sa page :
Jarvis la redémarrera tout seul avec la bonne version.
