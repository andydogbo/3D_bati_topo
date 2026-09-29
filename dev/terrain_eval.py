import os, sys
sys.path.insert(0, "dev"); sys.path.insert(0, "src")
import rhinoinside
rhinoinside.load(r"C:\Program Files\Rhino 8\System", "net8.0")
import Rhino, numpy as np
import Rhino.Geometry as rg
import zone
Z = zone.load(extra=60)
z, x0, y0, res = Z["mnt_terrain"]
rng = np.random.default_rng(1)
I = rng.integers(0, z.shape[0], 60000); J = rng.integers(0, z.shape[1], 60000)
X = x0 + J * res; Y = y0 - I * res
k = np.hypot(X, Y) < 195
X, Y, ZT = X[k][:20000], Y[k][:20000], z[I[k], J[k]][:20000]
doc = Rhino.RhinoDoc.OpenHeadless(os.path.abspath(sys.argv[1]))
for name in ("Terrain MNT LiDAR", "Terrain triangule diagonales MNT", "Terrain QuadRemesh"):
    m = list(doc.Objects.FindByLayer(doc.Layers.FindName(name)))[0].Geometry
    m.FaceNormals.ComputeFaceNormals()
    down = sum(1 for i in range(m.FaceNormals.Count) if m.FaceNormals[i].Z < 0)
    d = []
    for x, y, zt in zip(X, Y, ZT):
        t = rg.Intersect.Intersection.MeshRay(m, rg.Ray3d(rg.Point3d(float(x), float(y), 500.0), rg.Vector3d(0, 0, -1)))
        if t >= 0: d.append(500.0 - t - zt)
    d = np.abs(np.array(d))
    print("%-34s %7d faces | vers le bas %3d | écart au MNT 50 cm : médiane %.3f m, 95e %.2f, 99e %.2f, max %.2f"
          % (name, m.Faces.Count, down, np.median(d), np.percentile(d, 95), np.percentile(d, 99), d.max()))
sys.stdout.flush(); os._exit(0)
