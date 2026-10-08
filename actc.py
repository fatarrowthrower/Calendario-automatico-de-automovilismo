import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


ACTC_SOURCES = {
    "TC": {
        "calendar": "https://tiempos.actc.org.ar/calendario?categoria=tc",
        "news": "https://actc.org.ar/tc/noticias",
    },
    "TC Pista": {
        "calendar": "https://tiempos.actc.org.ar/calendario?categoria=tcp",
        "news": "https://actc.org.ar/tcp/noticias",
    },
    "TC Pick Up": {
        "calendar": "https://tiempos.actc.org.ar/calendario?categoria=tcpk",
        "news": "https://actc.org.ar/tcpk/noticias",
    },
}

OUTPUT = Path("data/actc_events.json")

YEAR = datetime.now().year

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
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


def parse_argentina_date(text):
    months = {
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

    match = re.search(
        r"(\d{1,2})\s+([A-Za-zÁÉÍÓÚáéíóú]+)\s+(\d{4})",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    day = int(match.group(1))
    month_name = match.group(2).lower()[:3]
    year = int(match.group(3))

    month = months.get(month_name)

    if not month:
        return None

    return datetime(
        year,
        month,
        day,
    ).date()


def parse_numeric_date(text):
    match = re.search(
        r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b",
        text,
    )

    if not match:
        return None

    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))

    if year < 100:
        year += 2000

    try:
        return datetime(
            year,
            month,
            day,
        ).date()
    except ValueError:
        return None


def parse_calendar(championship, url):
    print(
        f"  Leyendo calendario: {url}"
    )

    html = fetch(url)

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    text = soup.get_text(
        " ",
        strip=True,
    )

    events = []

    # El calendario de Tiempos ACTC muestra
    # fechas como:
    #
    # 15 FEB 2026
    # Fecha 1 — CALAFATE
    #
    # Buscamos los bloques de fecha + Fecha N.
    pattern = re.compile(
        r"(\d{1,2})\s+"
        r"(ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC)"
        r"\s+"
        r"(\d{4})"
        r".{0,250}?"
        r"Fecha\s+(\d+)",
        re.IGNORECASE,
    )

    months = {
        "ENE": 1,
        "FEB": 2,
        "MAR": 3,
        "ABR": 4,
        "MAY": 5,
        "JUN": 6,
        "JUL": 7,
        "AGO": 8,
        "SEP": 9,
        "OCT": 10,
        "NOV": 11,
        "DIC": 12,
    }

    for match in pattern.finditer(text):

        day = int(match.group(1))
        month = months.get(
            match.group(2).upper()
        )
        year = int(match.group(3))
        round_number = int(match.group(4))

        if not month:
            continue

        try:
            date = datetime(
                year,
                month,
                day,
            ).date()
        except ValueError:
            continue

        if year != YEAR:
            continue

        block = match.group(0)

        location_match = re.search(
            r"Fecha\s+\d+\s+[—-]\s*"
            r"([A-Za-zÁÉÍÓÚáéíóú0-9 .'-]+)",
            block,
            re.IGNORECASE,
        )

        location = (
            clean(
                location_match.group(1)
            )
            if location_match
            else "Argentina"
        )

        events.append(
            {
                "round": round_number,
                "date": date,
                "location": location,
            }
        )

    # Fallback para formatos diferentes.
    if not events:
        events = parse_calendar_fallback(
            text
        )

    # Eliminar duplicados.
    unique = {}

    for event in events:
        key = (
            event["round"],
            event["date"],
        )

        unique[key] = event

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
        f"  Fechas encontradas: "
        f"{len(events)}"
    )

    return events


def parse_calendar_fallback(text):
    events = []

    lines = [
        clean(line)
        for line in text.splitlines()
        if clean(line)
    ]

    current_date = None

    months = {
        "ENE": 1,
        "FEB": 2,
        "MAR": 3,
        "ABR": 4,
        "MAY": 5,
        "JUN": 6,
        "JUL": 7,
        "AGO": 8,
        "SEP": 9,
        "OCT": 10,
        "NOV": 11,
        "DIC": 12,
    }

    for index, line in enumerate(lines):

        date_match = re.search(
            r"\b(\d{1,2})\s+"
            r"(ENE|FEB|MAR|ABR|MAY|JUN|JUL|AGO|SEP|OCT|NOV|DIC)"
            r"\s+(\d{4})\b",
            line,
            re.IGNORECASE,
        )

        if date_match:

            day = int(
                date_match.group(1)
            )

            month = months.get(
                date_match.group(2).upper()
            )

            year = int(
                date_match.group(3)
            )

            try:
                current_date = datetime(
                    year,
                    month,
                    day,
                ).date()
            except ValueError:
                current_date = None

        round_match = re.search(
            r"Fecha\s+(\d+)",
            line,
            re.IGNORECASE,
        )

        if (
            round_match
            and current_date
            and current_date.year == YEAR
        ):
            round_number = int(
                round_match.group(1)
            )

            location = re.sub(
                r"Fecha\s+\d+\s*[—-]?",
                "",
                line,
                flags=re.IGNORECASE,
            )

            events.append(
                {
                    "round": round_number,
                    "date": current_date,
                    "location": clean(location),
                }
            )

    return events


def get_news_links(
    base_url,
    max_pages=40,
):
    """
    Descarga las páginas de noticias de ACTC.

    Se detiene cuando las noticias ya son claramente
    anteriores al año que estamos procesando.
    """

    links = []

    for page in range(
        1,
        max_pages + 1,
    ):

        url = base_url

        if page > 1:
            url = (
                f"{base_url}?page={page}"
            )

        try:
            html = fetch(
                url
            )
        except Exception as exc:
            print(
                f"    Página {page}: "
                f"ERROR {exc}"
            )
            continue

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        page_links = []

        for a in soup.find_all(
            "a",
            href=True,
        ):
            href = a.get(
                "href",
                "",
            )

            title = clean(
                a.get_text(
                    " ",
                    strip=True,
                )
            )

            if not title:
                continue

            full_url = urljoin(
                base_url,
                href,
            )

            if (
                "/noticias/" not in full_url
                and "/tc/noticias/" not in full_url
                and "/tcp/noticias/" not in full_url
                and "/tcpk/noticias/" not in full_url
            ):
                continue

            item = {
                "url": full_url,
                "title": title,
            }

            if item not in page_links:
                page_links.append(
                    item
                )

        links.extend(
            page_links
        )

        print(
            f"    Noticias página {page}: "
            f"{len(page_links)}"
        )

        # Cuando ya no hay artículos,
        # no tiene sentido seguir.
        if not page_links:
            break

        # Para el año actual normalmente las
        # primeras páginas contienen todo lo necesario.
        if page >= 20:
            break

    unique = {}

    for item in links:
        unique[
            item["url"]
        ] = item

    return list(
        unique.values()
    )


def article_matches_event(
    title,
    article_text,
    event,
):
    """
    Decide si una noticia parece ser el cronograma
    de una fecha determinada.
    """

    combined = (
        f"{title} {article_text}"
    ).lower()

    location = (
        event["location"]
        .lower()
    )

    round_number = str(
        event["round"]
    )

    schedule_words = (
        "cronograma",
        "horarios",
        "horario",
        "actividades",
    )

    has_schedule_word = any(
        word in combined
        for word in schedule_words
    )

    if not has_schedule_word:
        return False

    # La noticia debe mencionar la sede
    # o la fecha.
    location_words = [
        word
        for word in re.split(
            r"\W+",
            location,
        )
        if len(word) >= 4
    ]

    location_match = any(
        word in combined
        for word in location_words
    )

    round_match = (
        re.search(
            rf"\b{re.escape(round_number)}[°º]?\s*fecha\b",
            combined,
            re.IGNORECASE,
        )
        is not None
    )

    return (
        location_match
        or round_match
    )


def get_article_info(url):
    html = fetch(
        url
    )

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    title = ""

    if soup.title:
        title = clean(
            soup.title.get_text()
        )

    h1 = soup.find("h1")

    if h1:
        title = clean(
            h1.get_text(
                " ",
                strip=True,
            )
        )

    text = soup.get_text(
        "\n",
        strip=True,
    )

    return title, text


def normalize_category_text(text):
    text = text.upper()

    text = (
        text
        .replace(
            "PICK UP",
            "PICKUP",
        )
        .replace(
            "TC PICK-UP",
            "TCPK",
        )
        .replace(
            "TC PICK UP",
            "TCPK",
        )
    )

    return text


def line_belongs_to_championship(
    line,
    championship,
):
    upper = normalize_category_text(
        line
    )

    if championship == "TC":
        # En las noticias de TC puede aparecer
        # también TC Pista.
        return (
            "TC" in upper
            and "TCPK" not in upper
            and "TCM" not in upper
            and "TCPM" not in upper
        )

    if championship == "TC Pista":
        return (
            "TCP" in upper
            and "TCPK" not in upper
            and "TCPM" not in upper
        )

    if championship == "TC Pick Up":
        return (
            "TCPK" in upper
            or "PICKUP" in upper
            or "PICK UP" in upper
        )

    return False


def classify_session(line):
    text = line.lower()

    if (
        "entrenamiento" in text
        or "práctica" in text
        or "practica" in text
    ):
        return "Entrenamiento"

    if (
        "clasificación" in text
        or "clasificacion" in text
    ):
        return "Clasificación"

    if (
        "serie" in text
    ):
        return "Serie"

    if (
        "final" in text
        or "carrera" in text
    ):
        return "Carrera"

    return None


def extract_time_range(line):
    """
    Extrae:

    09:25 a 09:55
    09:25 - 09:55

    o una sola hora:

    15:10 Hs.
    """

    match = re.search(
        r"\b([01]?\d|2[0-3]):([0-5]\d)"
        r"\s*"
        r"(?:a|-|–|hasta)"
        r"\s*"
        r"([01]?\d|2[0-3]):([0-5]\d)\b",
        line,
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

    single = re.search(
        r"\b([01]?\d|2[0-3]):([0-5]\d)\b",
        line,
    )

    if single:
        start = (
            f"{int(single.group(1)):02d}:"
            f"{int(single.group(2)):02d}"
        )

        return start, None

    return None, None


def extract_duration(line):
    match = re.search(
        r"(\d+)\s*(?:min|minutos|MIN)",
        line,
        re.IGNORECASE,
    )

    if not match:
        return None

    return int(
        match.group(1)
    )


def build_session_event(
    championship,
    event,
    session_date,
    start_time,
    end_time,
    tipo,
    name,
    source_url,
):
    start_dt = datetime.strptime(
        (
            f"{session_date.isoformat()} "
            f"{start_time}"
        ),
        "%Y-%m-%d %H:%M",
    )

    if end_time:
        end_dt = datetime.strptime(
            (
                f"{session_date.isoformat()} "
                f"{end_time}"
            ),
            "%Y-%m-%d %H:%M",
        )

        # Si el horario cruza medianoche.
        if end_dt < start_dt:
            end_dt += timedelta(
                days=1
            )

    else:
        duration = extract_duration(
            name
        )

        if duration:
            end_dt = (
                start_dt
                + timedelta(
                    minutes=duration
                )
            )
        else:
            # No inventamos duración.
            # Una hora sola se convierte en
            # evento de 1 minuto para que Calendar
            # pueda mostrarlo sin falsear una duración.
            end_dt = (
                start_dt
                + timedelta(
                    minutes=1
                )
            )

    clean_name = clean(
        name
    )

    uid = (
        "actc-"
        f"{championship.lower().replace(' ', '-')}-"
        f"{event['date'].isoformat()}-"
        f"{session_date.isoformat()}-"
        f"{start_time.replace(':', '')}-"
        f"{re.sub(r'[^a-z0-9]+', '-', clean_name.lower()).strip('-')}"
    )

    return {
        "uid": uid,
        "categoria": "Argentina",
        "campeonato": championship,
        "tipo": tipo,
        "fecha_inicio": start_dt.strftime(
            "%Y-%m-%dT%H:%M:%S"
        ),
        "fecha_fin": end_dt.strftime(
            "%Y-%m-%dT%H:%M:%S"
        ),
        "ubicacion": event["location"],
        "descripcion": (
            f"{championship} - "
            f"Fecha {event['round']} - "
            f"{clean_name}\n"
            f"Fuente: {source_url}"
        ),
        "imperdible": (
            tipo == "Carrera"
        ),
    }


def parse_schedule_article(
    championship,
    event,
    title,
    text,
    source_url,
):
    """
    Analiza una noticia oficial de ACTC.

    Los cronogramas suelen estar separados en:

    VIERNES
    ...
    SÁBADO
    ...
    DOMINGO
    ...

    El día de carrera se considera DOMINGO.
    """

    events = []

    race_date = event["date"]

    current_day = race_date

    lines = [
        clean(line)
        for line in text.splitlines()
        if clean(line)
    ]

    for line in lines:

        upper = line.upper()

        # Cambiamos de día según encabezados.
        if re.search(
            r"\bVIERNES\b",
            upper,
        ):
            current_day = (
                race_date
                - timedelta(days=2)
            )
            continue

        if re.search(
            r"\bS[ÁA]BADO\b",
            upper,
        ):
            current_day = (
                race_date
                - timedelta(days=1)
            )
            continue

        if re.search(
            r"\bDOMINGO\b",
            upper,
        ):
            current_day = race_date
            continue

        # Si la propia línea contiene
        # una fecha numérica, la usamos.
        numeric_date = parse_numeric_date(
            line
        )

        if numeric_date:
            if (
                numeric_date.year
                == YEAR
            ):
                current_day = numeric_date

        # Debe ser una actividad de pista.
        tipo = classify_session(
            line
        )

        if not tipo:
            continue

        # Debe corresponder a la categoría.
        if not line_belongs_to_championship(
            line,
            championship,
        ):
            continue

        start_time, end_time = (
            extract_time_range(
                line
            )
        )

        if not start_time:
            continue

        # Limpiamos prefijos como:
        #
        # TCP |
        # TC |
        # TCPK |
        #
        name = re.sub(
            r"^\s*(?:TC\s*PICK\s*UP|TCPK|TCP|TC)\s*\|\s*",
            "",
            line,
            flags=re.IGNORECASE,
        )

        name = clean(
            name
        )

        session = build_session_event(
            championship=championship,
            event=event,
            session_date=current_day,
            start_time=start_time,
            end_time=end_time,
            tipo=tipo,
            name=name,
            source_url=source_url,
        )

        events.append(
            session
        )

    # Deduplicar.
    unique = {}

    for item in events:
        unique[
            item["uid"]
        ] = item

    return list(
        unique.values()
    )


def find_schedule_articles(
    championship,
    events,
    news_url,
):
    print(
        f"  Buscando cronogramas en noticias ACTC..."
    )

    news_links = get_news_links(
        news_url
    )

    print(
        f"  Noticias descubiertas: "
        f"{len(news_links)}"
    )

    result = []

    # Procesamos las fechas más cercanas
    # primero.
    sorted_events = sorted(
        events,
        key=lambda item: item["date"],
        reverse=True,
    )

    for event in sorted_events:

        print(
            f"  Fecha {event['round']} "
            f"({event['date']}) "
            f"{event['location']}"
        )

        candidates = []

        for article in news_links:

            title = article[
                "title"
            ]

            title_lower = title.lower()

            if not any(
                word in title_lower
                for word in (
                    "cronograma",
                    "horarios",
                    "horario",
                    "actividades",
                )
            ):
                continue

            candidates.append(
                article
            )

        best = None

        for article in candidates:

            try:
                title, text = (
                    get_article_info(
                        article["url"]
                    )
                )
            except Exception:
                continue

            if article_matches_event(
                title,
                text,
                event,
            ):
                best = (
                    article,
                    title,
                    text,
                )
                break

        if not best:
            print(
                "    No se encontró noticia "
                "de cronograma."
            )
            continue

        article, title, text = best

        print(
            f"    Encontrado: {title}"
        )
        print(
            f"    URL: {article['url']}"
        )

        sessions = parse_schedule_article(
            championship,
            event,
            title,
            text,
            article["url"],
        )

        print(
            f"    Sesiones con horario: "
            f"{len(sessions)}"
        )

        result.extend(
            sessions
        )

    return result


def build_race_events(
    championship,
    calendar_events,
):
    """
    Mantiene una entrada de carrera para cada
    fecha del campeonato.

    No se le asigna una hora falsa.
    """
    events = []

    for event in calendar_events:

        race_date = event["date"]

        # Para mantener compatibilidad con update.py,
        # usamos 00:00-23:59 solamente como evento
        # de respaldo cuando todavía no existe
        # un horario oficial.
        events.append(
            {
                "uid": (
                    "actc-"
                    f"{championship.lower().replace(' ', '-')}-"
                    f"{race_date.isoformat()}-"
                    f"fecha-{event['round']}"
                ),
                "categoria": "Argentina",
                "campeonato": championship,
                "tipo": "Carrera",
                "fecha_inicio": (
                    f"{race_date.isoformat()}"
                    "T00:00:00"
                ),
                "fecha_fin": (
                    f"{race_date.isoformat()}"
                    "T23:59:00"
                ),
                "ubicacion": event[
                    "location"
                ],
                "descripcion": (
                    f"{championship} - "
                    f"Fecha {event['round']}"
                ),
                "imperdible": True,
            }
        )

    return events


def main():
    print(
        f"Consultando ACTC para {YEAR}..."
    )

    all_events = []

    for championship, config in (
        ACTC_SOURCES.items()
    ):

        print()
        print(
            f"Consultando ACTC: "
            f"{championship}"
        )

        try:
            calendar_events = parse_calendar(
                championship,
                config["calendar"],
            )

            race_events = build_race_events(
                championship,
                calendar_events,
            )

            all_events.extend(
                race_events
            )

            schedule_events = (
                find_schedule_articles(
                    championship,
                    calendar_events,
                    config["news"],
                )
            )

            all_events.extend(
                schedule_events
            )

            print(
                f"  Eventos base: "
                f"{len(race_events)}"
            )

            print(
                f"  Sesiones encontradas: "
                f"{len(schedule_events)}"
            )

        except Exception as exc:
            print(
                f"  ERROR: {exc}"
            )

    # Deduplicar.
    unique = {}

    for event in all_events:
        unique[
            event["uid"]
        ] = event

    events = list(
        unique.values()
    )

    events.sort(
        key=lambda item: (
            item.get(
                "fecha_inicio",
                "",
            ),
            item.get(
                "campeonato",
                "",
            ),
            item.get(
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
    print("Resumen por campeonato:")

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
    print("Resumen por tipo:")

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
