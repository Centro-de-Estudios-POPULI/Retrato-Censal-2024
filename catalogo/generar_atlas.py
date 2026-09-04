# -*- coding: utf-8 -*-
"""
GENERADOR DEL `data.json` DEL ATLAS SOCIOECONÓMICO MUNICIPAL.
==============================================================

El Atlas publicado se armó con `extraer_microdatos_v2.py`, que tenía **mal el
denominador** (metía viviendas vacías) en 44 de 47 indicadores de vivienda. Al
comparar sus 136 indicadores contra este motor, **98 de 126 comparables diferían**,
con errores sistemáticos de hasta **+21,4 pp en electricidad**, +16,4 en celular,
+14,9 en cocina exclusiva. Este script lo regenera desde los motores validados.

★ TRES VOCABULARIOS, no dos. El motor emite `poblacion`, el catálogo declara
  `pob_total` y el Atlas publica `pct_gas_natural` donde nosotros decimos
  `pct_gas_red`. La traducción va en dos pasos: `alias.renombrar` (motor →
  catálogo) y `alias.ATLAS` (atlas → catálogo, que acá se usa al revés).
  Sin el segundo, 6 indicadores del Atlas parecerían "no calculados" y el
  reemplazo sería una regresión.

★ LA CLAVE DEL JSON ES EL CÓDIGO SIGEP, no el INE: así lo indexa el HTML del
  Atlas (`CENSO[f.properties.sigep]`). El `cod_ine` viaja dentro de cada registro.

★ LA SERIE 2012 VIAJA EN UN ARCHIVO APARTE (`data_2012.json`), no como columnas
  `<clave>__2012` dentro del mismo. Dos razones: el Atlas ya pesa 1,9 MB y no
  todos los visitantes van a mirar la serie; y así el archivo de 2024 queda
  exactamente igual que hoy, o sea que la etapa de valores no se re-litiga.

    python generar_atlas.py            # escribe data_nuevo.json, data_2012_nuevo.json
"""
import pathlib, json, csv
import pandas as pd, numpy as np
from alias import renombrar, ATLAS

# ── cuántos municipios con dato hacen falta para decir que la serie EXISTE ────
# No es un umbral de calidad: los indicadores que 2012 no puede dar salen vacíos
# en los 343, no en algunos. Se deja margen por si un bloque tiene huecos.
UMBRAL_2012 = 300

# ── DESCRIPCIONES QUE NOMBRABAN UN CENSO ─────────────────────────────────────
# Al poder alternar de año, una tarjeta que dice "según el CPV 2024" queda
# MINTIENDO en cuanto se mira 2012. Son diez las que nombran un año y cinco de
# ellas tienen serie, así que se reescriben en forma neutral. ⚠️ No sirve
# reemplazar "2024" por "2012" al vuelo: varias hablan de 2019 (el quinquenio
# previo, la creación del SUS) y el reemplazo ciego inventaría fechas.
DESC_NEUTRA = {
 "pob_total": "Total de habitantes del municipio.",
 "pct_autoident_indigena": "Porcentaje de la población que se autoidentifica con alguna "
                           "nación o pueblo indígena originario campesino o afroboliviano.",
 "pct_migrante_reciente": "Porcentaje de residentes que cinco años antes del censo vivían en "
                          "otro municipio o país. Mide la atracción migratoria del quinquenio.",
 "pct_hogar_fallecido": "Porcentaje de hogares donde murió al menos un miembro en el período "
                        "que releva cada censo.",
 "edad_prom_fallecimiento": "Edad promedio al morir de los fallecidos declarados en el período "
                            "que releva cada censo. Proxy municipal de longevidad.",
}

# ★ POR QUÉ FALTA CADA UNO — DECLARADO, NO INFERIDO.
#   El catálogo trae un campo `y12`, pero MIENTE: dice "si" en `pct_agua_rio`,
#   `tasa_mortalidad` y la tipología de hogar, que salen vacíos igual. La
#   presencia se MIDE del dato; lo único que se declara acá es la explicación,
#   y cada una está verificada contra el motor o el diccionario del censo.
#   Se distingue lo IMPOSIBLE (el censo de 2012 no lo pregunta o no lo separa)
#   de lo PENDIENTE (se puede calcular y todavía no se calculó): decir "no hay
#   dato" cuando en realidad es "no lo hicimos" convierte una tarea en una ley.
SIN_2012 = {
 # — el censo de 2012 no lo pregunta —
 "pct_seguro_salud":   "El censo de 2012 no preguntaba por afiliación a un seguro de salud.",
 "pct_seguro_privado": "El censo de 2012 no preguntaba por afiliación a un seguro de salud.",
 "pct_sin_seguro":     "El censo de 2012 no preguntaba por afiliación a un seguro de salud.",
 "pct_sus":            "El SUS se creó en 2019: no existía cuando se levantó el censo de 2012.",
 "edad_1er_hijo":      "El censo de 2012 no pregunta la edad al primer hijo.",
 "pct_tv_cable":       "El censo de 2012 no pregunta por televisión por cable.",
 "pct_refrigerador":   "El censo de 2012 no pregunta por este equipamiento del hogar.",
 "pct_lavadora":       "El censo de 2012 no pregunta por este equipamiento del hogar.",
 "pct_microondas":     "El censo de 2012 no pregunta por este equipamiento del hogar.",
 "pct_aire_acond":     "El censo de 2012 no pregunta por este equipamiento del hogar.",
 "pct_muertes_covid":  "La pregunta por muertes de COVID-19 no existe en 2012.",
 "pct_trabaja_fuera":  "La pregunta por el municipio donde se trabaja no existe en 2012.",
 # — el censo de 2012 lo junta con otra categoría y no se puede separar —
 "pct_celular":        "En 2012 la telefonía fija y el celular se preguntan juntos, en una sola pregunta.",
 "pct_telefono_fijo":  "En 2012 la telefonía fija y el celular se preguntan juntos, en una sola pregunta.",
 "pct_internet_fijo":  "El censo de 2012 pregunta por acceso a internet sin distinguir fijo de móvil.",
 "pct_internet_movil": "El censo de 2012 pregunta por acceso a internet sin distinguir fijo de móvil.",
 "pct_choza":          "El censo de 2012 junta casa, choza y pahuichi en una sola categoría.",
 "pct_agua_rio":       "En 2012 «lluvia, río, vertiente y acequia» es una sola categoría, que mezcla fuentes protegidas y no protegidas.",
 "pct_agua_lluvia":    "En 2012 «lluvia, río, vertiente y acequia» es una sola categoría, que mezcla fuentes protegidas y no protegidas.",
 "pct_agua_mejorada":  "En 2012 «lluvia, río, vertiente y acequia» es una sola categoría: incluirla sobrecuenta y excluirla subcuenta.",
 "pct_agua_no_mejorada": "En 2012 «lluvia, río, vertiente y acequia» es una sola categoría: incluirla sobrecuenta y excluirla subcuenta.",
 # — el dato existe pero no da una cifra comparable —
 "tasa_mortalidad":    "El módulo de mortalidad de 2012 no registra el año de fallecimiento: sus muertes son un acumulado de varios años y no dan una tasa anual comparable.",
 "pct_discapacidad":   "En 2012 la discapacidad se capta a nivel de hogar y en un módulo aparte; no es comparable con el registro por persona de 2024.",
 "pct_disc_ver":       "En 2012 la discapacidad se capta a nivel de hogar y en un módulo aparte; no es comparable con el registro por persona de 2024.",
 "pct_disc_oir":       "En 2012 la discapacidad se capta a nivel de hogar y en un módulo aparte; no es comparable con el registro por persona de 2024.",
 "pct_disc_caminar":   "En 2012 la discapacidad se capta a nivel de hogar y en un módulo aparte; no es comparable con el registro por persona de 2024.",
 "pct_disc_cognitiva": "En 2012 la discapacidad se capta a nivel de hogar y en un módulo aparte; no es comparable con el registro por persona de 2024.",
 "pct_parto_calificado": "La pregunta existe en 2012, pero el diccionario del censo no trae las etiquetas de sus categorías: sin ellas la cifra no es confiable.",
 # — necesita la matriz origen-destino, que sólo puede armarse con 2024 —
 "saldo_migratorio":       "Requiere la matriz origen-destino, que sólo puede armarse con el censo de 2024.",
 "poblacion_flotante":     "Requiere la matriz origen-destino, que sólo puede armarse con el censo de 2024.",
 "autocontencion_laboral": "Requiere la pregunta por el municipio donde se trabaja, que no existe en 2012.",
 "dependencia_capital":    "Requiere la pregunta por el municipio donde se trabaja, que no existe en 2012.",
 # — PENDIENTE: se puede calcular y todavía no se calculó —
 "pct_hogar_nuclear":      "Todavía sin calcular para 2012: la tipología de hogar habría que reconstruirla desde la relación de parentesco.",
 "pct_hogar_monoparental": "Todavía sin calcular para 2012: la tipología de hogar habría que reconstruirla desde la relación de parentesco.",
 "pct_hogar_compuesto":    "Todavía sin calcular para 2012: la tipología de hogar habría que reconstruirla desde la relación de parentesco.",
 "pct_hogar_extendido":    "Todavía sin calcular para 2012: la tipología de hogar habría que reconstruirla desde la relación de parentesco.",
}

AQUI = pathlib.Path(__file__).parent
REPO = pathlib.Path(r"C:\Users\HP\OneDrive\Desktop\Proyectos"
                    r"\Observatorio de Presupuesto Fiscal Departamental\_github_atlas_fiscal")
SPINE = pathlib.Path(r"C:\Users\HP\OneDrive\Desktop\Proyectos\bo-geo-maestro\spine\municipios.csv")
FUENTES = ["municipal", "personas", "nbi", "otros", "flujos_municipal"]


def cargar(anio):
    d = None
    for f in FUENTES:
        p = AQUI / f"{f}_{anio}.csv"
        if not p.exists():
            print(f"  (falta {p.name})")
            continue
        x = pd.read_csv(p, index_col=0, dtype={0: str})
        x.index = x.index.astype(str).str.zfill(6)
        x = x.drop(columns=[c for c in x.columns if c.startswith("_den_")])
        x = renombrar(x).rename(columns={"n_viviendas": "viviendas"})
        d = x if d is None else d.join(x[[c for c in x.columns if c not in d.columns]],
                                       how="outer")
    return d


def main():
    mio = cargar(2024)
    mio12 = cargar(2012)
    sp = {r["cod_ine"]: r for r in csv.DictReader(open(SPINE, encoding="utf-8"))}
    viejo = json.load(open(REPO / "data.json", encoding="utf-8"))
    cat = json.load(open(REPO / "catalogo.json", encoding="utf-8"))
    # ★ El Atlas ya no se limita a sus 136 originales: publica TODO lo que el
    #   motor calcula. Los 136 viejos conservan su clave (para no romper enlaces
    #   ni el `dir` de la rampa de color) y el resto se agrega con la clave del
    #   catálogo del motor, agrupado por su categoría declarada.
    viejos = [i["key"] for g in cat["grupos"] for i in g["indicadores"]]
    inds = list(viejos)
    equiv = {ATLAS.get(k, k) for k in viejos}       # sus claves, en vocabulario del catálogo
    decl = {i["k"]: i for i in json.loads(
        (AQUI / "catalogo.json").read_text(encoding="utf-8"))["indicadores"]}
    nuevos_k = [c for c in mio.columns if c not in equiv and c in decl]
    inds += sorted(nuevos_k)
    print(f"indicadores: {len(viejos)} del Atlas + {len(nuevos_k)} nuevos = {len(inds)}")

    # ★ COMPONENTES DE LAS BRECHAS — BUG VIVO (encontrado 2026-08-16).
    #   Una brecha no se promedia ni ponderando: es la RESTA de dos porcentajes,
    #   y hay que rearmarla desde sus dos mitades. El catálogo las declara en
    #   `comp` desde agosto y el frontend ya sabe usarlas, pero **las columnas
    #   nunca se emitieron al data.json** ⇒ en el Atlas publicado las cuatro
    #   brechas salen sin cifra en el resumen nacional y en el departamental
    #   (el municipal siempre estuvo bien, porque ahí el valor viaja directo).
    #   Son columnas de apoyo: no entran al menú ni tienen mapa propio.
    comps = sorted({c for g in cat["grupos"] for i in g["indicadores"]
                    for c in i.get("comp", [])})
    print(f"componentes de brecha que ahora viajan: {len(comps)}")

    def apoyo(fila, fuente, ci):
        for c in comps:
            if c in fuente.columns and ci in fuente.index:
                v = fuente.at[ci, c]
                if pd.notna(v):
                    fila[c] = round(float(v), 3)

    nuevo, faltan, hechos = {}, set(), set()
    for sigep, reg in viejo.items():
        ci = str(reg["cod_ine"]).zfill(6)
        fila = {"cod_ine": ci,
                "nombre": sp.get(ci, {}).get("nombre", reg.get("nombre")),
                "dpto": sp.get(ci, {}).get("dpto", reg.get("dpto"))}
        for k in inds:
            col = ATLAS.get(k, k)          # traducción atlas -> catálogo
            if col in mio.columns and ci in mio.index:
                v = mio.at[ci, col]
                if pd.notna(v):
                    # los porcentajes con un decimal, como el Atlas actual
                    fila[k] = round(float(v), 1 if str(k).startswith("pct_") or
                                    str(k).startswith("tasa_") else 3)
                    hechos.add(k)
                    continue
            faltan.add(k)
        apoyo(fila, mio, ci)
        nuevo[sigep] = fila

    (REPO.parent / "data_nuevo.json").write_text(
        json.dumps(nuevo, ensure_ascii=False), encoding="utf-8")

    # ── LA MISMA CAJA, CON EL CENSO DE 2012 ──────────────────────────────────
    # Se emiten SÓLO los indicadores que 2012 realmente puede dar. Un indicador
    # que 2012 no tiene y que viajara en cero se leería como "nadie tenía" y
    # fabricaría un cambio intercensal que nunca ocurrió — es el error que ya
    # apareció una vez en los ~22 indicadores de equipamiento.
    con12, sin12 = {}, {}
    for k in inds:
        col = ATLAS.get(k, k)
        n = int(mio12[col].notna().sum()) if col in mio12.columns else 0
        (con12 if n >= UMBRAL_2012 else sin12)[k] = n
    viejo12 = {}
    for sigep, reg in viejo.items():
        ci = str(reg["cod_ine"]).zfill(6)
        fila = {"cod_ine": ci}
        for k in con12:
            col = ATLAS.get(k, k)
            if ci in mio12.index:
                v = mio12.at[ci, col]
                if pd.notna(v):
                    fila[k] = round(float(v), 1 if str(k).startswith("pct_") or
                                    str(k).startswith("tasa_") else 3)
        apoyo(fila, mio12, ci)
        viejo12[sigep] = fila
    (REPO.parent / "data_2012_nuevo.json").write_text(
        json.dumps(viejo12, ensure_ascii=False), encoding="utf-8")
    print(f"\nserie 2012: {len(con12)} indicadores con cifra · {len(sin12)} sólo 2024")
    huerf = [k for k in sin12 if k not in SIN_2012]
    if huerf:
        # ⚠️ Un "sólo 2024" sin explicación es una caja negra en la pantalla:
        #    el lector no puede saber si el censo no lo trae o si no lo hicimos.
        print(f"  ⚠️ SIN MOTIVO DECLARADO (agregar a SIN_2012): {', '.join(sorted(huerf))}")
    sobran = [k for k in SIN_2012 if k in con12]
    if sobran:
        print(f"  ⚠️ declarados sin 2012 pero el motor SÍ los calcula: {', '.join(sorted(sobran))}")

    # ── catálogo ampliado: los grupos viejos intactos + los nuevos por categoría
    #    declarada en el catálogo del motor, que ya trae etiqueta, unidad y `dir`
    grupos = [dict(g) for g in cat["grupos"]]
    porcat = {}
    for k in nuevos_k:
        i = decl[k]
        porcat.setdefault(i["g"], []).append(
            {"key": k, "label": i["l"], "unit": i["u"], "dir": i.get("d", 0),
             "desc": i.get("nota") or i["l"]})
    # ⚠️ El emparejamiento de grupos va SIN mayúsculas: el catálogo del motor dice
    #    "Vivienda y materiales" y el del Atlas "Vivienda y Materiales", y con
    #    comparación exacta aparecía un grupo NUEVO duplicado, idéntico salvo una
    #    letra, con un solo indicador adentro.
    idx = {g["label"].casefold(): g for g in grupos}
    for g, items in sorted(porcat.items()):
        if g.casefold() in idx:
            idx[g.casefold()]["indicadores"] = idx[g.casefold()]["indicadores"] + items
        else:
            grupos.append({"key": g.lower().replace(" ", "_"), "label": g,
                           "indicadores": items})
    # ── cada indicador declara si tiene serie, por qué no, y su ESCALA ────────
    #    Va en el catálogo y no en los datos porque la interfaz lo necesita
    #    ANTES de bajar el archivo de 2012: es lo que decide qué tarjetas se
    #    pueden mirar en cada censo.
    #
    # ★ Y ACÁ VIAJA EL DOMINIO DE COLOR, que es la parte fina. La decisión de
    #   producto es "una sola escala para los dos censos", o sea que el rango
    #   dibujado se calcula sobre la UNIÓN de 2012 y 2024. Si el navegador lo
    #   calculara solo, no podría hacerlo hasta que bajara el archivo de 2012
    #   —que llega en diferido— y el mapa **cambiaría de color solo**, un segundo
    #   después de cargar. Declarado acá, el primer pintado ya es el definitivo.
    #   Se calcula sobre los valores YA REDONDEADOS, que son los que ve el
    #   navegador, para que el corte caiga en el mismo lugar.
    def q(v, p):
        if not v:
            return None
        v = sorted(v)
        h = (len(v) - 1) * p
        a = int(h // 1)
        b = min(a + 1, len(v) - 1)
        return v[a] + (h - a) * (v[b] - v[a])

    for g in grupos:
        for i in g["indicadores"]:
            k = i["key"]
            if k in DESC_NEUTRA:
                i["desc"] = DESC_NEUTRA[k]
            i["s12"] = k in con12
            if k not in con12:
                i["w12"] = SIN_2012.get(k, "Sin cifra comparable para 2012.")
            else:
                i.pop("w12", None)
            a = [r[k] for r in nuevo.values() if r.get(k) is not None]
            b = [r[k] for r in viejo12.values() if r.get(k) is not None] if k in con12 else []
            u = a + b
            if u:
                i["dom"] = [round(q(u, .02), 4), round(q(u, .98), 4)]
            if k not in con12:
                i.pop("domd", None)
                continue
            # el dominio del CAMBIO, simétrico alrededor de cero: un avance y un
            # retroceso del mismo tamaño tienen que pintarse con la misma fuerza
            conteo = i.get("agg") == "suma"
            ds = []
            for s, r in nuevo.items():
                x, y = viejo12.get(s, {}).get(k), r.get(k)
                if x is None or y is None:
                    continue
                if conteo:
                    if x:
                        ds.append(100 * (y - x) / x)
                else:
                    ds.append(y - x)
            if ds:
                i["domd"] = round(max(abs(q(ds, .02)), abs(q(ds, .98))) or 1, 4)
    (REPO.parent / "catalogo_nuevo.json").write_text(
        json.dumps({"grupos": grupos}, ensure_ascii=False), encoding="utf-8")
    tot = sum(len(g["indicadores"]) for g in grupos)
    n12 = sum(1 for g in grupos for i in g["indicadores"] if i["s12"])
    print(f"catálogo ampliado: {len(grupos)} grupos · {tot} indicadores · {n12} con serie 2012")

    print(f"municipios: {len(nuevo)} · indicadores del Atlas: {len(inds)}")
    print(f"  cubiertos por el motor : {len(hechos)}")
    print(f"  sin cubrir             : {sorted(set(inds) - hechos)}")

    # ── cuánto se mueve cada indicador, que es lo que hay que poder explicar ──
    A = pd.DataFrame(viejo).T
    B = pd.DataFrame(nuevo).T
    filas = []
    for k in sorted(hechos):
        a = pd.to_numeric(A[k], errors="coerce") if k in A.columns else None
        if a is None:
            continue
        b = pd.to_numeric(B[k], errors="coerce")
        j = pd.concat([a, b], axis=1, keys=["viejo", "nuevo"]).dropna()
        if len(j) < 300:
            continue
        d = j["nuevo"] - j["viejo"]
        filas.append((k, d.median(), d.abs().max(), (d.abs() < 0.05).mean() * 100))
    r = pd.DataFrame(filas, columns=["ind", "dif_mediana", "max_abs", "pct_iguales"])
    r.to_csv(AQUI / "atlas_cambios.csv", index=False, encoding="utf-8")
    print(f"\nindicadores que NO se mueven: {(r.pct_iguales > 99).sum()} de {len(r)}")
    print("\nLOS 15 QUE MÁS CAMBIAN (nuevo − viejo)")
    print("=" * 52)
    for _, x in r.reindex(r.dif_mediana.abs().sort_values(ascending=False).index).head(15).iterrows():
        print(f"  {x['ind']:<30}{x['dif_mediana']:>+9.2f}")
    print(f"\n-> data_nuevo.json · data_2012_nuevo.json · catalogo_nuevo.json "
          f"(NO se pisó el vivo) · atlas_cambios.csv")


if __name__ == "__main__":
    main()
