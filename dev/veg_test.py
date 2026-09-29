import sys, time, numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.image import imread
sys.path.insert(0, "dev"); sys.path.insert(0, "src")
import zone, roofprints as rp, vegetation as veg
Z = zone.load(extra=60)
t = time.time()
bm, mx0, my0, mc = rp.building_mask(Z["pts"], Z["bbox"], Z["mnt"])
bm = rp.ndimage.binary_dilation(rp.clean_mask(bm, mc), iterations=1)
trees, chm, lab, x0, y0 = veg.detect_trees(Z["pts"], Z["bbox"], Z["mnt"], building_mask=bm)
inR = [t_ for t_ in trees if np.hypot(t_["x"], t_["y"]) <= Z["R"]]
print("%d arbres détectés sur la zone chargée, %d dans le cercle de %.0f m (%.1fs)" % (len(trees), len(inR), Z["R"], time.time() - t))
H = np.array([t_["hauteur"] for t_ in inR]); D = np.array([2 * t_["rayon"] for t_ in inR]); B = np.array([t_["base"] for t_ in inR])
print("hauteur : médiane %.1f m (%.1f..%.1f) | diamètre couronne : médiane %.1f m (%.1f..%.1f) | base couronne médiane %.1f m"
      % (np.median(H), H.min(), H.max(), np.median(D), D.min(), D.max(), np.median(B)))
path, (ox0, oy0, ox1, oy1) = Z["ortho"]
img = imread(path)
fig, axs = plt.subplots(1, 2, figsize=(20, 10))
for ax, lim in ((axs[0], (-100, 100, -100, 100)), (axs[1], (-60, 0, -95, -35))):
    ax.imshow(img, extent=(ox0, ox1, oy0, oy1))
    edges = (lab != np.roll(lab, 1, 0)) | (lab != np.roll(lab, 1, 1))
    E = np.ma.masked_where(~(edges & (lab > 0)), edges)
    ax.imshow(E, extent=(x0, x0 + lab.shape[1] * 0.5, y0 - lab.shape[0] * 0.5, y0), cmap="autumn", alpha=0.9, interpolation="nearest")
    for t_ in trees:
        ax.plot(t_["x"], t_["y"], "c+", ms=6, mew=1.5)
    ax.add_patch(plt.Circle((0, 0), Z["R"], fill=False, color="cyan", ls="--"))
    ax.set_xlim(lim[0], lim[1]); ax.set_ylim(lim[2], lim[3])
axs[0].set_title("%d arbres dans le cercle (croix = sommets, rouge = limites de houppiers)" % len(inR))
plt.tight_layout(); plt.savefig("dev/veg_check.png", dpi=55)
