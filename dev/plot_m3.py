import sys, pickle, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
sys.path.insert(0, "dev"); sys.path.insert(0, "src")
import zone, roofs
Z = zone.load(); res = pickle.load(open("dev/m3.pkl", "rb"))
pts6 = Z["pts"][Z["pts"][:, 3] == 6]
ids = [int(a) for a in sys.argv[1:]] or [1, 7, 51, 17]
cmap = plt.get_cmap("tab20")
fig = plt.figure(figsize=(16, 4 * len(ids)))
for r, i in enumerate(ids):
    m3 = res[i][3]; fp = Z["blds"][i][1]
    P, N = roofs.building_points(fp, pts6)
    for c, (el, az) in enumerate([(35, -60), (35, 120), (90, -90)]):
        ax = fig.add_subplot(len(ids), 4, r * 4 + c + 1, projection="3d")
        cols = [cmap(l % 20) if l >= 0 else (0.1, 0.1, 0.1, 1) for l in m3["face_label"]]
        ax.add_collection3d(Poly3DCollection(m3["V"][m3["F"]], facecolors=cols, edgecolors="none"))
        V = m3["V"]; mid = (V.max(0) + V.min(0)) / 2; s = (V.max(0) - V.min(0)).max() / 2
        ax.set_xlim(mid[0]-s, mid[0]+s); ax.set_ylim(mid[1]-s, mid[1]+s); ax.set_zlim(mid[2]-s/2, mid[2]+s/2)
        ax.view_init(el, az); ax.set_title("bât %d vue %d" % (i, c)); ax.set_axis_off()
    ax = fig.add_subplot(len(ids), 4, r * 4 + 4, projection="3d")
    ax.scatter(P[:, 0], P[:, 1], P[:, 2], s=1, c=P[:, 2], cmap="viridis")
    ax.view_init(35, -60); ax.set_title("points LiDAR"); ax.set_axis_off()
plt.tight_layout(); plt.savefig("dev/m3_check.png", dpi=70)
