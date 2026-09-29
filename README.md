# 3D_bati_topo — maquette 3D de site pour Rhino 8

À partir d'une coordonnée (lat/lon) et d'un rayon, génère dans Rhino 8 le terrain (MNT LiDAR HD),
les bâtiments (BD TOPO) et la végétation (LiDAR HD), à partir des données ouvertes IGN.
Livrable visé : un composant Grasshopper Python 3. Détails des choix techniques : [CLAUDE.md](CLAUDE.md).

## Installer le projet sur un nouveau poste (Windows)

Prérequis : **Rhino 8** installé dans `C:\Program Files\Rhino 8`, **Git pour Windows**
et une connexion Internet (données IGN téléchargées à la volée).

1. **Initialiser le Python de Rhino** : ouvrir Rhino 8 une fois, lancer la commande `ScriptEditor`,
   créer un script Python 3 et l'exécuter. Rhino installe alors son CPython 3.9 dans
   `%USERPROFILE%\.rhinocode\py39-rh8`.

2. **Cloner le dépôt** :
   ```powershell
   git clone https://github.com/andydogbo/3D_bati_topo.git
   cd 3D_bati_topo
   ```

3. **Créer l'environnement Python** (à partir du Python de Rhino, obligatoirement) :
   ```powershell
   & "$env:USERPROFILE\.rhinocode\py39-rh8\python.exe" -m venv .venv
   .venv\Scripts\python.exe -m pip install --only-binary=lazrs -r requirements.txt
   ```

4. **Décompresser roofer** (utilisé par `dev/run_test.py` pour les méthodes de toiture comparées) :
   ```powershell
   Expand-Archive tools\roofer.zip tools\roofer
   Expand-Archive tools\roofer11.zip tools\roofer11
   ```
   roofer 1.0.0 et 1.1.0-beta.1 (3DBAG, GPLv3) — sources : https://github.com/3DBAG/roofer

5. **Tester** : régénère le modèle de Briançon, à comparer à `out/test_briancon_v15_vegetation.3dm`
   (le premier lancement télécharge les données IGN dans `data/cache`, quelques minutes) :
   ```powershell
   .venv\Scripts\python.exe -u dev/run_test.py out/test_nouveau_poste.3dm
   ```

## Contenu

| Dossier | Rôle |
|---|---|
| `src/` | bibliothèque : géodésie, accès IGN, terrain, toitures, végétation, construction Rhino |
| `dev/` | scripts d'essai et de diagnostic ; `run_test.py` = génération du modèle test |
| `out/` | dernier modèle validé (`.3dm` + orthophoto de texture), seul fichier Rhino versionné |
| `tools/` | archives des exécutables roofer |

Non versionnés (recréés automatiquement ou à l'installation) : `.venv/`, `data/` (cache IGN),
anciennes versions des `.3dm`, images de diagnostic.

## Reprendre le travail avec Claude Code

Ouvrir Claude Code dans le dossier cloné : il lit automatiquement [CLAUDE.md](CLAUDE.md), qui
contient l'état du projet, les choix validés, les pièges connus et la prochaine étape.
