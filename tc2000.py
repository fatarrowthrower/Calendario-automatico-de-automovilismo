from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.tc2000.com.ar"
YEAR = datetime.now().year

OUTPUT = Path("data/tc2000_events.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; AutomovilismoCalendar/1.0; "
        "+https://github.com/fatarrowthrower/Calendario-automatico-de-automovilismo)"
    )
}


def get(url: str, timeout: int = 20) -> requests.Response | None:
    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=timeout,
        )

        if r.status_code == 200:
            return r

        print(f"    HTTP {r.status_code}: {url}")

    except requests.RequestException as exc:
        print(f"    Error: {exc}")

    return None


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize(text: str) -> str:
    replacements = {
        "Á": "A",
        "É": "E",
        "Í": "I",
        "Ó": "O",
        "Ú": "U",
        "Ü": "U",
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
    }

    for a, b in replacements.items():
        text = text.replace(a, b)

    return text.upper()


def extract_date(text: str, year: int) -> str | None:
    months = {
        "ENERO": 1,
        "FEBRERO": 2,
        "MARZO": 3,
        "ABRIL": 4,
        "MAYO": 5,
        "JUNIO": 6,
        "JULIO": 7,
        "AGOSTO": 8,
        "SEPTIEMBRE": 9,
        "SETIEMBRE": 9,
        "OCTUBRE": 10,
        "NOVIEMBRE": 11,
        "DICIEMBRE": 12,
    }

    text = normalize(text)

    # Ejemplo:
    # 15 DE MARZO DE 2026
    match = re.search(
        r"\b(\d{1,2})\s+DE\s+"
        r"(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|"
        r"AGOSTO|SEPTIEMBRE|SETIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)"
        r"\s+DE\s+(\d{4})\b",
        text,
    )

    if match:
        day = int(match.group(1))
        month = months[match.group(2)]
        found_year = int(match.group(3))

        return f"{found_year:04d}-{month:02d}-{day:02d}"

    # Formato 15/03/2026
    match = re.search(
        r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
        text,
    )

    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        found_year = int(match.group(3))

        return f"{found_year:04d}-{month:02d}-{day:02d}"

    return None


def extract_calendar() -> list[dict]:
    """
    Obtiene el calendario desde la página oficial.
    """

    url = f"{BASE_URL}/carreras.php?evento=calendario"

    print(f"Consultando calendario oficial:")
    print(url)

    response = get(url)

    if not response:
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    text = soup.get_text("\n", strip=True)

    events = []

    # El sitio puede cambiar ligeramente su HTML.
    # Primero intentamos detectar bloques que contengan
    # "Fecha" + fecha + circuito.
    lines = [
        clean(x)
        for x in text.splitlines()
        if clean(x)
    ]

    current_round = None

    for i, line in enumerate(lines):

        normalized = normalize(line)

        round_match = re.search(
            r"(?:FECHA|CAPITULO|CAPÍTULO)\s*(\d{1,2})",
            normalized,
        )

        if round_match:
            current_round = int(round_match.group(1))

        date = extract_date(line, YEAR)

        if not date:
            continue

        # Buscamos el circuito en las líneas cercanas.
        location = None

        nearby = lines[
            max(0, i - 4): min(len(lines), i + 5)
        ]

        location_candidates = [
            x for x in nearby
            if len(x) < 80
            and not re.search(
                r"\d{1,2}/\d{1,2}/\d{4}",
                x,
            )
            and "FECHA" not in normalize(x)
            and "CAPITULO" not in normalize(x)
            and "CALENDARIO" not in normalize(x)
        ]

        if location_candidates:
            location = location_candidates[-1]

        events.append(
            {
                "round": current_round or len(events) + 1,
                "fecha": date,
                "circuito": location or "Argentina",
            }
        )

    # Dedupe
    unique = {}

    for event in events:
        key = (
            event["round"],
            event["fecha"],
        )

        unique[key] = event

    events = list(unique.values())

    events.sort(
        key=lambda x: (
            x["fecha"],
            x["round"],
        )
    )

    return events


def find_cronogram_pages() -> list[str]:
    """
    Busca enlaces internos del sitio que apunten a carreras,
    noticias o cronogramas.
    """

    urls = set()

    pages = [
        f"{BASE_URL}/",
        f"{BASE_URL}/noticias.php",
        f"{BASE_URL}/carreras.php?evento=calendario",
    ]

    for page in pages:
        print(f"Buscando enlaces: {page}")

        response = get(page)

        if not response:
            continue

        soup = BeautifulSoup(response.text, "html.parser")

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()

            text = normalize(
                a.get_text(" ", strip=True)
            )

            full_url = urljoin(
                page,
                href,
            )

            if not full_url.startswith(BASE_URL):
                continue

            combined = normalize(
                full_url + " " + text
            )

            if any(
                term in combined
                for term in (
                    "CRONOGRAMA",
                    "HORARIOS",
                    "FECHA",
                    "CARRERA",
                )
            ):
                urls.add(full_url)

    return sorted(urls)


def extract_pdf_urls(html: str, page_url: str) -> list[str]:
    """
    Busca PDFs directamente dentro del HTML.
    """

    urls = set()

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(True):

        for attr in (
            "href",
            "src",
            "data-href",
            "data-url",
        ):
            value = tag.get(attr)

            if not value:
                continue

            if ".pdf" not in value.lower():
                continue

            full_url = urljoin(
                page_url,
                value,
            )

            if full_url.lower().startswith("http"):
                urls.add(full_url)

    # También buscamos URLs PDF escritas en el HTML.
    matches = re.findall(
        r'https?://[^"\'>\s]+\.pdf(?:\?[^"\'>\s]*)?',
        html,
        flags=re.IGNORECASE,
    )

    for url in matches:
        urls.add(url)

    return sorted(urls)


def is_relevant_pdf(url: str) -> bool:
    n = normalize(url)

    return (
        ".PDF" in n
        and (
            "TC2000" in n
            or "CRONOGRAMA" in n
            or "PRENSA" in n
            or "PRESS" in n
        )
    )


def parse_time(text: str) -> tuple[str | None, str | None]:
    text = (
        text
        .replace("–", "-")
        .replace("—", "-")
    )

    # 10:20 a 10:40
    match = re.search(
        r"\b(\d{1,2}:\d{2})\s*(?:A|-)\s*(\d{1,2}:\d{2})\b",
        text,
        flags=re.IGNORECASE,
    )

    if match:
        return (
            match.group(1),
            match.group(2),
        )

    # 13:00
    match = re.search(
        r"\b(\d{1,2}:\d{2})\b",
        text,
    )

    if match:
        return (
            match.group(1),
            None,
        )

    return None, None


def is_sporting_activity(text: str) -> bool:
    n = normalize(text)

    # Tiene que ser TC2000.
    if "TC2000" not in n:
        return False

    sporting = (
        "PRACTICA",
        "PRÁCTICA",
        "SHAKEDOWN",
        "CLASIFICACION",
        "CLASIFICACIÓN",
        "SPRINT",
        "CARRERA",
        "FINAL",
        "WARM-UP",
        "WARM UP",
    )

    administrative = (
        "ACREDITACION",
        "ACREDITACIONES",
        "VERIFICACION",
        "VERIFICACIÓN",
        "ADMINISTRATIVA",
        "NEUMATICOS",
        "NEUMÁTICOS",
        "SORTEO",
        "REUNION",
        "REUNIÓN",
        "BRIEFING",
        "CONFERENCIA",
    )

    return (
        any(x in n for x in sporting)
        and not any(x in n for x in administrative)
    )


def session_type(text: str) -> str:
    n = normalize(text)

    if "SHAKEDOWN" in n:
        return "Shakedown"

    if "PRACTICA" in n or "PRÁCTICA" in n:
        return "Práctica"

    if "CLASIFICACION" in n or "CLASIFICACIÓN" in n:
        return "Clasificación"

    if "SPRINT" in n:
        return "Sprint"

    if "WARM-UP" in n or "WARM UP" in n:
        return "Warm-up"

    if "FINAL" in n or "CARRERA" in n:
        return "Carrera"

    return "Actividad"


def extract_sessions(
    text: str,
    event: dict,
) -> list[dict]:

    lines = [
        clean(x)
        for x in text.splitlines()
        if clean(x)
    ]

    sessions = []

    for line in lines:

        if not is_sporting_activity(line):
            continue

        start, end = parse_time(line)

        if not start:
            continue

        tipo = session_type(line)

        uid_text = re.sub(
            r"[^a-z0-9]+",
            "-",
            normalize(line).lower(),
        ).strip("-")

        uid = (
            f"tc2000-{YEAR}-"
            f"{event['round']:02d}-"
            f"{event['fecha']}-"
            f"{start.replace(':', '')}-"
            f"{uid_text[:80]}"
        )

        sessions.append(
            {
                "uid": uid,
                "fecha": event["fecha"],
                "hora_inicio": start,
                "hora_fin": end,
                "titulo": line,
                "campeonato": "TC2000",
                "categoria": "Argentina",
                "disciplina": "TC2000",
                "tipo": tipo,
                "ronda": event["round"],
                "circuito": event["circuito"],
                "timezone": "America/Argentina/Buenos_Aires",
                "fuente": BASE_URL,
            }
        )

    unique = {}

    for event_data in sessions:
        key = (
            event_data["fecha"],
            event_data["hora_inicio"],
            event_data["titulo"],
        )

        unique[key] = event_data

    return list(unique.values())


def main():
    print()
    print("=" * 45)
    print(f"TC2000 - {YEAR}")
    print("=" * 45)

    calendar = extract_calendar()

    print()
    print(f"Fechas detectadas: {len(calendar)}")

    for event in calendar:
        print(
            f"  Fecha {event['round']}: "
            f"{event['fecha']} - "
            f"{event['circuito']}"
        )

    if not calendar:
        print("No se encontró el calendario.")
        return

    print()
    print("Buscando páginas de carreras y cronogramas...")

    pages = find_cronogram_pages()

    print(
        f"Páginas candidatas encontradas: {len(pages)}"
    )

    all_events = []

    # Limitamos deliberadamente la cantidad de páginas.
    # Esto evita que el workflow se quede recorriendo
    # cientos de artículos.
    for page in pages[:30]:

        print()
        print(f"Analizando: {page}")

        response = get(page)

        if not response:
            continue

        html = response.text

        pdfs = [
            url
            for url in extract_pdf_urls(
                html,
                page,
            )
            if is_relevant_pdf(url)
        ]

        if not pdfs:
            continue

        print(
            f"  PDFs encontrados: {len(pdfs)}"
        )

        for pdf_url in pdfs[:5]:

            print(
                f"  Probando: {pdf_url}"
            )

            pdf_response = get(
                pdf_url,
                timeout=40,
            )

            if not pdf_response:
                continue

            # PDF parsing sencillo.
            try:
                import io
                from pypdf import PdfReader

                reader = PdfReader(
                    io.BytesIO(
                        pdf_response.content
                    )
                )

                text = "\n".join(
                    page.extract_text() or ""
                    for page in reader.pages
                )

            except Exception as exc:
                print(
                    f"  Error leyendo PDF: {exc}"
                )
                continue

            if "TC2000" not in normalize(text):
                continue

            # Intentamos asociarlo a una fecha.
            pdf_date = extract_date(
                text,
                YEAR,
            )

            matched_event = None

            for event in calendar:

                if pdf_date == event["fecha"]:
                    matched_event = event
                    break

            if not matched_event:
                # Si no pudimos identificar la fecha,
                # no inventamos una asociación.
                continue

            sessions = extract_sessions(
                text,
                matched_event,
            )

            if sessions:
                print(
                    f"  Actividades encontradas: "
                    f"{len(sessions)}"
                )

                all_events.extend(
                    sessions
                )

    # Dedupe final.
    unique = {}

    for event in all_events:
        key = (
            event["uid"],
            event["fecha"],
            event["hora_inicio"],
            event["titulo"],
        )

        unique[key] = event

    all_events = list(unique.values())

    all_events.sort(
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
            all_events,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 45)
    print(
        f"ACTIVIDADES TC2000: "
        f"{len(all_events)}"
    )
    print("=" * 45)
    print(
        f"Archivo generado: {OUTPUT}"
    )


if __name__ == "__main__":
    main()
