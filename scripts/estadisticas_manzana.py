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


def contraste(ordenados, lo, piv, hi):
    """Cuánta rampa separa al cuartil de abajo del de arriba.

    Es la medida de si un mapa se puede LEER: con 0,10 los municipios típicos
    caen todos en el mismo tono y la variación no se ve, aunque la rampa entera
    esté declarada. Réplica exacta de `posEnRampa()` del tablero, incluido el
    recorte del 8% que impide que el pivote se pegue a un borde."""
    pad = (hi - lo) * .08
    pv = min(max(piv, lo + pad), hi - pad)
    ps = []
    for v in ordenados:
        if v <= pv:
            t = .5 if pv == lo else .5 * (v - lo) / (pv - lo)
        else:
            t = .5 + .5 * (v - pv) / (hi - pv)
        ps.append(max(0.0, min(1.0, t)))
    ps.sort()
    return cuantil(ps, .75) - cuantil(ps, .25)


def escala_unica(cat, out, mun):
    """★★ UN SOLO DOMINIO Y UN SOLO CENTRO POR INDICADOR, PARA LOS DOS NIVELES.

    ⛔ EL DEFECTO QUE ESTO ARREGLA (medido 2026-09-04): cada nivel armaba su
       escala por su cuenta —el municipal con el agregado del país, el de manzana
       con el suyo— y los dos centros no coincidían. Medido sobre los 74 que
       existen en ambos: el centro salta más de 5 puntos en 30 indicadores y
       hasta 24,5 en «recojo formal de basura». O sea que **el mismo valor
       cambiaba de color al cruzar el zoom**, que es justo lo contrario de lo que
       este tablero promete.

    ⚠️ Y NO ALCANZA CON ELEGIR UNA DE LAS DOS MEDIANAS. Las dos distribuciones son
       genuinamente distintas y no por ruido: la mitad de los municipios son
       chicos y rurales, la mitad de las manzanas están en ciudades. En
       alcantarillado el municipio típico tiene 17,3% y la manzana típica 75,0%.
       Con el centro en la mediana municipal, el 92% de las manzanas de «piso de
       tierra» cae de un solo lado y el contraste dentro de la ciudad se desploma
       de 0,55 a 0,16 — se pierde justo la desigualdad intraurbana que este nivel
       existe para mostrar.

    ⇒ El centro se BUSCA: el valor que deja el mejor contraste en el PEOR de los
      dos niveles. No pretende ser una estadística, y por eso la leyenda no lo
      rotula como tal: marca aparte el país y las dos medianas, que sí lo son.
    """
    vals_mun = {}
    for f in mun:
        for k, v in (f.get("municipal") or {}).items():
            if v is not None and np.isfinite(v):
                vals_mun.setdefault(k, []).append(float(v))

    n_ok, saltos = 0, []
    for g in cat["grupos"]:
        for i in g["indicadores"]:
            k = i["key"]
            st_ = out.get(k)
            vm = sorted(vals_mun.get(i.get("k_mun") or "", []))
            if not st_ or len(vm) < 50:
                continue
            q = [x for x in st_["esc"]["q"] if x is not None]
            if len(q) < 20:
                continue
            # ★ LOS TRES PARÁMETROS SE BUSCAN JUNTOS, no sólo el centro.
            #   Medido: con el dominio fijado a la unión de los dos —lo primero
            #   que probé— la escala única quedaba PEOR que las dos separadas
            #   (0,22 de contraste en el peor nivel contra 0,26, y 41
            #   indicadores ilegibles contra 32). El problema no era el centro
            #   sino los bordes: la unión estira el dominio hasta cubrir la cola
            #   del nivel más disperso y aplasta al otro.
            #   Buscando los tres sobre la distribución AGRUPADA, la escala única
            #   pasa a ser MEJOR que las dos que reemplaza: 0,33 y 24 ilegibles.
            #   El recorte no pasa del 5% por punta y la leyenda ya lo dice con
            #   sus «≤» y «≥».
            pool = sorted(vm + q)
            mejor, cbest = None, -1
            for pl in (0, .01, .02, .05):
                for ph in (1, .99, .98, .95):
                    l, h = cuantil(pool, pl), cuantil(pool, ph)
                    if h <= l:
                        continue
                    for j in range(5, 96):
                        pv = l + (h - l) * j / 100
                        c = min(contraste(vm, l, pv, h), contraste(q, l, pv, h))
                        if c > cbest:
                            cbest, mejor = c, (l, pv, h)
            if mejor is None:
                continue
            i["esc"] = [round(mejor[0], 4), round(mejor[1], 4), round(mejor[2], 4)]
            # las referencias que SÍ significan algo, para que la leyenda las marque
            i["ref"] = {"pais": cat["region"]["municipal"].get(i.get("k_mun")),
                        "med_mun": round(cuantil(vm, .5), 2),
                        "med_mz": round(cuantil(q, .5), 2)}
            n_ok += 1
            saltos.append(cbest)
    (DATOS / "catalogo_manzana.json").write_text(
        json.dumps(cat, ensure_ascii=False), encoding="utf-8")
    print(f"escala única declarada en {n_ok} indicadores · contraste del peor nivel: "
          f"mediana {np.median(saltos):.2f} · bajo 0,20: {sum(1 for c in saltos if c < .20)}")


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

    escala_unica(cat, out, mun)

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
