# -*- coding: utf-8 -*-
"""
ARMA LOS DOS TABLEROS NACIONALES DESDE EL MOTOR VALIDADO.
===========================================================

Port del armador metropolitano a los 343 municipios (Retrato Censal). Cambia el
alcance, no el método: los mismos motores, el mismo catálogo y la misma puerta
de comparación entre niveles.

★ QUÉ CAMBIA RESPECTO DE LA VERSIÓN METROPOLITANA, y por qué:
  · `region` pasa a ser el PAÍS — los 343 ponderados por el universo de cada
    indicador. La clave del JSON se conserva (`region`) porque es la que lee el
    tablero; lo que cambia es qué agrega, no cómo.
  · SIN BLOQUE FISCAL. Los 30 fiscales son de la región metropolitana y salen de
    la ejecución del MEFP por gestión; a nivel nacional eso ya vive en el Atlas
    Fiscal Municipal, que es otro producto. Meterlos acá duplicaría la fuente.

Decisión de producto de Carlos: son DOS sitios, no uno.

  · **Tablero A — municipal**: todo lo que el motor calcula a nivel municipio
    para los 343.
  · **Tablero B — municipio ↔ manzana**: SÓLO los que existen en los dos niveles
    con la MISMA definición y que además REPRODUCEN la cifra urbana del
    microdato, para que el toggle conserve el indicador en vez de cambiar de
    objeto en silencio.

★ POR QUÉ DOS. El nivel manzana no tiene serie temporal, no tiene flujos y es
  sólo urbano. Un tablero único tendría que apagar medio panel al bajar de nivel.

★ DE DÓNDE SALE CADA COSA. La web venía leyendo el pipeline VIEJO
  (`derivar_indicadores.py` + `fusionar_catalogos.py`): 193 indicadores anteriores
  a toda la validación, con el denominador equivocado. Acá se lee lo que producen
  los motores validados contra el tabulado del INE.

★ SE EMITE EN LA FORMA QUE LA WEB YA CONSUME (`catalogo_tablero.json` +
  `municipios.json`), a propósito: así los dos sitios son el MISMO motor de
  interfaz —que ya funciona— con distinto par de archivos, en vez de una
  reescritura.

⚠️ EL AGREGADO REGIONAL SE PONDERA POR EL UNIVERSO DE CADA INDICADOR, no por
   población. Es el mismo error que tuvo el Atlas nacional: un porcentaje de
   VIVIENDAS ponderado por PERSONAS le da más peso a los municipios con hogares
   grandes. Cada motor emite su denominador en `_den_<indicador>`.

    python armar_tableros.py
"""
import json, pathlib, csv
import pandas as pd, numpy as np
from alias import renombrar, ALIAS
from generar_atlas import SIN_2012

import sys as _sys
_sys.stdout.reconfigure(encoding="utf-8")  # la consola de Windows es cp1252 y revienta con los avisos

AQUI = pathlib.Path(__file__).parent
RAIZ = AQUI.parent
SALIDA = RAIZ / "docs" / "datos"
# ★ EL NIVEL MUNICIPAL NO SE PUBLICA COMO SITIO (2026-09-04). Se sigue armando
#   —es el nivel de arriba del propio tablero de manzana y el contraste que
#   verifica los 91— pero sus dos archivos van a `datos/`, fuera de lo que se
#   sirve: el tablero municipal nacional ya existe y es el Atlas Socioeconómico
#   Municipal (215 indicadores, con serie 2012). Medido: 209 de los 213 que
#   emitía este paso ya estaban ahí. Publicarlos era un segundo tablero para el
#   mismo dato, con otro motor y con cuatro indicadores de diferencia.
SALIDA_MUN = RAIZ / "datos"
SPINE = pathlib.Path(r"C:\Users\HP\OneDrive\Desktop\Proyectos\bo-geo-maestro\spine\municipios.csv")

POR_BLOQUE = {"municipal": "n_viviendas", "municipal_urbano": "n_viviendas",
              "personas": "poblacion", "personas_urbano": "poblacion",
              "nbi": "poblacion_nbi", "flujos_municipal": "trabajan_en_su_municipio"}
# ⚠️ `geo` (superficie y densidad municipal) va al final a propósito: es la
#    única fuente que NO sale del censo sino del mapa maestro. Sin ella la
#    densidad se calculaba y no llegaba a ningún tablero.
FUENTES24 = ["municipal", "personas", "nbi", "otros", "flujos_municipal", "geo"]
FUENTES12 = ["municipal", "personas", "nbi", "otros"]
FUENTES_URB = ["municipal_urbano", "personas_urbano"]

# ★ LA DEL NIVEL MANZANA NO SE ESCRIBE ACÁ: la MIDE `armar_municipios.py` sobre
#   los parquets del geoportal y viaja en `datos/cobertura.json`. Las dos cifras
#   dicen cosas distintas y las dos hacen falta —la mitad de las manzanas no
#   tiene ficha, pero las que la tienen son donde vive casi toda la gente: lo que
#   el INE suprime por privacidad son manzanas chicas—, y si mañana el geoportal
#   publica otra extracción, la frase tiene que moverse sola.
COBERTURA = {
 "municipio": "todo el territorio municipal, urbano y rural",
}


def cobertura_manzana(c):
    mil = lambda n: f"{int(n):,}".replace(",", ".")
    dec = lambda x: f"{x:.1f}".replace(".", ",")
    return (f"área urbana censada; {mil(c['con_ficha'])} manzanas con ficha de "
            f"{mil(c['manzanas'])} ({dec(c['pct_manzanas'])}%), que concentran el "
            f"{dec(c['pct_personas'])}% de la población que vive en manzano")

# ★ LA TARJETA TIENE QUE DECIR QUÉ MUESTRA EL MAPA (pedido de Carlos).
#   ⚠️ NO sirve el campo `nota` del catálogo: son anotaciones INTERNAS de método
#      ("El INE lo publica sobre POBLACIÓN, no sobre viviendas: validar contra esa
#      hoja"). Usarlas como descripción le muestra al lector nuestra cocina.
#   La descripción se compone del universo declarado, que es el dato que de
#   verdad hace falta para leer el número: un 40% no significa lo mismo sobre
#   viviendas que sobre personas.
UNIVERSO = {
 "viv_ocu": "las viviendas particulares ocupadas",
 "viv_part": "todas las viviendas particulares",
 "hogares": "los hogares",
 "personas": "la población",
 "ocupados": "la población ocupada",
 "pet15": "la población en edad de trabajar (15 años o más)",
 "p19mas": "la población de 19 años o más",
 "p18mas": "la población de 18 años o más",
 "p15mas": "la población de 15 años o más",
 "p6_17": "la población de 6 a 17 años",
 "p4_5": "la población de 4 y 5 años",
 "muj12": "las mujeres de 12 años o más",
 "mef": "las mujeres en edad fértil (15 a 49 años)",
}

# ★ QUÉ ES UN CONTEO — DECLARADO, NO DEDUCIDO DE LA UNIDAD.
#   La interfaz lo necesita en dos lugares: el PIVOTE de la escala (el promedio
#   ponderado de un conteo no significa nada legible —da Σp²/Σp, el tamaño del
#   municipio de la persona promedio— así que un conteo se centra en su mediana)
#   y la UNIDAD DEL CAMBIO intercensal (un conteo cambia en PORCENTAJE, un
#   porcentaje cambia en PUNTOS PORCENTUALES).
#   ⚠️ Venía deducido de la unidad: `unidad === "hab" || unidad === "viv"` en el
#      JS. Hoy acierta de casualidad —las 4 razones de unidad `pers`
#      (tam_hogar, pers_x_vivienda…) no son conteos y quedan afuera solas— pero
#      es exactamente el error que publicó "Personas por hogar: 1.049,2" en la
#      pantalla de entrada del Atlas nacional y "Viviendas: país 62.550" en su
#      leyenda. Cuatro veces el mismo error de fondo. Acá se declara.
CONTEOS = {"pob_total", "pob_hombres", "pob_mujeres", "viviendas",
           "poblacion_flotante", "saldo_migratorio"}

# ★ POR QUÉ FALTA CADA UNO — DECLARADO, y con la MISMA redacción que el Atlas
#   nacional. Es el mismo censo y la misma ausencia: dos textos distintos para el
#   mismo hecho se leen como dos hechos distintos. Se IMPORTAN en vez de
#   copiarse, para que no se separen con el tiempo.
#   Los 34 sin serie de acá son 33 de los 36 del nacional más `pct_disc_comunicar`,
#   que es de la misma familia y comparte el motivo.
MOTIVO_2012 = dict(SIN_2012)
MOTIVO_2012.setdefault("pct_disc_comunicar", MOTIVO_2012["pct_disc_ver"])
# ★ Y EL QUE APARECIÓ AL SUBIR A ESCALA NACIONAL. `densidad` necesita la
#   superficie, y la superficie sale del mapa maestro, que es de hoy: el motor no
#   emite una de 2012. Sin motivo declarado, la tarjeta decía "sólo 2024" y
#   dejaba al lector sin saber si el censo no lo trae o si no lo hicimos.
MOTIVO_2012.setdefault("densidad",
                       "La densidad necesita la superficie municipal, que sale del mapa "
                       "maestro vigente. El motor no emite una superficie de 2012, así que "
                       "no hay cifra intercensal comparable.")
MOTIVO_GENERICO = "Sin cifra comparable para 2012."
# ⚠️ Los 30 fiscales declaraban `serie: true`, pero ahí `serie` significaba OTRA
#    cosa: la de gestiones 2016-2025. Con un conmutador de censo en pantalla, ese
#    flag prometía 2012 en 30 indicadores que no lo tienen ni pueden tenerlo.
MOTIVO_FISCAL = ("Es un indicador fiscal, no censal: se publica por gestión "
                 "(2016-2025) y no tiene lectura del censo de 2012.")


def cuantil(v, p):
    """El MISMO cuantil que usa el JS del tablero, para que el corte de color
    caiga en el mismo lugar del que lo calcularía el navegador."""
    if not v:
        return None
    v = sorted(v)
    h = (len(v) - 1) * p
    a = int(h // 1)
    b = min(a + 1, len(v) - 1)
    return v[a] + (h - a) * (v[b] - v[a])


def medir_serie(v12, claves, cods):
    """
    ★ LA PRESENCIA SE MIDE DEL DATO; lo único que se declara es la EXPLICACIÓN.

    Lo que había era `serie = {k for k in ks_a if k in v12.columns}`: mide que la
    COLUMNA EXISTA, no que tenga valor. Los motores emiten la columna igual
    —vacía— cuando 2012 no puede dar el indicador, así que el catálogo declaraba
    serie 2012 en 208 de 210 indicadores y sólo 176 tenían cifra. Con un
    conmutador de censo en la interfaz eso no es un flag inexacto: es prometerle
    al lector un mapa que va a salir gris entero.

    Un indicador con dato en ALGUNOS municipios sí tiene serie —el hueco es del
    municipio, no del censo— pero se avisa fuerte, porque hoy no hay ninguno y
    si aparece uno hay que mirarlo.
    """
    con, parcial, sin = set(), {}, set()
    for k in claves:
        if v12 is None or k not in v12.columns:
            sin.add(k)
            continue
        n = int(v12.loc[v12.index.isin(cods), k].notna().sum())
        if n == 0:
            sin.add(k)
        else:
            con.add(k)
            if n < len(cods):
                parcial[k] = n
    return con, parcial, sin


def anotar_serie(grupos, fichas, con12):
    """
    Cada indicador declara si se puede mirar en 2012, por qué no, y su ESCALA.

    ★ EL DOMINIO DE COLOR VIAJA EN EL CATÁLOGO, no se calcula en el navegador.
      La decisión de producto es UNA SOLA ESCALA PARA LOS DOS CENSOS —así un
      mismo tono significa un mismo valor y al alternar de año el corrimiento de
      color ES el avance— y para eso el rango se toma sobre la UNIÓN de 2012 y
      2024. Calcularlo en el cliente obligaría a esperar los dos censos antes
      del primer pintado.
      Se calcula sobre los valores YA REDONDEADOS que emite `bloque()`, que son
      los que ve el navegador, para que el corte caiga en el mismo lugar.

    Los fiscales quedan SIN `dom` a propósito: su valor depende de la gestión
    elegida, así que el rango lo sigue calculando la interfaz sobre lo que hay en
    pantalla.
    """
    for g in grupos:
        for i in g["indicadores"]:
            k = i["key"]
            if i.get("fuente") == "fiscal":
                i["s12"] = False
                i["w12"] = MOTIVO_FISCAL
                if "serie" in i:
                    i["serie_gestiones"] = i.pop("serie")
                continue
            if k in CONTEOS:
                i["agg"] = "suma"
            i["s12"] = k in con12
            if k not in con12:
                i["w12"] = MOTIVO_2012.get(k, MOTIVO_GENERICO)
            a = [f["municipal"].get(k) for f in fichas]
            b = [f.get("municipal_2012", {}).get(k) for f in fichas] if k in con12 else []
            u = [x for x in a + b if x is not None]
            if u:
                i["dom"] = [round(cuantil(u, .02), 4), round(cuantil(u, .98), 4)]
            if k not in con12:
                continue
            # el dominio del CAMBIO, simétrico alrededor de cero: un avance y un
            # retroceso del mismo tamaño tienen que pintarse con la misma fuerza,
            # o el mapa miente sobre la magnitud
            ds = []
            for f in fichas:
                x, y = f.get("municipal_2012", {}).get(k), f["municipal"].get(k)
                if x is None or y is None:
                    continue
                if k in CONTEOS:
                    if x:
                        ds.append(100 * (y - x) / x)
                else:
                    ds.append(y - x)
            if ds:
                i["domd"] = round(max(abs(cuantil(ds, .02)),
                                      abs(cuantil(ds, .98))) or 1, 4)


# ★ LAS DEFINICIONES SE DECLARAN, NO SE COMPONEN (2026-08-26).
#   Antes esto armaba la descripción pegando el título, el denominador y —si el
#   nombre coincidía exacto— la entrada del glosario del INE. El resultado era
#   «Acceso a fuente mejorada. Porcentaje sobre las viviendas particulares
#   ocupadas»: el título repetido más contabilidad. Decía sobre qué se divide,
#   nunca qué se está mirando.
#   Pedido de Carlos: «que se entienda solo leyendo qué nos muestra el gráfico».
#   Ahora hay una definición ESCRITA para cada uno de los 243 indicadores del
#   tablero municipal, en `catalogo/definiciones.json`, redactada contra la
#   expresión real (`e24`) y no contra el título —varios títulos prometen más de
#   lo que el dato mide—. Se arma con `catalogo/armar_definiciones.py` desde
#   `definiciones_a/b/c.py`, que son la fuente de verdad.
DEFINICIONES = json.loads((AQUI / "definiciones.json").read_text(encoding="utf-8"))


def describir(i, glosario):
    """La definición declarada. Si falta, se avisa fuerte en vez de inventar."""
    d = DEFINICIONES.get(i["k"])
    if not d:
        print(f"  ⚠ sin definición declarada: {i['k']} ({i['l']})")
        return i["l"] + "."
    return d


def universo_de(i):
    """Sobre qué se calcula. Va SEPARADO de la definición: es lo que hace falta
    para leer el número —un 40% no significa lo mismo sobre viviendas que sobre
    personas— pero no es lo que el indicador mide, así que no puede ocupar el
    lugar de la definición ni mezclarse con ella."""
    uni = UNIVERSO.get(i.get("uni"))
    if not uni:
        return ""
    return f"sobre {uni}" if i["u"] == "%" else f"medido sobre {uni}"


def cargar(fuentes, sufijo):
    """Une los CSV de los motores y devuelve (valores, denominadores)."""
    val, den = None, {}
    for f in fuentes:
        p = AQUI / f"{f}_{sufijo}.csv"
        if not p.exists():
            print(f"  (falta {p.name})")
            continue
        d = pd.read_csv(p, index_col=0, dtype={0: str})
        d.index = d.index.astype(str).str.zfill(6)
        base = POR_BLOQUE.get(f)
        propios = {c[5:]: d[c] for c in d.columns if c.startswith("_den_")}
        d = d.drop(columns=[c for c in d.columns if c.startswith("_den_")])
        for c in d.columns:
            den[c] = propios.get(c, d[base] if base and base in d.columns else None)
        d = renombrar(d)
        val = d if val is None else val.join(
            d[[c for c in d.columns if c not in val.columns]], how="outer")
    return val, {ALIAS.get(k, k): v for k, v in den.items()}


def region(val, den, ks, cods):
    """Agregado del PAÍS, ponderado por el universo de cada indicador."""
    out = {}
    if val is None:
        return out
    for k in ks:
        if k not in val.columns:
            continue
        sub = val.loc[val.index.isin(cods), k]
        w = den.get(k)
        if w is None:
            if sub.notna().any():
                out[k] = round(float(sub.mean()), 3)
            continue
        ww = w.reindex(sub.index)
        m = sub.notna() & ww.notna() & (ww > 0)
        if m.any():
            out[k] = round(float((sub[m] * ww[m]).sum() / ww[m].sum()), 3)
    return out


def bloque(val, ks, ci):
    if val is None or ci not in val.index:
        return {}
    o = {}
    for k in ks:
        if k in val.columns:
            v = val.at[ci, k]
            if np.isfinite(v):
                o[k] = round(float(v), 3)
    return o


def catalogo(claves, decl, nivel, glosario, avisos=None, err=None):
    """Catálogo en la forma que consume la web: grupos con `k_mun` / `k_mz`.

    La serie 2012 NO se declara acá: la anota `anotar_serie()` midiéndola del
    dato ya emitido. Antes salía de este punto un campo `serie` que nadie leía y
    que mentía en 62 de 240 indicadores."""
    por = {}
    for k in claves:
        i = decl[k]
        it = {"key": k, "label": i["l"], "unit": i["u"], "dir": i.get("d", 0),
              "desc": describir(i, glosario), "universo": universo_de(i),
              "fuente": "censo",
              "nivel": nivel, "k_mun": k,
              "k_mz": k if nivel in ("ambos", "solo_mz") else None,
              "continuo": nivel == "ambos"}
        # ★ SÓLO MANZANA. La ficha del geoportal separa cosas que el microdato
        #   municipal no separa —vertiente protegida, hacinamiento medio, el
        #   detalle de pisos—, así que estos indicadores existen abajo y no
        #   arriba. Entran igual, porque son la mitad del valor del nivel
        #   manzana, pero SE ROTULAN: al subir de nivel el mapa no muestra la
        #   cifra municipal del censo (no hay), sino el agregado de las manzanas
        #   urbanas de ese municipio. Callarlo sería publicar una cifra urbana
        #   bajo el nombre de una municipal, que es exactamente el sesgo de
        #   universo que este proyecto ya documentó.
        if nivel == "solo_mz":
            it["solo_mz"] = True
            it["aviso"] = ("Sólo existe a nivel manzana: el microdato municipal "
                           "no lo separa igual. Al ver el mapa de municipios se "
                           "muestra la suma de sus manzanas urbanas, que no "
                           "cubre el área rural.")
        if avisos and k in avisos:
            it["aviso"] = (f"La suma de las manzanas y la cifra urbana del municipio "
                           f"difieren {err.get(k, 0):.1f} pp en promedio: varía fuerte "
                           f"en el borde del área urbana censada.")
        por.setdefault(i["g"], []).append(it)
    return [{"key": g.lower().replace(" ", "_").replace("ó", "o").replace("í", "i"),
             "label": g, "indicadores": sorted(v, key=lambda x: x["label"])}
            for g, v in sorted(por.items())]


def main():
    decl = {i["k"]: i for i in
            json.loads((AQUI / "catalogo.json").read_text(encoding="utf-8"))["indicadores"]}
    comp = json.loads((AQUI / "comparables.json").read_text(encoding="utf-8"))
    muns = json.loads((RAIZ / "datos" / "municipios.json").read_text(encoding="utf-8"))
    cods = [m["cod_ine"] for m in muns]
    # ★ CUÁNTAS MANZANAS SON, MEDIDO Y NO ESCRITO. Sale de sumar lo que trae
    #   `municipios.json`, que a su vez lo contó del geoportal. Un número
    #   tipeado a mano en la portada envejece sin que nada falle.
    N_MANZANAS = sum(m.get("manzanas", 0) for m in muns)
    COBERTURA["manzana"] = cobertura_manzana(
        json.loads((RAIZ / "datos" / "cobertura.json").read_text(encoding="utf-8")))
    sp = {r["cod_ine"]: r for r in csv.DictReader(open(SPINE, encoding="utf-8"))}
    glosario = json.loads((AQUI / "glosario_ine.json").read_text(encoding="utf-8"))

    v24, d24 = cargar(FUENTES24, "2024")
    v12, d12 = cargar(FUENTES12, "2012")
    vur, dur = cargar(FUENTES_URB, "2024")

    def ficha(m, ks, con_urbano, con_2012):
        ci = m["cod_ine"]
        r = {"sigep": m.get("sigep"), "cod_ine": ci,
             "nombre": sp.get(ci, {}).get("nombre", m["nombre"]),
             "dpto": m.get("dpto"), "manzanas": m.get("manzanas"),
             "con_ficha": m.get("con_ficha"),
             "personas_urbano": m.get("personas_urbano"),
             "viviendas_urbano": m.get("viviendas_urbano"),
             # ★ población y viviendas viajan SIEMPRE, aunque no estén entre los
             #   indicadores del tablero: son CONTEXTO, no un indicador elegible.
             #   Sin esto el Tablero B —donde `pob_total` no es comparable con la
             #   manzana— encabezaba la ficha con "9 municipios · 0 personas".
             "municipal": bloque(v24, sorted(set(ks) | {"pob_total", "viviendas"}), ci)}
        r["urbano"] = bloque(vur, ks, ci) if con_urbano else {}
        if con_2012:
            r["municipal_2012"] = bloque(v12, ks, ci)
        return r

    # ── TABLERO A — municipal ────────────────────────────────────────────────
    ks_a = sorted(k for k in v24.columns if k in decl)
    con12, parcial12, sin12 = medir_serie(v12, ks_a, cods)
    print(f"TABLERO A · municipal: {len(ks_a)} indicadores · "
          f"con serie 2012 MEDIDA: {len(con12)} · sólo 2024: {len(sin12)}")
    if parcial12:
        print("  ⚠️ serie 2012 INCOMPLETA (dato en algunos municipios): "
              + ", ".join(f"{k} {n}/{len(cods)}" for k, n in sorted(parcial12.items())))
    huerf = sorted(k for k in sin12 if k not in MOTIVO_2012)
    if huerf:
        # ⚠️ Un "sólo 2024" sin explicación es una caja negra en la pantalla: el
        #    lector no puede saber si el censo no lo trae o si no lo hicimos.
        print(f"  ⚠️ SIN MOTIVO DECLARADO (agregar a SIN_2012 en generar_atlas.py): "
              f"{', '.join(huerf)}")
    sobran = sorted(k for k in MOTIVO_2012 if k in con12)
    if sobran:
        print(f"  ⚠️ declarados sin 2012 pero el motor SÍ los calcula: {', '.join(sobran)}")
    # las fichas se arman ANTES del catálogo porque el catálogo declara el
    # dominio de color, y ese dominio se mide sobre los valores ya redondeados
    # que van a viajar — no sobre los del dataframe
    fichas_a = [ficha(m, ks_a, False, True) for m in muns]
    grupos_a = catalogo(ks_a, decl, "municipio", glosario)
    anotar_serie(grupos_a, fichas_a, con12)
    ncont = sum(1 for g in grupos_a for i in g["indicadores"] if i.get("agg") == "suma")
    ndom = sum(1 for g in grupos_a for i in g["indicadores"] if i.get("dom"))
    print(f"  serie declarada: {sum(1 for g in grupos_a for i in g['indicadores'] if i['s12'])}"
          f" con 2012 · {ncont} conteos · {ndom} con dominio de color declarado")
    # ── EL COSTO DE COMPARTIR ESCALA, DICHO EN VOZ ALTA ──────────────────────
    # Compartir el dominio entre los dos censos es una decisión de producto (un
    # tono = un valor), y su costo es que el mapa de 2024 usa menos rampa. Con los
    # 343 el Atlas nacional midió que no costaba nada —la cola de municipios
    # extremos mantiene el dominio ancho—, pero se sigue informando: si algún día
    # cuesta, el número tiene que aparecer solo y no dejar de mirarse.
    # Se mide la POSICIÓN EN LA RAMPA, no el tramo de valores sobre el dominio:
    # son cosas distintas porque el pivote parte la rampa en dos mitades de ancho
    # numérico desigual, y es la posición la que el lector ve como color. Réplica
    # exacta de `escala()` + `posEnRampa()` del JS, para que este número y el que
    # se ve en pantalla sean el mismo.
    reg24 = region(v24, d24, ks_a, cods)

    def tramo_rampa(i):
        lo, hi = i["dom"]
        vals = [f["municipal"].get(i["key"]) for f in fichas_a]
        vals = [x for x in vals if x is not None]
        if not vals or hi <= lo:
            return None
        piv = (cuantil(sorted(vals), .5) if i.get("agg") == "suma"
               else reg24.get(i["key"], cuantil(sorted(vals), .5)))
        pad = (hi - lo) * .08
        piv = min(max(piv, lo + pad), hi - pad)
        def pos(x):
            t = (.5 if piv == lo else .5 * (x - lo) / (piv - lo)) if x <= piv \
                else .5 + .5 * (x - piv) / (hi - piv)
            return max(0.0, min(1.0, t))
        p = [pos(x) for x in vals]
        return max(p) - min(p)

    angosto = sorted((round(t, 2), i["key"]) for g in grupos_a for i in g["indicadores"]
                     if i.get("s12") and i.get("dom")
                     and (t := tramo_rampa(i)) is not None and t < .5)
    if angosto:
        print(f"  ⚠️ al compartir escala, {len(angosto)} indicadores dejan el mapa de 2024 "
              f"usando menos de la MITAD de la rampa (el avance intercensal fue grande):")
        for frac, k in angosto:
            print(f"    {k:26} usa {frac:.2f} de la rampa")
    else:
        print("  compartir escala no deja a ningún indicador bajo media rampa en 2024")

    (SALIDA_MUN / "catalogo_municipal.json").write_text(json.dumps({
        "tablero": "municipal", "anios_fiscal": [],
        "niveles": {"municipio": {"n": len(muns), "fuente": "INE Censo 2024 y 2012 · MEFP",
                                  "cobertura": COBERTURA["municipio"]}},
        "grupos": grupos_a,
        "region": {"municipal": region(v24, d24, ks_a, cods),
                   "municipal_2012": region(v12, d12, sorted(con12), cods)},
    }, ensure_ascii=False), encoding="utf-8")
    (SALIDA_MUN / "municipios_municipal.json").write_text(json.dumps(
        fichas_a, ensure_ascii=False), encoding="utf-8")

    # ── TABLERO B — municipio ↔ manzana ──────────────────────────────────────
    ks_b0 = sorted(set(comp["verificados"]) & set(decl) & set(v24.columns))
    ks_b = ks_b0

    # ★ LOS SÓLO-MANZANA NECESITAN UNA CIFRA MUNICIPAL PARA EL PANEL. El
    #   comparativo entre los nueve y la tira de distribución se dibujan con
    #   `k_mun`; sin ningún valor ahí, el panel derecho queda mudo justo en los
    #   indicadores nuevos. La cifra es el AGREGADO DE SUS MANZANAS, que
    #   `motor_manzana.py` ya calcula y guarda, y va rotulada como tal.
    agr = pd.read_csv(AQUI / "manzana_agregado_municipal.csv", dtype={0: str})
    agr = agr.rename(columns={agr.columns[0]: "cod_ine"}).set_index("cod_ine")
    agr.index = agr.index.astype(str).str.zfill(6)
    agr.columns = [ALIAS.get(c, c) for c in agr.columns]
    ks_mz = sorted(set(comp.get("solo_manzana", [])) & set(decl) & set(agr.columns))
    for k in ks_mz:
        if k not in v24.columns:
            v24[k] = agr[k].reindex(v24.index)
    print(f"TABLERO B · sólo manzana: {len(ks_mz)} indicadores "
          f"(cifra municipal = agregado de sus manzanas)")
    avisos, err = set(comp.get("con_aviso", [])), comp.get("error_pp", {})
    print(f"TABLERO B · comparables: {len(ks_b)} indicadores "
          f"({len(avisos)} con aviso · {len(comp.get('excluidos', []))} excluidos por definición)")
    grupos_b = catalogo(ks_b, decl, "ambos", glosario, avisos, err)
    # los sólo-manzana se funden en los mismos grupos temáticos, no en uno aparte:
    # lo que los distingue es la etiqueta de la tarjeta, no dónde viven
    for g_extra in catalogo(ks_mz, decl, "solo_mz", glosario):
        hit = next((g for g in grupos_b if g["key"] == g_extra["key"]), None)
        if hit:
            hit["indicadores"] = sorted(hit["indicadores"] + g_extra["indicadores"],
                                        key=lambda x: x["label"])
        else:
            grupos_b.append(g_extra)
    grupos_b.sort(key=lambda g: g["label"])
    # el nivel manzana no tiene serie intercensal (las fichas por manzano son sólo
    # de 2024), así que acá no va `s12` ni dominio declarado: lo único que hace
    # falta es que un conteo se sepa conteo, para que la escala lo centre en su
    # mediana en vez de en un promedio ponderado que no significa nada
    for g in grupos_b:
        for i in g["indicadores"]:
            if i["key"] in CONTEOS:
                i["agg"] = "suma"
    (SALIDA / "catalogo_manzana.json").write_text(json.dumps({
        "tablero": "manzana", "anios_fiscal": [],
        "niveles": {k: {"n": len(muns) if k == "municipio" else N_MANZANAS,
                        "fuente": ("INE Censo 2024, microdato" if k == "municipio"
                                   else "INE Censo 2024, fichas por manzano"),
                        "cobertura": COBERTURA[k]} for k in ("municipio", "manzana")},
        "excluidos": comp.get("excluidos", []),
        "grupos": grupos_b,
        "region": {"municipal": region(v24, d24, ks_b, cods),
                   "urbano": region(vur, dur, ks_b, cods)},
    }, ensure_ascii=False), encoding="utf-8")
    (SALIDA / "municipios_manzana.json").write_text(json.dumps(
        # ⚠️ ks_b + ks_mz: sin las claves sólo-manzana, la ficha municipal no las
        #    trae y el comparativo entre los nueve queda en "Sin datos para este
        #    indicador" justo en densidad y en los otros 16 — que son los que se
        #    acaban de agregar. La tira de abajo sí los dibujaba (sale de
        #    `mz_stats.json`), así que el panel se contradecía consigo mismo.
        [ficha(m, sorted(set(ks_b) | set(ks_mz)), True, False) for m in muns],
        ensure_ascii=False), encoding="utf-8")

    for d, n in ((SALIDA_MUN, "catalogo_municipal"), (SALIDA_MUN, "municipios_municipal"),
                 (SALIDA, "catalogo_manzana"), (SALIDA, "municipios_manzana")):
        f = d / f"{n}.json"
        donde = "datos/" if d is SALIDA_MUN else "docs/datos/"
        print(f"  -> {donde + f.name:<40}{f.stat().st_size/1024:>8.0f} KB"
              + ("   (no se publica)" if d is SALIDA_MUN else ""))


if __name__ == "__main__":
    main()
