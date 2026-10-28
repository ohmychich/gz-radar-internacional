# Radar Internacional

Dashboard de noticias de medios internacionales sobre **mercado de capitales**, **tecnología e IA**
y **geopolítica**, con foco en **África y Medio Oriente**.

- Corre solo, gratis y sin IA: un robot de GitHub Actions lee los feeds RSS una vez por hora.
- Las noticias en español e inglés quedan en su idioma original. Las que están en árabe, hebreo,
  alemán y francés se traducen al español con [Argos Translate](https://github.com/argosopentech/argos-translate),
  que corre dentro del mismo robot (sin claves ni límites).
- El sitio es estático y se publica con GitHub Pages.

## Cómo funciona

```
feeds RSS ──► GitHub Actions (cada hora)                   ──► GitHub Pages
              1. descarga los feeds          radar/feeds.py      docs/index.html
              2. clasifica por tema/región   radar/classify.py   lee docs/data/news.json
              3. traduce al español          radar/translate.py
              4. guarda docs/data/*.json     radar/main.py
```

| Archivo | Para qué sirve |
|---|---|
| `config/feeds.yaml` | Lista de medios y feeds. Para sumar uno, agregá un bloque. |
| `config/temas.yaml` | Palabras clave de cada tema y región, y los filtros que descartan titulares de cotizaciones. |
| `docs/data/news.json` | Noticias de los últimos 7 días (lo genera el robot). |
| `docs/data/feeds-status.json` | Estado de cada feed en la última corrida (se ve en el botón "Estado de fuentes"). |
| `docs/data/translations-cache.json` | Traducciones ya hechas, para no repetirlas. |

## Puesta en marcha (una sola vez)

1. **Pages:** *Settings → Pages → Build and deployment*: *Source* = **Deploy from a branch**,
   *Branch* = **main** y carpeta **/docs**.
2. **Primera corrida:** *Actions → Actualizar noticias → Run workflow*. La primera tarda más
   porque descarga los modelos de traducción.
3. El sitio queda en `https://ohmychich.github.io/gz-radar-internacional/`.

## Correrlo localmente

```bash
python -m venv .venv && . .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python -m unittest
python -m radar.main
python -m http.server -d docs 8000
```

## Notas

- Solo se muestran titular, resumen y link. El artículo completo se lee en el sitio de cada medio.
- GitHub pausa los workflows programados de repos públicos después de 60 días sin actividad.
  Los commits del robot cuentan como actividad, pero si alguna vez se pausa, se reactiva desde la pestaña *Actions*.
