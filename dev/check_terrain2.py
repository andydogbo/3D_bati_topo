import os, sys
import rhinoinside
rhinoinside.load(r"C:\Program Files\Rhino 8\System", "net8.0")
import Rhino, numpy as np
doc = Rhino.RhinoDoc.OpenHeadless(os.path.abspath(sys.argv[1]))
for L in doc.Layers:
    objs = list(doc.Objects.FindByLayer(L)) if not L.IsDeleted else []
    meshes = [o for o in objs if isinstance(o.Geometry, Rhino.Geometry.Mesh)]
    if "errain" in L.Name:
        for o in meshes:
            m = o.Geometry
            q = sum(1 for i in range(m.Faces.Count) if m.Faces[i].IsQuad)
            m.FaceNormals.ComputeFaceNormals()
            down = sum(1 for i in range(m.FaceNormals.Count) if m.FaceNormals[i].Z < 0)
            bb = m.GetBoundingBox(True)
            print("calque '%s' : %d sommets, %d faces dont %d quads et %d triangles, %d normales vers le bas | x %.0f..%.0f y %.0f..%.0f | maillage='%s'"
                  % (L.Name, m.Vertices.Count, m.Faces.Count, q, m.Faces.Count - q, down, bb.Min.X, bb.Max.X, bb.Min.Y, bb.Max.Y,
                     o.Attributes.GetUserString("maillage")))
print("calques terrain :", [L.Name for L in doc.Layers if "errain" in L.Name])
sys.stdout.flush(); os._exit(0)
