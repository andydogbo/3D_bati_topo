import os, sys
import rhinoinside
rhinoinside.load(r"C:\Program Files\Rhino 8\System", "net8.0")
import Rhino, numpy as np
import Rhino.Geometry as rg
doc = Rhino.RhinoDoc.OpenHeadless(os.path.abspath(sys.argv[1]))
box = [float(v) for v in sys.argv[2].split(",")]
tris, cols = [], []
def add_mesh(m, col):
    m = m.DuplicateMesh(); m.Faces.ConvertQuadsToTriangles()
    V = np.array([[v.X, v.Y, v.Z] for v in m.Vertices]); F = np.array([[f.A, f.B, f.C] for f in m.Faces])
    if not len(F): return
    c = V[F].mean(1); k = (c[:, 0] > box[0]) & (c[:, 0] < box[1]) & (c[:, 1] > box[2]) & (c[:, 1] < box[3])
    tris.append(V[F[k]]); cols.append(np.tile(col, (k.sum(), 1)))
for name in ("Vegetation arbres (blocs)", "Vegetation masses boisees", "Vegetation arbustes et haies", "M0 Extrusion BD TOPO", "Terrain MNT LiDAR"):
    L = doc.Layers.FindName(name)
    for o in doc.Objects.FindByLayer(L):
        g = o.Geometry
        if isinstance(o, Rhino.DocObjects.InstanceObject):
            bb = o.Geometry.GetBoundingBox(True) if hasattr(o.Geometry, "GetBoundingBox") else None
            for sub in o.InstanceDefinition.GetObjects():
                m = sub.Geometry.DuplicateMesh() if isinstance(sub.Geometry, rg.Mesh) else None
                if m is None: continue
                m.Transform(o.InstanceXform)
                c = sub.Attributes.ObjectColor
                add_mesh(m, (c.R / 255, c.G / 255, c.B / 255))
        elif isinstance(g, rg.Mesh):
            col = {"Vegetation masses boisees": (0.33, 0.5, 0.3), "Vegetation arbustes et haies": (0.55, 0.65, 0.38), "Terrain MNT LiDAR": (0.78, 0.76, 0.7)}[name]
            add_mesh(g, col)
        elif isinstance(g, (rg.Brep, rg.Extrusion)):
            b = g.ToBrep() if isinstance(g, rg.Extrusion) else g
            for m in rg.Mesh.CreateFromBrep(b, rg.MeshingParameters.FastRenderMesh): add_mesh(m, (0.9, 0.9, 0.88))
np.savez(sys.argv[3], tris=np.vstack(tris), cols=np.vstack(cols))
print("triangles :", sum(len(t) for t in tris))
sys.stdout.flush(); os._exit(0)
