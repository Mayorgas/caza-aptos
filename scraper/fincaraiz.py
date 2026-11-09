#!/usr/bin/env python3
"""
Actualiza docs/listings.json con avisos de arriendo de Fincaraíz.

Uso (desde la carpeta Caza-Apartamentos):
    python scraper/fincaraiz.py
    python scraper/fincaraiz.py --paginas 3          # solo las primeras 3 páginas por localidad
    python scraper/fincaraiz.py --playwright          # si el sitio bloquea las peticiones simples

Cada página de resultados de Fincaraíz trae los avisos en un bloque JSON
(<script id="__NEXT_DATA__">), así que no hace falta leer el HTML visual.
Los filtros de zona y precio van en la URL, igual que en el sitio.
"""
import argparse, json, re, sys, time, urllib.request, urllib.error
from datetime import date
from pathlib import Path

# ---- Configuración de la búsqueda ------------------------------------------
LOCALIDADES = ["usaquen", "chapinero", "suba", "barrios-unidos"]
PRECIO_MAX = 1_800_000          # el portal filtra por arriendo; el tope con admin se aplica abajo
BASE = "https://www.fincaraiz.com.co"
PAUSA_SEG = 1.5                 # pausa entre páginas, para no cargar el sitio
# -----------------------------------------------------------------------------

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "docs" / "listings.json"
NEXT_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
    "Accept-Language": "es-CO,es;q=0.9",
}


def url_busqueda(localidad, pagina):
    u = f"{BASE}/arriendo/apartamentos/{localidad}/bogota/hasta-{PRECIO_MAX}/pesos"
    return u if pagina == 1 else f"{u}/pagina{pagina}"


def html_simple(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


_pw = {}
def html_playwright(url):
    if "page" not in _pw:
        from playwright.sync_api import sync_playwright
        _pw["p"] = sync_playwright().start()
        _pw["b"] = _pw["p"].chromium.launch()
        _pw["page"] = _pw["b"].new_page(user_agent=HEADERS["User-Agent"])
    _pw["page"].goto(url, wait_until="domcontentloaded", timeout=45000)
    return _pw["page"].content()


def leer_pagina(url, usar_playwright):
    html = html_playwright(url) if usar_playwright else html_simple(url)
    m = NEXT_RE.search(html)
    if not m:
        raise RuntimeError("La página no trae el bloque de datos (posible bloqueo o cambio del sitio)")
    return json.loads(m.group(1))["props"]["pageProps"]["fetchResult"]["searchFast"]


def num(v):
    d = re.sub(r"\D", "", str(v or ""))
    return int(d) if d else None


def normalizar(a, localidad):
    ts = {t.get("field"): t.get("value") for t in (a.get("technicalSheet") or [])}
    admin = (a.get("commonExpenses") or {}).get("amount") or None
    arriendo = a["price"]["amount"]
    total = a["price"].get("admin_included") or arriendo
    hoy = date.today().isoformat()
    return {
        "id": f"fr-{a['id']}",
        "fuente": "Fincaraíz",
        "url": BASE + a["link"],
        "arriendo": arriendo,
        "admin": admin,
        "total": total,
        "admin_conocida": bool(admin) or total > arriendo,
        "area": num(a.get("m2apto")) or a.get("m2"),
        "habs": a.get("bedrooms") or a.get("rooms"),
        "banos": a.get("bathrooms"),
        "parqueaderos": a.get("garage") or 0,
        "estrato": a.get("stratum"),
        "piso": num(ts.get("floor")),
        "barrio": (a.get("locations") or {}).get("location_main", {}).get("name", "").strip().title(),
        "localidad": localidad,
        "lat": a.get("latitude"),
        "lng": a.get("longitude"),
        "fotos": [i["image"] for i in (a.get("images") or [])[:5] if i.get("image")],
        "desc": re.sub(r"\s+", " ", a.get("description") or "")[:280],
        "extras": [f["name"] for f in (a.get("facilities") or [])][:8],
        "anunciante": (a.get("owner") or {}).get("name"),
        "publicado": a.get("created_at"),
        "actualizado": a.get("updated_at"),
        "primera_vez": hoy,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paginas", type=int, default=0, help="máximo de páginas por localidad (0 = todas)")
    ap.add_argument("--playwright", action="store_true", help="usar un navegador real en vez de peticiones simples")
    args = ap.parse_args()

    previos = {}
    if SALIDA.exists():
        try:
            previos = {x["id"]: x for x in json.loads(SALIDA.read_text(encoding="utf-8")).get("items", [])}
        except Exception:
            pass

    nuevos = {}
    for loc in LOCALIDADES:
        pagina, ultima = 1, 1
        while pagina <= ultima and (not args.paginas or pagina <= args.paginas):
            url = url_busqueda(loc, pagina)
            try:
                s = leer_pagina(url, args.playwright)
            except (urllib.error.URLError, RuntimeError) as e:
                print(f"[{loc} p{pagina}] {e}", file=sys.stderr)
                break
            ultima = s["paginatorInfo"]["lastPage"]
            for a in s["data"]:
                x = normalizar(a, loc)
                if x["total"] <= PRECIO_MAX:             # tope real: arriendo + administración
                    if x["id"] in previos:               # conserva la fecha en que lo vimos por primera vez
                        x["primera_vez"] = previos[x["id"]].get("primera_vez", x["primera_vez"])
                    nuevos[x["id"]] = x
            print(f"[{loc}] página {pagina}/{ultima}: {len(nuevos)} avisos acumulados")
            pagina += 1
            time.sleep(PAUSA_SEG)

    if not nuevos:
        sys.exit("No se obtuvo ningún aviso; no se modificó listings.json")

    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps({
        "generado": date.today().isoformat(),
        "fuente": "Fincaraíz",
        "items": sorted(nuevos.values(), key=lambda x: x.get("actualizado") or "", reverse=True),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Listo: {len(nuevos)} avisos en {SALIDA}")


if __name__ == "__main__":
    main()
