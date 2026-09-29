import sys, time, numpy as np
sys.path.insert(0, "dev"); sys.path.insert(0, "src")
import zone, roofs, roofer_io
Z = zone.load()
fps = [fp for _, fp in Z["blds"]]
ht = [roofs.ground_z(fp, Z["mnt"]) for fp in fps]
hr = [h + (p["hauteur"] or 3.0) for h, (p, _) in zip(ht, Z["blds"])]
roofer_io.write_inputs("data/roofer_in", Z["pts"], fps, Z["origin"], ht, hr)
t = time.time()
r = roofer_io.run("tools/roofer/bin/roofer.exe", "data/roofer_in", "data/roofer_out")
print("code", r.returncode, "%.1fs" % (time.time() - t)); print(r.stdout[-2500:]); print(r.stderr[-2500:])
res = roofer_io.read_cjseq("data/roofer_out", Z["origin"])
print(len(res), "bâtiments lus")
k = sorted(res)[:3]
for b in k: print(b, len(res[b]["surfaces"]), {s for s, _ in res[b]["surfaces"]}, list(res[b]["attributes"].items())[:12])
