import os, sys, rhinoinside
rhinoinside.load(r"C:\Program Files\Rhino 8\System", "net8.0")
import System, Rhino
g = System.Guid(sys.argv[1])
for f in ("out/test_briancon_toitures_v2.3dm", "out/test_briancon_toitures_v1.3dm"):
    m = Rhino.FileIO.File3dm.Read(os.path.abspath(f))
    o = m.Objects.FindId(g)
    if o is None:
        print(f, "-> introuvable"); continue
    a = o.Attributes
    us = a.GetUserStrings()
    print(f, "-> calque", a.LayerIndex, {k: us[k] for k in us.AllKeys})
sys.stdout.flush()
os._exit(0)
