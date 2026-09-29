#! python3
"""Captures de vues comparatives (lancé dans une instance Rhino séparée)."""
import os
import System
import Rhino
import scriptcontext as sc

OUT = r"C:\Users\AMD\Documents\00_AMDSIM\02_Topo\dev"
open(os.path.join(OUT, 'capture_log.txt'), 'w').write('demarrage\n')
doc = sc.doc
view = doc.Views.Find("Perspective", False) or doc.Views.ActiveView
doc.Views.ActiveView = view
view.Maximized = True
mode = Rhino.Display.DisplayModeDescription.FindByName("Arctic") or Rhino.Display.DisplayModeDescription.FindByName("Shaded")
view.ActiveViewport.DisplayMode = mode
SETS = {"M0": ["Terrain MNT LiDAR", "M0 Extrusion BD TOPO"],
        "M6": ["Terrain MNT LiDAR", "M6 Murs BD TOPO + toiture LiDAR"]}
CAMS = {"ensemble": ((0, 0, 5), (-150, -190, 130)),
        "ilot_sud": ((-20, -40, 8), (35, -95, 45)),
        "ilot_nord": ((15, 45, 8), (-40, -5, 40))}
for name, layers in SETS.items():
    for i in range(doc.Layers.Count):
        L = doc.Layers[i]
        if L.IsDeleted:
            continue
        L.IsVisible = L.Name in layers
        doc.Layers.Modify(L, i, True)
    for cam, (t, loc) in CAMS.items():
        vp = view.ActiveViewport
        vp.ChangeToPerspectiveProjection(True, 35.0)
        vp.SetCameraLocations(Rhino.Geometry.Point3d(*t), Rhino.Geometry.Point3d(*loc))
        view.Redraw()
        bmp = view.CaptureToBitmap(System.Drawing.Size(1400, 900))
        bmp.Save(os.path.join(OUT, "cap_%s_%s.png" % (cam, name)))
doc.Modified = False
Rhino.RhinoApp.RunScript("_-Exit", False)

