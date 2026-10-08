import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright


YEAR = datetime.now().year

OUTPUT = Path("data/actc_events.json")

CATEGORIES = {
    "TC": {
        "calendar": "https://actc.org.ar/tc/calendario",
        "news": "https://actc.org.ar/tc/noticias",
        "code": "TC",
    },
    "TC Pista": {
        "calendar": "https://actc.org.ar/tcp/calendario",
        "news": "https://actc.org.ar/tcp/noticias",
        "code": "TCP",
    },
    "TC Pick Up": {
        "calendar": "https://actc.org.ar/tcpk/calendario",
        "news": "https://actc.org.ar/tcpk/noticias",
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


MONTH_NAMES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}


def clean(text):
    return re.sub(
        r"\s+",
        " ",
        text or "",
    ).strip()


def normalize(text):
    text = clean(text).lower()

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

    return text


def slugify(text):
    text = normalize(text)

    text = re.sub(
        r"[^a-z0-9]+",
        "-",
        text,
    )

    return text.strip("-")


def parse_date(text):
    if not text:
        return None

    match = re.search(
        r"\b(\d{1,2})\s+"
        r"(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)"
        r"\s+(\d{4})\b",
        text,
        re.IGNORECASE,
    )

    if match:
        try:
            return datetime(
                int(match.group(3)),
                MONTHS[
                    match.group(2).lower()
                ],
                int(match.group(1)),
            ).date()
        except Exception:
            pass

    match = re.search(
        r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
        text,
    )

    if match:
        try:
            return datetime(
                int(match.group(3)),
                int(match.group(2)),
                int(match.group(1)),
            ).date()
        except Exception:
            pass

    return None


def parse_calendar(page):
    text = page.locator(
        "body"
    ).inner_text()

    lines = [
        clean(line)
        for line in text.splitlines()
        if clean(line)
    ]

    events = []

    current_round = None
    current_location = "Argentina"

    for index, line in enumerate(lines):

        match = re.search(
            r"Fecha\s+(\d+)",
            line,
            re.IGNORECASE,
        )

        if match:
            current_round = int(
                match.group(1)
            )

            location_match = re.search(
                r"Fecha\s+\d+\s*[—\-:]\s*(.+)",
                line,
                re.IGNORECASE,
            )

            if location_match:
                current_location = clean(
                    location_match.group(1)
                )

        date = parse_date(line)

        if not date:
            continue

        if date.year != YEAR:
            continue

        if current_round is None:

            for previous in reversed(
                lines[
                    max(0, index - 10):index
                ]
            ):

                previous_match = re.search(
                    r"Fecha\s+(\d+)",
                    previous,
                    re.IGNORECASE,
                )

                if previous_match:
                    current_round = int(
                        previous_match.group(1)
                    )
                    break

        if current_round is None:
            continue

        events.append(
            {
                "round": current_round,
                "date": date,
                "location": current_location,
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
        key=lambda x: x["date"]
    )

    return events


def find_article_links(page):
    links = []

    try:
        locator = page.locator(
            "a[href]"
        )

        for index in range(
            min(locator.count(), 1000)
        ):

            link = locator.nth(index)

            try:
                href = link.get_attribute(
                    "href"
                )

                text = clean(
                    link.inner_text()
                )

            except Exception:
                continue

            if not href:
                continue

            full_url = urljoin(
                page.url,
                href,
            )

            lower_url = full_url.lower()

            if (
                "/noticias/" in lower_url
                or "/prensa/noticias/" in lower_url
            ):
                links.append(
                    {
                        "url": full_url,
                        "title": text,
                    }
                )

    except Exception:
        pass

    unique = {}

    for item in links:
        unique[
            item["url"]
        ] = item

    return list(
        unique.values()
    )


def get_news_articles(
    browser,
    news_url,
):
    """
    Recorre las páginas de noticias y
    recopila artículos de ACTC.

    No depende de una cantidad fija de páginas.
    Se detiene cuando deja de encontrar artículos
    nuevos.
    """

    articles = {}

    page = browser.new_page()

    try:

        for page_number in range(
            1,
            31,
        ):

            if page_number == 1:
                url = news_url
            else:
                url = (
                    f"{news_url}"
                    f"?page={page_number}"
                )

            try:

                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )

                page.wait_for_timeout(
                    1000
                )

            except Exception as exc:

                print(
                    f"    Error noticias "
                    f"página {page_number}: "
                    f"{exc}"
                )

                continue

            found = find_article_links(
                page
            )

            before = len(
                articles
            )

            for item in found:

                articles[
                    item["url"]
                ] = item

            added = (
                len(articles)
                - before
            )

            print(
                f"    Noticias página "
                f"{page_number}: "
                f"{added} nuevas"
            )

            if (
                page_number >= 3
                and added == 0
            ):
                break

    finally:
        page.close()

    return list(
        articles.values()
    )


def article_relevance(
    article_text,
    championship,
    calendar_event,
):
    text = normalize(
        article_text
    )

    score = 0

    location = normalize(
        calendar_event[
            "location"
        ]
    )

    if location and len(location) >= 4:
        if location in text:
            score += 10

    round_number = str(
        calendar_event[
            "round"
        ]
    )

    if (
        f"fecha {round_number}" in text
        or f"{round_number} fecha" in text
        or f"fecha {round_number} del" in text
    ):
        score += 8

    date = calendar_event[
        "date"
    ]

    month_name = MONTH_NAMES[
        date.month
    ]

    date_variants = [
        f"{date.day} de {month_name}",
        f"{date.day}/{date.month}/{date.year}",
        f"{date.day:02d}/{date.month:02d}/{date.year}",
        f"{date.day} {month_name}",
    ]

    for variant in date_variants:
        if normalize(
            variant
        ) in text:
            score += 5
            break

    if championship == "TC":
        if (
            "turismo carretera" in text
            or re.search(
                r"\btc\b",
                text,
            )
        ):
            score += 3

    elif championship == "TC Pista":
        if (
            "tc pista" in text
            or "tcp" in text
        ):
            score += 3

    elif championship == "TC Pick Up":
        if (
            "tc pick up" in text
            or "tcpk" in text
        ):
            score += 3

    schedule_words = [
        "cronograma",
        "cronograma de actividades",
        "horarios",
        "horario",
        "actividad",
        "entrenamiento",
        "clasificacion",
        "clasificación",
        "series",
        "final",
    ]

    for word in schedule_words:
        if word in text:
            score += 1

    return score


def find_best_articles(
    articles,
    championship,
    calendar_event,
):
    scored = []

    for article in articles:

        score = article_relevance(
            article.get(
                "title",
                "",
            )
            + "\n"
            + article.get(
                "text",
                "",
            ),
            championship,
            calendar_event,
        )

        if score > 0:
            scored.append(
                (
                    score,
                    article,
                )
            )

    scored.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    return [
        article
        for score, article in scored[:8]
    ]


def load_article(
    browser,
    article,
):
    page = browser.new_page()

    try:

        page.goto(
            article["url"],
            wait_until="domcontentloaded",
            timeout=60000,
        )

        page.wait_for_timeout(
            1200
        )

        text = page.locator(
            "body"
        ).inner_text()

        article["text"] = text

        return article

    except Exception:
        return None

    finally:
        page.close()


def classify_session(
    text,
):
    lower = normalize(
        text
    )

    if (
        "entrenamiento" in lower
        or "practica" in lower
    ):
        return "Entrenamiento"

    if (
        "clasificacion" in lower
    ):
        return "Clasificación"

    if "serie" in lower:
        return "Serie"

    if "final" in lower:
        return "Carrera"

    return None


def parse_times_from_line(
    line,
):
    """
    Acepta formatos como:

    09:15
    9:15
    09:15 hs
    09.15 hs
    09:15 - 10:00
    """

    normalized = line.replace(
        ".",
        ":",
    )

    matches = re.findall(
        r"\b"
        r"([01]?\d|2[0-3]):([0-5]\d)"
        r"(?:\s*hs?)?"
        r"\b",
        normalized,
        re.IGNORECASE,
    )

    if not matches:
        return []

    result = []

    for hour, minute in matches:

        result.append(
            f"{int(hour):02d}:"
            f"{int(minute):02d}"
        )

    return result


def build_session(
    championship,
    calendar_event,
    session_type,
    date,
    start_time,
    name,
    source,
):
    start = datetime.strptime(
        (
            f"{date.isoformat()} "
            f"{start_time}"
        ),
        "%Y-%m-%d %H:%M",
    )

    end = start + timedelta(
        minutes=1
    )

    uid = (
        "actc-"
        f"{slugify(championship)}-"
        f"{date.isoformat()}-"
        f"{start_time.replace(':', '')}-"
        f"{slugify(name)}"
    )

    return {
        "uid": uid,
        "categoria": "Argentina",
        "campeonato": championship,
        "tipo": session_type,
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
            f"Fecha {calendar_event['round']}\n"
            f"{name}\n"
            f"Fuente: {source}"
        ),
        "imperdible": (
            session_type == "Carrera"
        ),
    }


def parse_schedule_from_article(
    article,
    championship,
    calendar_event,
):
    text = article.get(
        "text",
        "",
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

    for index, line in enumerate(lines):

        date = parse_date(
            line
        )

        if date and date.year == YEAR:
            current_date = date

        session_type = classify_session(
            line
        )

        if not session_type:
            continue

        times = parse_times_from_line(
            line
        )

        # Si la línea no tiene hora,
        # miramos algunas líneas siguientes.
        if not times:

            for next_line in lines[
                index + 1:index + 4
            ]:

                times = parse_times_from_line(
                    next_line
                )

                if times:
                    break

        if not times:
            continue

        start_time = times[0]

        name = clean(
            line
        )

        event = build_session(
            championship,
            calendar_event,
            session_type,
            current_date,
            start_time,
            name,
            article["url"],
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


def fallback_event(
    championship,
    calendar_event,
):
    date = calendar_event[
        "date"
    ]

    return {
        "uid": (
            "actc-"
            f"{slugify(championship)}-"
            f"fecha-{calendar_event['round']}"
        ),
        "categoria": "Argentina",
        "campeonato": championship,
        "tipo": "Carrera",
        "fecha_inicio": (
            f"{date.isoformat()}"
            "T00:00:00"
        ),
        "fecha_fin": (
            f"{date.isoformat()}"
            "T23:59:00"
        ),
        "ubicacion": calendar_event[
            "location"
        ],
        "descripcion": (
            f"{championship} - "
            f"Fecha {calendar_event['round']} "
            f"(horario pendiente)"
        ),
        "imperdible": True,
    }


def process_category(
    browser,
    championship,
    config,
):
    print()
    print(
        f"Consultando ACTC: "
        f"{championship}"
    )

    calendar_page = browser.new_page()

    try:

        calendar_page.goto(
            config["calendar"],
            wait_until="domcontentloaded",
            timeout=90000,
        )

        calendar_page.wait_for_timeout(
            2500
        )

        calendar_events = (
            parse_calendar(
                calendar_page
            )
        )

        print(
            f"  Fechas encontradas: "
            f"{len(calendar_events)}"
        )

        # Noticias ACTC.
        print(
            "  Buscando noticias "
            "oficiales..."
        )

        article_index = (
            get_news_articles(
                browser,
                config["news"],
            )
        )

        print(
            f"  Noticias encontradas: "
            f"{len(article_index)}"
        )

        results = []

        for calendar_event in calendar_events:

            round_number = calendar_event[
                "round"
            ]

            print(
                f"  Fecha {round_number}: "
                f"{calendar_event['date']} "
                f"{calendar_event['location']}"
            )

            candidates = find_best_articles(
                article_index,
                championship,
                calendar_event,
            )

            print(
                f"    Noticias candidatas: "
                f"{len(candidates)}"
            )

            found = []

            for candidate in candidates:

                article = load_article(
                    browser,
                    candidate,
                )

                if not article:
                    continue

                events = (
                    parse_schedule_from_article(
                        article,
                        championship,
                        calendar_event,
                    )
                )

                if events:

                    found.extend(
                        events
                    )

                    print(
                        f"    Horarios encontrados: "
                        f"{len(events)}"
                    )

                    print(
                        f"    Fuente: "
                        f"{article['url']}"
                    )

            # Eliminar duplicados.
            unique = {}

            for event in found:
                unique[
                    event["uid"]
                ] = event

            found = list(
                unique.values()
            )

            if found:
                results.extend(
                    found
                )
            else:
                print(
                    "    Sin horarios publicados; "
                    "se conserva carrera de respaldo."
                )

                results.append(
                    fallback_event(
                        championship,
                        calendar_event,
                    )
                )

        return results

    finally:
        calendar_page.close()


def main():
    print(
        f"Consultando ACTC para {YEAR}..."
    )

    all_events = []

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True
        )

        try:

            for championship, config in (
                CATEGORIES.items()
            ):

                try:

                    events = process_category(
                        browser,
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

        finally:
            browser.close()

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
