import os, sys
import rhinoinside
rhinoinside.load(r"C:\Program Files\Rhino 8\System", "net8.0")
import Rhino
doc = Rhino.RhinoDoc.OpenHeadless(os.path.abspath(sys.argv[1]))
e = doc.EarthAnchorPoint
print("ancrage : lat %.6f lon %.6f alt %.2f | base modèle %s | nord modèle %s" % (e.EarthBasepointLatitude, e.EarthBasepointLongitude, e.EarthBasepointElevation, e.ModelBasePoint, e.ModelNorth))
print("unités :", doc.ModelUnitSystem, "| chaînes :", {k: doc.Strings.GetValue(k) for k in ("origine_L93_X", "origine_altitude_IGN69", "nord_geographique_deg")})
L = doc.Layers.FindName("Terrain MNT LiDAR")
for o in doc.Objects.FindByLayer(L):
    bb = o.Geometry.GetBoundingBox(True)
    print("terrain : x %.1f..%.1f  y %.1f..%.1f  z %.1f..%.1f" % (bb.Min.X, bb.Max.X, bb.Min.Y, bb.Max.Y, bb.Min.Z, bb.Max.Z))
    r = Rhino.Geometry.Intersect.Intersection.MeshRay(o.Geometry, Rhino.Geometry.Ray3d(Rhino.Geometry.Point3d(0, 0, 100), Rhino.Geometry.Vector3d(0, 0, -1)))
    print("altitude du terrain en (0,0) : %.3f m" % (100 - r))
sys.stdout.flush(); os._exit(0)
