# -*- coding: utf-8 -*-
"""
¿LOS 62 COMPARABLES MIDEN DE VERDAD LO MISMO?
==============================================

Tener la misma clave en los dos niveles NO alcanza: ya pasó que
`pct_sin_educacion` existía en ambos catálogos —misma clave— midiendo el 15+ en
municipio y toda la población en manzana. Un merge por clave los habría unido en
silencio.

★ LA PRUEBA: agregar las manzanas a nivel municipio y contrastarlas contra la
  cifra URBANA del microdato (`municipal_urbano_*`), que es el único universo
  estrictamente comparable —las manzanas son bloques urbanos—.

⚠️ NO se espera identidad: "área urbana censada" y `urbrur = urbana` no son el
   mismo polígono, y el INE suprime las manzanas chicas por privacidad (25.698
   con ficha de 38.892, que concentran el 93,8% de la población). Un desvío de
   1-3 pp es normal. Lo que delata una definición distinta es un desvío GRANDE y
   SISTEMÁTICO (siempre del mismo lado).

    python comparar_niveles.py
"""
import pathlib, json
import pandas as pd, numpy as np
from alias import renombrar

AQUI = pathlib.Path(__file__).parent
UMBRAL = 5.0        # pp de error absoluto medio: por encima, se revisa a mano


def leer(nombre):
    d = pd.read_csv(AQUI / nombre, index_col=0, dtype={0: str})
    d.index = d.index.astype(str).str.zfill(6)
    return renombrar(d.drop(columns=[c for c in d.columns if c.startswith("_den_")]))


def unir(*nombres):
    d = None
    for n in nombres:
        x = leer(n)
        d = x if d is None else d.join(
            x[[c for c in x.columns if c not in d.columns]], how="outer")
    return d


mz = leer("manzana_agregado_municipal.csv")
# ★ La cifra urbana de PERSONAS (`personas_urbano_2024.csv`) se agregó el
#   2026-08-15: sin ella, 20 de los 62 comparables —empleo, salud, educación,
#   migración— no se podían verificar, porque la diferencia contra el municipio
#   entero mezcla el sesgo urbano con una posible definición distinta.
urb = unir("municipal_urbano_2024.csv", "personas_urbano_2024.csv")
mun = unir("municipal_2024.csv", "personas_2024.csv")
comp = json.loads((AQUI / "comparables.json").read_text(encoding="utf-8"))["comparables"]
# la unidad declarada de cada indicador: decide en qué se mide la distancia
UNID = {i["k"]: i["u"] for i in
        json.loads((AQUI / "catalogo.json").read_text(encoding="utf-8"))["indicadores"]}

filas = []
for k in comp:
    if k not in mz.columns:
        continue
    for etq, ref in (("urbano", urb), ("municipal", mun)):
        if k not in ref.columns:
            continue
        j = pd.concat([mz[k], ref[k]], axis=1, keys=["mz", "ref"]).dropna()
        if len(j) < 100:
            continue
        d = j.mz - j.ref
        # ★ LA MÉTRICA DEPENDE DE LA UNIDAD, Y LA UNIDAD LA DECLARA EL CATÁLOGO.
        #   Para un porcentaje, la distancia se mide en puntos porcentuales. Para
        #   un CONTEO —población, viviendas— la resta está en personas, y medirla
        #   con el mismo umbral de 10 "pp" excluía `pob_total` por "3.420 pp",
        #   que no son pp sino gente. Es el mismo error de inferir la naturaleza
        #   de un indicador en vez de leerla, que este proyecto ya cometió tres
        #   veces (ver `agregacion.py` y `armar_metro.py`).
        u_ = UNID.get(k, "%")
        if u_ in ("%", "pp"):
            err, ses, peor = d.abs().mean(), d.mean(), d.abs().max()
        else:
            rel = 100 * d / j.ref.replace(0, np.nan)
            err, ses, peor = rel.abs().mean(), rel.mean(), rel.abs().max()
        filas.append({"ind": k, "contra": etq, "n": len(j), "unidad": u_,
                      "error_abs_medio": err, "sesgo": ses, "peor": peor})
r = pd.DataFrame(filas)
u = r[r.contra == "urbano"].set_index("ind").sort_values("error_abs_medio", ascending=False)

print(f"CONTRA LA CIFRA URBANA — {len(u)} indicadores\n")
print(f"{'indicador':<28}{'err.abs':>9}{'sesgo':>9}{'peor':>8}")
for k, x in u.iterrows():
    marca = "  <-- REVISAR" if x.error_abs_medio > UMBRAL else ""
    print(f"{k:<28}{x.error_abs_medio:>9.2f}{x.sesgo:>+9.2f}{x.peor:>8.1f}{marca}")

# ★ EL UMBRAL SOLO NO ALCANZA: hay que mirar si la diferencia es SISTEMÁTICA.
#   `|sesgo| / error_abs` cerca de 1 quiere decir que TODAS las diferencias van
#   para el mismo lado ⇒ es una definición distinta. Bastante por debajo de 1 es
#   dispersión: el desvío existe pero cambia de signo según el municipio, que es
#   la forma del efecto de borde urbano ("área urbana censada" y `urbrur=urbana`
#   no son el mismo polígono).
#   Medido: el bloque de salud da 1,00 —el municipal divide por TODA la población
#   y admite respuesta múltiple (sus categorías suman 128%), mientras la manzana
#   divide por la suma de las categorías (suman 100%)— y alcantarillado da 0,59.
u["sistematico"] = (u.sesgo.abs() / u.error_abs_medio).round(2)
# ⚠️ El corte de exclusión también depende de la unidad. Un conteo puede
#    diferir 30% entre "área urbana censada" y `urbrur==urbana` sin que la
#    definición sea otra: es el borde urbano, y en los municipios más rurales
#    llega a +34% (Porongo) mientras en los urbanos puros da 0,0% (Montero).
#    Excluirlos por eso sería tirar el dato más directo que tiene la ficha.
TOPE = {"%": 10, "pp": 10}
excluidos = [k for k in u.index
             if u.at[k, "error_abs_medio"] > TOPE.get(UNID.get(k, "%"), 60)
             and u.at[k, "sistematico"] > .95]
avisar = [k for k in u.index if k not in excluidos and u.at[k, "error_abs_medio"] > UMBRAL]

print(f"\nresumen: error absoluto medio global {u.error_abs_medio.mean():.2f} pp")
print(f"  por debajo de {UMBRAL} pp: {(u.error_abs_medio <= UMBRAL).sum()} de {len(u)}")
print(f"  EXCLUIDOS del Tablero B (definición distinta): {excluidos}")
for k in excluidos:
    print(f"     {k}: {u.at[k,'error_abs_medio']:.1f} pp, sistemático {u.at[k,'sistematico']}")
print(f"  incluidos CON AVISO (borde urbano): {avisar}")

sin_urbano = [k for k in comp if k not in u.index]
if sin_urbano:
    print(f"\nsin cifra urbana para contrastar ({len(sin_urbano)}): {sin_urbano}")

# ★ SIN CONTRASTE POSIBLE ⇒ NO SE PUBLICA COMO CONTINUO. `densidad` es el caso:
#   la municipal divide por TODA la superficie del municipio y la de manzana por
#   la superficie amanzanada. No son la misma magnitud, así que al subir de
#   nivel el número daría un salto que parece un dato y es un cambio de
#   denominador. Pasa a "sólo manzana", donde su cifra municipal es el agregado
#   de sus propias manzanas —eso sí es continuo— y la tarjeta lo dice.
prev = json.loads((AQUI / "comparables.json").read_text(encoding="utf-8"))
solo_mz = sorted(set(prev.get("solo_manzana", [])) | set(sin_urbano))

(AQUI / "comparables.json").write_text(json.dumps({
    **prev,
    "verificados": [k for k in u.index if k not in excluidos],
    "solo_manzana": solo_mz,
    "con_aviso": avisar,
    "excluidos": excluidos,
    "error_pp": {k: round(float(u.at[k, "error_abs_medio"]), 2) for k in u.index},
}, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"\n-> comparables.json · Tablero B queda con "
      f"{len([k for k in u.index if k not in excluidos])} indicadores")
