# -*- coding: utf-8 -*-
"""
LAS CLASES DEL MAPA: DECILES QUE SE ADAPTAN.
=============================================
Traído TAL CUAL del tablero de la Gobernación (`scz-metropolitana-gobernacion/
scripts/deciles.py`, 2026-10-29) el 2026-10-31, a pedido de Carlos: «la paleta
por deciles creo que está mejor, para hacer los contrastes». Allá pinta las
manzanas; acá pinta los DOS niveles: las manzanas (deciles de las 131.797 del
país, o de las de una ciudad con el conmutador) y los 343 municipios (deciles
de los municipios). Cada nivel con su propia cuenta, y la leyenda lo dice.

Pedido original de Carlos (2026-10-29): «adaptar automáticamente en base a que
se vea bien visualmente la paleta de colores de las manzanas y poner por
deciles (como hicimos en parte en el dashboard de niñez)». El Atlas de la Niñez
pinta sus manzanas por cuantiles (`gasto-ninez/scripts/84_manzanas.py`).

★ EL PROBLEMA DE LOS DECILES PUROS. En «Acceso a fuente mejorada» el 88 % de
  las manzanas está en 100 %: nueve de los diez cortes caen en 100 y el mapa
  sale de UN color. Pasa en buena parte de los indicadores de servicios (todo
  en 100) y de carencias (todo en 0).

★ LA REGLA. Si un mismo valor junta a más de 1 de cada 10 manzanas (el «punto
  de masa»: casi siempre 100 % o 0 %), va en su propia clase y el RESTO se
  reparte en deciles (nueve grupos de igual cantidad). Si no hay punto de
  masa, son deciles comunes (diez). Los cortes repetidos se funden, así que
  puede haber menos de diez clases; los colores se reparten entonces a lo
  largo de la paleta completa, de punta a punta, para que el contraste no se
  pierda.

ESTE ARCHIVO ES LA REFERENCIA. El tablero la replica en JavaScript
(`clasesDeciles()` en `plantilla/tablero.html`, para los 343 municipios, que
se calculan en el navegador) y `scripts/estadisticas_manzana.py` la importa
para las manzanas. `python scripts/deciles.py` imprime las clases de algunos
indicadores para comparar las dos implementaciones.
"""
from collections import Counter

UMBRAL_MASA = 0.10      # un valor con más de 1 de cada 10 manzanas va aparte
EPS = 1e-9


def _cuantil(ordenados, q):
    """Interpolación lineal, igual que numpy.quantile (método por defecto)."""
    h = (len(ordenados) - 1) * q
    b = int(h)
    if b + 1 >= len(ordenados):
        return ordenados[-1]
    return ordenados[b] + (h - b) * (ordenados[b + 1] - ordenados[b])


def clases(valores):
    """Devuelve {'cortes', 'masa', 'n'}.

    `cortes` son los umbrales de un `step` (clase i = valores en
    [cortes[i-1], cortes[i]) ), crecientes. Si hay punto de masa interior o en
    una punta, la clase de la masa es exactamente [masa, masa + EPS).
    `n` = cantidad de clases = len(cortes) + 1; `p_masa` = parte de las
    manzanas que están en el punto de masa (para decirlo en la leyenda)."""
    v = sorted(float(x) for x in valores if x is not None and x == x)
    if not v:
        return {"cortes": [], "masa": None, "n": 1, "p_masa": None}
    masa, n_masa = Counter(v).most_common(1)[0]
    if n_masa / len(v) <= UMBRAL_MASA:
        masa = None
    resto = [x for x in v if x != masa] if masa is not None else v
    k = 9 if masa is not None else 10
    cortes = []
    if resto:
        for i in range(1, k):
            c = round(_cuantil(resto, i / k), 6)
            if c > resto[0] and (not cortes or c > cortes[-1]):
                cortes.append(c)
    if masa is not None:
        # la masa entra como clase propia: un corte en ella y otro apenas arriba
        cortes = [c for c in cortes if abs(c - masa) > EPS]
        cortes += [masa, masa + EPS] if masa > v[0] else [masa + EPS]
        cortes = sorted(set(cortes))
        if masa >= v[-1]:                     # la masa es el máximo: no hay clase arriba
            cortes = [c for c in cortes if c <= masa]
    return {"cortes": cortes, "masa": masa, "n": len(cortes) + 1,
            "p_masa": round(n_masa / len(v), 3) if masa is not None else None}


def colores(n, paleta):
    """`n` clases repartidas de punta a punta sobre los diez colores (ya
    orientados según la dirección del indicador)."""
    if n <= 1:
        return [paleta[len(paleta) // 2]]
    return [paleta[round(i * (len(paleta) - 1) / (n - 1))] for i in range(n)]


def clase_de(v, cortes):
    """Índice de clase de un valor (como el `step` de MapLibre)."""
    i = 0
    while i < len(cortes) and v >= cortes[i]:
        i += 1
    return i


if __name__ == "__main__":
    import json, pathlib, sys
    sys.stdout.reconfigure(encoding="utf-8")
    col = pathlib.Path(__file__).resolve().parent.parent / "docs" / "datos" / "col"
    for k in sys.argv[1:] or ["pct_agua_mejorada", "pct_alcantarillado", "densidad", "pct_edu_superior"]:
        arr = json.loads((col / f"{k}.json").read_text(encoding="utf-8"))
        c = clases(arr)
        cnt = Counter(clase_de(x, c["cortes"]) for x in arr if x is not None)
        print(f"{k}: masa={c['masa']} cortes={c['cortes']} -> {c['n']} clases, "
              f"manzanas por clase {[cnt[i] for i in range(c['n'])]}")
