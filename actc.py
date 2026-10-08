import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


YEAR = datetime.now().year

OUTPUT = Path("data/actc_events.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
}


CATEGORIES = {
    "TC": {
        "results": "https://actc.org.ar/tc/resultados",
        "news": "https://actc.org.ar/tc/noticias",
        "code": "TC",
    },
    "TC Pista": {
        "results": "https://actc.org.ar/tcp/resultados",
        "news": "https://actc.org.ar/tcp/noticias",
        "code": "TCP",
    },
    "TC Pick Up": {
        "results": "https://actc.org.ar/tcpk/resultados",
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


def slugify(text):
    text = text.lower()

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
        text = text.replace(
            old,
            new,
        )

    text = re.sub(
        r"[^a-z0-9]+",
        "-",
        text,
    )

    return text.strip("-")


def parse_date(text):
    match = re.search(
        r"\b(\d{1,2})\s+"
        r"(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)"
        r"\s+(\d{4})\b",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    day = int(
        match.group(1)
    )

    month = MONTHS.get(
        match.group(2).lower()
    )

    year = int(
        match.group(3)
    )

    if not month:
        return None

    try:
        return datetime(
            year,
            month,
            day,
        ).date()

    except ValueError:
        return None


def parse_results_page(
    championship,
    url,
):
    print(
        f"  Leyendo resultados: {url}"
    )

    html = fetch(
        url
    )

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

    events = []

    current_round = None
    current_location = "Argentina"
    current_date = None

    for index, line in enumerate(
        lines
    ):

        # Ejemplo:
        #
        # Fecha 12 · SAN NICOLAS
        #
        round_match = re.search(
            r"Fecha\s+(\d+)\s*[·•\-]\s*(.+)",
            line,
            re.IGNORECASE,
        )

        if round_match:

            current_round = int(
                round_match.group(1)
            )

            current_location = clean(
                round_match.group(2)
            )

            continue

        # Fecha del evento.
        date = parse_date(
            line
        )

        if date:

            if date.year == YEAR:
                current_date = date

            continue

        if not current_round:
            continue

        if not current_date:
            continue

        session = classify_result(
            line
        )

        if not session:
            continue

        # Ignoramos parciales, grillas y similares.
        lower = line.lower()

        if (
            "parcial" in lower
            or "grilla" in lower
            or "rectificada" in lower
            or "rectificado" in lower
        ):
            continue

        events.append(
            {
                "round": current_round,
                "date": current_date,
                "location": current_location,
                "tipo": session,
                "nombre": line,
            }
        )

    unique = {}

    for event in events:

        key = (
            event["round"],
            event["date"],
            event["tipo"],
            event["nombre"],
        )

        unique[key] = event

    events = list(
        unique.values()
    )

    events.sort(
        key=lambda event: (
            event["date"],
            event["round"],
        )
    )

    print(
        f"  Sesiones encontradas en resultados: "
        f"{len(events)}"
    )

    return events


def classify_result(text):
    lower = text.lower()

    if (
        "entrenamiento" in lower
    ):
        return "Entrenamiento"

    if (
        "clasificacion" in lower
        or "clasificación" in lower
    ):
        return "Clasificación"

    if "serie" in lower:
        return "Serie"

    if (
        re.search(
            r"\bfinal\b",
            lower,
        )
        and "parcial" not in lower
    ):
        return "Carrera"

    return None


def get_news_links(
    url,
):
    """
    ACTC devuelve actualmente las noticias más
    recientes en la página de categoría.

    No usamos ?page= porque ACTC está sirviendo
    la misma página en ese endpoint.
    """

    print(
        f"  Leyendo noticias: {url}"
    )

    html = fetch(
        url
    )

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    links = []

    for a in soup.find_all(
        "a",
        href=True,
    ):

        href = a[
            "href"
        ]

        title = clean(
            a.get_text(
                " ",
                strip=True,
            )
        )

        full_url = urljoin(
            url,
            href,
        )

        if (
            "/noticias/" not in full_url
        ):
            continue

        if not title:
            continue

        item = {
            "url": full_url,
            "title": title,
        }

        if item not in links:
            links.append(
                item
            )

    print(
        f"  Noticias encontradas: "
        f"{len(links)}"
    )

    return links


def get_article(
    url,
):
    html = fetch(
        url
    )

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    title = ""

    h1 = soup.find(
        "h1"
    )

    if h1:
        title = clean(
            h1.get_text(
                " ",
                strip=True,
            )
        )

    if not title and soup.title:
        title = clean(
            soup.title.get_text(
                " ",
                strip=True,
            )
        )

    text = soup.get_text(
        "\n",
        strip=True,
    )

    return title, text


def parse_time_range(
    text,
):
    # 09:00 a 09:15
    # 09:00 - 09:15
    # 09:00 – 09:15

    match = re.search(
        r"\b"
        r"([01]?\d|2[0-3]):([0-5]\d)"
        r"\s*"
        r"(?:a|-|–|hasta)"
        r"\s*"
        r"([01]?\d|2[0-3]):([0-5]\d)"
        r"\b",
        text,
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

    # Solamente hora de comienzo.
    match = re.search(
        r"\b"
        r"([01]?\d|2[0-3]):([0-5]\d)"
        r"\b",
        text,
    )

    if match:

        start = (
            f"{int(match.group(1)):02d}:"
            f"{int(match.group(2)):02d}"
        )

        return start, None

    return None, None


def duration_from_text(
    text,
):
    match = re.search(
        r"(\d+)\s*"
        r"(?:min|minutos)",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    return int(
        match.group(1)
    )


def find_day(
    line,
    race_date,
):
    upper = line.upper()

    if "VIERNES" in upper:
        return (
            race_date
            - timedelta(days=2)
        )

    if (
        "SÁBADO" in upper
        or "SABADO" in upper
    ):
        return (
            race_date
            - timedelta(days=1)
        )

    if "DOMINGO" in upper:
        return race_date

    return None


def article_matches_event(
    title,
    text,
    event,
):
    combined = (
        f"{title}\n{text}"
    ).lower()

    # Tiene que hablar de horarios o cronograma.
    if not any(
        word in combined
        for word in (
            "horarios",
            "horario",
            "cronograma",
            "actividades",
        )
    ):
        return False

    location = (
        event["location"]
        .lower()
    )

    # Palabras suficientemente específicas
    # de la sede.
    location_words = [
        word
        for word in re.split(
            r"\W+",
            location,
        )
        if len(word) >= 5
    ]

    location_match = any(
        word in combined
        for word in location_words
    )

    round_number = str(
        event["round"]
    )

    round_match = re.search(
        rf"\bfecha\s+{re.escape(round_number)}\b",
        combined,
        re.IGNORECASE,
    )

    return (
        location_match
        or round_match is not None
    )


def article_has_category(
    text,
    code,
):
    upper = text.upper()

    if code == "TC":

        return (
            re.search(
                r"\bTC\s*-",
                upper,
            )
            is not None
        )

    if code == "TCP":

        return (
            "TCP -" in upper
            or "TCP |" in upper
            or "TC PISTA" in upper
        )

    if code == "TCPK":

        return (
            "TC PICK UP" in upper
            or "TC PICK-UP" in upper
            or "TCPK" in upper
        )

    return False


def parse_schedule_article(
    championship,
    code,
    calendar_event,
    title,
    text,
    source_url,
):
    """
    Convierte líneas del cronograma ACTC en
    eventos del calendario.

    Ejemplo real publicado por ACTC:

    TC - 09:00 a 09:15 Hs.
    1er. Entrenamiento (Grupo A)

    TC - 15:55 a 16:03 Hs.
    Clasificación
    """

    events = []

    race_date = calendar_event[
        "date"
    ]

    current_date = race_date

    lines = [
        clean(line)
        for line in text.splitlines()
        if clean(line)
    ]

    for line in lines:

        detected_day = find_day(
            line,
            race_date,
        )

        if detected_day:
            current_date = detected_day
            continue

        tipo = classify_result(
            line
        )

        if not tipo:
            continue

        if not article_has_category(
            line,
            code,
        ):
            continue

        start_time, end_time = (
            parse_time_range(
                line
            )
        )

        if not start_time:
            continue

        name = line

        # Quitamos prefijos de categoría.
        name = re.sub(
            r"^\s*(?:TC|TCP|TCPK)\s*[-|]\s*",
            "",
            name,
            flags=re.IGNORECASE,
        )

        name = clean(
            name
        )

        # Si la línea tiene solamente
        # "10:10 Hs. 1ra Serie",
        # la duración puede estar indicada.
        duration = duration_from_text(
            name
        )

        start = datetime.strptime(
            (
                f"{current_date.isoformat()} "
                f"{start_time}"
            ),
            "%Y-%m-%d %H:%M",
        )

        if end_time:

            end = datetime.strptime(
                (
                    f"{current_date.isoformat()} "
                    f"{end_time}"
                ),
                "%Y-%m-%d %H:%M",
            )

        elif duration:

            end = (
                start
                + timedelta(
                    minutes=duration
                )
            )

        else:

            # ACTC publica una sola hora para
            # series. No inventamos una duración.
            end = (
                start
                + timedelta(
                    minutes=1
                )
            )

        uid = (
            "actc-"
            f"{slugify(championship)}-"
            f"{current_date.isoformat()}-"
            f"{start_time.replace(':', '')}-"
            f"{slugify(name)}"
        )

        events.append(
            {
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
                    f"Fecha {calendar_event['round']} - "
                    f"{name}\n"
                    f"Fuente ACTC: {source_url}"
                ),
                "imperdible": (
                    tipo == "Carrera"
                ),
            }
        )

    unique = {}

    for event in events:
        unique[
            event["uid"]
        ] = event

    return list(
        unique.values()
    )


def make_fallback_race(
    championship,
    result_event,
):
    date = result_event[
        "date"
    ]

    return {
        "uid": (
            "actc-"
            f"{slugify(championship)}-"
            f"fecha-{result_event['round']}"
        ),
        "categoria": "Argentina",
        "campeonato": championship,
        "tipo": "Carrera",
        "fecha_inicio": (
            f"{date.isoformat()}T00:00:00"
        ),
        "fecha_fin": (
            f"{date.isoformat()}T23:59:00"
        ),
        "ubicacion": result_event[
            "location"
        ],
        "descripcion": (
            f"{championship} - "
            f"Fecha {result_event['round']}"
        ),
        "imperdible": True,
    }


def process_category(
    championship,
    config,
):
    print()
    print(
        f"Consultando ACTC: "
        f"{championship}"
    )

    result_sessions = parse_results_page(
        championship,
        config["results"],
    )

    # Agrupamos por fecha.
    dates = {}

    for session in result_sessions:

        key = (
            session["round"],
            session["date"],
        )

        if key not in dates:
            dates[key] = {
                "round": session[
                    "round"
                ],
                "date": session[
                    "date"
                ],
                "location": session[
                    "location"
                ],
            }

    # Noticias recientes de la categoría.
    news_links = get_news_links(
        config["news"]
    )

    timed_events = []

    for event in dates.values():

        print(
            f"  Fecha {event['round']} "
            f"({event['date']}) "
            f"{event['location']}"
        )

        matched = False

        for article in news_links:

            try:
                title, text = get_article(
                    article["url"]
                )
            except Exception:
                continue

            if not article_matches_event(
                title,
                text,
                event,
            ):
                continue

            if not article_has_category(
                text,
                config["code"],
            ):
                continue

            sessions = parse_schedule_article(
                championship=championship,
                code=config["code"],
                calendar_event=event,
                title=title,
                text=text,
                source_url=article["url"],
            )

            if sessions:

                print(
                    f"    Cronograma encontrado: "
                    f"{title}"
                )

                print(
                    f"    Sesiones con horario: "
                    f"{len(sessions)}"
                )

                timed_events.extend(
                    sessions
                )

                matched = True

                break

        if not matched:
            print(
                "    Sin cronograma horario "
                "en noticias recientes."
            )

    # Para fechas que ya tienen resultados,
    # conservamos las sesiones aunque no haya
    # noticia con horario.
    #
    # Pero NO las agregamos como eventos de
    # calendario, porque no queremos inventar
    # horas.
    #
    # Sí mantenemos la fecha de carrera.
    all_events = []

    for event in dates.values():

        all_events.append(
            make_fallback_race(
                championship,
                event,
            )
        )

    all_events.extend(
        timed_events
    )

    return all_events


def main():
    print(
        f"Consultando ACTC para {YEAR}..."
    )

    all_events = []

    for championship, config in (
        CATEGORIES.items()
    ):

        try:

            events = process_category(
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
