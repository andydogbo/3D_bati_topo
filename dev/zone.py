"""Chargement de la zone test en coordonnées locales (origine = centre arrondi au mètre)."""
import sys, json, numpy as np
sys.path.insert(0, "src")
import ign, roofs
from geo import wgs84_to_l93
LAT, LON, R = 44.892599016233035, 6.6360779217772725, 100.0
TERRAIN_FACTOR = 2.0  # rayon du terrain = TERRAIN_FACTOR x rayon d'analyse
CACHE = "data/cache"

def load(extra=0.0):
    """extra > 0 : LiDAR et rasters chargés sur un carré de demi-côté R + extra, et
    `blds_all` contient toutes les emprises BD TOPO de ce carré."""
    cx, cy = wgs84_to_l93(LAT, LON)
    ox, oy = cx, cy  # (0, 0) = la coordonnée géographique exacte
    feats = ign.wfs("BDTOPO_V3:batiment", (cx - R, cy - R, cx + R, cy + R), CACHE)
    blds = []
    for f in feats:
        for fp in roofs.polygons_from_geojson(f["geometry"], (ox, oy)):
            ring = fp.rings[0]
            if np.min(np.hypot(ring[:, 0] - (cx - ox), ring[:, 1] - (cy - oy))) <= R:
                blds.append((f["properties"], fp))
    allxy = np.vstack([fp.seg_a for _, fp in blds]) + (ox, oy)
    bb = (min(allxy[:, 0].min(), cx - R) - 5, min(allxy[:, 1].min(), cy - R) - 5,
          max(allxy[:, 0].max(), cx + R) + 5, max(allxy[:, 1].max(), cy + R) + 5)
    blds_all = blds
    if extra > 0:
        E = R + extra
        bb = (min(bb[0], cx - E), min(bb[1], cy - E), max(bb[2], cx + E), max(bb[3], cy + E))
        blds_all = [(f["properties"], fp) for f in ign.wfs("BDTOPO_V3:batiment", bb, CACHE)
                    for fp in roofs.polygons_from_geojson(f["geometry"], (ox, oy))]
    pts = ign.lidar_points(bb, CACHE).copy(); pts[:, 0] -= ox; pts[:, 1] -= oy
    z, x0, y0, res = ign.raster(ign.LAYER_MNT, bb, CACHE); mnt = (z, x0 - ox, y0 - oy, res)
    z, x0, y0, res = ign.raster(ign.LAYER_MNS, bb, CACHE); mns = (z, x0 - ox, y0 - oy, res)
    # Z = 0 au niveau du terrain (MNT) à la coordonnée
    z0 = float(roofs.bilinear(*mnt, np.array([[0.0, 0.0]]))[0])
    pts[:, 2] -= z0
    mnt = (mnt[0] - z0,) + mnt[1:]
    mns = (mns[0] - z0,) + mns[1:]
    # terrain de contexte : MNT sur un rayon TERRAIN_FACTOR x R
    RT = TERRAIN_FACTOR * R
    z, x0, y0, res = ign.raster(ign.LAYER_MNT, (cx - RT - 2, cy - RT - 2, cx + RT + 2, cy + RT + 2), CACHE)
    mnt_terrain = (z - z0, x0 - ox, y0 - oy, res)
    # orthophotographie IGN sur l'emprise du terrain
    obb = (cx - RT - 2, cy - RT - 2, cx + RT + 2, cy + RT + 2)
    ortho_path, _ = ign.orthophoto(obb, CACHE)
    ortho = (ortho_path, (obb[0] - ox, obb[1] - oy, obb[2] - ox, obb[3] - oy))
    # nord géographique dans le repère Lambert-93 (convergence des méridiens)
    nx, ny = wgs84_to_l93(LAT + 0.001, LON)
    north = np.array([nx - cx, ny - cy]); north /= np.hypot(*north)
    return dict(origin=(ox, oy), z0=z0, mnt_terrain=mnt_terrain, ortho=ortho, R_terrain=RT, latlon=(LAT, LON), north=north,
                center=(0.0, 0.0), R=R, blds=blds, blds_all=blds_all, pts=pts,
                mnt=mnt, mns=mns, bbox=(bb[0] - ox, bb[1] - oy, bb[2] - ox, bb[3] - oy))
