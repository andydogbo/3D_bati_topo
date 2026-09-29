import sys, time, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, "dev"); sys.path.insert(0, "src")
import zone, roofprints as rp
Z = zone.load(extra=60)
t = time.time()
m, x0, y0, c = rp.building_mask(Z["pts"], Z["bbox"], Z["mnt"])
mc = rp.clean_mask(m, c)
fa, _ = rp.lidar_roofprints(mc, x0, y0, c)
fb, _ = rp.split_by_footprints(mc, x0, y0, c, [fp for _, fp in Z["blds_all"]])
print("îlots LiDAR: %d  | découpés BD TOPO: %d  (%.1fs)" % (len(fa), len(fb), time.time() - t))
cx, cy = Z["center"]; R = Z["R"]
fig, axs = plt.subplots(1, 2, figsize=(20, 10))
for ax, fps, title in ((axs[0], fa, "M5a : emprises LiDAR (îlots)"), (axs[1], fb, "M5b : emprises LiDAR découpées par la BD TOPO")):
    ax.imshow(mc, extent=(x0, x0 + mc.shape[1] * c, y0 - mc.shape[0] * c, y0), cmap="Greys", alpha=0.25)
    for _, fp in Z["blds_all"]:
        for r in fp.rings: ax.plot(*np.vstack([r, r[:1]]).T, color="tab:blue", lw=0.8)
    for k, fp in fps.items():
        for j, r in enumerate(fp.rings): ax.plot(*np.vstack([r, r[:1]]).T, color="tab:red" if j == 0 else "tab:orange", lw=1.2)
    ax.add_patch(plt.Circle((cx, cy), R, fill=False, ls="--", color="k"))
    ax.set_xlim(cx - 60, cx + 20); ax.set_ylim(cy - 70, cy + 10); ax.set_aspect("equal"); ax.set_title(title + " — bleu : BD TOPO, rouge : LiDAR")
plt.tight_layout(); plt.savefig("dev/roofprints.png", dpi=60)
