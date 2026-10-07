import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

URL = "https://aptpweb.com.ar/calendario-2026/"
OUTPUT = Path("data/turismo_pista_events.json")


def fetch(url):
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
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


def parse_calendar(html):
    text = clean(
        re.sub(
            r"<[^>]+>",
            " ",
            html
        )
    )

    events = []

    # Buscamos fechas del tipo:
    # 1 de febrero
    # 22 de marzo
    # 19 de abril
    pattern = re.compile(
        r"(\d{1,2})\s+de\s+"
        r"(enero|febrero|marzo|abril|mayo|junio|"
        r"julio|agosto|septiembre|octubre|noviembre|diciembre)",
        re.IGNORECASE,
    )

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
        "octubre": 10,
        "noviembre": 11,
        "diciembre": 12,
    }

    matches = list(pattern.finditer(text))

    for index, match in enumerate(matches, start=1):

        day = int(match.group(1))
        month_name = match.group(2).lower()
        month = months[month_name]

        date = (
            f"2026-{month:02d}-{day:02d}"
        )

        fragment = text[
            max(0, match.start() - 100):
            match.end() + 200
        ]

        location = "Argentina"

        # Intentamos encontrar una ciudad/circuito
        # cercana a la fecha publicada.
        known_locations = [
            "La Plata",
            "Concepción del Uruguay",
            "San Nicolás",
            "Rosario",
            "Paraná",
            "Alta Gracia",
            "Rafaela",
            "Buenos Aires",
            "Olavarría",
            "San Jorge",
            "Toay",
            "Termas de Río Hondo",
            "9 de Julio",
        ]

        for known in known_locations:
            if known.lower() in fragment.lower():
                location = known
                break

        events.append(
            {
                "uid": (
                    f"turismo-pista-2026-"
                    f"{index:02d}"
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
                "evento": (
                    f"Turismo Pista - "
                    f"Fecha {index}"
                ),
                "prioridad": "Normal",
                "ubicacion": location,
                "descripcion": (
                    f"Turismo Pista - "
                    f"Fecha {index}"
                ),
            }
        )

    return events


def main():

    print(
        "Consultando Turismo Pista / APTP..."
    )

    html = fetch(URL)

    events = parse_calendar(html)

    if not events:
        raise SystemExit(
            "ERROR: no se encontraron fechas "
            "de Turismo Pista."
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

    print(
        f"Guardado en {OUTPUT}"
    )


if __name__ == "__main__":
    main()
