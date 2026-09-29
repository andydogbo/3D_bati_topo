import sys, time, numpy as np
sys.path.insert(0, "dev"); sys.path.insert(0, "src")
import zone, roofs
Z = zone.load()
pts6 = Z["pts"][Z["pts"][:, 3] == 6]
print(len(Z["blds"]), "emprises")
t = time.time(); res = []
for i, (props, fp) in enumerate(Z["blds"]):
    P, N = roofs.building_points(fp, pts6)
    m1 = roofs.roof_lidar(fp, P); m2 = roofs.roof_mns(fp, Z["mns"])
    try:
        m3 = roofs.roof_planes(fp, P, N)
    except Exception as e:
        import traceback; traceback.print_exc(); m3 = None
    res.append((i, fp.area, len(P), m3))
    if m3: print("%2d aire %6.1f pts %5d pans %2d étiquetés %3.0f%% faces %5d raccords %d" % (i, fp.area, len(P), len(m3["planes"]), 100*m3["n_labeled"]/max(1,m3["n_pts"]), len(m3["F"]), (m3["face_label"]==-2).sum()))
    else: print("%2d aire %6.1f pts %5d -> pas de pan" % (i, fp.area, len(P)))
print("total %.1fs" % (time.time() - t))
import pickle; pickle.dump(res, open("dev/m3.pkl", "wb"))
