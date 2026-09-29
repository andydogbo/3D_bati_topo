import os, sys, time
import rhinoinside
rhinoinside.load(r"C:\Program Files\Rhino 8\System", "net8.0")
import Rhino, numpy as np
import Rhino.Geometry as rg
doc = Rhino.RhinoDoc.OpenHeadless(os.path.abspath(sys.argv[1]))
L = doc.Layers.FindName("Terrain MNT LiDAR")
m = list(doc.Objects.FindByLayer(L))[0].Geometry
m.FaceNormals.ComputeFaceNormals()
nz = np.array([m.FaceNormals[i].Z for i in range(m.Faces.Count)])
quads = sum(1 for i in range(m.Faces.Count) if m.Faces[i].IsQuad)
print("terrain : %d sommets, %d faces (%d quads) | normales vers le bas : %d (%.2f%%) | quasi verticales (|nz|<0.2) : %d"
      % (m.Vertices.Count, m.Faces.Count, quads, (nz < 0).sum(), 100 * (nz < 0).mean(), (np.abs(nz) < 0.2).sum()))
# quads non plans : écart max du 4e sommet au plan des 3 premiers
dev = []
for i in range(m.Faces.Count):
    f = m.Faces[i]
    if f.IsQuad:
        a, b, c, d = (m.Vertices[f.A], m.Vertices[f.B], m.Vertices[f.C], m.Vertices[f.D])
        p = rg.Plane(rg.Point3d(a), rg.Point3d(b), rg.Point3d(c))
        dev.append(abs(p.DistanceTo(rg.Point3d(d))))
dev = np.array(dev)
print("quads non plans : écart médian %.3f m, 99e %.3f m, max %.3f m" % (np.median(dev), np.percentile(dev, 99), dev.max()))
print("maillage valide :", m.IsValid, "| orienté :", m.IsOriented, "| variété :", m.IsManifold(True, None, None) if hasattr(m, "IsManifold") else "?")
sys.stdout.flush(); os._exit(0)
