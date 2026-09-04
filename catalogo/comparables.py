# -*- coding: utf-8 -*-
"""
QUÉ INDICADORES BAJAN A MANZANA CON LA MISMA DEFINICIÓN.
=========================================================

Define el reparto de los DOS tableros:

  · Tablero A — municipal: todo lo que el motor calcula a nivel municipio.
  · Tablero B — municipio ↔ manzana: SÓLO los que existen en los dos niveles
    con la MISMA definición, para que el toggle nunca cambie de indicador.

★ Ahora esto se puede medir de verdad: `motor_manzana.py` traduce las fichas del
  geoportal a los MISMOS nombres canónicos que el motor municipal, así que la
  intersección de columnas ES la lista de comparables. Con el pipeline viejo
  (`derivar_indicadores.py`) los dos niveles hablaban vocabularios distintos y
  había que emparejar a mano — de ahí salían los "gemelos" con la misma clave y
  distinta definición.

⚠️ LA TERCERA CIFRA. Un indicador comparable sirve TRES números: municipio entero ·
   municipio URBANO · manzana. La distancia entre los dos primeros ES el sesgo
   urbano —las manzanas son bloques urbanos y la cifra municipal cubre también lo
   rural—, y el único universo estrictamente comparable con la manzana es el del
   medio. Por eso el contraste se hace contra `municipal_urbano_*`, no contra
   `municipal_*`.

    python comparables.py        # imprime el reparto y escribe comparables.json
"""
import pathlib, json
import pandas as pd

AQUI = pathlib.Path(__file__).parent
CAT = json.loads((AQUI / "catalogo.json").read_text(encoding="utf-8"))
DECL = {i["k"]: i for i in CAT["indicadores"]}


def columnas(nombre):
    """Sólo el encabezado: `manzana_2024.csv` pesa 91 MB."""
    d = pd.read_csv(AQUI / nombre, nrows=0)
    return [c for c in d.columns
            if c not in ("cod_ine", "codigo", "nombre") and not c.startswith("_den_")]


mz = set(columnas("manzana_2024.csv"))
mun = set(columnas("municipal_2024.csv")) | set(columnas("personas_2024.csv")) \
    | set(columnas("nbi_2024.csv")) | set(columnas("otros_2024.csv")) \
    | set(columnas("geo_2024.csv"))    # densidad y superficie, del mapa maestro
urb = set(columnas("municipal_urbano_2024.csv"))

# el motor emite su propio vocabulario; manda el del catálogo
from alias import ALIAS
tr = lambda s: {ALIAS.get(c, c) for c in s}
mz, mun, urb = tr(mz), tr(mun), tr(urb)

ambos = sorted((mz & mun) & set(DECL))
solo_mun = sorted((mun - mz) & set(DECL))
solo_mz = sorted((mz - mun) & set(DECL))
sin_declarar = sorted((mz | mun) - set(DECL))

print(f"nivel manzana : {len(mz)} indicadores")
print(f"nivel municipio: {len(mun)}")
print()
print(f"★ COMPARABLES (los dos niveles, misma definición): {len(ambos)}")
print(f"  con cifra urbana además: {len(set(ambos) & urb)}")
print(f"  sólo municipio : {len(solo_mun)}")
print(f"  sólo manzana   : {len(solo_mz)}  -> {solo_mz}")
print(f"  sin declarar en el catálogo: {len(sin_declarar)}")

# ── lo que dice el catálogo vs lo que hay de verdad ──
declara_mz = {k for k, i in DECL.items() if i.get("n") in ("mun+mz", "mz")}
print(f"\nel catálogo declara nivel manzana en {len(declara_mz)}")
print(f"  declarados y NO están: {sorted(declara_mz - set(ambos) - set(solo_mz))[:12]}")
print(f"  están y NO declarados: {sorted(set(ambos) - declara_mz)[:12]}")

por_grupo = {}
for k in ambos:
    por_grupo.setdefault(DECL[k]["g"], []).append(k)
print(f"\nCOMPARABLES POR CATEGORÍA ({len(por_grupo)} categorías)")
for g, ks in sorted(por_grupo.items(), key=lambda x: -len(x[1])):
    print(f"  {g:<34}{len(ks):>3}   {', '.join(ks[:4])}{' …' if len(ks) > 4 else ''}")

(AQUI / "comparables.json").write_text(json.dumps(
    {"comparables": ambos, "solo_municipio": solo_mun, "solo_manzana": solo_mz,
     "con_urbano": sorted(set(ambos) & urb)}, ensure_ascii=False, indent=1),
    encoding="utf-8")
print(f"\n-> comparables.json")
