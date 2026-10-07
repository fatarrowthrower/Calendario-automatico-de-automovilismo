import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

URL = "https://aptpweb.com.ar/resultados-clase-1/"
OUTPUT = Path("data/turismo_pista_events.json")

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
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def fetch(url):
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    with urlopen(req, timeout=30) as response:
        return response.read().decode(
            "utf-8",
            errors="ignore"
        )


def clean(text):
    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


def parse_date(text):
    match = re.search(
        r"(\d{1,2}).*?"
        r"(enero|febrero|marzo|abril|mayo|junio|"
        r"julio|agosto|septiembre|octubre|noviembre|diciembre)",
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    day = int(match.group(1))
    month = MONTHS[match.group(2).lower()]

    return f"2026-{month:02d}-{day:02d}"


def parse_calendar(html):
    text = clean(
        re.sub(
            r"<[^>]+>",
            " ",
            html
        )
    )

    events = []

    pattern = re.compile(
        r"Fecha\s+(\d+)\s*-\s*"
        r"([^F]+?)"
        r"(?=Fecha\s+\d+\s*-|$)",
        re.IGNORECASE
    )

    matches = pattern.findall(text)

    for round_number, fragment in matches:

        round_number = int(round_number)

        # Evitamos fechas de otros años.
        if round_number > 10:
            continue

        fragment = clean(fragment)

        date = parse_date(fragment)

        if not date:
            continue

        # Sedes conocidas publicadas por APTP.
        locations = [
            "La Plata",
            "Toay",
            "Concordia",
            "San Jorge",
            "Rosario",
            "Río Cuarto",
            "San Nicolás",
            "Termas de Río Hondo",
            "Concepción del Uruguay",
            "Rafaela",
        ]

        location = "Argentina"

        for candidate in locations:
            if candidate.lower() in fragment.lower():
                location = candidate
                break

        events.append(
            {
                "uid": (
                    f"turismo-pista-2026-"
                    f"{round_number:02d}"
                ),
                "fecha_inicio": (
                    f"{date}T12:00:00"
                ),
                "fecha_fin": (
                    f"{date}T23:59:00"
                ),
                "evento": (
                    f"Turismo Pista - "
                    f"Fecha {round_number}"
                ),
                "categoria": "Argentina",
                "campeonato": "Turismo Pista",
                "tipo": "Carrera",
                "prioridad": "Normal",
                "ubicacion": location,
                "descripcion": (
                    f"Turismo Pista - "
                    f"Fecha {round_number}"
                ),
            }
        )

    return events


def main():

    print(
        "Consultando Turismo Pista / APTP..."
    )

    html = fetch(URL)

    print(f"HTML recibido: {len(html)} caracteres")
    print(html[:2000])
    
    events = parse_calendar(html)

    if not events:
        raise SystemExit(
            "ERROR: no se encontraron fechas "
            "de Turismo Pista."
        )

    # Eliminar duplicados.
    unique = {}

    for event in events:
        unique[event["uid"]] = event

    events = list(unique.values())

    events.sort(
        key=lambda event: event["fecha_inicio"]
    )

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    OUTPUT.write_text(
        json.dumps(
            events,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print(
        f"Turismo Pista: {len(events)} "
        f"fechas encontradas."
    )

    for event in events:
        print(
            f'  Fecha {event["uid"][-2:]}: '
            f'{event["fecha_inicio"][:10]} - '
            f'{event["ubicacion"]}'
        )

    print(
        f"Guardado en {OUTPUT}"
    )


if __name__ == "__main__":
    main()
