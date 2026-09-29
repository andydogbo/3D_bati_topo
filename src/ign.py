"""Accès aux données IGN de la Géoplateforme (data.geopf.fr), en Lambert-93.

- BD TOPO (WFS)          : emprises de bâtiments, végétation...
- LiDAR HD (COPC)        : nuage de points classé, lu uniquement sur l'emprise voulue
- MNT / MNS LiDAR HD     : rasters 50 cm via WMS-R au format BIL 32 bits

Tout ce qui est téléchargé est mis en cache dans `cache_dir`.
"""
import hashlib
import json
import math
import os

import numpy as np
import requests

WFS = "https://data.geopf.fr/wfs/ows"
WMS_R = "https://data.geopf.fr/wms-r"
LAYER_MNT = "IGNF_LIDAR-HD_MNT_ELEVATION.ELEVATIONGRIDCOVERAGE.LAMB93"
LAYER_MNS = "IGNF_LIDAR-HD_MNS_ELEVATION.ELEVATIONGRIDCOVERAGE.LAMB93"

# Classes LiDAR HD
SOL, VEG_BASSE, VEG_MOY, VEG_HAUTE, BATI, EAU, PONT, SURSOL = 2, 3, 4, 5, 6, 9, 17, 64

_TIMEOUT = 120


def _cache_path(cache_dir, prefix, key, ext):
    h = hashlib.md5(key.encode("utf-8")).hexdigest()[:12]
    return os.path.join(cache_dir, "%s_%s.%s" % (prefix, h, ext))


def wfs(typename, bbox, cache_dir, page=1000):
    """Entités GeoJSON (Lambert-93) d'une couche WFS dans une bbox (xmin, ymin, xmax, ymax)."""
    path = _cache_path(cache_dir, typename.split(":")[-1], "%s|%r" % (typename, bbox), "json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    feats, start = [], 0
    while True:
        params = dict(SERVICE="WFS", VERSION="2.0.0", REQUEST="GetFeature", TYPENAMES=typename,
                      SRSNAME="EPSG:2154", OUTPUTFORMAT="application/json",
                      BBOX="%f,%f,%f,%f,EPSG:2154" % tuple(bbox), COUNT=page, STARTINDEX=start)
        r = requests.get(WFS, params=params, timeout=_TIMEOUT)
        r.raise_for_status()
        batch = r.json()["features"]
        feats += batch
        if len(batch) < page:
            break
        start += page
    os.makedirs(cache_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(feats, f)
    return feats


def raster(layer, bbox, cache_dir, res=0.5):
    """Raster d'altitude (MNT/MNS) sur la bbox, calé sur la grille IGN.

    Retourne (z, x0, y0, res) : z[i, j] est l'altitude du pixel de centre
    (x0 + j*res, y0 - i*res), ligne 0 au nord. Les valeurs absentes sont NaN.
    """
    # grille IGN : bords de pixels sur les multiples de res décalés d'un demi-pixel
    h = res / 2
    xmin = math.floor((bbox[0] + h) / res) * res - h
    ymin = math.floor((bbox[1] + h) / res) * res - h
    xmax = math.ceil((bbox[2] + h) / res) * res - h
    ymax = math.ceil((bbox[3] + h) / res) * res - h
    w, hgt = int(round((xmax - xmin) / res)), int(round((ymax - ymin) / res))
    key = "%s|%.2f,%.2f,%.2f,%.2f|%s" % (layer, xmin, ymin, xmax, ymax, res)
    path = _cache_path(cache_dir, "mns" if "MNS" in layer else "mnt", key, "npy")
    if os.path.exists(path):
        z = np.load(path)
    else:
        params = dict(SERVICE="WMS", VERSION="1.3.0", REQUEST="GetMap", LAYERS=layer, STYLES="",
                      CRS="EPSG:2154", BBOX="%f,%f,%f,%f" % (xmin, ymin, xmax, ymax),
                      WIDTH=w, HEIGHT=hgt, FORMAT="image/x-bil;bits=32")
        r = requests.get(WMS_R, params=params, timeout=_TIMEOUT)
        r.raise_for_status()
        if len(r.content) != w * hgt * 4:
            raise RuntimeError("Réponse WMS-R inattendue : %s" % r.text[:300])
        z = np.frombuffer(r.content, dtype="<f4").reshape(hgt, w).astype(np.float32)
        z = np.where(z < -1000, np.nan, z)
        os.makedirs(cache_dir, exist_ok=True)
        np.save(path, z)
    return z, xmin + h, ymax - h, res


def lidar_tiles(bbox, cache_dir):
    """URLs COPC des dalles LiDAR HD qui recouvrent la bbox."""
    feats = wfs("IGNF_LIDAR-HD_METADONNEE:metadata", bbox, cache_dir)
    return sorted({f["properties"]["url_npl"] for f in feats if f["properties"].get("url_npl")})


def lidar_points(bbox, cache_dir):
    """Points LiDAR HD dans la bbox : tableau (N, 4) float64 [x, y, z, classe]."""
    path = _cache_path(cache_dir, "lidar", "%r" % (tuple(bbox),), "npy")
    if os.path.exists(path):
        return np.load(path)
    import laspy  # dépendances : laspy, lazrs

    bounds = laspy.copc.Bounds(mins=np.array(bbox[:2], dtype=float), maxs=np.array(bbox[2:], dtype=float))
    import time

    parts = []
    for url in lidar_tiles(bbox, cache_dir):
        for attempt in range(6):  # la Géoplateforme limite le débit (HTTP 429)
            try:
                with laspy.CopcReader.open(url, http_num_threads=6) as reader:
                    p = reader.query(bounds)
                break
            except requests.HTTPError as e:
                if e.response is None or e.response.status_code != 429 or attempt == 5:
                    raise
                time.sleep(5 * (attempt + 1))
        if len(p):
            parts.append(np.column_stack([np.asarray(p.x), np.asarray(p.y), np.asarray(p.z),
                                          np.asarray(p.classification, dtype=float)]))
    pts = np.vstack(parts) if parts else np.zeros((0, 4))
    # la requête COPC travaille par cellules d'octree : on recoupe strictement
    m = (pts[:, 0] >= bbox[0]) & (pts[:, 0] <= bbox[2]) & (pts[:, 1] >= bbox[1]) & (pts[:, 1] <= bbox[3])
    pts = pts[m]
    os.makedirs(cache_dir, exist_ok=True)
    np.save(path, pts)
    return pts


LAYER_ORTHO = "ORTHOIMAGERY.ORTHOPHOTOS"


def orthophoto(bbox, cache_dir, res=0.2, layer=LAYER_ORTHO, max_px=5000):
    """Orthophotographie IGN (JPEG) sur la bbox Lambert-93. Retourne (chemin, bbox effective).

    La résolution est dégradée si nécessaire pour rester sous `max_px` pixels de côté.
    """
    w = (bbox[2] - bbox[0]) / res
    h = (bbox[3] - bbox[1]) / res
    k = max(1.0, max(w, h) / max_px)
    w, h = int(round(w / k)), int(round(h / k))
    key = "%s|%.2f,%.2f,%.2f,%.2f|%dx%d" % (layer, *bbox, w, h)
    path = _cache_path(cache_dir, "ortho", key, "jpg")
    if not os.path.exists(path):
        params = dict(SERVICE="WMS", VERSION="1.3.0", REQUEST="GetMap", LAYERS=layer, STYLES="",
                      CRS="EPSG:2154", BBOX="%f,%f,%f,%f" % tuple(bbox), WIDTH=w, HEIGHT=h,
                      FORMAT="image/jpeg")
        r = requests.get(WMS_R, params=params, timeout=_TIMEOUT)
        r.raise_for_status()
        if not r.headers.get("content-type", "").startswith("image/"):
            raise RuntimeError("Réponse WMS-R inattendue : %s" % r.text[:300])
        os.makedirs(cache_dir, exist_ok=True)
        with open(path, "wb") as f:
            f.write(r.content)
    return os.path.abspath(path), tuple(bbox)
