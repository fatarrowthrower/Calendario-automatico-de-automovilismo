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
        r"</tr\s*>",
        "\n",
        html,
        flags=re.I,
    )

    html = re.sub(
        r"</td\s*>",
        " | ",
        html,
        flags=re.I,
    )

    html = re.sub(
        r"</th\s*>",
        " | ",
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

            title = clean_html(
                title
            )

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


def extract_calendar_section(text, year):
    normalized = normalize(text)

    marker = f"calendario {year}"

    start = normalized.find(
        marker
    )

    if start == -1:
        return ""

    section = normalized[start:]

    # Cortamos antes de las noticias
    # que aparecen debajo del calendario.
    end_markers = [
        "compartir en:",
    ]

    end_positions = []

    for marker_end in end_markers:
        position = section.find(
            marker_end,
            len(marker),
        )

        if position != -1:
            end_positions.append(
                position
            )

    if end_positions:
        section = section[
            :min(end_positions)
        ]

    return section


def extract_events(text, year):
    section = extract_calendar_section(
        text,
        year,
    )

    if not section:
        print(
            "  No se encontró la sección "
            f"CALENDARIO {year}."
        )
        return []

    print(
        f"  Sección CALENDARIO {year} encontrada."
    )

    events = []

    # APTP publica actualmente:
    #
    # 1° FECHA 1° febrero – La Plata
    # 2° FECHA 1° marzo
    # 3° FECHA 12 de abril
    #
    # Importante:
    # el día también puede llevar °
    # o º, por ejemplo 1° febrero.

    pattern = re.compile(
        r"(?P<round>\d{1,2})"
        r"\s*(?:°|º|o)?"
        r"\s*fecha"
        r"\s*(?:\||:)?\s*"
        r"(?P<day>\d{1,2})"
        r"\s*(?:°|º|o)?"
        r"\s*(?:de\s+)?"
        r"(?P<month>"
        r"enero|febrero|marzo|abril|mayo|junio|"
        r"julio|agosto|septiembre|setiembre|"
        r"octubre|noviembre|diciembre"
        r")"
        r"(?:\s*[-–—|]\s*"
        r"(?P<location>"
        r"[a-záéíóúüñ0-9 .,'()\-]+"
        r"))?",
        re.I,
    )

    for match in pattern.finditer(
        section
    ):
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

        location = (
            match.group("location")
            or ""
        ).strip()

        if not location:
            location = "Argentina"

        location = re.sub(
            r"\s+",
            " ",
            location,
        ).strip(
            " -–—|:;,.\"'"
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

    events = []

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

        text = clean_html(
            html
        )

        candidate_events = extract_events(
            text,
            year,
        )

        print(
            f"  Fechas encontradas: "
            f"{len(candidate_events)}"
        )

        if len(candidate_events) > len(events):
            events = candidate_events

        if len(events) >= 10:
            break

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

    if len(events) != 10:
        print()
        print(
            "ADVERTENCIA: "
            f"se esperaban 10 fechas y "
            f"se encontraron {len(events)}."
        )


if __name__ == "__main__":
    main()
