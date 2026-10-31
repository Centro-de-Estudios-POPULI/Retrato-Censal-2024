# -*- coding: utf-8 -*-
"""
LAS CIFRAS POR PROVINCIA Y POR DEPARTAMENTO.
=============================================

Pedido de Carlos (2026-10-31): «que en el panel derecho las barras sean por
municipio y/o provincia, no que salgan la lista de los 343 municipios». El panel
pasa a comparar dentro de un ÁMBITO —Bolivia › departamento › provincia— y para
eso hacen falta cifras de provincia y de departamento que no existían.

★ SE CALCULAN COMO LA DEL PAÍS, Y POR ESO SE PUEDEN PONER AL LADO. La cifra
  «país» que ya muestra el tablero la arma `region()` de
  `catalogo/armar_tableros.py`: el promedio de los municipios ponderado por el
  UNIVERSO de cada indicador (`_den_<clave>` del motor, o el total del bloque:
  viviendas para lo de vivienda, personas para lo de personas). Acá se aplica
  la MISMA función a cada provincia y cada departamento. La prueba de que es la
  misma cuenta: agrupando a los 343 juntos sale exactamente el «país» publicado
  (se verifica al correr; si no da, no escribe).

★ LOS SÓLO-MANZANA SALEN DE LAS MANZANAS. Para los 17 que el microdato
  municipal no separa, la cifra de un municipio ya es la suma de sus manzanas
  urbanas (`armar_tableros.py`); la de una provincia es lo mismo con más
  manzanas: Σ numerador / Σ denominador, con `numeradores()` del motor —la misma
  de «Comparar zonas»—. Nunca un promedio de porcentajes. La verificación:
  agrupando por municipio tiene que salir la cifra que ya publica cada uno.
  Y de paso esos 17 ganan su cifra del PAÍS (las manzanas urbanas de todo el
  país), que hasta hoy faltaba y el panel decía «país s/d».

★ LOS CONTEOS SE SUMAN (población).

Produce `docs/datos/territorios.json`:
  `dptos`  — [{cod, nombre, v: {clave: cifra}}]
  `provs`  — [{cod, nombre, dpto, v}]   (114 provincias del mapa maestro)
  `mun`    — {sigep: cod_prov}
  `pais`   — {clave: cifra} de los sólo-manzana (los otros ya están en el catálogo)

    python scripts/agregados_territoriales.py
"""
import csv, gzip, json, pathlib, sys

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
RAIZ = pathlib.Path(__file__).resolve().parent.parent
DATOS = RAIZ / "docs" / "datos"
SALIDA = DATOS / "territorios.json"
sys.path.insert(0, str(RAIZ / "catalogo"))

BRECHAS = {"brecha_edu_superior": "pct_edu_superior", "brecha_edu_ninguno": "pct_sin_educacion",
           "brecha_sin_seguro": "pct_sin_seguro", "brecha_cuenta_propia": "pct_cuenta_propia"}


def r3(v):
    return None if v is None or not np.isfinite(v) else round(float(v), 3)


def main():
    from armar_tableros import cargar, region, FUENTES24, SPINE
    from motor_manzana import FUENTE, numeradores

    cat = json.loads((DATOS / "catalogo_manzana.json").read_text(encoding="utf-8"))
    inds = [i for g in cat["grupos"] for i in g["indicadores"]]
    mun = json.loads((DATOS / "municipios_manzana.json").read_text(encoding="utf-8"))
    sp = {r["cod_ine"]: r for r in csv.DictReader(open(SPINE, encoding="utf-8"))}
    faltan = [m["cod_ine"] for m in mun if m["cod_ine"] not in sp]
    if faltan:
        sys.exit(f"⛔ municipios sin fila en el mapa maestro: {faltan}")

    # ── los ámbitos ─────────────────────────────────────────────────────
    #    ★ La provincia sale del CÓDIGO INE (`cod_prov`), no del nombre. El
    #      mapa maestro rotula a la autonomía Jatun Ayllu Yura (051204) «Tomás
    #      Frías», pero su código la pone en la provincia 12 de Potosí, Antonio
    #      Quijarro. Va donde dice el código, y el nombre de cada provincia es el
    #      que llevan la mayoría de sus municipios.
    from collections import Counter
    provs, dptos = {}, {}
    for m in mun:
        r = sp[m["cod_ine"]]
        p = provs.setdefault(r["cod_prov"], {"cod": r["cod_prov"], "nombres": Counter(),
                                             "dpto": r["cod_dep"], "cods": []})
        p["cods"].append(m["cod_ine"]); p["nombres"][r["provincia"]] += 1
        dptos.setdefault(r["cod_dep"], {"cod": r["cod_dep"], "nombre": r["dpto"], "cods": []})["cods"].append(m["cod_ine"])
    for p in provs.values():
        p["nombre"] = p["nombres"].most_common(1)[0][0]
    todos = [m["cod_ine"] for m in mun]
    print(f"{len(mun)} municipios · {len(provs)} provincias · {len(dptos)} departamentos")

    # ── 1 · los verificados: la cuenta del país, por ámbito ─────────────────
    v24, d24 = cargar(FUENTES24, "2024")
    ks = [i["k_mun"] for i in inds if not i.get("solo_mz") and i.get("k_mun")]
    publicado = cat["region"]["municipal"]
    peor = (None, 0.0)
    pais_rec = region(v24, d24, ks, todos)
    for k in ks:
        if k in publicado and k in pais_rec:
            d = abs(publicado[k] - pais_rec[k])
            if d > peor[1]:
                peor = (k, d)
    if peor[1] > 1e-6:
        sys.exit(f"⛔ la cuenta no reproduce el «país» publicado: {peor}")
    print(f"  verificados: {len(ks)} · el país recalculado = el publicado (peor {peor[1]:.1e})")
    conteos = [i["k_mun"] for i in inds if i.get("agg") == "suma"]

    def agregar(cods):
        out = region(v24, d24, ks, cods)
        for k in conteos:                       # un conteo se SUMA
            if k in v24.columns:
                s = v24.loc[v24.index.isin(cods), k]
                out[k] = round(float(s.sum()), 3) if s.notna().any() else None
        return out

    # ── 2 · los sólo-manzana: Σ numerador / Σ denominador ────────────────
    solo = [i["k_mz"] for i in inds if i.get("solo_mz")]
    f = pd.read_parquet(FUENTE / "fichas.parquet")
    f["codigo"] = f.codigo.astype(str)
    pob = pd.read_parquet(FUENTE / "poblacion.parquet")
    pob["codigo"] = pob.codigo.astype(str)
    import geopandas as gpd
    g = gpd.read_parquet(FUENTE / "manzanos.parquet", columns=["codigo", "geometry"])
    area = pd.Series(g.geometry.to_crs(32720).area.values, index=g.codigo.astype(str).values)
    del g
    puente = pd.read_parquet(RAIZ / "datos" / "manzano_municipio.parquet")
    puente["codigo"] = puente.codigo.astype(str)
    base = pob.set_index("codigo")[["personas", "viviendas"]].join(area.rename("area"))
    base = base.join(puente.set_index("codigo")["cod_ine"])
    f = f.set_index("codigo").reindex(base.index)
    nd = {k: (a.to_numpy(float), b.to_numpy(float), 100) for k, (a, b) in numeradores(f.reset_index()).items()}
    nd["densidad"] = (base.personas.to_numpy(float), base.area.to_numpy(float), 1e4)
    cod = base.cod_ine.astype(str).to_numpy()

    def suma_mz(k, mask):
        """La cifra de un conjunto de manzanas: Σnum/Σden (brecha: mujeres − hombres)."""
        if k in BRECHAS:
            b = BRECHAS[k]
            vm, vh = suma_mz(f"{b}__muj", mask), suma_mz(f"{b}__hom", mask)
            return None if vm is None or vh is None else vm - vh
        if k not in nd:
            return None
        a, b, fac = nd[k]
        a, b = a[mask], b[mask]
        ok = np.isfinite(a) & np.isfinite(b)
        den = b[ok].sum()
        return fac * a[ok].sum() / den if den > 0 else None

    sin_nd = [k for k in solo if k not in nd and k not in BRECHAS]
    if sin_nd:
        sys.exit(f"⛔ sin numerador y denominador: {sin_nd}")
    # verificación contra la cifra que ya publica cada municipio
    peor = (None, None, 0.0)
    por_mun = {c: cod == c for c in todos}
    for m in mun:
        for k in solo:
            pub = (m.get("municipal") or {}).get(k)
            if pub is None:
                continue
            v = suma_mz(k, por_mun[m["cod_ine"]])
            if v is None:
                continue
            d = abs(v - pub)
            if d > peor[2]:
                peor = (m["nombre"], k, d)
    print(f"  sólo-manzana: {len(solo)} · contra la cifra de cada municipio, peor diferencia "
          f"{peor[2]:.3f} ({peor[1]}, {peor[0]})")
    if peor[2] > .05:
        sys.exit("⛔ la suma de manzanas no reproduce la cifra municipal publicada")

    # las cifras viajan como una fila por ámbito alineada con `claves` (el
    # nombre de cada indicador una sola vez, no 122)
    claves = [i["key"] for i in inds]
    k_de = {i["key"]: (i["k_mz"] if i.get("solo_mz") else i["k_mun"]) for i in inds}

    def ambito(cods):
        v = agregar(cods)
        mask = np.isin(cod, cods)
        for k in solo:
            v[k] = r3(suma_mz(k, mask))
        return [v.get(k_de[c]) for c in claves]

    salida = {
        "claves": claves,
        "dptos": [{"cod": d["cod"], "nombre": d["nombre"], "v": ambito(d["cods"])}
                  for d in sorted(dptos.values(), key=lambda x: x["cod"])],
        "provs": [{"cod": p["cod"], "nombre": p["nombre"], "dpto": p["dpto"], "v": ambito(p["cods"])}
                  for p in sorted(provs.values(), key=lambda x: x["cod"])],
        "mun": {m["sigep"]: sp[m["cod_ine"]]["cod_prov"] for m in mun},
        "pais": {k: r3(suma_mz(k, np.ones(len(cod), bool))) for k in solo},
    }
    # control: la suma de los departamentos en población = el total del país
    if conteos:
        k = conteos[0]
        j = claves.index(next(c for c in claves if k_de[c] == k))
        tot = sum(d["v"][j] or 0 for d in salida["dptos"])
        print(f"  {k}: suma de departamentos {tot:,.0f} · país {v24[k].sum():,.0f}")
    txt = json.dumps(salida, ensure_ascii=False, separators=(",", ":"))
    SALIDA.write_text(txt, encoding="utf-8")
    print(f"  -> {SALIDA.relative_to(RAIZ)}  {len(txt)/1024:.0f} KB "
          f"({len(gzip.compress(txt.encode('utf-8'), 9))/1024:.0f} KB gzip)")
    print("  país de los sólo-manzana:", ", ".join(f"{k} {v}" for k, v in salida["pais"].items()))


if __name__ == "__main__":
    main()
