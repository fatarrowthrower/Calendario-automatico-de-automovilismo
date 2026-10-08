import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


YEAR = datetime.now().year

OUTPUT = Path("data/actc_events.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
}


CATEGORIES = {
    "TC": {
        "page": "https://actc.org.ar/tc",
        "calendar": "https://tiempos.actc.org.ar/calendario?categoria=tc",
        "code": "TC",
    },
    "TC Pista": {
        "page": "https://actc.org.ar/tcp",
        "calendar": "https://tiempos.actc.org.ar/calendario?categoria=tcp",
        "code": "TCP",
    },
    "TC Pick Up": {
        "page": "https://actc.org.ar/tcpk",
        "calendar": "https://tiempos.actc.org.ar/calendario?categoria=tcpk",
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


def fetch(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    return response.text


def slugify(text):
    text = text.lower()

    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
        "ñ": "n",
    }

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
    month = MONTHS[
        match.group(2).lower()
    ]
    year = int(match.group(3))

    try:
        return datetime(
            year,
            month,
            day,
        ).date()
    except ValueError:
        return None


def parse_calendar(calendar_url):
    print(
        f"  Leyendo calendario: {calendar_url}"
    )

    html = fetch(
        calendar_url
    )

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    text = soup.get_text(
        "\n",
        strip=True,
    )

    events = []

    lines = [
        clean(line)
        for line in text.splitlines()
        if clean(line)
    ]

    for index, line in enumerate(lines):

        date = parse_date(
            line
        )

        if not date:
            continue

        if date.year != YEAR:
            continue

        nearby = " ".join(
            lines[
                index:index + 8
            ]
        )

        round_match = re.search(
            r"Fecha\s+(\d+)",
            nearby,
            re.IGNORECASE,
        )

        if not round_match:
            continue

        round_number = int(
            round_match.group(1)
        )

        location = "Argentina"

        location_match = re.search(
            r"Fecha\s+\d+\s*[—-]\s*"
            r"(.+?)(?:\s+\d{1,2}\.\d{2}\.\d{2}|$)",
            nearby,
            re.IGNORECASE,
        )

        if location_match:
            location = clean(
                location_match.group(1)
            )

        events.append(
            {
                "round": round_number,
                "date": date,
                "location": location,
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
        key=lambda item: (
            item["date"],
            item["round"],
        )
    )

    print(
        f"  Fechas encontradas: {len(events)}"
    )

    return events


def find_cronograma_link(category_url):
    """
    La página oficial de la categoría contiene
    el botón 'Cronograma'.

    Buscamos cualquier href que apunte a:
        /cronogramas/...
    """

    html = fetch(
        category_url
    )

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    candidates = []

    for link in soup.find_all(
        "a",
        href=True,
    ):
        href = link[
            "href"
        ]

        label = clean(
            link.get_text(
                " ",
                strip=True,
            )
        )

        full_url = urljoin(
            category_url,
            href,
        )

        lower_url = full_url.lower()
        lower_label = label.lower()

        if (
            "/cronogramas/" in lower_url
            or "cronograma" in lower_label
        ):
            if full_url not in candidates:
                candidates.append(
                    full_url
                )

    if candidates:
        print(
            "  Cronograma encontrado:"
        )

        for url in candidates:
            print(
                f"    {url}"
            )

        return candidates[0]

    return None


def extract_dates_from_text(text):
    """
    Busca fechas dentro de un cronograma.
    """

    dates = []

    patterns = [
        r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
        r"\b(\d{1,2})-(\d{1,2})-(\d{4})\b",
        r"\b(\d{1,2})\s+"
        r"(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)"
        r"\s+(\d{4})\b",
    ]

    for pattern in patterns:

        for match in re.finditer(
            pattern,
            text,
            re.IGNORECASE,
        ):

            try:

                if len(match.groups()) == 3:

                    if match.group(2).isalpha():
                        day = int(
                            match.group(1)
                        )
                        month = MONTHS[
                            match.group(2).lower()
                        ]
                        year = int(
                            match.group(3)
                        )

                    else:
                        day = int(
                            match.group(1)
                        )
                        month = int(
                            match.group(2)
                        )
                        year = int(
                            match.group(3)
                        )

                    date = datetime(
                        year,
                        month,
                        day,
                    ).date()

                    dates.append(
                        date
                    )

            except (
                ValueError,
                KeyError,
            ):
                pass

    return dates


def parse_time_range(text):
    """
    Acepta:

    09:25 a 09:55
    09:25 - 09:55
    09:25 – 09:55
    09:25 Hs.
    """

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
        r"\s*(?:Hs?\.?)?"
        r"\b",
        text,
        re.IGNORECASE,
    )

    if match:
        start = (
            f"{int(match.group(1)):02d}:"
            f"{int(match.group(2)):02d}"
        )

        return start, None

    return None, None


def extract_duration(text):
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
        or "sesión clasificatoria" in lower
        or "sesion clasificatoria" in lower
    ):
        return "Clasificación"

    if "serie" in lower:
        return "Serie"

    if (
        "final" in lower
        or "carrera" in lower
    ):
        return "Carrera"

    return None


def category_line(line, code):
    upper = line.upper()

    if code == "TC":
        return (
            re.search(
                r"\bTC\b",
                upper,
            )
            is not None
            and "TCP" not in upper
            and "TCPK" not in upper
        )

    if code == "TCP":
        return (
            "TCP" in upper
            and "TCPK" not in upper
        )

    if code == "TCPK":
        return (
            "TCPK" in upper
            or "PICK UP" in upper
            or "PICK-UP" in upper
        )

    return False


def clean_session_name(
    line,
    code,
):
    name = line

    prefixes = [
        f"{code} |",
        f"{code}|",
    ]

    for prefix in prefixes:
        if name.upper().startswith(
            prefix.upper()
        ):
            name = name[
                len(prefix):
            ]
            break

    return clean(
        name
    )


def build_event(
    championship,
    calendar_event,
    session_date,
    start_time,
    end_time,
    tipo,
    name,
    source,
):
    start = datetime.strptime(
        (
            f"{session_date.isoformat()} "
            f"{start_time}"
        ),
        "%Y-%m-%d %H:%M",
    )

    if end_time:

        end = datetime.strptime(
            (
                f"{session_date.isoformat()} "
                f"{end_time}"
            ),
            "%Y-%m-%d %H:%M",
        )

        if end < start:
            end += timedelta(
                days=1
            )

    else:

        duration = extract_duration(
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
            # Si ACTC publica solamente la hora
            # de largada, usamos 1 minuto para
            # no inventar una duración.
            end = (
                start
                + timedelta(
                    minutes=1
                )
            )

    uid = (
        "actc-"
        f"{slugify(championship)}-"
        f"{session_date.isoformat()}-"
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


def parse_cronograma(
    html,
    championship,
    code,
    calendar_event,
    source,
):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    text = soup.get_text(
        "\n",
        strip=True,
    )

    lines = [
        clean(line)
        for line in text.splitlines()
        if clean(line)
    ]

    events = []

    current_date = calendar_event[
        "date"
    ]

    # Detectamos fechas explícitas del cronograma.
    date_positions = []

    for index, line in enumerate(lines):

        dates = extract_dates_from_text(
            line
        )

        for date in dates:
            if date.year == YEAR:
                date_positions.append(
                    (
                        index,
                        date,
                    )
                )

    for index, line in enumerate(lines):

        upper = line.upper()

        # Cambio de día mediante encabezados.
        if re.search(
            r"\bVIERNES\b",
            upper,
        ):
            current_date = (
                calendar_event["date"]
                - timedelta(days=2)
            )

        elif re.search(
            r"\bS[ÁA]BADO\b",
            upper,
        ):
            current_date = (
                calendar_event["date"]
                - timedelta(days=1)
            )

        elif re.search(
            r"\bDOMINGO\b",
            upper,
        ):
            current_date = (
                calendar_event["date"]
            )

        # Si encontramos una fecha explícita
        # cerca de esta línea, la utilizamos.
        for position, date in date_positions:

            if position == index:
                current_date = date

        tipo = classify_session(
            line
        )

        if not tipo:
            continue

        if not category_line(
            line,
            code,
        ):
            continue

        start_time, end_time = (
            parse_time_range(
                line
            )
        )

        if not start_time:
            continue

        name = clean_session_name(
            line,
            code,
        )

        if not name:
            continue

        event = build_event(
            championship=championship,
            calendar_event=calendar_event,
            session_date=current_date,
            start_time=start_time,
            end_time=end_time,
            tipo=tipo,
            name=name,
            source=source,
        )

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


def build_fallback_race(
    championship,
    event,
):
    date = event["date"]

    return {
        "uid": (
            "actc-"
            f"{slugify(championship)}-"
            f"{date.isoformat()}-"
            f"fecha-{event['round']}"
        ),
        "categoria": "Argentina",
        "campeonato": championship,
        "tipo": "Carrera",
        "fecha_inicio": (
            f"{date.isoformat()}T00:00:00"
        ),
        "fecha_fin": (
            f"{date.isoformat()}T23:59:00"
        ),
        "ubicacion": event[
            "location"
        ],
        "descripcion": (
            f"{championship} - "
            f"Fecha {event['round']} "
            f"(horario oficial pendiente)"
        ),
        "imperdible": True,
    }


def process_category(
    championship,
    config,
):
    print()
    print(
        f"Consultando ACTC: "
        f"{championship}"
    )

    calendar_events = parse_calendar(
        config["calendar"]
    )

    all_events = []

    # Siempre conservamos las fechas.
    for calendar_event in calendar_events:
        all_events.append(
            build_fallback_race(
                championship,
                calendar_event,
            )
        )

    # Ahora buscamos directamente el cronograma
    # de la página de la categoría.
    cronograma_url = None

    try:
        cronograma_url = (
            find_cronograma_link(
                config["page"]
            )
        )
    except Exception as exc:
        print(
            f"  ERROR buscando cronograma: "
            f"{exc}"
        )

    if not cronograma_url:
        print(
            "  No hay cronograma publicado "
            "en la página de categoría."
        )

        return all_events

    try:
        print(
            f"  Descargando cronograma..."
        )

        html = fetch(
            cronograma_url
        )

        for calendar_event in calendar_events:

            sessions = parse_cronograma(
                html=html,
                championship=championship,
                code=config["code"],
                calendar_event=calendar_event,
                source=cronograma_url,
            )

            if sessions:
                print(
                    f"  Fecha "
                    f"{calendar_event['round']}: "
                    f"{len(sessions)} sesiones"
                )

                all_events.extend(
                    sessions
                )

    except Exception as exc:
        print(
            f"  ERROR leyendo cronograma: "
            f"{exc}"
        )

    return all_events


def main():
    print(
        f"Consultando ACTC para {YEAR}..."
    )

    all_events = []

    for championship, config in (
        CATEGORIES.items()
    ):

        try:
            events = process_category(
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

    # Deduplicamos.
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
