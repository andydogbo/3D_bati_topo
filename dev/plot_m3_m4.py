import sys, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
sys.path.insert(0, "dev"); sys.path.insert(0, "src")
import zone, roofs, roofer_io
Z = zone.load(); pts6 = Z["pts"][Z["pts"][:, 3] == 6]
res4 = roofer_io.read_cjseq("data/roofer_out", Z["origin"])
ids = [int(a) for a in sys.argv[1:]]
cmap = plt.get_cmap("tab20")
fig = plt.figure(figsize=(15, 4.2 * len(ids)))
def setlim(ax, V):
    mid = (V.max(0) + V.min(0)) / 2; s = (V.max(0) - V.min(0))[:2].max() / 2
    ax.set_xlim(mid[0]-s, mid[0]+s); ax.set_ylim(mid[1]-s, mid[1]+s); ax.set_zlim(V[:, 2].max() - 1.2*s, V[:, 2].max() + 0.2*s)
for r, i in enumerate(ids):
    fp = Z["blds"][i][1]; P, N = roofs.building_points(fp, pts6)
    m3 = roofs.roof_planes(fp, P, N)
    ax = fig.add_subplot(len(ids), 3, 3*r + 1, projection="3d")
    cols = [cmap(l % 20) if l >= 0 else (0.15, 0.15, 0.15, 1) for l in m3["face_label"]]
    ax.add_collection3d(Poly3DCollection(m3["V"][m3["F"]], facecolors=cols, edgecolors="none"))
    setlim(ax, P); ax.view_init(40, -60); ax.set_axis_off(); ax.set_title("bât %d — M3 (maison)" % i)
    ax = fig.add_subplot(len(ids), 3, 3*r + 2, projection="3d")
    polys, cols = [], []
    for k, (t, rings) in enumerate(res4[i]["surfaces"]):
        if t == "RoofSurface": polys.append(rings[0]); cols.append(cmap(k % 20))
        elif t == "WallSurface": polys.append(rings[0]); cols.append((0.25, 0.25, 0.25, 1))
    ax.add_collection3d(Poly3DCollection(polys, facecolors=cols, edgecolors="k", linewidths=0.2))
    setlim(ax, P); ax.view_init(40, -60); ax.set_axis_off(); ax.set_title("bât %d — M4 roofer (%s)" % (i, res4[i]["attributes"].get("rf_extrusion_mode")))
    ax = fig.add_subplot(len(ids), 3, 3*r + 3, projection="3d")
    ax.scatter(P[:, 0], P[:, 1], P[:, 2], s=1, c=P[:, 2], cmap="viridis"); setlim(ax, P)
    ax.view_init(40, -60); ax.set_axis_off(); ax.set_title("points LiDAR")
plt.tight_layout(); plt.savefig("dev/m3_m4.png", dpi=62)
