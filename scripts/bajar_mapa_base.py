# -*- coding: utf-8 -*-
"""
BAJA Y FUSIONA EL MAPA BASE VECTORIAL — OpenFreeMap (desde el 2026-09-26).
===========================================================================

Es el MISMO script que `scz-metropolitana-gobernacion/scripts/bajar_mapa_base.py`
(el tablero de la Gobernación salió de éste); sólo cambia la tinta de los
rótulos, que acá es la de la identidad OFPDT. Hasta hoy el Retrato no tenía el
script: el `mapa_base.json` de CARTO había llegado horneado.

⛔⛔ POR QUÉ YA NO ES CARTO — dos veces en un mes el sitio publicado apareció con
   «API KEY REQUIRED» estampado sobre el mapa:
   · 2026-08-26: CARTO empezó a exigir clave para sus mapas base ráster
     (`light_all`, `dark_all`, `*_nolabels`). Se pasó a sus estilos vectoriales
     GL + la capa ráster de SÓLO RÓTULOS, que seguía libre.
   · 2026-09-26: la capa de sólo rótulos (`light_only_labels`,
     `dark_only_labels`) también pasó a exigir clave. Responde 200 con la
     tesela marcada: el tablero «funciona» y se ve roto, y ningún monitor lo ve.
   ⇒ Se deja CARTO entero. **OpenFreeMap** (https://openfreemap.org) sirve
     teselas vectoriales de OpenStreetMap sin clave, sin registro y sin cuota
     —es su razón de ser—, con estilo claro (`positron`) y oscuro (`dark`) que
     comparten fuente, fuentes tipográficas y sprite.

★ LOS RÓTULOS SON VECTORIALES Y VAN ARRIBA DE LOS DATOS. Antes eran una imagen
  debajo de la coropleta, lavada por su transparencia. Ahora son capas `symbol`
  que el tablero sube por encima de municipios y manzanas (`rotulos` en el
  paquete): se leen nítidos a cualquier zoom.
  · En CASTELLANO: los estilos originales rotulan `name_en` cuando existe; acá
    se reescribe a `name:es` con el nombre local de respaldo.
  · Fuera lo que no sirve en Santa Cruz: escudos de autopistas de EE. UU. y las
    flechas de sentido único.

★ POR QUÉ SE HORNEA EN LA PLANTILLA EN VEZ DE PEDIRLO EN CALIENTE
  El mapa se construye de forma SÍNCRONA dentro de un `try` y todo lo que sigue
  depende de que `map` exista. Horneado: sin ida y vuelta extra, sin una falla
  nueva posible, y el estilo queda fijado y versionado.

★ POR QUÉ LOS DOS ESTILOS Y NO UNO
  El tablero alterna tema **sin `setStyle()`**: las dos bases viven en el mismo
  estilo y se conmuta su visibilidad, porque reemplazar el estilo entero se
  lleva puestas las capas de municipios y manzanas. Van con prefijo (`bc_`,
  `bo_`) para que no choquen, y comparten la MISMA fuente vectorial.

    python scripts/bajar_mapa_base.py
    python scripts/generar_sitios.py
"""
import json
import pathlib
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "plantilla" / "mapa_base.json"

ESTILOS = {
    "claro":  {"url": "https://tiles.openfreemap.org/styles/positron", "prefijo": "bc_"},
    "oscuro": {"url": "https://tiles.openfreemap.org/styles/dark",     "prefijo": "bo_"},
}
ATRIB = ('<a href="https://openfreemap.org" target="_blank">OpenFreeMap</a> '
         '© <a href="https://www.openmaptiles.org/" target="_blank">OpenMapTiles</a> · '
         'datos © <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>')

# capas que en Santa Cruz no dicen nada o ensucian sobre la coropleta
FUERA = ("shield", "oneway", "road_shield")
# la tinta del Retrato (identidad OFPDT: `--tx` de `docs/estilo-atlas.css`)
ROTULO = {
    "claro":  {"text-color": "#16232c", "text-halo-color": "#ffffff",
               "text-halo-width": 1.4, "text-halo-blur": .4},
    "oscuro": {"text-color": "#e9eff2", "text-halo-color": "#0f1a20",
               "text-halo-width": 1.5, "text-halo-blur": .4},
}
# el nombre en castellano, con el local de respaldo (OpenMapTiles trae `name:es`)
NOMBRE_ES = ["coalesce", ["get", "name:es"], ["get", "name:latin"], ["get", "name"]]


def bajar(url):
    pedido = urllib.request.Request(url, headers={"User-Agent": "scz-metropoli/1.0"})
    with urllib.request.urlopen(pedido, timeout=45) as r:
        return json.loads(r.read().decode("utf-8"))


def castellano(expr):
    """Reemplaza, dentro de un `text-field`, la elección de nombre del estilo
    (que prefiere `name_en`) por `NOMBRE_ES`. Si la expresión no habla de
    nombres (un `ref` de ruta, por ejemplo) se deja como está."""
    if "name" not in json.dumps(expr):
        return expr
    return NOMBRE_ES


fuentes, capas, rotulos, glyphs, sprite = {}, {}, {}, None, None
for tema, cfg in ESTILOS.items():
    st = bajar(cfg["url"])
    glyphs = glyphs or st.get("glyphs")
    sprite = sprite or st.get("sprite")
    for sid, sdef in st["sources"].items():
        if sid not in fuentes:
            sdef = dict(sdef)
            sdef["attribution"] = ATRIB
            fuentes[sid] = sdef
    propias, rot = [], []
    for capa in st["layers"]:
        c = dict(capa)
        if c.get("type") == "background":
            continue            # el fondo lo pone el tablero, que lo repinta al cambiar de tema
        if any(x in c["id"] for x in FUERA):
            continue
        if "fill-pattern" in json.dumps(c.get("paint") or {}):
            continue            # pide un ícono («wood-pattern») que el sprite de OFM no trae

        c["id"] = cfg["prefijo"] + c["id"]
        lay = dict(c.get("layout") or {})
        lay["visibility"] = "visible" if tema == "claro" else "none"
        if c.get("type") == "symbol" and "text-field" in lay:
            lay["text-field"] = castellano(lay["text-field"])
            # ★ TINTA Y HALO PROPIOS: el oscuro de OFM rotula en gris sobre gris,
            #   y encima de la coropleta verde el texto desaparecía. Tinta de la
            #   marca con un halo del fondo: se lee sobre cualquier tono de la rampa.
            pa = dict(c.get("paint") or {})
            pa.update(ROTULO[tema])
            c["paint"] = pa
        c["layout"] = lay
        c.pop("metadata", None)
        propias.append(c)
        if c.get("type") == "symbol":
            rot.append(c["id"])
    capas[tema], rotulos[tema] = propias, rot
    print(f"{tema:7} · {len(propias):>3} capas ({len(rot)} de rótulos) · {cfg['url']}")

paquete = {
    "glyphs": glyphs,
    "sprite": sprite,
    "sources": fuentes,
    "capas": capas,          # separadas por tema: el tablero las conmuta
    "rotulos": rotulos,      # las `symbol`: el tablero las sube encima de los datos
    "atribucion": ATRIB,
    "origen": {t: c["url"] for t, c in ESTILOS.items()},
}
SALIDA.write_text(json.dumps(paquete, ensure_ascii=False, separators=(",", ":")),
                  encoding="utf-8")
print(f"\n✔ {SALIDA.relative_to(RAIZ)} · {SALIDA.stat().st_size/1024:.0f} KB "
      f"· {len(fuentes)} fuentes · {sum(len(v) for v in capas.values())} capas")
print("  ahora: python scripts/generar_sitios.py")
