import os, sys
sys.path.insert(0, "dev"); sys.path.insert(0, "src")
import rhinoinside
rhinoinside.load(r"C:\Program Files\Rhino 8\System", "net8.0")
import Rhino, numpy as np
import Rhino.Geometry as rg
import zone, roofer_io, rhino_build as rb
Z = zone.load()
res4 = roofer_io.read_cjseq("data/roofer_out", Z["origin"])
def via_mesh(surfaces):
    m = rg.Mesh()
    for _, rings in surfaces:
        crv = [rg.Polyline(rb.net_list([rg.Point3d(*map(float, p)) for p in np.vstack([r, r[:1]])], rg.Point3d)) for r in rings]
        f = rg.Mesh.CreateFromClosedPolyline(crv[0]) if len(crv) == 1 else None
        if f is None:
            bs = rg.Brep.CreatePlanarBreps(rb.net_list([c.ToPolylineCurve() for c in crv], rg.Curve), 0.05)
            f = rg.Mesh()
            for b in (bs or []):
                for x in rg.Mesh.CreateFromBrep(b, rg.MeshingParameters.QualityRenderMesh): f.Append(x)
        m.Append(f)
    m.Vertices.CombineIdentical(True, True)
    m.Weld(np.pi)
    m.HealNakedEdges(0.02)
    m.Vertices.CombineIdentical(True, True)
    m.UnifyNormals()
    return m
for i in (8, 27, 29, 31, 32, 33, 37, 44, 63):
    m = via_mesh(res4[i]["surfaces"])
    b = rg.Brep.CreateFromMesh(m, True)
    ok = b.MergeCoplanarFaces(0.01, 0.02) if b else False
    print(i, "maillage fermé:", m.IsClosed, "| brep solide:", b.IsSolid if b else None, "faces", b.Faces.Count if b else 0)
sys.stdout.flush(); os._exit(0)
