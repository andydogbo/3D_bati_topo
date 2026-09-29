import os, sys
sys.path.insert(0, "dev"); sys.path.insert(0, "src")
import rhinoinside
rhinoinside.load(r"C:\Program Files\Rhino 8\System", "net8.0")
import Rhino, numpy as np
import zone, roofer_io, rhino_build as rb
Z = zone.load()
res4 = roofer_io.read_cjseq("data/roofer_out", Z["origin"])
for tol in (0.01, 0.02):
    bad = []
    for i, r in sorted(res4.items()):
        parts_fail = 0
        b, solid, nf = rb.brep_from_surfaces(r["surfaces"], tol)
        if not solid:
            nk = b.Edges.Count and sum(1 for e in b.Edges if e.Valence == Rhino.Geometry.EdgeAdjacency.Naked)
            bad.append((i, r["attributes"].get("rf_extrusion_mode"), nf, b.Faces.Count, nk))
    print("tol", tol, "non fermés:", bad)
sys.stdout.flush(); os._exit(0)
