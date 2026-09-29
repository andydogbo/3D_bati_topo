import sys, json, re, requests
sys.path.insert(0, "src")
from geo import wgs84_to_l93
lat, lon = 44.892599016233035, 6.6360779217772725
x, y = wgs84_to_l93(lat, lon)
print("L93:", round(x, 2), round(y, 2))
R = 100
bbox = (x - R, y - R, x + R, y + R)
W = "https://data.geopf.fr/wfs/ows"
def wfs(typename, bbox, srs="EPSG:2154"):
    p = dict(SERVICE="WFS", VERSION="2.0.0", REQUEST="GetFeature", TYPENAMES=typename,
             SRSNAME="EPSG:2154", OUTPUTFORMAT="application/json",
             BBOX="%f,%f,%f,%f,%s" % (*bbox, srs))
    r = requests.get(W, params=p, timeout=60); r.raise_for_status(); return r.json()
b = wfs("BDTOPO_V3:batiment", bbox)
print("bâtiments:", len(b["features"]))
print("attributs:", sorted(b["features"][0]["properties"].keys()))
# contrôle de la projection : même requête avec bbox en WGS84 (ordre lat,lon)
d = 0.0005
b2 = wfs("BDTOPO_V3:batiment", (lat - d, lon - d, lat + d, lon + d), "urn:ogc:def:crs:EPSG::4326")
ids = {f["properties"]["cleabs"] for f in b["features"]}
print("contrôle proj: %d/%d bâtiments WGS84 trouvés dans la bbox L93" % (sum(f["properties"]["cleabs"] in ids for f in b2["features"]), len(b2["features"])))
t = wfs("IGNF_NUAGES-DE-POINTS-LIDAR-HD:dalle", bbox)
for f in t["features"]:
    print("dalle:", json.dumps(f["properties"], ensure_ascii=False))
cap = requests.get("https://data.geopf.fr/wms-r/ows", params=dict(SERVICE="WMS", REQUEST="GetCapabilities", VERSION="1.3.0"), timeout=120).text
names = set(re.findall(r"<Name>([^<]*LIDAR[^<]*|[^<]*ELEVATION[^<]*)</Name>", cap))
print("\n".join(sorted(names)))
fmts = set(re.findall(r"<Format>([^<]+)</Format>", cap)); print(fmts)
