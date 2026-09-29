"""Détection individuelle des arbres à partir du LiDAR HD (classes végétation).

Méthode classique (CHM + maxima locaux à fenêtre variable + ligne de partage des eaux) :
  1. modèle de hauteur de canopée (CHM) 50 cm : max des points végétation - MNT
  2. sommets = maxima locaux dans une fenêtre dont la taille croît avec la hauteur
     (Popescu & Wynne 2004 : largeur = 2,51503 + 0,00901 h², en mètres)
  3. houppiers = bassins versants (watershed) du CHM inversé autour des sommets
  4. par arbre : position du sommet, hauteur, diamètre de couronne, base de couronne
"""
import numpy as np
from scipy import ndimage
from scipy.spatial import ConvexHull

import roofs

VEG_CLASSES = (4, 5)  # végétation moyenne (0,5-1,5 m) et haute (> 1,5 m)


def canopy_height_model(pts, bbox, mnt, cell=0.5, classes=VEG_CLASSES):
    """CHM : hauteur max de la végétation au-dessus du MNT. Retourne (chm HxW, x0, y0, cell)."""
    x0, y0 = bbox[0], bbox[3]
    w = int(np.ceil((bbox[2] - bbox[0]) / cell))
    h = int(np.ceil((bbox[3] - bbox[1]) / cell))
    P = pts[np.isin(pts[:, 3], classes)]
    hag = P[:, 2] - roofs.bilinear(*mnt, P[:, :2])
    j = ((P[:, 0] - x0) / cell).astype(int)
    i = ((y0 - P[:, 1]) / cell).astype(int)
    ok = (i >= 0) & (i < h) & (j >= 0) & (j < w)
    chm = np.zeros((h, w), np.float32)
    np.maximum.at(chm, (i[ok], j[ok]), hag[ok].astype(np.float32))
    # comble les cellules vides isolées à l'intérieur des couronnes, puis léger lissage
    filled = ndimage.grey_closing(chm, size=(3, 3))
    chm = np.where(chm > 0, chm, filled)
    chm = ndimage.gaussian_filter(chm, 0.6)
    return chm, x0, y0, cell


def _window_radius(h):
    """Rayon (m) de la fenêtre de recherche des maxima selon la hauteur (Popescu & Wynne 2004)."""
    return 0.5 * (2.51503 + 0.00901 * h ** 2)


def tree_tops(chm, cell, min_height=3.0):
    """Sommets des arbres : maxima locaux à fenêtre variable. Retourne (lignes, colonnes)."""
    radii = np.array([1.0, 1.5, 2.0, 2.5, 3.0, 4.0])
    maxes = []
    for r in radii:
        k = max(1, int(round(r / cell)))
        yy, xx = np.mgrid[-k:k + 1, -k:k + 1]
        disk = (xx ** 2 + yy ** 2) <= k ** 2
        maxes.append(ndimage.maximum_filter(chm, footprint=disk))
    maxes = np.array(maxes)
    need = np.searchsorted(radii, np.clip(_window_radius(chm), radii[0], radii[-1]))
    need = np.clip(need, 0, len(radii) - 1)
    local_max = np.take_along_axis(maxes, need[None], axis=0)[0]
    tops = (chm >= local_max - 1e-6) & (chm >= min_height)
    # plateaux : un seul sommet par composante
    lab, n = ndimage.label(tops)
    if n == 0:
        return np.array([], int), np.array([], int)
    c = ndimage.center_of_mass(tops, lab, range(1, n + 1))
    rc = np.round(np.array(c)).astype(int)
    return rc[:, 0], rc[:, 1]


def crowns(chm, rows, cols, min_height=2.0):
    """Segmentation des houppiers par ligne de partage des eaux. Retourne l'image d'étiquettes (0 = rien)."""
    markers = np.zeros(chm.shape, np.int32)
    markers[rows, cols] = np.arange(1, len(rows) + 1)
    mask = chm >= min_height
    markers[~mask & (markers == 0)] = -1  # fond
    inv = (np.clip(chm.max() - chm, 0, None) * 100).astype(np.uint16)
    lab = ndimage.watershed_ift(inv, markers)
    lab[~mask] = 0
    lab[lab < 0] = 0
    return lab


def detect_trees(pts, bbox, mnt, building_mask=None, cell=0.5, min_height=3.0, min_crown_area=1.0,
                 method="dalponte"):
    """Détecte les arbres. Retourne (liste de dict, CHM, étiquettes, x0, y0).

    Chaque arbre : x, y (sommet), z_sol, hauteur, rayon (couronne), base (hauteur de la base de
    couronne), aire, points (Nx3 des points du houppier).
    """
    chm, x0, y0, cell = canopy_height_model(pts, bbox, mnt, cell)
    if building_mask is not None:  # pas d'arbre sur les toits (points mal classés)
        chm = np.where(building_mask, 0, chm)
    rows, cols = tree_tops(chm, cell, min_height)
    lab = dalponte(chm, rows, cols, cell) if method == "dalponte" else crowns(chm, rows, cols)
    # points végétation -> houppier
    P = pts[np.isin(pts[:, 3], VEG_CLASSES)]
    j = ((P[:, 0] - x0) / cell).astype(int)
    i = ((y0 - P[:, 1]) / cell).astype(int)
    ok = (i >= 0) & (i < lab.shape[0]) & (j >= 0) & (j < lab.shape[1])
    P, i, j = P[ok], i[ok], j[ok]
    pid = lab[i, j]
    order = np.argsort(pid)
    P, pid = P[order], pid[order]
    starts = np.searchsorted(pid, np.arange(1, len(rows) + 2))
    areas = ndimage.sum(np.ones_like(lab), lab, index=np.arange(1, len(rows) + 1)) * cell * cell
    trees = []
    for k in range(len(rows)):
        pts_k = P[starts[k]:starts[k + 1], :3]
        if areas[k] < min_crown_area or len(pts_k) < 5:
            continue
        x, y = x0 + (cols[k] + 0.5) * cell, y0 - (rows[k] + 0.5) * cell
        zg = float(roofs.bilinear(*mnt, np.array([[x, y]]))[0])
        hk = pts_k[:, 2] - roofs.bilinear(*mnt, pts_k[:, :2])
        height = float(np.percentile(hk, 99))
        if height < min_height:
            continue
        base = float(np.clip(np.percentile(hk, 5), 0.15 * height, 0.7 * height))
        t = dict(x=x, y=y, z_sol=zg, hauteur=height, rayon=float(np.sqrt(areas[k] / np.pi)),
                 base=base, aire=float(areas[k]), points=pts_k, label=k + 1)
        t["type"] = classify_tree(t)
        trees.append(t)
    return trees, chm, lab, x0, y0


def crown_hull(points):
    """Enveloppe convexe des points du houppier : (sommets Nx3, triangles Mx3) ou None."""
    if len(points) < 8:
        return None
    try:
        h = ConvexHull(points)
    except Exception:
        return None
    V = points[h.vertices]
    remap = {v: k for k, v in enumerate(h.vertices)}
    F = np.array([[remap[a], remap[b], remap[c]] for a, b, c in h.simplices])
    # orientation vers l'extérieur
    c = V.mean(axis=0)
    p = V[F]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    flip = np.einsum("ij,ij->i", n, p.mean(axis=1) - c) < 0
    F[flip] = F[flip][:, [0, 2, 1]]
    return V, F


# ---------------------------------------------------------------------------------------------
# Segmentation Dalponte & Coomes (2016) : croissance de régions depuis les sommets

def dalponte(chm, rows, cols, cell, th_tree=2.0, th_seed=0.45, th_cr=0.55):
    """Croissance de régions depuis les sommets (Dalponte & Coomes 2016, comme lidR::dalponte2016).

    Un pixel rejoint le houppier voisin s'il est plus haut que th_tree, que th_seed x hauteur du
    sommet et que th_cr x hauteur moyenne du houppier, et s'il reste à moins du rayon maximal
    (fonction de la hauteur du sommet). Les pixels sont traités du plus haut au plus bas.
    """
    import heapq
    H, W = chm.shape
    lab = np.zeros((H, W), np.int32)
    n = len(rows)
    seed_h = chm[rows, cols].astype(float)
    max_r = np.clip(0.3 * seed_h + 1.0, 1.5, 8.0) / cell  # en pixels
    sum_h = seed_h.copy()
    cnt = np.ones(n)
    heap = []
    for k in range(n):
        lab[rows[k], cols[k]] = k + 1
    nb = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1))

    def push(i, j, k):
        for di, dj in nb:
            a, b = i + di, j + dj
            if 0 <= a < H and 0 <= b < W and lab[a, b] == 0 and chm[a, b] > th_tree:
                heapq.heappush(heap, (-float(chm[a, b]), a, b, k))

    for k in range(n):
        push(rows[k], cols[k], k)
    while heap:
        negh, i, j, k = heapq.heappop(heap)
        if lab[i, j]:
            continue
        h = -negh
        if h <= th_seed * seed_h[k] or h <= th_cr * sum_h[k] / cnt[k]:
            continue
        if (i - rows[k]) ** 2 + (j - cols[k]) ** 2 > max_r[k] ** 2:
            continue
        lab[i, j] = k + 1
        sum_h[k] += h
        cnt[k] += 1
        push(i, j, k)
    return lab


def classify_tree(tree):
    """Type de silhouette à partir des points du houppier : 'conifere', 'fastigie' ou 'feuillu'."""
    P = tree["points"]
    hag = P[:, 2] - tree["z_sol"]
    crown_h = tree["hauteur"] - tree["base"]
    if 2 * tree["rayon"] > 0 and crown_h / (2 * tree["rayon"]) > 2.2:
        return "fastigie"
    r = np.hypot(P[:, 0] - tree["x"], P[:, 1] - tree["y"])
    z0, z1 = tree["base"], tree["hauteur"]
    top = r[hag > z0 + 0.66 * (z1 - z0)]
    low = r[(hag > z0) & (hag < z0 + 0.5 * (z1 - z0))]
    if len(top) >= 5 and len(low) >= 5:
        ratio = np.percentile(top, 90) / max(np.percentile(low, 90), 0.1)
        if ratio < 0.55:
            return "conifere"
    return "feuillu"


# ---------------------------------------------------------------------------------------------
# Masses végétales (bosquets) et arbustes / haies

def vegetation_masses(chm, lab, tree_ids, cell, min_area=120.0, min_trees=4, cover=0.75):
    """Repère les bosquets : composantes du couvert (CHM > 3 m) assez grandes et denses.

    Retourne (masque des masses, ensemble des étiquettes d'arbres absorbés par une masse).
    """
    canopy = ndimage.binary_closing(chm > 3.0, iterations=1)
    comp, n = ndimage.label(canopy, structure=np.ones((3, 3)))
    mass = np.zeros_like(canopy)
    absorbed = set()
    for c in range(1, n + 1):
        m = comp == c
        area = m.sum() * cell * cell
        if area < min_area:
            continue
        ids = set(np.unique(lab[m])) - {0}
        ids &= tree_ids
        if len(ids) < min_trees:
            continue
        # compacité : part du rectangle englobant occupée (évite les alignements d'arbres)
        rr, cc = np.nonzero(m)
        fill = m.sum() / ((np.ptp(rr) + 1) * (np.ptp(cc) + 1))
        if fill < 0.35 and len(ids) < 8:
            continue
        mass |= m
        absorbed |= ids
    return mass, absorbed


def lens_mesh(mask, height, x0, y0, cell, mnt, base_ratio=0.35, edge=2.0, ground=False, step=2, smooth=2.0):
    """Volume fermé « en lentille » sur un masque raster : dessus = hauteur locale, dessous = base
    de couronne (ou le sol si ground=True) ; épaisseur nulle sur le contour, arrondie sur `edge` m.

    Travaille au pas `step` pixels. Retourne une liste de (V, F) par composante connexe.
    """
    m = mask[::step, ::step]
    hgt = ndimage.grey_dilation(height, size=(step, step))[::step, ::step]
    c = cell * step
    # lissage (en mètres) : une canopée continue plutôt qu'une succession de pics
    w = ndimage.gaussian_filter(m.astype(float), smooth / c)
    hgt = ndimage.gaussian_filter(np.where(m, hgt, 0.0), smooth / c) / np.maximum(w, 1e-6)
    out = []
    comp, n = ndimage.label(m)
    for k in range(1, n + 1):
        mk = comp == k
        if mk.sum() < 4:
            continue
        idx = -np.ones(mk.shape, int)
        ii, jj = np.nonzero(mk)
        idx[ii, jj] = np.arange(len(ii))
        # dessus : deux triangles par maille dont les 4 coins sont dans le masque
        a = idx[:-1, :-1].ravel(); b = idx[:-1, 1:].ravel(); cc = idx[1:, 1:].ravel(); d = idx[1:, :-1].ravel()
        ok = (a >= 0) & (b >= 0) & (cc >= 0) & (d >= 0)
        a, b, cc, d = a[ok], b[ok], cc[ok], d[ok]
        if not len(a):
            continue
        Ftop = np.vstack([np.column_stack([a, d, cc]), np.column_stack([a, cc, b])])
        # contour du maillage : épaisseur nulle, dessus et dessous y partagent leurs sommets
        border = np.zeros(len(ii), bool)
        for loop in roofs.boundary_loops(Ftop):
            border[loop] = True
        used = np.zeros(len(ii), bool)
        used[Ftop.ravel()] = True
        bimg = np.ones(mk.shape, bool)
        bimg[ii[border], jj[border]] = False
        dist = ndimage.distance_transform_edt(bimg)[ii, jj] * c
        f = np.sqrt(np.clip(dist / edge, 0, 1) * (2 - np.clip(dist / edge, 0, 1)))  # profil arrondi
        xs = x0 + (jj + 0.5) * c
        ys = y0 - (ii + 0.5) * c
        zg = roofs.bilinear(*mnt, np.column_stack([xs, ys]))
        Hh = hgt[ii, jj]
        if ground:
            top, bot = Hh * f, np.zeros_like(Hh)
        else:
            B = base_ratio * Hh
            mid, half = (Hh + B) / 2, (Hh - B) / 2 * f
            top, bot = mid + half, mid - half
        nv = len(ii)
        inner = ~border
        bot_idx = np.where(border, np.arange(nv), nv + np.cumsum(inner) - 1)
        V = np.vstack([np.column_stack([xs, ys, zg + top]),
                       np.column_stack([xs, ys, zg + bot])[inner]])
        Fbot = bot_idx[Ftop][:, [0, 2, 1]]
        F = np.vstack([Ftop, Fbot])
        # faces dégénérées (trois sommets de contour) : dessus et dessous confondus, on les retire
        deg = border[Ftop].all(axis=1)
        F = np.vstack([Ftop[~deg], Fbot[~deg]])
        out.append((V, F))
    return out
