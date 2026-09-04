# Retrato Censal de Bolivia

El Censo 2024 **del municipio a la manzana**, en dos tableros que hablan el mismo
vocabulario. Producto del **Observatorio de Finanzas Públicas y Desarrollo Territorial
(OFPDT)**.

- **`docs/municipal/`** — 213 indicadores para los 343 municipios, con la lectura de 2012
  en 178 de ellos.
- **`docs/manzana/`** — los 91 que existen en los dos niveles con la misma definición: el
  mapa arranca en el municipio y al acercarse se abre en las 247.429 manzanas censadas.

> **Reemplaza al Retrato Censal anterior.** Aquél mostraba 43 indicadores con vocabulario
> propio (`pct_menor20`, `pct_educ_superior`), un GeoJSON por municipio y sin zoom desde el
> nivel municipal. Éste usa los nombres canónicos del motor censal, así que el mismo
> indicador es el mismo objeto acá, en el Atlas Socioeconómico y en el Banco de Gráficos.

---

## Lo que hay que entender antes de tocar nada

**El nivel manzana NO sale del microdato.** El microdato del INE llega hasta municipio y no
trae identificador de manzano: es anonimización, no una limitación nuestra. Las fichas por
manzana vienen ya agregadas del geoportal, vía `mauforonda/atlasurbano`.

⇒ Entonces el trabajo no es un *join*, es una **traducción con control**:
`motor_manzana.py` reescribe las fichas en los nombres canónicos del motor municipal, y
`comparar_niveles.py` verifica cada indicador agregando sus manzanas por municipio y
contrastándolas contra la **cifra urbana del microdato** — dos fuentes independientes del
mismo censo.

**No se espera identidad**: «área urbana censada» y `urbrur = urbana` no son el mismo
polígono. Lo que delata una definición distinta no es el tamaño del desvío sino que sea
**sistemático** (`|sesgo| / error` cerca de 1: todas las diferencias del mismo lado).

Resultado del contraste, nacional, sobre 185 municipios con cifra urbana:

| | |
|---|---|
| indicadores contrastados | 79 |
| por debajo de 5 pp | 66 |
| **verificados** (entran al Tablero 2) | **74** |
| con aviso (borde urbano, no sistemático) | 8 |
| **excluidos** por definición distinta | 5 |
| sólo manzana (sin cifra comparable) | `densidad` |

Los 5 excluidos: `viviendas`, `pct_salud_publica`, `pct_salud_tradicional`,
`pct_salud_privada`, `pct_migrante_reciente`. El bloque de salud da sesgo 1,00 porque el
municipal divide por TODA la población y admite respuesta múltiple (sus categorías suman
128%) mientras la manzana divide por la suma de las categorías (suman 100%).

**Hasta dónde llega el nivel manzana:** 131.801 manzanas con ficha de 247.429 (53,3%). El
INE suprime las chicas por privacidad, así que la mitad de las manzanas no tiene ficha —
pero las que la tienen concentran el **89,5%** de la gente que vive en manzano. Población y
viviendas SÍ existen para las 247.429, así que las suprimidas se pintan con su población y
no con el gris de «sin dato».

---

## El orden del pipeline

Cada paso depende del anterior. Los cuatro primeros son de datos; los dos últimos, del sitio.

```
1. catalogo/armar_municipios.py     → datos/municipios.json · datos/cobertura.json
                                      datos/manzano_municipio.parquet
2. catalogo/motor_manzana.py        → catalogo/manzana_2024.csv (247.429 × 96)
                                      catalogo/manzana_agregado_municipal.csv
3. catalogo/comparar_niveles.py     → catalogo/comparables.json   (la puerta)
4. catalogo/armar_tableros.py       → docs/datos/catalogo_*.json · municipios_*.json
5. scripts/preparar_web.py          → docs/datos/municipios.geojson · region.geojson · mini.json
   scripts/estadisticas_manzana.py  → docs/datos/mz_stats.json
   scripts/generar_pmtiles.py       → docs/datos/manzanas.pmtiles      (~9 min)
6. scripts/generar_sitios.py        → docs/municipal/ · docs/manzana/
   scripts/armar_portada.py         → docs/index.html
```

### Contratos entre pasos

| archivo | qué es | quién lo escribe |
|---|---|---|
| `datos/municipios.json` | los 343 con `sigep`, `cod_ine`, `dpto` y su contexto de manzanas | paso 1 |
| `datos/manzano_municipio.parquet` | **el puente manzano→municipio**, la única copia | paso 1 |
| `datos/cobertura.json` | las cifras de cobertura que el tablero muestra al pie | paso 1 |
| `catalogo/comparables.json` | `verificados` · `con_aviso` · `excluidos` · `solo_manzana` | paso 3 |
| `docs/datos/catalogo_*.json` | grupos, indicadores, dominio de color y el agregado país | paso 4 |
| `docs/datos/manzanas.pmtiles` | geometría + los 91 indicadores como atributos | paso 5 |

---

## Las trampas, medidas

- **⚠️ El puente manzano→municipio es por NOMBRE**, porque el geoportal no publica el código
  INE. A escala nacional eso dejaba **2.287 manzanos (0,92%) sin municipio**: cinco
  autonomías indígenas rotuladas por el nombre de su autonomía («AIOC de Salinas» por
  Salinas de Garci Mendoza) y un tipeo del geoportal («Vitiche» por Vitichi). Están
  declaradas una por una en `armar_municipios.py`; **no se resuelven por parecido de texto**,
  porque un emparejamiento difuso que acierta cinco veces puede errar la sexta sin que nada
  avise, y errar acá significa mandarle las manzanas de un municipio a otro.
- **⚠️ La clave del municipio en las teselas es `sigep`, no el slug del nombre.** Con nueve
  municipios el nombre alcanzaba; con 343 hay **nueve nombres repetidos** en departamentos
  distintos (San Pedro y Santa Rosa existen tres veces cada uno).
- **⚠️ El motor y el catálogo no hablan igual**: el motor emite `pct_rama_comercio` y el
  catálogo declara `pct_comercio`. Todo lo que lea `manzana_2024.csv` tiene que pasar por
  `renombrar()` de `alias.py`, o **nueve de los 91 indicadores viajan vacíos** y el mapa se
  ve bien, en gris, como si el INE no los publicara.
- **⚠️ Reparar la geometría no es prolijidad.** Las fichas del geoportal traen polígonos
  inválidos; GEOS no falla al leerlos, falla en la primera intersección contra una tesela y
  se lleva puesta la corrida entera.
- **⚠️ El techo de zoom de las teselas es z13, no z14.** Con z14 el archivo pesó 139,9 MB y
  **GitHub rechaza archivos de más de 100 MB**. Por encima de z13 MapLibre sobre-escala la
  última tesela: se sigue viendo la manzana. El peso de ese archivo son los ATRIBUTOS
  repetidos en cada nivel de zoom, no los polígonos.
- **⚠️ El teselado va por bloques** y eso es lo que lo hace correr en esta máquina, no una
  optimización: cargar las 247.429 geometrías y su índice espacial a la vez pide más memoria
  de la que hay libre.

## Verificación

- Chrome headless sirve para verificar: los rellenos vectoriales de MapLibre **sí** renderizan.
  Lo que no se puede verificar así es la **fluidez** ni las capas `circle`/`symbol`.
- `--window-size` **no** fija el viewport (Windows impone ~500 px de ancho mínimo): para
  probar móvil, un iframe de ancho CSS explícito.

## Fuentes

INE · Censo de Población y Vivienda 2024 — microdato (nivel municipal) y fichas por manzano
del geoportal, vía `mauforonda/atlasurbano` (nivel manzana). La lista de los 343 municipios
y el crosswalk INE↔SIGEP salen de `bo-geo-maestro`, la georreferencia madre del ecosistema.
