# -*- coding: utf-8 -*-
"""
PRUEBA: LOS DECILES DEL NAVEGADOR = LOS DE PYTHON.
===================================================

El tablero calcula en JavaScript los deciles de los 343 municipios
(`clasesDeciles()` en `plantilla/tablero.html`) y lee hechos los de las
manzanas (`scripts/deciles.py`, vía `estadisticas_manzana.py`). Son dos
implementaciones de la misma regla; esto comprueba que den lo mismo, con el
código REAL de la plantilla corrido en Node y los datos reales del repo:

  1 · los 91 indicadores sobre los valores municipales (lo que pinta el mapa
      de municipios);
  2 · los 91 sobre las columnas publicadas de manzanas, contra `esc.dec` de
      `mz_stats.json`;
  3 · los deciles de cada ciudad de una muestra de indicadores, contra `loc`
      de `deciles/<clave>.json`;
  4 · el reparto de colores (`coloresClases` = `colores()`) para 1 a 10 clases.

    python scripts/prueba_deciles.py
"""
import json, pathlib, re, subprocess, sys, tempfile

sys.stdout.reconfigure(encoding="utf-8")
RAIZ = pathlib.Path(__file__).resolve().parent.parent
DATOS = RAIZ / "docs" / "datos"
sys.path.insert(0, str(RAIZ / "scripts"))
from deciles import clases, colores

html = (RAIZ / "plantilla" / "tablero.html").read_text(encoding="utf-8")
ini = html.index("const UMBRAL_MASA")
fin = html.index("/* `a` llevado hacia `b`")
m = re.search(r"function cuantil\(ord, q\)\{.*?\n\}", html, re.S)
codigo = m.group(0) + "\n" + html[ini:fin]

cat = json.loads((DATOS / "catalogo_manzana.json").read_text(encoding="utf-8"))
inds = [i for g in cat["grupos"] for i in g["indicadores"]]
mun = json.loads((DATOS / "municipios_manzana.json").read_text(encoding="utf-8"))
mzs = json.loads((DATOS / "mz_stats.json").read_text(encoding="utf-8"))

casos, esperado = [], []
for i in inds:
    vals = [(mm.get("municipal") or {}).get(i["k_mun"]) for mm in mun]
    casos.append(vals); esperado.append(("municipal", i["key"], clases(vals)))
for i in inds:
    col = json.loads((DATOS / "col" / f"{i['k_mz']}.json").read_text(encoding="utf-8"))
    casos.append(col); esperado.append(("manzana", i["key"], mzs[i["k_mz"]]["esc"]["dec"]))
# las ciudades: los valores de cada municipio salen de la columna + el puente
import pandas as pd, pyarrow.parquet as pq
sys.path.insert(0, str(RAIZ / "catalogo"))
from motor_manzana import FUENTE
cod = pq.read_table(str(FUENTE / "manzanos.parquet"), columns=["codigo"]).column(0).to_pandas().astype(str)
pue = pd.read_parquet(RAIZ / "datos" / "manzano_municipio.parquet")
sig = pue.assign(codigo=pue.codigo.astype(str)).set_index("codigo")["sigep"].astype(str).reindex(cod).to_numpy()
for k in ("pct_agua_mejorada", "pct_alcantarillado", "pct_edu_superior", "densidad", "pct_piso_tierra"):
    col = json.loads((DATOS / "col" / f"{k}.json").read_text(encoding="utf-8"))
    loc = json.loads((DATOS / "deciles" / f"{k}.json").read_text(encoding="utf-8"))["loc"]
    for s in list(loc)[:60]:
        vals = [v for v, ss in zip(col, sig) if ss == s]
        casos.append(vals)
        d = loc[s]
        esperado.append(("ciudad", f"{k}@{s}", {"cortes": d["c"], "masa": d["m"], "n": len(d["c"]) + 1, "p_masa": d["pm"]}))

with tempfile.TemporaryDirectory() as tmp:
    pc = pathlib.Path(tmp) / "casos.json"
    pc.write_text(json.dumps(casos), encoding="utf-8")
    pj = pathlib.Path(tmp) / "prueba.js"
    pj.write_text(codigo + """
const fs = require("fs");
const casos = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const pal = ["a","b","c","d","e","f","g","h","i","j"];
const col = []; for (let n = 1; n <= 10; n++) col.push(coloresClases(n, pal));
process.stdout.write(JSON.stringify({dec: casos.map(clasesDeciles), col}));
""", encoding="utf-8")
    r = subprocess.run(["node", str(pj), str(pc)], capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        sys.exit("⛔ node: " + r.stderr[:2000])
    js = json.loads(r.stdout)

mal = 0
for (tipo, k, py), j in zip(esperado, js["dec"]):
    ok = (py["n"] == j["n"] and py["masa"] == j["masa"] and py["p_masa"] == j["p_masa"]
          and len(py["cortes"]) == len(j["cortes"])
          and all(abs(a - b) < 1e-9 for a, b in zip(py["cortes"], j["cortes"])))
    if not ok:
        mal += 1
        if mal <= 8:
            print(f"  ✗ {tipo} {k}\n     py {py}\n     js {j}")
pal = list("abcdefghij")
mal_col = sum(1 for n in range(1, 11) if js["col"][n - 1] != colores(n, pal))
print(f"deciles: {len(esperado) - mal} de {len(esperado)} iguales "
      f"({sum(1 for e in esperado if e[0] == 'municipal')} municipales · "
      f"{sum(1 for e in esperado if e[0] == 'manzana')} de manzanas del país · "
      f"{sum(1 for e in esperado if e[0] == 'ciudad')} de ciudades)")
print(f"colores: {10 - mal_col} de 10 repartos iguales")
sys.exit(1 if mal or mal_col else 0)
