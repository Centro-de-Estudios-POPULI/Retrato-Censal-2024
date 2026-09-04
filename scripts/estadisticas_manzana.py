# -*- coding: utf-8 -*-
"""
ESTADÍSTICAS DEL NIVEL MANZANA — el precio de pasar a teselas.
===============================================================

Port nacional. La lógica es la misma que en el tablero metropolitano y los
números que emite tienen que seguir siendo los mismos que calcularía el
navegador; lo único que cambia es DE DÓNDE salen los valores: allá de los
`dat_<muni>.json` que ya vivían partidos por municipio, acá del CSV del motor
(`catalogo/manzana_2024.csv`, 247.429 × 96) más el puente manzano→municipio.

Con PMTiles el navegador sólo ve las teselas del viewport, así que lo que antes
se computaba sobre la marcha hay que **precalcularlo**: es `escala()` movido de
tiempo de ejecución a tiempo de armado.

Produce `docs/datos/mz_stats.json` con dos bloques por indicador:

  `esc`  — q02/q98 (el dominio dibujado), pivote ponderado por personas, mín,
           máx, n y una rejilla de cuantiles, para que el tooltip pueda decir en
           qué percentil cae una manzana sin tener las 131.801 al lado.
  `dist` — la distribución DENTRO de cada municipio (min · p10 · p25 · p50 · p75
           · p90 · max, y n), que es lo que dibuja la tira del panel derecho.

★ POR QUÉ LA TIRA: la desigualdad dentro de un municipio suele ser mayor que
  todo el rango entre municipios. El comparativo de barras retrata la variación
  ENTRE; sin esto, la mayor de las dos no se ve en ninguna parte. El número
  exacto se recalcula al final de esta corrida para que no sea una afirmación
  suelta: si deja de ser cierto, se ve.

⚠️ EL UNIVERSO SON LAS MANZANAS CON FICHA. Las que el INE suprime por privacidad
   no son ceros: meterlas como 0 inventaría un piso de carencia que no está en
   el dato. Acá eso sale gratis porque esas filas vienen vacías del motor.

    python scripts/estadisticas_manzana.py
"""
import gzip, json, pathlib
import numpy as np
import pandas as pd

import sys as _sys
_sys.stdout.reconfigure(encoding="utf-8")
_sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "catalogo"))
from alias import renombrar

RAIZ = pathlib.Path(__file__).resolve().parent.parent
DATOS = RAIZ / "docs" / "datos"
SALIDA = DATOS / "mz_stats.json"
CORTES = [i / 50 for i in range(51)]     # 51 cortes: cada 2%
MIN_MZ = 30                              # con menos, los deciles no dicen nada


def cuantil(ord_, q):
    """Idéntica a `cuantil()` del tablero: interpolación lineal entre vecinos."""
    if len(ord_) == 0:
        return None
    h = (len(ord_) - 1) * q
    b = int(h)
    r = h - b
    return float(ord_[b] + r * (ord_[b + 1] - ord_[b])) if b + 1 < len(ord_) else float(ord_[b])


def r1(v):
    return None if v is None else round(v, 1)


def main():
    cat = json.loads((DATOS / "catalogo_manzana.json").read_text(encoding="utf-8"))
    orden = [i["key"] for g in cat["grupos"] for i in g["indicadores"]]
    mun = json.loads((DATOS / "municipios_manzana.json").read_text(encoding="utf-8"))

    print("leyendo el motor…")
    # ⚠️ Se lee ENTERO y después se traduce: `usecols` con los nombres del
    #    catálogo dejaba fuera las nueve columnas que el motor llama distinto
    #    (`pct_rama_comercio` → `pct_comercio`). Ver `alias.py`.
    mz = renombrar(pd.read_csv(RAIZ / "catalogo" / "manzana_2024.csv",
                               dtype={"codigo": str}))
    mz = mz[[c for c in mz.columns if c in set(orden) | {"codigo", "pob_total"}]]
    pue = pd.read_parquet(RAIZ / "datos" / "manzano_municipio.parquet")
    mz = mz.merge(pue[["codigo", "sigep"]], on="codigo", how="left")
    # ⚠️ El peso del pivote es la GENTE de la manzana, no su superficie ni su
    #    cuenta: un promedio simple de manzanas le da el mismo peso a una de 20
    #    personas que a una de 2.000. Es la misma regla del motor municipal.
    peso = mz["pob_total"].to_numpy(dtype=float)
    sig = mz["sigep"].to_numpy()
    print(f"  {len(mz):,} manzanas · {len(orden)} indicadores del catálogo")

    out = {}
    for k in orden:
        if k not in mz.columns:
            continue
        v = mz[k].to_numpy(dtype=float)
        ok = np.isfinite(v)
        if not ok.any():
            continue
        vv, pp, ss = v[ok], peso[ok], sig[ok]
        ordenados = np.sort(vv)
        sw = np.nansum(pp)
        piv = (float(np.nansum(vv * np.nan_to_num(pp)) / sw) if sw > 0
               else cuantil(ordenados, .5))

        dist = {}
        d = pd.DataFrame({"s": ss, "v": vv})
        for s, g in d.groupby("s", sort=False):
            if len(g) < MIN_MZ:
                continue
            a = np.sort(g["v"].to_numpy())
            dist[s] = {
                "n": int(len(a)),
                # ★ min y max ADEMÁS de los deciles: el bigote p10-p90 cubre el
                #   80% central y deja fuera una manzana de cada diez en cada
                #   punta. No es el rango, y confundirlos hace parecer que el
                #   mínimo del municipio es el p10.
                "min": r1(float(a[0])), "max": r1(float(a[-1])),
                "p10": r1(cuantil(a, .10)), "p25": r1(cuantil(a, .25)),
                "p50": r1(cuantil(a, .50)), "p75": r1(cuantil(a, .75)),
                "p90": r1(cuantil(a, .90)),
            }
        out[k] = {
            "esc": {
                "lo": r1(cuantil(ordenados, .02)), "hi": r1(cuantil(ordenados, .98)),
                "piv": r1(piv), "tipo": "país" if sw > 0 else "mediana",
                "min": r1(float(ordenados[0])), "max": r1(float(ordenados[-1])),
                "n": int(len(ordenados)),
                "q": [r1(cuantil(ordenados, c)) for c in CORTES],
            },
            "dist": dist,
        }

    SALIDA.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")),
                      encoding="utf-8")
    b = SALIDA.read_bytes()
    print(f"{SALIDA.name}: {len(out)} indicadores · {len(b)/1024:.0f} KB "
          f"({len(gzip.compress(b,9))/1024:.0f} KB gzip)")
    print(f"  distribución en {sum(len(v['dist']) for v in out.values()):,} "
          f"pares indicador×municipio")

    gana = 0
    for k, v in out.items():
        entre = [m["municipal"].get(k) for m in mun
                 if m.get("municipal", {}).get(k) is not None]
        if len(entre) < 8 or not v["dist"]:
            continue
        rango = max(entre) - min(entre)
        dentro = np.sort([d["p90"] - d["p10"] for d in v["dist"].values()])
        if cuantil(dentro, .5) > rango:
            gana += 1
    print(f"  en {gana} de {len(out)} indicadores la desigualdad DENTRO de un "
          f"municipio supera el rango ENTRE los 343")


if __name__ == "__main__":
    main()
