# -*- coding: utf-8 -*-
"""
SERVIDOR LOCAL CON RANGE REQUESTS — el que hace falta para probar PMTiles.
==========================================================================

⚠️ `python -m http.server` NO implementa `Range`: ante un pedido de rango
   responde **200 con el archivo entero**. Con teselas eso significa bajar los
   11,5 MB completos en cada pedido, así que la prueba local mide algo que no
   se parece en nada a producción — y peor, puede parecer que PMTiles "no
   sirve" cuando el que no sirve es el servidor de prueba.

GitHub Pages sí lo implementa (verificado: `Accept-Ranges: bytes` y un 206 con
la cantidad exacta de bytes pedidos), que es lo que hace viable servir un
archivo de teselas desde ahí.

    python scripts/servir.py [puerto]
"""
import functools, http.server, os, pathlib, re, socketserver, sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent / "docs"


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        # sin caché: al iterar sobre el tablero, una tesela vieja en caché
        # manda a diagnosticar un bug que ya estaba arreglado
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_head(self):
        rango = self.headers.get("Range")
        if not rango:
            return super().send_head()
        m = re.match(r"bytes=(\d*)-(\d*)$", rango.strip())
        ruta = self.translate_path(self.path)
        if not m or not os.path.isfile(ruta):
            return super().send_head()
        tam = os.path.getsize(ruta)
        ini, fin = m.group(1), m.group(2)
        if ini == "":                      # sufijo: los últimos N bytes
            largo = min(int(fin or 0), tam)
            ini = tam - largo
            fin = tam - 1
        else:
            ini = int(ini)
            fin = int(fin) if fin else tam - 1
        if ini >= tam:
            self.send_error(416, "Rango fuera del archivo")
            return None
        fin = min(fin, tam - 1)
        f = open(ruta, "rb")
        f.seek(ini)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(ruta))
        self.send_header("Content-Range", f"bytes {ini}-{fin}/{tam}")
        self.send_header("Content-Length", str(fin - ini + 1))
        self.end_headers()
        # SimpleHTTPRequestHandler copia hasta EOF, así que se acota el archivo
        # a la ventana pedida antes de devolverlo
        datos = f.read(fin - ini + 1)
        f.close()
        import io
        return io.BytesIO(datos)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    puerto = int(sys.argv[1]) if len(sys.argv) > 1 else 8099
    os.chdir(RAIZ)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", puerto), Handler) as s:
        print(f"http://127.0.0.1:{puerto}/  (con Range)  · Ctrl-C para parar")
        s.serve_forever()
