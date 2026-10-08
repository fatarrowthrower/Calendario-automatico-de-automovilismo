import io
import json
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import pytz
import requests
from pypdf import PdfReader
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
        "results_url": "https://actc.org.ar/tc/resultados",
        "home_url": "https://actc.org.ar/tc",
    },
    {
        "name": "TC Pista",
        "championship": "TC Pista",
        "calendar_url": "https://actc.org.ar/tcp/calendario",
        "results_url": "https://actc.org.ar/tcp/resultados",
        "home_url": "https://actc.org.ar/tcp",
    },
    {
        "name": "TC Pick Up",
        "championship": "TC Pick Up",
        "calendar_url": "https://actc.org.ar/tcpk/calendario",
        "results_url": "https://actc.org.ar/tcpk/resultados",
        "home_url": "https://actc.org.ar/tcpk",
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


def parse_date(text):
    text = normalize(text)

    match = re.search(
        r"\b(\d{1,2})\s+([A-Z]+)\s+(20\d{2})\b",
        text,
    )

    if match:
        day = int(match.group(1))
        month = MONTHS.get(
            match.group(2)
        )
        year = int(match.group(3))

        if month:
            try:
                return datetime(
                    year,
                    month,
                    day,
                ).date()
            except ValueError:
                pass

    match = re.search(
        r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b",
        text,
    )

    if match:
        try:
            return datetime(
                int(match.group(3)),
                int(match.group(2)),
                int(match.group(1)),
            ).date()
        except ValueError:
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

    page.wait_for_timeout(
        2500
    )

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

        date = parse_date(
            line
        )

        if not date:
            continue

        if date.year != YEAR:
            continue

        key = (
            current_round,
            date.isoformat(),
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

    # Fallback: algunas versiones del HTML
    # separan "Fecha N" y la fecha.
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
                date = parse_date(
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
                        ),
                        "round": round_number,
                        "date": date,
                        "location": location,
                    }
                )

                break

    events.sort(
        key=lambda event:
        event["round"]
    )

    return events


def get_result_url(
    category,
    race,
):
    return (
        f"{category['results_url']}"
        f"?year={YEAR}"
        f"&fecha={race['round']}"
    )


def extract_pdf_links(
    page,
    category,
    race,
):
    url = get_result_url(
        category,
        race,
    )

    print(
        f"    Resultados: {url}"
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
            f"    Error resultados: "
            f"{error}"
        )

        return []

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

            full_url = urljoin(
                url,
                href,
            )

            if (
                ".pdf"
                not in full_url.lower()
            ):
                continue

            text = normalize(
                anchor.inner_text()
            )

            links.append(
                {
                    "url": full_url,
                    "text": text,
                }
            )

        except Exception:
            continue

    unique = {}

    for item in links:
        unique[
            item["url"]
        ] = item

    return list(
        unique.values()
    )


def download_pdf_text(
    url,
):
    try:
        response = requests.get(
            url,
            timeout=45,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(X11; Linux x86_64) "
                    "AppleWebKit/537.36 "
                    "Chrome/131 Safari/537.36"
                )
            },
        )

        response.raise_for_status()

        reader = PdfReader(
            io.BytesIO(
                response.content
            )
        )

        pages = []

        for pdf_page in reader.pages:
            try:
                pages.append(
                    pdf_page.extract_text()
                    or ""
                )
            except Exception:
                continue

        return "\n".join(
            pages
        )

    except Exception as error:
        print(
            f"      Error PDF: "
            f"{error}"
        )

        return ""


def classify_session(
    text,
):
    normalized = normalize(
        text
    )

    if (
        "FINAL" in normalized
        or "CARRERA" in normalized
    ):
        return "Carrera"

    if "SERIE" in normalized:
        return "Serie"

    if "CLASIFICACION" in normalized:
        return "Clasificación"

    if "ENTRENAMIENTO" in normalized:
        return "Entrenamiento"

    return None


def extract_start_time(
    text,
):
    normalized = normalize(
        text
    )

    # Ejemplo:
    # 14/2/2026 15:55
    matches = re.findall(
        r"\b\d{1,2}/\d{1,2}/20\d{2}\s+(\d{1,2}):(\d{2})\b",
        normalized,
    )

    if matches:
        hour = int(
            matches[-1][0]
        )

        minute = int(
            matches[-1][1]
        )

        return (
            hour,
            minute,
        )

    # Ejemplo:
    # iniciado a 15:55:05
    matches = re.findall(
        r"(?:INICIADO|INICIO|STARTED)\s+A\s+(\d{1,2}):(\d{2})",
        normalized,
    )

    if matches:
        hour = int(
            matches[-1][0]
        )

        minute = int(
            matches[-1][1]
        )

        return (
            hour,
            minute,
        )

    return None


def session_date_from_pdf(
    text,
    fallback,
):
    normalized = normalize(
        text
    )

    match = re.search(
        r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b",
        normalized,
    )

    if match:
        try:
            return datetime(
                int(match.group(3)),
                int(match.group(2)),
                int(match.group(1)),
            ).date()
        except ValueError:
            pass

    return fallback


def duration_for_session(
    session_type,
):
    if session_type == "Carrera":
        return 60

    if session_type == "Serie":
        return 25

    if session_type == "Clasificación":
        return 20

    return 30


def make_event(
    category,
    race,
    date,
    start,
    session_type,
    name,
    source,
):
    hour, minute = start

    start_dt = TZ.localize(
        datetime(
            date.year,
            date.month,
            date.day,
            hour,
            minute,
        )
    )

    end_dt = (
        start_dt
        + timedelta(
            minutes=duration_for_session(
                session_type
            )
        )
    )

    return {
        "uid": (
            "actc-"
            + slug(category["name"])
            + "-"
            + date.isoformat()
            + "-"
            + slug(session_type)
            + "-"
            + slug(name)
        ),
        "fecha_inicio": (
            start_dt.isoformat()
        ),
        "fecha_fin": (
            end_dt.isoformat()
        ),
        "ubicacion": race[
            "location"
        ],
        "categoria": "Argentina",
        "campeonato": category[
            "championship"
        ],
        "tipo": session_type,
        "nombre": name,
        "descripcion": (
            f"Fecha {race['round']} "
            f"de {category['championship']}."
        ),
        "fuente": source,
        "imperdible": (
            session_type == "Carrera"
        ),
        "round": race["round"],
    }


def parse_pdf(
    pdf_text,
    pdf_name,
    category,
    race,
):
    if not pdf_text:
        return None

    session_type = classify_session(
        pdf_name
        + "\n"
        + pdf_text
    )

    if not session_type:
        return None

    start = extract_start_time(
        pdf_text
    )

    if not start:
        return None

    date = session_date_from_pdf(
        pdf_text,
        race["date"],
    )

    name = normalize(
        pdf_name
    )

    if not name:
        name = session_type

    return {
        "date": date,
        "start": start,
        "type": session_type,
        "name": name,
    }


def process_results(
    page,
    category,
    race,
):
    pdf_links = extract_pdf_links(
        page,
        category,
        race,
    )

    if not pdf_links:
        print(
            "      PDFs encontrados: 0"
        )

        return []

    print(
        f"      PDFs encontrados: "
        f"{len(pdf_links)}"
    )

    sessions = []

    for item in pdf_links:
        text = download_pdf_text(
            item["url"]
        )

        parsed = parse_pdf(
            text,
            item["text"],
            category,
            race,
        )

        if not parsed:
            continue

        sessions.append(
            (
                parsed,
                item["url"],
            )
        )

    unique = {}

    for parsed, source in sessions:
        key = (
            parsed["date"],
            parsed["start"],
            parsed["type"],
            normalize(
                parsed["name"]
            ),
        )

        unique[key] = (
            parsed,
            source,
        )

    result = []

    for parsed, source in unique.values():
        result.append(
            make_event(
                category,
                race,
                parsed["date"],
                parsed["start"],
                parsed["type"],
                parsed["name"],
                source,
            )
        )

    return result


def find_next_race(
    races,
):
    today = datetime.now(
        TZ
    ).date()

    future = [
        race
        for race in races
        if race["date"] >= today
    ]

    if not future:
        return None

    return min(
        future,
        key=lambda race:
        race["date"]
    )


def find_cronograma_from_home(
    page,
    category,
    race,
):
    """
    Para la próxima fecha ACTC suele mostrar
    el botón "Cronograma" en la página principal
    de la categoría.

    Lo buscamos solamente para la próxima fecha,
    porque es la que ACTC mantiene publicada.
    """

    print(
        f"    Buscando cronograma próximo "
        f"en {category['home_url']}"
    )

    try:
        page.goto(
            category["home_url"],
            wait_until="domcontentloaded",
            timeout=60000,
        )

        page.wait_for_timeout(
            1500
        )

    except Exception:
        return None

    links = []

    for anchor in page.locator(
        "a"
    ).all():
        try:
            href = anchor.get_attribute(
                "href"
            )

            text = normalize(
                anchor.inner_text()
            )

            if not href:
                continue

            full = urljoin(
                category["home_url"],
                href,
            )

            if (
                "CRONOGRAMA" in text
                and (
                    "/carrera-online/"
                    in full.lower()
                    or "cronograma"
                    in full.lower()
                )
            ):
                links.append(
                    full
                )

        except Exception:
            continue

    if links:
        return links[0]

    # Puede ser un botón con onclick.
    try:
        html = page.content()

        matches = re.findall(
            r"""(?:https?:)?//[^"'\\s<>]+(?:cronograma|carrera-online)[^"'\\s<>]*""",
            html,
            flags=re.IGNORECASE,
        )

        for match in matches:
            if match.startswith("//"):
                match = "https:" + match

            return urljoin(
                category["home_url"],
                match,
            )

    except Exception:
        pass

    return None


def parse_cronograma(
    page,
    url,
    category,
    race,
):
    if not url:
        return []

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

    except Exception:
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

    current_date = None

    for line in lines:
        normalized = normalize(
            line
        )

        if "VIERNES" in normalized:
            current_date = (
                race["date"]
                - timedelta(days=2)
            )
            continue

        if "SABADO" in normalized:
            current_date = (
                race["date"]
                - timedelta(days=1)
            )
            continue

        if "DOMINGO" in normalized:
            current_date = race[
                "date"
            ]
            continue

        kind = classify_session(
            line
        )

        if not kind:
            continue

        times = re.findall(
            r"\b(\d{1,2}):(\d{2})\s*(?:A|-|–)\s*(\d{1,2}):(\d{2})\b",
            normalized,
        )

        if not times:
            continue

        if current_date is None:
            current_date = (
                race["date"]
                - timedelta(days=1)
            )

        for sh, sm, eh, em in times:
            start = (
                int(sh),
                int(sm),
            )

            end = (
                int(eh),
                int(em),
            )

            start_dt = TZ.localize(
                datetime(
                    current_date.year,
                    current_date.month,
                    current_date.day,
                    start[0],
                    start[1],
                )
            )

            end_dt = TZ.localize(
                datetime(
                    current_date.year,
                    current_date.month,
                    current_date.day,
                    end[0],
                    end[1],
                )
            )

            events.append(
                {
                    "uid": (
                        "actc-"
                        + slug(category["name"])
                        + "-"
                        + current_date.isoformat()
                        + "-"
                        + slug(kind)
                        + "-"
                        + slug(line)
                    ),
                    "fecha_inicio": (
                        start_dt.isoformat()
                    ),
                    "fecha_fin": (
                        end_dt.isoformat()
                    ),
                    "ubicacion": race[
                        "location"
                    ],
                    "categoria": "Argentina",
                    "campeonato": category[
                        "championship"
                    ],
                    "tipo": kind,
                    "nombre": line,
                    "descripcion": (
                        f"Fecha {race['round']} "
                        f"de {category['championship']}."
                    ),
                    "fuente": url,
                    "imperdible": (
                        kind == "Carrera"
                    ),
                    "round": race["round"],
                }
            )

    return events


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

    today = datetime.now(
        TZ
    ).date()

    next_race = find_next_race(
        races
    )

    for race in races:
        print()
        print(
            f"  Fecha {race['round']}: "
            f"{race['location']}"
        )

        # Fechas ya disputadas:
        # usamos los PDFs oficiales.
        if race["date"] < today:
            events = process_results(
                page,
                category,
                race,
            )

            print(
                f"      Sesiones con horario: "
                f"{len(events)}"
            )

            result.extend(
                events
            )

            continue

        # Próxima fecha:
        # intentamos cronograma oficial.
        if (
            next_race
            and race["round"]
            == next_race["round"]
        ):
            cronograma = (
                find_cronograma_from_home(
                    page,
                    category,
                    race,
                )
            )

            if cronograma:
                events = parse_cronograma(
                    page,
                    cronograma,
                    category,
                    race,
                )

                print(
                    f"      Sesiones del cronograma: "
                    f"{len(events)}"
                )

                result.extend(
                    events
                )

            else:
                print(
                    "      Cronograma todavía "
                    "no publicado."
                )

        else:
            print(
                "      Fecha futura: "
                "sin cronograma publicado."
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
