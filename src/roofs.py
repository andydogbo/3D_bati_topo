"""Reconstruction des toitures à partir des emprises BD TOPO et du LiDAR HD.

Ce module ne dépend que de numpy / scipy : il produit des sommets et des faces,
la conversion en géométrie Rhino se fait dans rhino_build.py.

Trois méthodes :
  roof_lidar  : triangulation directe des points LiDAR « bâtiment »
  roof_mns    : maillage régulier drapé sur le MNS 50 cm
  roof_planes : détection des pans de toiture (RANSAC) puis toiture plane par morceaux
"""
import numpy as np
from scipy.spatial import Delaunay, cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

EPS = 1e-9


# --------------------------------------------------------------------------- emprises

def _signed_area(r):
    x, y = r[:, 0], r[:, 1]
    return 0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)


def polygons_from_geojson(geom, origin=(0.0, 0.0)):
    """Liste de polygones (liste d'anneaux Nx2, extérieur CCW, trous CW)."""
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    out = []
    for poly in polys:
        rings = []
        for k, ring in enumerate(poly):
            r = np.asarray(ring, float)[:, :2] - np.asarray(origin, float)
            if np.allclose(r[0], r[-1]):
                r = r[:-1]
            keep = np.r_[True, np.hypot(*np.diff(r, axis=0).T) > 1e-3]
            r = r[keep]
            if len(r) < 3 or abs(_signed_area(r)) < 1e-2:
                continue
            if (k == 0) != (_signed_area(r) > 0):
                r = r[::-1]
            rings.append(r)
        if rings:
            out.append(Footprint(rings))
    return out


class Footprint:
    """Emprise polygonale (avec trous éventuels) en coordonnées locales."""

    def __init__(self, rings):
        self.rings = rings
        a = np.vstack(rings)
        self.bbox = (a[:, 0].min(), a[:, 1].min(), a[:, 0].max(), a[:, 1].max())
        self.seg_a = np.vstack(rings)
        self.seg_b = np.vstack([np.roll(r, -1, axis=0) for r in rings])
        self.area = sum(_signed_area(r) for r in rings)

    def contains(self, xy):
        """Test point-dans-polygone (règle pair-impair), vectorisé sur les points."""
        x, y = xy[:, 0], xy[:, 1]
        inside = np.zeros(len(xy), bool)
        for (xa, ya), (xb, yb) in zip(self.seg_a, self.seg_b):
            cross = (ya > y) != (yb > y)
            xi = xa + (y - ya) * (xb - xa) / (yb - ya + EPS)
            inside ^= cross & (x < xi)
        return inside

    def boundary_distance(self, xy):
        d = np.full(len(xy), np.inf)
        for a, b in zip(self.seg_a, self.seg_b):
            ab = b - a
            t = np.clip(((xy - a) @ ab) / (ab @ ab + EPS), 0, 1)
            d = np.minimum(d, np.hypot(*(xy - (a + t[:, None] * ab)).T))
        return d

    def densified(self, spacing):
        """Contour échantillonné : (points Nx2, normale intérieure Nx2, est_un_sommet N)."""
        pts, nrm, corner = [], [], []
        for r in self.rings:
            nxt = np.roll(r, -1, axis=0)
            d = nxt - r
            ln = np.hypot(d[:, 0], d[:, 1])
            n_left = np.column_stack([-d[:, 1], d[:, 0]]) / ln[:, None]  # matière à gauche
            n_prev = np.roll(n_left, 1, axis=0)
            for i in range(len(r)):
                k = max(1, int(np.ceil(ln[i] / spacing)))
                for j in range(k):
                    pts.append(r[i] + d[i] * j / k)
                    if j == 0:
                        m = n_left[i] + n_prev[i]
                        nrm.append(m / (np.hypot(*m) + EPS))
                        corner.append(True)
                    else:
                        nrm.append(n_left[i])
                        corner.append(False)
        return np.array(pts), np.array(nrm), np.array(corner)


def _triangulate(fp, nodes):
    """Delaunay des nœuds puis suppression des triangles hors emprise (orientés CCW)."""
    tri = Delaunay(nodes).simplices
    cen = nodes[tri].mean(axis=1)
    tri = tri[fp.contains(cen)]
    p = nodes[tri]
    area = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    tri[area < 0] = tri[area < 0][:, [0, 2, 1]]
    return tri[np.abs(area) > 1e-8]


def footprint_mesh(fp, spacing=0.5):
    """Maillage régulier de l'emprise : (nœuds Nx2, triangles, n_contour, normales contour)."""
    bnd, nrm, _ = fp.densified(spacing)
    x0, y0, x1, y1 = fp.bbox
    gx, gy = np.meshgrid(np.arange(x0 + spacing / 2, x1, spacing), np.arange(y0 + spacing / 2, y1, spacing))
    g = np.column_stack([gx.ravel(), gy.ravel()])
    if len(g):
        g = g[fp.contains(g)]
        g = g[fp.boundary_distance(g) > 0.35 * spacing]
    nodes = np.vstack([bnd, g]) if len(g) else bnd
    return nodes, _triangulate(fp, nodes), len(bnd), nrm


# --------------------------------------------------------------------------- nuage

def building_points(fp, pts, min_nz=0.3):
    """Points classés bâtiment dans l'emprise, sans les impacts de façade.

    Retourne (P Nx3, normales Nx3).
    """
    x0, y0, x1, y1 = fp.bbox
    m = (pts[:, 0] >= x0) & (pts[:, 0] <= x1) & (pts[:, 1] >= y0) & (pts[:, 1] <= y1)
    P = pts[m]
    P = P[fp.contains(P[:, :2]), :3]
    if len(P) < 5:
        return P, np.zeros_like(P)
    N = normals(P)
    keep = np.abs(N[:, 2]) >= min_nz
    P, N = P[keep], N[keep]
    keep = upper_envelope(P, N)
    return P[keep], N[keep]


def upper_envelope(P, N, radius=0.8, tol=0.3):
    """Ne garde que la surface la plus haute (élimine balcons, auvents, points sous débords).

    Un point est gardé s'il n'existe pas, dans un rayon horizontal donné, de point plus haut
    que ce que la pente locale peut expliquer.
    """
    if len(P) < 3:
        return np.ones(len(P), bool)
    tree = cKDTree(P[:, :2])
    slope = np.sqrt(np.maximum(1 - N[:, 2] ** 2, 0)) / np.maximum(N[:, 2], 0.2)  # tan(pente)
    zmax = np.array([P[nb, 2].max() for nb in tree.query_ball_point(P[:, :2], radius)])
    return P[:, 2] >= zmax - (radius * slope + tol)


def normals(P, k=10):
    """Normales par ACP locale (k plus proches voisins), orientées vers le haut."""
    k = min(k, len(P))
    _, nn = cKDTree(P).query(P, k=k)
    Q = P[nn] - P[nn].mean(axis=1, keepdims=True)
    _, _, vt = np.linalg.svd(Q, full_matrices=False)
    n = vt[:, 2, :]
    n[n[:, 2] < 0] *= -1
    return n


# --------------------------------------------------------------------------- méthode 1

def roof_lidar(fp, P, spacing=0.5):
    """Toiture = triangulation directe des points (contour calé sur l'emprise)."""
    bnd, _, _ = fp.densified(spacing)
    if len(P) < 3:
        return None
    tree = cKDTree(P[:, :2])
    _, nn = tree.query(bnd, k=min(4, len(P)))
    zb = np.median(P[nn.reshape(len(bnd), -1), 2], axis=1)
    inner = P[fp.boundary_distance(P[:, :2]) > 0.15]
    _, u = np.unique(np.round(inner[:, :2], 2), axis=0, return_index=True)
    inner = inner[np.sort(u)]
    V = np.vstack([np.column_stack([bnd, zb]), inner])
    return V, _triangulate(fp, V[:, :2]), len(bnd)


# --------------------------------------------------------------------------- méthode 2

def bilinear(z, x0, y0, res, xy):
    """Interpolation bilinéaire d'un raster (x0, y0 = centre du pixel [0, 0], ligne 0 au nord)."""
    c = (xy[:, 0] - x0) / res
    r = (y0 - xy[:, 1]) / res
    c = np.clip(c, 0, z.shape[1] - 1.001)
    r = np.clip(r, 0, z.shape[0] - 1.001)
    c0, r0 = np.floor(c).astype(int), np.floor(r).astype(int)
    fc, fr = c - c0, r - r0
    return ((1 - fr) * ((1 - fc) * z[r0, c0] + fc * z[r0, c0 + 1])
            + fr * ((1 - fc) * z[r0 + 1, c0] + fc * z[r0 + 1, c0 + 1]))


def roof_mns(fp, mns, spacing=0.5, inset=0.6):
    """Toiture = maillage régulier drapé sur le MNS (contour lu un peu à l'intérieur)."""
    nodes, tri, nb, nrm = footprint_mesh(fp, spacing)
    q = nodes.copy()
    q[:nb] += nrm * inset
    return np.column_stack([nodes, bilinear(*mns, q)]), tri, nb


# --------------------------------------------------------------------------- méthode 3

def _fit(P):
    c = P.mean(axis=0)
    _, _, vt = np.linalg.svd(P - c, full_matrices=False)
    n = vt[2] if vt[2][2] >= 0 else -vt[2]
    return np.r_[n, -n @ c]


def plane_z(pl, xy):
    return -(pl[3] + pl[0] * xy[..., 0] + pl[1] * xy[..., 1]) / pl[2]


def segment_planes(P, N, dist=0.15, max_angle=25.0, min_area=1.5, iters=250, seed=0):
    """RANSAC séquentiel à échantillonnage local. Retourne (plans Kx4, étiquettes N)."""
    rng = np.random.default_rng(seed)
    n = len(P)
    labels = -np.ones(n, int)
    planes = []
    if n < 10:
        return np.zeros((0, 4)), labels
    tree = cKDTree(P)
    x0, y0 = P[:, :2].min(axis=0)
    x1, y1 = P[:, :2].max(axis=0)
    density = n / max((x1 - x0) * (y1 - y0), 1.0)
    min_pts = max(12, int(min_area * density))
    cos_t = np.cos(np.radians(max_angle))
    remaining = np.ones(n, bool)

    def inliers(pl, mask):
        return mask & (np.abs(P @ pl[:3] + pl[3]) < dist) & (np.abs(N @ pl[:3]) > cos_t)

    while remaining.sum() >= min_pts and len(planes) < 40:
        idx = np.flatnonzero(remaining)
        best, best_cnt = None, 0
        for _ in range(iters):
            s = rng.choice(idx)
            nb = [i for i in tree.query_ball_point(P[s], 2.0) if remaining[i] and i != s]
            if len(nb) < 2:
                continue
            a, b = rng.choice(nb, 2, replace=False)
            nv = np.cross(P[a] - P[s], P[b] - P[s])
            ln = np.linalg.norm(nv)
            if ln < 1e-6:
                continue
            nv /= ln
            if nv[2] < 0:
                nv = -nv
            if nv[2] < 0.4:  # pans de plus de 66° : ignorés
                continue
            pl = np.r_[nv, -nv @ P[s]]
            cnt = inliers(pl, remaining).sum()
            if cnt > best_cnt:
                best, best_cnt = pl, cnt
        if best is None or best_cnt < min_pts:
            break
        for _ in range(2):  # affinage par moindres carrés
            m = inliers(best, remaining)
            if m.sum() < 3:
                break
            best = _fit(P[m])
        m = np.flatnonzero(inliers(best, remaining))
        if len(m) < min_pts:
            if not len(m):
                break
            remaining[m] = False
            continue
        # composante connexe principale (évite de fusionner deux pans disjoints)
        pairs = cKDTree(P[m]).query_pairs(1.0, output_type="ndarray")
        g = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(len(m), len(m)))
        _, cc = connected_components(g, directed=False)
        main = m[cc == np.bincount(cc).argmax()]
        if len(main) < min_pts:
            remaining[m] = False  # trop petit : on l'abandonne
            continue
        pl = _fit(P[main])
        if pl[2] < 0.4:
            remaining[main] = False
            continue
        labels[main] = len(planes)
        planes.append(pl)
        remaining[main] = False
    return np.array(planes).reshape(-1, 4), labels


def merge_planes(planes, labels, P, max_angle=6.0, max_dist=0.2, adj=1.0):
    """Fusionne les pans voisins quasi coplanaires (un même pan découpé par le RANSAC)."""
    planes, labels = list(planes), labels.copy()
    cos_t = np.cos(np.radians(max_angle))
    while True:
        best = None
        ks = [k for k in range(len(planes)) if (labels == k).any()]
        trees = {k: cKDTree(P[labels == k, :2]) for k in ks}
        for ia, a in enumerate(ks):
            for b in ks[ia + 1:]:
                if abs(planes[a][:3] @ planes[b][:3]) < cos_t:
                    continue
                pa, pb = P[labels == a], P[labels == b]
                if not np.isfinite(trees[a].query(pb[:, :2], distance_upper_bound=adj)[0]).any():
                    continue
                d = max(np.mean(np.abs(pb @ planes[a][:3] + planes[a][3])),
                        np.mean(np.abs(pa @ planes[b][:3] + planes[b][3])))
                if d < max_dist and (best is None or d < best[0]):
                    best = (d, a, b)
        if best is None:
            break
        _, a, b = best
        labels[labels == b] = a
        planes[a] = _fit(P[labels == a])
    # renumérotation compacte
    used = sorted(set(labels[labels >= 0].tolist()))
    remap = {k: i for i, k in enumerate(used)}
    labels = np.array([remap.get(l, -1) for l in labels])
    return np.array([planes[k] for k in used]).reshape(-1, 4), labels


def _pair_types(planes, P, labels):
    """Nature de la jonction entre deux pans : 'min' (faîtage), 'max' (noue) ou 'step' (ressaut)."""
    types = {}
    trees = {k: cKDTree(P[labels == k, :2]) for k in range(len(planes))}
    for a in range(len(planes)):
        for b in range(a + 1, len(planes)):
            pa, pb = P[labels == a], P[labels == b]
            da, _ = trees[b].query(pa[:, :2], distance_upper_bound=2.0)
            db, _ = trees[a].query(pb[:, :2], distance_upper_bound=2.0)
            na, nb_ = pa[np.isfinite(da)], pb[np.isfinite(db)]
            if len(na) < 3 or len(nb_) < 3:
                continue
            sa = np.median(plane_z(planes[a], na[:, :2]) - plane_z(planes[b], na[:, :2]))
            sb = np.median(plane_z(planes[b], nb_[:, :2]) - plane_z(planes[a], nb_[:, :2]))
            t = "min" if (sa < -0.05 and sb < -0.05) else "max" if (sa > 0.05 and sb > 0.05) else "step"
            types[(a, b)] = types[(b, a)] = t
    return types


def roof_planes(fp, P, N, spacing=0.5):
    """Toiture plane par morceaux.

    Retourne dict(V, F, face_label, planes, n_pts, n_labeled) ou None.
    face_label : indice du pan, -2 pour les faces de raccord (ressauts).
    """
    planes, labels = segment_planes(P, N)
    if len(planes) == 0:
        return None
    planes, labels = merge_planes(planes, labels, P)
    nodes, tri, nb, _ = footprint_mesh(fp, spacing)
    lp = P[labels >= 0]
    ll = labels[labels >= 0]
    tree = cKDTree(lp[:, :2])
    k = min(7, len(lp))
    d, nn = tree.query(nodes, k=k)
    d, nn = d.reshape(len(nodes), -1), nn.reshape(len(nodes), -1)
    Z = np.array([plane_z(pl, nodes) for pl in planes])  # (K, N)
    # plausibilité locale : un pan prolongé jusqu'au nœud doit rester dans la fourchette
    # d'altitude des points voisins (évite les pans extrapolés loin de leurs points)
    zlo = np.full(len(nodes), P[:, 2].min())
    zhi = np.full(len(nodes), P[:, 2].max())
    for i, nb_ in enumerate(cKDTree(P[:, :2]).query_ball_point(nodes, 2.5)):
        if len(nb_) >= 3:
            zlo[i], zhi[i] = P[nb_, 2].min(), P[nb_, 2].max()
    plausible = (Z >= zlo - 0.5) & (Z <= zhi + 0.5)  # (K, N)
    dist_to = np.array([cKDTree(lp[ll == k, :2]).query(nodes)[0] for k in range(len(planes))])
    lab = np.empty(len(nodes), int)
    for i in range(len(nodes)):
        c = ll[nn[i][d[i] < 1.5]]
        c = c[plausible[c, i]]
        if len(c):
            lab[i] = np.bincount(c).argmax()
        else:  # nœud loin des points : pan plausible le plus proche
            order = np.argsort(dist_to[:, i] + 1e6 * ~plausible[:, i])
            lab[i] = order[0]
    types = _pair_types(planes, P, labels)

    # arêtes du maillage
    E = np.vstack([tri[:, [0, 1]], tri[:, [1, 2]], tri[:, [2, 0]]])
    E = np.unique(np.sort(E, axis=1), axis=0)

    # lissage : un nœud prend l'étiquette majoritaire de ses voisins (supprime les îlots)
    nbrs = [[] for _ in range(len(nodes))]
    for i, j in E:
        nbrs[i].append(j)
        nbrs[j].append(i)
    for _ in range(2):
        new = lab.copy()
        for i in range(len(nodes)):
            c = np.bincount(lab[nbrs[i]], minlength=len(planes))
            if c.max() > len(nbrs[i]) / 2 and c.argmax() != lab[i] and plausible[c.argmax(), i]:
                new[i] = c.argmax()
        lab = new

    # cohérence étiquettes / enveloppe : au faîtage le toit est le pan le plus bas,
    # dans une noue le plus haut
    for _ in range(3):
        changed = 0
        for i, j in E:
            for u, v in ((i, j), (j, i)):
                a, b = lab[u], lab[v]
                t = types.get((a, b))
                if a == b or t is None or t == "step" or not plausible[b, u]:
                    continue
                if (t == "min" and Z[b, u] < Z[a, u] - 0.02) or (t == "max" and Z[b, u] > Z[a, u] + 0.02):
                    lab[u] = b
                    changed += 1
        if not changed:
            break

    step_lines = _straighten_steps(nodes, E, lab, types, plausible)

    # contrôle final : tout nœud resté sur un pan invraisemblable est réaffecté
    for i in np.flatnonzero(~plausible[lab, np.arange(len(nodes))]):
        if plausible[:, i].any():
            lab[i] = np.argsort(dist_to[:, i] + 1e6 * ~plausible[:, i])[0]
        else:
            lab[i] = np.argmin(np.abs(Z[:, i] - np.clip(Z[:, i], zlo[i], zhi[i])))

    V = [np.column_stack([nodes, Z[lab, np.arange(len(nodes))]])]
    nv = len(nodes)
    split = {}  # (i, j) -> liste ordonnée de i vers j de (sommet, étiquette ou None)

    def new_vertex(xy, z):
        nonlocal nv
        V.append(np.array([[xy[0], xy[1], z]]))
        nv += 1
        return nv - 1

    def edge_split(u, v):
        key = (min(u, v), max(u, v))
        if key not in split:
            i, j = key
            a, b = lab[i], lab[j]
            di, dj = Z[a, i] - Z[b, i], Z[a, j] - Z[b, j]
            t = types.get((a, b), "step")
            if t != "step" and di * dj < 0:
                s = np.clip(di / (di - dj), 1e-3, 1 - 1e-3)
                xy = nodes[i] + s * (nodes[j] - nodes[i])
                split[key] = [(new_vertex(xy, plane_z(planes[a], xy)), None)]
            else:
                xy = 0.5 * (nodes[i] + nodes[j])
                line = step_lines.get((min(a, b), max(a, b)))
                if line is not None:  # ressaut redressé : on coupe l'arête sur la droite
                    c, nrm = line
                    si, sj = (nodes[i] - c) @ nrm, (nodes[j] - c) @ nrm
                    if si * sj < 0:
                        xy = nodes[i] + np.clip(si / (si - sj), 0.05, 0.95) * (nodes[j] - nodes[i])
                split[key] = [(new_vertex(xy, plane_z(planes[a], xy)), a),
                              (new_vertex(xy, plane_z(planes[b], xy)), b)]
        s = split[key]
        return s if u < v else s[::-1]

    faces, flabel = [], []

    def emit(poly, label):
        for q in range(1, len(poly) - 1):
            faces.append((poly[0], poly[q], poly[q + 1]))
            flabel.append(label)

    for t in tri:
        L = lab[t]
        if L[0] == L[1] == L[2]:
            faces.append(tuple(t))
            flabel.append(L[0])
            continue
        seq = []  # (sommet, étiquette, est_transition)
        for q in range(3):
            u, v = t[q], t[(q + 1) % 3]
            seq.append((u, lab[u], False))
            if lab[u] != lab[v]:
                seq += [(w, l, True) for w, l in edge_split(u, v)]
        n = len(seq)
        for X in np.unique(L):
            poly = []
            for q, (w, l, _) in enumerate(seq):
                if l == X:
                    poly.append(w)
                elif l is None and X in (seq[q - 1][1], seq[(q + 1) % n][1]):
                    poly.append(w)
            if len(poly) >= 3:
                emit(poly, X)
        center = [w for w, _, tr in seq if tr]
        if len(set(center)) >= 3:
            emit(center, -2)

    V = np.vstack(V)
    F = np.array(faces, int)
    FL = np.array(flabel, int)
    # élimine les faces dégénérées
    p = V[F]
    ar = np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1)
    ok = ar > 1e-8
    return dict(V=V, F=F[ok], face_label=FL[ok], planes=planes, node_label=lab, nodes=nodes,
                n_pts=len(P), n_labeled=int((labels >= 0).sum()))


def _straighten_steps(nodes, E, lab, types, plausible, max_rms=0.4, band=1.5):
    """Redresse les frontières de ressaut entre deux pans lorsqu'elles sont proches d'une droite.

    Modifie `lab` en place. Retourne {(a, b): (point, normale)} pour les frontières redressées.
    """
    lines = {}
    la, lb = lab[E[:, 0]], lab[E[:, 1]]
    pairs = {(min(a, b), max(a, b)) for a, b in zip(la, lb) if a != b}
    for a, b in pairs:
        if types.get((a, b), "step") != "step":
            continue
        m = ((la == a) & (lb == b)) | ((la == b) & (lb == a))
        if m.sum() < 4:
            continue
        M = 0.5 * (nodes[E[m, 0]] + nodes[E[m, 1]])
        c = M.mean(axis=0)
        w, v = np.linalg.eigh(np.cov((M - c).T))
        u, nrm = v[:, 1], v[:, 0]
        if np.sqrt(w[0]) > max_rms:
            continue
        t = (M - c) @ u
        sel = np.flatnonzero(np.isin(lab, (a, b)))
        q = nodes[sel] - c
        tn, dn = q @ u, q @ nrm
        zone = (np.abs(dn) < band) & (tn > t.min() - 0.5) & (tn < t.max() + 0.5)
        side_a = np.sign(np.sum(np.sign(dn[zone & (lab[sel] == a)])))
        if side_a == 0:
            continue
        new = np.where(np.sign(dn[zone]) == side_a, a, b)
        ok = plausible[new, sel[zone]]
        lab[sel[zone][ok]] = new[ok]
        lines[(a, b)] = (c, nrm)
    return lines


# --------------------------------------------------------------------------- utilitaires

def boundary_loops(F):
    """Boucles de bord orientées d'un maillage triangulaire (listes d'indices)."""
    E = np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    key = np.sort(E, axis=1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    B = E[cnt[inv.ravel()] == 1]
    nxt = {int(a): int(b) for a, b in B}
    loops, seen = [], set()
    for s in list(nxt):
        if s in seen:
            continue
        loop, v = [], s
        while v not in seen and v in nxt:
            seen.add(v)
            loop.append(v)
            v = nxt[v]
        if len(loop) >= 3:
            loops.append(loop)
    return loops


def ground_z(fp, mnt, spacing=1.0):
    """Altitude minimale du terrain le long de l'emprise."""
    b, _, _ = fp.densified(spacing)
    return float(np.nanmin(bilinear(*mnt, b)))
