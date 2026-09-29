"""Pont vers roofer (3DBAG, https://github.com/3DBAG/roofer) : écriture des entrées, lecture du CityJSONSeq.

roofer reconstruit des bâtiments LoD 2.2 à partir d'un nuage LAS/LAZ classé et d'emprises.
"""
import json
import os
import subprocess

import numpy as np


def write_inputs(folder, pts, blds, origin, h_terrain, h_roof):
    """Écrit points.laz (Lambert-93) et footprints.geojson (EPSG:2154).

    pts : (N, 4) [x, y, z, classe] en coordonnées locales ; blds : liste de Footprint ;
    h_terrain / h_roof : altitudes de repli par bâtiment.
    """
    import laspy

    os.makedirs(folder, exist_ok=True)
    ox, oy = origin
    hdr = laspy.LasHeader(point_format=6, version="1.4")
    hdr.scales = np.array([0.01, 0.01, 0.01])
    hdr.offsets = np.array([ox, oy, 0.0])
    las = laspy.LasData(hdr)
    las.x = pts[:, 0] + ox
    las.y = pts[:, 1] + oy
    las.z = pts[:, 2]
    las.classification = pts[:, 3].astype(np.uint8)
    las.write(os.path.join(folder, "points.laz"))

    feats = []
    for i, fp in enumerate(blds):
        rings = [[[float(x + ox), float(y + oy)] for x, y in np.vstack([r, r[:1]])] for r in fp.rings]
        feats.append({"type": "Feature", "properties": {"bid": i, "h_terrain": float(h_terrain[i]),
                                                        "h_roof": float(h_roof[i])},
                      "geometry": {"type": "Polygon", "coordinates": rings}})
    fc = {"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2154"}},
          "features": feats}
    with open(os.path.join(folder, "footprints.geojson"), "w", encoding="utf-8") as f:
        json.dump(fc, f)


def run(exe, folder, out, extra=()):
    cmd = [exe, "--srs", "EPSG:2154", "--id-attribute", "bid",
           "--h-terrain-attribute", "h_terrain", "--h-terrain-strategy", "buffer_user",
           "--h-roof-attribute", "h_roof", "--lod12", "--lod22", *extra,
           os.path.join(folder, "points.laz"), os.path.join(folder, "footprints.geojson"), out]
    # roofer embarque GDAL/PROJ : on neutralise une éventuelle autre installation de GDAL
    share = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(exe))), "share")
    env = {k: v for k, v in os.environ.items() if k not in ("PROJ_LIB", "PROJ_DATA", "GDAL_DATA", "GDAL_DRIVER_PATH")}
    env.update(PROJ_DATA=os.path.join(share, "proj"), PROJ_LIB=os.path.join(share, "proj"),
               GDAL_DATA=os.path.join(share, "gdal"))
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def read_cjseq(out, origin, lod="2.2"):
    """Lit les CityJSONSeq produits. Retourne {bid: dict(surfaces, attributes)}.

    surfaces : liste de (type_sémantique, [anneaux Nx3 en coordonnées locales]).
    """
    files = [os.path.join(dp, f) for dp, _, fs in os.walk(out) for f in fs if f.endswith((".city.jsonl", ".jsonl"))]
    res = {}
    for path in files:
        with open(path, encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        meta = next((l for l in lines if l.get("type") == "CityJSON"), None)
        scale = np.array(meta["transform"]["scale"])
        trans = np.array(meta["transform"]["translate"]) - np.array([origin[0], origin[1], 0.0])
        for feat in lines:
            if feat.get("type") != "CityJSONFeature":
                continue
            V = np.array(feat["vertices"], float) * scale + trans
            objs = feat["CityObjects"]
            parent = objs[feat["id"]]
            attrs = parent.get("attributes", {})
            bid = attrs.get("bid", feat["id"])
            surfaces = []
            for oid, o in objs.items():
                for g in o.get("geometry", []):
                    if str(g.get("lod")) != lod:
                        continue
                    sem = g.get("semantics", {})
                    stypes = [s["type"] for s in sem.get("surfaces", [])]
                    for si, shell in enumerate(g["boundaries"]):
                        for fi, face in enumerate(shell):
                            v = sem.get("values", [[None] * len(shell)] * len(g["boundaries"]))[si][fi]
                            surfaces.append((stypes[v] if v is not None else "?", [V[r] for r in face]))
            res[int(bid)] = dict(surfaces=surfaces, attributes=attrs)
    return res
