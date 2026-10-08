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
        "code": "TC",
    },
    "TC Pista": {
        "calendar": "https://actc.org.ar/tcp/calendario",
        "code": "TCP",
    },
    "TC Pick Up": {
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


def get_calendar_events(
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
        key=lambda event: event["date"]
    )

    print(
        f"  Fechas encontradas: "
        f"{len(events)}"
    )

    return events


def find_date_elements(
    page,
):
    """
    Busca elementos visibles que contienen
    'Fecha N'.

    No asumimos una clase CSS concreta.
    """

    elements = []

    locators = [
        page.get_by_text(
            re.compile(
                r"Fecha\s+\d+",
                re.IGNORECASE,
            )
        ),
        page.locator(
            "button"
        ),
        page.locator(
            "a"
        ),
    ]

    seen = set()

    for locator in locators:

        try:
            count = locator.count()
        except Exception:
            continue

        for index in range(
            min(count, 500)
        ):

            try:
                element = locator.nth(
                    index
                )

                text = clean(
                    element.inner_text()
                )

                if not text:
                    continue

                match = re.search(
                    r"Fecha\s+(\d+)",
                    text,
                    re.IGNORECASE,
                )

                if not match:
                    continue

                round_number = int(
                    match.group(1)
                )

                key = (
                    round_number,
                    text,
                )

                if key in seen:
                    continue

                seen.add(key)

                elements.append(
                    {
                        "element": element,
                        "round": round_number,
                        "text": text,
                    }
                )

            except Exception:
                continue

    return elements


def find_cronograma_link(
    page,
):
    """
    Busca el botón/link Cronograma DESPUÉS
    de seleccionar una fecha.
    """

    candidates = []

    try:
        links = page.locator(
            "a"
        )

        for index in range(
            min(links.count(), 300)
        ):

            link = links.nth(
                index
            )

            try:
                href = link.get_attribute(
                    "href"
                )

                text = clean(
                    link.inner_text()
                )
            except Exception:
                continue

            if not href:
                continue

            full_url = urljoin(
                page.url,
                href,
            )

            if (
                "/cronogramas/" in
                full_url.lower()
            ):
                candidates.append(
                    full_url
                )

            elif (
                "cronograma" in
                text.lower()
            ):
                candidates.append(
                    full_url
                )

    except Exception:
        pass

    # Eliminar duplicados.
    unique = []

    for url in candidates:
        if url not in unique:
            unique.append(
                url
            )

    if unique:
        return unique[0]

    return None


def classify_session(
    text,
):
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
            "TCP" not in upper
            and "TCPK" not in upper
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


def parse_time_range(
    text,
):
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

        return (
            f"{int(match.group(1)):02d}:"
            f"{int(match.group(2)):02d}",
            f"{int(match.group(3)):02d}:"
            f"{int(match.group(4)):02d}",
        )

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


def parse_duration(
    text,
):
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


def build_event(
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
            line
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

    name = clean(
        line
    )

    uid = (
        "actc-"
        f"{slugify(championship)}-"
        f"{date.isoformat()}-"
        f"{start_time.replace(':', '')}-"
        f"{slugify(name)}"
    )

    return {
        "uid": uid,
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


def parse_schedule(
    schedule_page,
    championship,
    code,
    calendar_event,
):
    """
    Lee el texto ya renderizado por Chromium.
    """

    text = schedule_page.locator(
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
            current_date = (
                calendar_event["date"]
                - timedelta(days=2)
            )
            continue

        if (
            "SÁBADO" in upper
            or "SABADO" in upper
        ):
            current_date = (
                calendar_event["date"]
                - timedelta(days=1)
            )
            continue

        if "DOMINGO" in upper:
            current_date = (
                calendar_event["date"]
            )
            continue

        event = build_event(
            championship,
            code,
            calendar_event,
            current_date,
            line,
            schedule_page.url,
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

        page.goto(
            config["calendar"],
            wait_until="networkidle",
            timeout=60000,
        )

        page.wait_for_timeout(
            3000
        )

        calendar_events = (
            get_calendar_events(
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

        date_elements = (
            find_date_elements(
                page
            )
        )

        print(
            f"  Selectores de fechas "
            f"detectados: "
            f"{len(date_elements)}"
        )

        # Procesamos cada fecha.
        processed_rounds = set()

        for date_info in date_elements:

            round_number = date_info[
                "round"
            ]

            if round_number in processed_rounds:
                continue

            processed_rounds.add(
                round_number
            )

            calendar_event = None

            for event in calendar_events:
                if event[
                    "round"
                ] == round_number:
                    calendar_event = event
                    break

            if not calendar_event:
                continue

            print(
                f"  Fecha {round_number}: "
                f"{calendar_event['date']} "
                f"{calendar_event['location']}"
            )

            try:

                # Volvemos a la página del
                # calendario antes de cada click,
                # así evitamos que el estado anterior
                # interfiera.
                page.goto(
                    config["calendar"],
                    wait_until="networkidle",
                    timeout=60000,
                )

                page.wait_for_timeout(
                    1500
                )

                selectors = (
                    find_date_elements(
                        page
                    )
                )

                target = None

                for candidate in selectors:
                    if candidate[
                        "round"
                    ] == round_number:
                        target = candidate[
                            "element"
                        ]
                        break

                if target is None:
                    print(
                        "    No se encontró "
                        "el selector de esta fecha."
                    )
                    continue

                try:
                    target.scroll_into_view_if_needed(
                        timeout=5000
                    )
                except Exception:
                    pass

                target.click(
                    timeout=10000
                )

                page.wait_for_timeout(
                    2500
                )

                cronograma = (
                    find_cronograma_link(
                        page
                    )
                )

                if not cronograma:
                    print(
                        "    No apareció "
                        "cronograma."
                    )
                    continue

                print(
                    f"    Cronograma: "
                    f"{cronograma}"
                )

                schedule_page = (
                    browser.new_page()
                )

                try:

                    schedule_page.goto(
                        cronograma,
                        wait_until="networkidle",
                        timeout=60000,
                    )

                    schedule_page.wait_for_timeout(
                        3000
                    )

                    sessions = parse_schedule(
                        schedule_page,
                        championship,
                        config["code"],
                        calendar_event,
                    )

                    print(
                        f"    Sesiones: "
                        f"{len(sessions)}"
                    )

                    all_events.extend(
                        sessions
                    )

                finally:
                    schedule_page.close()

            except Exception as exc:

                print(
                    f"    ERROR Fecha "
                    f"{round_number}: "
                    f"{exc}"
                )

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
