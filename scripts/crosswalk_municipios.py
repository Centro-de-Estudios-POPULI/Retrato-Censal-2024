# -*- coding: utf-8 -*-
"""
EMPALME MANZANO -> MUNICIPIO (`cod_ine`).
=========================================

El parquet de manzanos del INE identifica al municipio por NOMBRE
(`departamento` + `municipio`). La espina de `bo-geo-maestro` lo identifica por
`cod_ine`, y su razon de existir es que "se acaben los empalmes por nombre que
se rompen solos". Este modulo es el puente, y se escribe A MANO a proposito.

MEDIDO sobre los 340 pares (departamento, municipio) del parquet nacional:

    331 calzan 1-a-1 normalizando el nombre   (244.683 manzanas)
      9 NO calzan                             (  2.663 manzanas, 1,1%)

Los 9 estan abajo, uno por uno, con el motivo. NO se resuelven por similitud de
texto: un emparejador difuso le habria puesto a "AIOC Guarani Kereimba
Iyaambae" el municipio "Charagua Iyambae" (comparten "Iyambae") en vez de
"Gutierrez", que es el correcto. En un crosswalk un falso positivo no es ruido:
es una ciudad entera pintada con los datos de otra, y nadie lo revisa despues.

Tres motivos, y son distintos entre si:

  GAIOC   El INE rotula la unidad como AIOC/TIOC y la espina la tiene con su
          nombre de municipio. Es la MISMA unidad territorial, con `cod_ine`
          propio: la espina ya trae las cuatro GAIOC recortadas de su municipio
          madre (ver el README de bo-geo-maestro).
  ERRATA  El nombre viene mal escrito en la fuente del INE.
  FORMA   El nombre trae un prefijo o parentesis que el normalizador no saca.
"""

# (departamento, municipio_en_el_parquet) -> (cod_ine, nombre_en_la_espina, motivo)
DECLARADOS = {
    ("Oruro",      "AIOC de Salinas"):                  ("040801", "Salinas de Garci Mendoza", "GAIOC"),
    ("Santa Cruz", "AIOC Charagua Iyambae"):            ("070702", "Charagua Iyambae",         "GAIOC"),
    ("Oruro",      "AIOC Uru Chipaya"):                 ("040903", "Uru Chipaya",              "GAIOC"),
    # ⚠️ Kereimba Iyaambae es la AIOC que se constituyo sobre el municipio de
    #    Gutierrez. Comparte la palabra "Iyambae" con Charagua y NO es Charagua.
    ("Santa Cruz", "AIOC Guaraní Kereimba Iyaambae"):   ("070705", "Gutiérrez",                "GAIOC"),
    ("Potosí",     "TIOC Jatun Ayllu Yura"):            ("051204", "Jatun Ayllu Yura",         "GAIOC"),
    ("Cochabamba", "TIOC Raqaypampa"):                  ("031304", "Raqaypampa",               "GAIOC"),
    ("Chuquisaca", "TIOC Guaraní Chaqueño de Huacaya"): ("011002", "Huacaya",                  "GAIOC"),
    ("La Paz",     "La (Marka) San Andrés de Machaca"): ("020805", "San Andrés de Machaca",    "FORMA"),
    # El INE escribe "Vitiche"; el municipio es Vitichi (Nor Chichas, Potosi).
    ("Potosí",     "Vitiche"):                          ("050602", "Vitichi",                  "ERRATA"),
}
