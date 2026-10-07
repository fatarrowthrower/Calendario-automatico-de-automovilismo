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
    """
    Ejemplos:
      Friday, Mar 6
      Saturday, Mar 7
      Sunday, Mar 8
    """

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
    """
    Acepta:
      10:00AM ET
      2:00PM ET
      4:30PM ET
      10:00 AM ET
    """

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
    """
    Determina si una línea parece ser una sesión deportiva.
    """

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

    return any(keyword in lower for keyword in keywords)


def normalize_session_name(text):
    text = clean(text)

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


def extract_event_info(soup, url):
    """
    Busca nombre de evento y circuito sin depender
    de que la página de calendario tenga un título limpio.
    """

    title = ""

    h1 = soup.find("h1")
    if h1:
        title = clean(h1.get_text(" ", strip=True))

    if not title:
        page_title = soup.find("title")
        if page_title:
            title = clean(page_title.get_text(" ", strip=True))

    circuit = ""

    lines = [
        clean(line)
        for line in soup.get_text("\n").splitlines()
        if clean(line)
    ]

    try:
        details_index = next(
            i for i, line in enumerate(lines)
            if line.lower() == "event details"
        )

        for line in lines[details_index + 1:details_index + 30]:
            lower = line.lower()

            if "raceway" in lower:
                circuit = line
                break

            if "speedway" in lower:
                circuit = line
                break

            if "street" in lower and len(line) < 100:
                circuit = line
                break

            if "park" in lower and len(line) < 100:
                circuit = line
                break

            if "circuit" in lower and len(line) < 100:
                circuit = line
                break

    except StopIteration:
        pass

    return title, circuit


def extract_schedule(soup):
    """
    Lee exclusivamente el bloque situado entre:

      Schedule

    y

      Event Details

    Esto evita contaminar las sesiones con fechas de noticias,
    resultados o contenido de otras carreras.
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

    schedule_lines = lines[schedule_index + 1:details_index]

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

            # Buscamos las siguientes líneas para encontrar
            # el nombre real de la sesión.
            for j in range(i + 1, min(i + 5, len(schedule_lines))):
                candidate = schedule_lines[j]

                # Si aparece otro día antes del nombre,
                # esta hora quedó sin sesión.
                if parse_day_header(candidate):
                    break

                # No queremos tomar otra hora.
                if parse_time_et(candidate):
                    continue

                if is_session_name(candidate):
                    session_name = normalize_session_name(candidate)
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
    Descubre dinámicamente las carreras desde la página oficial.
    No hay fechas ni carreras hardcodeadas.
    """

    races = []
    seen = set()

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")

        match = re.search(
            rf"/Schedule/{YEAR}/([^/?#]+)",
            href,
            re.IGNORECASE,
        )

        if not match:
            continue

        url = urljoin(BASE_URL, href)

        if url in seen:
            continue

        seen.add(url)

        races.append(
            {
                "url": url,
                "slug": match.group(1),
            }
        )

    return races


def make_event(race, session, event_title, circuit):
    session_date = session["date"]
    session_time = session["time"]

    slug = race["slug"]

    uid = (
        f"indycar-{YEAR}-"
        f"{slug.lower()}-"
        f"{session_date}-"
        f"{session_time.replace(':', '')}-"
        f"{re.sub(r'[^a-z0-9]+', '-', session['title'].lower()).strip('-')}"
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
                soup,
                race["url"],
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

    # Eliminar duplicados exactos.
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

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT.open("w", encoding="utf-8") as f:
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
