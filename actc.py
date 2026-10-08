import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright


YEAR = datetime.now().year

OUTPUT = Path("data/actc_events.json")


CATEGORIES = {
    "TC": {
        "calendar": "https://actc.org.ar/tc/calendario",
        "results": "https://actc.org.ar/tc/resultados",
        "code": "TC",
    },
    "TC Pista": {
        "calendar": "https://actc.org.ar/tcp/calendario",
        "results": "https://actc.org.ar/tcp/resultados",
        "code": "TCP",
    },
    "TC Pick Up": {
        "calendar": "https://actc.org.ar/tcpk/calendario",
        "results": "https://actc.org.ar/tcpk/resultados",
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

    try:
        return datetime(
            int(match.group(3)),
            MONTHS[
                match.group(2).lower()
            ],
            int(match.group(1)),
        ).date()
    except Exception:
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
    except Exception:
        return None


def extract_calendar_events(page):
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

        date = parse_date(line)

        if not date:
            date = parse_numeric_date(line)

        if not date:
            continue

        if date.year != YEAR:
            continue

        if current_round is None:

            for previous in reversed(
                lines[
                    max(0, index - 10):index
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

    events = list(
        unique.values()
    )

    events.sort(
        key=lambda x: x["date"]
    )

    return events


def find_results_links(
    page,
    round_number,
):
    links = []

    try:
        locator = page.locator(
            "a"
        )

        count = locator.count()

        for index in range(
            min(count, 1000)
        ):

            link = locator.nth(
                index
            )

            try:
                text = clean(
                    link.inner_text()
                )

                href = link.get_attribute(
                    "href"
                )

            except Exception:
                continue

            if not href:
                continue

            if (
                "resultado" not in
                text.lower()
                and "ver resultados"
                not in text.lower()
            ):
                continue

            full_url = urljoin(
                page.url,
                href,
            )

            links.append(
                full_url
            )

    except Exception:
        pass

    unique = []

    for url in links:
        if url not in unique:
            unique.append(url)

    return unique


def parse_session_type(text):
    lower = text.lower()

    if "entrenamiento" in lower:
        return "Entrenamiento"

    if "clasificación" in lower:
        return "Clasificación"

    if "clasificacion" in lower:
        return "Clasificación"

    if "serie" in lower:
        return "Serie"

    if "final" in lower:
        return "Carrera"

    return None


def find_session_date(
    text,
    fallback_date,
):
    date = parse_date(text)

    if date:
        return date

    date = parse_numeric_date(text)

    if date:
        return date

    return fallback_date


def parse_result_page(
    page,
    championship,
    code,
    calendar_event,
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

    current_date = calendar_event[
        "date"
    ]

    for index, line in enumerate(lines):

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

        session_type = (
            parse_session_type(
                line
            )
        )

        if not session_type:
            continue

        # Evitamos encabezados de navegación
        # o textos genéricos.
        if len(line) < 4:
            continue

        # La página de resultados no siempre
        # publica la hora. Cuando la publica,
        # intentamos capturarla.
        time_match = re.search(
            r"\b"
            r"([01]?\d|2[0-3]):([0-5]\d)"
            r"\b",
            line,
        )

        if time_match:

            start_time = (
                f"{int(time_match.group(1)):02d}:"
                f"{int(time_match.group(2)):02d}"
            )

        else:

            # Buscamos una hora en las líneas
            # inmediatamente siguientes.
            start_time = None

            for next_line in lines[
                index + 1:index + 4
            ]:

                time_match = re.search(
                    r"\b"
                    r"([01]?\d|2[0-3]):([0-5]\d)"
                    r"\b",
                    next_line,
                )

                if time_match:
                    start_time = (
                        f"{int(time_match.group(1)):02d}:"
                        f"{int(time_match.group(2)):02d}"
                    )
                    break

        if not start_time:
            continue

        start = datetime.strptime(
            (
                f"{current_date.isoformat()} "
                f"{start_time}"
            ),
            "%Y-%m-%d %H:%M",
        )

        end = start + timedelta(
            minutes=1
        )

        uid = (
            "actc-"
            f"{slugify(championship)}-"
            f"{current_date.isoformat()}-"
            f"{start_time.replace(':', '')}-"
            f"{slugify(line)}"
        )

        events.append(
            {
                "uid": uid,
                "categoria": "Argentina",
                "campeonato": championship,
                "tipo": session_type,
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
                    f"Fecha {calendar_event['round']}\n"
                    f"{line}\n"
                    f"Fuente ACTC: {page.url}"
                ),
                "imperdible": (
                    session_type == "Carrera"
                ),
            }
        )

    unique = {}

    for event in events:
        unique[
            event["uid"]
        ] = event

    return list(
        unique.values()
    )


def fallback_event(
    championship,
    item,
):
    date = item[
        "date"
    ]

    return {
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

    calendar_page = browser.new_page()

    try:

        calendar_page.goto(
            config["calendar"],
            wait_until="domcontentloaded",
            timeout=90000,
        )

        calendar_page.wait_for_timeout(
            3000
        )

        calendar_events = (
            extract_calendar_events(
                calendar_page
            )
        )

        print(
            f"  Fechas encontradas: "
            f"{len(calendar_events)}"
        )

        results = []

        for item in calendar_events:

            print(
                f"  Fecha {item['round']}: "
                f"{item['date']} "
                f"{item['location']}"
            )

            # Buscamos el enlace "Ver resultados"
            # asociado a esa fecha.
            #
            # Primero buscamos elementos que
            # contengan el número de fecha.
            result_url = None

            try:

                # Buscamos todos los enlaces de
                # resultados de la página.
                urls = find_results_links(
                    calendar_page,
                    item["round"],
                )

                if urls:

                    # El sitio normalmente entrega
                    # los resultados en orden cronológico.
                    position = (
                        item["round"] - 1
                    )

                    if position < len(urls):
                        result_url = urls[
                            position
                        ]

                    else:
                        result_url = urls[-1]

            except Exception:
                pass

            # Si no pudimos asociarlo desde el
            # calendario, construimos una búsqueda
            # en la página de resultados.
            if not result_url:
                result_url = (
                    config["results"]
                    + f"?year={YEAR}"
                )

            print(
                f"    Resultados: "
                f"{result_url}"
            )

            result_page = browser.new_page()

            try:

                result_page.goto(
                    result_url,
                    wait_until="domcontentloaded",
                    timeout=90000,
                )

                result_page.wait_for_timeout(
                    2500
                )

                sessions = parse_result_page(
                    result_page,
                    championship,
                    config["code"],
                    item,
                )

                print(
                    f"    Sesiones con horario: "
                    f"{len(sessions)}"
                )

                if sessions:
                    results.extend(
                        sessions
                    )

            except Exception as exc:

                print(
                    f"    Error resultados: "
                    f"{exc}"
                )

            finally:
                result_page.close()

        # Agregamos las carreras de calendario
        # como respaldo solamente para las fechas
        # que todavía no tienen sesiones.
        rounds_with_sessions = set()

        for event in results:

            match = re.search(
                r"Fecha\s+(\d+)",
                event.get(
                    "descripcion",
                    "",
                ),
                re.IGNORECASE,
            )

            if match:
                rounds_with_sessions.add(
                    int(
                        match.group(1)
                    )
                )

        for item in calendar_events:

            if item[
                "round"
            ] not in rounds_with_sessions:

                results.append(
                    fallback_event(
                        championship,
                        item,
                    )
                )

        return results

    finally:
        calendar_page.close()


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
