import sys, numpy as np
sys.path.insert(0, "dev"); sys.path.insert(0, "src")
import zone, roofs
Z = zone.load(); pts6 = Z["pts"][Z["pts"][:, 3] == 6]
rows = []
for i, (props, fp) in enumerate(Z["blds"]):
    P, N = roofs.building_points(fp, pts6)
    if len(P) < 20: continue
    r = roofs.roof_planes(fp, P, N)
    if r is None: continue
    V, F, L = r["V"], r["F"], r["face_label"]
    p = V[F]; n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]); a = np.linalg.norm(n, axis=1) / 2
    vert = (L == -2)
    hmax = (p[vert][:, :, 2].max(1) - p[vert][:, :, 2].min(1)).max() if vert.any() else 0
    rows.append((a[vert].sum(), hmax, i, fp.area, len(r["planes"]), V[:, 2].max() - P[:, 2].max()))
rows.sort(reverse=True)
print("aire_raccords  h_max  id  aire_emprise  pans  dépassement_z")
for r in rows[:10]: print("%8.1f %6.1f %4d %8.1f %4d %6.2f" % r)
