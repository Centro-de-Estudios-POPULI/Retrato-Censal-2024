# -*- coding: utf-8 -*-
"""
LA PALETA, DECLARADA UNA SOLA VEZ.
===================================

★ EL PROBLEMA QUE ESTO RESUELVE (2026-08-20). La rampa estaba escrita a mano en
  cuatro archivos —`plantilla/tablero.html`, `sistema-graficos/motor/estilo.py`,
  `scripts/portal/plantilla_portal.html` y `sistema-graficos/motor/plantilla_sitio.html`—
  y `estilo.py` lo decía sin vueltas: «SI CAMBIA EL TABLERO, CAMBIA ESTO. Son dos
  implementaciones del mismo criterio; no hay forma de que una se entere sola de
  la otra». No se enteró: el tablero y el banco terminaron pintando el MISMO dato
  con tres diferencias (la bisagra, los neutros y la saturación).

  Acá la rampa se declara UNA vez. `assets/paleta.json` es el contrato, este
  módulo lo deriva y lo escribe, y los consumidores lo leen:

      assets/paleta.json  ──┬── plantilla/tablero.html   (literal inyectado acá)
                            └── sistema-graficos/motor/estilo.py  (lo lee al importar)

  `python scripts/paleta.py` recalcula y sincroniza.
  `python scripts/paleta.py --verificar` falla si alguien se desvió. Es lo que
  hay que correr antes de publicar.

★ QUÉ ES DECLARADO Y QUÉ ES DERIVADO. `declarada` es la rampa tal como la entregó
  la Gobernación: no se toca, es identidad. `ajustes` son las tres decisiones que
  tomamos sobre ella, cada una con su motivo. `pinta` es el resultado —lo único
  que consume el código— y se recalcula siempre desde las dos de arriba, nunca
  se edita a mano.
"""
import colorsys
import json
import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
ARCHIVO = RAIZ / "assets" / "paleta.json"
TABLERO = RAIZ / "plantilla" / "tablero.html"

# marcadores dentro del tablero; lo que queda entre ellos lo escribe este script
ABRE = "/* ⇩⇩ PALETA GENERADA — no editar a mano: sale de assets/paleta.json ⇩⇩ */"
CIERRA = "/* ⇧⇧ FIN DE LA PALETA GENERADA ⇧⇧ */"


# ── el contrato, si todavía no existe ────────────────────────────────────────
DEFECTO = {
    "_": "Fuente única de la paleta. Ver scripts/paleta.py. `pinta` es DERIVADO.",
    "declarada": {
        "_": "Rampa entregada por el Gobierno Autónomo Departamental de Santa Cruz.",
        "divergente": ["#00733b", "#419a3a", "#8bc53f", "#eeebe1",
                       "#dea015", "#d8690c", "#a8381e"],
        "sin_dato": "#8a8f96",
        "senal": "#8bc53f",
        "institucional": "#00733b",
    },
    "ajustes": {
        "bisagra": {
            "valor": "#f4ecc9",
            "por_que": (
                "La parada del medio declarada (#eeebe1) es EXACTAMENTE el fondo "
                "del tablero (--fondo en identidad-gobernacion.css), así que todo "
                "lo que cae en el pivote se pintaba del color del papel y "
                "desaparecía. Medido sobre el tablero municipal: 465 de 1.917 "
                "celdas municipio×indicador (24,3%) caen en esa parada, los nueve "
                "municipios pasan por ahí en algún indicador, y en «Jóvenes "
                "(15-29)» son 7 de 9 a la vez. Pasa a una paja pálida: clara, para "
                "que el centro siga quieto, pero inconfundible contra el crema. "
                "Es el mismo recurso del RdYlGn clásico. Sólo afectaba al tema "
                "claro: en oscuro esa parada se realza y se ve bien."),
        },
        "suave_factor": {
            "valor": 0.80,
            "por_que": (
                "Pedido de Carlos (2026-08-19): «bajale un poco a los colores, se "
                "ve medio chillón». Baja la SATURACIÓN un 20% y deja la "
                "luminosidad quieta, así que el orden de la rampa no se mueve — "
                "sólo deja de gritar. Vivía sólo en el banco; desde 2026-08-20 "
                "vale también para los tableros, que es lo que hace que la lámina "
                "y la pantalla muestren el mismo color para el mismo valor."),
        },
        "realce_oscuro": {
            "valor": 0.26,
            "por_que": (
                "En tema oscuro NO se cambia de rampa: se usan los mismos tonos, "
                "más brillantes. El realce es proporcional a lo que le falta a "
                "cada tono para llegar al blanco (l + (1-l)·k), no una suma fija: "
                "los oscuros —que sobre fondo oscuro se cierran— suben mucho y los "
                "que ya eran claros casi no se mueven. El tono no se toca, que es "
                "lo que hace que se reconozca la misma paleta."),
        },
        "sin_secuencial": {
            "valor": True,
            "por_que": (
                "Decisión de Carlos (2026-08-20). Entre el 19 y el 20 el banco "
                "pintó los indicadores neutros (dir == 0) con una rampa secuencial "
                "de un solo tono, para no afirmar un lado bueno donde el dato no "
                "lo trae. Se bajó: la divergente vale para TODO, en el tablero y "
                "en la lámina. Costó regenerar 184 de las 375 láminas. Si algún "
                "día se retoma, el argumento está acá: en `pob_total` la "
                "divergente pinta a Santa Cruz de la Sierra de rojo por ser la más "
                "poblada y a Colpa Bélgica de verde por ser la más chica."),
        },
    },
}


def _hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _rgb_hex(t):
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02x}" for c in t)


def _suavizar(h, f):
    """Baja la saturación y deja la luminosidad quieta."""
    y, l, s = colorsys.rgb_to_hls(*_hex_rgb(h))
    return _rgb_hex(colorsys.hls_to_rgb(y, l, s * f))


def _brillar(h, k):
    """Acerca el tono al blanco en proporción a lo que le falta, sin cambiar de
    tono. La saturación sube apenas para que el aclarado no lo lave.

    ⚠️ Con `k == 0` devuelve el color INTACTO. La compensación de saturación
    existe para que el aclarado no lave el tono; sin aclarado no hay nada que
    compensar, y aplicarla igual movía la rampa oscura uno o dos puntos por
    canal respecto de la clara. Imperceptible, pero deja de ser cierto que «es
    la misma rampa», que es justamente lo que se decidió el 2026-08-26."""
    if not k:
        return h
    y, l, s = colorsys.rgb_to_hls(*_hex_rgb(h))
    return _rgb_hex(colorsys.hls_to_rgb(y, l + (1 - l) * k, min(1.0, s * 1.06)))


def derivar(p):
    """`pinta` desde `declarada` + `ajustes`. Es la única cuenta del sistema."""
    d = p["declarada"]
    a = p["ajustes"]
    f = a["suave_factor"]["valor"]
    k = a["realce_oscuro"]["valor"]

    # 1 · la bisagra reemplaza la parada del medio
    base = list(d["divergente"])
    base[len(base) // 2] = a["bisagra"]["valor"]
    # 2 · el tema claro baja la saturación; 3 · el oscuro además se realza
    claro = [_suavizar(c, f) for c in base]
    oscuro = [_suavizar(_brillar(c, k), f) for c in base]
    return {
        "_": "DERIVADO por scripts/paleta.py — no editar a mano.",
        "divergente": claro,
        "divergente_oscuro": oscuro,
        # ★ EL GRIS TAMBIÉN SE SUAVIZA, y la regla no tiene excepción. Se probó
        #   dejarlo crudo —es un aviso de ausencia, no un dato— y la diferencia
        #   es de UN punto por canal (#8b8f95 vs #8a8f96): invisible, pero
        #   habría obligado a regenerar las 90 láminas de manzana que ya están
        #   publicadas, porque todas dibujan en gris las 13.194 manzanas que el
        #   INE suprime. Cien megas de historial por algo que nadie ve. La regla
        #   simple —se suaviza todo lo que PINTA— sale más barata y deja el
        #   banco sin estados mezclados.
        "sin_dato": _suavizar(d["sin_dato"], f),
        "senal": d["senal"],                 # identidad, nunca dato
        "institucional": d["institucional"],  # identidad, nunca dato
    }


def cargar():
    """La paleta completa, con `pinta` siempre recalculado."""
    p = json.loads(ARCHIVO.read_text(encoding="utf-8")) if ARCHIVO.exists() else DEFECTO
    p["pinta"] = derivar(p)
    return p


def _bloque_js(p):
    """El literal que va dentro del tablero, entre los marcadores."""
    q = p["pinta"]
    arr = lambda xs: "[" + ",".join(f'"{c}"' for c in xs) + "]"
    return (
        f"{ABRE}\n"
        f"const DIV_CLARA  = {arr(q['divergente'])};\n"
        f"const DIV_OSCURO = {arr(q['divergente_oscuro'])};\n"
        f'const SIN_DATO = {{claro:"{q["sin_dato"]}", oscuro:"{q["sin_dato"]}"}};\n'
        f'const SENAL = "{q["senal"]}";\n'
        f"{CIERRA}"
    )


def sincronizar(escribir=True):
    """Escribe el JSON y mete el literal en el tablero. Devuelve si hubo cambios."""
    p = cargar()
    cambios = []

    nuevo = json.dumps(p, ensure_ascii=False, indent=2) + "\n"
    if not ARCHIVO.exists() or ARCHIVO.read_text(encoding="utf-8") != nuevo:
        cambios.append(str(ARCHIVO.relative_to(RAIZ)))
        if escribir:
            ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
            ARCHIVO.write_text(nuevo, encoding="utf-8")

    html = TABLERO.read_text(encoding="utf-8")
    bloque = _bloque_js(p)
    patron = re.compile(re.escape(ABRE) + r".*?" + re.escape(CIERRA), re.S)
    if patron.search(html):
        salida = patron.sub(lambda _: bloque, html)
    else:
        raise SystemExit(
            f"No encontré los marcadores en {TABLERO}.\n"
            f"Tiene que existir un bloque entre:\n  {ABRE}\n  {CIERRA}")
    if salida != html:
        cambios.append(str(TABLERO.relative_to(RAIZ)))
        if escribir:
            TABLERO.write_text(salida, encoding="utf-8")
    return p, cambios


if __name__ == "__main__":
    verificar = "--verificar" in sys.argv
    p, cambios = sincronizar(escribir=not verificar)
    q = p["pinta"]
    if verificar:
        if cambios:
            print("FALLA: la paleta se desvio de assets/paleta.json:")
            for c in cambios:
                print("   ·", c)
            print("  Corre: python scripts/paleta.py")
            sys.exit(1)
        print("OK: paleta sincronizada")
    else:
        print("rampa clara :", " ".join(q["divergente"]))
        print("rampa oscura:", " ".join(q["divergente_oscuro"]))
        print("sin dato    :", q["sin_dato"])
        print("actualizado :", ", ".join(cambios) if cambios else "nada que cambiar")
