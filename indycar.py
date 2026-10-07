import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


YEAR = datetime.now().year

BASE_URL = "https://www.indycar.com"
SCHEDULE_URL = f"{BASE_URL}/Schedule?year={YEAR}"

OUTPUT = Path("data/indycar_events.json")

ET_ZONE = ZoneInfo("America/New_York")
ARG_ZONE = ZoneInfo("America/Argentina/Buenos_Aires")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


MONTHS = {
    "JAN": 1,
    "JANUARY": 1,
    "FEB": 2,
    "FEBRUARY": 2,
    "MAR": 3,
    "MARCH": 3,
    "APR": 4,
    "APRIL": 4,
    "MAY": 5,
    "JUN": 6,
    "JUNE": 6,
    "JUL": 7,
    "JULY": 7,
    "AUG": 8,
    "AUGUST": 8,
    "SEP": 9,
    "SEPT": 9,
    "SEPTEMBER": 9,
    "OCT": 10,
    "OCTOBER": 10,
    "NOV": 11,
    "NOVEMBER": 11,
    "DEC": 12,
    "DECEMBER": 12,
}


def get(url):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30,
            allow_redirects=True,
        )

        if response.status_code == 200:
            return response

        print(
            f"    HTTP {response.status_code}: {url}"
        )

    except requests.RequestException as exc:
        print(
            f"    Error: {exc}"
        )

    return None


def clean(text):
    return re.sub(
        r"\s+",
        " ",
        text or "",
    ).strip()


def normalize(text):
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "Á": "A",
        "É": "E",
        "Í": "I",
        "Ó": "O",
        "Ú": "U",
    }

    for old, new in replacements.items():
        text = text.replace(
            old,
            new,
        )

    return text.upper()


def parse_date(text):
    pattern = re.compile(
        r"\b("
        r"Jan(?:uary)?|"
        r"Feb(?:ruary)?|"
        r"Mar(?:ch)?|"
        r"Apr(?:il)?|"
        r"May|"
        r"Jun(?:e)?|"
        r"Jul(?:y)?|"
        r"Aug(?:ust)?|"
        r"Sep(?:t(?:ember)?)?|"
        r"Oct(?:ober)?|"
        r"Nov(?:ember)?|"
        r"Dec(?:ember)?"
        r")"
        r"\.?\s+"
        r"(\d{1,2})"
        r"(?:st|nd|rd|th)?"
        r"(?:,?\s+(\d{4}))?"
        r"\b",
        re.IGNORECASE,
    )

    match = pattern.search(text)

    if not match:
        return None

    month = MONTHS.get(
        normalize(match.group(1))
    )

    if not month:
        return None

    day = int(
        match.group(2)
    )

    year = match.group(3)

    if year:
        year = int(year)
    else:
        year = YEAR

    if year != YEAR:
        return None

    try:
        return datetime(
            year,
            month,
            day,
        ).strftime("%Y-%m-%d")

    except ValueError:
        return None


def parse_time(text):
    match = re.search(
        r"\b(\d{1,2}):(\d{2})\s*(AM|PM)"
        r"(?:\s*ET)?\b",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    hour = int(
        match.group(1)
    )

    minute = int(
        match.group(2)
    )

    ampm = match.group(3).upper()

    if ampm == "PM" and hour != 12:
        hour += 12

    if ampm == "AM" and hour == 12:
        hour = 0

    return hour, minute


def convert_to_argentina(
    date_text,
    time_text,
):
    parsed = parse_time(
        time_text
    )

    if not parsed:
        return date_text, None

    hour, minute = parsed

    dt_et = datetime(
        int(date_text[0:4]),
        int(date_text[5:7]),
        int(date_text[8:10]),
        hour,
        minute,
        tzinfo=ET_ZONE,
    )

    dt_arg = dt_et.astimezone(
        ARG_ZONE
    )

    return (
        dt_arg.strftime("%Y-%m-%d"),
        dt_arg.strftime("%H:%M"),
    )


def session_type(text):
    value = normalize(text)

    if "FAST FRIDAY" in value:
        return "Entrenamiento"

    if "PRACTICE" in value:
        return "Entrenamiento"

    if "QUALIFICATION" in value:
        return "Clasificación"

    if "QUALIFYING" in value:
        return "Clasificación"

    if "WARMUP" in value:
        return "Warm-up"

    if "WARM-UP" in value:
        return "Warm-up"

    if "PRE-RACE" in value:
        return "Pre-carrera"

    if "RACE" in value:
        return "Carrera"

    return None


def extract_races(html):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    races = {}

    for link in soup.find_all(
        "a",
        href=True,
    ):
        href = link.get(
            "href",
            "",
        ).strip()

        full_url = urljoin(
            BASE_URL,
            href,
        )

        if not re.search(
            rf"/Schedule/{YEAR}/",
            full_url,
            re.IGNORECASE,
        ):
            continue

        text = clean(
            link.get_text(
                " ",
                strip=True,
            )
        )

        if not text:
            continue

        parent = link

        for _ in range(5):
            if parent.parent:
                parent = parent.parent

        context = clean(
            parent.get_text(
                " ",
                strip=True,
            )
        )

        combined = clean(
            f"{text} {context}"
        )

        date = parse_date(
            combined
        )

        if not date:
            continue

        if date in races:
            continue

        races[date] = {
            "fecha": date,
            "titulo": text,
            "url": full_url,
        }

    result = list(
        races.values()
    )

    result.sort(
        key=lambda item: item["fecha"]
    )

    return result


def extract_circuit(soup, fallback):
    selectors = [
        "[class*='track']",
        "[class*='venue']",
        "[class*='location']",
        "[class*='circuit']",
    ]

    candidates = []

    for selector in selectors:
        for element in soup.select(selector):
            text = clean(
                element.get_text(
                    " ",
                    strip=True,
                )
            )

            if text:
                candidates.append(text)

    for candidate in candidates:
        normalized = normalize(
            candidate
        )

        if "RACE RECAP" in normalized:
            continue

        if "INDYCAR" in normalized:
            continue

        if len(candidate) > 100:
            continue

        return candidate

    return fallback


def extract_schedule_rows(
    soup,
    race,
):
    schedule_heading = None

    for element in soup.find_all(
        string=re.compile(
            r"^\s*Schedule\s*$",
            re.IGNORECASE,
        )
    ):
        schedule_heading = element.parent
        break

    if not schedule_heading:
        return []

    container = schedule_heading

    for _ in range(6):
        if not container.parent:
            break

        text = clean(
            container.get_text(
                " ",
                strip=True,
            )
        )

        if "Practice" in text or "Race" in text:
            break

        container = container.parent

    rows = []

    for element in container.find_all(
        ["tr", "li", "div"],
    ):
        text = clean(
            element.get_text(
                " ",
                strip=True,
            )
        )

        if not text:
            continue

        if not parse_time(text):
            continue

        tipo = session_type(
            text
        )

        if not tipo:
            continue

        if "HIGHLIGHTS" in normalize(
            text
        ):
            continue

        if "RESULTS" in normalize(
            text
        ):
            continue

        rows.append(text)

    return rows


def extract_sessions(
    html,
    race,
):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    circuit = extract_circuit(
        soup,
        race["titulo"],
    )

    rows = extract_schedule_rows(
        soup,
        race,
    )

    sessions = []

    for row in rows:

        parsed_time = parse_time(
            row
        )

        if not parsed_time:
            continue

        tipo = session_type(
            row
        )

        if not tipo:
            continue

        fecha_arg, hora_arg = (
            convert_to_argentina(
                race["fecha"],
                row,
            )
        )

        if not hora_arg:
            continue

        titulo = clean(
            row
        )

        if not titulo.upper().startswith(
            "NTT INDYCAR SERIES"
        ):
            titulo = (
                "NTT INDYCAR SERIES - "
                + titulo
            )

        slug = re.sub(
            r"[^a-z0-9]+",
            "-",
            normalize(
                titulo
            ).lower(),
        ).strip("-")

        uid = (
            f"indycar-"
            f"{fecha_arg}-"
            f"{hora_arg.replace(':', '')}-"
            f"{slug[:70]}"
        )

        sessions.append(
            {
                "uid": uid,
                "fecha": fecha_arg,
                "hora_inicio": hora_arg,
                "hora_fin": None,
                "titulo": titulo,
                "campeonato": "IndyCar",
                "categoria": "IndyCar",
                "disciplina": "IndyCar",
                "tipo": tipo,
                "ronda": race["ronda"],
                "circuito": circuit,
                "timezone": (
                    "America/Argentina/"
                    "Buenos_Aires"
                ),
                "fuente": race["url"],
            }
        )

    unique = {}

    for event in sessions:
        key = (
            event["fecha"],
            event["hora_inicio"],
            event["titulo"],
        )

        unique[key] = event

    return list(
        unique.values()
    )


def main():
    print()
    print("=" * 50)
    print(
        f"INDYCAR - {YEAR}"
    )
    print("=" * 50)

    print()
    print(
        "Consultando calendario oficial:"
    )
    print(
        SCHEDULE_URL
    )

    schedule = get(
        SCHEDULE_URL
    )

    if not schedule:
        print()
        print(
            "ERROR: no se pudo acceder "
            "al calendario oficial."
        )
        return

    races = extract_races(
        schedule.text
    )

    print()
    print(
        f"Carreras detectadas: "
        f"{len(races)}"
    )

    if not races:
        print()
        print(
            "ERROR: no se detectaron "
            "carreras."
        )
        return

    for index, race in enumerate(
        races,
        start=1,
    ):
        race["ronda"] = index

    all_sessions = []

    for race in races:

        print()
        print(
            f"Fecha {race['ronda']}: "
            f"{race['fecha']}"
        )

        print(
            f"Evento: "
            f"{race['titulo']}"
        )

        print(
            f"URL: "
            f"{race['url']}"
        )

        page = get(
            race["url"]
        )

        if not page:
            print(
                "No se pudo acceder."
            )
            continue

        sessions = extract_sessions(
            page.text,
            race,
        )

        print(
            f"Sesiones encontradas: "
            f"{len(sessions)}"
        )

        for session in sessions:
            print(
                f"  {session['fecha']} "
                f"{session['hora_inicio']} "
                f"- {session['tipo']} "
                f"- {session['titulo']}"
            )

        all_sessions.extend(
            sessions
        )

    unique = {}

    for event in all_sessions:
        key = (
            event["fecha"],
            event["hora_inicio"],
            event["titulo"],
        )

        unique[key] = event

    all_sessions = list(
        unique.values()
    )

    all_sessions.sort(
        key=lambda event: (
            event["fecha"],
            event["hora_inicio"],
            event["titulo"],
        )
    )

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT.write_text(
        json.dumps(
            all_sessions,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 50)
    print(
        f"SESIONES INDYCAR: "
        f"{len(all_sessions)}"
    )
    print("=" * 50)

    print()
    print(
        f"Archivo generado: "
        f"{OUTPUT}"
    )


if __name__ == "__main__":
    main()
