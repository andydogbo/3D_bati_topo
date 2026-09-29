import os, sys
sys.path.insert(0, "dev"); sys.path.insert(0, "src")
import rhinoinside
rhinoinside.load(r"C:\Program Files\Rhino 8\System", "net8.0")
import Rhino, numpy as np
import Rhino.Geometry as rg
import zone, roofer_io, rhino_build as rb
Z = zone.load(extra=60)
res = roofer_io.read_cjseq("data/roofer_out_M5b", Z["origin"])
vol = lambda b: rg.VolumeMassProperties.Compute(b).Volume
for i, k in ((23, 92), (24, 93)):
    S, solid, _ = rb.brep_from_surfaces(res[i]["surfaces"])
    fp = Z["blds_all"][k - 1][1]
    bb = S.GetBoundingBox(True)
    F = rb.extrusion(fp, bb.Min.Z - 1.0, bb.Max.Z - bb.Min.Z + 2.0)
    body = rb.body_on_footprint(S, fp)
    print(i, "S vol %.0f z %.1f..%.1f | F vol %.0f | corps:" % (vol(S), bb.Min.Z, bb.Max.Z, vol(F)),
          [("vol %.0f" % vol(b), "zmax %.1f" % b.GetBoundingBox(True).Max.Z) for b in body])
    plates = rb.overhang_plates(res[i]["surfaces"], fp)
    print("   plaques", len(plates), "zmax", ["%.1f" % p.GetBoundingBox(True).Max.Z for p in plates][:10],
          "aire totale %.1f" % sum(rg.AreaMassProperties.Compute(p).Area / 2 for p in plates))
sys.stdout.flush(); os._exit(0)
