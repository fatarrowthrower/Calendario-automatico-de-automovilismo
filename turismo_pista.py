import json
import re
from datetime import datetime
from html import unescape
from pathlib import Path
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


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
        return response.read()


def fetch_text(url):
    return fetch(url).decode(
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


def search_aptp(query):
    url = (
        WP_SEARCH_URL
        + "?search="
        + quote(query)
        + "&per_page=30"
    )

    try:
        data = json.loads(
            fetch_text(url)
        )
    except Exception as exc:
        print(
            f"  ERROR búsqueda '{query}': "
            f"{exc}"
        )
        return []

    if not isinstance(data, list):
        return []

    results = []

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

        if isinstance(
            title_data,
            dict,
        ):
            title = title_data.get(
                "rendered",
                "",
            )
        else:
            title = str(
                title_data
            )

        title = clean_html(
            title
        )

        if not link:
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


def search_calendar_articles(year):
    queries = [
        f"calendario {year}",
        f"turismo pista calendario {year}",
        f"calendario turismo pista {year}",
    ]

    results = []

    for query in queries:
        print(
            f"Buscando en APTP: {query}"
        )

        results.extend(
            search_aptp(query)
        )

    unique = {}

    for result in results:
        unique[result["url"]] = result

    return list(
        unique.values()
    )


def score_calendar_article(
    article,
    year,
):
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

    return score


def extract_calendar_events(
    html,
    year,
):
    tables = re.findall(
        r"<table\b[^>]*>.*?</table>",
        html,
        flags=re.I | re.S,
    )

    for table in tables:

        table_text = normalize(
            clean_html(table)
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
                clean_html(cell)
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

            month = MONTHS.get(
                date_match.group(2).lower()
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

            location = "Argentina"

            location_match = re.search(
                r"[-–—]\s*(.+)$",
                cells[1],
            )

            if location_match:
                location = (
                    location_match.group(1)
                    .strip()
                )

            events.append(
                {
                    "uid": (
                        f"turismo-pista-"
                        f"{year}-"
                        f"{round_number:02d}"
                    ),
                    "round": round_number,
                    "categoria": "Argentina",
                    "campeonato": "Turismo Pista",
                    "tipo": "Carrera",
                    "fecha": date,
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

        if events:
            unique = {}

            for event in events:
                unique[event["uid"]] = event

            events = list(
                unique.values()
            )

            events.sort(
                key=lambda event: event[
                    "fecha"
                ]
            )

            return events

    return []


def find_calendar(
    articles,
    year,
):
    best = []

    for article in sorted(
        articles,
        key=lambda item: score_calendar_article(
            item,
            year,
        ),
        reverse=True,
    ):

        try:
            html = fetch_text(
                article["url"]
            )
        except Exception:
            continue

        events = extract_calendar_events(
            html,
            year,
        )

        if len(events) > len(best):
            best = events

        if len(best) >= 10:
            break

    return best


def round_queries(
    event,
    year,
):
    round_number = event[
        "round"
    ]

    location = event[
        "ubicacion"
    ]

    month_name = datetime.strptime(
        event["fecha"],
        "%Y-%m-%d",
    ).strftime("%B")

    spanish_months = {
        "January": "enero",
        "February": "febrero",
        "March": "marzo",
        "April": "abril",
        "May": "mayo",
        "June": "junio",
        "July": "julio",
        "August": "agosto",
        "September": "septiembre",
        "October": "octubre",
        "November": "noviembre",
        "December": "diciembre",
    }

    month_name = spanish_months.get(
        month_name,
        month_name,
    )

    queries = [
        f"Turismo Pista fecha {round_number} {year}",
        f"Turismo Pista {location} {year}",
        f"Turismo Pista {month_name} {year}",
        f"Turismo Pista cronograma {year}",
    ]

    return queries


def score_round_article(
    article,
    event,
    year,
):
    title = normalize(
        article["title"]
    )

    url = normalize(
        article["url"]
    )

    combined = title + " " + url

    round_number = event[
        "round"
    ]

    location = normalize(
        event["ubicacion"]
    )

    score = 0

    if "turismo pista" in combined:
        score += 20

    if str(year) in combined:
        score += 10

    if location != "argentina":
        if location in combined:
            score += 30

    if re.search(
        rf"\bfecha\s*{round_number}\b",
        combined,
    ):
        score += 40

    if re.search(
        rf"\bfecha\s*{round_number:02d}\b",
        combined,
    ):
        score += 40

    if "cronograma" in combined:
        score += 25

    if "actividades" in combined:
        score += 10

    return score


def find_round_articles(
    event,
    year,
):
    results = []

    for query in round_queries(
        event,
        year,
    ):
        print(
            f"  Buscando: {query}"
        )

        results.extend(
            search_aptp(query)
        )

    unique = {}

    for article in results:
        unique[article["url"]] = article

    articles = list(
        unique.values()
    )

    articles.sort(
        key=lambda article: score_round_article(
            article,
            event,
            year,
        ),
        reverse=True,
    )

    return articles


def extract_pdf_urls(
    html,
    article_url,
):
    """
    Extrae URLs PDF directamente del HTML,
    incluso cuando el PDF no está dentro
    de un <a> convencional.
    """

    html = unescape(
        html
    )

    patterns = [
        r'https?://[^"\']+?\.pdf(?:\?[^"\']*)?',
        r'["\']([^"\']+?\.pdf(?:\?[^"\']*)?)["\']',
    ]

    found = []

    for pattern in patterns:

        matches = re.findall(
            pattern,
            html,
            flags=re.I,
        )

        for match in matches:

            if isinstance(
                match,
                tuple,
            ):
                match = match[0]

            url = urljoin(
                article_url,
                match,
            )

            if ".pdf" not in url.lower():
                continue

            found.append(
                url
            )

    unique = []

    seen = set()

    for url in found:

        if url in seen:
            continue

        seen.add(url)

        unique.append(
            url
        )

    # Priorizar URLs que mencionen cronograma.
    unique.sort(
        key=lambda url: (
            "cronograma" not in normalize(url),
            "actividad" not in normalize(url),
        )
    )

    return unique


def extract_pdf_text(
    pdf_bytes,
):
    if PdfReader is None:
        raise RuntimeError(
            "Falta pypdf."
        )

    import io

    reader = PdfReader(
        io.BytesIO(pdf_bytes)
    )

    pages = []

    for page in reader.pages:

        text = page.extract_text()

        if text:
            pages.append(text)

    return "\n".join(
        pages
    )


def clean_pdf_text(text):
    text = text.replace(
        "\xa0",
        " ",
    )

    text = text.replace(
        "\r",
        "\n",
    )

    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    text = re.sub(
        r"\n+",
        "\n",
        text,
    )

    return text.strip()


def is_sporting_activity(
    text,
):
    normalized = normalize(
        text
    )

    allowed = [
        "entrenamiento",
        "clasificacion",
        "serie",
        "final",
    ]

    if not any(
        item in normalized
        for item in allowed
    ):
        return False

    if "turismo pista" not in normalized:
        return False

    excluded = [
        "acreditacion",
        "acreditaciones",
        "apertura de boxes",
        "cierre de boxes",
        "verificacion tecnica",
        "verificación técnica",
        "administrativa",
        "sorteo",
        "sellado",
        "combustible",
        "neumaticos",
        "neumáticos",
        "reunion",
        "reunión",
        "vuelta previa",
    ]

    for item in excluded:
        if item in normalized:
            return False

    return True


def extract_sessions(
    pdf_text,
    year,
    round_number,
    location,
):
    text = clean_pdf_text(
        pdf_text
    )

    lines = [
        line.strip()
        for line in text.split("\n")
        if line.strip()
    ]

    sessions = []

    current_date = None

    for line in lines:

        normalized_line = normalize(
            line
        )

        date_match = re.search(
            r"(\d{1,2})\s+de\s+"
            r"(enero|febrero|marzo|abril|mayo|"
            r"junio|julio|agosto|septiembre|"
            r"setiembre|octubre|noviembre|diciembre)"
            r"(?:\s+de\s+(\d{4}))?",
            normalized_line,
            flags=re.I,
        )

        if date_match:

            day = int(
                date_match.group(1)
            )

            month = MONTHS.get(
                date_match.group(2).lower()
            )

            detected_year = (
                int(date_match.group(3))
                if date_match.group(3)
                else year
            )

            if month:

                try:
                    current_date = datetime(
                        detected_year,
                        month,
                        day,
                    )
                except ValueError:
                    pass

        if not current_date:
            continue

        if not is_sporting_activity(
            line
        ):
            continue

        time_match = re.search(
            r"\b(\d{1,2}:\d{2})"
            r"(?:\s*[aA]\s*(\d{1,2}:\d{2}))?",
            line,
        )

        if not time_match:
            continue

        start_time = time_match.group(
            1
        )

        end_time = (
            time_match.group(2)
            or ""
        )

        if "entrenamiento" in normalized_line:
            activity = "Entrenamiento"

        elif "clasificacion" in normalized_line:
            activity = "Clasificación"

        elif "serie" in normalized_line:
            activity = "Serie"

        elif "final" in normalized_line:
            activity = "Final"

        else:
            continue

        class_match = re.search(
            r"turismo\s*pista\s*"
            r"(clase\s*[123])",
            normalized_line,
        )

        if not class_match:
            continue

        clase = (
            re.sub(
                r"\s+",
                " ",
                class_match.group(1),
            )
            .title()
        )

        group_match = re.search(
            r"grupo\s*([a-z])",
            normalized_line,
        )

        grupo = ""

        if group_match:
            grupo = (
                "Grupo "
                + group_match.group(1).upper()
            )

        description_parts = [
            "Turismo Pista",
            clase,
            activity,
        ]

        if grupo:
            description_parts.append(
                grupo
            )

        description = " - ".join(
            description_parts
        )

        date_string = (
            current_date.strftime(
                "%Y-%m-%d"
            )
        )

        start_datetime = (
            f"{date_string}T"
            f"{start_time}:00"
        )

        if end_time:
            end_datetime = (
                f"{date_string}T"
                f"{end_time}:00"
            )
        else:
            end_datetime = (
                f"{date_string}T"
                f"{start_time}:00"
            )

        uid = (
            f"turismo-pista-"
            f"{year}-fecha-{round_number:02d}-"
            f"{date_string}-"
            f"{start_time.replace(':', '')}-"
            f"{normalize(clase).replace(' ', '-')}-"
            f"{normalize(activity).replace(' ', '-')}"
        )

        if grupo:
            uid += (
                "-"
                + normalize(grupo)
                .replace(" ", "-")
            )

        sessions.append(
            {
                "uid": uid,
                "categoria": "Argentina",
                "campeonato": "Turismo Pista",
                "tipo": activity,
                "fecha_inicio": start_datetime,
                "fecha_fin": end_datetime,
                "ubicacion": location,
                "descripcion": description,
                "prioridad": "",
                "fecha_turismo_pista": round_number,
                "clase": clase,
                "grupo": grupo,
            }
        )

    unique = {}

    for session in sessions:
        unique[session["uid"]] = session

    sessions = list(
        unique.values()
    )

    sessions.sort(
        key=lambda event: event[
            "fecha_inicio"
        ]
    )

    return sessions


def main():

    year = current_year()

    print(
        f"Buscando Turismo Pista "
        f"para {year}..."
    )

    # -----------------------------------------
    # CALENDARIO BASE
    # -----------------------------------------

    calendar_articles = search_calendar_articles(
        year
    )

    print(
        f"Artículos de calendario: "
        f"{len(calendar_articles)}"
    )

    calendar_events = find_calendar(
        calendar_articles,
        year,
    )

    print(
        f"Fechas del campeonato: "
        f"{len(calendar_events)}"
    )

    if not calendar_events:
        print(
            "No se pudo obtener el "
            "calendario base."
        )
        return

    all_sessions = []

    # -----------------------------------------
    # CRONOGRAMAS
    # -----------------------------------------

    for event in calendar_events:

        round_number = event[
            "round"
        ]

        print()
        print(
            "======================================"
        )
        print(
            f"Fecha {round_number}: "
            f"{event['fecha']} - "
            f"{event['ubicacion']}"
        )
        print(
            "======================================"
        )

        articles = find_round_articles(
            event,
            year,
        )

        print(
            f"  Artículos candidatos: "
            f"{len(articles)}"
        )

        found_sessions = []

        for article in articles[:10]:

            print(
                f"  Analizando: "
                f"{article['title']}"
            )

            print(
                f"  {article['url']}"
            )

            try:
                html = fetch_text(
                    article["url"]
                )
            except Exception as exc:
                print(
                    f"    ERROR artículo: "
                    f"{exc}"
                )
                continue

            pdf_urls = extract_pdf_urls(
                html,
                article["url"],
            )

            print(
                f"    PDFs encontrados: "
                f"{len(pdf_urls)}"
            )

            for pdf_url in pdf_urls[:10]:

                print(
                    f"    Probando PDF: "
                    f"{pdf_url}"
                )

                try:
                    pdf_bytes = fetch(
                        pdf_url
                    )

                    pdf_text = extract_pdf_text(
                        pdf_bytes
                    )

                    sessions = extract_sessions(
                        pdf_text,
                        year,
                        round_number,
                        event["ubicacion"],
                    )

                except Exception as exc:
                    print(
                        f"      ERROR: {exc}"
                    )
                    continue

                print(
                    f"      Actividades deportivas: "
                    f"{len(sessions)}"
                )

                if len(sessions) > len(
                    found_sessions
                ):
                    found_sessions = sessions

                if len(found_sessions) >= 5:
                    break

            if found_sessions:
                break

        print(
            f"  Resultado Fecha {round_number}: "
            f"{len(found_sessions)} actividades"
        )

        all_sessions.extend(
            found_sessions
        )

    # -----------------------------------------
    # GUARDAR
    # -----------------------------------------

    unique = {}

    for session in all_sessions:
        unique[session["uid"]] = session

    all_sessions = list(
        unique.values()
    )

    all_sessions.sort(
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
            all_sessions,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(
        "======================================"
    )
    print(
        f"ACTIVIDADES DEPORTIVAS: "
        f"{len(all_sessions)}"
    )
    print(
        "======================================"
    )

    for session in all_sessions:
        print(
            f"{session['fecha_inicio']} | "
            f"{session['descripcion']} | "
            f"{session['ubicacion']}"
        )


if __name__ == "__main__":
    main()
