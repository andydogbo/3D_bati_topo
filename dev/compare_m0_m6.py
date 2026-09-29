"""Compare M0 (extrusion BD TOPO) et M6 dans un .3dm : couverture, hauteurs, objets en plus/en moins."""
import os, sys, json
sys.path.insert(0, "dev"); sys.path.insert(0, "src")
import rhinoinside
rhinoinside.load(r"C:\Program Files\Rhino 8\System", "net8.0")
import Rhino, numpy as np
import Rhino.Geometry as rg
import zone, rhino_build as rb

Z = zone.load(extra=60)
doc = Rhino.RhinoDoc.OpenHeadless(os.path.abspath(sys.argv[1]))
def objs(layer):
    L = doc.Layers.FindName(layer)
    return list(doc.Objects.FindByLayer(L)) if L else []
def to_mesh(g):
    m = rg.Mesh()
    if isinstance(g, rg.Brep):
        for x in rg.Mesh.CreateFromBrep(g, rg.MeshingParameters.FastRenderMesh): m.Append(x)
    elif isinstance(g, rg.Extrusion):
        for x in rg.Mesh.CreateFromBrep(g.ToBrep(), rg.MeshingParameters.FastRenderMesh): m.Append(x)
    else: m.Append(g)
    return m
m6 = objs("M6 Murs BD TOPO + toiture LiDAR")
m0 = objs("M0 Extrusion BD TOPO")
print("objets : M0 = %d, M6 = %d" % (len(m0), len(m6)))
by_cle = {}
orph = []
for o in m6:
    c = o.Attributes.GetUserString("cleabs")
    st = o.Attributes.GetUserString("statut")
    (by_cle.setdefault(c, []) if c else orph).append((o, st))
M6all = rg.Mesh()
for o in m6: M6all.Append(to_mesh(o.Geometry))
M0all = rg.Mesh()
for o in m0: M0all.Append(to_mesh(o.Geometry))
rows = []
for props, fp in Z["blds"]:
    c = props["cleabs"]
    x0, y0, x1, y1 = fp.bbox
    gx, gy = np.meshgrid(np.arange(x0 + .25, x1, .5), np.arange(y0 + .25, y1, .5))
    G = np.column_stack([gx.ravel(), gy.ravel()]); G = G[fp.contains(G)]
    G = G[fp.boundary_distance(G) > 0.3]
    if not len(G): continue
    z6 = rb.top_z(M6all, G); z0 = rb.top_z(M0all, G)
    cov = np.isfinite(z6).mean()
    dz = np.nanmedian(z6 - z0) if np.isfinite(z6).any() else np.nan
    sts = sorted({s for _, s in by_cle.get(c, [])}) or ["absent de M6"]
    rows.append((c, fp.area, cov, dz, props["hauteur"], ",".join(sts)))
rows.sort(key=lambda r: r[2])
print("\nemprises BD TOPO du cercle : %d" % len(rows))
print("couverture de l'emprise par M6 : médiane %.0f%% | < 90%% : %d bât. | < 50%% : %d bât. | 0%% : %d bât."
      % (100 * np.median([r[2] for r in rows]), sum(r[2] < .9 for r in rows), sum(r[2] < .5 for r in rows), sum(r[2] == 0 for r in rows)))
print("\nbâtiments les moins couverts par M6 :")
for c, a, cov, dz, h, st in rows[:14]:
    print("  %s  aire %6.1f m²  couverte %3.0f%%  h BDTOPO %5s  toit M6 - M0 %6s m  | %s" % (c[-9:], a, 100 * cov, h, "%.1f" % dz if np.isfinite(dz) else "-", st))
dzs = np.array([r[3] for r in rows if np.isfinite(r[3])])
print("\ntoit M6 - toit M0 (médiane par bâtiment) : médiane %.1f m, 10e %.1f, 90e %.1f" % (np.median(dzs), np.percentile(dzs, 10), np.percentile(dzs, 90)))
areas = []
for o, st in orph:
    bb = o.Geometry.GetBoundingBox(True)
    areas.append(((bb.Max.X - bb.Min.X) * (bb.Max.Y - bb.Min.Y), bb.Max.Z - bb.Min.Z))
areas = np.array(areas) if areas else np.zeros((0, 2))
print("\nobjets M6 sans bâtiment BD TOPO : %d (emprise bbox médiane %.0f m², hauteur médiane %.1f m)" % (len(orph), np.median(areas[:, 0]) if len(areas) else 0, np.median(areas[:, 1]) if len(areas) else 0))
st_all = {}
for o in m6:
    s = o.Attributes.GetUserString("statut"); st_all[s] = st_all.get(s, 0) + 1
print("statuts M6 :", st_all)
sys.stdout.flush(); os._exit(0)
