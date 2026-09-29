"""Conversion WGS84 (lat/lon) -> Lambert-93 (EPSG:2154), sans dépendance.

Projection conique conforme de Lambert à deux parallèles sur l'ellipsoïde GRS80.
RGF93 et WGS84 sont confondus à quelques centimètres près en métropole.
"""
import math

_A = 6378137.0
_F = 1 / 298.257222101
_E = math.sqrt(_F * (2 - _F))
_LAT1 = math.radians(44.0)
_LAT2 = math.radians(49.0)
_LAT0 = math.radians(46.5)
_LON0 = math.radians(3.0)
_X0 = 700000.0
_Y0 = 6600000.0


def _m(lat):
    return math.cos(lat) / math.sqrt(1 - (_E * math.sin(lat)) ** 2)


def _t(lat):
    s = _E * math.sin(lat)
    return math.tan(math.pi / 4 - lat / 2) / ((1 - s) / (1 + s)) ** (_E / 2)


_N = (math.log(_m(_LAT1)) - math.log(_m(_LAT2))) / (math.log(_t(_LAT1)) - math.log(_t(_LAT2)))
_FF = _m(_LAT1) / (_N * _t(_LAT1) ** _N)
_RHO0 = _A * _FF * _t(_LAT0) ** _N


def wgs84_to_l93(lat, lon):
    """Retourne (x, y) en mètres Lambert-93."""
    lat, lon = math.radians(lat), math.radians(lon)
    rho = _A * _FF * _t(lat) ** _N
    theta = _N * (lon - _LON0)
    return _X0 + rho * math.sin(theta), _Y0 + _RHO0 - rho * math.cos(theta)
