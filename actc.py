import json
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import pytz
from playwright.sync_api import sync_playwright


YEAR = datetime.now().year

TZ = pytz.timezone(
    "America/Argentina/Buenos_Aires"
)

OUTPUT = Path(
    "data/actc_events.json"
)


CATEGORIES = [
    {
        "name": "TC",
        "championship": "Turismo Carretera",
        "calendar_url": "https://actc.org.ar/tc/calendario",
    },
    {
        "name": "TC Pista",
        "championship": "TC Pista",
        "calendar_url": "https://actc.org.ar/tcp/calendario",
    },
    {
        "name": "TC Pick Up",
        "championship": "TC Pick Up",
        "calendar_url": "https://actc.org.ar/tcpk/calendario",
    },
]


MONTHS = {
    "ENE": 1,
    "ENERO": 1,
    "FEB": 2,
    "FEBRERO": 2,
    "MAR": 3,
    "MARZO": 3,
    "ABR": 4,
    "ABRIL": 4,
    "MAY": 5,
    "MAYO": 5,
    "JUN": 6,
    "JUNIO": 6,
    "JUL": 7,
    "JULIO": 7,
    "AGO": 8,
    "AGOSTO": 8,
    "SEP": 9,
    "SEPT": 9,
    "SEPTIEMBRE": 9,
    "SET": 9,
    "SETIEMBRE": 9,
    "OCT": 10,
    "OCTUBRE": 10,
    "NOV": 11,
    "NOVIEMBRE": 11,
    "DIC": 12,
    "DICIEMBRE": 12,
}


def normalize(text):
    text = text or ""

    text = unicodedata.normalize(
        "NFD",
        text,
    )

    text = "".join(
        c
        for c in text
        if unicodedata.category(c) != "Mn"
    )

    text = text.upper()

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def slug(text):
    text = normalize(text).lower()

    text = re.sub(
        r"[^a-z0-9]+",
        "-",
        text,
    )

    return text.strip("-")


def parse_calendar_date(line):
    text = normalize(line)

    match = re.search(
        r"\b(\d{1,2})\s+([A-Z]+)\s+(20\d{2})\b",
        text,
    )

    if not match:
        return None

    day = int(match.group(1))
    month = MONTHS.get(
        match.group(2)
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


def extract_calendar_events(
    page,
    category,
):
    print(
        f"  Abriendo calendario: "
        f"{category['calendar_url']}"
    )

    page.goto(
        category["calendar_url"],
        wait_until="domcontentloaded",
        timeout=60000,
    )

    page.wait_for_timeout(2500)

    text = page.locator(
        "body"
    ).inner_text()

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    events = []

    current_round = None
    current_location = None

    for line in lines:
        normalized = normalize(line)

        match = re.match(
            r"^FECHA\s+(\d+)\s*[—–-]\s*(.+)$",
            normalized,
        )

        if match:
            current_round = int(
                match.group(1)
            )

            current_location = (
                match.group(2).strip()
            )

            continue

        if current_round is None:
            continue

        date = parse_calendar_date(
            line
        )

        if not date:
            continue

        if date.year != YEAR:
            continue

        key = (
            current_round,
            date.isoformat(),
            normalize(
                current_location
            ),
        )

        if any(
            event["_key"] == key
            for event in events
        ):
            continue

        events.append(
            {
                "_key": key,
                "round": current_round,
                "date": date,
                "location": current_location,
            }
        )

        current_round = None
        current_location = None

    # Segunda pasada por si ACTC cambia
    # ligeramente el HTML.
    if not events:
        for index, line in enumerate(lines):
            normalized = normalize(line)

            match = re.match(
                r"^FECHA\s+(\d+)\s*[—–-]\s*(.+)$",
                normalized,
            )

            if not match:
                continue

            round_number = int(
                match.group(1)
            )

            location = match.group(2).strip()

            for next_line in lines[
                index + 1:index + 15
            ]:
                date = parse_calendar_date(
                    next_line
                )

                if not date:
                    continue

                if date.year != YEAR:
                    continue

                events.append(
                    {
                        "_key": (
                            round_number,
                            date.isoformat(),
                            location,
                        ),
                        "round": round_number,
                        "date": date,
                        "location": location,
                    }
                )

                break

    events.sort(
        key=lambda item:
        item["round"]
    )

    return events


def find_result_links(
    page,
):
    links = []

    for anchor in page.locator(
        "a"
    ).all():
        try:
            href = anchor.get_attribute(
                "href"
            )

            if not href:
                continue

            href = urljoin(
                "https://actc.org.ar",
                href,
            )

            if "/resultados" not in href:
                continue

            if href not in links:
                links.append(href)

        except Exception:
            continue

    return links


def get_result_url_for_round(
    page,
    category,
    race,
):
    """
    Busca el enlace real de resultados de una
    fecha dentro del calendario.

    No intenta interpretar el HTML:
    solamente busca href que contengan
    /resultados y fecha=N.
    """

    page.goto(
        category["calendar_url"],
        wait_until="domcontentloaded",
        timeout=60000,
    )

    page.wait_for_timeout(1000)

    links = find_result_links(
        page
    )

    wanted = f"fecha={race['round']}"

    candidates = [
        link
        for link in links
        if wanted in link.lower()
    ]

    if candidates:
        return candidates[0]

    return None


def find_online_url_in_page(
    page,
):
    """
    Busca cualquier referencia a
    carrera-online dentro de la página.

    ACTC puede colocarla como enlace,
    atributo HTML o URL embebida.
    """

    # 1. Enlaces normales.
    for anchor in page.locator(
        "a"
    ).all():
        try:
            href = anchor.get_attribute(
                "href"
            )

            if not href:
                continue

            full = urljoin(
                "https://actc.org.ar",
                href,
            )

            if (
                "/carrera-online/"
                in full.lower()
            ):
                return full

        except Exception:
            continue

    # 2. HTML completo.
    try:
        html = page.content()

        matches = re.findall(
            r"""(?:https?:)?//[^"'\\s<>]+/carrera-online/[^"'\\s<>]+""",
            html,
            flags=re.IGNORECASE,
        )

        if matches:
            url = matches[0]

            if url.startswith("//"):
                url = "https:" + url

            return urljoin(
                "https://actc.org.ar",
                url,
            )

    except Exception:
        pass

    return None


def find_carrera_online(
    page,
    category,
    race,
):
    """
    Primero abre resultados de la fecha.

    Después busca allí carrera-online.

    Si ACTC no lo deja expuesto en resultados,
    inspecciona el calendario de esa categoría.
    """

    result_url = get_result_url_for_round(
        page,
        category,
        race,
    )

    if result_url:
        print(
            f"    Resultados: "
            f"{result_url}"
        )

        try:
            page.goto(
                result_url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.wait_for_timeout(
                1200
            )

            online = (
                find_online_url_in_page(
                    page
                )
            )

            if online:
                return online

        except Exception as error:
            print(
                f"    Error leyendo resultados: "
                f"{error}"
            )

    # Segundo intento:
    # buscar carrera-online en calendario.
    try:
        page.goto(
            category["calendar_url"],
            wait_until="domcontentloaded",
            timeout=60000,
        )

        page.wait_for_timeout(
            1000
        )

        html = page.content()

        matches = re.findall(
            r"""(?:https?:)?//[^"'\\s<>]+/carrera-online/[^"'\\s<>]+""",
            html,
            flags=re.IGNORECASE,
        )

        for match in matches:
            if (
                f"fecha-{race['round']}"
                in match.lower()
            ):
                if match.startswith("//"):
                    match = "https:" + match

                return urljoin(
                    category["calendar_url"],
                    match,
                )

    except Exception:
        pass

    return None


def extract_time_pairs(text):
    normalized = normalize(text)

    result = []

    # 09:25 a 09:55
    # 09:25 - 09:55
    ranges = re.findall(
        r"\b(\d{1,2})[:.](\d{2})\s*(?:A|-|–)\s*(\d{1,2})[:.](\d{2})\b",
        normalized,
    )

    for sh, sm, eh, em in ranges:
        sh = int(sh)
        sm = int(sm)
        eh = int(eh)
        em = int(em)

        if (
            0 <= sh <= 23
            and 0 <= sm <= 59
            and 0 <= eh <= 23
            and 0 <= em <= 59
        ):
            result.append(
                (
                    (sh, sm),
                    (eh, em),
                )
            )

    if result:
        return result

    # Hora única.
    values = re.findall(
        r"\b(\d{1,2})[:.](\d{2})\b",
        normalized,
    )

    for hour, minute in values:
        hour = int(hour)
        minute = int(minute)

        if (
            0 <= hour <= 23
            and 0 <= minute <= 59
        ):
            result.append(
                (
                    (hour, minute),
                    None,
                )
            )

    return result


def get_session_type(text):
    text = normalize(text)

    if (
        "FINAL" in text
        or "CARRERA" in text
    ):
        return "Carrera"

    if "SERIE" in text:
        return "Serie"

    if "CLASIFICACION" in text:
        return "Clasificación"

    if (
        "ENTRENAMIENTO" in text
        or "PRACTICA" in text
    ):
        return "Entrenamiento"

    return None


def get_category(text):
    text = normalize(text)

    if (
        "TCPK" in text
        or "TC PICK UP" in text
    ):
        return "TC Pick Up"

    if (
        re.search(
            r"\bTCP\b",
            text,
        )
        or "TC PISTA" in text
    ):
        return "TC Pista"

    if (
        re.search(
            r"\bTC\b",
            text,
        )
        or "TURISMO CARRETERA" in text
    ):
        return "TC"

    return None


def get_day(
    line,
    race_date,
):
    text = normalize(line)

    if "VIERNES" in text:
        return race_date - timedelta(
            days=2
        )

    if "SABADO" in text:
        return race_date - timedelta(
            days=1
        )

    if "DOMINGO" in text:
        return race_date

    return None


def make_name(text):
    name = normalize(text)

    name = re.sub(
        r"\b\d{1,2}[:.]\d{2}\s*(?:A|-|–)\s*\d{1,2}[:.]\d{2}\b",
        "",
        name,
    )

    name = re.sub(
        r"\b\d{1,2}[:.]\d{2}\b",
        "",
        name,
    )

    name = re.sub(
        r"\b(?:HS|HORA|HORAS)\b",
        "",
        name,
    )

    name = re.sub(
        r"\s+",
        " ",
        name,
    )

    return name.strip(
        " -|:;,.()"
    ) or "Actividad"


def parse_online_page(
    page,
    url,
    race,
    category,
):
    print(
        f"    Cronograma: {url}"
    )

    try:
        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        page.wait_for_timeout(
            1500
        )

    except Exception as error:
        print(
            f"    ERROR cronograma: "
            f"{error}"
        )

        return []

    text = page.locator(
        "body"
    ).inner_text()

    if not text:
        return []

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    events = []

    current_day = None
    current_category = None

    for line in lines:
        detected_day = get_day(
            line,
            race["date"],
        )

        if detected_day:
            current_day = detected_day
            continue

        detected_category = get_category(
            line
        )

        if detected_category:
            current_category = (
                detected_category
            )

        kind = get_session_type(
            line
        )

        if not kind:
            continue

        # Si ACTC no puso encabezado de categoría,
        # aceptamos la categoría de la URL/página.
        if (
            current_category
            and current_category
            != category["name"]
        ):
            continue

        times = extract_time_pairs(
            line
        )

        if not times:
            continue

        if current_day is None:
            if kind in (
                "Serie",
                "Carrera",
            ):
                current_day = race["date"]
            else:
                current_day = (
                    race["date"]
                    - timedelta(days=1)
                )

        name = make_name(
            line
        )

        for start, end in times:
            sh, sm = start

            start_dt = TZ.localize(
                datetime(
                    current_day.year,
                    current_day.month,
                    current_day.day,
                    sh,
                    sm,
                )
            )

            if end:
                eh, em = end

                end_dt = TZ.localize(
                    datetime(
                        current_day.year,
                        current_day.month,
                        current_day.day,
                        eh,
                        em,
                    )
                )

            else:
                end_dt = (
                    start_dt
                    + timedelta(
                        minutes=30
                    )
                )

            events.append(
                {
                    "date": current_day,
                    "inicio": start_dt,
                    "fin": end_dt,
                    "tipo": kind,
                    "nombre": name,
                    "fuente": url,
                }
            )

    unique = {}

    for event in events:
        key = (
            event["date"],
            event["inicio"],
            event["fin"],
            event["tipo"],
            normalize(
                event["nombre"]
            ),
        )

        unique[key] = event

    result = list(
        unique.values()
    )

    result.sort(
        key=lambda event:
        event["inicio"]
    )

    return result


def make_event(
    category,
    race,
    session,
):
    uid = (
        "actc-"
        + slug(category["name"])
        + "-"
        + session["date"].isoformat()
        + "-"
        + slug(session["tipo"])
        + "-"
        + slug(session["nombre"])
    )

    return {
        "uid": uid,
        "fecha_inicio": (
            session["inicio"].isoformat()
        ),
        "fecha_fin": (
            session["fin"].isoformat()
        ),
        "ubicacion": race["location"],
        "categoria": "Argentina",
        "campeonato": category[
            "championship"
        ],
        "tipo": session["tipo"],
        "nombre": session["nombre"],
        "descripcion": (
            f"Fecha {race['round']} "
            f"de {category['championship']}."
        ),
        "fuente": session["fuente"],
        "imperdible": (
            session["tipo"] == "Carrera"
        ),
        "round": race["round"],
    }


def process_category(
    page,
    category,
):
    print()
    print(
        f"Consultando ACTC: "
        f"{category['name']}"
    )

    races = extract_calendar_events(
        page,
        category,
    )

    print(
        f"  Fechas encontradas: "
        f"{len(races)}"
    )

    if not races:
        return []

    for race in races:
        print(
            f"  Fecha {race['round']}: "
            f"{race['date']} "
            f"{race['location']}"
        )

    result = []

    for race in races:
        print()
        print(
            f"  Fecha {race['round']}: "
            f"buscando carrera-online..."
        )

        online_url = find_carrera_online(
            page,
            category,
            race,
        )

        if not online_url:
            print(
                "    NO encontrada"
            )

            continue

        sessions = parse_online_page(
            page,
            online_url,
            race,
            category,
        )

        print(
            f"    Sesiones encontradas: "
            f"{len(sessions)}"
        )

        for session in sessions:
            result.append(
                make_event(
                    category,
                    race,
                    session,
                )
            )

    return result


def deduplicate(events):
    unique = {}

    for event in events:
        key = (
            event["uid"],
            event["fecha_inicio"],
            event["fecha_fin"],
        )

        unique[key] = event

    return list(
        unique.values()
    )


def main():
    print(
        f"Consultando ACTC para {YEAR}..."
    )

    all_events = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            locale="es-AR",
            timezone_id=(
                "America/Argentina/Buenos_Aires"
            ),
            viewport={
                "width": 1440,
                "height": 1200,
            },
        )

        for category in CATEGORIES:
            try:
                events = process_category(
                    page,
                    category,
                )

                all_events.extend(
                    events
                )

            except Exception as error:
                print(
                    f"  ERROR en "
                    f"{category['name']}: "
                    f"{error}"
                )

        browser.close()

    all_events = deduplicate(
        all_events
    )

    all_events.sort(
        key=lambda event:
        event["fecha_inicio"]
    )

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            all_events,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print(
        f"ACTC: "
        f"{len(all_events)} eventos guardados "
        f"en {OUTPUT}"
    )

    print()
    print(
        "Resumen por campeonato:"
    )

    championships = {}

    for event in all_events:
        championships[
            event["campeonato"]
        ] = (
            championships.get(
                event["campeonato"],
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

    for event in all_events:
        types[event["tipo"]] = (
            types.get(
                event["tipo"],
                0,
            )
            + 1
        )

    for name in sorted(types):
        print(
            f"  {name}: "
            f"{types[name]}"
        )


if __name__ == "__main__":
    main()
