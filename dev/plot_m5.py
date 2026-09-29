import sys, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
sys.path.insert(0, "dev"); sys.path.insert(0, "src")
import zone, roofer_io
Z = zone.load(extra=60)
box = (-62, -72, 22, 12)
fig = plt.figure(figsize=(20, 9))
for k, (out, title) in enumerate((("data/roofer_out", "M4 roofer + emprises BD TOPO"), ("data/roofer_out_M5b", "M5b roofer + emprises LiDAR découpées"))):
    res = roofer_io.read_cjseq(out, Z["origin"])
    polys, cols = [], []
    for r in res.values():
        for t, rings in r["surfaces"]:
            c = rings[0].mean(0)
            if not (box[0] < c[0] < box[2] and box[1] < c[1] < box[3]): continue
            if t == "RoofSurface":
                n = np.cross(rings[0][1] - rings[0][0], rings[0][2] - rings[0][0]); n /= np.linalg.norm(n) + 1e-9
                sh = 0.45 + 0.5 * max(0, n @ np.array([-0.4, -0.5, 0.77]))
                polys.append(rings[0]); cols.append((0.85 * sh, 0.35 * sh, 0.3 * sh, 1))
            elif t == "WallSurface":
                polys.append(rings[0]); cols.append((0.8, 0.78, 0.74, 1))
    ax = fig.add_subplot(1, 2, k + 1, projection="3d")
    ax.add_collection3d(Poly3DCollection(polys, facecolors=cols, edgecolors=(0, 0, 0, 0.3), linewidths=0.2))
    ax.set_xlim(box[0], box[2]); ax.set_ylim(box[1], box[3]); ax.set_zlim(1195, 1240)
    ax.set_box_aspect((1, 1, 0.55)); ax.view_init(38, -65); ax.set_axis_off(); ax.set_title(title)
plt.tight_layout(); plt.savefig("dev/m4_m5b.png", dpi=70)
