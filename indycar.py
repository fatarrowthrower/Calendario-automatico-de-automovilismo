import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


YEAR = datetime.now().year

OUTPUT = Path("data/indycar_events.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,"
              "application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


ET_ZONE = ZoneInfo("America/New_York")
ARG_ZONE = ZoneInfo("America/Argentina/Buenos_Aires")


RACES_2026 = [
    {
        "ronda": 1,
        "fecha": "2026-03-01",
        "circuito": "Streets of St. Petersburg",
        "url": "https://www.indycar.com/Schedule/2026/St-Petersburg",
    },
    {
        "ronda": 2,
        "fecha": "2026-03-07",
        "circuito": "Phoenix Raceway",
        "url": "https://www.indycar.com/Schedule/2026/Phoenix",
    },
    {
        "ronda": 3,
        "fecha": "2026-03-15",
        "circuito": "Streets of Arlington",
        "url": "https://www.indycar.com/Schedule/2026/Arlington",
    },
    {
        "ronda": 4,
        "fecha": "2026-03-29",
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
        "fecha": "2026-05-09",
        "circuito": "Indianapolis Motor Speedway Road Course",
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
        "fecha": "2026-05-31",
        "circuito": "Streets of Detroit",
        "url": "https://www.indycar.com/Schedule/2026/Detroit",
    },
    {
        "ronda": 9,
        "fecha": "2026-06-07",
        "circuito": "World Wide Technology Raceway",
        "url": "https://www.indycar.com/Schedule/2026/Gateway",
    },
    {
        "ronda": 10,
        "fecha": "2026-06-21",
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
        "fecha": "2026-08-09",
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
        "circuito": "Streets of Washington",
        "url": "https://www.indycar.com/Schedule/2026/Washington-DC",
    },
    {
        "ronda": 16,
        "fecha": "2026-08-29",
        "circuito": "Milwaukee Mile",
        "url": "https://www.indycar.com/Schedule/2026/Milwaukee-Race1",
    },
    {
        "ronda": 17,
        "fecha": "2026-08-30",
        "circuito": "Milwaukee Mile",
        "url": "https://www.indycar.com/Schedule/2026/Milwaukee-Race2",
    },
    {
        "ronda": 18,
        "fecha": "2026-09-06",
        "circuito": "WeatherTech Raceway Laguna Seca",
        "url": "https://www.indycar.com/Schedule/2026/Laguna-Seca",
    },
]


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
            f"HTTP {response.status_code}: {url}"
        )

    except requests.RequestException as exc:
        print(
            f"Error: {exc}"
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


def parse_time(text):
    match = re.search(
        r"\b(\d{1,2}):(\d{2})\s*(AM|PM)\b",
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


def convert_et_to_argentina(
    fecha,
    hora,
):
    parsed = parse_time(hora)

    if not parsed:
        return fecha, None

    hour, minute = parsed

    dt_et = datetime(
        int(fecha[0:4]),
        int(fecha[5:7]),
        int(fecha[8:10]),
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
    normalized = normalize(text)

    if "FAST FRIDAY" in normalized:
        return "Entrenamiento"

    if "PRACTICE" in normalized:
        return "Entrenamiento"

    if "PIT STOP COMPETITION" in normalized:
        return "Competencia"

    if "QUALIFYING" in normalized:
        return "Clasificación"

    if "WARMUP" in normalized:
        return "Warm-up"

    if "WARM-UP" in normalized:
        return "Warm-up"

    if "PRE-RACE" in normalized:
        return "Pre-carrera"

    if "RACE" in normalized:
        return "Carrera"

    return None


def is_indycar_session(text):
    normalized = normalize(text)

    keywords = (
        "PRACTICE",
        "QUALIFYING",
        "WARMUP",
        "WARM-UP",
        "RACE",
        "FAST FRIDAY",
        "PIT STOP COMPETITION",
        "PRE-RACE",
    )

    return (
        "INDYCAR" in normalized
        and any(
            keyword in normalized
            for keyword in keywords
        )
    )


def extract_sessions(
    html,
    race,
):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    lines = []

    for line in soup.get_text(
        "\n"
    ).splitlines():

        line = clean(line)

        if line:
            lines.append(line)

    sessions = []

    for index, line in enumerate(lines):

        if not is_indycar_session(
            line
        ):
            continue

        tipo = session_type(
            line
        )

        if not tipo:
            continue

        hora_et = parse_time(
            line
        )

        if not hora_et:
            nearby = " ".join(
                lines[
                    max(0, index - 2):
                    min(len(lines), index + 3)
                ]
            )

            hora_et = parse_time(
                nearby
            )

        if not hora_et:
            continue

        hour, minute = hora_et

        hora_texto = datetime(
            2000,
            1,
            1,
            hour,
            minute,
        ).strftime(
            "%I:%M %p"
        )

        fecha_arg, hora_arg = (
            convert_et_to_argentina(
                race["fecha"],
                hora_texto,
            )
        )

        titulo = clean(
            line
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
            f"{slug[:60]}"
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
                "circuito": race["circuito"],
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

    if YEAR != 2026:
        print()
        print(
            "ATENCION: el calendario base "
            "configurado es 2026."
        )

    print()
    print(
        "Carreras a comprobar:"
    )
    print(
        len(RACES_2026)
    )

    all_sessions = []

    for race in RACES_2026:

        print()
        print(
            f"Fecha {race['ronda']}: "
            f"{race['fecha']}"
        )

        print(
            f"Circuito: "
            f"{race['circuito']}"
        )

        print(
            f"URL: "
            f"{race['url']}"
        )

        response = get(
            race["url"]
        )

        if not response:

            print(
                "No se pudo acceder."
            )

            continue

        sessions = extract_sessions(
            response.text,
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
