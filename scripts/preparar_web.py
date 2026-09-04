# -*- coding: utf-8 -*-
"""
PREPARA LOS INSUMOS GEOGRÁFICOS DEL NIVEL MUNICIPIO — LOS 343.
================================================================

Port nacional del preparador metropolitano. Emite en `docs/datos/`:

  · `municipios.geojson`  los 343 polígonos, desde el mapa MAESTRO
    (`bo-geo-maestro`, clave `sigep`). No se recorta de ninguna otra fuente: la
    espina madre ya tiene los nombres curados y el crosswalk INE↔SIGEP congelado.
  · `region.geojson`      el contorno del PAÍS (unión de los 343), para el
    encuadre inicial y para tapar lo de afuera.
    ⚠️ El nombre del archivo se conserva —lo lee el tablero— aunque acá «región»
       sea Bolivia entera. Renombrarlo obligaría a tocar el JS por cosmética.
  · `mini.json`           las siluetas para los minimapas de cada tarjeta.

★ LA TOLERANCIA DE SIMPLIFICACIÓN NO SE HEREDA, SE MIDE. La versión
  metropolitana simplifica a 320 m porque su lienzo de 100×100 cubre ~150 km.
  El mismo lienzo sobre Bolivia cubre ~1.500 km: 100 unidades para 1.500 km son
  15 km por unidad, así que 320 m es una décima de píxel —detalle que nadie ve y
  que multiplica por diez el peso del archivo—. Se usa una tolerancia acorde y
  se INFORMA el peso resultante para poder discutirlo con un número.

    python scripts/preparar_web.py
"""
import json, pathlib, re
import geopandas as gpd

import sys as _sys
_sys.stdout.reconfigure(encoding="utf-8")

RAIZ = pathlib.Path(__file__).resolve().parent.parent
GEO = RAIZ.parent / "bo-geo-maestro" / "geo" / "atlas_muni_343.topojson"
SALIDA = RAIZ / "docs" / "datos"
TOL_MINI_M = 2000     # ver la nota de arriba: ~0,13 unidades del lienzo


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    muns = json.loads((RAIZ / "datos" / "municipios.json").read_text(encoding="utf-8"))
    quiero = {m["sigep"]: m for m in muns}

    g = gpd.read_file(GEO)
    # El topojson maestro no declara CRS y GeoJSON sin proyección es una bomba de
    # tiempo para quien lo consuma después. Es lon/lat.
    if g.crs is None:
        g = g.set_crs("EPSG:4326")
    col = "sigep" if "sigep" in g.columns else g.columns[0]
    g[col] = g[col].astype(str)
    sub = g[g[col].isin(quiero)].copy()
    if len(sub) != len(quiero):
        faltan = set(quiero) - set(sub[col])
        raise SystemExit(f"ERROR: faltan municipios en el mapa maestro: {sorted(faltan)}")

    sub["sigep"] = sub[col]
    sub["nombre"] = sub["sigep"].map(lambda s: quiero[s]["nombre"])
    sub["dpto"] = sub["sigep"].map(lambda s: quiero[s]["dpto"])
    sub = sub[["sigep", "nombre", "dpto", "geometry"]]
    sub.to_file(SALIDA / "municipios.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)

    borde = gpd.GeoDataFrame(geometry=[sub.union_all()], crs=sub.crs)
    borde.to_file(SALIDA / "region.geojson", driver="GeoJSON", COORDINATE_PRECISION=5)

    # ── minimapas de las tarjetas ────────────────────────────────────────────
    # Cada indicador del panel lleva una miniatura del país pintada con SU valor.
    # Se precalculan los contornos ya simplificados y proyectados a un lienzo
    # 100×100, para que el navegador sólo tenga que pintarlos.
    mini = sub.to_crs("EPSG:32720")
    mini["geometry"] = mini.geometry.simplify(TOL_MINI_M, preserve_topology=True)
    mini = mini.to_crs("EPSG:4326")
    mxmin, mymin, mxmax, mymax = mini.total_bounds
    ancho, alto = mxmax - mxmin, mymax - mymin
    esc = 100 / max(ancho, alto)
    dx = (100 - ancho * esc) / 2
    dy = (100 - alto * esc) / 2

    def a_path(geom):
        partes = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
        d = []
        for p in partes:
            for anillo in [p.exterior] + list(p.interiors):
                pts = [(round((x - mxmin) * esc + dx, 1),
                        round(100 - ((y - mymin) * esc + dy), 1))
                       for x, y in anillo.coords]
                if len(pts) < 3:
                    continue
                d.append("M" + " ".join(f"{x},{y}" for x, y in pts) + "Z")
        return "".join(d)

    paths = {r["sigep"]: a_path(r["geometry"]) for _, r in mini.iterrows()}
    # La caja real, con 2% de margen: Bolivia es casi cuadrada, pero el lienzo
    # ajustado igual evita el aire de los bordes.
    _n = [float(t) for d in paths.values() for t in re.findall(r"-?\d+(?:\.\d+)?", d)]
    _x, _y = _n[0::2], _n[1::2]
    _m = (max(_x) - min(_x)) * .02
    caja = "%.2f %.2f %.2f %.2f" % (min(_x)-_m, min(_y)-_m,
                                    max(_x)-min(_x)+2*_m, max(_y)-min(_y)+2*_m)
    (SALIDA / "mini.json").write_text(
        json.dumps({"viewBox": "0 0 100 100", "viewBoxTight": caja, "paths": paths},
                   ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    kb = lambda f: (SALIDA / f).stat().st_size / 1024
    xmin, ymin, xmax, ymax = sub.total_bounds
    print(f"{len(sub)} municipios · bbox [{xmin:.2f}, {ymin:.2f}, {xmax:.2f}, {ymax:.2f}]")
    print(f"  municipios.geojson {kb('municipios.geojson'):>8.0f} KB")
    print(f"  region.geojson     {kb('region.geojson'):>8.0f} KB")
    print(f"  mini.json          {kb('mini.json'):>8.0f} KB  "
          f"({len(paths)} siluetas, simplificadas a {TOL_MINI_M} m)")
    print(f"  → {SALIDA}")


if __name__ == "__main__":
    main()
