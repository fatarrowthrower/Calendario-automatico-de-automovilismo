import json
import re
from datetime import datetime, date, time
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.indycar.com"
YEAR = datetime.now().year

SCHEDULE_URL = f"{BASE_URL}/Schedule?year={YEAR}"

ET_ZONE = ZoneInfo("America/New_York")
ARG_ZONE = ZoneInfo("America/Argentina/Buenos_Aires")

OUTPUT = Path("data/indycar_events.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    )
}


MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


def clean(text):
    return re.sub(r"\s+", " ", text).strip()


def get_page(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def parse_day_header(text):
    text = clean(text)

    match = re.match(
        r"^(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
        r"([A-Z][a-z]{2})\s+(\d{1,2})$",
        text,
    )

    if not match:
        return None

    month_name = match.group(1)
    day = int(match.group(2))

    month = MONTHS.get(month_name)

    if not month:
        return None

    return date(YEAR, month, day)


def parse_time_et(text):
    text = clean(text)

    match = re.match(
        r"^(\d{1,2}):(\d{2})\s*(AM|PM)\s*ET$",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))
    ampm = match.group(3).upper()

    if ampm == "AM":
        if hour == 12:
            hour = 0
    else:
        if hour != 12:
            hour += 12

    return time(hour, minute)


def is_session_name(text):
    text = clean(text)

    if not text:
        return False

    lower = text.lower()

    keywords = [
        "practice",
        "qualifications",
        "qualification",
        "qualifying",
        "warmup",
        "warm-up",
        "race",
        "fast friday",
        "final practice",
        "high line",
        "pre-race",
        "pre race",
        "carb day",
        "pit stop competition",
    ]

    # Non-sporting promotional activity.
    excluded = [
        "pre-race show",
        "pre race show",
    ]

    if any(item in lower for item in excluded):
        return False

    return any(keyword in lower for keyword in keywords)


def normalize_session_name(text):
    text = clean(text)

    # Eliminamos el prefijo que agrega IndyCar.
    text = re.sub(
        r"^NTT INDYCAR SERIES\s*-\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    replacements = {
        "Qualifying": "Qualifications",
        "Qualification": "Qualifications",
        "Warm-up": "Warmup",
        "Warm Up": "Warmup",
    }

    for old, new in replacements.items():
        if text.lower() == old.lower():
            return new

    return text


def extract_event_info(soup):
    """
    Obtiene el nombre del evento desde H1.

    Para el circuito busca el primer H3 que aparece
    después de 'Event Details'.
    """

    event_title = ""

    h1 = soup.find("h1")

    if h1:
        event_title = clean(
            h1.get_text(" ", strip=True)
        )

    if not event_title:
        page_title = soup.find("title")

        if page_title:
            event_title = clean(
                page_title.get_text(" ", strip=True)
            )

    circuit = ""

    # Buscar el encabezado Event Details.
    details_heading = None

    for tag in soup.find_all(
        ["h2", "h3", "div", "span", "button"]
    ):
        text = clean(
            tag.get_text(" ", strip=True)
        )

        if text.lower() == "event details":
            details_heading = tag
            break

    if details_heading:
        # Primero intentamos encontrar el siguiente H3.
        for element in details_heading.find_all_next("h3"):
            candidate = clean(
                element.get_text(" ", strip=True)
            )

            if candidate and candidate.lower() != "toggle event details":
                circuit = candidate
                break

    return event_title, circuit


def extract_schedule(soup):
    """
    Lee exclusivamente el bloque Schedule -> Event Details.
    """

    lines = [
        clean(line)
        for line in soup.get_text("\n").splitlines()
        if clean(line)
    ]

    schedule_index = None
    details_index = None

    for i, line in enumerate(lines):
        if line.lower() == "schedule":
            schedule_index = i
            break

    if schedule_index is None:
        return []

    for i in range(schedule_index + 1, len(lines)):
        if lines[i].lower() == "event details":
            details_index = i
            break

    if details_index is None:
        details_index = len(lines)

    schedule_lines = lines[
        schedule_index + 1:details_index
    ]

    sessions = []
    current_date = None

    i = 0

    while i < len(schedule_lines):
        line = schedule_lines[i]

        parsed_date = parse_day_header(line)

        if parsed_date:
            current_date = parsed_date
            i += 1
            continue

        parsed_time = parse_time_et(line)

        if parsed_time and current_date:
            session_name = None

            for j in range(
                i + 1,
                min(i + 5, len(schedule_lines)),
            ):
                candidate = schedule_lines[j]

                if parse_day_header(candidate):
                    break

                if parse_time_et(candidate):
                    continue

                if is_session_name(candidate):
                    session_name = normalize_session_name(
                        candidate
                    )
                    break

            if session_name:
                dt_et = datetime.combine(
                    current_date,
                    parsed_time,
                ).replace(tzinfo=ET_ZONE)

                dt_arg = dt_et.astimezone(ARG_ZONE)

                sessions.append(
                    {
                        "date": dt_arg.date().isoformat(),
                        "time": dt_arg.strftime("%H:%M"),
                        "datetime": dt_arg.isoformat(),
                        "title": session_name,
                        "timezone": "America/Argentina/Buenos_Aires",
                    }
                )

        i += 1

    return sessions


def discover_races(soup):
    """
    Descubre dinámicamente las carreras del año.

    Caso especial:
    Milwaukee tiene Race1 y Race2 como URLs separadas,
    pero Race1 contiene el calendario completo del dobleheader.
    """

    discovered = {}

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")

        match = re.search(
            rf"/Schedule/{YEAR}/([^/?#]+)",
            href,
            re.IGNORECASE,
        )

        if not match:
            continue

        slug = match.group(1)
        url = urljoin(BASE_URL, href)

        # Milwaukee:
        # si existe Race1 usamos esa como página canónica.
        if slug.lower() == "milwaukee-race2":
            continue

        if url not in discovered:
            discovered[url] = {
                "url": url,
                "slug": slug,
            }

    races = list(discovered.values())

    return races


def make_event(race, session, event_title, circuit):
    session_date = session["date"]
    session_time = session["time"]

    slug = race["slug"]

    clean_title = re.sub(
        r"[^a-z0-9]+",
        "-",
        session["title"].lower(),
    ).strip("-")

    uid = (
        f"indycar-{YEAR}-"
        f"{slug.lower()}-"
        f"{session_date}-"
        f"{session_time.replace(':', '')}-"
        f"{clean_title}"
    )

    return {
        "uid": uid,
        "date": session_date,
        "time": session_time,
        "datetime": session["datetime"],
        "title": session["title"],
        "category": "IndyCar",
        "championship": "IndyCar",
        "location": circuit,
        "event": event_title,
        "source": race["url"],
        "timezone": "America/Argentina/Buenos_Aires",
        "prioridad": False,
        "imperdible": False,
    }


def main():
    print()
    print("=" * 60)
    print(f"INDYCAR - {YEAR}")
    print("=" * 60)
    print()

    print("Consultando calendario oficial:")
    print(SCHEDULE_URL)
    print()

    schedule_soup = get_page(SCHEDULE_URL)

    races = discover_races(schedule_soup)

    print(f"Carreras detectadas: {len(races)}")
    print()

    all_events = []

    for index, race in enumerate(races, start=1):
        print(f"Carrera {index}:")
        print(f"URL: {race['url']}")

        try:
            soup = get_page(race["url"])

            event_title, circuit = extract_event_info(
                soup
            )

            sessions = extract_schedule(soup)

            print(f"Evento: {event_title}")
            print(f"Circuito: {circuit}")
            print(f"Sesiones encontradas: {len(sessions)}")

            for session in sessions:
                event = make_event(
                    race,
                    session,
                    event_title,
                    circuit,
                )

                all_events.append(event)

                print(
                    f"  {session['date']} "
                    f"{session['time']} "
                    f"{session['title']}"
                )

        except Exception as exc:
            print(f"ERROR: {exc}")

        print()

    # Duplicados exactos.
    unique = {}

    for event in all_events:
        key = (
            event["date"],
            event["time"],
            event["title"],
            event["source"],
        )

        unique[key] = event

    events = list(unique.values())

    events.sort(
        key=lambda event: (
            event["date"],
            event["time"],
            event["title"],
        )
    )

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            events,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("=" * 60)
    print(f"SESIONES INDYCAR: {len(events)}")
    print(f"Archivo generado: {OUTPUT}")
    print("=" * 60)


if __name__ == "__main__":
    main()
