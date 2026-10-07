import json
import re
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

ACTC_SOURCES = {
    "TC": "https://actc.org.ar/tc/calendario",
    "TC Pista": "https://actc.org.ar/tcp/calendario",
    "TC Pick Up": "https://actc.org.ar/tcpk/calendario",
}

OUTPUT = Path("data/actc_events.json")


def fetch(url):
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
    )
    with urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="ignore")


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


def parse_date(text):
    months = {
        "ene": 1,
        "feb": 2,
        "mar": 3,
        "abr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "ago": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dic": 12,
    }

    match = re.search(
        r"(\d{1,2})\s+([a-záéíóú]+)\s+(\d{4})",
        text.lower(),
    )

    if not match:
        return None

    day = int(match.group(1))
    month_name = match.group(2)[:3]
    year = int(match.group(3))

    month = months.get(month_name)

    if not month:
        return None

    return f"{year:04d}-{month:02d}-{day:02d}"


def parse_calendar(html, championship):
    text = clean(re.sub(r"<[^>]+>", " ", html))

    events = []

    pattern = re.compile(
        r"Fecha\s+(\d+).*?"
        r"(\d{1,2}\s+[A-Za-zÁÉÍÓÚáéíóú]+\s+\d{4})",
        re.IGNORECASE,
    )

    matches = list(pattern.finditer(text))

    for match in matches:
        round_number = int(match.group(1))
        date_text = match.group(2)

        date = parse_date(date_text)

        if not date:
            continue

        start = match.end()
        fragment = text[start:start + 250]

        fragment = re.sub(
            r"\s+",
            " ",
            fragment,
        ).strip()

        location = fragment.split("Fecha")[0].strip()

        if not location:
            location = "Argentina"

        location = location[:100]

        events.append(
            {
                "uid": f"actc-{championship.lower().replace(' ', '-')}-2026-{round_number:02d}",
                "categoria": "Argentina",
                "campeonato": championship,
                "tipo": "Carrera",
                "fecha_inicio": f"{date}T12:00:00",
                "fecha_fin": f"{date}T23:59:00",
                "ubicacion": location,
                "descripcion": f"{championship} - Fecha {round_number}",
                "imperdible": championship in [
                    "TC",
                    "TC Pista",
                    "TC Pick Up",
                ],
            }
        )

    return events


def main():
    all_events = []

    for championship, url in ACTC_SOURCES.items():
        print(f"Consultando ACTC: {championship}")

        try:
            html = fetch(url)
            events = parse_calendar(html, championship)

            print(f"  Encontrados: {len(events)}")

            all_events.extend(events)

        except Exception as exc:
            print(f"  ERROR: {exc}")

    # Eliminar duplicados por UID
    unique = {}

    for event in all_events:
        unique[event["uid"]] = event

    events = list(unique.values())

    events.sort(key=lambda x: x["fecha_inicio"])

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    OUTPUT.write_text(
        json.dumps(
            events,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print(f"ACTC: {len(events)} eventos guardados en {OUTPUT}")


if __name__ == "__main__":
    main()
