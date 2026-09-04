# -*- coding: utf-8 -*-
"""
ARMA `datos/municipios.json` — LOS 343, CON SU CONTEXTO DE MANZANAS.
=====================================================================

Es el archivo que el tablero lee para saber qué municipios existen y con qué
metadatos se rotula cada ficha. La versión metropolitana traía nueve entradas
escritas a mano; acá son los 343 de la espina madre (`bo-geo-maestro`), que es
la única lista de municipios que este ecosistema reconoce.

Cada entrada lleva, además del nombre y las dos claves (INE y SIGEP):

  · `manzanas`         cuántos manzanos tiene el municipio en el geoportal
  · `con_ficha`        cuántos de esos traen ficha (el INE suprime los chicos)
  · `personas_urbano`  la gente que vive en manzano — TODOS, con ficha o sin ella
  · `viviendas_urbano` idem viviendas

★ LOS CONTEOS SALEN DE `poblacion.parquet`, NO DE LAS FICHAS. Población y
  viviendas existen para los 247.429 manzanos, incluidos los ~116k que el INE
  suprime por privacidad; sólo los indicadores de ficha faltan ahí. Contar la
  gente sobre los que tienen ficha subestimaría el universo urbano de cada
  municipio y dejaría la cobertura peor de lo que es.

⚠️ EL PUENTE MANZANO→MUNICIPIO ES POR NOMBRE, no por código: el geoportal
   rotula departamento y municipio en texto y no publica el código INE. Se
   normaliza contra `nombre_censo` y `nombre` de la espina —los dos, porque el
   censo escribe algunos distinto— y al final se INFORMA qué porcentaje quedó
   sin identificar. Si ese número no es ~100%, hay municipios cuyas manzanas se
   están perdiendo en silencio.

    python catalogo/armar_municipios.py
"""
import csv, json, pathlib, unicodedata
import pandas as pd

import sys as _sys
_sys.stdout.reconfigure(encoding="utf-8")  # la consola de Windows es cp1252

AQUI = pathlib.Path(__file__).parent
RAIZ = AQUI.parent
FUENTE = RAIZ / "fuente"
SALIDA = RAIZ / "datos" / "municipios.json"
SPINE = pathlib.Path(r"C:\Users\HP\OneDrive\Desktop\Proyectos\bo-geo-maestro\spine\municipios.csv")


def norm(s):
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace("-", " ").split())


# ★ LOS SEIS QUE EL NOMBRE NO CRUZA — DECLARADOS UNO POR UNO, NO ADIVINADOS.
#   Medido: con el puente por nombre solo, 2.287 manzanos (0,92%) se quedaban
#   sin municipio, y no eran ruido: son cinco AUTONOMÍAS INDÍGENAS, que el
#   geoportal rotula por el nombre de su autonomía ("AIOC de Salinas") mientras
#   la espina las tiene por el nombre del municipio ("Salinas de Garci Mendoza"),
#   más un error de tipeo del geoportal ("Vitiche" por "Vitichi").
#   Se resuelven a mano y no por parecido de texto: un emparejamiento difuso que
#   acierta cinco veces también puede errar la sexta sin que nada avise, y acá
#   errar significa mandarle las manzanas de un municipio a otro.
#   ⚠️ El mismo puente vive en `motor_manzana.py` del pipeline metropolitano, y
#      allá esta corrección NO está: su agregado municipal sale con 340 y no 346
#      entradas. En la región no se notaba porque los seis quedan fuera.
DECLARADOS = {
    ("Oruro", "AIOC de Salinas"):                    "040801",  # Salinas de Garci Mendoza
    ("Oruro", "AIOC Uru Chipaya"):                   "040903",  # Uru Chipaya
    ("Santa Cruz", "AIOC Charagua Iyambae"):         "070702",  # Charagua Iyambae
    ("Santa Cruz", "AIOC Guaraní Kereimba Iyaambae"): "070705",  # Gutiérrez
    ("Chuquisaca", "TIOC Guaraní Chaqueño de Huacaya"): "011002",  # Huacaya
    ("Potosí", "Vitiche"):                           "050602",  # Vitichi (tipeo del geoportal)
}


def main():
    sp = list(csv.DictReader(open(SPINE, encoding="utf-8")))
    clave = {}
    for r in sp:
        for nm in {norm(r["nombre_censo"]), norm(r["nombre"])}:
            clave[(norm(r["dpto"]), nm)] = r["cod_ine"]
    for (dp, mu), ci in DECLARADOS.items():
        clave[(norm(dp), norm(mu))] = ci

    geo = pd.read_parquet(FUENTE / "manzanos.parquet",
                          columns=["codigo", "departamento", "municipio"])
    pob = pd.read_parquet(FUENTE / "poblacion.parquet")
    d = geo.merge(pob, on="codigo", how="left")
    d["cod_ine"] = [clave.get((norm(a), norm(m))) for a, m in
                    zip(d.departamento, d.municipio)]

    sin = d.cod_ine.isna()
    print(f"manzanos: {len(d):,} · con municipio identificado: {(~sin).mean():.2%}")
    if sin.any():
        huerf = d[sin].groupby(["departamento", "municipio"]).size().sort_values(ascending=False)
        print(f"  ⚠️ {sin.sum():,} manzanos SIN cruce ({huerf.size} nombres):")
        for (dp, mu), n in huerf.head(15).items():
            print(f"     {dp:<12} {mu:<32} {n:>6,}")

    # ★★ LA SUPERFICIE AMANZANADA Y LA CAJA URBANA (2026-09-04, pedido de Carlos).
    #   Dos números que salen de la misma pasada por la geometría y que arreglan
    #   dos cosas distintas:
    #   · `area_manzanada_ha` — la densidad municipal se venía calculando sobre
    #     TODO el territorio del municipio, y eso no es una densidad urbana: en
    #     un municipio con 3.000 km² de monte y una mancha de 200 ha, dividir por
    #     el municipio entero da un número que no describe a nadie. Es además la
    #     razón por la que `densidad` estaba EXCLUIDA de la comparación entre
    #     niveles: el municipal dividía por el municipio y el de manzana por la
    #     manzana. Con la superficie amanzanada las dos miden lo mismo.
    #   · `bbox_urbano` — el rectángulo que ocupan las manzanas del municipio, que
    #     es a dónde tiene que llevar el buscador: encuadrar el POLÍGONO municipal
    #     deja la ciudad como un punto en medio del campo.
    #   ⚠️ El área se mide reproyectando a UTM 20S. Calcularla sobre grados da un
    #     número que no es una superficie.
    import numpy as np, shapely
    import pyarrow.parquet as pq
    print("midiendo la superficie amanzanada…")
    areas, cajas, cods = [], [], []
    pf = pq.ParquetFile(FUENTE / "manzanos.parquet")
    for lote in pf.iter_batches(batch_size=20000, columns=["codigo", "geometry"]):
        g_ = shapely.from_wkb(lote.column("geometry").to_numpy(zero_copy_only=False))
        cods.extend(lote.column("codigo").to_pylist())
        cajas.append(shapely.bounds(g_))
        # área en m²: proyección cilíndrica equivalente local, exacta a esta escala
        lat = np.radians(shapely.get_y(shapely.centroid(g_)))
        gm = shapely.transform(g_, lambda c: np.column_stack([
            np.radians(c[:, 0]) * 6378137.0,
            np.radians(c[:, 1]) * 6378137.0]))
        areas.append(shapely.area(gm) * np.cos(lat))
    areas = np.concatenate(areas); cajas = np.vstack(cajas)
    geo_m = pd.DataFrame({"codigo": cods, "area_m2": areas,
                          "x0": cajas[:, 0], "y0": cajas[:, 1],
                          "x1": cajas[:, 2], "y1": cajas[:, 3]})
    d = d.merge(geo_m, on="codigo", how="left")

    caja_mun = d.dropna(subset=["cod_ine"]).groupby("cod_ine").agg(
        x0=("x0", "min"), y0=("y0", "min"), x1=("x1", "max"), y1=("y1", "max"),
        area_m2=("area_m2", "sum"))

    g = d.dropna(subset=["cod_ine"]).groupby("cod_ine").agg(
        manzanas=("codigo", "size"),
        con_ficha=("validado", "sum"),
        personas_urbano=("personas", "sum"),
        viviendas_urbano=("viviendas", "sum"))

    out = []
    for r in sp:
        ci = r["cod_ine"]
        x = g.loc[ci] if ci in g.index else None
        out.append({
            "sigep": r["sigep"],
            "cod_ine": ci,
            "nombre": r["nombre"],
            "dpto": r["dpto"],
            # ★ Un municipio sin una sola manzana en el geoportal NO es un error:
            #   es un municipio íntegramente disperso. Va con ceros y el tablero
            #   lo apaga en el nivel manzana, en vez de quedar sin la llave.
            "manzanas": int(x.manzanas) if x is not None else 0,
            "con_ficha": int(x.con_ficha) if x is not None else 0,
            "personas_urbano": float(x.personas_urbano) if x is not None else 0.0,
            "viviendas_urbano": float(x.viviendas_urbano) if x is not None else 0.0,
            # superficie que ocupan sus manzanas, en hectáreas
            "area_manzanada_ha": (round(float(caja_mun.at[ci, "area_m2"]) / 1e4, 2)
                                  if ci in caja_mun.index else 0.0),
            # el rectángulo de su mancha urbana, para el buscador
            "bbox_urbano": ([[round(float(caja_mun.at[ci, "x0"]), 5),
                              round(float(caja_mun.at[ci, "y0"]), 5)],
                             [round(float(caja_mun.at[ci, "x1"]), 5),
                              round(float(caja_mun.at[ci, "y1"]), 5)]]
                            if ci in caja_mun.index else None),
        })

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")

    # ★ LA COBERTURA SE MIDE ACÁ Y VIAJA — no se tipea en el armador del tablero.
    #   Es la frase que el lector ve al pie del nivel manzana ("131.801 de
    #   247.429, que concentran el 89,5% de la gente"): si el geoportal publica
    #   otra extracción, la frase tiene que moverse sola o miente.
    pers_ficha = float(d.loc[d.validado == True, "personas"].sum())
    pers_tot = float(d.personas.sum())
    (RAIZ / "datos" / "cobertura.json").write_text(json.dumps({
        "manzanas": int(len(d)),
        "con_ficha": int(d.validado.sum()),
        "personas": pers_tot,
        "personas_con_ficha": pers_ficha,
        "pct_manzanas": round(100 * float(d.validado.mean()), 1),
        "pct_personas": round(100 * pers_ficha / pers_tot, 1),
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    # ★ EL PUENTE, ESCRITO UNA SOLA VEZ. El teselador también necesita saber a
    #   qué municipio pertenece cada manzano, y la peor forma de dárselo sería
    #   que repitiera esta misma resolución por nombre: dos copias de un puente
    #   se desincronizan en cuanto una se corrige. Se emite acá y se lee allá.
    #   Va la clave SIGEP porque es la que usa el mapa maestro y el tablero.
    sig = {r["cod_ine"]: r["sigep"] for r in sp}
    puente = d[["codigo", "cod_ine"]].copy()
    puente["sigep"] = puente.cod_ine.map(sig)
    puente.to_parquet(RAIZ / "datos" / "manzano_municipio.parquet", index=False)

    con = sum(1 for m in out if m["manzanas"])
    print(f"\n{len(out)} municipios · {con} con manzanas · {len(out) - con} sin una sola")
    print(f"manzanas: {sum(m['manzanas'] for m in out):,} · "
          f"con ficha: {sum(m['con_ficha'] for m in out):,} "
          f"({sum(m['con_ficha'] for m in out) / sum(m['manzanas'] for m in out):.1%})")
    print(f"gente en manzano: {sum(m['personas_urbano'] for m in out):,.0f} · "
          f"en manzano CON ficha: {pers_ficha:,.0f} ({100*pers_ficha/pers_tot:.1f}%)")
    sup = sum(m["area_manzanada_ha"] for m in out)
    print(f"superficie amanzanada del país: {sup:,.0f} ha "
          f"({sup/100:,.0f} km²) · densidad urbana media: "
          f"{sum(m['personas_urbano'] for m in out)/sup:,.1f} hab/ha")
    print(f"-> {SALIDA.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
