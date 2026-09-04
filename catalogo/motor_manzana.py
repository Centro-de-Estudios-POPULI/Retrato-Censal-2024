# -*- coding: utf-8 -*-
"""
MOTOR DE MANZANA — el tercer nivel del Tablero 2.
==================================================

A diferencia de los otros dos motores, éste NO sale del microdato y no puede:
el microdato llega hasta municipio y no trae identificador de manzano (es una
restricción de anonimización del INE). Las fichas por manzana vienen ya
agregadas del geoportal, vía `mauforonda/atlasurbano`.

Lo que hace este archivo es traducir esas fichas a los MISMOS nombres canónicos
que `motor.py`, para que el indicador sea el mismo objeto en los tres niveles:

    municipio  ·  municipio urbano  ·  manzana

La ficha trae CONTEOS por categoría, así que cada indicador es
`categoría / suma de las categorías de esa pregunta` — cada pregunta lleva su
propio denominador, que es como se forman los porcentajes en el origen.

★ CONTROL DE CALIDAD: al final se agregan las manzanas por municipio y se
  contrastan contra `municipal_urbano_2024.csv`, que sale del microdato. Son dos
  fuentes independientes del INE; si coinciden, la traducción es correcta. No se
  espera identidad exacta —"área urbana censada" y `urbrur=urbana` no son
  exactamente el mismo polígono— sino diferencias del orden de 1 pp.
"""
import pathlib, unicodedata, csv, re
import pandas as pd, numpy as np

AQUI = pathlib.Path(__file__).parent
FUENTE = AQUI.parent / "fuente"
SPINE = pathlib.Path(r"C:\Users\HP\OneDrive\Desktop\Proyectos\bo-geo-maestro\spine\municipios.csv")

def norm(s):
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode()
    return " ".join(s.lower().replace("-", " ").split())

# indicador canónico -> (prefijo de la pregunta en la ficha, sufijos que suman)
# El denominador de cada uno es la suma de TODAS las columnas de su prefijo.
IND = {
 "pct_agua_caneria":       ("agua_",   ["cañería"]),
 "pct_agua_pileta":        ("agua_",   ["piletapública"]),
 "pct_agua_pozo":          ("agua_",   ["pozoconbomba", "pozosinbomba"]),
 "pct_agua_pozo_bomba":    ("agua_",   ["pozoconbomba"]),
 "pct_agua_carro":         ("agua_",   ["carrorepartidor"]),
 "pct_alcantarillado":     ("desague_", ["alcantarillado"]),
 "pct_camara_septica":     ("desague_", ["camaraséptica"]),
 "pct_pozo_ciego":         ("desague_", ["pozociego"]),
 "pct_desague_superficie": ("desague_", ["superficie"]),
 "pct_sin_desague":        ("desague_", ["notiene"]),
 "pct_electricidad":       ("energiaelectrica_", ["serviciopublico", "motorpropio",
                                                  "panelsolar", "otra"]),
 "pct_elec_red":           ("energiaelectrica_", ["serviciopublico"]),
 "pct_panel_solar":        ("energiaelectrica_", ["panelsolar"]),
 "pct_sin_energia":        ("energiaelectrica_", ["notiene"]),
 "pct_gas_garrafa":        ("combustible_", ["gasgarrafa"]),
 "pct_gas_red":            ("combustible_", ["gascañería"]),
 "pct_lena_guano":         ("combustible_", ["leña", "guano"]),
 "pct_basura_formal":      ("basura_",  ["basureropúblico", "carrobasurero"]),
 "pct_basura_carro":       ("basura_",  ["carrobasurero"]),
 "pct_basura_quema":       ("basura_",  ["quema"]),
 "pct_basura_entierra":    ("basura_",  ["entierra"]),
 "pct_basura_informal":    ("basura_",  ["calle", "río"]),
 "pct_viv_propia":         ("viviendatenencia_", ["propia"]),
 "pct_viv_alquilada":      ("viviendatenencia_", ["alquilada"]),
 "pct_viv_anticretico":    ("viviendatenencia_", ["anticretico"]),
 "pct_viv_prestada":       ("viviendatenencia_", ["prestada"]),
 "pct_pared_ladrillo":     ("material_paredes_", ["ladrillo"]),
 "pct_pared_adobe":        ("material_paredes_", ["adobe"]),
 "pct_pared_madera":       ("material_paredes_", ["madera"]),
 "pct_revoque":            ("material_revoque_", ["con"]),
 "pct_techo_calamina":     ("material_techo_", ["calamina"]),
 "pct_techo_teja":         ("material_techo_", ["teja"]),
 "pct_techo_losa":         ("material_techo_", ["losa"]),
 "pct_techo_paja":         ("material_techo_", ["paja"]),
 "pct_piso_tierra":        ("material_piso_", ["tierra"]),
 "pct_piso_cemento":       ("material_piso_", ["cemento"]),
 "pct_piso_ceramica":      ("material_piso_", ["ceramica", "mosaico"]),
 "pct_hogar_unipersonal":  ("hogar_",   ["unipersonal"]),
 "pct_hogar_extendido":    ("hogar_",   ["extendido"]),
 "pct_hogar_monoparental": ("hogar_",   ["monoparental"]),
 "pct_radio":              ("tics_",    ["radio"]),
 "pct_televisor":          ("tics_",    ["televisor"]),
 "pct_internet":           ("tics_",    ["internet"]),
 "pct_celular":            ("tics_",    ["celular"]),
 # personas: la ficha trae todo partido por sexo, así que el denominador es la
 # suma de las dos mitades
 "pct_menor20":            ("edad_",    ["0a19_hombre", "0a19_mujer"]),
 "pct_60_mas":             ("edad_",    ["60omas_hombre", "60omas_mujer"]),
 "pct_edu_superior":       ("educacion_", ["superior_hombre", "superior_mujer"]),
 "pct_edu_ninguno":        ("educacion_", ["ninguno_hombre", "ninguno_mujer"]),
 "pct_salud_publica":      ("salud_",   ["centropublico_hombre", "centropublico_mujer"]),
 "pct_salud_privada":      ("salud_",   ["centroprivado_hombre", "centroprivado_mujer"]),
 "pct_salud_tradic":       ("salud_",   ["medicinatradicional_hombre", "medicinatradicional_mujer"]),
 "pct_sin_seguro":         ("saludafiliacion_", ["ninguno_hombre", "ninguno_mujer"]),
 "pct_sus":                ("saludafiliacion_", ["sus_hombre", "sus_mujer"]),
 "pct_nacido_otro_municipio": ("nacimiento_", ["otromunicipio_hombre", "otromunicipio_mujer"]),
 "pct_nacido_extranjero":  ("nacimiento_", ["otropais_hombre", "otropais_mujer"]),
 "pct_catocu_asalariado":  ("ocupacion_", ["empleado_hombre", "empleado_mujer"]),
 "pct_catocu_cuenta_propia": ("ocupacion_", ["cuentapropia_hombre", "cuentapropia_mujer"]),
 "pct_rama_agricultura":   ("actividad_", ["agricultura_hombre", "agricultura_mujer"]),
 "pct_rama_comercio":      ("actividad_", ["comercio_hombre", "comercio_mujer"]),
 "pct_rama_manufactura":   ("actividad_", ["manufactura_hombre", "manufactura_mujer"]),
 "pct_rama_construccion":  ("actividad_", ["construccion_hombre", "construccion_mujer"]),
 "pct_rama_transporte":    ("actividad_", ["transporte_hombre", "transporte_mujer"]),
 "pct_rama_alojamiento":   ("actividad_", ["alojamientoycomida_hombre", "alojamientoycomida_mujer"]),

 # ── AGREGADOS 2026-08-19 ────────────────────────────────────────────────
 # La ficha trae 127 categorías y este motor usaba 63. Lo que sigue son las
 # que faltaban y tienen sentido a nivel manzana. Las que además existen en
 # el catálogo municipal bajan como CONTINUAS; las otras quedan rotuladas
 # como "sólo manzana" (decisión de Carlos, 2026-08-19).

 # tramos de edad que faltaban: sólo se emitían los dos extremos
 "pct_20_39":              ("edad_",    ["20a39_hombre", "20a39_mujer"]),
 "pct_40_59":              ("edad_",    ["40a59_hombre", "40a59_mujer"]),

 # familia HACINAMIENTO — estaba entera sin tocar.
 # ★ El municipal define hacinamiento como "más de 3 personas por dormitorio",
 #   que es palabra por palabra el "alto" del glosario del INE, así que la
 #   clave canónica es la misma y el indicador es continuo.
 "pct_hacinamiento":       ("hacinamiento_", ["alto"]),
 "pct_hacinamiento_medio": ("hacinamiento_", ["medio"]),

 # familia VIVIENDATIPO — estaba entera sin tocar
 "pct_vivienda_desocupada": ("viviendatipo_", ["particulardesocupada"]),
 "pct_viv_colectiva":      ("viviendatipo_", ["colectiva"]),

 # familia RESIDENCIA — estaba entera sin tocar. Es dónde vivía la persona
 # hace 5 años: migración RECIENTE, distinta del lugar de nacimiento que ya
 # estaba.
 "pct_migrante_reciente":  ("residencia_", ["otromunicipio_hombre", "otromunicipio_mujer"]),
 "pct_res5_extranjero":    ("residencia_", ["otropais_hombre", "otropais_mujer"]),

 # educación: sólo se emitían los dos extremos (superior y ninguno)
 "pct_edu_primaria":       ("educacion_", ["primaria_hombre", "primaria_mujer"]),
 "pct_edu_secundaria":     ("educacion_", ["secundaria_hombre", "secundaria_mujer"]),

 # ramas que el motor agrupaba en "otras"
 "pct_rama_ensenanza":     ("actividad_", ["enseñanza_hombre", "enseñanza_mujer"]),
 "pct_rama_salud":         ("actividad_", ["saludyasistencia_hombre", "saludyasistencia_mujer"]),

 # tipos de hogar que faltaban
 "pct_hogar_nuclear":      ("hogar_",   ["parejanuclear", "nuclearcompleto"]),
 "pct_hogar_compuesto":    ("hogar_",   ["compuesto"]),
 "pct_hogar_sin_jefe":     ("hogar_",   ["sinjefe"]),

 # materiales de piso que se perdían
 "pct_piso_madera":        ("material_piso_", ["madera", "machimbre"]),
 "pct_piso_ladrillo":      ("material_piso_", ["ladrillo"]),
 "pct_pared_tabique":      ("material_paredes_", ["tabique"]),

 # fuentes de agua que faltaban. ⚠️ Acá la ficha SEPARA vertiente protegida de
 # no protegida, cosa que el microdato de 2012 no permite (ver la nota de
 # `pct_agua_mejorada` en el catálogo): a nivel manzana el corte SÍ es decidible.
 "pct_agua_mejorada":      ("agua_",    ["cañería", "piletapública", "pozoconbomba",
                                          "vertienteprotegida"]),
 "pct_agua_vertiente":     ("agua_",    ["vertienteprotegida", "vertientenoprotegida"]),
 "pct_agua_lluvia":        ("agua_",    ["cosechadelluvia"]),

 # cómo se cocina, más allá del gas y la leña
 "pct_cocina_electricidad": ("combustible_", ["electricidad"]),
 "pct_cocina_solar":       ("combustible_", ["energíasolar"]),
 "pct_no_cocina":          ("combustible_", ["nococina"]),
}

# ★ BRECHAS DE GÉNERO. La ficha parte 43 categorías por sexo, así que la brecha
#   se puede medir dentro de la manzana. Se emiten sólo las que tienen sentido
#   territorial; el resto quedaría como ruido en manzanas chicas.
#   Cada una es (prefijo, sufijo sin el sexo): pp de mujeres MENOS pp de hombres,
#   calculadas cada una sobre SU propio denominador por sexo — que es lo que
#   hace `motor_persona.py` para las brechas municipales.
BRECHAS = {
 "brecha_edu_superior":    ("educacion_", "superior"),
 "brecha_edu_ninguno":     ("educacion_", "ninguno"),
 "brecha_sin_seguro":      ("saludafiliacion_", "ninguno"),
 "brecha_cuenta_propia":   ("ocupacion_", "cuentapropia"),
}
# las preguntas cuyo "sin especificar" NO debe entrar al denominador
SIN_ESP = ("sinespecificar",)

# ★ DENOMINADOR ESPECIAL. La regla general —sumar todas las categorías del
#   prefijo— sirve para las preguntas de opción única (agua, techo, tenencia…),
#   pero NO para las de sí/no independientes: `tics_radio`, `tics_televisor`,
#   `tics_celular` e `tics_internet` son CUATRO preguntas distintas, no cuatro
#   categorías de una. Sumarlas daba denominadores absurdos y errores de 40 a 50
#   pp contra el microdato. Su denominador es el total de viviendas del manzano.
DEN_PROPIO = {"tics_": ["viviendatipo_personaspresentes"]}


def areas_m2():
    """Superficie de cada manzano, en m². Sale de la geometría del geoportal.

    ⚠️ Se reproyecta a UTM 20S antes de medir: calcular áreas sobre grados
    da un número que no es una superficie. Son 247.429 polígonos y geopandas
    los resuelve en un par de segundos."""
    import geopandas as gpd
    g = gpd.read_parquet(FUENTE / "manzanos.parquet", columns=["codigo", "geometry"])
    return pd.Series(g.to_crs(32720).area.values, index=g.codigo.values, name="area_m2")


def calcular_manzana():
    f = pd.read_parquet(FUENTE / "fichas.parquet")
    cols = list(f.columns)

    # ★ EL UNIVERSO SON TODOS LOS MANZANOS, NO SÓLO LOS QUE TIENEN FICHA.
    #   `poblacion.parquet` trae personas y viviendas de los 247.429, incluidos
    #   los 116k que el INE suprime por privacidad en las fichas. En la región
    #   metropolitana eso son 13.194 manzanas y 137.789 personas —el 6,2%— que
    #   hasta ahora se pintaban del gris de "sin dato" teniendo dato.
    #   Los indicadores de ficha quedan vacíos ahí, que es lo correcto; la
    #   población y la densidad, no.
    pob = pd.read_parquet(FUENTE / "poblacion.parquet")
    out = pd.DataFrame({"codigo": pob.codigo})
    f = out[["codigo"]].merge(f, on="codigo", how="left")
    faltan = []
    for k, (pref, sufijos) in IND.items():
        grupo = [c for c in cols if c.startswith(pref) and not any(s in c for s in SIN_ESP)]
        num_cols = [c for c in grupo if any(c == pref + s for s in sufijos)]
        if not num_cols:
            faltan.append((k, pref, [c[len(pref):] for c in grupo][:8])); continue
        den = f[DEN_PROPIO[pref]].sum(axis=1) if pref in DEN_PROPIO else f[grupo].sum(axis=1)
        out[k] = 100 * f[num_cols].sum(axis=1) / den.replace(0, np.nan)
    # ── brechas: cada sexo sobre su propio denominador ──────────────────
    for k, (pref, suf) in BRECHAS.items():
        grupo = [c for c in cols if c.startswith(pref) and not any(s in c for s in SIN_ESP)]
        gh = [c for c in grupo if c.endswith("_hombre")]
        gm = [c for c in grupo if c.endswith("_mujer")]
        nh, nm = pref + suf + "_hombre", pref + suf + "_mujer"
        if not (gh and gm and nh in f.columns and nm in f.columns):
            faltan.append((k, pref, [])); continue
        ph = 100 * f[nh] / f[gh].sum(axis=1).replace(0, np.nan)
        pm = 100 * f[nm] / f[gm].sum(axis=1).replace(0, np.nan)
        out[k] = pm - ph

    # ── conteos y densidad ──────────────────────────────────────────────
    # No son porcentajes y por eso no caben en `IND`: vienen de otra fuente
    # (poblacion.parquet) y la densidad necesita además la geometría.
    # ⚠️ El nombre canónico de la población es `pob_total`, no `personas`: así lo
    #    declara el catálogo y así se llama en el motor municipal. Emitirlo con
    #    otro nombre lo dejaba fuera del cruce sin que nada fallara.
    out["pob_total"] = pob.personas.values
    out["viviendas"] = pob.viviendas.values
    # personas por vivienda: el catálogo ya lo declara con nivel manzana y sale
    # de dividir los dos conteos que acaban de entrar
    out["tam_hogar"] = out.pob_total / out.viviendas.replace(0, np.nan)
    a = areas_m2().reindex(out.codigo).values
    # hab/HECTÁREA, que es la unidad que declara el catálogo. En km² los
    # números de manzana salen en miles y no se pueden poner al lado de la
    # densidad municipal, que en hectáreas va de 0 a 25.
    out["densidad"] = out.pob_total.values / (a / 1e4)
    # una manzana sin superficie medible no tiene densidad; no es un cero
    out.loc[~np.isfinite(out.densidad), "densidad"] = np.nan
    # ★ La razón de masculinidad es un COCIENTE de dos totales, no un
    #   porcentaje sobre un denominador común: se arma aparte.
    hs = [c for c in cols if c.startswith("edad_") and c.endswith("_hombre")]
    ms = [c for c in cols if c.startswith("edad_") and c.endswith("_mujer")]
    out["indice_masculinidad"] = 100 * f[hs].sum(axis=1) / f[ms].sum(axis=1).replace(0, np.nan)

    if faltan:
        print("⚠️ sin columna en la ficha:")
        for k, pref, hay in faltan:
            print(f"   {k:<28} prefijo {pref!r} — hay: {hay}")
    listos = [k for k in list(IND) + list(BRECHAS) +
              ["pob_total", "viviendas", "tam_hogar", "densidad", "indice_masculinidad"]
              if k in out.columns]
    return out, listos


if __name__ == "__main__":
    mz, listos = calcular_manzana()
    print(f"\n{len(mz):,} manzanas · {len(listos)} indicadores canónicos")

    # ── control: agregar por municipio y contrastar con el microdato urbano ──
    geo = pd.read_parquet(FUENTE / "manzanos.parquet", columns=["codigo", "departamento", "municipio"])
    # ★ EL PUENTE MANZANO→MUNICIPIO SE LEE, NO SE REHACE (2026-09-04, port
    #   nacional). Acá vivía la misma resolución por nombre que hace
    #   `armar_municipios.py`, y a escala país dejaba 2.287 manzanos sin
    #   municipio: cinco AUTONOMÍAS INDÍGENAS que el geoportal rotula por el
    #   nombre de su autonomía («AIOC de Salinas» por Salinas de Garci Mendoza)
    #   más un tipeo del geoportal («Vitiche» por Vitichi). En la región
    #   metropolitana no se notaba porque los seis quedan afuera.
    #   Dos copias del mismo puente se desincronizan en cuanto una se corrige,
    #   así que hay una sola y ésta la consume.
    puente = pd.read_parquet(AQUI.parent / "datos" / "manzano_municipio.parquet")
    geo = geo.merge(puente[["codigo", "cod_ine"]], on="codigo", how="left")
    print(f"manzanos con municipio identificado: {geo.cod_ine.notna().mean():.1%}")

    f = pd.read_parquet(FUENTE / "fichas.parquet")
    d = f.merge(geo[["codigo", "cod_ine"]], on="codigo", how="left")
    agr = {}
    cols = list(f.columns)
    for k, (pref, sufijos) in IND.items():
        grupo = [c for c in cols if c.startswith(pref) and not any(s in c for s in SIN_ESP)]
        num_cols = [c for c in grupo if any(c == pref + s for s in sufijos)]
        if not num_cols: continue
        g = d.groupby("cod_ine")
        dcols = DEN_PROPIO[pref] if pref in DEN_PROPIO else grupo
        agr[k] = 100 * g[num_cols].sum().sum(axis=1) / g[dcols].sum().sum(axis=1)
    agr = pd.DataFrame(agr)

    # ★ LOS CONTEOS SE AGREGAN SUMANDO, no promediando, y por eso no caben en el
    #   bucle de arriba —que arma porcentajes—. Sin esto quedaban FUERA del
    #   `manzana_agregado_municipal.csv`, y como `comparar_niveles.py` sólo puede
    #   verificar lo que está en ese archivo, población y densidad terminaban
    #   sin contraste y por lo tanto fuera del tablero: entraban al pipeline y
    #   desaparecían sin que nada avisara.
    pob = pd.read_parquet(FUENTE / "poblacion.parquet")
    ar = areas_m2()
    cg = geo[["codigo", "cod_ine"]].merge(pob, on="codigo", how="left")
    cg["area_m2"] = ar.reindex(cg.codigo).values
    t = cg.groupby("cod_ine").agg(_p=("personas", "sum"), _v=("viviendas", "sum"),
                                  _a=("area_m2", "sum"))
    agr["pob_total"] = t._p
    agr["viviendas"] = t._v
    agr["tam_hogar"] = t._p / t._v.replace(0, np.nan)
    agr["densidad"] = t._p / (t._a / 1e4)
    # razón de dos totales, igual que en la manzana
    hs = [c for c in cols if c.startswith("edad_") and c.endswith("_hombre")]
    ms = [c for c in cols if c.startswith("edad_") and c.endswith("_mujer")]
    gh = d.groupby("cod_ine")[hs].sum().sum(axis=1)
    gm = d.groupby("cod_ine")[ms].sum().sum(axis=1)
    agr["indice_masculinidad"] = 100 * gh / gm.replace(0, np.nan)
    # las brechas se rearman de los TOTALES del municipio: promediar brechas
    # manzana por manzana daría otra cosa (y le daría el mismo peso a una
    # manzana de 20 personas que a una de 2.000)
    for k, (pref, suf) in BRECHAS.items():
        grupo = [c for c in cols if c.startswith(pref) and not any(x in c for x in SIN_ESP)]
        h = [c for c in grupo if c.endswith("_hombre")]
        m_ = [c for c in grupo if c.endswith("_mujer")]
        nh, nm = pref + suf + "_hombre", pref + suf + "_mujer"
        if nh not in d.columns or nm not in d.columns:
            continue
        g_ = d.groupby("cod_ine")
        ph = 100 * g_[nh].sum() / g_[h].sum().sum(axis=1).replace(0, np.nan)
        pm = 100 * g_[nm].sum() / g_[m_].sum().sum(axis=1).replace(0, np.nan)
        agr[k] = pm - ph

    agr.to_csv(AQUI / "manzana_agregado_municipal.csv", encoding="utf-8")
    mz.to_csv(AQUI / "manzana_2024.csv", index=False, encoding="utf-8")

    urb = pd.read_csv(AQUI / "municipal_urbano_2024.csv", index_col=0, dtype={0: str})
    urb.index = urb.index.astype(str).str.zfill(6)
    comunes = [c for c in agr.columns if c in urb.columns]
    print(f"\nCONTRASTE contra el microdato urbano — {len(comunes)} indicadores comparables")
    print(f"{'indicador':<30}{'|dif| media':>13}{'mediana':>10}{'máx':>10}")
    filas = []
    for c in comunes:
        dif = (agr[c] - urb[c]).abs().dropna()
        if len(dif) < 50: continue
        filas.append((c, dif.mean(), dif.median(), dif.max()))
    filas.sort(key=lambda x: x[1])
    for c, m, md, mx in filas:
        print(f"{c:<30}{m:>12.2f}{md:>10.2f}{mx:>10.2f}")
    tot = np.mean([x[1] for x in filas])
    print(f"\nerror absoluto medio global: {tot:.2f} pp  ·  {len(filas)} indicadores")
    print("→ manzana_2024.csv · manzana_agregado_municipal.csv")
