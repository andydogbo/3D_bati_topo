import sys, time, numpy as np
sys.path.insert(0, "src")
import ign
from geo import wgs84_to_l93
LAT, LON, R = 44.892599016233035, 6.6360779217772725, 100.0
CACHE = "data/cache"
cx, cy = wgs84_to_l93(LAT, LON)
t = time.time()
feats = ign.wfs("BDTOPO_V3:batiment", (cx - R, cy - R, cx + R, cy + R), CACHE)
g = feats[0]["geometry"]; print("géométrie:", g["type"], "coord ex:", g["coordinates"][0][0][:2])
def inside(f):
    ring = np.array(f["geometry"]["coordinates"][0][0])[:, :2]
    return np.min(np.hypot(ring[:, 0] - cx, ring[:, 1] - cy)) <= R
sel = [f for f in feats if inside(f)]
allxy = np.vstack([np.array(p[0])[:, :2] for f in sel for p in f["geometry"]["coordinates"]])
bb = (min(allxy[:, 0].min(), cx - R) - 5, min(allxy[:, 1].min(), cy - R) - 5, max(allxy[:, 0].max(), cx + R) + 5, max(allxy[:, 1].max(), cy + R) + 5)
print("%d bâtiments dans le cercle, bbox %.0f x %.0f m" % (len(sel), bb[2] - bb[0], bb[3] - bb[1]))
from collections import Counter
print("nature:", Counter(f["properties"]["nature"] for f in sel)); print("usage:", Counter(f["properties"]["usage_1"] for f in sel))
print("hauteurs:", sorted(round(f["properties"]["hauteur"] or 0, 1) for f in sel))
pts = ign.lidar_points(bb, CACHE)
print("%d points LiDAR (%.0fs)" % (len(pts), time.time() - t))
print("classes:", {int(k): int(v) for k, v in zip(*np.unique(pts[:, 3], return_counts=True))})
for lay in (ign.LAYER_MNT, ign.LAYER_MNS):
    z, x0, y0, res = ign.raster(lay, bb, CACHE)
    print(lay.split("_")[2], z.shape, "z %.1f..%.1f" % (np.nanmin(z), np.nanmax(z)), "NaN:", int(np.isnan(z).sum()), "origine", x0, y0)
