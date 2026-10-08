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
        char
        for char in text
        if unicodedata.category(char) != "Mn"
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


def parse_date_from_text(text):
    text = normalize(text)

    patterns = [
        r"\b(\d{1,2})\s+([A-Z]+)\s+(20\d{2})\b",
        r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b",
        r"\b(\d{1,2})-(\d{1,2})-(20\d{2})\b",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
        )

        if not match:
            continue

        try:
            if pattern.endswith(
                r"(20\d{2})\b"
            ) and match.group(2).isalpha():
                day = int(match.group(1))
                month = MONTHS.get(
                    match.group(2)
                )
                year = int(match.group(3))

                if month:
                    return datetime(
                        year,
                        month,
                        day,
                    ).date()

            else:
                day = int(match.group(1))
                month = int(match.group(2))
                year = int(match.group(3))

                return datetime(
                    year,
                    month,
                    day,
                ).date()

        except Exception:
            pass

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

    page.wait_for_timeout(2000)

    links = page.locator("a").all()

    events = []

    current_round = None
    current_location = None

    for link in links:
        try:
            text = link.inner_text().strip()
            href = link.get_attribute("href")

            if not text:
                continue

            normalized = normalize(text)

            round_match = re.search(
                r"FECHA\s+(\d+)",
                normalized,
            )

            if round_match:
                current_round = int(
                    round_match.group(1)
                )

                current_location = (
                    normalized
                    .replace(
                        f"FECHA {current_round}",
                        "",
                    )
                    .strip(
                        " —–-"
                    )
                )

            date = parse_date_from_text(
                text
            )

            if (
                date
                and date.year == YEAR
                and current_round is not None
            ):
                result_url = None

                if href:
                    result_url = urljoin(
                        category[
                            "calendar_url"
                        ],
                        href,
                    )

                key = (
                    current_round,
                    date.isoformat(),
                )

                if not any(
                    event["_key"] == key
                    for event in events
                ):
                    events.append(
                        {
                            "_key": key,
                            "round": current_round,
                            "date": date,
                            "location": current_location,
                            "result_url": result_url,
                        }
                    )

        except Exception:
            continue

    # La estructura del calendario puede tener
    # fecha y botón "Ver resultados" en elementos
    # distintos. Si faltan URLs, hacemos una segunda
    # pasada buscando los enlaces de resultados.
    if events:
        result_links = []

        for link in links:
            try:
                href = link.get_attribute(
                    "href"
                )

                text = normalize(
                    link.inner_text()
                )

                if (
                    href
                    and (
                        "RESULTADOS" in text
                        or "/resultados" in href
                    )
                ):
                    result_links.append(
                        urljoin(
                            category[
                                "calendar_url"
                            ],
                            href,
                        )
                    )

            except Exception:
                continue

        result_links = list(
            dict.fromkeys(
                result_links
            )
        )

        for event in events:
            if event["result_url"]:
                continue

            candidates = [
                url
                for url in result_links
                if (
                    f"fecha={event['round']}"
                    in url.lower()
                )
            ]

            if candidates:
                event["result_url"] = (
                    candidates[0]
                )

    events.sort(
        key=lambda event:
        event["round"]
    )

    return events


def find_carrera_online_from_result(
    page,
    result_url,
):
    if not result_url:
        return None

    print(
        f"    Resultados: {result_url}"
    )

    try:
        page.goto(
            result_url,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        page.wait_for_timeout(1200)

    except Exception as error:
        print(
            f"      Error abriendo resultados: "
            f"{error}"
        )

        return None

    # Primero buscamos un enlace directo.
    anchors = page.locator(
        "a"
    ).all()

    candidates = []

    for anchor in anchors:
        try:
            href = anchor.get_attribute(
                "href"
            )

            text = normalize(
                anchor.inner_text()
            )

            if not href:
                continue

            full_url = urljoin(
                result_url,
                href,
            )

            if (
                "/carrera-online/"
                in full_url
            ):
                candidates.append(
                    full_url
                )

                continue

            if (
                "CRONOGRAMA"
                in text
                and "/carrera-online/"
                in full_url
            ):
                candidates.append(
                    full_url
                )

        except Exception:
            continue

    if candidates:
        # Preferimos explícitamente /cronograma/.
        for candidate in candidates:
            if "/cronograma/" in candidate:
                return candidate

        return candidates[0]

    # Si no aparece como <a>, buscamos la URL
    # directamente en el HTML.
    try:
        html = page.content()

        matches = re.findall(
            r'https?://[^"\']+/carrera-online/[^"\']+',
            html,
            flags=re.IGNORECASE,
        )

        if matches:
            for match in matches:
                if "/cronograma/" in match:
                    return match

            return matches[0]

    except Exception:
        pass

    return None


def find_carrera_online_by_search(
    page,
    category,
    race,
):
    """
    Último recurso.

    ACTC usa una estructura estable para carrera-online:
    
    /categoria/carrera-online/AÑO/cronograma/...

    Buscamos dentro del HTML del calendario y de
    resultados cualquier referencia que contenga:
    
        carrera-online
        fecha-N
    """

    urls_to_check = [
        category["calendar_url"],
    ]

    if race.get("result_url"):
        urls_to_check.append(
            race["result_url"]
        )

    target = (
        f"fecha-{race['round']}"
    )

    for url in urls_to_check:
        try:
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.wait_for_timeout(
                700
            )

            html = page.content()

            matches = re.findall(
                r'(?:https?:)?//[^"\']*carrera-online/[^"\']+',
                html,
                flags=re.IGNORECASE,
            )

            for match in matches:
                match = match.replace(
                    "&amp;",
                    "&",
                )

                if target in match.lower():
                    if match.startswith("//"):
                        match = (
                            "https:"
                            + match
                        )

                    return urljoin(
                        url,
                        match,
                    )

        except Exception:
            continue

    return None


def extract_clock_pairs(text):
    normalized = normalize(text)

    pairs = []

    patterns = [
        r"\b(\d{1,2}):(\d{2})\s*(?:A|-|–)\s*(\d{1,2}):(\d{2})\b",
        r"\b(\d{1,2})\.(\d{2})\s*(?:A|-|–)\s*(\d{1,2})\.(\d{2})\b",
    ]

    for pattern in patterns:
        for match in re.finditer(
            pattern,
            normalized,
        ):
            sh = int(match.group(1))
            sm = int(match.group(2))
            eh = int(match.group(3))
            em = int(match.group(4))

            if (
                0 <= sh <= 23
                and 0 <= sm <= 59
                and 0 <= eh <= 23
                and 0 <= em <= 59
            ):
                pairs.append(
                    (
                        (sh, sm),
                        (eh, em),
                    )
                )

    if pairs:
        return pairs

    # Una sola hora.
    single_patterns = [
        r"\b(\d{1,2}):(\d{2})\b",
        r"\b(\d{1,2})\.(\d{2})\b",
    ]

    for pattern in single_patterns:
        for match in re.finditer(
            pattern,
            normalized,
        ):
            hour = int(
                match.group(1)
            )

            minute = int(
                match.group(2)
            )

            if (
                0 <= hour <= 23
                and 0 <= minute <= 59
            ):
                pairs.append(
                    (
                        (hour, minute),
                        None,
                    )
                )

    return pairs


def session_type(text):
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


def session_name(text):
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
        " -|:;,."
    ) or "Actividad"


def detect_category(text):
    text = normalize(text)

    if (
        re.search(
            r"\bTCPK\b",
            text,
        )
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


def detect_day(
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

    # Si la página dice solamente "Sabado /"
    # o "Domingo /", ya quedó contemplado arriba.
    return None


def build_datetime(
    date,
    clock,
):
    hour, minute = clock

    return TZ.localize(
        datetime(
            date.year,
            date.month,
            date.day,
            hour,
            minute,
        )
    )


def parse_carrera_online(
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
            1200
        )

    except Exception as error:
        print(
            f"      Error abriendo cronograma: "
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
    active_category = category["name"]

    for line in lines:
        normalized = normalize(line)

        day = detect_day(
            line,
            race["date"],
        )

        if day:
            current_day = day
            continue

        detected_category = (
            detect_category(line)
        )

        if detected_category:
            active_category = (
                detected_category
            )

        kind = session_type(line)

        if not kind:
            continue

        # Algunas páginas tienen texto de resultados
        # junto al nombre. No queremos generar eventos
        # desde eso.
        if (
            "RESULTADOS" in normalized
            and not (
                "ENTRENAMIENTO"
                in normalized
                or "CLASIFICACION"
                in normalized
                or "SERIE"
                in normalized
                or "FINAL" in normalized
            )
        ):
            continue

        clocks = extract_clock_pairs(
            line
        )

        if not clocks:
            continue

        if (
            active_category
            != category["name"]
        ):
            continue

        # Si no encontramos "Sabado/Domingo",
        # inferimos según el tipo.
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

        name = session_name(
            line
        )

        for start, end in clocks:
            start_dt = build_datetime(
                current_day,
                start,
            )

            if end:
                end_dt = build_datetime(
                    current_day,
                    end,
                )
            else:
                # Cuando ACTC publica únicamente
                # la hora de inicio, usamos 30 minutos.
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

    # Eliminar duplicados.
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

    events = list(
        unique.values()
    )

    events.sort(
        key=lambda event:
        event["inicio"]
    )

    return events


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

    for race in races:
        print(
            f"  Fecha {race['round']}: "
            f"{race['date']} "
            f"{race['location']}"
        )

    if not races:
        return []

    events = []

    for race in races:
        print()
        print(
            f"  Procesando Fecha "
            f"{race['round']}: "
            f"{race['location']}"
        )

        online_url = None

        # 1. Intentamos descubrir carrera-online
        # desde la página de resultados.
        if race.get("result_url"):
            online_url = (
                find_carrera_online_from_result(
                    page,
                    race["result_url"],
                )
            )

        # 2. Si no apareció, buscamos la referencia
        # directamente en las páginas.
        if not online_url:
            online_url = (
                find_carrera_online_by_search(
                    page,
                    category,
                    race,
                )
            )

        if not online_url:
            print(
                "    ADVERTENCIA: "
                "no se encontró carrera-online."
            )

            continue

        sessions = parse_carrera_online(
            page,
            online_url,
            race,
            category,
        )

        print(
            f"    Horarios encontrados: "
            f"{len(sessions)}"
        )

        for session in sessions:
            events.append(
                make_event(
                    category,
                    race,
                    session,
                )
            )

    return events


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
        name = event["campeonato"]

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

    for event in all_events:
        name = event["tipo"]

        types[name] = (
            types.get(
                name,
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
