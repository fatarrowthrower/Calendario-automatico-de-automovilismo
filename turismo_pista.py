import json
import re
from datetime import datetime
from html import unescape
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


OUTPUT = Path("data/turismo_pista_events.json")

BASE_URL = "https://aptpweb.com.ar"
WP_SEARCH_URL = BASE_URL + "/wp-json/wp/v2/search"


MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def current_year():
    return datetime.now().year


def fetch(url):
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; AutomovilismoCalendar/1.0)"
            )
        },
    )

    with urlopen(request, timeout=30) as response:
        return response.read().decode(
            "utf-8",
            errors="ignore",
        )


def clean_html(html):
    html = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        html,
        flags=re.I | re.S,
    )

    html = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        html,
        flags=re.I | re.S,
    )

    html = re.sub(
        r"<br\s*/?>",
        "\n",
        html,
        flags=re.I,
    )

    html = re.sub(
        r"</p\s*>",
        "\n",
        html,
        flags=re.I,
    )

    html = re.sub(
        r"</li\s*>",
        "\n",
        html,
        flags=re.I,
    )

    html = re.sub(
        r"<[^>]+>",
        " ",
        html,
    )

    html = unescape(html)

    html = html.replace("\xa0", " ")

    html = re.sub(
        r"[ \t]+",
        " ",
        html,
    )

    html = re.sub(
        r"\n+",
        "\n",
        html,
    )

    return html.strip()


def normalize(text):
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
        "Á": "a",
        "É": "e",
        "Í": "i",
        "Ó": "o",
        "Ú": "u",
        "Ü": "u",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text.lower()


def search_aptp(year):
    queries = [
        f"calendario {year}",
        f"turismo pista calendario {year}",
        f"calendario turismo pista {year}",
    ]

    results = []

    for query in queries:
        url = (
            WP_SEARCH_URL
            + "?search="
            + quote(query)
            + "&per_page=20"
        )

        print(
            f"Buscando en APTP: {query}"
        )

        try:
            data = json.loads(fetch(url))
        except Exception as exc:
            print(
                f"  ERROR búsqueda: {exc}"
            )
            continue

        if not isinstance(data, list):
            continue

        for item in data:
            if not isinstance(item, dict):
                continue

            link = item.get("url", "")

            title_data = item.get(
                "title",
                "",
            )

            if isinstance(title_data, dict):
                title = title_data.get(
                    "rendered",
                    "",
                )
            else:
                title = str(title_data)

            title = clean_html(title)

            if not link:
                continue

            combined = normalize(
                title
                + " "
                + link
            )

            if str(year) not in combined:
                continue

            if "turismo pista" not in combined:
                continue

            results.append(
                {
                    "url": link,
                    "title": title,
                }
            )

    unique = {}

    for result in results:
        unique[result["url"]] = result

    return list(unique.values())


def score_article(article, year):
    title = normalize(article["title"])

    score = 0

    if "calendario" in title:
        score += 20

    if str(year) in title:
        score += 20

    if "turismo pista" in title:
        score += 10

    if "presentaron el calendario" in title:
        score += 30

    if "recorrido completo" in title:
        score += 25

    if "calendario completo" in title:
        score += 25

    return score


def find_calendar_blocks(text, year):
    """
    Busca bloques de texto alrededor de expresiones como:

    1° Fecha: 1 de febrero - La Plata
    2° Fecha: 1 de marzo - Toay

    También acepta variantes como:

    1 Fecha
    1º Fecha
    1° FECHA
    Fecha 1
    """

    text = text.replace("\r", "\n")

    # Mantener una copia normalizada para las búsquedas.
    normalized = normalize(text)

    blocks = []

    # Caso habitual:
    # 1 Fecha ... 1 de febrero ... La Plata
    pattern_a = re.compile(
        r"(?P<round>\d{1,2})"
        r"\s*(?:°|º|o)?"
        r"\s*fecha"
        r".{0,250}?"
        r"(?P<day>\d{1,2})"
        r"\s*(?:de\s+)?"
        r"(?P<month>"
        r"enero|febrero|marzo|abril|mayo|junio|"
        r"julio|agosto|septiembre|setiembre|"
        r"octubre|noviembre|diciembre"
        r")"
        r"(?P<after>.{0,180})",
        re.I | re.S,
    )

    for match in pattern_a.finditer(normalized):
        blocks.append(match)

    # Variante:
    # Fecha 1 ... 1 de febrero ... La Plata
    pattern_b = re.compile(
        r"fecha"
        r"\s*(?P<round>\d{1,2})"
        r".{0,250}?"
        r"(?P<day>\d{1,2})"
        r"\s*(?:de\s+)?"
        r"(?P<month>"
        r"enero|febrero|marzo|abril|mayo|junio|"
        r"julio|agosto|septiembre|setiembre|"
        r"octubre|noviembre|diciembre"
        r")"
        r"(?P<after>.{0,180})",
        re.I | re.S,
    )

    for match in pattern_b.finditer(normalized):
        blocks.append(match)

    return blocks


def extract_location(after):
    """
    Intenta obtener la localidad que aparece después de la fecha.
    """

    text = after

    # Separadores típicos usados en calendarios.
    text = re.sub(
        r"^[\s\-–—|:;,]+",
        "",
        text,
    )

    # Cortar cuando empieza otra fecha/fecha siguiente.
    text = re.split(
        r"\b\d{1,2}\s*(?:°|º|o)?\s*fecha\b",
        text,
        maxsplit=1,
        flags=re.I,
    )[0]

    text = re.split(
        r"\bfecha\s+\d{1,2}\b",
        text,
        maxsplit=1,
        flags=re.I,
    )[0]

    # Cortar frases que claramente no son una localidad.
    text = re.split(
        r"\b(?:la temporada|el calendario|"
        r"turismo pista|clase uno|clase dos|"
        r"clase tres|actc|autodromo|autódromo)\b",
        text,
        maxsplit=1,
        flags=re.I,
    )[0]

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip(
        " -–—|:;,.\"'"
    )

    # Evitar capturar párrafos completos.
    if len(text) > 70:
        text = text[:70]

    # Si quedó algo demasiado genérico, no inventamos.
    if not text:
        return "Argentina"

    return text


def extract_events(text, year):
    events = []

    matches = find_calendar_blocks(
        text,
        year,
    )

    seen_rounds = set()

    for match in matches:
        try:
            round_number = int(
                match.group("round")
            )

            day = int(
                match.group("day")
            )

            month_name = (
                match.group("month")
            ).lower()

            month = MONTHS.get(
                month_name
            )

            if not month:
                continue

            if round_number in seen_rounds:
                continue

            if day < 1 or day > 31:
                continue

            date = (
                f"{year:04d}-"
                f"{month:02d}-"
                f"{day:02d}"
            )

            # Validación real de la fecha.
            try:
                datetime.strptime(
                    date,
                    "%Y-%m-%d",
                )
            except ValueError:
                continue

            location = extract_location(
                match.group("after")
            )

            events.append(
                {
                    "uid": (
                        f"turismo-pista-"
                        f"{year}-"
                        f"{round_number:02d}"
                    ),
                    "categoria": "Argentina",
                    "campeonato": "Turismo Pista",
                    "tipo": "Carrera",
                    "fecha_inicio": (
                        f"{date}T12:00:00"
                    ),
                    "fecha_fin": (
                        f"{date}T23:59:00"
                    ),
                    "ubicacion": location,
                    "descripcion": (
                        f"Turismo Pista - "
                        f"Fecha {round_number}"
                    ),
                    "prioridad": "",
                }
            )

            seen_rounds.add(
                round_number
            )

        except Exception:
            continue

    return events


def main():
    year = current_year()

    print(
        f"Buscando Turismo Pista "
        f"para {year}..."
    )

    articles = search_aptp(year)

    print(
        f"Artículos candidatos: "
        f"{len(articles)}"
    )

    if not articles:
        print(
            f"APTP todavía no publicó "
            f"un calendario detectable "
            f"para {year}."
        )

        OUTPUT.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        OUTPUT.write_text(
            "[]",
            encoding="utf-8",
        )

        return

    articles.sort(
        key=lambda article: score_article(
            article,
            year,
        ),
        reverse=True,
    )

    all_events = []

    for article in articles:
        print()
        print(
            f"Analizando: "
            f"{article['title']}"
        )

        print(article["url"])

        try:
            html = fetch(
                article["url"]
            )
        except Exception as exc:
            print(
                f"  ERROR: {exc}"
            )
            continue

        text = clean_html(html)

        events = extract_events(
            text,
            year,
        )

        print(
            f"  Fechas encontradas: "
            f"{len(events)}"
        )

        all_events.extend(events)

        # Si ya tenemos las 10 fechas,
        # no necesitamos seguir analizando
        # artículos secundarios.
        if len(
            {
                event["uid"]
                for event in all_events
            }
        ) >= 10:
            break

    unique = {}

    for event in all_events:
        unique[event["uid"]] = event

    events = list(unique.values())

    events.sort(
        key=lambda event: event[
            "fecha_inicio"
        ]
    )

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT.write_text(
        json.dumps(
            events,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(
        f"Turismo Pista: "
        f"{len(events)} eventos encontrados."
    )

    for event in events:
        print(
            f"  {event['uid']} | "
            f"{event['fecha_inicio']} | "
            f"{event['ubicacion']}"
        )

    if not events:
        print(
            f"No se encontraron fechas "
            f"para {year}."
        )


if __name__ == "__main__":
    main()
