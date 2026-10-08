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


def get_calendar_events(page):
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


def find_date_elements(page):
    results = []

    try:
        locator = page.locator(
            "text=/Fecha\\s+\\d+/i"
        )

        count = locator.count()

        for index in range(
            count
        ):

            try:
                element = locator.nth(
                    index
                )

                text = clean(
                    element.inner_text()
                )

                match = re.search(
                    r"Fecha\s+(\d+)",
                    text,
                    re.IGNORECASE,
                )

                if not match:
                    continue

                results.append(
                    {
                        "element": element,
                        "round": int(
                            match.group(1)
                        ),
                        "text": text,
                    }
                )

            except Exception:
                continue

    except Exception:
        pass

    unique = {}
    for item in results:
        unique[
            item["round"]
        ] = item

    return list(
        unique.values()
    )


def discover_cronogram_urls(page):
    """
    Busca cronogramas no solamente en <a>.
    ACTC puede insertar la URL mediante JS.
    """

    urls = set()

    # 1. href normales.
    try:
        links = page.locator(
            "[href]"
        )

        for index in range(
            min(links.count(), 1000)
        ):

            try:
                href = links.nth(
                    index
                ).get_attribute(
                    "href"
                )

                if not href:
                    continue

                if (
                    "cronograma" in
                    href.lower()
                ):
                    urls.add(
                        urljoin(
                            page.url,
                            href,
                        )
                    )

            except Exception:
                pass

    except Exception:
        pass

    # 2. HTML completo.
    try:
        html = page.content()

        matches = re.findall(
            r"""https?://[^"'\\\s<>]+/cronogramas/[A-Za-z0-9_-]+""",
            html,
            re.IGNORECASE,
        )

        for match in matches:
            urls.add(
                match.rstrip(
                    ".,);"
                )
            )

        matches = re.findall(
            r"""["']([^"']*/cronogramas/[A-Za-z0-9_-]+)["']""",
            html,
            re.IGNORECASE,
        )

        for match in matches:
            urls.add(
                urljoin(
                    page.url,
                    match,
                )
            )

    except Exception:
        pass

    # 3. Texto visible.
    try:
        text = page.locator(
            "body"
        ).inner_text()

        matches = re.findall(
            r"""(?:https?://)?[^\s"'<>]+/cronogramas/[A-Za-z0-9_-]+""",
            text,
            re.IGNORECASE,
        )

        for match in matches:
            if match.startswith(
                "http"
            ):
                urls.add(match)
            else:
                urls.add(
                    urljoin(
                        page.url,
                        match,
                    )
                )

    except Exception:
        pass

    return sorted(
        urls
    )


def extract_schedule_text(
    page,
):
    """
    Devuelve texto útil de la página
    del cronograma.
    """

    try:
        return page.locator(
            "body"
        ).inner_text()
    except Exception:
        return ""


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
        end = start + timedelta(
            minutes=1
        )

    name = clean(line)

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
            f"Fecha {calendar_event['round']}\n"
            f"{name}\n"
            f"Fuente ACTC: {source}"
        ),
        "imperdible": tipo == "Carrera",
    }


def parse_schedule(
    text,
    championship,
    code,
    calendar_event,
    source,
):
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
            source,
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

        date = item["date"]

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
                page
            )
        )

        print(
            f"  Fechas encontradas: "
            f"{len(calendar_events)}"
        )

        all_events = fallback_events(
            championship,
            calendar_events,
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

        processed = set()

        for item in calendar_events:

            round_number = item[
                "round"
            ]

            if round_number in processed:
                continue

            processed.add(
                round_number
            )

            print(
                f"  Fecha {round_number}: "
                f"{item['date']} "
                f"{item['location']}"
            )

            try:

                # Recargar el calendario.
                page.goto(
                    config["calendar"],
                    wait_until="networkidle",
                    timeout=60000,
                )

                page.wait_for_timeout(
                    1500
                )

                elements = (
                    find_date_elements(
                        page
                    )
                )

                target = None

                for candidate in elements:
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
                        "el botón de la fecha."
                    )
                    continue

                try:
                    target.scroll_into_view_if_needed(
                        timeout=5000
                    )
                except Exception:
                    pass

                print(
                    "    Seleccionando fecha..."
                )

                target.click(
                    timeout=10000
                )

                # Esperamos a que ACTC termine
                # de actualizar el contenido.
                page.wait_for_timeout(
                    4000
                )

                urls = (
                    discover_cronogram_urls(
                        page
                    )
                )

                if not urls:

                    # A veces el contenido aparece
                    # después de unos segundos.
                    page.wait_for_timeout(
                        5000
                    )

                    urls = (
                        discover_cronogram_urls(
                            page
                        )
                    )

                if not urls:

                    print(
                        "    No se encontró "
                        "URL de cronograma."
                    )

                    # Guardamos información de
                    # diagnóstico únicamente para
                    # el primer caso.
                    if round_number == 1:

                        try:
                            debug_dir = Path(
                                "data/actc_debug"
                            )

                            debug_dir.mkdir(
                                parents=True,
                                exist_ok=True,
                            )

                            (
                                debug_dir
                                / f"{slugify(championship)}-fecha-1.html"
                            ).write_text(
                                page.content(),
                                encoding="utf-8",
                            )

                            (
                                debug_dir
                                / f"{slugify(championship)}-fecha-1.txt"
                            ).write_text(
                                page.locator(
                                    "body"
                                ).inner_text(),
                                encoding="utf-8",
                            )

                            print(
                                "    Diagnóstico "
                                "guardado en "
                                "data/actc_debug/"
                            )

                        except Exception as exc:
                            print(
                                f"    No se pudo "
                                f"guardar diagnóstico: "
                                f"{exc}"
                            )

                    continue

                print(
                    f"    Cronogramas encontrados: "
                    f"{len(urls)}"
                )

                # Probamos todos los cronogramas
                # descubiertos hasta encontrar
                # sesiones correspondientes.
                found_sessions = []

                for cronograma in urls:

                    print(
                        f"    Abriendo: "
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
                            2500
                        )

                        text = (
                            extract_schedule_text(
                                schedule_page
                            )
                        )

                        sessions = parse_schedule(
                            text,
                            championship,
                            config["code"],
                            item,
                            cronograma,
                        )

                        if sessions:
                            found_sessions.extend(
                                sessions
                            )

                            print(
                                f"      Sesiones "
                                f"encontradas: "
                                f"{len(sessions)}"
                            )

                    except Exception as exc:

                        print(
                            f"      Error: "
                            f"{exc}"
                        )

                    finally:
                        schedule_page.close()

                if found_sessions:

                    all_events.extend(
                        found_sessions
                    )

                else:

                    print(
                        "    No se encontraron "
                        "sesiones con horario."
                    )

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
