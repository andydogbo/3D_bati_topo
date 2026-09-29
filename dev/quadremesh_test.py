import os, sys, time
import rhinoinside
rhinoinside.load(r"C:\Program Files\Rhino 8\System", "net8.0")
import Rhino, numpy as np
import Rhino.Geometry as rg
doc = Rhino.RhinoDoc.OpenHeadless(os.path.abspath(sys.argv[1]))
L = doc.Layers.FindName("Terrain MNT LiDAR")
m = list(doc.Objects.FindByLayer(L))[0].Geometry
for target in (60000, 30000):
    p = rg.QuadRemeshParameters()
    p.TargetQuadCount = target
    p.AdaptiveSize = 50
    p.AdaptiveQuadCount = True
    p.DetectHardEdges = True
    t = time.time()
    q = m.QuadRemesh(p)
    if q is None:
        print("QuadRemesh a échoué (cible %d)" % target); continue
    q.FaceNormals.ComputeFaceNormals()
    nz = np.array([q.FaceNormals[i].Z for i in range(q.Faces.Count)])
    quads = sum(1 for i in range(q.Faces.Count) if q.Faces[i].IsQuad)
    # écart au terrain d'origine : altitude du remaillage vs MNT maillé, sur 3000 points
    rng = np.random.default_rng(0); d = []
    for _ in range(3000):
        x, y = rng.uniform(-190, 190, 2)
        if np.hypot(x, y) > 190: continue
        r0 = rg.Intersect.Intersection.MeshRay(m, rg.Ray3d(rg.Point3d(x, y, 500), rg.Vector3d(0, 0, -1)))
        r1 = rg.Intersect.Intersection.MeshRay(q, rg.Ray3d(rg.Point3d(x, y, 500), rg.Vector3d(0, 0, -1)))
        if r0 >= 0 and r1 >= 0: d.append(r1 - r0)
    d = np.abs(np.array(d))
    print("cible %d : %.0fs -> %d faces (%d quads), normales vers le bas %d, écart au MNT médian %.3f m, 99e %.2f m, max %.2f m"
          % (target, time.time() - t, q.Faces.Count, quads, (nz < 0).sum(), np.median(d), np.percentile(d, 99), d.max()))
sys.stdout.flush(); os._exit(0)
