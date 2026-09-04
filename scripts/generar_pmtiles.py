# -*- coding: utf-8 -*-
"""
TESELA LAS 247.429 MANZANAS DEL PAÍS A UN ARCHIVO PMTiles.
============================================================

Port nacional del teselador metropolitano. Mismo formato de salida y mismos
zooms, pero seis veces más manzanas y una máquina con 7,3 GB de RAM: la
diferencia no es de escala, es de MÉTODO.

★ POR QUÉ TESELAR, que sigue siendo la razón original: con los datos dentro de
  la tesela como atributos, cambiar de indicador es cambiar la expresión de
  color —`["get", clave]`— y nada más. La alternativa (un GeoJSON con los
  valores y `setData()` en cada cambio) reserializa el nivel entero para
  cambiar un color.

★ SIN tippecanoe: no hay binario de Windows ni WSL en esta máquina. Se tesela
  con shapely + mapbox_vector_tile y se empaqueta con `pmtiles` de Protomaps.

⚠️ SE TRABAJA POR BLOQUES, Y NO ES UNA OPTIMIZACIÓN: es lo que hace que esto
   corra. Cargar las 247.429 geometrías y su índice espacial de una vez pide
   más memoria de la que hay libre (medido: 0,3 GB de 7,3 GB en esta máquina, el
   resto son navegadores). Así que:

     1. UNA pasada en tandas convierte cada manzana a Mercator, la simplifica y
        guarda su WKB y su caja. Nunca hay más de `TANDA` geometrías vivas.
     2. Las manzanas se agrupan por TESELA DE ZMIN. Cada bloque arma su propio
        índice espacial, emite sus teselas de todos los zooms y se libera.

   Cada tesela de zoom mayor cae dentro de exactamente una de ZMIN, así que
   ningún bloque puede pisar la tesela de otro. Los vecinos SÍ entran al bloque
   —la selección usa la caja del bloque más el buffer— para que las manzanas no
   se corten en la costura.

⚠️ EL `Writer` de pmtiles ORDENA al finalizar (`sorted(tile_entries)`) y guarda
   los bytes en un temporal, así que emitir las teselas fuera de orden es
   válido. Sólo marca el archivo como "no agrupado", que cuesta algo de
   eficiencia en las peticiones por rango, no corrección.

★ LA CLAVE DEL MUNICIPIO ES `sigep`, NO EL NOMBRE. El tablero metropolitano
  identificaba la manzana con el slug del nombre de su municipio, y con nueve
  funcionaba. Con 343 hay NUEVE COLISIONES que afectan a veinte municipios
  —San Pedro y Santa Rosa existen tres veces cada uno, en departamentos
  distintos—, así que ese slug le habría atribuido las manzanas de un municipio
  a otro sin que nada fallara. El puente manzano→municipio lo emite
  `armar_municipios.py`; acá sólo se lee.

    python scripts/generar_pmtiles.py
"""
import gzip, json, math, pathlib, sys, time
import numpy as np
import pandas as pd
import shapely
from shapely import STRtree
from shapely.geometry import box
import mapbox_vector_tile
from mapbox_vector_tile.encoder import on_invalid_geometry_make_valid
from pmtiles.writer import Writer
from pmtiles.tile import Compression, TileType, zxy_to_tileid

_sys = sys
_sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "catalogo"))
from alias import renombrar

RAIZ = pathlib.Path(__file__).resolve().parent.parent
FUENTE = RAIZ / "fuente"
CAT = RAIZ / "catalogo"
DATOS = RAIZ / "docs" / "datos"
SALIDA = DATOS / "manzanas.pmtiles"

# ── Banda de zoom ────────────────────────────────────────────────────────────
# Misma que la metropolitana, y por la misma razón: el cruce municipio→manzana
# empieza en z11,4 y las teselas tienen que existir un poco antes. A z10 una
# manzana de 100 m mide 0,7 px —sub-píxel—, así que se lee como mancha y no como
# polígono; es el piso razonable.
# ⚠️ EL TECHO ES z13, NO z14 (2026-09-04, port nacional). A escala país el
#    archivo con techo 14 pesó 139,9 MB y GitHub RECHAZA cualquier archivo de
#    más de 100 MB: no es una preferencia de peso, es que no se puede publicar.
#    El costo de bajarlo es nulo a la vista: MapLibre SOBRE-ESCALA la última
#    tesela, así que por encima de z13 se sigue viendo la manzana, con la
#    geometría cuantizada a 1,2 m —el ancho de una vereda— en vez de 0,6.
#    Lo que se ahorra es que los 91 atributos de cada manzana NO se repitan una
#    quinta vez: el peso de este archivo son los atributos, no los polígonos.
ZMIN, ZMAX = 10, 13
EXTENT = 4096
BUFFER = 64          # unidades de tesela: cose los bordes entre teselas vecinas
CAPA = "manzanas"
R = 6378137.0
MUNDO = math.pi * R
TANDA = 20000        # geometrías vivas por vez en la pasada de preparación
# Simplificación previa, en metros de Mercator. La geometría del geoportal trae
# el detalle del catastro; a z14 —el zoom más fino que se tesela— un píxel son
# 2,4 m en el ecuador, así que por debajo de eso no hay nada que ver. Se hace UNA
# vez acá en vez de en cada tesela, que es donde estaba el costo.
TOL_PREVIA_M = 1.5


def merc(lon, lat):
    x = R * math.radians(lon)
    y = R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, y


def merc_np(c):
    """La misma proyección, vectorizada. `math.log` sobre un arreglo revienta:
    la conversión de las 247.429 geometrías se hace con numpy o no se hace."""
    x = R * np.radians(c[:, 0])
    y = R * np.log(np.tan(np.pi / 4 + np.radians(c[:, 1]) / 2))
    return np.column_stack([x, y])


def tile_bounds(z, x, y):
    lado = 2 * MUNDO / (2 ** z)
    return (-MUNDO + x * lado, MUNDO - (y + 1) * lado,
            -MUNDO + (x + 1) * lado, MUNDO - y * lado)


def tile_xy(z, mx, my):
    lado = 2 * MUNDO / (2 ** z)
    return (int((mx + MUNDO) // lado), int((MUNDO - my) // lado))


def normalizar(g):
    """Todo a (Multi)Polygon. Un GeometryCollection revienta el codificador."""
    if g is None or g.is_empty:
        return None
    t = g.geom_type
    if t in ("Polygon", "MultiPolygon"):
        return g
    if t == "GeometryCollection":
        partes = [p for p in g.geoms if p.geom_type in ("Polygon", "MultiPolygon")]
        return shapely.union_all(partes) if partes else None
    return None


def preparar():
    """Convierte a Mercator, simplifica y devuelve (wkb, cajas, propiedades).

    La geometría vuelve como WKB —bytes— a propósito: 247.429 objetos de shapely
    vivos a la vez no entran, y los bytes sí. Cada bloque los revive."""
    import pyarrow.parquet as pq

    print("preparando geometría…")
    t0 = time.time()
    pf = pq.ParquetFile(FUENTE / "manzanos.parquet")
    codigos, wkbs, cajas = [], [], []
    leidas, rotas = 0, [0]
    for lote in pf.iter_batches(batch_size=TANDA, columns=["codigo", "geometry"]):
        cod = lote.column("codigo").to_pylist()
        g = shapely.from_wkb(lote.column("geometry").to_numpy(zero_copy_only=False))
        g = shapely.transform(g, merc_np, include_z=False)
        g = shapely.simplify(g, TOL_PREVIA_M, preserve_topology=True)
        # ⚠️ REPARAR ES OBLIGATORIO, NO PROLIJIDAD. La geometría del geoportal
        #    trae polígonos inválidos (anillos que se tocan, "side location
        #    conflict"), y simplificar puede crear alguno más. GEOS no falla al
        #    guardarlos: falla HORAS DESPUÉS, en la primera intersección contra
        #    una tesela, y se lleva puesta la corrida entera. Se repara sólo lo
        #    inválido —`make_valid` sobre todo sería caro y tocaría lo sano— y se
        #    vuelve a (Multi)Polygon, porque la reparación puede devolver
        #    colecciones que el codificador de MVT no acepta.
        malas = ~shapely.is_valid(g)
        if malas.any():
            g[malas] = shapely.make_valid(g[malas])
            g[malas] = np.array([normalizar(x) for x in g[malas]], dtype=object)
            rotas[0] += int(malas.sum())
        b = shapely.bounds(g)
        codigos.extend(cod)
        wkbs.extend(shapely.to_wkb(g))
        cajas.append(b)
        leidas += len(cod)
        print(f"\r  {leidas:,} / {pf.metadata.num_rows:,}", end="", flush=True)
    cajas = np.vstack(cajas)
    print(f"\r  {leidas:,} manzanas convertidas y simplificadas "
          f"({time.time()-t0:,.0f}s)")
    return codigos, np.array(wkbs, dtype=object), cajas


def propiedades(codigos):
    """Nombre, municipio (sigep), si tiene ficha y los 91 indicadores."""
    print("leyendo datos…")
    mz = pd.read_csv(CAT / "manzana_2024.csv", dtype={"codigo": str})
    # ⚠️ EL MOTOR Y EL CATÁLOGO NO HABLAN EL MISMO IDIOMA, y `alias.py` es quien
    #    traduce: el motor emite `pct_rama_comercio` y el catálogo declara
    #    `pct_comercio`. Sin esta línea, NUEVE indicadores de los 91 no
    #    encontraban su columna y viajaban vacíos a las teselas —el mapa se veía
    #    bien, en gris, como si el INE no los publicara—.
    mz = renombrar(mz)
    mz = mz.set_index("codigo")
    # ★ SÓLO LO QUE EL TABLERO PUBLICA. El CSV del motor trae 96 columnas, pero
    #   cinco están EXCLUIDAS del nivel manzana por definición distinta
    #   (`comparables.json`): viajarían en cada tesela sin que nada las pueda
    #   mostrar. La lista sale del catálogo ya armado, que es quien decide.
    cat = json.loads((DATOS / "catalogo_manzana.json").read_text(encoding="utf-8"))
    publica = {i["key"] for g in cat["grupos"] for i in g["indicadores"]}
    claves = sorted(c for c in mz.columns if c in publica)
    sobran = sorted(set(mz.columns) - publica - {"codigo"})
    if sobran:
        print(f"  fuera de las teselas ({len(sobran)}): {', '.join(sobran)}")
    # ★★ LOS PORCENTAJES VAN SIN DECIMAL, Y NO ES PARA AHORRAR PESO: ES QUE EL
    #    DECIMAL NO EXISTE. Medido sobre las 131.801 manzanas con ficha, la
    #    mediana tiene 17 VIVIENDAS —el 80% tiene menos de 30—, así que una sola
    #    vivienda mueve el indicador 5,9 puntos. Publicar «63,9%» sobre esa base
    #    es afirmar una precisión 59 veces más fina que el dato. En el nivel
    #    municipal el decimal sí corresponde: ahí los denominadores son miles.
    #    · El ahorro es un efecto secundario, y es grande: medido sobre la tesela
    #      más pesada (z10, 27.584 manzanas), −27% del archivo. Con decimal el
    #      archivo daba 103,6 MB y GitHub rechaza todo lo que pase de 100.
    #    · LAS CUATRO RAZONES CONSERVAN SU DECIMAL. `densidad` va de 0,002 a
    #      1.000 hab/ha y redondearla dejaría en cero a la mitad rural;
    #      `tam_hogar` (3,58 personas), `indice_masculinidad` (100,3) y las
    #      brechas viven en un rango angosto donde el entero borra la señal.
    #      La unidad se LEE del catálogo, no se deduce del nombre.
    unid = {i["k"]: i.get("u") for i in
            json.loads((CAT / "catalogo.json").read_text(encoding="utf-8"))["indicadores"]}
    CON_DECIMAL = {"densidad", "indice_masculinidad", "tam_hogar"}
    mz = mz[claves]
    mz = mz.apply(lambda col: col.round(1 if col.name in CON_DECIMAL else 0))
    sin_dec = [k for k in claves if k not in CON_DECIMAL]
    print(f"  {len(sin_dec)} indicadores redondeados a entero · "
          f"{len(CON_DECIMAL & set(claves))} conservan un decimal")

    import pyarrow.parquet as pq
    nom = pq.read_table(FUENTE / "manzanos.parquet",
                        columns=["codigo", "nombre"]).to_pandas().set_index("codigo")
    pue = pd.read_parquet(RAIZ / "datos" / "manzano_municipio.parquet").set_index("codigo")
    pob = pq.read_table(FUENTE / "poblacion.parquet",
                        columns=["codigo", "validado"]).to_pandas().set_index("codigo")

    mz = mz.reindex(codigos)
    nom = nom.reindex(codigos)
    pue = pue.reindex(codigos)
    pob = pob.reindex(codigos)

    vals = {k: mz[k].to_numpy() for k in claves}
    nombres = nom["nombre"].fillna("").to_numpy()
    sigeps = pue["sigep"].fillna("").to_numpy()
    ficha = pob["validado"].fillna(False).to_numpy()
    print(f"  {len(claves)} indicadores · {int(ficha.sum()):,} manzanas con ficha")
    return claves, vals, nombres, sigeps, ficha


def main():
    t0 = time.time()
    codigos, wkbs, cajas = preparar()
    claves, vals, nombres, sigeps, ficha = propiedades(codigos)

    minx, miny = cajas[:, 0].min(), cajas[:, 1].min()
    maxx, maxy = cajas[:, 2].max(), cajas[:, 3].max()
    print(f"  bbox mercator  x {minx:,.0f}..{maxx:,.0f}   y {miny:,.0f}..{maxy:,.0f}")

    # ── agrupar por tesela de ZMIN ───────────────────────────────────────────
    lado0 = 2 * MUNDO / (2 ** ZMIN)
    bx0 = ((cajas[:, 0] + MUNDO) // lado0).astype(int)
    bx1 = ((cajas[:, 2] + MUNDO) // lado0).astype(int)
    by0 = ((MUNDO - cajas[:, 3]) // lado0).astype(int)
    by1 = ((MUNDO - cajas[:, 1]) // lado0).astype(int)
    bloques = {}
    for i in range(len(codigos)):
        for tx in range(bx0[i], bx1[i] + 1):
            for ty in range(by0[i], by1[i] + 1):
                bloques.setdefault((tx, ty), []).append(i)
    print(f"  {len(bloques)} bloques de z{ZMIN} · "
          f"el mayor con {max(len(v) for v in bloques.values()):,} manzanas")

    DATOS.mkdir(parents=True, exist_ok=True)
    escritas, saltadas = 0, [0]
    with open(SALIDA, "wb") as fh:
        w = Writer(fh)
        for n_b, ((tx0, ty0), idx) in enumerate(sorted(bloques.items()), 1):
            idx = np.array(idx)
            # los vecinos entran al bloque: sin ellos las manzanas del borde se
            # cortarían en la costura entre teselas de bloques distintos
            bb = box(*tile_bounds(ZMIN, tx0, ty0)).buffer(lado0 * BUFFER / EXTENT)
            cerca = idx[(cajas[idx, 2] >= bb.bounds[0]) & (cajas[idx, 0] <= bb.bounds[2]) &
                        (cajas[idx, 3] >= bb.bounds[1]) & (cajas[idx, 1] <= bb.bounds[3])]
            if not len(cerca):
                continue
            geoms = shapely.from_wkb(list(wkbs[cerca]))
            arbol = STRtree(geoms)
            props = []
            for k in cerca:
                p = {"s": sigeps[k], "nom": nombres[k]}
                if ficha[k]:
                    p["f"] = 1
                for c in claves:
                    v = vals[c][k]
                    # ausente y cero son cosas distintas: el mapa distingue "sin
                    # ficha" de "cero" con `["has", clave]`
                    if v == v:      # not NaN
                        p[c] = float(v)
                props.append(p)

            for z in range(ZMIN, ZMAX + 1):
                f = 2 ** (z - ZMIN)
                lado = 2 * MUNDO / (2 ** z)
                bmundo = lado * BUFFER / EXTENT
                tol = lado / EXTENT * 0.5
                for tx in range(tx0 * f, (tx0 + 1) * f):
                    for ty in range(ty0 * f, (ty0 + 1) * f):
                        cx0, cy0, cx1, cy1 = tile_bounds(z, tx, ty)
                        caja = box(cx0 - bmundo, cy0 - bmundo, cx1 + bmundo, cy1 + bmundo)
                        hit = arbol.query(caja)
                        if len(hit) == 0:
                            continue
                        feats = []
                        for k in hit:
                            g = geoms[k]
                            try:
                                if not g.intersects(caja):
                                    continue
                                g = normalizar(g.intersection(caja))
                            except Exception:
                                # que una manzana imposible no se lleve la
                                # corrida: se cuenta y se informa al final
                                saltadas[0] += 1
                                continue
                            if g is None:
                                continue
                            g = normalizar(g.simplify(tol, preserve_topology=True))
                            if g is None or g.is_empty:
                                continue
                            feats.append({"geometry": g, "properties": props[k]})
                        if not feats:
                            continue
                        tile = mapbox_vector_tile.encode(
                            {"name": CAPA, "features": feats},
                            default_options={
                                "quantize_bounds": (cx0, cy0, cx1, cy1),
                                "extents": EXTENT,
                                "on_invalid_geometry": on_invalid_geometry_make_valid,
                            })
                        if not tile:
                            continue
                        # ⚠️ `write_tile` NO comprime y el encabezado declara GZIP:
                        #    sin esto el archivo queda mal formado. De paso es la
                        #    mitad del peso.
                        w.write_tile(zxy_to_tileid(z, tx, ty), gzip.compress(tile, 9))
                        escritas += 1
            del geoms, arbol, props
            print(f"\r  bloque {n_b}/{len(bloques)} · {escritas:,} teselas "
                  f"· {time.time()-t0:,.0f}s", end="", flush=True)

        print()

        def inv(mx, my):
            lon = math.degrees(mx / R)
            lat = math.degrees(2 * math.atan(math.exp(my / R)) - math.pi / 2)
            return lon, lat
        lo, hi = inv(minx, miny), inv(maxx, maxy)
        w.finalize(
            {"tile_type": TileType.MVT, "tile_compression": Compression.GZIP,
             "min_zoom": ZMIN, "max_zoom": ZMAX,
             "min_lon_e7": int(lo[0] * 1e7), "min_lat_e7": int(lo[1] * 1e7),
             "max_lon_e7": int(hi[0] * 1e7), "max_lat_e7": int(hi[1] * 1e7),
             "center_zoom": ZMIN,
             "center_lon_e7": int((lo[0] + hi[0]) / 2 * 1e7),
             "center_lat_e7": int((lo[1] + hi[1]) / 2 * 1e7)},
            {"attribution": "INE · Censo 2024, fichas por manzano",
             "vector_layers": [{"id": CAPA, "minzoom": ZMIN, "maxzoom": ZMAX,
                                "fields": {**{k: "Number" for k in claves},
                                           "s": "String", "nom": "String",
                                           "f": "Number"}}]})
    mb = SALIDA.stat().st_size / 1e6
    print(f"\n{SALIDA.name}: {escritas:,} teselas · {mb:.1f} MB · {time.time()-t0:,.0f}s")


if __name__ == "__main__":
    main()
