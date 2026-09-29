# Projet 02_Topo — maquette 3D de site (Rhino 8 / Grasshopper)

Outil destiné à des architectes : à partir d'une coordonnée (lat/lon) et d'un rayon, générer dans Rhino
le terrain, les bâtiments et la végétation, à partir des données ouvertes IGN. Livrable final : un
composant Grasshopper Python 3 (Rhino 8) partageable avec les collègues.

## Choix validés par l'utilisateur

| Élément | Méthode retenue |
|---|---|
| Repère | (0,0,0) = coordonnée exacte ; Z = 0 = MNT en ce point ; EarthAnchorPoint Rhino renseigné ; nord géographique = +Y tourné de la convergence Lambert-93 (≈ 2,64° à Briançon) |
| Terrain | MNT LiDAR HD 50 cm (WMS-R, BIL 32 bits), maillage triangulé au pas de 1 m, chaque maille coupée selon la diagonale la plus fidèle au MNT (`terrain_mesh_tri`), rayon = 2 × rayon d'analyse |
| Texture | Orthophoto IGN `ORTHOIMAGERY.ORTHOPHOTOS` 20 cm (WMS-R JPEG), UV planes, image copiée à côté du .3dm |
| Bâtiments | Extrusion des emprises BD TOPO (WFS `BDTOPO_V3:batiment`) à la hauteur BD TOPO, base = min du MNT sur l'emprise. **Toitures LiDAR non retenues** (M3 pans RANSAC, roofer, emprises LiDAR, M6 murs BD TOPO + toit LiDAR jugés non satisfaisants) — réflexion en cours |
| Végétation | CHM 50 cm (classes LiDAR 4-5), sommets à fenêtre variable (Popescu & Wynne), segmentation Dalponte 2016 ; arbres isolés = instances de 3 blocs normalisés (feuillu, conifere, fastigie ; hauteur 1, diamètre 1) ; bosquets = masses « lentille » lissées ; arbustes/haies 0,5–3 m = massifs bas. L'utilisateur n'aime pas les arbres « sucettes » (tronc + ellipsoïde) |

Rejeté : QuadRemesh pour le terrain (lisse les ruptures), 3dfier (LoD1 seulement), Point2Building
(apprentissage profond, non transposable), roofer 1.1 beta (un peu moins précis que 1.0).

## Données et pièges connus

- Géoplateforme IGN : WFS `https://data.geopf.fr/wfs/ows`, WMS-R `https://data.geopf.fr/wms-r`.
- Index des dalles LiDAR : couche WFS `IGNF_LIDAR-HD_METADONNEE:metadata`, attribut `url_npl` (COPC).
  L'ancienne couche `IGNF_NUAGES-DE-POINTS-LIDAR-HD:dalle` n'existe plus.
- Lecture COPC partielle avec laspy : `http_num_threads=6` et nouvelles tentatives sur HTTP 429.
  **Ne pas utiliser `decompression_selection`** : corrompt les Z.
- Python : `.venv` créé depuis le CPython 3.9 de Rhino 8 (`%USERPROFILE%\.rhinocode\py39-rh8`).
  `lazrs` récent n'a pas de wheel cp39 → installer avec `--only-binary=:all:`.
- Headless : `rhinoinside.load(r"C:\Program Files\Rhino 8\System", "net8.0")` ; terminer par
  `os._exit(0)` (plantage au finaliseur sinon). pythonnet 3 : convertir les listes en `List[T]`.
- Un GDAL système (`C:\Program Files\GDAL`) pollue PROJ : roofer doit recevoir ses propres
  PROJ_DATA/GDAL_DATA (voir `roofer_io.run`).
- Ne pas lancer d'instance Rhino graphique sans prévenir l'utilisateur (tentative de capture bloquée).

## Code

- `src/` : `geo.py`, `ign.py` (accès données + cache `data/cache`), `roofs.py`, `roofprints.py`,
  `roofer_io.py`, `vegetation.py`, `rhino_build.py`.
- `dev/zone.py` : zone test Briançon (44.892599016233035, 6.6360779217772725, R = 100 m).
- `dev/run_test.py` : génère le .3dm de test (toutes méthodes + mesures).
  `.venv/Scripts/python.exe -u dev/run_test.py out/<nom>.3dm`
- `tools/roofer`, `tools/roofer11` : exécutables roofer 1.0 / 1.1 beta (GPLv3).
- Dernier fichier validé : `out/test_briancon_v15_vegetation.3dm`.

## Prochaine étape (proposée, en attente de validation)

Refonte en une bibliothèque unique `site3d.py` (sections : paramètres `SiteParams`, géodésie,
données IGN, outils 2D, terrain, bâtiments, végétation, sortie Rhino, orchestrateur `SiteModel`)
+ script principal court (composant Grasshopper). Les méthodes de toiture expérimentales vont dans
`archives/`. Vérifier que la refonte reproduit exactement v15 sur Briançon, puis construire le
composant (dépendances via `# r: numpy, scipy, laspy, lazrs, requests`).
Questions ouvertes : fichier unique vs petit paquet ; emplacement (dossier partagé vs à côté du .gh).
