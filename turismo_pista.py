import json
import re
from datetime import datetime
from html import unescape
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen


BASE_URL = "https://aptpweb.com.ar/"
OUTPUT = Path("data/turismo_pista_events.json")


def current_year():
    return datetime.now().year


def fetch(url):
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
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

    html = re.sub(
        r"\s+",
        " ",
        html,
    )

    return html.strip()


def normalize(text):
    text = text.lower()

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

    return text


def month_number(name):
    months = {
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

    return months.get(
        normalize(name)
    )


def find_date(text, year):
    pattern = re.compile(
        r"(\d{1,2})\s+"
        r"(enero|febrero|marzo|abril|mayo|junio|"
        r"julio|agosto|septiembre|setiembre|octubre|"
        r"noviembre|diciembre)"
        r"(?:\s+de)?\s+"
        r"(\d{4})",
        re.I,
    )

    matches = list(
        pattern.finditer(text)
    )

    for match in matches:
        event_year = int(
            match.group(3)
        )

        if event_year != year:
            continue

        day = int(
            match.group(1)
        )

        month = month_number(
            match.group(2)
        )

        if not month:
            continue

        return (
            f"{event_year:04d}-"
            f"{month:02d}-"
            f"{day:02d}"
        )

    return None


def find_round(text):
    patterns = [
        r"(\d{1,2})[°º]?\s*fecha",
        r"fecha\s*(\d{1,2})",
        r"carrera\s*(\d{1,2})",
    ]

    normalized = normalize(text)

    for pattern in patterns:
        match = re.search(
            pattern,
            normalized,
            re.I,
        )

        if match:
            return int(
                match.group(1)
            )

    return None


def find_location(text):
    locations = [
        "La Plata",
        "Toay",
        "Concordia",
        "San Jorge",
        "Rosario",
        "Río Cuarto",
        "Rio Cuarto",
        "San Nicolás",
        "San Nicolas",
        "Termas de Río Hondo",
        "Termas de Rio Hondo",
        "Concepción del Uruguay",
        "Concepcion del Uruguay",
        "Rafaela",
    ]

    normalized = normalize(text)

    for location in locations:
        if normalize(location) in normalized:
            return location

    return "Argentina"


def find_calendar_links(html, year):
    links = []

    pattern = re.compile(
        r'href=["\']([^"\']+)["\']',
        re.I,
    )

    for match in pattern.finditer(html):
        href = match.group(1)

        full_url = urljoin(
            BASE_URL,
            href,
        )

        normalized_url = normalize(
            full_url
        )

        if (
            "calendario" in normalized_url
            and str(year) in normalized_url
        ):
            links.append(
                full_url
            )

    return list(
        dict.fromkeys(links)
    )


def extract_calendar_article(
    url,
    year,
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
        return []

    text = clean_html(
        html
    )

    if "turismo pista" not in normalize(
        text
    ):
        return []

    events = []

    round_pattern = re.compile(
        r"(\d{1,2})[°º]?\s*fecha",
        re.I,
    )

    matches = list(
        round_pattern.finditer(
            normalize(text)
        )
    )

    for index, match in enumerate(
        matches
    ):
        round_number = int(
            match.group(1)
        )

        start = match.start()

        if index + 1 < len(matches):
            end = matches[
                index + 1
            ].start()
        else:
            end = min(
                len(text),
                start + 2500,
            )

        fragment = text[
            start:end
        ]

        date = find_date(
            fragment,
            year,
        )

        if not date:
            continue

        location = find_location(
            fragment
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

    # Página oficial de calendario del año.
    calendar_url = (
        f"https://aptpweb.com.ar/"
        f"calendario-{year}/"
    )

    candidates = [
        calendar_url,
        (
            f"https://aptpweb.com.ar/"
            f"recorrido-completo-para-el-"
            f"calendario-{year}/"
        ),
        (
            f"https://aptpweb.com.ar/"
            f"turismo-pista-y-actc-"
            f"presentaron-el-calendario-"
            f"{year}-en-la-tv-publica/"
        ),
    ]

    events = []

    for url in candidates:
        try:
            found = extract_calendar_article(
                url,
                year,
            )

            events.extend(
                found
            )

        except Exception as exc:
            print(
                f"ERROR procesando {url}: "
                f"{exc}"
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
            "Pista disponible todavía para "
            f"{year}."
        )


if __name__ == "__main__":
    main()
