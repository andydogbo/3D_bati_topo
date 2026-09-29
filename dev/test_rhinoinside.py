import time
t = time.time()
import rhinoinside
rhinoinside.load(r"C:\Program Files\Rhino 8\System", "net8.0")
import System
import Rhino
print("Rhino chargé en %.1f s" % (time.time() - t), Rhino.RhinoApp.Version)
doc = Rhino.RhinoDoc.CreateHeadless(None)
box = Rhino.Geometry.Box(Rhino.Geometry.Plane.WorldXY, Rhino.Geometry.Interval(0, 10), Rhino.Geometry.Interval(0, 10), Rhino.Geometry.Interval(0, 10))
doc.Objects.AddBrep(box.ToBrep())
ok = doc.Write3dmFile(r"C:\Users\AMD\Documents\00_AMDSIM\02_Topo\out\test.3dm", Rhino.FileIO.FileWriteOptions())
print("écriture 3dm:", ok)
