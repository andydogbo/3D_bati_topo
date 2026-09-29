"""Emprises de toiture (« roofprints ») extraites du LiDAR : projection au sol des points bâti.

Contrairement aux emprises BD TOPO (souvent le nu des murs, issu du cadastre), elles incluent
les débords de toiture. Deux variantes :
  - lidar_roofprints     : composantes connexes du masque bâti (un îlot mitoyen = un objet)
  - split_by_footprints  : même masque, redécoupé selon les emprises BD TOPO les plus proches
"""
import numpy as np
from scipy import ndimage

import roofs


def building_mask(pts, bbox, mnt=None, cell=0.5, min_height=1.5):
    """Masque raster des toitures : cellules contenant des points classés bâtiment.

    Retourne (masque bool HxW, x0, y0, cell) ; la cellule [i, j] couvre
    x in [x0 + j*cell, x0 + (j+1)*cell], y in [y0 - (i+1)*cell, y0 - i*cell] (ligne 0 au nord).
    """
    x0, y0 = bbox[0], bbox[3]
    w = int(np.ceil((bbox[2] - bbox[0]) / cell))
    h = int(np.ceil((bbox[3] - bbox[1]) / cell))
    P = pts[pts[:, 3] == 6]
    if mnt is not None:  # écarte les points « bâti » au ras du sol
        P = P[P[:, 2] - roofs.bilinear(*mnt, P[:, :2]) >= min_height]
    j = ((P[:, 0] - x0) / cell).astype(int)
    i = ((y0 - P[:, 1]) / cell).astype(int)
    ok = (i >= 0) & (i < h) & (j >= 0) & (j < w)
    m = np.zeros((h, w), bool)
    m[i[ok], j[ok]] = True
    return m, x0, y0, cell


def clean_mask(m, cell, close_m=1.0, open_m=0.5, min_area=8.0, max_hole=4.0):
    """Morphologie : comble les lacunes du nuage, retire les éléments fins et les petits objets."""
    st = ndimage.generate_binary_structure(2, 1)
    m = ndimage.binary_closing(m, st, iterations=max(1, int(round(close_m / cell))))
    m = ndimage.binary_opening(m, st, iterations=max(1, int(round(open_m / cell))))
    # petits trous (lacunes) bouchés, les vraies cours conservées
    holes, n = ndimage.label(~m)
    if n:
        sizes = ndimage.sum(np.ones_like(m), holes, index=np.arange(1, n + 1)) * cell * cell
        border = set(np.unique(np.r_[holes[0], holes[-1], holes[:, 0], holes[:, -1]]))
        small = [k + 1 for k, s in enumerate(sizes) if s < max_hole and (k + 1) not in border]
        m |= np.isin(holes, small)
    lab, n = ndimage.label(m)
    if n:
        sizes = ndimage.sum(m, lab, index=np.arange(1, n + 1)) * cell * cell
        m = np.isin(lab, [k + 1 for k, s in enumerate(sizes) if s >= min_area])
    return m


def _trace(lab, k):
    """Contours (bords de pixels) de la région lab == k, en indices de coins (i, j)."""
    r = np.pad(lab == k, 1)
    nxt = {}
    # arêtes orientées matière à gauche (sens trigonométrique en coordonnées x, y)
    ii, jj = np.nonzero(r[1:-1, 1:-1] & ~r[:-2, 1:-1])  # voisin nord vide : arête vers l'ouest
    for i, j in zip(ii, jj):
        nxt.setdefault((i, j + 1), []).append((i, j))
    ii, jj = np.nonzero(r[1:-1, 1:-1] & ~r[2:, 1:-1])  # sud vide : vers l'est
    for i, j in zip(ii, jj):
        nxt.setdefault((i + 1, j), []).append((i + 1, j + 1))
    ii, jj = np.nonzero(r[1:-1, 1:-1] & ~r[1:-1, :-2])  # ouest vide : vers le sud
    for i, j in zip(ii, jj):
        nxt.setdefault((i, j), []).append((i + 1, j))
    ii, jj = np.nonzero(r[1:-1, 1:-1] & ~r[1:-1, 2:])  # est vide : vers le nord
    for i, j in zip(ii, jj):
        nxt.setdefault((i + 1, j + 1), []).append((i, j + 1))
    loops = []
    while nxt:
        start = next(iter(nxt))
        loop, v = [start], nxt[start].pop()
        if not nxt[start]:
            del nxt[start]
        while v != start:
            loop.append(v)
            outs = nxt.get(v)
            if not outs:
                break
            nv = outs.pop()
            if not outs:
                del nxt[v]
            v = nv
        if len(loop) >= 4:
            loops.append(np.array(loop, float))
    return loops


def _douglas_peucker(P, tol):
    """Simplification d'un anneau fermé (Nx2)."""
    if len(P) < 4:
        return P
    # découpe l'anneau aux deux points les plus éloignés
    d = np.hypot(*(P - P[0]).T)
    k = int(np.argmax(d))

    def dp(Q):
        if len(Q) < 3:
            return Q
        a, b = Q[0], Q[-1]
        ab = b - a
        n = np.hypot(*ab)
        dist = np.abs(np.cross(ab, Q - a)) / n if n > 1e-9 else np.hypot(*(Q - a).T)
        i = int(np.argmax(dist))
        if dist[i] <= tol:
            return np.vstack([a, b])
        return np.vstack([dp(Q[: i + 1])[:-1], dp(Q[i:])])

    A = dp(np.vstack([P[: k + 1]]))
    B = dp(np.vstack([P[k:], P[:1]]))
    return np.vstack([A[:-1], B[:-1]])


def _line_intersection(p, d, q, e):
    den = d[0] * e[1] - d[1] * e[0]
    if abs(den) < 1e-9:
        return None
    t = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / den
    return p + t * d


def regularize(ring, angle_tol=15.0, merge_offset=0.4):
    """Régularise un anneau simplifié : les côtés proches de l'orientation dominante (modulo 90°)
    y sont alignés, les côtés alignés consécutifs fusionnés, les sommets recalculés par intersection.
    """
    n = len(ring)
    if n < 4:
        return ring
    V = ring
    D = np.roll(V, -1, axis=0) - V
    L = np.hypot(D[:, 0], D[:, 1])
    th = np.degrees(np.arctan2(D[:, 1], D[:, 0]))
    # orientation dominante (modulo 90°), pondérée par les longueurs
    hist = np.zeros(90)
    np.add.at(hist, np.mod(np.round(th), 90).astype(int) % 90, L)
    hist = sum(np.roll(hist, s) * wgt for s, wgt in ((-2, 1), (-1, 2), (0, 3), (1, 2), (2, 1)))
    dom = float(np.argmax(hist))
    lines = []  # (point, direction, longueur, aligné)
    for k in range(n):
        if L[k] < 1e-6:
            continue
        mid = V[k] + D[k] / 2
        delta = (th[k] - dom + 45) % 90 - 45
        if abs(delta) < angle_tol:
            a = np.radians(th[k] - delta)
            lines.append([mid, np.array([np.cos(a), np.sin(a)]), L[k], True])
        else:
            lines.append([mid, D[k] / L[k], L[k], False])
    # fusion des côtés consécutifs parallèles et quasi colinéaires
    merged = True
    while merged and len(lines) > 3:
        merged = False
        for k in range(len(lines)):
            a, b = lines[k], lines[(k + 1) % len(lines)]
            if a[3] and b[3] and abs(a[1] @ b[1]) > 0.999:
                off = abs(np.cross(a[1], b[0] - a[0]))
                if off < merge_offset:
                    w = a[2] + b[2]
                    a[0] = (a[0] * a[2] + b[0] * b[2]) / w
                    a[2] = w
                    lines.pop((k + 1) % len(lines))
                    merged = True
                    break
    out = []
    m = len(lines)
    for k in range(m):
        a, b = lines[k - 1], lines[k]
        p = _line_intersection(a[0], a[1], b[0], b[1])
        if p is None or np.hypot(*(p - b[0])) > 3 * (a[2] + b[2]):
            # côtés parallèles décalés : on relie par un segment perpendiculaire
            out.append(a[0] + ((b[0] - a[0]) @ a[1]) * a[1])
            out.append(b[0] - ((b[0] - a[0]) @ b[1]) * b[1])
        else:
            out.append(p)
    out = np.array(out)
    a0, a1 = roofs._signed_area(ring), roofs._signed_area(out)
    if len(out) < 3 or a0 == 0 or abs(a1 / a0 - 1) > 0.1 or np.sign(a1) != np.sign(a0):
        return ring  # régularisation rejetée
    return out


def mask_to_footprints(lab, ids, x0, y0, cell, simplify=0.5, regular=True):
    """Vectorise les régions d'une image d'étiquettes -> {id: Footprint}."""
    out = {}
    for k in ids:
        comp, nc = ndimage.label(lab == k)
        for c in range(1, nc + 1):
            ext, holes = None, []
            for loop in _trace(comp, c):
                xy = np.column_stack([x0 + loop[:, 1] * cell, y0 - loop[:, 0] * cell])
                xy = _douglas_peucker(xy, simplify)
                if regular and len(xy) >= 4:
                    xy = regularize(xy)
                a = roofs._signed_area(xy) if len(xy) >= 3 else 0.0
                if a > 1.0 and (ext is None or a > roofs._signed_area(ext)):
                    ext = xy
                elif a < -1.0:
                    holes.append(xy)
            if ext is not None:
                out[(k, c)] = roofs.Footprint([ext] + holes)
    return out


def lidar_roofprints(mask, x0, y0, cell, keep=None):
    """Variante 100 % LiDAR : une emprise par composante connexe (îlot)."""
    lab, n = ndimage.label(mask)
    ids = range(1, n + 1) if keep is None else [k for k in range(1, n + 1) if keep(lab == k)]
    return mask_to_footprints(lab, ids, x0, y0, cell), lab


def split_by_footprints(mask, x0, y0, cell, footprints, max_dist=3.0):
    """Variante hybride : chaque cellule bâtie est rattachée à l'emprise BD TOPO la plus proche.

    Les cellules à plus de `max_dist` de toute emprise forment de nouveaux bâtiments
    (absents de la BD TOPO). Retourne ({clé: Footprint}, image d'étiquettes).
    """
    h, w = mask.shape
    jj, ii = np.meshgrid(np.arange(w), np.arange(h))
    cx = x0 + (jj.ravel() + 0.5) * cell
    cy = y0 - (ii.ravel() + 0.5) * cell
    C = np.column_stack([cx, cy])
    fl = np.zeros(h * w, int)
    for k, fp in enumerate(footprints):
        x_0, y_0, x_1, y_1 = fp.bbox
        sel = np.flatnonzero((cx >= x_0) & (cx <= x_1) & (cy >= y_0) & (cy <= y_1))
        if len(sel):
            fl[sel[fp.contains(C[sel])]] = k + 1
    fl = fl.reshape(h, w)
    dist, (ni, nj) = ndimage.distance_transform_edt(fl == 0, return_indices=True)
    lab = np.where(mask & (dist * cell <= max_dist), fl[ni, nj], 0)
    # bâti LiDAR sans emprise BD TOPO proche : nouveaux objets
    orphan, n = ndimage.label(mask & (lab == 0))
    lab = np.where(orphan > 0, orphan + len(footprints), lab)
    ids = [k for k in np.unique(lab) if k > 0]
    return mask_to_footprints(lab, ids, x0, y0, cell), lab
