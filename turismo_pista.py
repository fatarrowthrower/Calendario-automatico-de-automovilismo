import json
import re
from datetime import datetime
from html import unescape
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


OUTPUT = Path("data/turismo_pista_events.json")

BASE_URL = "https://aptpweb.com.ar"
WP_SEARCH_URL = (
    BASE_URL
    + "/wp-json/wp/v2/search"
)

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
                "(compatible; "
                "AutomovilismoCalendar/1.0)"
            )
        },
    )

    with urlopen(
        request,
        timeout=30,
    ) as response:
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
        "°": "",
        "º": "",
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

        for item in data:
            link = item.get(
                "url",
                "",
            )

            title = (
                item.get(
                    "title",
                    {},
                )
                .get(
                    "rendered",
                    "",
                )
            )

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

            # El año debe estar realmente
            # asociado a la publicación.
            if str(year) not in combined:
                continue

            # Tiene que tratarse de Turismo Pista.
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
        score += 10

    if str(year) in title:
        score += 10

    if "turismo pista" in title:
        score += 5

    if (
        "presentaron el calendario"
        in title
    ):
        score += 20

    if (
        "recorrido completo"
        in title
    ):
        score += 15

    if (
        "calendario completo"
        in title
    ):
        score += 15

    return score


def extract_events(text, year):
    normalized = normalize(
        text
    )

    # Buscamos explícitamente "FECHA"
    # seguida de día + mes.
    pattern = re.compile(
        r"(\d{1,2})\s*"
        r"fecha"
        r".{0,120}?"
        r"(\d{1,2})\s*"
        r"(?:de\s+)?"
        r"(enero|febrero|marzo|abril|mayo|"
        r"junio|julio|agosto|septiembre|"
        r"setiembre|octubre|noviembre|"
        r"diciembre)"
        r"(?:.{0,100}?"
        r"[-–—|]\s*"
        r"([a-záéíóúñ0-9().,' ]+))?",
        re.I,
    )

    events = []

    for match in pattern.finditer(
        normalized
    ):

        round_number = int(
            match.group(1)
        )

        day = int(
            match.group(2)
        )

        month_name = match.group(3)

        month = MONTHS.get(
            month_name
        )

        if not month:
            continue

        location = (
            match.group(4)
            or ""
        ).strip()

        location = re.sub(
            r"\s+",
            " ",
            location,
        )

        # Evitar que texto posterior
        # del artículo sea tomado como sede.
        location = re.split(
            r"\b(?:fecha|carrera|calendario|"
            r"turismo pista)\b",
            location,
            maxsplit=1,
            flags=re.I,
        )[0].strip()

        if len(location) > 80:
            location = location[:80].strip()

        if not location:
            location = "Argentina"

        date = (
            f"{year:04d}-"
            f"{month:02d}-"
            f"{day:02d}"
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
            f"APT P todavía no publicó "
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

        events = extract_events(
            text,
            year,
        )

        print(
            f"  Fechas encontradas: "
            f"{len(events)}"
        )

        all_events.extend(
            events
        )

        # Un artículo con 10 fechas
        # es nuestro calendario completo.
        if len(events) >= 10:
            break

    unique = {}

    for event in all_events:
        unique[event["uid"]] = event

    events = list(
        unique.values()
    )

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
