```python
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


# Calendario oficial IndyCar 2026.
# Lo usamos como respaldo porque la página /schedule
# puede cargar parte de su contenido mediante JavaScript.
RACES_2026 = [
    {
        "ronda": 1,
        "fecha": "2026-03-01",
        "circuito": "Streets of St. Petersburg",
        "url": "https://www.indycar.com/Schedule/2026/St-Petersburg",
    },
    {
        "ronda": 2,
        "fecha": "2026-03-15",
        "circuito": "Phoenix Raceway",
        "url": "https://www.indycar.com/Schedule/2026/Phoenix",
    },
    {
        "ronda": 3,
        "fecha": "2026-03-29",
        "circuito": "Streets of Arlington",
        "url": "https://www.indycar.com/Schedule/2026/Arlington",
    },
    {
        "ronda": 4,
        "fecha": "2026-04-12",
        "circuito": "Barber Motorsports Park",
        "url": "https://www.indycar.com/Schedule/2026/Barber",
    },
    {
        "ronda": 5,
        "fecha": "2026-04-19",
        "circuito": "Streets of Long Beach",
        "url": "https://www.indycar.com/Schedule/2026/Long-Beach",
    },
    {
        "ronda": 6,
        "fecha": "2026-05-10",
        "circuito": "Indianapolis Motor Speedway",
        "url": "https://www.indycar.com/Schedule/2026/Indianapolis",
    },
    {
        "ronda": 7,
        "fecha": "2026-05-24",
        "circuito": "Indianapolis Motor Speedway",
        "url": "https://www.indycar.com/Schedule/2026/Indianapolis-500",
    },
    {
        "ronda": 8,
        "fecha": "2026-06-07",
        "circuito": "Streets of Detroit",
        "url": "https://www.indycar.com/Schedule/2026/Detroit",
    },
    {
        "ronda": 9,
        "fecha": "2026-06-21",
        "circuito": "World Wide Technology Raceway",
        "url": "https://www.indycar.com/Schedule/2026/Gateway",
    },
    {
        "ronda": 10,
        "fecha": "2026-06-28",
        "circuito": "Road America",
        "url": "https://www.indycar.com/Schedule/2026/Road-America",
    },
    {
        "ronda": 11,
        "fecha": "2026-07-05",
        "circuito": "Mid-Ohio Sports Car Course",
        "url": "https://www.indycar.com/Schedule/2026/Mid-Ohio",
    },
    {
        "ronda": 12,
        "fecha": "2026-07-19",
        "circuito": "Nashville Superspeedway",
        "url": "https://www.indycar.com/Schedule/2026/Nashville",
    },
    {
        "ronda": 13,
        "fecha": "2026-08-02",
        "circuito": "Portland International Raceway",
        "url": "https://www.indycar.com/Schedule/2026/Portland",
    },
    {
        "ronda": 14,
        "fecha": "2026-08-16",
        "circuito": "Streets of Markham",
        "url": "https://www.indycar.com/Schedule/2026/Markham",
    },
    {
        "ronda": 15,
        "fecha": "2026-08-23",
        "circuito": "Streets of Washington, D.C.",
        "url": "https://www.indycar.com/Schedule/2026/Washington-DC",
    },
    {
        "ronda": 16,
        "fecha": "2026-08-30",
        "circuito": "Milwaukee Mile",
        "url": "https://www.indycar.com/Schedule/2026/Milwaukee",
    },
    {
        "ronda": 17,
        "fecha": "2026-09-06",
        "circuito": "WeatherTech Raceway Laguna Seca",
        "url": "https://www.indycar.com/Schedule/2026/Laguna-Seca",
    },
]


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

        print(f"    HTTP {response.status_code}: {url}")

    except requests.RequestException as exc:
        print(f"    Error: {exc}")

    return None


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


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


def parse_time(text):
    match = re.search(
        r"\b(\d{1,2}):(\d{2})\s*(AM|PM)\s*(?:ET)?\b",
        text,
        flags=re.IGNORECASE,
    )

    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))
    ampm = match.group(3).upper()

    if ampm == "PM" and hour != 12:
        hour += 12

    if ampm == "AM" and hour == 12:
        hour = 0

    return f"{hour:02d}:{minute:02d}"


def session_type(text):
    n = normalize(text)

    if "FAST FRIDAY" in n:
        return "Entrenamiento"

    if "PRACTICE" in n:
        return "Entrenamiento"

    if "QUALIFYING" in n:
        return "Clasificación"

    if "WARMUP" in n or "WARM-UP" in n:
        return "Warm-up"

    if re.search(r"\bRACE\b", n):
        return "Carrera"

    return None


def is_indycar_session(text):
    n = normalize(text)

    if "INDYCAR" not in n:
        return False

    keywords = (
        "PRACTICE",
        "QUALIFYING",
        "WARMUP",
        "WARM-UP",
        "RACE",
        "FAST FRIDAY",
    )

    return any(
        keyword in n
        for keyword in keywords
    )


def extract_sessions(html, race):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    lines = [
        clean(line)
        for line in soup.get_text(
            "\n",
            strip=True,
        ).splitlines()
        if clean(line)
    ]

    sessions = []

    for index, line in enumerate(lines):

        if not is_indycar_session(line):
            continue

        tipo = session_type(line)

        if not tipo:
            continue

        hora = parse_time(line)

        if not hora:
            # A veces el horario está en una línea cercana.
            nearby = " ".join(
                lines[
                    max(0, index - 2):
                    min(len(lines), index + 3)
                ]
            )
            hora = parse_time(nearby)

        if not hora:
            continue

        titulo = clean(line)

        if not titulo.upper().startswith(
            "NTT INDYCAR SERIES"
        ):
            titulo = (
                f"NTT INDYCAR SERIES - "
                f"{titulo}"
            )

        slug = re.sub(
            r"[^a-z0-9]+",
            "-",
            normalize(titulo).lower(),
        ).strip("-")

        uid = (
            f"indycar-{YEAR}-"
            f"{race['fecha']}-"
            f"{hora.replace(':', '')}-"
            f"{slug[:70]}"
        )

        sessions.append(
            {
                "uid": uid,
                "fecha": race["fecha"],
                "hora_inicio": hora,
                "hora_fin": None,
                "titulo": titulo,
                "campeonato": "IndyCar",
                "categoria": "IndyCar",
                "disciplina": "IndyCar",
                "tipo": tipo,
                "ronda": race["ronda"],
                "circuito": race["circuito"],
                "timezone": "America/Argentina/Buenos_Aires",
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

    return list(unique.values())


def main():

    print()
    print("=" * 50)
    print(f"INDYCAR - {YEAR}")
    print("=" * 50)

    if YEAR != 2026:
        print()
        print(
            "ATENCION: esta prueba utiliza "
            "el calendario base de 2026."
        )

    print()
    print("Consultando calendario oficial:")
    print(SCHEDULE_URL)

    schedule = get(SCHEDULE_URL)

    if schedule:
        print("Calendario oficial accesible: OK")
    else:
        print(
            "No se pudo leer la página general, "
            "pero continuamos con las páginas "
            "individuales oficiales."
        )

    races = RACES_2026

    print()
    print(
        f"Carreras a comprobar: {len(races)}"
    )

    all_sessions = []

    for race in races:

        print()
        print(
            f"Fecha {race['ronda']}: "
            f"{race['fecha']}"
        )
        print(
            f"  Circuito: "
            f"{race['circuito']}"
        )
        print(
            f"  URL: "
            f"{race['url']}"
        )

        page = get(race["url"])

        if not page:
            print(
                "  No se pudo acceder "
                "a esta página."
            )
            continue

        sessions = extract_sessions(
            page.text,
            race,
        )

        print(
            f"  Sesiones encontradas: "
            f"{len(sessions)}"
        )

        for session in sessions:
            print(
                f"    {session['fecha']} "
                f"{session['hora_inicio']} "
                f"- {session['tipo']} "
                f"- {session['titulo']}"
            )

        all_sessions.extend(sessions)

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
        f"Archivo generado: {OUTPUT}"
    )


if __name__ == "__main__":
    main()
```
