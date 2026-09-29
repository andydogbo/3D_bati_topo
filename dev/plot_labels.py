import sys, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, "dev"); sys.path.insert(0, "src")
import zone, roofs
Z = zone.load(); pts6 = Z["pts"][Z["pts"][:, 3] == 6]
ids = [int(a) for a in sys.argv[1:]]
cmap = plt.get_cmap("tab20")
fig, axs = plt.subplots(len(ids), 3, figsize=(18, 6 * len(ids)), squeeze=False)
for r, i in enumerate(ids):
    fp = Z["blds"][i][1]
    P, N = roofs.building_points(fp, pts6)
    pl, lab = roofs.segment_planes(P, N)
    col = [cmap(l % 20) if l >= 0 else (0, 0, 0, 1) for l in lab]
    ax = axs[r, 0]; ax.scatter(P[:, 0], P[:, 1], s=4, c=col)
    for ring in fp.rings: ax.plot(*np.vstack([ring, ring[:1]]).T, "k-", lw=1)
    # voisinage : tous les points (toutes classes) autour
    x0, y0, x1, y1 = fp.bbox; A = Z["pts"]; m = (A[:, 0] > x0 - 3) & (A[:, 0] < x1 + 3) & (A[:, 1] > y0 - 3) & (A[:, 1] < y1 + 3)
    ax.set_aspect("equal"); ax.set_title("bât %d : %d pans (noir = non affecté)" % (i, len(pl)))
    ax = axs[r, 1]; A = A[m]
    u = np.array([np.cos(0.0), np.sin(0.0)])
    # coupe selon l'axe principal de l'emprise
    c = P[:, :2].mean(0); ev = np.linalg.eigh(np.cov((P[:, :2] - c).T))[1][:, 1]
    ax.scatter((P[:, :2] - c) @ ev, P[:, 2], s=3, c=col); ax.set_title("coupe long. (axe principal)")
    ax = axs[r, 2]; cls = {2: "sol", 3: "vb", 4: "vm", 5: "vh", 6: "bâti", 1: "nc"}
    for k, cc in [(1, "gray"), (2, "brown"), (5, "green"), (6, "red")]:
        q = A[A[:, 3] == k]; ax.scatter(q[:, 0], q[:, 1], s=2, c=cc, label=cls[k])
    for ring in fp.rings: ax.plot(*np.vstack([ring, ring[:1]]).T, "k-", lw=1.5)
    ax.set_aspect("equal"); ax.legend(); ax.set_title("classes LiDAR autour de l'emprise")
    print(i, "props:", {k: Z["blds"][i][0][k] for k in ("hauteur", "altitude_minimale_sol", "altitude_maximale_toit", "usage_1")}, "z pts %.1f..%.1f" % (P[:, 2].min(), P[:, 2].max()) if len(P) else "")
plt.tight_layout(); plt.savefig("dev/labels_check.png", dpi=55)
