"""Zone test : produit un .3dm comparant les méthodes de toiture (Rhino 8 headless)."""
import os
import sys
import time

import numpy as np

sys.path.insert(0, "dev")
sys.path.insert(0, "src")
import rhinoinside

rhinoinside.load(r"C:\Program Files\Rhino 8\System", "net8.0")
import System  # noqa: E402
import Rhino  # noqa: E402
from scipy.interpolate import LinearNDInterpolator  # noqa: E402

import roofs  # noqa: E402
import rhino_build as rb  # noqa: E402
import zone  # noqa: E402
import roofer_io  # noqa: E402
import roofprints as rp  # noqa: E402
import shutil  # noqa: E402

models = {}  # (méthode, id) -> géométrie, pour la mesure d'écart commune
samples = {}  # id -> points LiDAR de toiture (sous-échantillonnés)
rng = np.random.default_rng(0)

ROOFER = "tools/roofer11/bin/roofer.exe" if "--roofer11" in sys.argv else "tools/roofer/bin/roofer.exe"
OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "out/test_briancon_toitures.3dm")

t0 = time.time()
Z = zone.load(extra=60)
pts6 = Z["pts"][Z["pts"][:, 3] == 6]

doc = Rhino.RhinoDoc.CreateHeadless(None)
doc.ModelUnitSystem = Rhino.UnitSystem.Meters
doc.ModelAbsoluteTolerance = rb.TOL
conv = np.degrees(np.arctan2(-Z["north"][0], Z["north"][1]))  # angle du nord vrai par rapport à +Y
doc.Notes = ("Zone test Briançon, rayon %.0f m.\n"
             "Origine (0,0,0) = lat %.9f / lon %.9f = Lambert-93 X=%.3f Y=%.3f, Z=0 = terrain (MNT) à %.2f m IGN69.\n"
             "Axe +Y = nord Lambert-93 ; nord géographique = +Y tourné de %.2f° (sens trigonométrique).\n"
             "Altitude réelle = Z + %.2f ; Lambert-93 = (X + %.3f, Y + %.3f).\n"
             % (Z["R"], Z["latlon"][0], Z["latlon"][1], Z["origin"][0], Z["origin"][1], Z["z0"], conv,
                Z["z0"], Z["origin"][0], Z["origin"][1]))
eap = Rhino.DocObjects.EarthAnchorPoint()
eap.EarthBasepointLatitude, eap.EarthBasepointLongitude = Z["latlon"]
eap.EarthBasepointElevation = Z["z0"]
eap.ModelBasePoint = Rhino.Geometry.Point3d.Origin
eap.ModelNorth = Rhino.Geometry.Vector3d(float(Z["north"][0]), float(Z["north"][1]), 0.0)
eap.ModelEast = Rhino.Geometry.Vector3d(float(Z["north"][1]), float(-Z["north"][0]), 0.0)
doc.EarthAnchorPoint = eap
for k, v in (("origine_lat", Z["latlon"][0]), ("origine_lon", Z["latlon"][1]), ("origine_L93_X", Z["origin"][0]),
             ("origine_L93_Y", Z["origin"][1]), ("origine_altitude_IGN69", Z["z0"]), ("nord_geographique_deg", conv)):
    doc.Strings.SetString(k, "%.9f" % v)
print("origine : L93 %.3f %.3f, altitude %.2f m, nord géographique à %.2f° de +Y" % (Z["origin"][0], Z["origin"][1], Z["z0"], conv))

LAYERS = [
    ("Terrain MNT LiDAR", (150, 140, 120)),
    ("Emprises BD TOPO", (40, 40, 40)),
    ("M0 Extrusion BD TOPO", (200, 200, 200)),
    ("M1 Maillage LiDAR brut", (230, 150, 90)),
    ("M2 Maillage MNS 50cm", (110, 170, 220)),
    ("M3 Pans de toiture", (220, 90, 90)),
    ("M4 roofer 3DBAG LoD2.2", (90, 180, 110)),
    ("Emprises LiDAR ilots", (200, 60, 60)),
    ("Emprises LiDAR decoupees BD TOPO", (240, 130, 40)),
    ("M5a roofer emprises LiDAR ilots", (70, 150, 200)),
    ("M5b roofer emprises LiDAR decoupees", (240, 170, 60)),
    ("M6 Murs BD TOPO + toiture LiDAR", (205, 110, 80)),
    ("Repli sans LiDAR", (160, 60, 200)),
    ("Points LiDAR bati", (255, 0, 0)),
    ("Vegetation arbres (blocs)", (80, 130, 65)),
    ("Vegetation masses boisees", (70, 120, 60)),
    ("Vegetation arbustes et haies", (130, 160, 90)),
    ("Vegetation sommets", (30, 100, 30)),
]
lay = {}
for name, col in LAYERS:
    L = Rhino.DocObjects.Layer()
    L.Name = name
    L.Color = System.Drawing.Color.FromArgb(*col)
    lay[name] = doc.Layers.Add(L)


def add(geom, layer, **user):
    a = Rhino.DocObjects.ObjectAttributes()
    a.LayerIndex = lay[layer]
    for k, v in user.items():
        a.SetUserString(k, str(v))
    if isinstance(geom, Rhino.Geometry.Mesh):
        return doc.Objects.AddMesh(geom, a)
    if isinstance(geom, Rhino.Geometry.Brep):
        return doc.Objects.AddBrep(geom, a)
    if isinstance(geom, Rhino.Geometry.Curve):
        return doc.Objects.AddCurve(geom, a)
    if isinstance(geom, Rhino.Geometry.PointCloud):
        return doc.Objects.AddPointCloud(geom, a)
    if isinstance(geom, Rhino.Geometry.Point):
        return doc.Objects.AddPoint(geom.Location, a)
    if isinstance(geom, Rhino.Geometry.TextDot):
        return doc.Objects.AddTextDot(geom, a)
    raise TypeError(type(geom))


def err_stats(dz):
    dz = np.abs(dz[np.isfinite(dz)])
    return dz


terrain = rb.terrain_mesh_tri(Z["mnt_terrain"], Z["center"], Z["R_terrain"])
# orthophoto IGN copiée à côté du .3dm (chemin relatif) et drapée sur le terrain
import shutil as _sh  # noqa: E402
ortho_file = os.path.join(os.path.dirname(OUT), "orthophoto_IGN_%s.jpg" % os.path.splitext(os.path.basename(OUT))[0])
_sh.copyfile(Z["ortho"][0], ortho_file)
rb.drape_texture(terrain, Z["ortho"][1])
rm_ortho = rb.texture_material(doc, "Orthophoto IGN", ortho_file)
tid = add(terrain, "Terrain MNT LiDAR", rayon=Z["R_terrain"], maillage="triangles 1 m, diagonale la plus fidele au MNT",
          texture="BD ORTHO IGN 20 cm, licence ouverte Etalab 2.0")
tobj = doc.Objects.FindId(tid)
tobj.RenderMaterial = rm_ortho
tobj.CommitChanges()
L = Rhino.DocObjects.Layer(); L.Name = "Origine"; L.Color = System.Drawing.Color.Black; lay["Origine"] = doc.Layers.Add(L)
add(Rhino.Geometry.TextDot("0,0,0 = %.6f N, %.6f E, %.1f m" % (Z["latlon"][0], Z["latlon"][1], Z["z0"]),
                           Rhino.Geometry.Point3d.Origin), "Origine")
circ = Rhino.Geometry.Circle(Rhino.Geometry.Plane.WorldXY, Z["R"]).ToNurbsCurve()
add(circ, "Origine", nom="zone d'analyse R=%.0f m" % Z["R"])

errs = {k: [] for k in ("M0", "M2", "M3", "M4")}
count = {k: 0 for k in ("M1", "M2", "M3", "M3_solide", "repli")}
tri = {"M1": 0, "M2": 0}
m3_faces = 0
timing = {k: 0.0 for k in ("M1", "M2", "M3")}

for i, (props, fp) in enumerate(Z["blds"]):
    info = dict(id=i, cleabs=props["cleabs"], usage=props["usage_1"], hauteur_bdtopo=props["hauteur"])
    zb = roofs.ground_z(fp, Z["mnt"])
    for c in rb.footprint_curves(fp, zb):
        add(c, "Emprises BD TOPO", **info)
    h = props["hauteur"] or 3.0
    ext = rb.extrusion(fp, zb, h)
    if ext:
        add(ext, "M0 Extrusion BD TOPO", **info)
    P, N = roofs.building_points(fp, pts6)
    if len(P):
        samples[i] = P[rng.choice(len(P), min(len(P), 1500), replace=False)]
    if ext:
        models[("M0", i)] = ext

    if len(P) < 20:  # pas (assez) de LiDAR : repli sur l'extrusion
        if ext:
            add(ext.DuplicateBrep(), "Repli sans LiDAR", **info)
        count["repli"] += 1
        continue

    t = time.time()
    r1 = roofs.roof_lidar(fp, P) if "--m1" in sys.argv else None
    if r1:
        V, F, _ = r1
        add(rb.closed_mesh(V, F, zb), "M1 Maillage LiDAR brut", **info)
        count["M1"] += 1
        tri["M1"] += len(F)
    timing["M1"] += time.time() - t

    t = time.time()
    V, F, _ = roofs.roof_mns(fp, Z["mns"])
    m2 = rb.closed_mesh(V, F, zb)
    add(m2, "M2 Maillage MNS 50cm", **info)
    models[("M2", i)] = m2
    count["M2"] += 1
    tri["M2"] += len(F)
    timing["M2"] += time.time() - t

    t = time.time()
    r3 = roofs.roof_planes(fp, P, N)
    if r3 is None:
        if ext:
            add(ext.DuplicateBrep(), "Repli sans LiDAR", **info)
        count["repli"] += 1
        continue
    brep, solid = rb.planar_solid(fp, r3["V"], r3["F"], zb, r3["face_label"])
    add(brep, "M3 Pans de toiture", pans=len(r3["planes"]), solide=solid, **info)
    models[("M3", i)] = brep
    count["M3"] += 1
    count["M3_solide"] += solid
    m3_faces += brep.Faces.Count
    timing["M3"] += time.time() - t

# ---------------------------------------------------------------- M4 : roofer (3DBAG)
t = time.time()
fps = [fp for _, fp in Z["blds"]]
ht = [roofs.ground_z(fp, Z["mnt"]) for fp in fps]
hr = [g + (p["hauteur"] or 3.0) for g, (p, _) in zip(ht, Z["blds"])]
import shutil  # noqa: E402
shutil.rmtree("data/roofer_out", ignore_errors=True)
roofer_io.write_inputs("data/roofer_in", Z["pts"], fps, Z["origin"], ht, hr)
rr = roofer_io.run(ROOFER, "data/roofer_in", "data/roofer_out",
                   ["--ceil-point-density", "100"])
t_roofer = time.time() - t
res4 = roofer_io.read_cjseq("data/roofer_out", Z["origin"])
count["M4"] = count["M4_solide"] = 0
m4_faces = 0
for i, r in sorted(res4.items()):
    props = Z["blds"][i][0]
    brep, solid, nf = rb.brep_from_surfaces(r["surfaces"])
    if brep is None:
        continue
    mode = r["attributes"].get("rf_extrusion_mode")
    add(brep, "M4 roofer 3DBAG LoD2.2", id=i, cleabs=props["cleabs"], solide=solid, mode_roofer=mode)
    models[("M4", i)] = brep
    count["M4"] += 1
    count["M4_solide"] += solid
    m4_faces += nf
timing["M4"] = time.time() - t

# ---------------------------------------------------------------- M5 : emprises LiDAR + roofer
cx, cy, R = Z["center"][0], Z["center"][1], Z["R"]


def in_circle(fp):
    ring = fp.rings[0]
    return (np.min(np.hypot(ring[:, 0] - cx, ring[:, 1] - cy)) <= R
            or fp.contains(np.array([[cx, cy]]))[0])


t = time.time()
mask, mx0, my0, mc = rp.building_mask(Z["pts"], Z["bbox"], Z["mnt"])
mask = rp.clean_mask(mask, mc)
rf_a, _ = rp.lidar_roofprints(mask, mx0, my0, mc)
rf_b, _ = rp.split_by_footprints(mask, mx0, my0, mc, [fp for _, fp in Z["blds_all"]], max_dist=1.5)
t_rf = time.time() - t
keys_b = [k for k, fp in rf_b.items() if in_circle(fp)]
variants = {"M5a": ([fp for fp in rf_a.values() if in_circle(fp)], "M5a roofer emprises LiDAR ilots",
                    "Emprises LiDAR ilots"),
            "M5b": ([rf_b[k] for k in keys_b], "M5b roofer emprises LiDAR decoupees",
                    "Emprises LiDAR decoupees BD TOPO")}
# M5b : les bâtiments BD TOPO sans aucun point LiDAR sont ajoutés (extrusion de repli par roofer)
covered = np.zeros(len(Z["blds"]), bool)
for k, (props, fp) in enumerate(Z["blds"]):
    c = fp.seg_a.mean(axis=0)
    i_ = int((my0 - c[1]) / mc)
    j_ = int((c[0] - mx0) / mc)
    covered[k] = mask[max(i_ - 2, 0):i_ + 3, max(j_ - 2, 0):j_ + 3].any()
extra_b = [(fp, props) for (props, fp), cov in zip(Z["blds"], covered) if not cov]
m5_stats = {}
for name, (fps5, layer, layer_fp) in variants.items():
    t = time.time()
    hts = [roofs.ground_z(fp, Z["mnt"]) for fp in fps5]
    hrs = [g + 3.0 for g in hts]
    if name == "M5b":
        fps5 = fps5 + [fp for fp, _ in extra_b]
        hts += [roofs.ground_z(fp, Z["mnt"]) for fp, _ in extra_b]
        hrs += [roofs.ground_z(fp, Z["mnt"]) + (p["hauteur"] or 3.0) for fp, p in extra_b]
    for fp, g in zip(fps5, hts):
        for c in rb.footprint_curves(fp, g):
            add(c, layer_fp)
    folder, out = "data/roofer_in_" + name, "data/roofer_out_" + name
    shutil.rmtree(out, ignore_errors=True)
    roofer_io.write_inputs(folder, Z["pts"], fps5, Z["origin"], hts, hrs)
    r5 = roofer_io.run(ROOFER, folder, out, ["--ceil-point-density", "100"])
    t_r = time.time() - t
    res5 = roofer_io.read_cjseq(out, Z["origin"])
    if name == "M5b":
        res5b = res5
    n_ok = n_solid = n_faces = 0
    for i, r in sorted(res5.items()):
        g, solid, nf = rb.brep_from_surfaces(r["surfaces"])
        if g is None:
            continue
        add(g, layer, id="%s_%d" % (name, i), solide=solid, mode_roofer=r["attributes"].get("rf_extrusion_mode"))
        models[(name, i)] = g
        n_ok += 1
        n_solid += solid
        n_faces += nf
    m5_stats[name] = (len(fps5), n_ok, n_solid, n_faces, t_r, r5.returncode)

# ---------------------------------------------------------------- M6 : murs BD TOPO + toiture LiDAR
t = time.time()
m6 = {}
m6_log = []
m4_by_cleabs = {Z["blds"][i][0]["cleabs"]: g for (m_, i), g in models.items() if m_ == "M4"}
for (meth, i), g in list(models.items()):
    if meth != "M5b":
        continue
    key = keys_b[i] if i < len(keys_b) else None
    if key is not None and key[0] <= len(Z["blds_all"]):
        props, fpb = Z["blds_all"][key[0] - 1]
        m4 = m4_by_cleabs.get(props["cleabs"])
        g6, status = rb.walls_on_footprint(g, res5b[i]["surfaces"], fpb, m4)
        info6 = dict(id="M6_%d" % i, cleabs=props["cleabs"], usage=props["usage_1"], statut=status)
    else:  # bâti LiDAR absent de la BD TOPO, ou extrusion de repli : inchangé
        g6, status = g, "ok"
        info6 = dict(id="M6_%d" % i, statut="sans emprise BD TOPO" if key is not None else "extrusion BD TOPO")
    m6[status] = m6.get(status, 0) + 1
    m6_log.append((info6.get("cleabs"), status, i, key))
    g6 = g6 if isinstance(g6, list) else [g6]
    ids6 = [add(x, "M6 Murs BD TOPO + toiture LiDAR", **info6) for x in g6]
    if len(ids6) > 1:
        doc.Groups.Add(rb.net_list(ids6, System.Guid))
    if len(g6) == 1:
        models[("M6", i)] = g6[0]
    else:
        big = Rhino.Geometry.Mesh()
        for x in g6:
            if isinstance(x, Rhino.Geometry.Brep):
                for mm in Rhino.Geometry.Mesh.CreateFromBrep(x, Rhino.Geometry.MeshingParameters.FastRenderMesh):
                    big.Append(mm)
            else:
                big.Append(x)
        models[("M6", i)] = big
t_m6 = time.time() - t

# ---------------------------------------------------------------- mesure globale sur la zone
t = time.time()
Pall = Z["pts"]
Pall = Pall[np.hypot(Pall[:, 0] - cx, Pall[:, 1] - cy) <= R]
hgt = Pall[:, 2] - roofs.bilinear(*Z["mnt"], Pall[:, :2])
roofp = Pall[(Pall[:, 3] == 6) & (hgt >= 1.5)]
cells = np.floor(roofp[:, :2] / 0.5).astype(np.int64)
order = np.lexsort((-roofp[:, 2], cells[:, 1], cells[:, 0]))
_, first = np.unique(cells[order], axis=0, return_index=True)
roof_s = roofp[order][first]  # point le plus haut de chaque cellule de 50 cm
ground = Pall[Pall[:, 3] == 2]
gi = np.floor((my0 - ground[:, 1]) / mc).astype(int)
gj = np.floor((ground[:, 0] - mx0) / mc).astype(int)
dil = rp.ndimage.binary_dilation(mask, iterations=4)  # à plus de 2 m de tout toit
ground = ground[~dil[gi, gj]]
roof_s = roof_s[rng.choice(len(roof_s), min(15000, len(roof_s)), replace=False)]
ground_s = ground[rng.choice(len(ground), min(8000, len(ground)), replace=False)]
glob = {}
for meth in ("M0", "M2", "M3", "M4", "M5a", "M5b", "M6"):
    geoms = [g for (m_, _), g in models.items() if m_ == meth]
    if not geoms:
        continue
    big = Rhino.Geometry.Mesh()
    for g in geoms:
        if isinstance(g, Rhino.Geometry.Brep):
            for x in Rhino.Geometry.Mesh.CreateFromBrep(g, Rhino.Geometry.MeshingParameters.FastRenderMesh):
                big.Append(x)
        else:
            big.Append(g)
    zr = rb.top_z(big, roof_s)
    zg = rb.top_z(big, ground_s)
    glob[meth] = (zr, zg)
t_err = time.time() - t
import json; json.dump([list(map(str, x)) for x in m6_log], open("dev/m6_log.json", "w"))
np.savez("dev/glob.npz", roof_s=roof_s, **{k: v[0] for k, v in glob.items()})

# ---------------------------------------------------------------- végétation
import vegetation as veg  # noqa: E402
t = time.time()
rng_v = np.random.default_rng(11)
bmask, bx0, by0, bc = rp.building_mask(Z["pts"], Z["bbox"], Z["mnt"])
bmask = rp.ndimage.binary_dilation(rp.clean_mask(bmask, bc), iterations=1)
trees, chm, vlab, vx0, vy0 = veg.detect_trees(Z["pts"], Z["bbox"], Z["mnt"], building_mask=bmask)
# pixels dans la zone d'analyse
Hh, Ww = chm.shape
pj, pi = np.meshgrid(np.arange(Ww), np.arange(Hh))
in_zone = np.hypot(vx0 + (pj + 0.5) * 0.5, vy0 - (pi + 0.5) * 0.5) <= Z["R"]
# B. masses boisées (bosquets) et arbustes / haies
mass, absorbed = veg.vegetation_masses(chm, vlab, {t_["label"] for t_ in trees}, 0.5)
mass &= in_zone
n_mass = 0
for V, F in veg.lens_mesh(mass, chm, vx0, vy0, 0.5, Z["mnt"]):
    add(rb.mesh(V, F), "Vegetation masses boisees", type="masse boisee")
    n_mass += 1
shrub = (chm >= 0.5) & (chm < 3.0) & (vlab == 0) & ~mass & in_zone & ~bmask
shrub = rp.ndimage.binary_opening(shrub, iterations=1)
n_shrub = 0
for V, F in veg.lens_mesh(shrub, chm, vx0, vy0, 0.5, Z["mnt"], ground=True, edge=0.8):
    if len(F) >= 8:
        add(rb.mesh(V, F), "Vegetation arbustes et haies", type="arbustes / haie")
        n_shrub += 1
# A. arbres isolés : instances des blocs types
defs = rb.tree_block_definitions(doc, lay["Vegetation arbres (blocs)"])
solo = [t_ for t_ in trees if t_["label"] not in absorbed and np.hypot(t_["x"], t_["y"]) <= Z["R"]]
kinds = {}
for k, t_ in enumerate(solo):
    info_t = dict(id="arbre_%d" % k, type=t_["type"], hauteur="%.1f" % t_["hauteur"],
                  diametre_couronne="%.1f" % (2 * t_["rayon"]))
    a_ = Rhino.DocObjects.ObjectAttributes()
    a_.LayerIndex = lay["Vegetation arbres (blocs)"]
    for kk, vv in info_t.items():
        a_.SetUserString(kk, str(vv))
    doc.Objects.AddInstanceObject(defs[t_["type"]], rb.tree_transform(t_, rng_v.uniform(0, 2 * np.pi)), a_)
    add(Rhino.Geometry.Point(Rhino.Geometry.Point3d(t_["x"], t_["y"], t_["z_sol"] + t_["hauteur"])), "Vegetation sommets", **info_t)
    kinds[t_["type"]] = kinds.get(t_["type"], 0) + 1
doc.Layers[lay["Vegetation sommets"]].IsVisible = False
n_abs = sum(1 for t_ in trees if t_["label"] in absorbed and np.hypot(t_["x"], t_["y"]) <= Z["R"])
print("végétation : %d arbres isolés %s, %d masses boisées (%d arbres regroupés), %d massifs d'arbustes/haies (%.1fs)"
      % (len(solo), kinds, n_mass, n_abs, n_shrub, time.time() - t))

add(rb.point_cloud(pts6), "Points LiDAR bati")
doc.Layers[lay["Points LiDAR bati"]].IsVisible = False

ok = doc.Write3dmFile(OUT, Rhino.FileIO.FileWriteOptions())
print("fichier :", OUT, "OK" if ok else "ECHEC", "%.1f Mo" % (os.path.getsize(OUT) / 1e6))
print("bâtiments : %d emprises, %d en repli sans LiDAR" % (len(Z["blds"]), count["repli"]))
print("M1 : %d maillages, %d triangles, %.1fs" % (count["M1"], tri["M1"], timing["M1"]))
print("M2 : %d maillages, %d triangles, %.1fs" % (count["M2"], tri["M2"], timing["M2"]))
print("M3 : %d polysurfaces (%d fermées), %d faces, %.1fs" % (count["M3"], count["M3_solide"], m3_faces, timing["M3"]))
print("M4 : %d polysurfaces (%d fermées), %d faces, roofer %.1fs + import %.1fs"
      % (count["M4"], count["M4_solide"], m4_faces, t_roofer, timing["M4"] - t_roofer))
for k, (n_in, n_ok, n_solid, n_faces, t_r, code) in m5_stats.items():
    print("%s : %d emprises -> %d polysurfaces (%d fermées), %d faces, roofer %.1fs (code %d)"
          % (k, n_in, n_ok, n_solid, n_faces, t_r, code))
print("M6 : %s (%.1fs)" % (m6, t_m6))
print("emprises LiDAR : %d îlots, %d découpées, %d bât. BD TOPO sans LiDAR ajoutés à M5b (%.1fs)"
      % (len(rf_a), len(rf_b), len(extra_b), t_rf))
print("mesure globale dans le cercle : %d cellules de toit LiDAR, %d points sol hors bâti (%.0fs)"
      % (len(roof_s), len(ground_s), t_err))
for k, (zr, zg) in glob.items():
    hit = np.isfinite(zr)
    dz = np.abs(roof_s[hit, 2] - zr[hit])
    false = np.mean(np.isfinite(zg) & (zg > ground_s[:, 2] + 1.0))
    print("  %-4s couverture toits %5.1f%% | écart médian %.2f m | %3.0f%% < 0,30 m | %4.1f%% > 1 m | fausses surfaces %4.1f%%"
          % (k, 100 * hit.mean(), np.median(dz), 100 * np.mean(dz < 0.3), 100 * np.mean(dz > 1), 100 * false))
print("durée totale %.0fs" % (time.time() - t0))
sys.stdout.flush()
doc.Dispose()
os._exit(0)
