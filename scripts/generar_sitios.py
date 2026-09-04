# -*- coding: utf-8 -*-
"""
GENERA EL TABLERO DESDE LA PLANTILLA.
======================================

★ ES UNO SOLO, Y ESO ES UNA CORRECCIÓN (2026-09-04). El port arrancó copiando la
  pareja de tableros del proyecto metropolitano —municipal + manzana— porque allá
  son dos. Allá tiene sentido: la región no tiene un tablero municipal propio, así
  que el nivel municipio no vivía en ningún lado.

  A escala nacional SÍ vive: es el **Atlas Socioeconómico Municipal**, publicado,
  con 215 indicadores y serie 2012. Medido indicador por indicador, 209 de los 213
  del tablero municipal que se había generado ya estaban ahí —204 con la misma
  clave y cinco con otro nombre para lo mismo—. Era un segundo tablero para el
  mismo dato con otro motor.

  ⇒ Se publica sólo lo que no existe en ninguna otra parte: **el zoom
    municipio ↔ manzana**. El reparto queda: el Atlas da la profundidad
    MUNICIPAL (215 indicadores, 2012), el Retrato da la profundidad
    TERRITORIAL (91 indicadores, hasta la manzana). El pie del tablero enlaza al
    Atlas para que los 91 no se lean como una falta.

  Lo que el motor sigue calculando para el nivel municipal queda en `datos/`, sin
  publicar: es el insumo del que sale el nivel de arriba del propio tablero y el
  contraste que verifica los 91. Sólo no se sirve como sitio.

El tablero vive en la RAÍZ (`docs/index.html`), como el Atlas y como el Retrato
anterior: quien entra al sitio ve el mapa, no una portada que lo haga hacer un
clic más.

⚠️ Es un DERIVADO: no editar `docs/index.html` a mano. Se toca
   `plantilla/tablero.html` y se vuelve a correr esto.

    python scripts/generar_sitios.py
"""
import pathlib, re, sys

sys.stdout.reconfigure(encoding="utf-8")

RAIZ = pathlib.Path(__file__).resolve().parent.parent
FUENTE = RAIZ / "plantilla" / "tablero.html"
SALIDA = RAIZ / "docs" / "index.html"

TITULO = "Retrato Censal de Bolivia — del municipio a la manzana"
CABECERA = '<b>Bolivia:</b> Retrato Censal'
CHIP = "<b>247.429 manzanas</b> en 341 municipios"


def derivar(html):
    # ── el par de archivos que carga ─────────────────────────────────────────
    # La plantilla apunta al catálogo municipal porque es el que tiene todo; acá
    # se la manda al de manzana, que es el que se publica.
    html = html.replace('"datos/catalogo_municipal.json"', '"datos/catalogo_manzana.json"')
    html = html.replace('"datos/municipios_municipal.json"', '"datos/municipios_manzana.json"')
    # ── rutas: el tablero vive en la raíz, así que no hay nivel que subir ─────
    html = html.replace('href="../favicon.svg"', 'href="favicon.svg"')
    # ── título, cabecera y la pastilla que dice de cuántas cosas habla ───────
    html = re.sub(r"<title>.*?</title>", f"<title>{TITULO}</title>", html, count=1)
    html = re.sub(r'(<div class="t-h">).*?(</div>)',
                  lambda m: m.group(1) + CABECERA + m.group(2), html, count=1)
    html = re.sub(r'(<div class="t-s" id="t-s">).*?(</div>)',
                  lambda m: m.group(1) + CHIP + m.group(2), html, count=1)
    return html


def main():
    if not FUENTE.exists():
        sys.exit(f"no encuentro {FUENTE}")
    # ★ LA PALETA, ANTES QUE NADA. La rampa se declara en `assets/paleta.json` y
    #   se inyecta en la plantilla ANTES de derivar, así no se puede publicar una
    #   versión desincronizada ni por descuido.
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
    import paleta
    _, cambios = paleta.sincronizar()
    if cambios:
        print("  paleta resincronizada:", ", ".join(cambios))
    base = FUENTE.read_text(encoding="utf-8")
    # ★ EL MAPA BASE, HORNEADO. CARTO empezó a exigir clave para sus bases
    #   ráster y el sitio metropolitano apareció con «API KEY REQUIRED» encima de
    #   los mapas. La base es vectorial y viene fijada en `plantilla/mapa_base.json`.
    mapa_base = RAIZ / "plantilla" / "mapa_base.json"
    if not mapa_base.exists():
        sys.exit(f"falta {mapa_base}")
    if "__MAPA_BASE__" not in base:
        sys.exit("la plantilla no tiene el marcador __MAPA_BASE__")
    estilo = mapa_base.read_text(encoding="utf-8").replace("</script", "<\\/script")
    base = base.replace("__MAPA_BASE__", estilo)
    print(f"  mapa base horneado: {len(estilo)/1024:.0f} KB")
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(derivar(base), encoding="utf-8")
    print(f"  -> docs/index.html   {SALIDA.stat().st_size/1024:.0f} KB · catalogo_manzana.json")


if __name__ == "__main__":
    main()
