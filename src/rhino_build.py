"""Conversion des résultats numpy (roofs.py) en géométrie RhinoCommon.

Fonctionne dans Rhino 8 (composant Python 3 de Grasshopper) comme en headless (rhinoinside).
"""
import numpy as np
import Rhino.Geometry as rg
from System.Collections.Generic import List

import roofs

TOL = 0.001
ANG_TOL = 0.01


def net_list(items, T):
    """Liste Python -> List<T> .NET (pythonnet 3 ne convertit pas implicitement)."""
    out = List[T]()
    for x in items:
        out.Add(x)
    return out


def mesh(V, F):
    m = rg.Mesh()
    m.Vertices.AddVertices(net_list([rg.Point3d(float(x), float(y), float(z)) for x, y, z in V], rg.Point3d))
    for a, b, c in F:
        m.Faces.AddFace(int(a), int(b), int(c))
    m.Normals.ComputeNormals()
    m.Compact()
    return m


def closed_mesh(V, F, zbase):
    """Maillage fermé : toiture + murs verticaux jusqu'à zbase + fond."""
    V = np.asarray(V, float)
    F = [tuple(f) for f in F]
    base = {}
    extra = []
    for loop in roofs.boundary_loops(np.asarray(F)):
        for u in loop:
            if u not in base:
                base[u] = len(V) + len(extra)
                extra.append((V[u, 0], V[u, 1], zbase))
        for u, v in zip(loop, loop[1:] + loop[:1]):
            F += [(v, u, base[u]), (v, base[u], base[v])]
    m = mesh(np.vstack([V, extra]) if extra else V, F)
    m.FillHoles()
    m.UnifyNormals()
    if m.IsClosed and m.Volume() < 0:
        m.Flip(True, True, True)
    m.Normals.ComputeNormals()
    return m


def _rings_curves(fp, z, origin=(0.0, 0.0)):
    return [rg.PolylineCurve(net_list([rg.Point3d(float(x), float(y), float(z)) for x, y in np.vstack([r, r[:1]])], rg.Point3d))
            for r in fp.rings]


def footprint_curves(fp, z):
    return _rings_curves(fp, z)


def extrusion(fp, zbase, height):
    """Emprise extrudée (méthode BD TOPO classique)."""
    faces = rg.Brep.CreatePlanarBreps(net_list(_rings_curves(fp, zbase), rg.Curve), TOL)
    if not faces:
        return None
    path = rg.LineCurve(rg.Point3d(0, 0, zbase), rg.Point3d(0, 0, zbase + height))
    b = faces[0].Faces[0].CreateExtrusion(path, True)
    if b is not None and b.SolidOrientation == rg.BrepSolidOrientation.Inward:
        b.Flip()
    return b


def _wall_polygons(fp, V, F, zbase):
    """Murs : un polygone plan par côté d'emprise (inclut les ressauts verticaux du toit)."""
    corners = np.vstack(fp.rings)
    walls = []
    for loop in roofs.boundary_loops(F):
        xy = V[loop, :2]
        d = np.min(np.hypot(xy[:, None, 0] - corners[None, :, 0], xy[:, None, 1] - corners[None, :, 1]), axis=1)
        cidx = [k for k in range(len(loop)) if d[k] < 1e-6]
        if len(cidx) < 2:  # repli : un quadrilatère par arête
            cidx = list(range(len(loop)))
        for a, b in zip(cidx, cidx[1:] + cidx[:1]):
            chain = [loop[k % len(loop)] for k in range(a, b + (len(loop) if b <= a else 0) + 1)]
            top = [rg.Point3d(*map(float, V[k])) for k in chain]
            pts = top + [rg.Point3d(top[-1].X, top[-1].Y, zbase), rg.Point3d(top[0].X, top[0].Y, zbase), top[0]]
            walls.append(rg.PolylineCurve(net_list(pts, rg.Point3d)))
    return walls


def _polyline(V, loop):
    pts = [rg.Point3d(*map(float, V[k])) for k in loop]
    return rg.PolylineCurve(net_list(pts + pts[:1], rg.Point3d))


def roof_faces(V, F, face_label):
    """Une face plane (éventuellement trouée) par pan, plus les faces de raccord."""
    parts = []
    for k in np.unique(face_label):
        sub = F[face_label == k]
        if k < 0:  # raccords : petits polygones plans, un par triangle
            for f in sub:
                b = rg.Brep.CreateFromCornerPoints(*[rg.Point3d(*map(float, V[i])) for i in f], TOL)
                if b:
                    parts.append(b)
            continue
        curves = [_polyline(V, loop) for loop in roofs.boundary_loops(sub)]
        b = rg.Brep.CreatePlanarBreps(net_list(curves, rg.Curve), TOL)
        if b:
            parts += list(b)
        else:  # repli : triangles
            parts += [rg.Brep.CreateFromCornerPoints(*[rg.Point3d(*map(float, V[i])) for i in f], TOL) for f in sub]
    return [p for p in parts if p is not None]


def planar_solid(fp, V, F, zbase, face_label=None):
    """Polysurface fermée à faces planes (méthode des pans). Retourne (brep, est_solide)."""
    if face_label is None:
        roof = rg.Brep.CreateFromMesh(mesh(V, F), True)
        roof.MergeCoplanarFaces(TOL, ANG_TOL)
        parts = [roof]
    else:
        parts = roof_faces(V, F, face_label)
        roof = parts[0]
    for c in _wall_polygons(fp, V, F, zbase):
        b = rg.Brep.CreatePlanarBreps(c, TOL)
        if b:
            parts += list(b)
    bottom = rg.Brep.CreatePlanarBreps(net_list(_rings_curves(fp, zbase), rg.Curve), TOL)
    if bottom:
        parts += list(bottom)
    joined = rg.Brep.JoinBreps(net_list(parts, rg.Brep), TOL)
    if joined is None or len(joined) == 0:
        return roof, False
    b = max(joined, key=lambda x: x.Faces.Count)
    b.MergeCoplanarFaces(TOL, ANG_TOL)
    b.Edges.MergeAllEdges(ANG_TOL)
    if b.IsSolid and b.SolidOrientation == rg.BrepSolidOrientation.Inward:
        b.Flip()
    return b, bool(b.IsSolid and len(joined) == 1)


def terrain_mesh(mnt, center, radius, step=2):
    """Maillage du MNT (1 pixel sur `step`) limité au disque (center, radius)."""
    z, x0, y0, res = mnt
    zs = z[::step, ::step]
    h, w = zs.shape
    xs = x0 + np.arange(w) * res * step
    ys = y0 - np.arange(h) * res * step
    X, Y = np.meshgrid(xs, ys)
    inside = np.hypot(X - center[0], Y - center[1]) <= radius + res * step
    idx = -np.ones((h, w), int)
    idx[inside] = np.arange(inside.sum())
    m = rg.Mesh()
    m.Vertices.AddVertices(net_list([rg.Point3d(float(x), float(y), float(zz))
                                      for x, y, zz in zip(X[inside], Y[inside], zs[inside])], rg.Point3d))
    for i in range(h - 1):
        for j in range(w - 1):
            a, b, c, d = idx[i, j], idx[i, j + 1], idx[i + 1, j + 1], idx[i + 1, j]
            if min(a, b, c, d) >= 0:
                m.Faces.AddFace(int(a), int(d), int(c), int(b))
    m.Normals.ComputeNormals()
    m.Compact()
    return m


def point_cloud(P, colors=None):
    pc = rg.PointCloud()
    pc.AddRange(net_list([rg.Point3d(float(x), float(y), float(z)) for x, y, z in P[:, :3]], rg.Point3d))
    return pc


def brep_from_surfaces(surfaces, tol=0.01):
    """Polysurface depuis des faces CityJSON [(type, [anneaux Nx3])]. Retourne (brep, fermé, nb_faces)."""
    parts = []
    for _, rings in surfaces:
        curves = [rg.PolylineCurve(net_list([rg.Point3d(*map(float, p)) for p in np.vstack([r, r[:1]])], rg.Point3d))
                  for r in rings]
        b = rg.Brep.CreatePlanarBreps(net_list(curves, rg.Curve), tol)
        if b:
            parts += list(b)
        else:  # face légèrement gauche (arrondi au mm) : maillée
            m = rg.Mesh.CreateFromClosedPolyline(curves[0].ToPolyline())
            if m:
                parts.append(rg.Brep.CreateFromMesh(m, True))
    parts = [p for p in parts if p is not None]
    if not parts:
        return None, False, 0
    joined = rg.Brep.JoinBreps(net_list(parts, rg.Brep), tol)
    b = max(joined, key=lambda x: x.Faces.Count)
    if not (b.IsSolid and len(joined) == 1):
        # jonctions en T / faces gauches : on passe par un maillage soudé et cicatrisé
        m = _healed_mesh(surfaces)
        if m.IsClosed:
            bm = rg.Brep.CreateFromMesh(m, True)
            if bm is not None:
                bm.MergeCoplanarFaces(tol, 0.02)
                if bm.IsSolid:
                    b, joined = bm, [bm]
                else:  # maillage fermé : on le garde tel quel
                    if m.Volume() < 0:
                        m.Flip(True, True, True)
                    return m, True, len(surfaces)
    _orient(b)
    return b, bool(b.IsSolid and len(joined) == 1), len(surfaces)


def _healed_mesh(surfaces):
    m = rg.Mesh()
    for _, rings in surfaces:
        pls = [rg.Polyline(net_list([rg.Point3d(*map(float, p)) for p in np.vstack([r, r[:1]])], rg.Point3d))
               for r in rings]
        f = rg.Mesh.CreateFromClosedPolyline(pls[0]) if len(pls) == 1 else None
        if f is None:  # face trouée
            bs = rg.Brep.CreatePlanarBreps(net_list([p.ToPolylineCurve() for p in pls], rg.Curve), 0.05)
            f = rg.Mesh()
            for bb in (bs or []):
                for x in rg.Mesh.CreateFromBrep(bb, rg.MeshingParameters.QualityRenderMesh):
                    f.Append(x)
        m.Append(f)
    m.Vertices.CombineIdentical(True, True)
    m.Weld(np.pi)
    m.HealNakedEdges(0.02)
    m.Vertices.CombineIdentical(True, True)
    m.UnifyNormals()
    m.Normals.ComputeNormals()
    return m


def top_z(geom, P):
    """Altitude de la surface la plus haute du modèle à l'aplomb de chaque point (NaN si aucune)."""
    if isinstance(geom, rg.Brep):
        ms = rg.Mesh.CreateFromBrep(geom, rg.MeshingParameters.FastRenderMesh)
        m = rg.Mesh()
        for x in ms:
            m.Append(x)
    else:
        m = geom
    zt = m.GetBoundingBox(True).Max.Z + 5.0
    out = np.full(len(P), np.nan)
    down = rg.Vector3d(0, 0, -1)
    for k, (x, y) in enumerate(P[:, :2]):
        t = rg.Intersect.Intersection.MeshRay(m, rg.Ray3d(rg.Point3d(float(x), float(y), zt), down))
        if t >= 0:
            out[k] = zt - t
    return out


def _volume(b):
    vm = rg.VolumeMassProperties.Compute(b)
    return vm.Volume if vm is not None else 0.0


def _orient(b):
    """Oriente un solide vers l'extérieur (d'après le signe du volume, plus fiable que SolidOrientation)."""
    if b is not None and b.IsSolid and _volume(b) < 0:
        b.Flip()
    return b


def _as_brep(g):
    if isinstance(g, rg.Mesh):
        return rg.Brep.CreateFromMesh(g, True)
    return g


def body_on_footprint(solid, fp, tol=0.01):
    """Corps du bâtiment : solide LiDAR ∩ prisme de l'emprise BD TOPO (murs sur la façade réelle)."""
    S = _orient(_as_brep(solid))
    if S is None or not S.IsSolid:
        return None
    bb = S.GetBoundingBox(True)
    vS = _volume(S)
    for t, grow in ((tol, 0.0), (0.001, 0.0), (tol, 0.002), (tol, -0.002)):
        fpx = fp if grow == 0 else roofs.Footprint([r + grow * _outward(r) for r in fp.rings])
        F = extrusion(fpx, bb.Min.Z - 1.0, bb.Max.Z - bb.Min.Z + 2.0)
        body = rg.Brep.CreateBooleanIntersection(S, F, t) if F is not None else None
        if body and all(b.IsSolid for b in body):
            out = [_orient(b) for b in body]
            vb = sum(_volume(b) for b in out)
            zmax = max(b.GetBoundingBox(True).Max.Z for b in out)
            # garde-fou : un booléen « réussi » peut rendre un volume faux
            if 0 < vb <= min(vS, _volume(F)) * 1.001 + 0.1 and zmax <= bb.Max.Z + 0.05:
                for b in out:
                    b.MergeCoplanarFaces(t, 0.02)
                return out
    return None


def overhang_plates(surfaces, fp, eave=0.25, tol=0.01, min_area=0.05):
    """Débords : parties des pans de toit hors de l'emprise, extrudées en plaques d'épaisseur `eave`."""
    def flat(pts):
        return rg.PolylineCurve(net_list([rg.Point3d(float(x), float(y), 0.0) for x, y in pts] +
                                         [rg.Point3d(float(pts[0][0]), float(pts[0][1]), 0.0)], rg.Point3d))
    ext = flat(fp.rings[0])
    holes = [flat(r) for r in fp.rings[1:]]
    down = rg.LineCurve(rg.Point3d(0, 0, 0), rg.Point3d(0, 0, -eave))
    plates = []
    for kind, rings in surfaces:
        if kind != "RoofSurface":
            continue
        P = np.asarray(rings[0], float)
        c = P.mean(axis=0)
        n = np.linalg.svd(P - c)[2][2]
        if abs(n[2]) < 0.05:
            continue
        roof = flat(P[:, :2])
        roof_area = abs(roofs._signed_area(P[:, :2]))
        pieces = list(rg.Curve.CreateBooleanDifference(roof, ext, tol) or [])
        for h in holes:  # débord au-dessus d'une cour intérieure
            pieces += list(rg.Curve.CreateBooleanIntersection(roof, h, tol) or [])
        for pc in pieces:
            ok, pl = pc.TryGetPolyline()
            if not ok:
                pl = pc.ToPolyline(tol, 0.01, 0.01, 1000).ToPolyline()
            pts3 = [rg.Point3d(q.X, q.Y, float(c[2] - (n[0] * (q.X - c[0]) + n[1] * (q.Y - c[1])) / n[2])) for q in pl]
            crv = rg.PolylineCurve(net_list(pts3, rg.Point3d))
            face = rg.Brep.CreatePlanarBreps(crv, tol)
            if not face:
                continue
            f = face[0]
            amp = rg.AreaMassProperties.Compute(f)
            if amp is None or amp.Area < min_area or amp.Area > roof_area * 1.01:
                continue
            # la plaque doit être hors de l'emprise (ou au-dessus d'une cour)
            mesh = rg.Mesh.CreateFromBrep(f, rg.MeshingParameters.FastRenderMesh)
            pts = np.array([[v.X, v.Y] for m_ in mesh for v in m_.Vertices]) if mesh else np.zeros((0, 2))
            if len(pts):
                q = np.array([[m_.Faces.GetFaceCenter(j).X, m_.Faces.GetFaceCenter(j).Y]
                              for m_ in mesh for j in range(m_.Faces.Count)])
                if fp.contains(q).mean() > 0.5 and not holes:
                    continue
            b = f.Faces[0].CreateExtrusion(down, True)
            if b is not None:
                if b.SolidOrientation == rg.BrepSolidOrientation.Inward:
                    b.Flip()
                plates.append(b)
    return plates


def walls_on_footprint(solid, surfaces, fp, fallback_body=None, eave=0.25):
    """Murs sur l'emprise BD TOPO + toiture LiDAR avec débords.

    Retourne (liste de géométries, statut). Le corps vient de solide ∩ emprise ; à défaut,
    de `fallback_body` (roofer lancé directement sur l'emprise BD TOPO).
    """
    body = body_on_footprint(solid, fp)
    status = "ok"
    if body is None:
        if fallback_body is None:
            return [solid], "repli M5b"
        body, status = [fallback_body], "corps M4"
    return body + overhang_plates(surfaces, fp, eave), status


def _outward(ring):
    """Normales extérieures (moyennées aux sommets) d'un anneau orienté matière à gauche."""
    d = np.roll(ring, -1, axis=0) - ring
    n = np.column_stack([d[:, 1], -d[:, 0]]) / (np.hypot(d[:, 0], d[:, 1])[:, None] + 1e-12)
    m = n + np.roll(n, 1, axis=0)
    return m / (np.hypot(m[:, 0], m[:, 1])[:, None] + 1e-12)


def terrain_mesh_tri(mnt, center, radius, step=2):
    """MNT triangulé : chaque maille est coupée selon la diagonale la plus fidèle au MNT.

    Avec step=2, le centre de chaque maille tombe exactement sur un pixel du MNT 50 cm ;
    on choisit la diagonale dont le milieu est le plus proche de cette altitude réelle.
    """
    z, x0, y0, res = mnt
    zs = z[::step, ::step]
    h, w = zs.shape
    xs = x0 + np.arange(w) * res * step
    ys = y0 - np.arange(h) * res * step
    X, Y = np.meshgrid(xs, ys)
    inside = np.hypot(X - center[0], Y - center[1]) <= radius + res * step
    idx = -np.ones((h, w), int)
    idx[inside] = np.arange(inside.sum())
    m = rg.Mesh()
    m.Vertices.AddVertices(net_list([rg.Point3d(float(x), float(y), float(zz))
                                      for x, y, zz in zip(X[inside], Y[inside], zs[inside])], rg.Point3d))
    half = step // 2
    for i in range(h - 1):
        for j in range(w - 1):
            a, b, c, d = idx[i, j], idx[i, j + 1], idx[i + 1, j + 1], idx[i + 1, j]
            if min(a, b, c, d) < 0:
                continue
            ci, cj = i * step + half, j * step + half
            zc = z[ci, cj] if (step % 2 == 0 and ci < z.shape[0] and cj < z.shape[1]) else None
            e_ac = abs(0.5 * (zs[i, j] + zs[i + 1, j + 1]) - zc) if zc is not None else 0
            e_bd = abs(0.5 * (zs[i, j + 1] + zs[i + 1, j]) - zc) if zc is not None else 1
            if e_ac <= e_bd:  # diagonale a-c
                m.Faces.AddFace(int(a), int(d), int(c))
                m.Faces.AddFace(int(a), int(c), int(b))
            else:  # diagonale b-d
                m.Faces.AddFace(int(a), int(d), int(b))
                m.Faces.AddFace(int(d), int(c), int(b))
    m.Normals.ComputeNormals()
    m.Compact()
    return m


def quad_remesh(mesh, target=60000):
    """Remaillage en quadrangles (QuadRemesh de Rhino), adapté à la courbure."""
    p = rg.QuadRemeshParameters()
    p.TargetQuadCount = target
    p.AdaptiveSize = 50
    p.AdaptiveQuadCount = True
    p.DetectHardEdges = True
    q = mesh.QuadRemesh(p)
    if q is not None:
        q.Normals.ComputeNormals()
    return q


def drape_texture(mesh, bbox_local):
    """Coordonnées de texture (u, v) planes : l'image couvre exactement bbox_local (xmin, ymin, xmax, ymax)."""
    x0, y0, x1, y1 = bbox_local
    mesh.TextureCoordinates.Clear()
    for i in range(mesh.Vertices.Count):
        v = mesh.Vertices[i]
        mesh.TextureCoordinates.Add((v.X - x0) / (x1 - x0), (v.Y - y0) / (y1 - y0))
    return mesh


def texture_material(doc, name, image_path):
    """Matériau de rendu Rhino avec l'image en texture de couleur. Retourne le RenderMaterial."""
    import Rhino
    mat = Rhino.DocObjects.Material()
    mat.Name = name
    mat.DiffuseColor = __import__("System").Drawing.Color.White
    mat.SetBitmapTexture(image_path)
    rm = Rhino.Render.RenderMaterial.CreateBasicMaterial(mat, doc)
    rm.Name = name
    doc.RenderMaterials.Add(rm)
    return rm


def tree_meshes(tree, crown="ellipsoid", u=16, v=10):
    """Arbre simplifié : tronc (cylindre) + houppier (ellipsoïde aux dimensions mesurées,
    ou enveloppe convexe des points LiDAR si crown='hull'). Retourne un maillage unique."""
    import vegetation
    x, y, zg, h, r, base = tree["x"], tree["y"], tree["z_sol"], tree["hauteur"], tree["rayon"], tree["base"]
    m = rg.Mesh()
    rt = max(0.1, 0.012 * h + 0.05)
    cyl = rg.Cylinder(rg.Circle(rg.Plane(rg.Point3d(x, y, zg - 0.3), rg.Vector3d.ZAxis), rt), base + 0.3 + 0.3 * (h - base))
    m.Append(rg.Mesh.CreateFromCylinder(cyl, 1, 8))
    if crown == "hull":
        hull = vegetation.crown_hull(tree["points"])
        if hull is not None:
            m.Append(mesh(*hull))
            m.Normals.ComputeNormals()
            return m
    rz = (h - base) / 2.0
    sph = rg.Mesh.CreateFromSphere(rg.Sphere(rg.Point3d.Origin, 1.0), u, v)
    sph.Transform(rg.Transform.Scale(rg.Plane.WorldXY, r, r, rz))
    sph.Translate(rg.Vector3d(x, y, zg + base + rz))
    m.Append(sph)
    m.Normals.ComputeNormals()
    return m


# ---------------------------------------------------------------------------------------------
# Végétation : arbres types en blocs, masses végétales

TREE_COLORS = {"feuillu": (96, 138, 70), "conifere": (52, 96, 62), "fastigie": (84, 124, 64)}
TRUNK_COLOR = (105, 82, 60)


def _lowpoly(m, rng, jitter=0.04):
    """Facettes franches (style maquette) et léger bruit sur les sommets."""
    for i in range(m.Vertices.Count):
        v = m.Vertices[i]
        m.Vertices.SetVertex(i, v.X * (1 + rng.uniform(-jitter, jitter)), v.Y * (1 + rng.uniform(-jitter, jitter)),
                             v.Z + rng.uniform(-jitter, jitter) * 0.5)
    m.Unweld(0, True)
    m.Normals.ComputeNormals()
    return m


def _ellipsoid(c, rx, ry, rz, u=9, v=6):
    s = rg.Mesh.CreateFromSphere(rg.Sphere(rg.Point3d.Origin, 1.0), u, v)
    s.Transform(rg.Transform.Scale(rg.Plane.WorldXY, rx, ry, rz))
    s.Translate(rg.Vector3d(*c))
    return s


def _cone(apex_z, h, r, n=9):
    pl = rg.Plane(rg.Point3d(0, 0, apex_z), -rg.Vector3d.ZAxis)
    return rg.Mesh.CreateFromCone(rg.Cone(pl, h, r), 1, n, True)


def tree_prototypes(seed=7):
    """Prototypes normalisés (hauteur totale 1, diamètre de couronne 1, pied du tronc à l'origine).
    Retourne {type: (maillage houppier, maillage tronc)}."""
    rng = np.random.default_rng(seed)
    out = {}
    # feuillu : houppier en nuage de lobes
    crown = rg.Mesh()
    crown.Append(_ellipsoid((0, 0, 0.62), 0.34, 0.34, 0.28))
    for k in range(6):
        a = np.radians(60 * k + rng.uniform(-15, 15))
        r = rng.uniform(0.2, 0.24)
        d = 0.5 - r
        crown.Append(_ellipsoid((d * np.cos(a), d * np.sin(a), rng.uniform(0.5, 0.64)), r, r, r * 0.9))
    crown.Append(_ellipsoid((0, 0, 0.8), 0.22, 0.22, 0.2))
    out["feuillu"] = (_lowpoly(crown, rng), rg.Mesh.CreateFromCylinder(
        rg.Cylinder(rg.Circle(rg.Plane.WorldXY, 0.03), 0.5), 1, 7))
    # conifère : étages de cônes
    crown = rg.Mesh()
    for i in range(4):
        base = 0.1 + 0.2 * i
        crown.Append(_cone(base + 0.3, 0.3 + (0.08 if i < 3 else 0.0), 0.5 * (1 - 0.22 * i)))
    out["conifere"] = (_lowpoly(crown, rng, 0.02), rg.Mesh.CreateFromCylinder(
        rg.Cylinder(rg.Circle(rg.Plane.WorldXY, 0.035), 0.25), 1, 7))
    # fastigié : fuseau
    crown = rg.Mesh()
    crown.Append(_ellipsoid((0, 0, 0.5), 0.5, 0.5, 0.38))
    crown.Append(_ellipsoid((0, 0, 0.78), 0.34, 0.34, 0.22))
    out["fastigie"] = (_lowpoly(crown, rng), rg.Mesh.CreateFromCylinder(
        rg.Cylinder(rg.Circle(rg.Plane.WorldXY, 0.04), 0.2), 1, 7))
    return out


def tree_block_definitions(doc, layer_index):
    """Crée les définitions de blocs « Arbre - feuillu / conifere / fastigie ». Retourne {type: index}."""
    import System
    import Rhino
    defs = {}
    for kind, (crown, trunk) in tree_prototypes().items():
        geos, attrs = [], []
        for g, col in ((crown, TREE_COLORS[kind]), (trunk, TRUNK_COLOR)):
            a = Rhino.DocObjects.ObjectAttributes()
            a.LayerIndex = layer_index
            a.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
            a.ObjectColor = System.Drawing.Color.FromArgb(*col)
            mat = Rhino.DocObjects.Material()
            mat.DiffuseColor = a.ObjectColor
            mat.Name = "Vegetation %s" % ("tronc" if g is trunk else kind)
            a.MaterialIndex = doc.Materials.Add(mat)
            a.MaterialSource = Rhino.DocObjects.ObjectMaterialSource.MaterialFromObject
            geos.append(g)
            attrs.append(a)
        name = "Arbre - %s" % kind
        idx = doc.InstanceDefinitions.Add(name, "Prototype normalisé : hauteur 1, diamètre de couronne 1. "
                                          "Remplacez sa géométrie par votre propre modèle.",
                                          rg.Point3d.Origin, net_list(geos, rg.GeometryBase),
                                          net_list(attrs, Rhino.DocObjects.ObjectAttributes))
        defs[kind] = idx
    return defs


def tree_transform(tree, angle):
    """Mise à l'échelle (diamètre, diamètre, hauteur), rotation autour de Z, pose au pied de l'arbre."""
    d = 2 * tree["rayon"]
    xf = rg.Transform.Translation(tree["x"], tree["y"], tree["z_sol"])
    xf = xf * rg.Transform.Rotation(angle, rg.Vector3d.ZAxis, rg.Point3d.Origin)
    xf = xf * rg.Transform.Scale(rg.Plane.WorldXY, d, d, tree["hauteur"])
    return xf
