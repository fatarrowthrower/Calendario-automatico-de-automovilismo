from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


YEAR = datetime.now().year

BASE_URL = "https://www.indycar.com"
SCHEDULE_URL = f"{BASE_URL}/schedule"

OUTPUT = Path("data/indycar_events.json")

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


def get(url, timeout=25):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=timeout,
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
        text = text.replace(old, new)

    return text.upper()


def month_number(name):
    months = {
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

    return months.get(
        normalize(name)
    )


def parse_date(text):
    """
    Detecta fechas como:

    Mar 1
    March 1
    May 24
    Sunday, May 24
    """

    text = clean(text)

    pattern = re.compile(
        r"\b(?:"
        r"Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"
        r")?,?\s*"
        r"(Jan|January|Feb|February|Mar|March|Apr|April|May|"
        r"Jun|June|Jul|July|Aug|August|Sep|Sept|September|"
        r"Oct|October|Nov|November|Dec|December)"
        r"\s+(\d{1,2})\b",
        re.IGNORECASE,
    )

    match = pattern.search(text)

    if not match:
        return None

    month = month_number(
        match.group(1)
    )

    day = int(
        match.group(2)
    )

    if not month:
        return None

    return (
        f"{YEAR:04d}-"
        f"{month:02d}-"
        f"{day:02d}"
    )


def parse_time(text):
    """
    Detecta:
      12:30 PM ET
      9:00AM ET
      4:30 PM ET
    """

    match = re.search(
        r"\b(\d{1,2}):(\d{2})\s*"
        r"(AM|PM)\s*(?:ET)?\b",
        text,
        flags=re.IGNORECASE,
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

    return f"{hour:02d}:{minute:02d}"


def extract_schedule_events(html):
    """
    Extrae carreras desde la página oficial.

    Se buscan enlaces que apunten a:
      /Schedule/2026/...
    """

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    events = {}

    for a in soup.find_all(
        "a",
        href=True,
    ):

        href = a["href"].strip()

        full_url = urljoin(
            BASE_URL,
            href,
        )

        if f"/Schedule/{YEAR}/" not in full_url:
            continue

        title = clean(
            a.get_text(
                " ",
                strip=True,
            )
        )

        if not title:
            continue

        parent = a.parent

        context = clean(
            parent.get_text(
                " ",
                strip=True,
            )
            if parent
            else title
        )

        combined = (
            title
            + " "
            + context
        )

        date = parse_date(
            combined
        )

        if not date:
            continue

        # Evitamos enlaces repetidos.
        key = full_url

        events[key] = {
            "url": full_url,
            "titulo": title,
            "fecha": date,
        }

    return list(
        events.values()
    )


def extract_location(text):
    """
    Intenta encontrar el circuito dentro
    del contexto de la carrera.
    """

    known = [
        "Streets of St. Petersburg",
        "Phoenix Raceway",
        "Streets of Arlington",
        "Barber Motorsports Park",
        "Streets of Long Beach",
        "Indianapolis Motor Speedway",
        "Streets of Detroit",
        "World Wide Technology Raceway",
        "Road America",
        "Mid-Ohio Sports Car Course",
        "Nashville Superspeedway",
        "Portland International Raceway",
        "Streets of Markham",
        "Streets of Washington, D.C.",
        "Milwaukee Mile",
        "WeatherTech Raceway Laguna Seca",
    ]

    normalized = normalize(text)

    for location in known:
        if normalize(location) in normalized:
            return location

    return "Estados Unidos"


def session_type(text):
    n = normalize(text)

    if "PRACTICE" in n:
        return "Entrenamiento"

    if "QUALIFYING" in n:
        return "Clasificación"

    if "WARMUP" in n or "WARM-UP" in n:
        return "Warm-up"

    if "RACE" in n:
        return "Carrera"

    if "FAST FRIDAY" in n:
        return "Entrenamiento"

    return None


def is_sporting_session(text):
    n = normalize(text)

    sporting = (
        "PRACTICE",
        "QUALIFYING",
        "WARMUP",
        "WARM-UP",
        "RACE",
        "FAST FRIDAY",
    )

    return (
        "INDYCAR" in n
        and any(
            term in n
            for term in sporting
        )
    )


def extract_sessions(
    html,
    event,
):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    text = soup.get_text(
        "\n",
        strip=True,
    )

    lines = [
        clean(line)
        for line in text.splitlines()
        if clean(line)
    ]

    sessions = []

    for i, line in enumerate(lines):

        if not is_sporting_session(
            line
        ):
            continue

        start = parse_time(
            line
        )

        if not start:
            continue

        tipo = session_type(
            line
        )

        if not tipo:
            continue

        # Buscamos contexto cercano.
        context = " ".join(
            lines[
                max(0, i - 2):
                min(len(lines), i + 3)
            ]
        )

        title = clean(
            line
        )

        # El texto de IndyCar a veces
        # separa "NTT INDYCAR SERIES"
        # de "Practice 1".
        if title.upper().startswith(
            "NTT INDYCAR SERIES"
        ):
            session_title = title
        else:
            session_title = (
                f"NTT INDYCAR SERIES - "
                f"{title}"
            )

        uid_slug = re.sub(
            r"[^a-z0-9]+",
            "-",
            normalize(
                session_title
            ).lower(),
        ).strip("-")

        uid = (
            f"indycar-{YEAR}-"
            f"{event['fecha']}-"
            f"{start.replace(':', '')}-"
            f"{uid_slug[:70]}"
        )

        sessions.append(
            {
                "uid": uid,
                "fecha": event["fecha"],
                "hora_inicio": start,
                "hora_fin": None,
                "titulo": session_title,
                "campeonato": "IndyCar",
                "categoria": "IndyCar",
                "disciplina": "IndyCar",
                "tipo": tipo,
                "ronda": event.get(
                    "ronda"
                ),
                "circuito": event[
                    "circuito"
                ],
                "timezone": (
                    "America/Argentina/"
                    "Buenos_Aires"
                ),
                "fuente": event[
                    "url"
                ],
            }
        )

    unique = {}

    for event_data in sessions:

        key = (
            event_data["fecha"],
            event_data[
                "hora_inicio"
            ],
            event_data[
                "titulo"
            ],
        )

        unique[key] = event_data

    return list(
        unique.values()
    )


def main():

    print()
    print("=" * 50)
    print(f"INDYCAR - {YEAR}")
    print("=" * 50)

    print()
    print(
        "Consultando calendario oficial:"
    )
    print(
        SCHEDULE_URL
    )

    response = get(
        SCHEDULE_URL
    )

    if not response:
        print(
            "No se pudo acceder al "
            "calendario oficial."
        )
        return

    events = extract_schedule_events(
        response.text
    )

    print()
    print(
        f"Eventos encontrados: "
        f"{len(events)}"
    )

    if not events:
        print(
            "No se encontraron eventos "
            "en la página oficial."
        )
        return

    # Ordenamos cronológicamente.
    events.sort(
        key=lambda x: x["fecha"]
    )

    # Asignamos ronda según orden.
    for index, event in enumerate(
        events,
        start=1,
    ):
        event["ronda"] = index
        event["circuito"] = (
            extract_location(
                event["titulo"]
            )
        )

    all_sessions = []

    # No procesamos cientos de páginas.
    # El calendario oficial nos da las páginas
    # exactas de los eventos.
    for event in events:

        print()
        print(
            f"Fecha {event['ronda']}: "
            f"{event['fecha']}"
        )
        print(
            f"  {event['url']}"
        )

        page = get(
            event["url"]
        )

        if not page:
            continue

        sessions = extract_sessions(
            page.text,
            event,
        )

        print(
            f"  Sesiones encontradas: "
            f"{len(sessions)}"
        )

        all_sessions.extend(
            sessions
        )

    # Dedupe global.
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
        key=lambda x: (
            x["fecha"],
            x["hora_inicio"],
            x["titulo"],
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

    for event in all_sessions[:30]:
        print(
            f"{event['fecha']} "
            f"{event['hora_inicio']} - "
            f"{event['titulo']}"
        )

    if len(all_sessions) > 30:
        print(
            f"... y "
            f"{len(all_sessions) - 30} más"
        )

    print()
    print(
        f"Archivo generado: "
        f"{OUTPUT}"
    )


if __name__ == "__main__":
    main()
