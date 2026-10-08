import json
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import pytz
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


YEAR = datetime.now().year
TZ = pytz.timezone("America/Argentina/Buenos_Aires")

OUTPUT = Path("data/actc_events.json")

CATEGORIES = [
    {
        "name": "TC",
        "championship": "Turismo Carretera",
        "calendar_url": "https://tiempos.actc.org.ar/calendario?categoria=tc",
        "news_url": "https://actc.org.ar/tc/noticias",
        "news_tag": "TC",
        "keywords": [
            "tc",
            "turismo carretera",
        ],
    },
    {
        "name": "TCP",
        "championship": "TC Pista",
        "calendar_url": "https://tiempos.actc.org.ar/calendario?categoria=tcp",
        "news_url": "https://actc.org.ar/tcp/noticias",
        "news_tag": "TCP",
        "keywords": [
            "tc pista",
            "tcp",
        ],
    },
    {
        "name": "TCPK",
        "championship": "TC Pick Up",
        "calendar_url": "https://tiempos.actc.org.ar/calendario?categoria=tcpk",
        "news_url": "https://actc.org.ar/tcpk/noticias",
        "news_tag": "TCPK",
        "keywords": [
            "tc pick up",
            "tcpk",
            "pick up",
        ],
    },
]


MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}


def normalize(text):
    text = text or ""
    text = unicodedata.normalize("NFD", text)
    text = "".join(
        char for char in text
        if unicodedata.category(char) != "Mn"
    )
    text = text.upper()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def slug(text):
    text = normalize(text).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def make_uid(category, date, session_type, name):
    return (
        f"actc-{category.lower()}-"
        f"{date.isoformat()}-"
        f"{slug(session_type)}-"
        f"{slug(name)}"
    )


def parse_date_from_text(text):
    text = normalize(text)

    patterns = [
        r"\b(\d{1,2})\s+DE\s+([A-Z]+)\s+DE\s+(\d{4})\b",
        r"\b(\d{1,2})\s+([A-Z]+)\s+(\d{4})\b",
        r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue

        a, b, c = match.groups()

        try:
            if "/" in pattern:
                day = int(a)
                month = int(b)
                year = int(c)
            else:
                day = int(a)
                month = MONTHS[b.lower()]
                year = int(c)

            return datetime(year, month, day).date()

        except Exception:
            continue

    return None


def parse_date_range(text):
    text = normalize(text)

    # Ejemplo:
    # 26 SEPT – 27 SEPT DE 2026
    match = re.search(
        r"\b(\d{1,2})\s*[-–]\s*(\d{1,2})\s+DE\s+([A-Z]+)\s+DE\s+(\d{4})\b",
        text,
    )

    if match:
        day1, day2, month_name, year = match.groups()

        try:
            month = MONTHS[month_name.lower()]
            return (
                datetime(int(year), month, int(day1)).date(),
                datetime(int(year), month, int(day2)).date(),
            )
        except Exception:
            pass

    single = parse_date_from_text(text)

    if single:
        return single, single

    return None, None


def clean_location(text):
    text = re.sub(
        r"^.*?FECHA\s+\d+\s*[-—]\s*",
        "",
        text,
        flags=re.I,
    )

    text = re.sub(
        r"\s+📍.*$",
        "",
        text,
        flags=re.I,
    )

    text = re.sub(
        r"\s+🏁.*$",
        "",
        text,
        flags=re.I,
    )

    return text.strip(" -—")


def get_calendar_events(page, category):
    print(f"  Consultando calendario oficial: {category['calendar_url']}")

    page.goto(
        category["calendar_url"],
        wait_until="domcontentloaded",
        timeout=60000,
    )

    page.wait_for_timeout(2500)

    text = page.locator("body").inner_text()

    events = []

    # La página oficial de tiempos tiene tarjetas:
    #
    # 15
    # FEB
    # 2026
    # Fecha 1 — CALAFATE
    # TC
    #
    # Buscamos directamente esa estructura.
    pattern = re.compile(
        r"""
        (?P<day>\d{1,2})
        \s+
        (?P<month>[A-ZÁÉÍÓÚÜÑ]+)
        \s+
        (?P<year>20\d{2})
        \s+
        Fecha\s+(?P<round>\d+)
        \s*[-—]\s*
        (?P<location>[^\n]+)
        """,
        re.I | re.X,
    )

    for match in pattern.finditer(text):
        day = int(match.group("day"))
        month_name = normalize(match.group("month")).lower()
        year = int(match.group("year"))
        round_number = int(match.group("round"))
        location = clean_location(match.group("location"))

        if year != YEAR:
            continue

        if month_name not in MONTHS:
            continue

        try:
            date = datetime(
                year,
                MONTHS[month_name],
                day,
            ).date()
        except ValueError:
            continue

        # Evitar tarjetas duplicadas del sitio.
        key = (
            category["name"],
            round_number,
            date.isoformat(),
            normalize(location),
        )

        if any(
            existing["_key"] == key
            for existing in events
        ):
            continue

        events.append(
            {
                "_key": key,
                "round": round_number,
                "date": date,
                "location": location,
            }
        )

    events.sort(key=lambda item: item["round"])

    return events


def extract_links(page):
    links = []

    for element in page.locator("a").all():
        try:
            href = element.get_attribute("href")
            title = element.inner_text().strip()

            if not href:
                continue

            href = urljoin(
                "https://actc.org.ar",
                href,
            )

            if "/noticias/" not in href:
                continue

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


def get_news_links(page, category):
    print(
        f"  Buscando noticias oficiales: "
        f"{category['news_url']}"
    )

    page.goto(
        category["news_url"],
        wait_until="domcontentloaded",
        timeout=60000,
    )

    page.wait_for_timeout(1500)

    links = extract_links(page)

    print(f"  Noticias encontradas: {len(links)}")

    return links


def load_article(page, url):
    try:
        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        page.wait_for_timeout(500)

        text = page.locator("body").inner_text()

        if not text:
            return ""

        return text

    except Exception:
        return ""


def article_matches_category(text, category):
    normalized = normalize(text)

    if category["name"] == "TCPK":
        return (
            "TC PICK UP" in normalized
            or "TCPK" in normalized
        )

    if category["name"] == "TCP":
        return (
            "TC PISTA" in normalized
            or re.search(r"\bTCP\b", normalized) is not None
        )

    if category["name"] == "TC":
        # TC no debe confundirse con TCP/TCPK.
        return (
            "TURISMO CARRETERA" in normalized
            or re.search(r"\bTC\b", normalized) is not None
        )

    return False


def article_matches_event(text, event):
    normalized = normalize(text)

    location = normalize(event["location"])

    # La fecha exacta es la señal más fuerte.
    date_string = event["date"].strftime("%d/%m/%Y")

    if date_string in normalized:
        return True

    day = event["date"].day
    month_name = normalize(
        event["date"].strftime("%B")
    )

    # Python devuelve nombres ingleses, así que usamos
    # también la forma numérica y el lugar.
    location_match = location in normalized

    round_match = (
        re.search(
            rf"\bFECHA\s+{event['round']}\b",
            normalized,
        )
        is not None
    )

    return location_match and round_match


def article_score(text, event, category):
    normalized = normalize(text)

    score = 0

    location = normalize(event["location"])

    if location and location in normalized:
        score += 20

    if re.search(
        rf"\bFECHA\s+{event['round']}\b",
        normalized,
    ):
        score += 20

    if article_matches_category(
        normalized,
        category,
    ):
        score += 10

    # Noticias que explícitamente hablan de horarios
    # tienen prioridad.
    if "HORARIOS" in normalized:
        score += 15

    if "CRONOGRAMA" in normalized:
        score += 15

    if "FIN DE SEMANA" in normalized:
        score += 5

    return score


def parse_time(value):
    value = value.replace(".", ":")
    value = value.replace("HS", "")
    value = value.replace("H", "")
    value = value.strip()

    match = re.fullmatch(
        r"(\d{1,2}):(\d{2})",
        value,
    )

    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))

    if hour > 23 or minute > 59:
        return None

    return hour, minute


def extract_time_ranges(line):
    line = normalize(line)

    # 09:25 A 09:55
    ranges = re.findall(
        r"\b(\d{1,2}[:.]\d{2})\s+A\s+(\d{1,2}[:.]\d{2})\b",
        line,
    )

    result = []

    for start, end in ranges:
        start_parsed = parse_time(start)
        end_parsed = parse_time(end)

        if start_parsed and end_parsed:
            result.append(
                (
                    start_parsed,
                    end_parsed,
                )
            )

    # 10:55 HS
    if not result:
        singles = re.findall(
            r"\b(\d{1,2}[:.]\d{2})\s*(?:HS|H)?\b",
            line,
        )

        for value in singles:
            parsed = parse_time(value)

            if parsed:
                result.append(
                    (
                        parsed,
                        None,
                    )
                )

    return result


def session_type(line):
    normalized = normalize(line)

    if "CLASIFICACION" in normalized:
        return "Clasificación"

    if "ENTRENAMIENTO" in normalized:
        return "Entrenamiento"

    if "SERIE" in normalized:
        return "Serie"

    if "FINAL" in normalized or "CARRERA" in normalized:
        return "Carrera"

    return None


def category_appears_in_line(line, category):
    normalized = normalize(line)

    if category["name"] == "TC":
        return (
            "TURISMO CARRETERA" in normalized
            or re.search(r"\bTC\b", normalized)
            is not None
        ) and not (
            "TC PISTA" in normalized
            or "TC PICK UP" in normalized
            or "TCPK" in normalized
        )

    if category["name"] == "TCP":
        return (
            "TC PISTA" in normalized
            or re.search(r"\bTCP\b", normalized)
            is not None
        )

    if category["name"] == "TCPK":
        return (
            "TC PICK UP" in normalized
            or "TCPK" in normalized
        )

    return False


def parse_article_sessions(
    article_text,
    event,
    category,
):
    if not article_text:
        return []

    if not article_matches_category(
        article_text,
        category,
    ):
        return []

    normalized_text = normalize(article_text)

    if (
        normalize(event["location"]) not in normalized_text
        and f"FECHA {event['round']}" not in normalized_text
    ):
        return []

    lines = [
        line.strip()
        for line in article_text.splitlines()
        if line.strip()
    ]

    sessions = []

    current_date = event["date"]

    # Algunas noticias separan explícitamente:
    # SÁBADO / DOMINGO.
    #
    # Como los cronogramas ACTC normalmente contienen
    # primero la fecha y después los horarios, usamos
    # la fecha de la fecha ACTC como base y desplazamos
    # al día siguiente cuando aparece DOMINGO.
    day_offset = 0

    for line in lines:
        normalized = normalize(line)

        if "DOMINGO" in normalized:
            day_offset = 1
            continue

        if "SABADO" in normalized:
            day_offset = 0
            continue

        if "VIERNES" in normalized:
            day_offset = -1
            continue

        if not category_appears_in_line(
            line,
            category,
        ):
            continue

        session = session_type(line)

        if not session:
            continue

        ranges = extract_time_ranges(line)

        if not ranges:
            continue

        session_name = re.sub(
            r"\b\d{1,2}[:.]\d{2}\s*(?:A\s*\d{1,2}[:.]\d{2})?\s*(?:HS|H)?\b",
            "",
            line,
            flags=re.I,
        )

        session_name = re.sub(
            r"\s+",
            " ",
            session_name,
        ).strip(" -|:")

        if not session_name:
            session_name = session

        date = current_date + timedelta(
            days=day_offset
        )

        for start, end in ranges:
            start_hour, start_minute = start

            if end:
                end_hour, end_minute = end
            else:
                end_hour = start_hour
                end_minute = start_minute + 30

                if end_minute >= 60:
                    end_hour += end_minute // 60
                    end_minute %= 60

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

            sessions.append(
                {
                    "date": date,
                    "inicio": start_dt,
                    "fin": end_dt,
                    "tipo": session,
                    "nombre": session_name,
                }
            )

    return sessions


def make_event(
    category,
    race,
    session,
):
    date = session["date"]

    uid = make_uid(
        category["name"],
        date,
        session["tipo"],
        session["nombre"],
    )

    return {
        "uid": uid,
        "fecha_inicio": session["inicio"].isoformat(),
        "fecha_fin": session["fin"].isoformat(),
        "ubicacion": race["location"],
        "categoria": "Argentina",
        "campeonato": category["championship"],
        "tipo": session["tipo"],
        "nombre": session["nombre"],
        "descripcion": (
            f"Fecha {race['round']} de "
            f"{category['championship']}."
        ),
        "fuente": category["calendar_url"],
        "imperdible": (
            session["tipo"] == "Carrera"
        ),
        "round": race["round"],
    }


def make_placeholder_event(category, race):
    """
    Si ACTC todavía no publicó horarios, conservamos
    la fecha de la carrera sin inventar un horario.

    El update.py existente espera horarios reales para
    crear eventos. Por eso NO generamos un evento 12:00
    ficticio.
    """

    return None


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


def process_category(page, category):
    print()
    print(
        f"Consultando ACTC: "
        f"{category['name']}"
    )

    races = get_calendar_events(
        page,
        category,
    )

    print(
        f"  Fechas encontradas: "
        f"{len(races)}"
    )

    if not races:
        print("  ERROR: no se encontraron fechas.")
        return []

    expected = {
        "TC": 15,
        "TCP": 15,
        "TCPK": 11,
    }.get(category["name"])

    if expected and len(races) != expected:
        print(
            f"  ADVERTENCIA: se esperaban "
            f"{expected} fechas y se encontraron "
            f"{len(races)}."
        )

    for race in races:
        print(
            f"  Fecha {race['round']}: "
            f"{race['date']} "
            f"{race['location']}"
        )

    news_links = get_news_links(
        page,
        category,
    )

    # Limitamos la cantidad de artículos para no
    # hacer cientos de descargas.
    #
    # La página oficial de noticias es paginada.
    # Las noticias recientes son las más relevantes
    # para los cronogramas todavía activos.
    articles = []

    for index, item in enumerate(news_links, start=1):
        if index > 40:
            break

        print(
            f"    Leyendo noticia "
            f"{index}/{min(len(news_links), 40)}"
        )

        text = load_article(
            page,
            item["url"],
        )

        if text:
            articles.append(
                {
                    "url": item["url"],
                    "title": item["title"],
                    "text": text,
                }
            )

    print(
        f"  Noticias cargadas: "
        f"{len(articles)}"
    )

    output = []

    for race in races:
        candidates = []

        for article in articles:
            score = article_score(
                article["text"],
                race,
                category,
            )

            if score <= 0:
                continue

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

        # Usamos solamente los mejores candidatos.
        for score, article in candidates[:5]:
            parsed = parse_article_sessions(
                article["text"],
                race,
                category,
            )

            if parsed:
                sessions.extend(parsed)

        # Eliminar duplicados de sesiones
        # que aparecen en varias noticias.
        clean_sessions = {}

        for session in sessions:
            key = (
                session["date"],
                session["inicio"],
                session["fin"],
                session["tipo"],
                normalize(session["nombre"]),
            )

            clean_sessions[key] = session

        sessions = list(
            clean_sessions.values()
        )

        sessions.sort(
            key=lambda item: item["inicio"]
        )

        for session in sessions:
            output.append(
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

        if not sessions:
            print(
                "    Sin cronograma publicado "
                "o sin coincidencia confiable."
            )

    return output


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
            timezone_id="America/Argentina/Buenos_Aires",
            viewport={
                "width": 1440,
                "height": 1000,
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
        key=lambda event: event["fecha_inicio"]
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
