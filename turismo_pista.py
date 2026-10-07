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
            "User-Agent": "Mozilla/5.0"
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
        r"<script.*?</script>",
        " ",
        html,
        flags=re.I | re.S,
    )

    html = re.sub(
        r"<style.*?</style>",
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
        "º": "°",
    }

    for old, new in replacements.items():
        text = text.replace(
            old,
            new,
        )

    return text.lower()


def month_number(name):
    return MONTHS.get(
        normalize(name)
    )


def extract_events(text, year):
    """
    Busca directamente estructuras del tipo:

    1° FECHA | 1° febrero – La Plata
    2° FECHA | 1° marzo
    3° FECHA | 12 de abril
    """

    normalized = normalize(text)

    pattern = re.compile(
        r"(\d{1,2})\s*°?\s*fecha"
        r".{0,80}?"
        r"(\d{1,2})\s*°?\s*"
        r"(?:de\s+)?"
        r"(enero|febrero|marzo|abril|mayo|junio|"
        r"julio|agosto|septiembre|setiembre|octubre|"
        r"noviembre|diciembre)"
        r"(?:.{0,100}?"
        r"[-–—]\s*"
        r"([A-Za-zÁÉÍÓÚáéíóúÑñ(). ]+))?",
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

        month = month_number(
            month_name
        )

        if not month:
            continue

        location = (
            match.group(4) or ""
        ).strip()

        location = re.sub(
            r"\s+",
            " ",
            location,
        )

        # Limpiar restos típicos del HTML/texto.
        location = re.sub(
            r"\s+(calendario|fecha|carrera).*",
            "",
            location,
            flags=re.I,
        ).strip()

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


def get_calendar_urls(year):
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
    ]


def main():
    year = current_year()

    print(
        f"Buscando Turismo Pista "
        f"para {year}..."
    )

    all_events = []

    for url in get_calendar_urls(
        year
    ):

        print(
            f"Consultando: {url}"
        )

        try:
            html = fetch(url)

        except Exception as exc:
            print(
                f"ERROR: {exc}"
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
            "No se encontraron fechas "
            f"de Turismo Pista para {year}."
        )


if __name__ == "__main__":
    main()
