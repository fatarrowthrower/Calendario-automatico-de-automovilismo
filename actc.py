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
    """
    Una sola lectura de la página de noticias.
    No recorremos 30 páginas.
    """

    links = []

    try:

        locator = page.locator(
            "a[href]"
        )

        count = locator.count()

        for index in range(
            min(count, 500)
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


def article_score(
    title,
    calendar_event,
    championship,
):
    text = normalize(
        title
    )

    score = 0

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
        score += 20

    round_number = str(
        calendar_event[
            "round"
        ]
    )

    if (
        f"fecha {round_number}" in text
        or f"fecha {round_number}:" in text
    ):
        score += 15

    date = calendar_event[
        "date"
    ]

    month = MONTH_NAMES[
        date.month
    ]

    if (
        f"{date.day} de {month}"
        in text
    ):
        score += 10

    if championship == "TC":
        if (
            "turismo carretera" in text
            or re.search(
                r"\btc\b",
                text,
            )
        ):
            score += 5

    if championship == "TC Pista":
        if (
            "tc pista" in text
            or "tcp" in text
        ):
            score += 5

    if championship == "TC Pick Up":
        if (
            "tc pick up" in text
            or "tcpk" in text
        ):
            score += 5

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


def extract_article_events(
    page,
    championship,
    calendar_event,
):
    text = page.locator(
        "body"
    ).inner_text()

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
                index + 1:index + 4
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
            page.url,
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

        # Una sola página de noticias.
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

            news_links = get_news_links(
                news_page
            )

        finally:
            news_page.close()

        print(
            f"  Noticias visibles: "
            f"{len(news_links)}"
        )

        results = []

        for item in calendar_events:

            print(
                f"  Fecha {item['round']}: "
                f"{item['date']} "
                f"{item['location']}"
            )

            ranked = []

            for article in news_links:

                score = article_score(
                    article["title"],
                    item,
                    championship,
                )

                if score >= 10:
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

            # Como máximo 2 noticias por fecha.
            candidates = [
                article
                for score, article in ranked[:2]
            ]

            print(
                f"    Candidatas: "
                f"{len(candidates)}"
            )

            found = []

            for article in candidates:

                article_page = browser.new_page()

                try:

                    article_page.goto(
                        article["url"],
                        wait_until="domcontentloaded",
                        timeout=45000,
                    )

                    article_page.wait_for_timeout(
                        500
                    )

                    events = (
                        extract_article_events(
                            article_page,
                            championship,
                            item,
                        )
                    )

                    if events:

                        found.extend(
                            events
                        )

                        print(
                            f"    Horarios: "
                            f"{len(events)}"
                        )

                        print(
                            f"    Fuente: "
                            f"{article['url']}"
                        )

                except Exception:
                    pass

                finally:
                    article_page.close()

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
                    "    Sin horarios publicados."
                )

                results.append(
                    fallback_event(
                        championship,
                        item,
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
