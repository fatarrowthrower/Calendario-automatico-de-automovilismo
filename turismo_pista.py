from __future__ import annotations

import io
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader


BASE_URL = "https://aptpweb.com.ar"
YEAR = datetime.now().year

OUTPUT = Path("data/turismo_pista_events.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; AutomovilismoCalendar/1.0; "
        "+https://github.com/fatarrowthrower/Calendario-automatico-de-automovilismo)"
    )
}

SPORT_TERMS = (
    "ENTRENAMIENTO",
    "CLASIFICACIÓN",
    "CLASIFICACION",
    "SERIE",
    "FINAL",
)

ADMIN_TERMS = (
    "ACREDITACION",
    "ACREDITACIONES",
    "COMBUSTIBLE",
    "ADMINISTRATIVA",
    "VERIFICACION",
    "VERIFICACIÓN",
    "NEUMATICOS",
    "NEUMÁTICOS",
    "SELLADO",
    "SORTEO",
    "REUNION",
    "REUNIÓN",
    "PILOTOS",
    "BOXES",
    "BOX",
    "SENSORES",
    "PRE-GRILLA",
    "PREGRILLA",
    "VUELTA PREVIA",
    "NOTAS EN GRILLA",
    "NOTAS EN GRILLA",
)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text.upper()


def get(url: str, timeout: int = 30) -> requests.Response | None:
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=timeout,
            allow_redirects=True,
        )

        if response.status_code == 200:
            return response

    except requests.RequestException as exc:
        print(f"    Error descargando {url}: {exc}")

    return None


def search_aptp(query: str, page: int = 1) -> list[dict]:
    """
    Busca artículos mediante el buscador de WordPress de APTP.
    """
    url = f"{BASE_URL}/wp-json/wp/v2/search"

    params = {
        "search": query,
        "per_page": 100,
        "page": page,
    }

    try:
        response = requests.get(
            url,
            params=params,
            headers=HEADERS,
            timeout=30,
        )

        if response.status_code != 200:
            return []

        data = response.json()

        results = []

        for item in data:
            results.append(
                {
                    "id": item.get("id"),
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                }
            )

        return results

    except (requests.RequestException, ValueError):
        return []


def get_article(url: str) -> str:
    response = get(url)

    if not response:
        return ""

    return response.text


def extract_pdf_urls(html: str, page_url: str) -> list[str]:
    """
    Extrae PDFs de múltiples formas.

    No dependemos solamente de <a href>.
    APTP/WordPress puede dejar la URL:
      - en href
      - en data attributes
      - dentro de shortcodes
      - dentro de scripts
      - como URL absoluta en el HTML
    """

    urls = set()

    # 1. Cualquier URL directa a PDF.
    patterns = [
        r'https?://[^"\'>\s]+?\.pdf(?:\?[^"\'>\s]*)?',
        r'//[^"\'>\s]+?\.pdf(?:\?[^"\'>\s]*)?',
        r'["\']([^"\']+?\.pdf(?:\?[^"\']*)?)["\']',
    ]

    for pattern in patterns:
        for match in re.findall(pattern, html, flags=re.IGNORECASE):
            if isinstance(match, tuple):
                match = match[0]

            url = match.strip()

            if url.startswith("//"):
                url = "https:" + url

            elif not url.startswith("http"):
                url = urljoin(page_url, url)

            urls.add(url)

    # 2. href/src de todos los elementos.
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup.find_all(True):
        for attr in ("href", "src", "data-href", "data-url", "data-file"):
            value = tag.get(attr)

            if not value:
                continue

            if ".pdf" not in value.lower():
                continue

            url = urljoin(page_url, value)

            if url.lower().startswith("http"):
                urls.add(url)

    return sorted(urls)


def pdf_text(pdf_bytes: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))

        pages = []

        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:
                pages.append("")

        return "\n".join(pages)

    except Exception as exc:
        print(f"    Error leyendo PDF: {exc}")
        return ""


def is_turismo_pista_line(text: str) -> bool:
    n = normalize(text)

    return (
        "TURISMO PISTA" in n
        and any(term in n for term in SPORT_TERMS)
        and not any(term in n for term in ADMIN_TERMS)
    )


def is_sporting_text(text: str) -> bool:
    n = normalize(text)

    if not is_turismo_pista_line(text):
        return False

    # Evita eventos de otras categorías que aparecen
    # en algunos cronogramas compartidos.
    if "TURISMO CARRETERA 2000" in n:
        return False

    return True


def parse_date_from_text(text: str, fallback_date: str) -> str:
    """
    Busca fechas del tipo:
      VIERNES 30 DE ENERO DE 2026
      SABADO 31 DE ENERO DE 2026
      DOMINGO 1 DE FEBRERO DE 2026
    """

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
        "OCTUBRE": 10,
        "NOVIEMBRE": 11,
        "DICIEMBRE": 12,
    }

    n = normalize(text)

    pattern = (
        r"(?:LUNES|MARTES|MIERCOLES|JUEVES|VIERNES|SABADO|DOMINGO)"
        r"\s+(\d{1,2})\s+DE\s+"
        r"(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|"
        r"SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)"
        r"\s+DE\s+(\d{4})"
    )

    match = re.search(pattern, n)

    if match:
        day = int(match.group(1))
        month = months[match.group(2)]
        year = int(match.group(3))

        return f"{year:04d}-{month:02d}-{day:02d}"

    return fallback_date


def extract_time(text: str) -> tuple[str | None, str | None]:
    """
    Detecta:
      10:00
      10:00 A 10:30
      10:00 - 10:30
      13:06
    """

    text = text.replace("–", "-").replace("—", "-")

    match = re.search(
        r"\b(\d{1,2}:\d{2})\s*(?:A|AL|-)\s*(\d{1,2}:\d{2})\b",
        text,
        flags=re.IGNORECASE,
    )

    if match:
        return match.group(1), match.group(2)

    match = re.search(
        r"\b(\d{1,2}:\d{2})\b",
        text,
    )

    if match:
        return match.group(1), None

    return None, None


def extract_class(text: str) -> str | None:
    n = normalize(text)

    match = re.search(r"CLASE\s+([123])\b", n)

    if match:
        return f"Clase {match.group(1)}"

    return None


def extract_group(text: str) -> str | None:
    n = normalize(text)

    match = re.search(
        r"GRUPO\s+([ABC])\b",
        n,
    )

    if match:
        return f"Grupo {match.group(1)}"

    return None


def extract_session_type(text: str) -> str | None:
    n = normalize(text)

    if "ENTRENAMIENTO" in n:
        return "Entrenamiento"

    if "CLASIFICACION" in n:
        return "Clasificación"

    if re.search(r"\bSERIE\b", n):
        return "Serie"

    if re.search(r"\bFINAL\b", n):
        return "Final"

    return None


def clean_session_name(text: str) -> str:
    """
    Limpia ruido de las tablas PDF y deja un nombre legible.
    """

    text = re.sub(r"\s+", " ", text).strip()

    # Quita columnas repetidas provenientes de PDFs tabulares.
    text = re.sub(
        r"^.*?TURISMO PISTA",
        "Turismo Pista",
        text,
        flags=re.IGNORECASE,
    )

    return text


def extract_sessions(
    text: str,
    fallback_date: str,
    round_number: int,
    location: str,
) -> list[dict]:

    lines = []

    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()

        if not line:
            continue

        if not is_sporting_text(line):
            continue

        session_type = extract_session_type(line)

        if not session_type:
            continue

        start, end = extract_time(line)

        if not start:
            continue

        date = parse_date_from_text(text, fallback_date)

        cls = extract_class(line)
        group = extract_group(line)

        name = clean_session_name(line)

        uid_base = (
            f"turismo-pista-{YEAR}-"
            f"{round_number:02d}-"
            f"{date}-{start.replace(':', '')}-"
            f"{normalize(name).replace(' ', '-')[:80]}"
        )

        event = {
            "uid": uid_base,
            "fecha": date,
            "hora_inicio": start,
            "hora_fin": end,
            "titulo": name,
            "campeonato": "Turismo Pista",
            "categoria": "Argentina",
            "disciplina": "Turismo Pista",
            "clase": cls,
            "grupo": group,
            "tipo": session_type,
            "ronda": round_number,
            "circuito": location,
            "timezone": "America/Argentina/Buenos_Aires",
            "fuente": "APTP",
        }

        lines.append(event)

    # El PDF puede repetir información por columnas.
    unique = {}

    for event in lines:
        key = (
            event["fecha"],
            event["hora_inicio"],
            event["titulo"],
        )

        unique[key] = event

    return list(unique.values())


def extract_location_from_article(html: str) -> str | None:
    """
    Intenta descubrir el circuito desde el artículo.
    """

    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    n = normalize(text)

    locations = [
        "LA PLATA",
        "TOAY",
        "CONCORDIA",
        "SAN JORGE",
        "ROSARIO",
        "RIO CUARTO",
        "SAN NICOLAS",
        "TERMAS DE RIO HONDO",
        "CONCEPCION DEL URUGUAY",
        "RAFAELA",
    ]

    for location in locations:
        if location in n:
            return location.title()

    return None


def score_pdf_url(
    url: str,
    round_number: int,
    year: int,
) -> int:

    n = normalize(url)

    score = 0

    if ".PDF" in n:
        score += 10

    if str(year) in n:
        score += 5

    if f"FECHA_{round_number}" in n:
        score += 100

    if f"FECHA{round_number}" in n:
        score += 100

    if "CRONOGRAMA" in n:
        score += 100

    if "CARPETA" in n:
        score += 50

    if "MATERIAL" in n:
        score += 50

    if "RESULTADOS" in n:
        score += 20

    return score


def discover_pdfs(
    round_number: int,
    year: int,
    known_articles: list[dict],
) -> list[str]:

    pdfs = set()

    # Primero revisamos los artículos encontrados.
    for article in known_articles:
        html = get_article(article["url"])

        if not html:
            continue

        for pdf in extract_pdf_urls(html, article["url"]):
            pdfs.add(pdf)

    # Luego buscamos directamente en WordPress.
    queries = [
        f"cronograma fecha {round_number}",
        f"cronograma fecha {round_number} {year}",
        f"turismo pista fecha {round_number}",
        f"turismo pista cronograma",
        f"carpeta prensa fecha {round_number}",
        f"material prensa fecha {round_number}",
    ]

    for query in queries:
        print(f"    Buscando PDF: {query}")

        results = search_aptp(query)

        for result in results:
            html = get_article(result["url"])

            if not html:
                continue

            for pdf in extract_pdf_urls(html, result["url"]):
                pdfs.add(pdf)

    # Ordenamos por probabilidad.
    return sorted(
        pdfs,
        key=lambda u: score_pdf_url(u, round_number, year),
        reverse=True,
    )


def calendar_events(year: int) -> list[dict]:
    """
    Obtiene las fechas base del calendario.
    """

    print(f"Buscando Turismo Pista para {year}...")

    queries = [
        f"calendario {year}",
        f"turismo pista calendario {year}",
        f"calendario turismo pista {year}",
    ]

    articles = {}

    for query in queries:
        print(f"Buscando en APTP: {query}")

        for result in search_aptp(query):
            articles[result["url"]] = result

    print(f"Artículos de calendario: {len(articles)}")

    # Buscamos específicamente la nota oficial del calendario.
    selected = None

    for article in articles.values():
        title = normalize(article["title"])

        if "CALENDARIO" in title and "TURISMO PISTA" in title:
            selected = article
            break

    if not selected and articles:
        selected = next(iter(articles.values()))

    if not selected:
        return []

    html = get_article(selected["url"])

    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")

    rows = []

    for tr in soup.find_all("tr"):
        cells = [
            re.sub(r"\s+", " ", td.get_text(" ", strip=True))
            for td in tr.find_all(["td", "th"])
        ]

        if len(cells) < 2:
            continue

        text = " ".join(cells)

        if not re.search(r"\d{1,2}.*(?:ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)", normalize(text)):
            continue

        rows.append(cells)

    events = []

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
        "OCTUBRE": 10,
        "NOVIEMBRE": 11,
        "DICIEMBRE": 12,
    }

    for cells in rows:
        joined = normalize(" ".join(cells))

        round_match = re.search(
            r"(\d{1,2})\s*(?:°|º)?\s*FECHA",
            joined,
        )

        if not round_match:
            continue

        round_number = int(round_match.group(1))

        date_match = re.search(
            r"(\d{1,2})\s*(?:DE)?\s*"
            r"(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|AGOSTO|"
            r"SEPTIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)",
            joined,
        )

        if not date_match:
            continue

        day = int(date_match.group(1))
        month = months[date_match.group(2)]

        date = f"{year:04d}-{month:02d}-{day:02d}"

        location = None

        if "–" in " ".join(cells):
            parts = re.split(r"\s*[–-]\s*", " ".join(cells), maxsplit=1)

            if len(parts) == 2:
                location = parts[1].strip()

        events.append(
            {
                "round": round_number,
                "fecha": date,
                "circuito": location or "Argentina",
                "titulo": f"Turismo Pista - Fecha {round_number}",
                "fuente": selected["url"],
            }
        )

    events.sort(key=lambda x: x["round"])

    # Si la tabla tiene problemas, mantenemos únicamente fechas válidas.
    return events


def find_best_pdf(
    pdf_urls: list[str],
    round_number: int,
    year: int,
    fallback_date: str,
    location: str,
) -> tuple[str | None, str]:

    for url in pdf_urls:
        print(f"    Probando PDF: {url}")

        response = get(url, timeout=60)

        if not response:
            continue

        content_type = response.headers.get("content-type", "").lower()

        if (
            "pdf" not in content_type
            and not url.lower().split("?")[0].endswith(".pdf")
        ):
            continue

        text = pdf_text(response.content)

        if not text:
            continue

        n = normalize(text)

        # Debe ser realmente un cronograma de Turismo Pista.
        if "TURISMO PISTA" not in n:
            continue

        # Debe contener al menos una actividad deportiva.
        sporting_lines = [
            line
            for line in text.splitlines()
            if is_sporting_text(line)
        ]

        if not sporting_lines:
            continue

        sessions = extract_sessions(
            text=text,
            fallback_date=fallback_date,
            round_number=round_number,
            location=location,
        )

        if sessions:
            return url, text

    return None, ""


def main():
    year = datetime.now().year

    print(f"Buscando Turismo Pista para {year}...")

    calendar = calendar_events(year)

    print(f"Fechas del campeonato: {len(calendar)}")

    if not calendar:
        print("No se encontraron fechas del Turismo Pista.")
        return

    all_events = []

    for event in calendar:

        round_number = event["round"]
        fallback_date = event["fecha"]
        location = event["circuito"]

        print()
        print("=" * 38)
        print(
            f"Fecha {round_number}: "
            f"{fallback_date} - {location}"
        )
        print("=" * 38)

        # Buscamos artículos relacionados con esa fecha.
        queries = [
            f"Turismo Pista fecha {round_number} {year}",
            f"Turismo Pista {location} {year}",
            f"Turismo Pista cronograma {year}",
        ]

        articles = {}

        for query in queries:
            print(f"  Buscando: {query}")

            for result in search_aptp(query):
                articles[result["url"]] = result

        article_list = list(articles.values())

        print(f"  Artículos candidatos: {len(article_list)}")

        # Descubrimiento de PDFs.
        pdf_urls = discover_pdfs(
            round_number=round_number,
            year=year,
            known_articles=article_list,
        )

        print(f"  PDFs candidatos: {len(pdf_urls)}")

        if not pdf_urls:
            print(
                "  Sin cronograma publicado todavía. "
                "Se conserva solamente la fecha base."
            )

            # Evento base SIN inventar hora.
            all_events.append(
                {
                    "uid": (
                        f"turismo-pista-{year}-"
                        f"{round_number:02d}-base"
                    ),
                    "fecha": fallback_date,
                    "hora_inicio": None,
                    "hora_fin": None,
                    "titulo": (
                        f"Turismo Pista - "
                        f"Fecha {round_number}"
                    ),
                    "campeonato": "Turismo Pista",
                    "categoria": "Argentina",
                    "disciplina": "Turismo Pista",
                    "clase": None,
                    "grupo": None,
                    "tipo": "Fecha",
                    "ronda": round_number,
                    "circuito": location,
                    "timezone": (
                        "America/Argentina/Buenos_Aires"
                    ),
                    "fuente": (
                        "https://aptpweb.com.ar/"
                    ),
                }
            )

            continue

        best_pdf, pdf_text_content = find_best_pdf(
            pdf_urls=pdf_urls,
            round_number=round_number,
            year=year,
            fallback_date=fallback_date,
            location=location,
        )

        if not best_pdf:
            print(
                "  Se encontraron PDFs, pero ninguno "
                "contiene actividades deportivas válidas."
            )

            all_events.append(
                {
                    "uid": (
                        f"turismo-pista-{year}-"
                        f"{round_number:02d}-base"
                    ),
                    "fecha": fallback_date,
                    "hora_inicio": None,
                    "hora_fin": None,
                    "titulo": (
                        f"Turismo Pista - "
                        f"Fecha {round_number}"
                    ),
                    "campeonato": "Turismo Pista",
                    "categoria": "Argentina",
                    "disciplina": "Turismo Pista",
                    "clase": None,
                    "grupo": None,
                    "tipo": "Fecha",
                    "ronda": round_number,
                    "circuito": location,
                    "timezone": (
                        "America/Argentina/Buenos_Aires"
                    ),
                    "fuente": (
                        "https://aptpweb.com.ar/"
                    ),
                }
            )

            continue

        sessions = extract_sessions(
            text=pdf_text_content,
            fallback_date=fallback_date,
            round_number=round_number,
            location=location,
        )

        print(f"  PDF seleccionado: {best_pdf}")
        print(f"  Actividades deportivas: {len(sessions)}")

        if sessions:
            all_events.extend(sessions)

            for session in sessions:
                print(
                    "   ",
                    session["fecha"],
                    session["hora_inicio"],
                    "-",
                    session["titulo"],
                )

    # Elimina duplicados globales.
    unique = {}

    for event in all_events:
        key = (
            event["uid"],
            event.get("fecha"),
            event.get("hora_inicio"),
            event.get("titulo"),
        )

        unique[key] = event

    all_events = list(unique.values())

    all_events.sort(
        key=lambda x: (
            x.get("fecha") or "9999-99-99",
            x.get("hora_inicio") or "99:99",
            x.get("uid") or "",
        )
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    OUTPUT.write_text(
        json.dumps(
            all_events,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 38)
    print(f"ACTIVIDADES DEPORTIVAS: {len(all_events)}")
    print("=" * 38)
    print(f"Archivo: {OUTPUT}")


if __name__ == "__main__":
    main()
