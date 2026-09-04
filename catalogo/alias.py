# -*- coding: utf-8 -*-
"""
ALIAS — un solo vocabulario entre el catálogo y los motores.
=============================================================

Los motores crecieron con nombres propios (`pct_catocu_asalariado`,
`pct_rama_agricultura`, `poblacion`) mientras el catálogo declaraba otros
(`pct_asalariados`, `pct_agricultura`, `pob_total`). No es un problema de
cálculo —los números son los mismos— pero sí de gobierno: si hay dos
vocabularios, el catálogo deja de ser la fuente única.

Acá se resuelve en una dirección: **manda el catálogo**. Los motores siguen
emitiendo lo que emiten y este archivo los traduce al vocabulario declarado.

`NUEVOS` son los indicadores que los motores producen y el catálogo todavía no
declara: hay que agregarlos a `catalogo.py`, no renombrarlos.
"""

# ── VOCABULARIO DEL ATLAS SOCIOECONÓMICO PUBLICADO ──────────────────────────
# ★ El Atlas usa un TERCER vocabulario, distinto del motor y del catálogo. Al
#   comparar sus 136 indicadores contra el motor aparecían 9 "que no
#   producimos"; leyendo sus definiciones, SEIS son el mismo indicador con otro
#   nombre y ya están validados al 343/343 contra el INE. Sólo tres había que
#   calcular (los cortes femeninos). Se declara acá para que el reemplazo del
#   `data.json` no pierda ningún indicador por una diferencia de rótulo.
#   `pct_disc_cognitiva` es literal: la variable `p42d_comuni` del censo se
#   llama "dificultad permanente para comunicarse, aprender, concentrarse o
#   razonar", que es palabra por palabra la definición del Atlas.
ATLAS = {
 "pct_gas_natural":        "pct_gas_red",
 "pct_combustible_solido": "pct_lena_guano",
 "pct_vivienda_propia":    "pct_viv_propia",
 "pct_alquiler":           "pct_viv_alquilada",
 "pct_tv":                 "pct_televisor",
 "pct_disc_cognitiva":     "pct_disc_comunicar",
}

# nombre en el motor -> nombre en el catálogo
ALIAS = {
 "poblacion":                    "pob_total",
 "n_mujeres":                    "pob_mujeres",
 "n_viviendas":                  "viviendas",
 "pct_catocu_asalariado":        "pct_asalariados",
 "pct_catocu_cuenta_propia":     "pct_cuenta_propia",
 "pct_catocu_empleador":         "pct_empleadores",
 "pct_catocu_familiar":          "pct_trab_familiar",
 "pct_rama_agricultura":         "pct_agricultura",
 "pct_rama_comercio":            "pct_comercio",
 "pct_rama_manufactura":         "pct_manufactura",
 "pct_rama_construccion":        "pct_construccion",
 "pct_rama_transporte":          "pct_transporte",
 "pct_rama_alojamiento":         "pct_alojamiento",
 "pct_rama_adm_publica":         "pct_admin_publica",
 "pct_salud_caja":               "pct_caja_salud",
 "pct_salud_tradic":             "pct_salud_tradicional",
 "pct_salud_autome":             "pct_automedicacion",
 "pct_salud_casera":             "pct_remedios_caseros",
 "pct_edu_ninguno":              "pct_sin_educacion",
 "pct_asistencia_4_17":          "pct_asistencia_escolar",
 "pct_cedula":                   "pct_cedula_identidad",
 "pct_idioma_castellano":        "pct_idioma_materno_castellano",
 "pct_afiliado_sus":             "pct_sus",
 "pct_afiliado_privado":         "pct_seguro_privado",
 "pct_afiliado_ninguno":         "pct_sin_seguro",
 "pct_pueblo_quechua":           "pct_quechua",
 "pct_pueblo_aymara":            "pct_aymara",
 "pct_pueblo_guarani":           "pct_guarani",
 "pct_pueblo_chiquitano":        "pct_chiquitano",
}

# lo que el motor produce y el catálogo aún no declara — se AGREGA al catálogo,
# no se renombra. Son indicadores nuevos, no duplicados.
NUEVOS = [
 "pct_ecivil_casado", "pct_ecivil_conviviente", "pct_ecivil_separado_divorciado",
 "pct_ecivil_soltero", "pct_ecivil_viudo",
 "pct_afiliado_caja", "edad_media_jefe", "pct_catocu_hogar",
 "pct_catocu_cooperativista", "pct_catocu_asalariado_amplio",
 "pct_rama_mineria", "pct_rama_ensenanza", "pct_rama_salud",
 "pct_telefonia", "pct_telefono_fijo", "pct_calefon", "pct_muertes_covid",
 "emigrantes", "fallecidos", "poblacion_nbi",
 # nivel HOGAR (2026-08-13): salen del enlace persona↔vivienda
 "hogares", "tam_hogar_pers",
 # flujos origen-destino, sólo 2024 (ver motor_flujos.py)
 "inmigrantes_5a", "emigrantes_internos_5a", "saldo_migratorio",
 "inmigrantes_vida", "emigrantes_internos_vida", "saldo_migratorio_vida",
 "entran_a_trabajar", "salen_a_trabajar", "poblacion_flotante",
 "trabajan_en_su_municipio",
 # pueblos que el catálogo no declaraba por separado
 "pct_pueblo_afroboliviano", "pct_pueblo_mojeno", "pct_pueblo_movima",
 "pct_pueblo_trinitario",
 # ⚠️ `guarayo` y `yuracare` dan 0,00% en 2024: esas etiquetas no existen en el
 #    diccionario de 2024 (sí en el de 2012). No es que no haya gente — es que
 #    el emparejamiento por nombre no encuentra la categoría. Revisar antes de
 #    publicarlos; por ahora NO se muestran.
 "pct_pueblo_guarayo", "pct_pueblo_yuracare",
]


def renombrar(df):
    """Aplica el vocabulario del catálogo a un DataFrame del motor."""
    ren = {k: v for k, v in ALIAS.items() if k in df.columns}
    # si el destino ya existe, el alias sobra: se descarta la columna duplicada
    choques = [k for k, v in ren.items() if v in df.columns]
    if choques:
        df = df.drop(columns=choques)
        ren = {k: v for k, v in ren.items() if k not in choques}
    return df.rename(columns=ren)


if __name__ == "__main__":
    import pandas as pd, json, pathlib
    AQUI = pathlib.Path(__file__).parent
    cat = {i["k"] for i in json.loads((AQUI / "catalogo.json")
                                      .read_text(encoding="utf-8"))["indicadores"]}
    motor = set()
    for f in ("municipal_2024", "personas_2024", "nbi_2024", "otros_2024"):
        p = AQUI / f"{f}.csv"
        if p.exists():
            motor |= {c for c in pd.read_csv(p, index_col=0, nrows=1).columns
                      if not c.startswith("_den_")}
    tras = {ALIAS.get(c, c) for c in motor}
    print(f"catálogo {len(cat)} · motor {len(motor)}")
    print(f"  coincidían antes del alias : {len(cat & motor)}")
    print(f"  coinciden después del alias: {len(cat & tras)}")
    sobran = sorted(tras - cat - set(NUEVOS))
    if sobran:
        print(f"  ⚠️ sin alias ni declarados: {sobran}")
    print(f"  del catálogo aún sin calcular: {len(cat - tras)}")
