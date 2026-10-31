# -*- coding: utf-8 -*-
"""
COMPARAR ZONAS — los conteos de cada manzana para sumar cualquier círculo.
==========================================================================

Mismo modo que el tablero de la Gobernación (2026-10-30): el lector pone dos
círculos en el mapa (A y B) y el panel compara lo que vive adentro de cada uno.
El navegador tiene que poder SUMAR manzanas: viajan numeradores y
denominadores, nunca porcentajes (promediar porcentajes le daría a una manzana
de 12 personas el mismo peso que a una de 900).

★ A ESCALA PAÍS NO SE BAJA TODO. Son 247.429 manzanas: se parten en las
  teselas z8 del mapa (unos 150 km de lado) según su punto representativo, y
  cada zona —radio de 5 km como mucho— baja sólo los pedazos que toca, y de
  cada pedazo sólo la categoría que está mirando.

Produce `docs/datos/zonas/`:

  `indice.json`       — pedazos (`clave → caja y cantidad`), `sigep` de cada
                        índice de municipio, tramos de edad, y por categoría el
                        mapa {clave: [columna num, columna den, factor]} que
                        comparten todos los pedazos. Formas especiales:
                        [col, -1, 1] = suma (población); ["bre", muj, hom] =
                        brecha mujeres − hombres de dos claves del mismo grupo.
  `<x>_<y>/base.json` — una fila por manzana del pedazo: `id` de la tesela
                        (diferencias), punto en cienmilésimas de grado
                        (diferencias), municipio, personas, si tiene ficha y
                        las ocho columnas de edad × sexo.
  `<x>_<y>/g_<grupo>.json` — `cols`: los conteos enteros de esa categoría, sólo
                        de las manzanas CON ficha y en su orden. Personas («p»),
                        viviendas («v») y superficie en m² («a») van en la base,
                        para todas: el mapa de la categoría las nombra por letra.

Se verifica, indicador por indicador, que el cociente de una manzana sola dé
su valor publicado en `docs/datos/col/` (los porcentajes viajan SIN decimal:
la tolerancia es medio punto).

    python scripts/zonas_manzana.py
"""
import gzip, json, math, pathlib, shutil, sys

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

sys.stdout.reconfigure(encoding="utf-8")
RAIZ = pathlib.Path(__file__).resolve().parent.parent
DATOS = RAIZ / "docs" / "datos"
SALIDA = DATOS / "zonas"
sys.path.insert(0, str(RAIZ / "catalogo"))

Q = 100_000          # cienmilésimas de grado (~1 m)
ZP = 8               # nivel de zoom de los pedazos
BRECHAS = {"brecha_edu_superior": "pct_edu_superior", "brecha_edu_ninguno": "pct_sin_educacion",
           "brecha_sin_seguro": "pct_sin_seguro", "brecha_cuenta_propia": "pct_cuenta_propia"}


def tesela(lon, lat, z=ZP):
    n = 2 ** z
    x = np.floor((lon + 180) / 360 * n).astype(int)
    la = np.radians(lat)
    y = np.floor((1 - np.log(np.tan(la) + 1 / np.cos(la)) / math.pi) / 2 * n).astype(int)
    return x, y


def enteros(a):
    return [int(v) for v in np.rint(np.nan_to_num(np.asarray(a, dtype=float))).astype(np.int64)]


def deltas(a):
    a = np.asarray(a, dtype=np.int64)
    return [int(v) for v in np.diff(a, prepend=0)]


def main():
    import geopandas as gpd
    from motor_manzana import FUENTE, numeradores

    cols_pub = json.loads((DATOS / "columnas.json").read_text(encoding="utf-8"))
    # ── el orden de la tesela: la fila de `manzanos.parquet` ES el `id` ─────
    g = gpd.read_parquet(FUENTE / "manzanos.parquet", columns=["codigo", "geometry"])
    n = len(g)
    if n != cols_pub["n"]:
        sys.exit(f"⛔ {n} manzanas y el manifiesto declara {cols_pub['n']}")
    # la superficie se mide en UTM 20S (igual que `areas_m2()`), con la misma lectura
    area = pd.Series(g.geometry.to_crs(32720).area.values, index=g.codigo.astype(str).values)
    if g.crs is not None and g.crs.to_epsg() != 4326:
        g = g.to_crs(4326)
    p = g.geometry.representative_point()
    lon, lat = p.x.values, p.y.values
    codigo = g.codigo.astype(str).values
    del g, p
    print(f"{n:,} manzanas, en el orden de las teselas")

    f = pd.read_parquet(FUENTE / "fichas.parquet")
    f["codigo"] = f.codigo.astype(str)
    f = f.set_index("codigo").reindex(codigo)
    pob = pd.read_parquet(FUENTE / "poblacion.parquet")
    pob = pob.assign(codigo=pob.codigo.astype(str)).set_index("codigo").reindex(codigo)
    area = area.reindex(codigo)
    ficha = f.notna().any(axis=1).values
    print(f"  con ficha: {int(ficha.sum()):,} · personas: {int(np.nansum(pob.personas.values)):,}")

    # ── municipio de cada manzana (el puente de `armar_municipios.py`) ─────
    puente = pd.read_parquet(RAIZ / "datos" / "manzano_municipio.parquet") \
        if (RAIZ / "datos" / "manzano_municipio.parquet").exists() else None
    mun = json.loads((DATOS / "municipios_manzana.json").read_text(encoding="utf-8"))
    sigeps = [m["sigep"] for m in mun]
    if puente is None:
        sys.exit("⛔ falta datos/manzano_municipio.parquet (lo escribe catalogo/armar_municipios.py)")
    puente = puente.assign(codigo=puente.codigo.astype(str)).set_index("codigo")
    col_s = "sigep" if "sigep" in puente.columns else [c for c in puente.columns if "sigep" in c][0]
    s_mz = puente[col_s].astype(str).reindex(codigo).values
    si = {s: k for k, s in enumerate(sigeps)}
    s_idx = np.array([si.get(s, 65535) for s in s_mz], dtype=np.int64)
    print(f"  sin municipio: {(s_idx == 65535).sum():,}")

    # ── numeradores y denominadores ─────────────────────────────────────
    nd = {k: (a, b, 100) for k, (a, b) in numeradores(f).items()}
    hs = [c for c in f.columns if c.startswith("edad_") and c.endswith("_hombre")]
    ms = [c for c in f.columns if c.startswith("edad_") and c.endswith("_mujer")]
    nd["indice_masculinidad"] = (f[hs].sum(axis=1), f[ms].sum(axis=1), 100)
    # personas, viviendas y superficie existen para TODAS las manzanas (también
    # las que el INE suprime en la ficha): viajan una sola vez, en la base
    # («p», «v», «a»), y las categorías las nombran por su letra
    BASE = {"p": pob.personas, "v": pob.viviendas, "a": area}
    nd["tam_hogar"] = ("p", "v", 1)
    nd["densidad"] = ("p", "a", 1e4)

    cat = json.loads((DATOS / "catalogo_manzana.json").read_text(encoding="utf-8"))

    def publicado(k):
        pth = DATOS / "col" / f"{k}.json"
        if not pth.exists():
            return None
        return np.array([np.nan if v is None else v for v in json.loads(pth.read_text(encoding="utf-8"))], float)

    serie = lambda x: BASE[x] if isinstance(x, str) else x

    def cociente(k):
        a, b, fac = nd[k]
        with np.errstate(divide="ignore", invalid="ignore"):
            return fac * np.asarray(serie(a), float) / np.asarray(serie(b), float)

    grupos, peor = {}, (None, 0.0)
    columnas = {}                    # grupo → lista de arrays enteros
    for gr in cat["grupos"]:
        cols, firma, ind = [], {}, {}

        def col(sr):
            if isinstance(sr, str):
                return sr                      # columna de la base
            v = np.rint(np.nan_to_num(np.asarray(sr, dtype=float))).astype(np.int64)
            h = hash(v.tobytes())
            if h not in firma:
                firma[h] = len(cols)
                cols.append(v)
            return firma[h]

        for i in gr["indicadores"]:
            k = i["k_mz"]
            if k in BRECHAS:
                base = BRECHAS[k]
                for sx in ("muj", "hom"):
                    kk = f"{base}__{sx}"
                    a, b, fac = nd[kk]
                    ind[kk] = [col(a), col(b), fac]
                ind[k] = ["bre", f"{base}__muj", f"{base}__hom"]
                v = cociente(f"{base}__muj") - cociente(f"{base}__hom")
            elif i.get("agg") == "suma":
                ind[k] = ["p", -1, 1]
                v = np.asarray(pob.personas, float)
            else:
                if k not in nd:
                    sys.exit(f"⛔ {gr['key']}: sin numerador y denominador para {k}")
                a, b, fac = nd[k]
                ind[k] = [col(a), col(b), fac]
                v = cociente(k)
            pub = publicado(k)
            if pub is not None:
                ok = np.isfinite(pub) & np.isfinite(v)
                d = float(np.max(np.abs(v[ok] - pub[ok]))) if ok.any() else 0.0
                if d > peor[1]:
                    peor = (k, d)
                tol = 1.01 if k in BRECHAS else (.51 if i.get("unit") == "%" else .06)
                if k == "densidad":
                    tol = 1.0
                if d > tol:
                    mal = int((np.abs(v[ok] - pub[ok]) > tol).sum())
                    print(f"  ⚠️ {k}: {mal} manzanas se apartan más de {tol} de su valor publicado (máx {d:.2f})")
        grupos[gr["key"]] = ind
        columnas[gr["key"]] = cols
    print(f"  verificado contra datos/col/: peor diferencia {peor[1]:.3f} ({peor[0]})")

    # ── los pedazos ─────────────────────────────────────────────────────
    tx, ty = tesela(lon, lat)
    clave = np.array([f"{a}_{b}" for a, b in zip(tx, ty)])
    if SALIDA.exists():
        shutil.rmtree(SALIDA)
    SALIDA.mkdir(parents=True)
    xq = np.rint(lon * Q).astype(np.int64)
    yq = np.rint(lat * Q).astype(np.int64)
    pers = np.rint(np.nan_to_num(pob.personas.values.astype(float))).astype(np.int64)
    vivs = np.rint(np.nan_to_num(pob.viviendas.values.astype(float))).astype(np.int64)
    sup = np.rint(np.nan_to_num(area.values.astype(float))).astype(np.int64)
    edad_h = [np.rint(np.nan_to_num(f[c].values.astype(float))).astype(np.int64) for c in hs]
    edad_m = [np.rint(np.nan_to_num(f[c].values.astype(float))).astype(np.int64) for c in ms]
    pedazos, total_gz = {}, 0
    for c in sorted(set(clave)):
        idx = np.nonzero(clave == c)[0]                 # ya en orden de id
        d = SALIDA / c
        d.mkdir()
        base = {"n": int(len(idx)), "id": deltas(idx), "x": deltas(xq[idx]), "y": deltas(yq[idx]),
                "s": [int(v) for v in s_idx[idx]], "p": [int(v) for v in pers[idx]],
                "v": [int(v) for v in vivs[idx]], "a": [int(v) for v in sup[idx]],
                "f": [int(v) for v in ficha[idx]],
                "eh": [[int(v) for v in a[idx]] for a in edad_h], "em": [[int(v) for v in a[idx]] for a in edad_m]}
        (d / "base.json").write_text(json.dumps(base, separators=(",", ":")), encoding="utf-8")
        # los conteos de las categorías, SÓLO de las manzanas con ficha (en el
        # mismo orden): las demás eran ceros y la mitad del peso
        fidx = idx[ficha[idx]]
        for gk, cols in columnas.items():
            (d / f"g_{gk}.json").write_text(json.dumps({"cols": [[int(v) for v in a[fidx]] for a in cols]},
                                                        separators=(",", ":")), encoding="utf-8")
        pedazos[c] = {"n": int(len(idx)), "con_ficha": int(ficha[idx].sum()),
                      "caja": [round(float(lon[idx].min()), 5), round(float(lat[idx].min()), 5),
                               round(float(lon[idx].max()), 5), round(float(lat[idx].max()), 5)]}
        total_gz += sum(len(gzip.compress(p_.read_bytes(), 6)) for p_ in d.iterdir())
    indice = {"n": n, "q": Q, "z": ZP, "sigeps": sigeps, "tramos": ["0-19", "20-39", "40-59", "60+"],
              "personas": int(pers.sum()), "pedazos": pedazos, "grupos": grupos}
    (SALIDA / "indice.json").write_text(json.dumps(indice, separators=(",", ":")), encoding="utf-8")
    crudo = sum(p_.stat().st_size for p_ in SALIDA.rglob("*") if p_.is_file())
    grande = max(pedazos.items(), key=lambda kv: kv[1]["n"])
    print(f"  {len(pedazos)} pedazos · {crudo / 1e6:,.1f} MB en disco · {total_gz / 1e6:,.1f} MB comprimido")
    print(f"  el pedazo más grande: {grande[0]} con {grande[1]['n']:,} manzanas")


if __name__ == "__main__":
    main()
