import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


YEAR = datetime.now().year

OUTPUT = Path("data/actc_events.json")

CATEGORIES = {
    "TC": {
        "page": "https://actc.org.ar/tc",
        "calendar": "https://actc.org.ar/tc/calendario",
        "code": "TC",
    },
    "TC Pista": {
        "page": "https://actc.org.ar/tcp",
        "calendar": "https://actc.org.ar/tcp/calendario",
        "code": "TCP",
    },
    "TC Pick Up": {
        "page": "https://actc.org.ar/tcpk",
        "calendar": "https://actc.org.ar/tcpk/calendario",
        "code": "TCPK",
    },
}


MONTHS = {
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


def clean(text):
    return re.sub(
        r"\s+",
        " ",
        text or "",
    ).strip()


def slugify(text):
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
        "ñ": "n",
    }

    text = text.lower()

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(
        r"[^a-z0-9]+",
        "-",
        text,
    )

    return text.strip("-")


def parse_date(text):
    match = re.search(
        r"\b(\d{1,2})\s+"
        r"(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)"
        r"\s+(\d{4})\b",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    day = int(match.group(1))
    month = MONTHS.get(
        match.group(2).lower()
    )
    year = int(match.group(3))

    if not month:
        return None

    try:
        return datetime(
            year,
            month,
            day,
        ).date()
    except ValueError:
        return None


def parse_numeric_date(text):
    match = re.search(
        r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
        text,
    )

    if not match:
        return None

    try:
        return datetime(
            int(match.group(3)),
            int(match.group(2)),
            int(match.group(1)),
        ).date()
    except ValueError:
        return None


def parse_calendar_page(
    page,
    championship,
):
    print(
        f"  Leyendo calendario dinámico: "
        f"{page.url}"
    )

    text = page.locator(
        "body"
    ).inner_text()

    lines = [
        clean(line)
        for line in text.splitlines()
        if clean(line)
    ]

    events = []

    current_round = None
    current_location = "Argentina"

    for index, line in enumerate(lines):

        round_match = re.search(
            r"Fecha\s+(\d+)",
            line,
            re.IGNORECASE,
        )

        if round_match:
            current_round = int(
                round_match.group(1)
            )

            location_match = re.search(
                r"Fecha\s+\d+\s*[—\-:]\s*(.+)",
                line,
                re.IGNORECASE,
            )

            if location_match:
                current_location = clean(
                    location_match.group(1)
                )

        date = parse_date(
            line
        )

        if not date:
            date = parse_numeric_date(
                line
            )

        if not date:
            continue

        if date.year != YEAR:
            continue

        # Si la fecha está en la línea pero
        # "Fecha N" está unas líneas antes,
        # buscamos hacia atrás.
        if current_round is None:
            for previous in reversed(
                lines[
                    max(0, index - 8):index
                ]
            ):
                previous_match = re.search(
                    r"Fecha\s+(\d+)",
                    previous,
                    re.IGNORECASE,
                )

                if previous_match:
                    current_round = int(
                        previous_match.group(1)
                    )
                    break

        if current_round is None:
            continue

        events.append(
            {
                "round": current_round,
                "date": date,
                "location": current_location,
            }
        )

    unique = {}

    for event in events:
        unique[
            (
                event["round"],
                event["date"],
            )
        ] = event

    result = list(
        unique.values()
    )

    result.sort(
        key=lambda item: (
            item["date"],
            item["round"],
        )
    )

    print(
        f"  Fechas encontradas: "
        f"{len(result)}"
    )

    return result


def discover_cronogram_links(page):
    links = []

    anchors = page.locator(
        "a"
    )

    count = anchors.count()

    for index in range(count):

        anchor = anchors.nth(
            index
        )

        try:
            href = anchor.get_attribute(
                "href"
            )

            text = clean(
                anchor.inner_text()
            )
        except Exception:
            continue

        if not href:
            continue

        full_url = urljoin(
            page.url,
            href,
        )

        lower_url = full_url.lower()
        lower_text = text.lower()

        if (
            "/cronogramas/" in lower_url
            or "cronograma" in lower_text
        ):
            if full_url not in links:
                links.append(
                    full_url
                )

    return links


def classify_session(text):
    lower = text.lower()

    if (
        "entrenamiento" in lower
        or "práctica" in lower
        or "practica" in lower
    ):
        return "Entrenamiento"

    if (
        "clasificación" in lower
        or "clasificacion" in lower
    ):
        return "Clasificación"

    if "serie" in lower:
        return "Serie"

    if re.search(
        r"\bfinal\b",
        lower,
    ):
        return "Carrera"

    return None


def category_matches(
    text,
    code,
):
    upper = text.upper()

    if code == "TC":
        return (
            "TCPK" not in upper
            and "TCP" not in upper
            and re.search(
                r"\bTC\b",
                upper,
            )
            is not None
        )

    if code == "TCP":
        return (
            "TCP" in upper
            and "TCPK" not in upper
        )

    if code == "TCPK":
        return (
            "TCPK" in upper
            or "TC PICK UP" in upper
            or "TC PICK-UP" in upper
        )

    return False


def parse_time_range(text):
    match = re.search(
        r"\b"
        r"([01]?\d|2[0-3]):([0-5]\d)"
        r"\s*"
        r"(?:a|-|–|hasta)"
        r"\s*"
        r"([01]?\d|2[0-3]):([0-5]\d)"
        r"\b",
        text,
        re.IGNORECASE,
    )

    if match:
        start = (
            f"{int(match.group(1)):02d}:"
            f"{int(match.group(2)):02d}"
        )

        end = (
            f"{int(match.group(3)):02d}:"
            f"{int(match.group(4)):02d}"
        )

        return start, end

    match = re.search(
        r"\b"
        r"([01]?\d|2[0-3]):([0-5]\d)"
        r"\b",
        text,
    )

    if match:
        return (
            f"{int(match.group(1)):02d}:"
            f"{int(match.group(2)):02d}",
            None,
        )

    return None, None


def parse_duration(text):
    match = re.search(
        r"(\d+)\s*(?:min|minutos)",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    return int(
        match.group(1)
    )


def build_session(
    championship,
    code,
    calendar_event,
    date,
    line,
    source,
):
    tipo = classify_session(
        line
    )

    if not tipo:
        return None

    if not category_matches(
        line,
        code,
    ):
        return None

    start_time, end_time = (
        parse_time_range(
            line
        )
    )

    if not start_time:
        return None

    name = clean(
        line
    )

    start = datetime.strptime(
        (
            f"{date.isoformat()} "
            f"{start_time}"
        ),
        "%Y-%m-%d %H:%M",
    )

    if end_time:
        end = datetime.strptime(
            (
                f"{date.isoformat()} "
                f"{end_time}"
            ),
            "%Y-%m-%d %H:%M",
        )

        if end < start:
            end += timedelta(
                days=1
            )

    else:
        duration = parse_duration(
            name
        )

        if duration:
            end = (
                start
                + timedelta(
                    minutes=duration
                )
            )
        else:
            end = (
                start
                + timedelta(
                    minutes=1
                )
            )

    return {
        "uid": (
            "actc-"
            f"{slugify(championship)}-"
            f"{date.isoformat()}-"
            f"{start_time.replace(':', '')}-"
            f"{slugify(name)}"
        ),
        "categoria": "Argentina",
        "campeonato": championship,
        "tipo": tipo,
        "fecha_inicio": start.strftime(
            "%Y-%m-%dT%H:%M:%S"
        ),
        "fecha_fin": end.strftime(
            "%Y-%m-%dT%H:%M:%S"
        ),
        "ubicacion": calendar_event[
            "location"
        ],
        "descripcion": (
            f"{championship} - "
            f"Fecha {calendar_event['round']} - "
            f"{name}\n"
            f"Fuente ACTC: {source}"
        ),
        "imperdible": (
            tipo == "Carrera"
        ),
    }


def parse_cronograma_page(
    page,
    championship,
    code,
    calendar_events,
):
    text = page.locator(
        "body"
    ).inner_text()

    lines = [
        clean(line)
        for line in text.splitlines()
        if clean(line)
    ]

    events = []

    current_date = None

    for line in lines:

        date = parse_date(
            line
        )

        if not date:
            date = parse_numeric_date(
                line
            )

        if date and date.year == YEAR:
            current_date = date
            continue

        upper = line.upper()

        if "VIERNES" in upper:
            if current_date:
                current_date = current_date

        elif (
            "SÁBADO" in upper
            or "SABADO" in upper
        ):
            pass

        elif "DOMINGO" in upper:
            pass

        if not current_date:
            # Si el cronograma no muestra
            # la fecha en el texto, usamos la
            # próxima fecha del calendario.
            continue

        # Buscamos la fecha de calendario
        # correspondiente.
        calendar_event = None

        for item in calendar_events:
            if item["date"] == current_date:
                calendar_event = item
                break

        if not calendar_event:
            # Algunas páginas sólo muestran
            # el día de la semana.
            calendar_event = min(
                calendar_events,
                key=lambda item: abs(
                    (
                        item["date"]
                        - current_date
                    ).days
                ),
            )

        event = build_session(
            championship=championship,
            code=code,
            calendar_event=calendar_event,
            date=current_date,
            line=line,
            source=page.url,
        )

        if event:
            events.append(
                event
            )

    unique = {}

    for event in events:
        unique[
            event["uid"]
        ] = event

    return list(
        unique.values()
    )


def fallback_events(
    championship,
    calendar_events,
):
    events = []

    for item in calendar_events:

        date = item[
            "date"
        ]

        events.append(
            {
                "uid": (
                    "actc-"
                    f"{slugify(championship)}-"
                    f"fecha-{item['round']}"
                ),
                "categoria": "Argentina",
                "campeonato": championship,
                "tipo": "Carrera",
                "fecha_inicio": (
                    f"{date.isoformat()}"
                    "T00:00:00"
                ),
                "fecha_fin": (
                    f"{date.isoformat()}"
                    "T23:59:00"
                ),
                "ubicacion": item[
                    "location"
                ],
                "descripcion": (
                    f"{championship} - "
                    f"Fecha {item['round']} "
                    f"(horario pendiente)"
                ),
                "imperdible": True,
            }
        )

    return events


def process_category(
    browser,
    championship,
    config,
):
    print()
    print(
        f"Consultando ACTC: "
        f"{championship}"
    )

    page = browser.new_page()

    try:
        print(
            f"  Abriendo: "
            f"{config['calendar']}"
        )

        page.goto(
            config["calendar"],
            wait_until="networkidle",
            timeout=60000,
        )

        page.wait_for_timeout(
            3000
        )

        calendar_events = (
            parse_calendar_page(
                page,
                championship,
            )
        )

        # Si el calendario dinámico no se pudo
        # leer, intentamos la página de categoría.
        if not calendar_events:

            print(
                "  Calendario sin fechas. "
                "Probando página de categoría..."
            )

            page.goto(
                config["page"],
                wait_until="networkidle",
                timeout=60000,
            )

            page.wait_for_timeout(
                3000
            )

            calendar_events = (
                parse_calendar_page(
                    page,
                    championship,
                )
            )

        all_events = fallback_events(
            championship,
            calendar_events,
        )

        print(
            f"  Eventos base: "
            f"{len(all_events)}"
        )

        # Descubrimos los cronogramas
        # directamente desde el navegador.
        page.goto(
            config["page"],
            wait_until="networkidle",
            timeout=60000,
        )

        page.wait_for_timeout(
            3000
        )

        links = discover_cronogram_links(
            page
        )

        print(
            f"  Cronogramas encontrados: "
            f"{len(links)}"
        )

        for link in links:

            print(
                f"    Abriendo cronograma: "
                f"{link}"
            )

            schedule_page = (
                browser.new_page()
            )

            try:

                schedule_page.goto(
                    link,
                    wait_until="networkidle",
                    timeout=60000,
                )

                schedule_page.wait_for_timeout(
                    3000
                )

                sessions = (
                    parse_cronograma_page(
                        schedule_page,
                        championship,
                        config["code"],
                        calendar_events,
                    )
                )

                print(
                    f"    Sesiones encontradas: "
                    f"{len(sessions)}"
                )

                all_events.extend(
                    sessions
                )

            except Exception as exc:

                print(
                    f"    ERROR: {exc}"
                )

            finally:
                schedule_page.close()

        return all_events

    finally:
        page.close()


def main():
    print(
        f"Consultando ACTC para {YEAR}..."
    )

    all_events = []

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True
        )

        try:

            for championship, config in (
                CATEGORIES.items()
            ):

                try:

                    events = process_category(
                        browser,
                        championship,
                        config,
                    )

                    print(
                        f"  Total {championship}: "
                        f"{len(events)}"
                    )

                    all_events.extend(
                        events
                    )

                except Exception as exc:

                    print(
                        f"  ERROR {championship}: "
                        f"{exc}"
                    )

        finally:
            browser.close()

    unique = {}

    for event in all_events:
        unique[
            event["uid"]
        ] = event

    events = list(
        unique.values()
    )

    events.sort(
        key=lambda event: (
            event.get(
                "fecha_inicio",
                "",
            ),
            event.get(
                "campeonato",
                "",
            ),
            event.get(
                "tipo",
                "",
            ),
        )
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
        f"ACTC: {len(events)} "
        f"eventos guardados en {OUTPUT}"
    )

    print()
    print(
        "Resumen por campeonato:"
    )

    championships = {}

    for event in events:
        name = event[
            "campeonato"
        ]

        championships[name] = (
            championships.get(
                name,
                0,
            )
            + 1
        )

    for name in sorted(
        championships
    ):
        print(
            f"  {name}: "
            f"{championships[name]}"
        )

    print()
    print(
        "Resumen por tipo:"
    )

    types = {}

    for event in events:
        tipo = event[
            "tipo"
        ]

        types[tipo] = (
            types.get(
                tipo,
                0,
            )
            + 1
        )

    for tipo in sorted(
        types
    ):
        print(
            f"  {tipo}: "
            f"{types[tipo]}"
        )


if __name__ == "__main__":
    main()
