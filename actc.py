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


def get_news_links(page):
    links = []

    try:

        locator = page.locator(
            "a[href]"
        )

        for index in range(
            min(locator.count(), 500)
        ):

            link = locator.nth(
                index
            )

            try:
                href = link.get_attribute(
                    "href"
                )

                title = clean(
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

            lower = full_url.lower()

            if (
                "/noticias/" not in lower
                and "/prensa/" not in lower
            ):
                continue

            if not title:
                continue

            links.append(
                {
                    "url": full_url,
                    "title": title,
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


def load_news(
    browser,
    links,
):
    """
    Carga cada noticia UNA sola vez.
    """

    articles = []

    for index, item in enumerate(
        links
    ):

        print(
            f"    Leyendo noticia "
            f"{index + 1}/{len(links)}"
        )

        page = browser.new_page()

        try:

            page.goto(
                item["url"],
                wait_until="domcontentloaded",
                timeout=45000,
            )

            page.wait_for_timeout(
                400
            )

            text = page.locator(
                "body"
            ).inner_text()

            articles.append(
                {
                    "url": item["url"],
                    "title": item["title"],
                    "text": text,
                }
            )

        except Exception:
            pass

        finally:
            page.close()

    return articles


def category_in_article(
    article_text,
    championship,
):
    text = normalize(
        article_text
    )

    if championship == "TC":
        # Si habla explícitamente de TCP
        # o TCPK, no la usamos como noticia
        # exclusiva de TC.
        if (
            "tc pista" in text
            or "tc pick up" in text
            or "tcpk" in text
        ):
            return (
                "turismo carretera" in text
                or re.search(
                    r"\btc\b",
                    text,
                )
                is not None
            )

        return (
            "turismo carretera" in text
            or re.search(
                r"\btc\b",
                text,
            )
            is not None
        )

    if championship == "TC Pista":
        return (
            "tc pista" in text
            or "tc pista" in normalize(
                article_text[:1000]
            )
        )

    if championship == "TC Pick Up":
        return (
            "tc pick up" in text
            or "tc pick-up" in text
            or "tcpk" in text
        )

    return False


def article_matches_date(
    article_text,
    calendar_event,
):
    text = normalize(
        article_text
    )

    date = calendar_event[
        "date"
    ]

    month = MONTH_NAMES[
        date.month
    ]

    variants = [
        f"{date.day} de {month}",
        f"{date.day:02d}/{date.month:02d}/{date.year}",
        f"{date.day}/{date.month}/{date.year}",
        f"fecha {calendar_event['round']}",
    ]

    for variant in variants:

        if normalize(
            variant
        ) in text:
            return True

    location = normalize(
        calendar_event[
            "location"
        ]
    )

    if (
        location
        and len(location) >= 4
        and location in text
    ):
        return True

    return False


def article_score(
    article,
    championship,
    calendar_event,
):
    text = normalize(
        article["title"]
        + " "
        + article["text"]
    )

    score = 0

    if not category_in_article(
        text,
        championship,
    ):
        return -100

    date = calendar_event[
        "date"
    ]

    location = normalize(
        calendar_event[
            "location"
        ]
    )

    if location in text:
        score += 20

    month = MONTH_NAMES[
        date.month
    ]

    if (
        f"{date.day} de {month}"
        in text
    ):
        score += 20

    if (
        f"fecha {calendar_event['round']}"
        in text
    ):
        score += 15

    for word in (
        "cronograma",
        "horario",
        "entrenamiento",
        "clasificacion",
        "clasificación",
        "series",
        "final",
    ):
        if word in text:
            score += 2

    return score


def parse_times(text):
    text = text.replace(
        ".",
        ":",
    )

    matches = re.findall(
        r"\b"
        r"([01]?\d|2[0-3]):([0-5]\d)"
        r"(?:\s*hs?)?"
        r"\b",
        text,
        re.IGNORECASE,
    )

    return [
        (
            f"{int(hour):02d}:"
            f"{int(minute):02d}"
        )
        for hour, minute in matches
    ]


def session_type(text):
    lower = normalize(
        text
    )

    if (
        "entrenamiento" in lower
        or "practica" in lower
    ):
        return "Entrenamiento"

    if "clasificacion" in lower:
        return "Clasificación"

    if "serie" in lower:
        return "Serie"

    if "final" in lower:
        return "Carrera"

    return None


def build_event(
    championship,
    calendar_event,
    tipo,
    date,
    time,
    name,
    source,
):
    start = datetime.strptime(
        (
            f"{date.isoformat()} "
            f"{time}"
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
        f"{time.replace(':', '')}-"
        f"{slugify(name)}"
    )

    return {
        "uid": uid,
        "categoria": "Argentina",
        "campeonato": championship,
        "tipo": tipo,
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
            tipo == "Carrera"
        ),
    }


def extract_events(
    article,
    championship,
    calendar_event,
):
    lines = [
        clean(line)
        for line in article["text"].splitlines()
        if clean(line)
    ]

    events = []

    current_date = calendar_event[
        "date"
    ]

    for index, line in enumerate(
        lines
    ):

        date = parse_date(
            line
        )

        if date and date.year == YEAR:
            current_date = date

        tipo = session_type(
            line
        )

        if not tipo:
            continue

        times = parse_times(
            line
        )

        if not times:

            for next_line in lines[
                index + 1:index + 5
            ]:

                times = parse_times(
                    next_line
                )

                if times:
                    break

        if not times:
            continue

        event = build_event(
            championship,
            calendar_event,
            tipo,
            current_date,
            times[0],
            line,
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
            2000
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

    finally:
        calendar_page.close()

    news_page = browser.new_page()

    try:

        news_page.goto(
            config["news"],
            wait_until="domcontentloaded",
            timeout=90000,
        )

        news_page.wait_for_timeout(
            1500
        )

        links = get_news_links(
            news_page
        )

    finally:
        news_page.close()

    print(
        f"  Noticias visibles: "
        f"{len(links)}"
    )

    print(
        "  Descargando contenido "
        "de noticias..."
    )

    articles = load_news(
        browser,
        links,
    )

    print(
        f"  Noticias cargadas: "
        f"{len(articles)}"
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

        ranked = []

        for article in articles:

            score = article_score(
                article,
                championship,
                calendar_event,
            )

            if score >= 15:
                ranked.append(
                    (
                        score,
                        article,
                    )
                )

        ranked.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        candidates = [
            article
            for score, article
            in ranked[:3]
        ]

        print(
            f"    Candidatas: "
            f"{len(candidates)}"
        )

        found = []

        for article in candidates:

            events = extract_events(
                article,
                championship,
                calendar_event,
            )

            if events:
                found.extend(
                    events
                )

        unique = {}

        for event in found:
            unique[
                event["uid"]
            ] = event

        found = list(
            unique.values()
        )

        if found:

            print(
                f"    Horarios: "
                f"{len(found)}"
            )

            results.extend(
                found
            )

        else:

            print(
                "    Sin horarios publicados."
            )

            results.append(
                fallback_event(
                    championship,
                    calendar_event,
                )
            )

    return results


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
