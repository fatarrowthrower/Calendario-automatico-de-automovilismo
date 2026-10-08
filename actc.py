import json
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

import pytz
from playwright.sync_api import sync_playwright


YEAR = datetime.now().year
TZ = pytz.timezone("America/Argentina/Buenos_Aires")

OUTPUT = Path("data/actc_events.json")


CATEGORIES = [
    {
        "name": "TC",
        "championship": "Turismo Carretera",
        "calendar_url": "https://actc.org.ar/tc/calendario",
        "news_url": "https://actc.org.ar/tc/noticias",
    },
    {
        "name": "TC Pista",
        "championship": "TC Pista",
        "calendar_url": "https://actc.org.ar/tcp/calendario",
        "news_url": "https://actc.org.ar/tcp/noticias",
    },
    {
        "name": "TC Pick Up",
        "championship": "TC Pick Up",
        "calendar_url": "https://actc.org.ar/tcpk/calendario",
        "news_url": "https://actc.org.ar/tcpk/noticias",
    },
]


MONTHS = {
    "ENERO": 1,
    "FEBRERO": 2,
    "MARZO": 3,
    "ABRIL": 4,
    "MAYO": 5,
    "JUNIO": 6,
    "JULIO": 7,
    "AGOSTO": 8,
    "SEPTIEMBRE": 9,
    "SETIEMBRE": 9,
    "OCTUBRE": 10,
    "NOVIEMBRE": 11,
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


def parse_date(day, month, year):
    try:
        return datetime(
            int(year),
            MONTHS[normalize(month)],
            int(day),
        ).date()
    except Exception:
        return None


def extract_calendar_events(page, category):
    print(
        f"  Abriendo calendario: "
        f"{category['calendar_url']}"
    )

    page.goto(
        category["calendar_url"],
        wait_until="domcontentloaded",
        timeout=60000,
    )

    page.wait_for_timeout(3000)

    text = page.locator("body").inner_text()

    normalized = normalize(text)

    events = []

    # ---------------------------------------------------------
    # FORMATO 1
    #
    # Fecha 1
    # 15
    # FEBRERO
    # 2026
    # EL CALAFATE
    # ---------------------------------------------------------

    pattern_1 = re.compile(
        r"""
        FECHA\s+(?P<round>\d+)
        .*?
        (?P<day>\d{1,2})
        \s+
        (?P<month>ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|
                  JULIO|AGOSTO|SEPTIEMBRE|SETIEMBRE|OCTUBRE|
                  NOVIEMBRE|DICIEMBRE)
        \s+
        (?P<year>20\d{2})
        .*?
        (?P<location>
            EL\s+CALAFATE|
            CALAFATE|
            VIEDMA|
            CENTENARIO|
            CONCEPCION\s+DEL\s+URUGUAY|
            TERMAS\s+DE\s+RIO\s+HONDO|
            ALTA\s+GRACIA|
            RAFAELA|
            POSADAS|
            ALBARDON|
            ALBARDÓN|
            PARANA|
            PARANÁ|
            SAN\s+LUIS|
            SAN\s+NICOLAS|
            SAN\s+NICOLÁS|
            ROSARIO|
            RIO\s+CUARTO|
            RÍO\s+CUARTO|
            LA\s+PLATA|
            BALCARCE|
            [A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ]{3,40}
        )
        """,
        re.I | re.X | re.S,
    )

    for match in pattern_1.finditer(normalized):
        date = parse_date(
            match.group("day"),
            match.group("month"),
            match.group("year"),
        )

        if not date or date.year != YEAR:
            continue

        round_number = int(
            match.group("round")
        )

        location = normalize(
            match.group("location")
        )

        events.append(
            {
                "round": round_number,
                "date": date,
                "location": location,
            }
        )

    # ---------------------------------------------------------
    # FORMATO 2
    #
    # Busca bloques "Fecha N" y toma la fecha que aparece
    # inmediatamente después.
    # ---------------------------------------------------------

    if len(events) < 5:
        pattern_2 = re.compile(
            r"""
            FECHA\s+(?P<round>\d+)
            (?P<block>.{0,500})
            """,
            re.I | re.X | re.S,
        )

        for match in pattern_2.finditer(normalized):
            round_number = int(
                match.group("round")
            )

            block = match.group("block")

            date_match = re.search(
                r"""
                (?P<day>\d{1,2})
                \s+
                (?P<month>ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|
                          JULIO|AGOSTO|SEPTIEMBRE|SETIEMBRE|OCTUBRE|
                          NOVIEMBRE|DICIEMBRE)
                \s+
                (?P<year>20\d{2})
                """,
                block,
                re.I | re.X,
            )

            if not date_match:
                continue

            date = parse_date(
                date_match.group("day"),
                date_match.group("month"),
                date_match.group("year"),
            )

            if not date or date.year != YEAR:
                continue

            before = block[
                :date_match.start()
            ]

            after = block[
                date_match.end():
            ]

            location = None

            location_candidates = [
                "CALAFATE",
                "VIEDMA",
                "CENTENARIO",
                "CONCEPCION DEL URUGUAY",
                "TERMAS DE RIO HONDO",
                "ALTA GRACIA",
                "RAFAELA",
                "POSADAS",
                "ALBARDON",
                "PARANA",
                "SAN LUIS",
                "SAN NICOLAS",
                "ROSARIO",
                "RIO CUARTO",
                "LA PLATA",
                "BALCARCE",
            ]

            combined = (
                before[-200:]
                + " "
                + after[:200]
            )

            for candidate in location_candidates:
                if candidate in combined:
                    location = candidate
                    break

            if not location:
                location = "Argentina"

            events.append(
                {
                    "round": round_number,
                    "date": date,
                    "location": location,
                }
            )

    # ---------------------------------------------------------
    # ELIMINAR DUPLICADOS
    # ---------------------------------------------------------

    unique = {}

    for event in events:
        key = (
            event["round"],
            event["date"],
            normalize(event["location"]),
        )

        unique[key] = event

    events = list(unique.values())

    events.sort(
        key=lambda item: item["round"]
    )

    return events


def extract_news_links(page, category):
    print(
        f"  Buscando noticias: "
        f"{category['news_url']}"
    )

    page.goto(
        category["news_url"],
        wait_until="domcontentloaded",
        timeout=60000,
    )

    page.wait_for_timeout(1500)

    links = []

    for element in page.locator("a").all():
        try:
            href = element.get_attribute(
                "href"
            )

            if not href:
                continue

            if "/noticias/" not in href:
                continue

            if href.startswith("/"):
                href = (
                    "https://actc.org.ar"
                    + href
                )

            title = element.inner_text().strip()

            links.append(
                {
                    "url": href,
                    "title": title,
                }
            )

        except Exception:
            continue

    unique = {}

    for item in links:
        unique[item["url"]] = item

    return list(unique.values())


def load_article(page, article):
    try:
        page.goto(
            article["url"],
            wait_until="domcontentloaded",
            timeout=60000,
        )

        page.wait_for_timeout(400)

        text = page.locator(
            "body"
        ).inner_text()

        return text or ""

    except Exception:
        return ""


def article_score(
    article_text,
    article_title,
    race,
    category,
):
    text = normalize(
        article_text
        + " "
        + article_title
    )

    score = 0

    location = normalize(
        race["location"]
    )

    if location and location in text:
        score += 30

    if (
        f"FECHA {race['round']}"
        in text
    ):
        score += 30

    # Nombres alternativos.
    aliases = {
        "SAN NICOLAS": [
            "SAN NICOLAS",
            "SAN NICOLÁS",
        ],
        "RIO CUARTO": [
            "RIO CUARTO",
            "RÍO CUARTO",
        ],
        "PARANA": [
            "PARANA",
            "PARANÁ",
        ],
        "ALBARDON": [
            "ALBARDON",
            "ALBARDÓN",
        ],
        "CONCEPCION DEL URUGUAY": [
            "CONCEPCION DEL URUGUAY",
            "CONCEPCIÓN DEL URUGUAY",
        ],
        "TERMAS DE RIO HONDO": [
            "TERMAS DE RIO HONDO",
            "TERMAS DE RÍO HONDO",
        ],
    }

    aliases_for_location = aliases.get(
        location,
        [location],
    )

    for alias in aliases_for_location:
        if alias in text:
            score += 15
            break

    if "HORARIOS" in text:
        score += 15

    if "CRONOGRAMA" in text:
        score += 15

    if category["name"] == "TC":
        if (
            "TURISMO CARRETERA"
            in text
        ):
            score += 10

    elif category["name"] == "TC Pista":
        if "TC PISTA" in text:
            score += 10

    elif category["name"] == "TC Pick Up":
        if (
            "TC PICK UP" in text
            or "TCPK" in text
        ):
            score += 10

    return score


def parse_time(value):
    value = value.strip()
    value = value.replace(".", ":")

    match = re.fullmatch(
        r"(\d{1,2}):(\d{2})",
        value,
    )

    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))

    if hour > 23:
        return None

    if minute > 59:
        return None

    return hour, minute


def extract_times(line):
    line = normalize(line)

    result = []

    # 10:15 A 10:45
    for start, end in re.findall(
        r"(\d{1,2}[:.]\d{2})\s+A\s+(\d{1,2}[:.]\d{2})",
        line,
    ):
        a = parse_time(start)
        b = parse_time(end)

        if a and b:
            result.append((a, b))

    # 10:15 HS
    if not result:
        for value in re.findall(
            r"\b(\d{1,2}[:.]\d{2})\s*(?:HS|H)?\b",
            line,
        ):
            a = parse_time(value)

            if a:
                result.append(
                    (
                        a,
                        None,
                    )
                )

    return result


def get_session_type(line):
    text = normalize(line)

    if "CLASIFICACION" in text:
        return "Clasificación"

    if "ENTRENAMIENTO" in text:
        return "Entrenamiento"

    if "SERIE" in text:
        return "Serie"

    if (
        "CARRERA" in text
        or "FINAL" in text
    ):
        return "Carrera"

    return None


def line_matches_category(
    line,
    category,
):
    text = normalize(line)

    if category["name"] == "TC":
        return (
            "TURISMO CARRETERA" in text
            or re.search(
                r"\bTC\b",
                text,
            ) is not None
        ) and (
            "TC PISTA" not in text
            and "TC PICK UP" not in text
            and "TCPK" not in text
        )

    if category["name"] == "TC Pista":
        return (
            "TC PISTA" in text
            or re.search(
                r"\bTCP\b",
                text,
            ) is not None
        )

    if category["name"] == "TC Pick Up":
        return (
            "TC PICK UP" in text
            or "TCPK" in text
        )

    return False


def parse_article(
    article,
    race,
    category,
):
    text = article["text"]

    if not text:
        return []

    normalized = normalize(text)

    location = normalize(
        race["location"]
    )

    if (
        location not in normalized
        and f"FECHA {race['round']}"
        not in normalized
    ):
        return []

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    events = []

    current_day_offset = 0

    for line in lines:
        normalized_line = normalize(line)

        if "SABADO" in normalized_line:
            current_day_offset = 0

        elif "DOMINGO" in normalized_line:
            current_day_offset = 1

        elif "VIERNES" in normalized_line:
            current_day_offset = -1

        if not line_matches_category(
            line,
            category,
        ):
            continue

        session = get_session_type(
            line
        )

        if not session:
            continue

        times = extract_times(line)

        if not times:
            continue

        for start, end in times:
            start_hour, start_minute = start

            if end:
                end_hour, end_minute = end
            else:
                end_hour = start_hour
                end_minute = start_minute + 30

                if end_minute >= 60:
                    end_hour += 1
                    end_minute -= 60

            date = (
                race["date"]
                + timedelta(
                    days=current_day_offset
                )
            )

            start_dt = TZ.localize(
                datetime(
                    date.year,
                    date.month,
                    date.day,
                    start_hour,
                    start_minute,
                )
            )

            end_dt = TZ.localize(
                datetime(
                    date.year,
                    date.month,
                    date.day,
                    end_hour,
                    end_minute,
                )
            )

            name = re.sub(
                r"\b\d{1,2}[:.]\d{2}\s*(?:A\s*\d{1,2}[:.]\d{2})?\s*(?:HS|H)?\b",
                "",
                line,
                flags=re.I,
            )

            name = re.sub(
                r"\s+",
                " ",
                name,
            ).strip(
                " -|:"
            )

            if not name:
                name = session

            events.append(
                {
                    "date": date,
                    "inicio": start_dt,
                    "fin": end_dt,
                    "tipo": session,
                    "nombre": name,
                    "fuente": article["url"],
                }
            )

    return events


def make_event(
    category,
    race,
    session,
):
    uid = (
        f"actc-"
        f"{slug(category['name'])}-"
        f"{session['date'].isoformat()}-"
        f"{slug(session['tipo'])}-"
        f"{slug(session['nombre'])}"
    )

    return {
        "uid": uid,
        "fecha_inicio": session[
            "inicio"
        ].isoformat(),
        "fecha_fin": session[
            "fin"
        ].isoformat(),
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


def deduplicate(events):
    unique = {}

    for event in events:
        key = (
            event["uid"],
            event["fecha_inicio"],
            event["fecha_fin"],
        )

        unique[key] = event

    return list(unique.values())


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

    expected = {
        "TC": 15,
        "TC Pista": 15,
        "TC Pick Up": 11,
    }[category["name"]]

    if len(races) != expected:
        print(
            f"  ADVERTENCIA: "
            f"se esperaban {expected} "
            f"fechas."
        )

    if not races:
        print(
            "  ERROR: no se pudo leer "
            "el calendario."
        )

        return []

    for race in races:
        print(
            f"  Fecha {race['round']}: "
            f"{race['date']} "
            f"{race['location']}"
        )

    links = extract_news_links(
        page,
        category,
    )

    print(
        f"  Noticias visibles: "
        f"{len(links)}"
    )

    articles = []

    limit = min(
        len(links),
        40,
    )

    for index in range(limit):
        article = links[index]

        print(
            f"    Leyendo noticia "
            f"{index + 1}/{limit}"
        )

        text = load_article(
            page,
            article,
        )

        if text:
            articles.append(
                {
                    "url": article["url"],
                    "title": article["title"],
                    "text": text,
                }
            )

    print(
        f"  Noticias cargadas: "
        f"{len(articles)}"
    )

    result = []

    for race in races:
        candidates = []

        for article in articles:
            score = article_score(
                article["text"],
                article["title"],
                race,
                category,
            )

            if score > 0:
                candidates.append(
                    (
                        score,
                        article,
                    )
                )

        candidates.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        sessions = []

        for score, article in candidates[:5]:
            parsed = parse_article(
                article,
                race,
                category,
            )

            sessions.extend(parsed)

        unique_sessions = {}

        for session in sessions:
            key = (
                session["date"],
                session["inicio"],
                session["fin"],
                session["tipo"],
                normalize(
                    session["nombre"]
                ),
            )

            unique_sessions[key] = session

        sessions = list(
            unique_sessions.values()
        )

        sessions.sort(
            key=lambda item: item["inicio"]
        )

        for session in sessions:
            result.append(
                make_event(
                    category,
                    race,
                    session,
                )
            )

        print(
            f"    Horarios encontrados: "
            f"{len(sessions)}"
        )

    return result


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

                all_events.extend(events)

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
    print("Resumen por campeonato:")

    championships = {}

    for event in all_events:
        name = event["campeonato"]

        championships[name] = (
            championships.get(name, 0) + 1
        )

    for name in sorted(championships):
        print(
            f"  {name}: "
            f"{championships[name]}"
        )

    print()
    print("Resumen por tipo:")

    types = {}

    for event in all_events:
        name = event["tipo"]

        types[name] = (
            types.get(name, 0) + 1
        )

    for name in sorted(types):
        print(
            f"  {name}: "
            f"{types[name]}"
        )


if __name__ == "__main__":
    main()
