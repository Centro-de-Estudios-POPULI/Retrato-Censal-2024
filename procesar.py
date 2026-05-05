"""
Atlas de Manzanos Bolivia CPV 2024 — Pipeline de datos
Fuente: mauforonda/atlasurbano
"""
import json, re, unicodedata, warnings
import pandas as pd
import geopandas as gpd
import numpy as np
from pathlib import Path

warnings.filterwarnings("ignore")

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

SRC         = Path("C:/Users/HP/Downloads")
SIMPLIFY    = 0.00005   # ~5 m en WGS84
MIN_MANZANOS = 5

def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")

def safe_div(num, den):
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(den > 0, num / den, np.nan)

def calc(arr, scale=100):
    return pd.array(pd.Series(arr * scale).round(0), dtype="Int64")

# ── Carga ─────────────────────────────────────────────────────────────────────
print("Cargando parquets...")
gdf = gpd.read_parquet(SRC / "manzanos.parquet").set_crs("EPSG:4326")
pop = pd.read_parquet(SRC / "poblacion.parquet")
fic = pd.read_parquet(SRC / "fichas.parquet")
print(f"  {len(gdf):,} manzanos  |  {len(fic):,} con ficha")

# ── Área en hectáreas ─────────────────────────────────────────────────────────
print("Calculando areas...")
gdf["area_ha"] = gdf.to_crs("EPSG:32720").geometry.area / 10000

# ── Join completo (todos los manzanos para calcular cobertura) ────────────────
df_all = gdf.merge(pop, on="codigo")

# Cobertura por municipio: manzanos_total vs validados
cob = df_all.groupby(["departamento","municipio"]).agg(
    manzanos_total=("codigo","count"),
    manzanos_val=("validado", "sum"),
    poblacion_total=("personas", "sum")
).reset_index()
cob["cobertura"] = (cob["manzanos_val"] / cob["manzanos_total"] * 100).round(1)

# Solo validados para indicadores
df_val = df_all[df_all["validado"] == True].merge(fic, on="codigo", how="left").copy()
print(f"  {len(df_val):,} manzanos validados")

# ── Poblaciones base ──────────────────────────────────────────────────────────
f = df_val

edad_h      = f[["edad_0a19_hombre","edad_20a39_hombre","edad_40a59_hombre","edad_60omas_hombre"]].sum(axis=1)
edad_m      = f[["edad_0a19_mujer","edad_20a39_mujer","edad_40a59_mujer","edad_60omas_mujer"]].sum(axis=1)
total_edad  = edad_h + edad_m

res_h       = f[["residencia_aqui_hombre","residencia_otromunicipio_hombre"]].sum(axis=1)
res_m       = f[["residencia_aqui_mujer","residencia_otromunicipio_mujer"]].sum(axis=1)
residente   = res_h + res_m

# Ocupados: incluye sinespecificar para que coincida con el universo de las
# columnas actividad_*, que sí contabilizan a esas personas. Sin esto, los
# indicadores pct_<actividad> pueden superar el 100% (ratio = numerador
# completo / denominador truncado).
ocup_h      = f[["ocupacion_empleado_hombre","ocupacion_cuentapropia_hombre",
                  "ocupacion_otros_hombre","ocupacion_sinespecificar_hombre"]].sum(axis=1)
ocup_m      = f[["ocupacion_empleado_mujer","ocupacion_cuentapropia_mujer",
                  "ocupacion_otros_mujer","ocupacion_sinespecificar_mujer"]].sum(axis=1)
ocupados    = ocup_h + ocup_m

educ_cols_h = ["educacion_ninguno_hombre","educacion_primaria_hombre","educacion_secundaria_hombre",
               "educacion_superior_hombre","educacion_sinespecificar_hombre"]
educ_cols_m = ["educacion_ninguno_mujer","educacion_primaria_mujer","educacion_secundaria_mujer",
               "educacion_superior_mujer","educacion_sinespecificar_mujer"]
educ_total  = f[educ_cols_h + educ_cols_m].sum(axis=1)
educ_h      = f[educ_cols_h].sum(axis=1)
educ_m      = f[educ_cols_m].sum(axis=1)

afil_h      = f[["saludafiliacion_sus_hombre","saludafiliacion_cajadesalud_hombre",
                  "saludafiliacion_seguroprivado_hombre","saludafiliacion_ninguno_hombre"]].sum(axis=1)
afil_m      = f[["saludafiliacion_sus_mujer","saludafiliacion_cajadesalud_mujer",
                  "saludafiliacion_seguroprivado_mujer","saludafiliacion_ninguno_mujer"]].sum(axis=1)
afil_total  = afil_h + afil_m

salud_total = f[["salud_centropublico_hombre","salud_cajadesalud_hombre","salud_centroprivado_hombre",
                  "salud_atenciondomicilio_hombre","salud_medicinatradicional_hombre",
                  "salud_farmaciasinreceta_hombre","salud_remedioscaseros_hombre",
                  "salud_centropublico_mujer","salud_cajadesalud_mujer","salud_centroprivado_mujer",
                  "salud_atenciondomicilio_mujer","salud_medicinatradicional_mujer",
                  "salud_farmaciasinreceta_mujer","salud_remedioscaseros_mujer"]].sum(axis=1)

viv         = f["viviendatipo_personaspresentes"]

# Nombres exactos de columnas del parquet de Foronda. Antes se usaban lookups
# con filtros laxos (next(c for c in ... if "le" in c)) que matcheaban varias
# columnas y elegían la primera del orden — generaban bugs silenciosos: el
# indicador "% leña o guano" sumaba "% gas garrafa" (factor 26x sobrestimado),
# y "% basura calle o río" sumaba "% calle" dos veces (max 200%).
COL_AGUA_RED      = "agua_cañería"
COL_GAS_RED       = "combustible_gascañería"
COL_BASURA_PUB    = "basura_basureropúblico"
COL_LENA          = "combustible_leña"
COL_GUANO         = "combustible_guano"
COL_BASURA_CALLE  = "basura_calle"
COL_BASURA_RIO    = "basura_río"
COL_CAMARA_SEPT   = "desague_camaraséptica"

# ── Indicadores ───────────────────────────────────────────────────────────────
print("Calculando indicadores...")

ind = pd.DataFrame({"codigo": f["codigo"].values})

# Demografía
ind["personas_x_ha"]        = calc(safe_div(f["personas"].values, f["area_ha"].values), 1)
ind["masculinidad"]         = calc(safe_div(edad_h.values, edad_m.values))
ind["pct_menor20"]          = calc(safe_div((f["edad_0a19_hombre"]+f["edad_0a19_mujer"]).values, total_edad.values))
ind["pct_60mas"]            = calc(safe_div((f["edad_60omas_hombre"]+f["edad_60omas_mujer"]).values, total_edad.values))
ind["pct_migrante"]         = calc(safe_div((f["nacimiento_otromunicipio_hombre"]+f["nacimiento_otromunicipio_mujer"]+
                                              f["nacimiento_otropais_hombre"]+f["nacimiento_otropais_mujer"]).values, total_edad.values))

# Economía
ind["dependencia_econ"]     = calc(safe_div((residente - ocupados).values, ocupados.values))
ind["pct_empleados"]        = calc(safe_div((f["ocupacion_empleado_hombre"]+f["ocupacion_empleado_mujer"]).values, ocupados.values))
ind["pct_cuentapropia"]     = calc(safe_div((f["ocupacion_cuentapropia_hombre"]+f["ocupacion_cuentapropia_mujer"]).values, ocupados.values))
ind["pct_agricultura"]      = calc(safe_div((f["actividad_agricultura_hombre"]+f["actividad_agricultura_mujer"]).values, ocupados.values))
ind["pct_comercio"]         = calc(safe_div((f["actividad_comercio_hombre"]+f["actividad_comercio_mujer"]).values, ocupados.values))
ind["pct_manufactura"]      = calc(safe_div((f["actividad_manufactura_hombre"]+f["actividad_manufactura_mujer"]).values, ocupados.values))
ind["pct_construccion"]     = calc(safe_div((f["actividad_construccion_hombre"]+f["actividad_construccion_mujer"]).values, ocupados.values))
ind["pct_transporte"]       = calc(safe_div((f["actividad_transporte_hombre"]+f["actividad_transporte_mujer"]).values, ocupados.values))
ind["pct_alojamiento"]      = calc(safe_div((f["actividad_alojamientoycomida_hombre"]+f["actividad_alojamientoycomida_mujer"]).values, ocupados.values))

# Educación
ind["pct_sin_educacion"]    = calc(safe_div((f["educacion_ninguno_hombre"]+f["educacion_ninguno_mujer"]).values, educ_total.values))
ind["pct_educ_superior"]    = calc(safe_div((f["educacion_superior_hombre"]+f["educacion_superior_mujer"]).values, educ_total.values))
ind["brecha_educ"]          = calc(
    safe_div((f["educacion_secundaria_mujer"]+f["educacion_superior_mujer"]).values, educ_m.values) -
    safe_div((f["educacion_secundaria_hombre"]+f["educacion_superior_hombre"]).values, educ_h.values)
)

# Salud — acceso formal
ind["pct_sin_seguro"]       = calc(safe_div((f["saludafiliacion_ninguno_hombre"]+f["saludafiliacion_ninguno_mujer"]).values, afil_total.values))
ind["pct_sus"]              = calc(safe_div((f["saludafiliacion_sus_hombre"]+f["saludafiliacion_sus_mujer"]).values, afil_total.values))
ind["pct_seguro_privado"]   = calc(safe_div((f["saludafiliacion_seguroprivado_hombre"]+f["saludafiliacion_seguroprivado_mujer"]).values, afil_total.values))
ind["brecha_seguro"]        = calc(
    safe_div((f["saludafiliacion_sus_mujer"]+f["saludafiliacion_cajadesalud_mujer"]+f["saludafiliacion_seguroprivado_mujer"]).values, afil_m.values) -
    safe_div((f["saludafiliacion_sus_hombre"]+f["saludafiliacion_cajadesalud_hombre"]+f["saludafiliacion_seguroprivado_hombre"]).values, afil_h.values)
)

# Salud — atención
ind["pct_salud_publica"]    = calc(safe_div((f["salud_centropublico_hombre"]+f["salud_centropublico_mujer"]).values, salud_total.values))
ind["pct_med_tradicional"]  = calc(safe_div((f["salud_medicinatradicional_hombre"]+f["salud_medicinatradicional_mujer"]).values, salud_total.values))
ind["pct_automedicacion"]   = calc(safe_div((f["salud_farmaciasinreceta_hombre"]+f["salud_farmaciasinreceta_mujer"]).values, salud_total.values))
ind["pct_remedios_caseros"] = calc(safe_div((f["salud_remedioscaseros_hombre"]+f["salud_remedioscaseros_mujer"]).values, salud_total.values))

# Vivienda
ind["pct_viv_desocupada"]   = calc(safe_div(f["viviendatipo_particulardesocupada"].values, f["viviendatipo_particular"].values))
ind["pct_alquiler"]         = calc(safe_div((f["viviendatenencia_alquilada"]+f["viviendatenencia_anticretico"]).values, viv.values))

# Servicios básicos — energía eléctrica
ind["pct_electricidad"]     = calc(safe_div(f["energiaelectrica_serviciopublico"].values, viv.values))
ind["pct_sin_electricidad"] = calc(safe_div(f["energiaelectrica_notiene"].values, viv.values))

# Servicios básicos — agua
ind["pct_agua_red"]         = calc(safe_div(f[COL_AGUA_RED].values, viv.values))

# Servicios básicos — saneamiento (desagüe)
ind["pct_alcantarillado"]   = calc(safe_div(f["desague_alcantarillado"].values, viv.values))
ind["pct_camara_septica"]   = calc(safe_div(f[COL_CAMARA_SEPT].values, viv.values))
ind["pct_pozo_ciego"]       = calc(safe_div(f["desague_pozociego"].values, viv.values))
ind["pct_sin_desague"]      = calc(safe_div(f["desague_notiene"].values, viv.values))

# Energía de cocción
ind["pct_gas_red"]          = calc(safe_div(f[COL_GAS_RED].values, viv.values))
ind["pct_gas_garrafa"]      = calc(safe_div(f["combustible_gasgarrafa"].values, viv.values))
ind["pct_lena_guano"]       = calc(safe_div((f[COL_LENA]+f[COL_GUANO]).values, viv.values))

# Residuos
ind["pct_basura_formal"]    = calc(safe_div((f["basura_carrobasurero"]+f[COL_BASURA_PUB]).values, viv.values))
ind["pct_basura_quema"]     = calc(safe_div(f["basura_quema"].values, viv.values))
ind["pct_basura_informal"]  = calc(safe_div((f[COL_BASURA_CALLE]+f[COL_BASURA_RIO]).values, viv.values))

# TICs (NUEVO)
ind["pct_internet"]         = calc(safe_div(f["tics_internet"].values, viv.values))
ind["pct_celular"]          = calc(safe_div(f["tics_celular"].values, viv.values))
ind["pct_televisor"]        = calc(safe_div(f["tics_televisor"].values, viv.values))

# ── Join final ────────────────────────────────────────────────────────────────
df_val = df_val.merge(ind, on="codigo")
ind_cols = [c for c in ind.columns if c != "codigo"]
print(f"  {len(ind_cols)} indicadores calculados")

# ── Breaks nacionales (escala absoluta para coloración) ───────────────────────
# Usamos cuantiles 20/40/60/80 sobre TODA Bolivia (no por ciudad). Esto permite
# que un mismo color signifique el mismo rango de valores en cualquier municipio
# del dashboard, garantizando comparabilidad inter-ciudad. La barra del popup
# (percentil intra-ciudad) se mantiene en el frontend para conservar la lectura
# local. Para indicadores con muchos ceros (donde p20==p40==0 etc.), se usan
# percentiles más altos como sustitutos hasta tener 4 breaks únicos.
print("Calculando breaks nacionales...")

def compute_breaks(vals):
    vals = pd.to_numeric(pd.Series(vals), errors="coerce").dropna().values
    if len(vals) < 5:
        return None
    candidates = list(np.percentile(vals, [20, 40, 60, 80]))
    breaks, prev = [], -np.inf
    for c in candidates:
        if c > prev:
            breaks.append(float(c)); prev = c
    if len(breaks) < 4:
        last = breaks[-1] if breaks else float(vals.min())
        for p in [50, 70, 85, 95, 99]:
            v = float(np.percentile(vals, p))
            if v > last:
                breaks.append(v); last = v
            if len(breaks) == 4:
                break
    return [int(round(b)) for b in breaks][:4]

breaks_global = {}
for col in ind_cols:
    b = compute_breaks(df_val[col].values)
    if b and len(b) >= 2:
        breaks_global[col] = b

with open(DATA_DIR / "breaks.json", "w", encoding="utf-8") as fp:
    json.dump(breaks_global, fp, ensure_ascii=False, indent=2)
print(f"  breaks calculados para {len(breaks_global)}/{len(ind_cols)} indicadores")

# ── Simplificar geometrías ────────────────────────────────────────────────────
print("Simplificando geometrias...")
df_val["geometry"] = df_val["geometry"].simplify(SIMPLIFY, preserve_topology=True)

# ── Exportar por municipio ────────────────────────────────────────────────────
print("Exportando GeoJSON por municipio...")
ciudades = []
grupos = df_val.groupby(["departamento","municipio"])

for i, ((dep, mun), grp) in enumerate(grupos, 1):
    if len(grp) < MIN_MANZANOS:
        continue

    s = slug(f"{dep}_{mun}")

    features = []
    for _, row in grp.iterrows():
        geom = row["geometry"]
        if geom is None or geom.is_empty:
            continue
        pval = row.get("personas", 0)
        props = {
            "n": str(row["nombre"]) if pd.notna(row["nombre"]) else "",
            "p": int(pval) if pd.notna(pval) else 0,
        }
        for col in ind_cols:
            v = row[col]
            props[col] = int(v) if pd.notna(v) else None
        features.append({
            "type": "Feature",
            "geometry": json.loads(gpd.GeoSeries([geom]).to_json())["features"][0]["geometry"],
            "properties": props
        })

    if not features:
        continue

    out = DATA_DIR / f"{s}.geojson"
    with open(out, "w", encoding="utf-8") as fp:
        json.dump({"type":"FeatureCollection","features":features}, fp, separators=(",",":"), ensure_ascii=False)

    row_cob = cob[(cob["departamento"]==dep) & (cob["municipio"]==mun)]
    cobertura = float(row_cob["cobertura"].iloc[0]) if len(row_cob) else 100.0
    poblacion  = int(row_cob["poblacion_total"].iloc[0]) if len(row_cob) else 0

    ciudades.append({
        "slug": s,
        "municipio": mun,
        "departamento": dep,
        "manzanos": len(features),
        "poblacion": poblacion,
        "cobertura": cobertura,
        "size_kb": round(out.stat().st_size / 1024, 1)
    })

    if i % 50 == 0 or i == len(grupos):
        print(f"  {i}/{len(grupos)} municipios...")

ciudades.sort(key=lambda x: x["municipio"])
with open(DATA_DIR / "ciudades.json", "w", encoding="utf-8") as fp:
    json.dump(ciudades, fp, ensure_ascii=False, indent=2)

print(f"\nListo: {len(ciudades)} municipios  |  {len(ind_cols)} indicadores")
sizes = [c["size_kb"] for c in ciudades]
print(f"Archivos: min={min(sizes):.0f} KB  max={max(sizes):.0f} KB  avg={sum(sizes)/len(sizes):.0f} KB")
print(f"Total: {sum(sizes)/1024:.0f} MB")
