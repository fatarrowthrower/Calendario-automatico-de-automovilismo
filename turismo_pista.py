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


def clean_cell(html):
    html = re.sub(
        r"<br\s*/?>",
        " ",
        html,
        flags=re.I,
    )

    html = re.sub(
        r"<[^>]+>",
        " ",
        html,
    )

    html = unescape(html)

    html = html.replace(
        "\xa0",
        " ",
    )

    html = re.sub(
        r"\s+",
        " ",
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
        text = text.replace(
            old,
            new,
        )

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
            data = json.loads(
                fetch(url)
            )
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

            link = item.get(
                "url",
                "",
            )

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

            title = clean_cell(title)

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

    return list(
        unique.values()
    )


def score_article(article, year):
    title = normalize(
        article["title"]
    )

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


def extract_calendar_table(html, year):
    """
    Busca una tabla HTML que contenga:

        CALENDARIO YYYY
        Carrera
        Fecha

    y extrae exclusivamente sus filas.
    """

    # Buscar todas las tablas de la página.
    tables = re.findall(
        r"<table\b[^>]*>.*?</table>",
        html,
        flags=re.I | re.S,
    )

    print(
        f"  Tablas HTML encontradas: "
        f"{len(tables)}"
    )

    for table in tables:
        table_text = normalize(
            clean_cell(table)
        )

        if (
            f"calendario {year}" not in table_text
            and "carrera" not in table_text
        ):
            continue

        rows = re.findall(
            r"<tr\b[^>]*>(.*?)</tr>",
            table,
            flags=re.I | re.S,
        )

        events = []

        for row in rows:
            cells = re.findall(
                r"<t[dh]\b[^>]*>(.*?)</t[dh]>",
                row,
                flags=re.I | re.S,
            )

            cells = [
                clean_cell(cell)
                for cell in cells
            ]

            if len(cells) < 2:
                continue

            first = normalize(
                cells[0]
            )

            second = normalize(
                cells[1]
            )

            # Ignorar encabezado.
            if (
                "carrera" in first
                or "fecha" in second
            ):
                continue

            round_match = re.search(
                r"(\d{1,2})"
                r"\s*(?:°|º|o)?"
                r"\s*fecha",
                first,
                flags=re.I,
            )

            if not round_match:
                continue

            round_number = int(
                round_match.group(1)
            )

            date_match = re.search(
                r"(\d{1,2})"
                r"\s*(?:°|º|o)?"
                r"\s*(?:de\s+)?"
                r"(enero|febrero|marzo|abril|"
                r"mayo|junio|julio|agosto|"
                r"septiembre|setiembre|octubre|"
                r"noviembre|diciembre)",
                second,
                flags=re.I,
            )

            if not date_match:
                continue

            day = int(
                date_match.group(1)
            )

            month_name = (
                date_match.group(2)
            ).lower()

            month = MONTHS.get(
                month_name
            )

            if not month:
                continue

            date = (
                f"{year:04d}-"
                f"{month:02d}-"
                f"{day:02d}"
            )

            try:
                datetime.strptime(
                    date,
                    "%Y-%m-%d",
                )
            except ValueError:
                continue

            # La localidad puede venir después
            # de un guion en la misma celda.
            location = ""

            location_match = re.search(
                r"[-–—]\s*(.+)$",
                cells[1],
            )

            if location_match:
                location = (
                    location_match.group(1)
                    .strip()
                )

            if not location:
                location = "Argentina"

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

        if len(events) >= 1:
            unique = {}

            for event in events:
                unique[event["uid"]] = event

            events = list(
                unique.values()
            )

            events.sort(
                key=lambda event: event[
                    "fecha_inicio"
                ]
            )

            return events

    return []


def main():
    year = current_year()

    print(
        f"Buscando Turismo Pista "
        f"para {year}..."
    )

    articles = search_aptp(
        year
    )

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

    best_events = []

    for article in articles:
        print()
        print(
            f"Analizando: "
            f"{article['title']}"
        )

        print(
            article["url"]
        )

        try:
            html = fetch(
                article["url"]
            )
        except Exception as exc:
            print(
                f"  ERROR: {exc}"
            )
            continue

        events = extract_calendar_table(
            html,
            year,
        )

        print(
            f"  Fechas encontradas: "
            f"{len(events)}"
        )

        if len(events) > len(best_events):
            best_events = events

        if len(best_events) >= 10:
            break

    best_events.sort(
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
            best_events,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(
        f"Turismo Pista: "
        f"{len(best_events)} eventos encontrados."
    )

    for event in best_events:
        print(
            f"  {event['uid']} | "
            f"{event['fecha_inicio']} | "
            f"{event['ubicacion']}"
        )

    if len(best_events) != 10:
        print()
        print(
            "ADVERTENCIA: "
            f"se esperaban 10 fechas y "
            f"se encontraron {len(best_events)}."
        )


if __name__ == "__main__":
    main()
