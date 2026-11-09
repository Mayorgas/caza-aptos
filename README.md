# Caza Aptos

App tipo swipe para revisar apartamentos en arriendo del norte de Bogotá (hasta $1.800.000 con administración).

- `docs/` es la página que se publica con GitHub Pages (`index.html` y `listings.json`).
- `scraper/fincaraiz.py` trae los avisos de Fincaraíz y reescribe `docs/listings.json`.
- `.github/workflows/actualizar.yml` corre el script todos los días a las 6:00 a. m. (Bogotá) y guarda el resultado.

Para correrlo en tu computador: `python scraper/fincaraiz.py`
