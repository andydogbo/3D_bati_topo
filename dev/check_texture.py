import os, sys
import rhinoinside
rhinoinside.load(r"C:\Program Files\Rhino 8\System", "net8.0")
import Rhino
doc = Rhino.RhinoDoc.OpenHeadless(os.path.abspath(sys.argv[1]))
o = list(doc.Objects.FindByLayer(doc.Layers.FindName("Terrain MNT LiDAR")))[0]
m = o.Geometry
rm = o.RenderMaterial
print("matériau :", rm.Name if rm else None, "| coords texture :", m.TextureCoordinates.Count, "/", m.Vertices.Count)
if rm:
    sm = rm.SimulatedMaterial(Rhino.Render.RenderTexture.TextureGeneration.Allow)
    t = sm.GetBitmapTexture()
    print("texture :", t.FileReference.FullPath if t else None, "| existe :", os.path.exists(t.FileReference.FullPath) if t else None)
sys.stdout.flush(); os._exit(0)
