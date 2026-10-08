import json
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import pytz
from playwright.sync_api import sync_playwright


YEAR = datetime.now().year
TZ = pytz.timezone("America/Argentina/Buenos_Aires")

OUTPUT = Path("data/actc_events.json")

# ACTC publica aproximadamente 12 noticias por página.
# Recorremos suficiente historial para cubrir todo el año.
MAX_NEWS_PAGES = 40


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

    # Segunda pasada por si cambia ligeramente
    # la separación visual de la tarjeta.
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


def article_is_schedule_candidate(
    title,
    category,
):
    text = normalize(title)

    schedule_words = [
        "HORARIOS",
        "HORARIO",
        "CRONOGRAMA",
        "CRONOGRAMA",
        "ACTIVIDAD",
    ]

    has_schedule_word = any(
        word in text
        for word in schedule_words
    )

    if not has_schedule_word:
        return False

    if category["name"] == "TC":
        # En la sección TC puede aparecer TCP dentro
        # de un título conjunto. Eso es válido.
        return True

    if category["name"] == "TC Pista":
        return True

    if category["name"] == "TC Pick Up":
        return True

    return False


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

            if not title:
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


def collect_schedule_links(
    page,
    category,
):
    """
    ACTC tiene cientos de páginas de noticias.

    En lugar de intentar adivinar enlaces de paginación,
    recorremos directamente:

        /noticias?page=1
        /noticias?page=2
        /noticias?page=3
        ...

    y guardamos solamente títulos que parecen ser
    cronogramas/horarios.
    """

    print(
        "  Buscando cronogramas en el "
        "archivo de noticias..."
    )

    schedule_links = {}

    empty_pages = 0

    for page_number in range(
        1,
        MAX_NEWS_PAGES + 1,
    ):
        if page_number == 1:
            url = category["news_url"]
        else:
            url = (
                f"{category['news_url']}"
                f"?page={page_number}"
            )

        try:
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            page.wait_for_timeout(400)

        except Exception:
            print(
                f"    Página {page_number}: "
                "error de carga"
            )
            continue

        links = extract_article_links(
            page
        )

        found_this_page = 0

        for article in links:
            if not article_is_schedule_candidate(
                article["title"],
                category,
            ):
                continue

            if article["url"] in schedule_links:
                continue

            schedule_links[
                article["url"]
            ] = article

            found_this_page += 1

        if found_this_page:
            print(
                f"    Página {page_number}: "
                f"{found_this_page} "
                "cronograma(s)"
            )
            empty_pages = 0
        else:
            empty_pages += 1

        # Después de muchas páginas sin ningún
        # cronograma ya estamos fuera del período útil.
        if empty_pages >= 12:
            break

    result = list(
        schedule_links.values()
    )

    print(
        f"  Cronogramas encontrados: "
        f"{len(result)}"
    )

    return result


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
        score += 100

    if (
        f"FECHA {race['round']}"
        in text
    ):
        score += 80

    if "HORARIOS" in text:
        score += 30

    if "CRONOGRAMA" in text:
        score += 30

    if "HORARIO" in text:
        score += 15

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

    # 10:10 Hs.
    # 10:10 horas.
    # 10:10
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

    # FINAL/CARRERA primero para no confundirla
    # con otras actividades.
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


def extract_category_from_line(line):
    text = normalize(line)

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
        r"^(TC PISTA|TC PICK UP|TURISMO CARRETERA|TCPK|TCP|TC)\s*[\-:|]\s*",
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


def determine_day(
    race_date,
    line,
):
    text = normalize(line)

    # Fecha explícita:
    #
    # SÁBADO 28
    # DOMINGO 29
    # SÁBADO 12 DE SEPTIEMBRE
    #
    # Primero buscamos día + mes.
    explicit = re.search(
        r"\b(\d{1,2})\s+([A-Z]+)\b",
        text,
    )

    if explicit:
        day = int(
            explicit.group(1)
        )

        month = MONTHS.get(
            explicit.group(2)
        )

        if month:
            try:
                candidate = datetime(
                    YEAR,
                    month,
                    day,
                ).date()

                if abs(
                    (candidate - race_date).days
                ) <= 3:
                    return candidate

            except Exception:
                pass

    # En ACTC la fecha del calendario es normalmente
    # el domingo de la carrera.
    #
    # Por eso:
    # viernes -> -2
    # sábado  -> -1
    # domingo ->  0

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

    # La noticia debe pertenecer a la fecha.
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

    # Categoría activa dentro de una noticia.
    active_category = None

    for line in lines:
        normalized_line = normalize(line)

        detected_day = determine_day(
            race["date"],
            line,
        )

        if detected_day:
            current_day = detected_day

        detected_category = (
            extract_category_from_line(
                line
            )
        )

        if detected_category:
            active_category = (
                detected_category
            )

        session = get_session_type(
            line
        )

        if not session:
            continue

        times = extract_times(line)

        if not times:
            continue

        # Si la línea trae categoría explícita,
        # usamos esa categoría.
        #
        # Si no la trae, usamos la última sección
        # de categoría detectada.
        line_category = (
            detected_category
            or active_category
        )

        if line_category != category["name"]:
            continue

        if current_day is None:
            continue

        name = extract_session_name(
            line
        )

        for start, end in times:
            sh, sm = start

            if end:
                eh, em = end
            else:
                # ACTC publicó solamente hora de inicio.
                # Para el calendario usamos 30 minutos
                # como duración técnica.
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

    print(
        f"  Fechas encontradas: "
        f"{len(races)}"
    )

    expected = {
        "TC": 15,
        "TC Pista": 15,
        "TC Pick Up": 11,
    }[category["name"]]

    # TCPK puede tener fechas futuras "A confirmar"
    # sin día/lugar publicado. No las inventamos.
    if (
        category["name"] != "TC Pick Up"
        and len(races) != expected
    ):
        print(
            f"  ADVERTENCIA: se esperaban "
            f"{expected} fechas."
        )

    if (
        category["name"] == "TC Pick Up"
        and len(races) < 9
    ):
        print(
            "  ADVERTENCIA: faltan fechas "
            "publicadas por ACTC."
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

    schedule_links = collect_schedule_links(
        page,
        category,
    )

    articles = []

    print(
        "  Descargando cronogramas..."
    )

    for index, article in enumerate(
        schedule_links,
        start=1,
    ):
        print(
            f"    Cronograma "
            f"{index}/{len(schedule_links)}: "
            f"{article['title']}"
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
        f"  Cronogramas cargados: "
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

        # Normalmente el mejor artículo es el
        # cronograma de la fecha.
        for score, article in candidates[:6]:
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
