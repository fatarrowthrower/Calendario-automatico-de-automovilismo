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
            + "&per_page=30"
        )

        print(
            f"Buscando en APTP: {query}"
        )

        try:
            data = json.loads(
                fetch_text(url)
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

    return score


def extract_calendar_events(
    html,
    year,
):
    """
    Extrae las 10 fechas de la tabla
    CALENDARIO YYYY.
    """

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

        if len(events) >= 1:
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


def find_article_for_round(
    articles,
    round_number,
    location,
    year,
):
    """
    Busca una nota de APTP relacionada
    con una fecha concreta.
    """

    candidates = []

    location_normalized = normalize(
        location
    )

    for article in articles:

        title = normalize(
            article["title"]
        )

        combined = normalize(
            article["title"]
            + " "
            + article["url"]
        )

        score = 0

        if str(year) in combined:
            score += 10

        if "turismo pista" in combined:
            score += 10

        if location_normalized != "argentina":
            if location_normalized in combined:
                score += 30

        # Buscar expresiones como:
        # fecha 5
        # quinta fecha
        # carrera 5
        if re.search(
            rf"\bfecha\s+{round_number}\b",
            title,
        ):
            score += 25

        if re.search(
            rf"\bcarrera\s+{round_number}\b",
            title,
        ):
            score += 20

        if score > 0:
            candidates.append(
                (
                    score,
                    article,
                )
            )

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    if candidates:
        return candidates[0][1]

    return None


def find_pdf_links(
    html,
    article_url,
):
    """
    Busca PDFs enlazados desde una nota APTP.

    Prioriza enlaces cuyo texto o URL
    mencione cronograma.
    """

    links = re.findall(
        r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>'
        r"(.*?)"
        r"</a>",
        html,
        flags=re.I | re.S,
    )

    candidates = []

    for href, anchor in links:

        full_url = urljoin(
            article_url,
            unescape(href),
        )

        anchor_text = clean_html(
            anchor
        )

        combined = normalize(
            anchor_text
            + " "
            + full_url
        )

        if ".pdf" not in combined:
            continue

        score = 0

        if "cronograma" in combined:
            score += 50

        if "cronograma oficial" in combined:
            score += 20

        if "actividad" in combined:
            score += 10

        if "carpeta" in combined:
            score += 5

        candidates.append(
            (
                score,
                full_url,
            )
        )

    candidates.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    unique = []

    seen = set()

    for score, url in candidates:

        if url in seen:
            continue

        seen.add(url)

        unique.append(
            (
                score,
                url,
            )
        )

    return unique


def extract_pdf_text(
    pdf_bytes,
):
    if PdfReader is None:
        raise RuntimeError(
            "Falta pypdf. "
            "Agregalo a requirements.txt."
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


def sporting_activity(text):
    normalized = normalize(
        text
    )

    # Solo queremos actividad deportiva.
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

    # Asegurarnos de que pertenece
    # al Turismo Pista.
    if "turismo pista" not in normalized:
        return False

    # Excluir actividades que no queremos.
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
        "notas en grilla",
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
    """
    Extrae entrenamientos,
    clasificaciones, series y finales.

    Esta función es deliberadamente
    conservadora: si una línea no tiene
    una hora clara, no se convierte en
    evento.
    """

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

        date_match = re.search(
            r"(\d{1,2})\s+de\s+"
            r"(enero|febrero|marzo|abril|mayo|"
            r"junio|julio|agosto|septiembre|"
            r"setiembre|octubre|noviembre|diciembre)"
            r"(?:\s+de\s+(\d{4}))?",
            normalize(line),
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

        if not sporting_activity(
            line
        ):
            continue

        # Buscar hora al comienzo.
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

        end_time = time_match.group(
            2
        ) or ""

        normalized = normalize(
            line
        )

        if "entrenamiento" in normalized:
            activity = "Entrenamiento"

        elif "clasificacion" in normalized:
            activity = "Clasificación"

        elif "serie" in normalized:
            activity = "Serie"

        elif "final" in normalized:
            activity = "Final"

        else:
            continue

        class_match = re.search(
            r"turismo pista\s+"
            r"(clase\s+[123])",
            normalized,
        )

        if not class_match:
            continue

        clase = (
            class_match.group(1)
            .title()
        )

        group_match = re.search(
            r"grupo\s+([a-z])",
            normalized,
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

        start_datetime = (
            f"{current_date.strftime('%Y-%m-%d')}"
            f"T{start_time}:00"
        )

        if end_time:
            end_datetime = (
                f"{current_date.strftime('%Y-%m-%d')}"
                f"T{end_time}:00"
            )
        else:
            end_datetime = (
                f"{current_date.strftime('%Y-%m-%d')}"
                f"T{start_time}:00"
            )

        uid_base = (
            f"turismo-pista-"
            f"{year}-"
            f"fecha-{round_number:02d}-"
            f"{current_date.strftime('%Y%m%d')}-"
            f"{start_time.replace(':', '')}-"
            f"{normalize(clase).replace(' ', '-')}-"
            f"{normalize(activity).replace(' ', '-')}"
        )

        if grupo:
            uid_base += (
                "-"
                + normalize(grupo)
                .replace(" ", "-")
            )

        sessions.append(
            {
                "uid": uid_base,
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

    # Deduplicar.
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

    articles = search_aptp(
        year
    )

    print(
        f"Artículos candidatos: "
        f"{len(articles)}"
    )

    if not articles:
        print(
            "No se encontraron artículos "
            "de Turismo Pista."
        )
        return

    # -------------------------------------------------
    # 1. Encontrar el artículo que contiene
    #    el calendario general.
    # -------------------------------------------------

    calendar_events = []

    for article in sorted(
        articles,
        key=lambda item: score_article(
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

        if len(events) > len(
            calendar_events
        ):
            calendar_events = events

        if len(calendar_events) >= 10:
            break

    print()
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

    # -------------------------------------------------
    # 2. Para cada fecha buscar su cronograma.
    # -------------------------------------------------

    all_sessions = []

    for event in calendar_events:

        round_number = event[
            "round"
        ]

        location = event[
            "ubicacion"
        ]

        print()
        print(
            "--------------------------------------"
        )
        print(
            f"Fecha {round_number}: "
            f"{event['fecha']} - "
            f"{location}"
        )

        article = find_article_for_round(
            articles,
            round_number,
            location,
            year,
        )

        if not article:
            print(
                "  No se encontró artículo "
                "específico."
            )
            continue

        print(
            f"  Artículo: "
            f"{article['title']}"
        )

        try:
            article_html = fetch_text(
                article["url"]
            )
        except Exception as exc:
            print(
                f"  ERROR artículo: {exc}"
            )
            continue

        pdfs = find_pdf_links(
            article_html,
            article["url"],
        )

        print(
            f"  PDFs candidatos: "
            f"{len(pdfs)}"
        )

        if not pdfs:
            print(
                "  Todavía no hay "
                "cronograma PDF detectable."
            )
            continue

        found_sessions = []

        for score, pdf_url in pdfs:

            print(
                f"  Probando PDF: "
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
                    location,
                )

            except Exception as exc:
                print(
                    f"    ERROR PDF: {exc}"
                )
                continue

            print(
                f"    Actividades deportivas: "
                f"{len(sessions)}"
            )

            if len(sessions) > len(
                found_sessions
            ):
                found_sessions = sessions

            # Un cronograma válido normalmente
            # tiene varias actividades.
            if len(found_sessions) >= 5:
                break

        all_sessions.extend(
            found_sessions
        )

    # -------------------------------------------------
    # 3. Guardar resultado.
    # -------------------------------------------------

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
        f"Actividades deportivas encontradas: "
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
