import json
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, urlencode, urlunparse

import pytz
from playwright.sync_api import sync_playwright


YEAR = datetime.now().year
TZ = pytz.timezone("America/Argentina/Buenos_Aires")

OUTPUT = Path("data/actc_events.json")

MAX_NEWS_PAGES = 20
MAX_ARTICLES = 250


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

    # Segunda pasada de seguridad.
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
        key=lambda item: item["round"]
    )

    return events


def extract_article_links(page):
    links = []

    for element in page.locator("a").all():
        try:
            href = element.get_attribute(
                "href"
            )

            if not href:
                continue

            href = urljoin(
                "https://actc.org.ar",
                href,
            )

            if "/noticias/" not in href:
                continue

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


def extract_pagination_links(page):
    links = []

    for element in page.locator("a").all():
        try:
            href = element.get_attribute(
                "href"
            )

            if not href:
                continue

            href = urljoin(
                "https://actc.org.ar",
                href,
            )

            parsed = urlparse(href)

            query = parse_qs(
                parsed.query
            )

            page_values = query.get(
                "page",
                [],
            )

            if not page_values:
                continue

            try:
                page_number = int(
                    page_values[0]
                )
            except Exception:
                continue

            if page_number < 1:
                continue

            if page_number > MAX_NEWS_PAGES:
                continue

            links.append(href)

        except Exception:
            continue

    return links


def collect_all_news(page, category):
    """
    Recorre las páginas de noticias que ACTC expone
    mediante su paginación.

    Esto evita depender solamente de las 12 noticias
    visibles en la primera página.
    """

    print(
        f"  Buscando archivo de noticias: "
        f"{category['news_url']}"
    )

    pending = [
        category["news_url"]
    ]

    visited_pages = set()
    articles = {}

    while pending:
        page_url = pending.pop(0)

        if page_url in visited_pages:
            continue

        if len(visited_pages) >= MAX_NEWS_PAGES:
            break

        visited_pages.add(page_url)

        try:
            page.goto(
                page_url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.wait_for_timeout(800)

        except Exception:
            continue

        page_articles = extract_article_links(
            page
        )

        for article in page_articles:
            articles[
                article["url"]
            ] = article

        pagination = extract_pagination_links(
            page
        )

        for pagination_url in pagination:
            if pagination_url not in visited_pages:
                pending.append(
                    pagination_url
                )

        # Si la página no tiene paginación explícita,
        # probamos páginas consecutivas.
        if not pagination:
            current_query = parse_qs(
                urlparse(page_url).query
            )

            current_page = 1

            if "page" in current_query:
                try:
                    current_page = int(
                        current_query["page"][0]
                    )
                except Exception:
                    current_page = 1

            if current_page < MAX_NEWS_PAGES:
                next_page = current_page + 1

                parsed = urlparse(
                    page_url
                )

                query = parse_qs(
                    parsed.query
                )

                query["page"] = [
                    str(next_page)
                ]

                next_url = urlunparse(
                    (
                        parsed.scheme,
                        parsed.netloc,
                        parsed.path,
                        parsed.params,
                        urlencode(
                            query,
                            doseq=True,
                        ),
                        parsed.fragment,
                    )
                )

                if next_url not in visited_pages:
                    pending.append(
                        next_url
                    )

    result = list(
        articles.values()
    )

    print(
        f"  Páginas de noticias consultadas: "
        f"{len(visited_pages)}"
    )

    print(
        f"  Noticias encontradas: "
        f"{len(result)}"
    )

    return result[:MAX_ARTICLES]


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

    # Las fechas futuras pueden decir
    # "A confirmar", por lo que la ubicación puede
    # estar vacía.
    if location and location in text:
        score += 40

    if (
        f"FECHA {race['round']}"
        in text
    ):
        score += 40

    # Algunas noticias dicen "quinta fecha",
    # "undécima fecha", etc. La ubicación suele ser
    # más fiable, por eso esto es solo un refuerzo.

    if "HORARIOS" in text:
        score += 30

    if "CRONOGRAMA" in text:
        score += 30

    if "HORARIO" in text:
        score += 10

    if category["name"] == "TC":
        if "TURISMO CARRETERA" in text:
            score += 15

        if re.search(
            r"\bTC\s*\|",
            text,
        ):
            score += 15

    elif category["name"] == "TC Pista":
        if "TC PISTA" in text:
            score += 15

        if re.search(
            r"\bTCP\s*\|",
            text,
        ):
            score += 20

    elif category["name"] == "TC Pick Up":
        if (
            "TC PICK UP" in text
            or "TCPK" in text
        ):
            score += 15

        if re.search(
            r"\bTCPK\s*[:|]",
            text,
        ):
            score += 20

    return score


def parse_clock(value):
    value = value.strip()
    value = value.replace(
        ".",
        ":",
    )

    match = re.fullmatch(
        r"(\d{1,2}):(\d{2})",
        value,
    )

    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))

    if not (
        0 <= hour <= 23
        and 0 <= minute <= 59
    ):
        return None

    return hour, minute


def extract_times(line):
    text = normalize(line)

    result = []

    # 09:25 A 09:55
    # 09:25 - 09:55
    # 09:25 – 09:55
    ranges = re.findall(
        r"\b(\d{1,2}[:.]\d{2})\s*(?:A|-|–)\s*(\d{1,2}[:.]\d{2})\b",
        text,
    )

    for start, end in ranges:
        a = parse_clock(start)
        b = parse_clock(end)

        if a and b:
            result.append(
                (
                    a,
                    b,
                )
            )

    if result:
        return result

    # 09:15 HS
    # 09:15 Hs
    # 09:15 horas
    # 09:15
    values = re.findall(
        r"\b(\d{1,2}[:.]\d{2})\s*(?:HS|HORA(?:S)?|H)?\b",
        text,
    )

    for value in values:
        parsed = parse_clock(value)

        if parsed:
            result.append(
                (
                    parsed,
                    None,
                )
            )

    return result


def get_session_type(line):
    text = normalize(line)

    # Primero carrera/final.
    if (
        "CARRERA" in text
        or "FINAL" in text
    ):
        return "Carrera"

    if (
        "SERIE" in text
    ):
        return "Serie"

    if (
        "CLASIFICACION" in text
    ):
        return "Clasificación"

    if (
        "ENTRENAMIENTO" in text
        or "PRACTICA" in text
        or "PRÁCTICA" in text
    ):
        return "Entrenamiento"

    return None


def category_marker(line, category):
    text = normalize(line)

    if category["name"] == "TC":
        return (
            "TC" in text
            and "TCP" not in text
            and "TC PISTA" not in text
            and "TCPK" not in text
            and "TC PICK UP" not in text
        )

    if category["name"] == "TC Pista":
        return (
            "TCP" in text
            or "TC PISTA" in text
        )

    if category["name"] == "TC Pick Up":
        return (
            "TCPK" in text
            or "TC PICK UP" in text
        )

    return False


def extract_session_name(line):
    name = normalize(line)

    name = re.sub(
        r"\b\d{1,2}[:.]\d{2}\s*(?:A|-|–)\s*\d{1,2}[:.]\d{2}\b",
        "",
        name,
    )

    name = re.sub(
        r"\b\d{1,2}[:.]\d{2}\s*(?:HS|HORA(?:S)?|H)?\b",
        "",
        name,
    )

    name = re.sub(
        r"\s+",
        " ",
        name,
    )

    name = name.strip(
        " -|:;,.()"
    )

    # Quitamos marcas de categoría del comienzo.
    name = re.sub(
        r"^(TC|TCP|TCPK|TC PISTA|TC PICK UP)\s*[\|:\-]\s*",
        "",
        name,
    )

    return name or "Actividad"


def determine_day(
    race_date,
    line,
):
    text = normalize(line)

    # Si la propia línea trae una fecha concreta,
    # tiene prioridad.
    date_match = re.search(
        r"\b(\d{1,2})\s+([A-Z]+)\b",
        text,
    )

    if date_match:
        day = int(
            date_match.group(1)
        )

        month = MONTHS.get(
            date_match.group(2)
        )

        if month:
            try:
                candidate = datetime(
                    YEAR,
                    month,
                    day,
                ).date()

                # Solo aceptamos fechas cercanas a la
                # fecha oficial de la carrera.
                if abs(
                    (candidate - race_date).days
                ) <= 2:
                    return candidate
            except Exception:
                pass

    # Para una carrera dominical:
    #
    # viernes = -2
    # sábado  = -1
    # domingo = 0
    #
    # Si el evento oficial tuviera otro formato,
    # estas líneas se detectan igual.

    if "VIERNES" in text:
        return race_date - timedelta(days=2)

    if "SABADO" in text:
        return race_date - timedelta(days=1)

    if "DOMINGO" in text:
        return race_date

    return None


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

    # Si tenemos circuito/lugar, exigimos coincidencia
    # salvo que la noticia mencione explícitamente
    # la fecha de carrera.
    if location:
        if (
            location not in normalized
            and (
                f"FECHA {race['round']}"
                not in normalized
            )
        ):
            return []

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    events = []

    current_day = None

    for line in lines:
        session = get_session_type(
            line
        )

        # Primero detectamos el día de la actividad.
        detected_day = determine_day(
            race["date"],
            line,
        )

        if detected_day:
            current_day = detected_day

        if not session:
            continue

        times = extract_times(line)

        if not times:
            continue

        # Si todavía no sabemos el día, no inventamos.
        if current_day is None:
            continue

        # Solo tomamos líneas de la categoría
        # cuando la categoría aparece explícitamente.
        #
        # Algunas noticias separan primero:
        # "Sábado (Turismo Carretera)"
        # y luego las actividades.
        #
        # Para esos casos mantenemos la categoría activa.
        if not category_marker(
            line,
            category,
        ):
            # Si la línea no tiene marcador, puede ser
            # una sección específica de la categoría.
            #
            # Aceptamos solamente si el nombre de la
            # noticia/artículo es claramente de esa
            # categoría y no menciona otra categoría.
            line_normalized = normalize(line)

            if category["name"] == "TC":
                if (
                    "TCP" in line_normalized
                    or "TC PISTA" in line_normalized
                    or "TCPK" in line_normalized
                    or "TC PICK UP" in line_normalized
                ):
                    continue

            elif category["name"] == "TC Pista":
                if (
                    "TC " in line_normalized
                    and "TCP" not in line_normalized
                    and "TC PISTA" not in line_normalized
                ):
                    continue

            elif category["name"] == "TC Pick Up":
                if (
                    "TCPK" not in line_normalized
                    and "TC PICK UP" not in line_normalized
                ):
                    continue

        name = extract_session_name(
            line
        )

        for start, end in times:
            sh, sm = start

            if end:
                eh, em = end
            else:
                # La noticia solo publicó la hora
                # de inicio. Conservamos esa hora y
                # damos 30 minutos técnicos de duración.
                eh = sh
                em = sm + 30

                if em >= 60:
                    eh += em // 60
                    em %= 60

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

    articles_links = collect_all_news(
        page,
        category,
    )

    articles = []

    print(
        "  Descargando contenido de noticias..."
    )

    for index, article in enumerate(
        articles_links,
        start=1,
    ):
        print(
            f"    Leyendo noticia "
            f"{index}/{len(articles_links)}"
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

        # Usamos más candidatos porque algunas fechas
        # tienen una noticia general y otra específica.
        for score, article in candidates[:12]:
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
            f"    Fecha {race['round']}: "
            f"{len(sessions)} horarios"
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
