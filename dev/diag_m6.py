import os, sys
sys.path.insert(0, "dev"); sys.path.insert(0, "src")
import rhinoinside
rhinoinside.load(r"C:\Program Files\Rhino 8\System", "net8.0")
import Rhino, numpy as np
import Rhino.Geometry as rg
import zone, roofer_io, roofprints as rp, rhino_build as rb
Z = zone.load(extra=60)
cx, cy, R = Z["center"][0], Z["center"][1], Z["R"]
mask, mx0, my0, mc = rp.building_mask(Z["pts"], Z["bbox"], Z["mnt"]); mask = rp.clean_mask(mask, mc)
rf_b, _ = rp.split_by_footprints(mask, mx0, my0, mc, [fp for _, fp in Z["blds_all"]])
def in_circle(fp):
    ring = fp.rings[0]
    return np.min(np.hypot(ring[:, 0] - cx, ring[:, 1] - cy)) <= R or fp.contains(np.array([[cx, cy]]))[0]
keys_b = [k for k, fp in rf_b.items() if in_circle(fp)]
res = roofer_io.read_cjseq("data/roofer_out_M5b", Z["origin"])
for i, r in sorted(res.items()):
    if i >= len(keys_b) or keys_b[i][0] > len(Z["blds_all"]): continue
    g, solid, nf = rb.brep_from_surfaces(r["surfaces"])
    fp = Z["blds_all"][keys_b[i][0] - 1][1]
    out, st = rb.walls_on_footprint(g, fp)
    if st != "repli M5b": continue
    S = rb._as_brep(g); bb = S.GetBoundingBox(True)
    F = rb.extrusion(fp, bb.Min.Z - 1, bb.Max.Z - bb.Min.Z + 2)
    body = rg.Brep.CreateBooleanIntersection(S, F, 0.01)
    low = S.DuplicateBrep(); low.Translate(rg.Vector3d(0, 0, -0.25))
    slab = rg.Brep.CreateBooleanDifference(S, low, 0.01)
    u = rg.Brep.CreateBooleanUnion(rb.net_list(list(body or []) + list(slab or []), rg.Brep), 0.01) if body and slab else None
    print(i, "type", type(g).__name__, "S solide", S.IsSolid, "faces", S.Faces.Count, "| F ok", F is not None and F.IsSolid,
          "| corps", len(body) if body else 0, "| débord", len(slab) if slab else 0, "| union", len(u) if u else 0,
          "| solides union", [b.IsSolid for b in u] if u else None, "| aire emprise %.0f" % fp.area)
sys.stdout.flush(); os._exit(0)
