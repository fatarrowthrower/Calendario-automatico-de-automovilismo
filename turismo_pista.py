import json
import re
from datetime import datetime
from html import unescape
from pathlib import Path
from urllib.request import Request, urlopen


OUTPUT = Path("data/turismo_pista_events.json")

BASE_URL = "https://aptpweb.com.ar"

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
                "(Windows NT 10.0; Win64; x64)"
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
        r"[ \t]+",
        " ",
        html,
    )

    html = re.sub(
        r"\n\s+",
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
    }

    for old, new in replacements.items():
        text = text.replace(
            old,
            new,
        )

    return text.lower()


def parse_date(day, month_name, year):
    month = MONTHS.get(
        normalize(month_name)
    )

    if not month:
        return None

    return (
        f"{year:04d}-"
        f"{month:02d}-"
        f"{int(day):02d}"
    )


def find_calendar_block(text, year):
    """
    Busca específicamente el bloque CALENDARIO YYYY.
    Evita tomar fechas de noticias, resultados
    o publicaciones secundarias de la página.
    """

    normalized = normalize(text)

    marker = f"calendario {year}"

    start = normalized.find(
        marker
    )

    if start == -1:
        return None

    block = text[start:]

    # El calendario 2026 tiene 10 fechas.
    # Cortamos cuando aparece una sección claramente posterior.
    stop_markers = [
        "turismo carretera 2000",
        "noticias",
        "campeonato",
        "resultados",
        "contacto",
    ]

    normalized_block = normalize(
        block
    )

    positions = []

    for marker in stop_markers:
        position = normalized_block.find(
            marker,
            100,
        )

        if position != -1:
            positions.append(
                position
            )

    if positions:
        block = block[
            :min(positions)
        ]

    return block


def extract_events_from_block(
    block,
    year,
):
    events = []

    """
    APTP publica actualmente líneas con formatos como:

    1° FECHA | 1° febrero – La Plata
    2° FECHA | 1° marzo
    3° FECHA | 12 de abril
    ...

    La sede puede aparecer solamente en algunas
    líneas. En ese caso conservamos la última sede
    conocida si corresponde.
    """

    pattern = re.compile(
        r"(\d{1,2})\s*[°º]?\s*"
        r"FECHA"
        r"\s*"
        r"(?:\||:|-)?"
        r"\s*"
        r"(\d{1,2})"
        r"(?:\s*de)?"
        r"\s+"
        r"(enero|febrero|marzo|abril|mayo|junio|"
        r"julio|agosto|septiembre|setiembre|octubre|"
        r"noviembre|diciembre)"
        r"(?:\s+de\s+\d{4})?"
        r"(?:\s*[-–—]\s*([^|\n]+))?",
        re.IGNORECASE,
    )

    matches = list(
        pattern.finditer(block)
    )

    if not matches:
        return []

    for match in matches:
        round_number = int(
            match.group(1)
        )

        day = int(
            match.group(2)
        )

        month_name = match.group(3)

        location = (
            match.group(4) or ""
        ).strip()

        location = re.sub(
            r"\s+",
            " ",
            location,
        )

        # Evitamos que una frase posterior
        # termine siendo tomada como circuito.
        if len(location) > 80:
            location = location[:80]

        date = parse_date(
            day,
            month_name,
            year,
        )

        if not date:
            continue

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
                "ubicacion": location
                if location
                else "Argentina",
                "descripcion": (
                    f"Turismo Pista - "
                    f"Fecha {round_number}"
                ),
                "prioridad": "",
            }
        )

    return events


def candidate_urls(year):
    return [
        (
            f"{BASE_URL}/"
            f"turismo-pista-y-actc-presentaron-"
            f"el-calendario-{year}-en-la-tv-publica/"
        ),
        (
            f"{BASE_URL}/"
            f"recorrido-completo-para-el-"
            f"calendario-{year}/"
        ),
        (
            f"{BASE_URL}/"
            f"calendario-{year}/"
        ),
    ]


def main():
    year = current_year()

    print(
        f"Buscando Turismo Pista "
        f"para {year}..."
    )

    all_events = []

    for url in candidate_urls(year):
        print(
            f"Consultando: {url}"
        )

        try:
            html = fetch(url)

        except Exception as exc:
            print(
                f"  No disponible: {exc}"
            )
            continue

        text = clean_html(
            html
        )

        block = find_calendar_block(
            text,
            year,
        )

        if not block:
            print(
                "  No se encontró el "
                f"bloque CALENDARIO {year}."
            )
            continue

        events = extract_events_from_block(
            block,
            year,
        )

        print(
            f"  Fechas encontradas: "
            f"{len(events)}"
        )

        all_events.extend(
            events
        )

        # Si encontramos un calendario
        # completo, no necesitamos seguir
        # usando otras fuentes.
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
            "No hay calendario de Turismo "
            f"Pista disponible para {year}."
        )


if __name__ == "__main__":
    main()
