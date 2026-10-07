import json
import re
from datetime import datetime
from html import unescape
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


OUTPUT = Path("data/turismo_pista_events.json")

BASE_URL = "https://aptpweb.com.ar"
WP_SEARCH_URL = BASE_URL + "/wp-json/wp/v2/search"

# PDF oficial de prueba:
# Fecha 5 - Rosario - 2026
TEST_PDF_URL = (
    "https://aptpweb.com.ar/wp-content/uploads/2026/06/"
    "cronograma_fecha_5_aptp_.pdf"
)

TEST_YEAR = 2026
TEST_ROUND = 5
TEST_LOCATION = "Rosario"


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


def extract_pdf_text(pdf_bytes):
    if PdfReader is None:
        raise RuntimeError(
            "Falta instalar pypdf."
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

    return "\n".join(pages)


def clean_pdf_text(text):
    text = text.replace(
        "\xa0",
        " ",
    )

    text = text.replace(
        "\r",
        "\n",
    )

    # Unificar espacios, pero conservar saltos
    # de línea porque ayudan a separar sesiones.
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


def is_sporting_activity(text):
    normalized = normalize(text)

    keywords = [
        "entrenamiento",
        "clasificacion",
        "clasificación",
        "serie",
        "final",
    ]

    return any(
        keyword in normalized
        for keyword in keywords
    )


def is_turismo_pista_class(text):
    normalized = normalize(text)

    return (
        "turismo pista clase 1" in normalized
        or "turismo pista clase 2" in normalized
        or "turismo pista clase 3" in normalized
    )


def extract_date_from_line(line, year):
    normalized = normalize(line)

    # Ejemplo:
    # VIERNES 12 DE JUNIO DE 2026
    pattern = re.search(
        r"(\d{1,2})\s+de\s+"
        r"(enero|febrero|marzo|abril|mayo|"
        r"junio|julio|agosto|septiembre|"
        r"setiembre|octubre|noviembre|diciembre)"
        r"(?:\s+de\s+(\d{4}))?",
        normalized,
        re.I,
    )

    if not pattern:
        return None

    day = int(
        pattern.group(1)
    )

    month = MONTHS.get(
        pattern.group(2)
    )

    detected_year = pattern.group(3)

    if detected_year:
        year = int(
            detected_year
        )

    if not month:
        return None

    try:
        return datetime(
            year,
            month,
            day,
        )
    except ValueError:
        return None


def parse_time_range(text):
    """
    Acepta:
    10:50 a 11:05
    14:30 a 14:40
    17:30
    """

    text = text.strip()

    match = re.match(
        r"(?P<start>\d{1,2}:\d{2})"
        r"(?:\s*[aA]\s*"
        r"(?P<end>\d{1,2}:\d{2}))?",
        text,
    )

    if not match:
        return None

    return (
        match.group("start"),
        match.group("end"),
    )


def extract_sessions(pdf_text):
    """
    Extrae actividades deportivas del PDF.

    En esta primera versión procesamos el
    cronograma oficial de prueba y mostramos
    las sesiones detectadas.
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

        detected_date = extract_date_from_line(
            line,
            TEST_YEAR,
        )

        if detected_date:
            current_date = detected_date

        if not current_date:
            continue

        if not is_sporting_activity(
            line
        ):
            continue

        if not is_turismo_pista_class(
            line
        ):
            continue

        # Buscar horario al comienzo de la línea.
        time_match = re.match(
            r"(?P<time>\d{1,2}:\d{2}"
            r"(?:\s*[aA]\s*\d{1,2}:\d{2})?)",
            line,
        )

        if not time_match:
            continue

        time_text = time_match.group(
            "time"
        )

        parsed_time = parse_time_range(
            time_text
        )

        if not parsed_time:
            continue

        start_time, end_time = (
            parsed_time
        )

        normalized = normalize(
            line
        )

        if "entrenamiento" in normalized:
            activity_type = "Entrenamiento"

        elif "clasificacion" in normalized:
            activity_type = "Clasificación"

        elif "serie" in normalized:
            activity_type = "Serie"

        elif "final" in normalized:
            activity_type = "Final"

        else:
            continue

        class_match = re.search(
            r"turismo pista "
            r"(clase [123])",
            normalized,
            re.I,
        )

        if class_match:
            category_class = (
                class_match.group(1)
                .title()
            )
        else:
            category_class = ""

        group_match = re.search(
            r"grupo\s+([a-z])",
            normalized,
            re.I,
        )

        group = ""

        if group_match:
            group = (
                "Grupo "
                + group_match.group(1).upper()
            )

        sessions.append(
            {
                "fecha": current_date.strftime(
                    "%Y-%m-%d"
                ),
                "hora_inicio": start_time,
                "hora_fin": end_time or "",
                "actividad": activity_type,
                "clase": category_class,
                "grupo": group,
                "texto_original": line,
            }
        )

    return sessions


def main():

    print(
        "======================================"
    )
    print(
        "PRUEBA CRONOGRAMA TURISMO PISTA"
    )
    print(
        "======================================"
    )
    print()

    print(
        f"Fecha de prueba: "
        f"{TEST_ROUND}"
    )

    print(
        f"Circuito: "
        f"{TEST_LOCATION}"
    )

    print()

    print(
        "Descargando PDF oficial..."
    )

    print(TEST_PDF_URL)

    try:
        pdf_bytes = fetch(
            TEST_PDF_URL
        )
    except Exception as exc:
        print()
        print(
            f"ERROR descargando PDF: "
            f"{exc}"
        )
        return

    print(
        f"PDF descargado: "
        f"{len(pdf_bytes)} bytes"
    )

    print()

    if PdfReader is None:
        print(
            "ERROR: falta pypdf."
        )
        print(
            "Agregá pypdf a requirements.txt"
        )
        return

    try:
        pdf_text = extract_pdf_text(
            pdf_bytes
        )
    except Exception as exc:
        print()
        print(
            f"ERROR leyendo PDF: "
            f"{exc}"
        )
        return

    print(
        f"Texto extraído: "
        f"{len(pdf_text)} caracteres"
    )

    print()

    sessions = extract_sessions(
        pdf_text
    )

    print(
        f"Actividades deportivas "
        f"detectadas: {len(sessions)}"
    )

    print()

    for number, session in enumerate(
        sessions,
        start=1,
    ):
        print(
            f"{number:02d}. "
            f"{session['fecha']} "
            f"{session['hora_inicio']}"
            f"{' - ' + session['hora_fin'] if session['hora_fin'] else ''}"
            f" | "
            f"{session['actividad']}"
            f" | "
            f"{session['clase']}"
            f" | "
            f"{session['grupo']}"
        )

    print()

    print(
        "======================================"
    )
    print(
        "FIN DE LA PRUEBA"
    )
    print(
        "======================================"
    )


if __name__ == "__main__":
    main()
