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


def parse_calendar_date(line):
    text = normalize(line)

    match = re.search(
        r"\b(\d{1,2})\s+([A-Z]+)\s+(20\d{2})\b",
        text,
    )

    if not match:
        return None

    day = int(match.group(1))
    month_name = match.group(2)
    year = int(match.group(3))

    month = MONTHS.get(month_name)

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

    page.wait_for_timeout(2500)

    text = page.locator("body").inner_text()

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

        date = parse_calendar_date(line)

        if not date:
            continue

        if date.year != YEAR:
            continue

        key = (
            current_round,
            date.isoformat(),
            normalize(current_location),
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

    if len(events) == 0:
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
                index + 1:index + 12
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

        page.wait_for_timeout(500)

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
        score += 40

    if (
        f"FECHA {race['round']}"
        in text
    ):
        score += 40

    if "HORARIOS" in text:
        score += 15

    if "CRONOGRAMA" in text:
        score += 20

    if "ACTIVIDAD" in text:
        score += 5

    if category["name"] == "TC":
        if (
            "TURISMO CARRETERA"
            in text
        ):
            score += 15

    elif category["name"] == "TC Pista":
        if "TC PISTA" in text:
            score += 15

    elif category["name"] == "TC Pick Up":
        if (
            "TC PICK UP" in text
            or "TCPK" in text
        ):
            score += 15

    return score


def extract_times(line):
    text = normalize(line)

    results = []

    # 10:15 A 10:45
    ranges = re.findall(
        r"\b(\d{1,2}[:.]\d{2})\s*(?:A|-|–)\s*(\d{1,2}[:.]\d{2})\b",
        text,
    )

    for start, end in ranges:
        start = start.replace(".", ":")
        end = end.replace(".", ":")

        try:
            sh, sm = map(
                int,
                start.split(":"),
            )

            eh, em = map(
                int,
                end.split(":"),
            )

            if (
                0 <= sh <= 23
                and 0 <= eh <= 23
                and 0 <= sm <= 59
                and 0 <= em <= 59
            ):
                results.append(
                    (
                        (sh, sm),
                        (eh, em),
                    )
                )

        except Exception:
            pass

    if results:
        return results

    # 10:15 HS
    singles = re.findall(
        r"\b(\d{1,2}[:.]\d{2})\s*(?:HS|H)?\b",
        text,
    )

    for value in singles:
        value = value.replace(".", ":")

        try:
            hour, minute = map(
                int,
                value.split(":"),
            )

            if (
                0 <= hour <= 23
                and 0 <= minute <= 59
            ):
                results.append(
                    (
                        (hour, minute),
                        None,
                    )
                )

        except Exception:
            pass

    return results


def get_session_type(line):
    text = normalize(line)

    if (
        "CLASIFICACION" in text
        or "CLASIFICACIÓN" in text
    ):
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


def extract_session_name(line):
    name = normalize(line)

    name = re.sub(
        r"\b\d{1,2}[:.]\d{2}\s*(?:A|-|–)\s*\d{1,2}[:.]\d{2}\b",
        "",
        name,
    )

    name = re.sub(
        r"\b\d{1,2}[:.]\d{2}\s*(?:HS|H)?\b",
        "",
        name,
    )

    name = re.sub(
        r"\s+",
        " ",
        name,
    )

    name = name.strip(
        " -|:;,"
    )

    return name


def line_has_activity(line):
    text = normalize(line)

    return (
        get_session_type(line)
        is not None
    )


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

    # La noticia debe tener por lo menos
    # una de estas señales.
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

    current_day = race["date"]

    for line in lines:
        normalized_line = normalize(line)

        # --------------------------------------------------
        # Detectamos el día independientemente de la
        # categoría.
        # --------------------------------------------------

        if re.search(
            r"\bVIERNES\b",
            normalized_line,
        ):
            current_day = (
                race["date"]
                - timedelta(days=1)
            )

        elif re.search(
            r"\bSABADO\b",
            normalized_line,
        ):
            current_day = race["date"]

        elif re.search(
            r"\bDOMINGO\b",
            normalized_line,
        ):
            current_day = (
                race["date"]
                + timedelta(days=1)
            )

        session = get_session_type(
            line
        )

        if not session:
            continue

        times = extract_times(line)

        if not times:
            continue

        name = extract_session_name(
            line
        )

        if not name:
            name = session

        for start, end in times:
            sh, sm = start

            if end:
                eh, em = end
            else:
                # Cuando ACTC solamente publica
                # la hora de inicio, usamos 30 min
                # como duración técnica del evento.
                # NO modifica la hora de inicio.
                eh = sh
                em = sm + 30

                if em >= 60:
                    eh += 1
                    em -= 60

                if eh >= 24:
                    eh = 23
                    em = 59

            start_dt = TZ.localize(
                datetime(
                    current_day.year,
                    current_day.month,
                    current_day.day,
                    sh,
                    sm,
                )
            )

            end_dt = TZ.localize(
                datetime(
                    current_day.year,
                    current_day.month,
                    current_day.day,
                    eh,
                    em,
                )
            )

            events.append(
                {
                    "date": current_day,
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

    expected = {
        "TC": 15,
        "TC Pista": 15,
        "TC Pick Up": 11,
    }[category["name"]]

    print(
        f"  Fechas encontradas: "
        f"{len(races)}"
    )

    if len(races) != expected:
        print(
            f"  ADVERTENCIA: se esperaban "
            f"{expected} fechas."
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

    for index, article in enumerate(
        links[:40],
        start=1,
    ):
        print(
            f"    Leyendo noticia "
            f"{index}/{min(len(links), 40)}"
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

        # Miramos hasta 8 noticias candidatas,
        # no solamente 2 o 3.
        for score, article in candidates[:8]:
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
            key=lambda item:
            item["inicio"]
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
