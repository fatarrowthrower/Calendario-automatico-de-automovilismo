from __future__ import annotations

import io
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader


BASE_URL = "https://www.tc2000.com.ar"
YEAR = datetime.now().year

OUTPUT = Path("data/tc2000_events.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
}


def get(url: str, timeout: int = 20) -> requests.Response | None:
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
        print(f"    Error descargando {url}: {exc}")

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

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text.upper()


def month_number(name: str) -> int | None:
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

    return months.get(normalize(name))


def extract_date(text: str) -> str | None:
    text = normalize(text)

    # 27/09/2026
    match = re.search(
        r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b",
        text,
    )

    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))

        return f"{year:04d}-{month:02d}-{day:02d}"

    # 27 DE SEPTIEMBRE DE 2026
    match = re.search(
        r"\b(\d{1,2})\s+DE\s+"
        r"(ENERO|FEBRERO|MARZO|ABRIL|MAYO|JUNIO|JULIO|"
        r"AGOSTO|SEPTIEMBRE|SETIEMBRE|OCTUBRE|NOVIEMBRE|DICIEMBRE)"
        r"\s+DE\s+(\d{4})\b",
        text,
    )

    if match:
        day = int(match.group(1))
        month = month_number(match.group(2))
        year = int(match.group(3))

        if month:
            return f"{year:04d}-{month:02d}-{day:02d}"

    return None


def extract_round(text: str) -> int | None:
    text = normalize(text)

    patterns = [
        r"\bFECHA\s+(\d{1,2})\b",
        r"\b(\d{1,2})[°º]\s*FECHA\b",
        r"\bCAPITULO\s+(\d{1,2})\b",
        r"\bCAP[IÍ]TULO\s+(\d{1,2})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            return int(match.group(1))

    return None


def extract_location(text: str) -> str | None:
    """
    Detecta circuitos argentinos habituales en las noticias.
    """

    normalized = normalize(text)

    locations = [
        ("SAN JUAN", "San Juan"),
        ("TOAY", "Toay"),
        ("LA PAMPA", "La Pampa"),
        ("JUNIN", "Junín"),
        ("JUNÍN", "Junín"),
        ("SAN NICOLAS", "San Nicolás"),
        ("SAN NICOLÁS", "San Nicolás"),
        ("SALTA", "Salta"),
        ("CONCORDIA", "Concordia"),
        ("BUENOS AIRES", "Buenos Aires"),
        ("BUENOS AIRES", "Buenos Aires"),
        ("EL ZONDA", "San Juan"),
        ("EDUARDO COPELLO", "San Juan"),
        ("AUTODROMO DE BUENOS AIRES", "Buenos Aires"),
    ]

    for needle, value in locations:
        if needle in normalized:
            return value

    return None


def get_page(url: str) -> tuple[str, BeautifulSoup] | None:
    response = get(url)

    if not response:
        return None

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    return response.text, soup


def discover_news() -> list[dict]:
    """
    Lee solamente la sección oficial de noticias.
    No utiliza carreras.php?evento=calendario.
    """

    candidates = []

    urls = [
        f"{BASE_URL}/noticias.php",
        f"{BASE_URL}/",
    ]

    seen = set()

    for url in urls:

        print(f"Consultando: {url}")

        result = get_page(url)

        if not result:
            continue

        html, soup = result

        for a in soup.find_all("a", href=True):

            href = a.get("href", "").strip()

            if not href:
                continue

            full_url = urljoin(url, href)

            if not full_url.startswith(BASE_URL):
                continue

            title = clean(
                a.get_text(
                    " ",
                    strip=True,
                )
            )

            if not title:
                continue

            combined = normalize(
                title + " " + full_url
            )

            # Solo noticias claramente relacionadas
            # con TC2000.
            if "TC2000" not in combined:
                continue

            if full_url in seen:
                continue

            seen.add(full_url)

            candidates.append(
                {
                    "url": full_url,
                    "title": title,
                }
            )

    return candidates


def score_news(article: dict) -> int:
    title = normalize(article["title"])
    url = normalize(article["url"])

    score = 0

    if "TC2000" in title:
        score += 20

    if str(YEAR) in title:
        score += 20

    if "HORARIOS" in title:
        score += 100

    if "CRONOGRAMA" in title:
        score += 100

    if "PRACTICA" in title:
        score += 40

    if "CLASIFICACION" in title:
        score += 40

    if "CARRERA" in title:
        score += 30

    if "FECHA" in title:
        score += 30

    if "CAPITULO" in title:
        score += 30

    if "FECHA" in url:
        score += 20

    return score


def extract_pdf_urls(
    html: str,
    page_url: str,
) -> list[str]:

    urls = set()

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    # Enlaces normales.
    for tag in soup.find_all(True):

        for attr in (
            "href",
            "src",
            "data-href",
            "data-url",
            "data-file",
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

    # URLs escritas directamente en HTML/scripts.
    patterns = [
        r'https?://[^"\'>\s]+?\.pdf(?:\?[^"\'>\s]*)?',
        r'//[^"\'>\s]+?\.pdf(?:\?[^"\'>\s]*)?',
    ]

    for pattern in patterns:

        matches = re.findall(
            pattern,
            html,
            flags=re.IGNORECASE,
        )

        for value in matches:

            value = value.strip()

            if value.startswith("//"):
                value = "https:" + value

            if value.startswith("http"):
                urls.add(value)

    return sorted(urls)


def pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(
            io.BytesIO(content)
        )

        pages = []

        for page in reader.pages:
            pages.append(
                page.extract_text() or ""
            )

        return "\n".join(pages)

    except Exception as exc:
        print(f"    Error leyendo PDF: {exc}")
        return ""


def is_sporting_activity(text: str) -> bool:
    n = normalize(text)

    if "TC2000" not in n:
        return False

    sporting = (
        "SHAKEDOWN",
        "PRACTICA",
        "PRUEBA COMUNITARIA",
        "CLASIFICACION",
        "SPRINT",
        "CARRERA",
        "FINAL",
        "WARM-UP",
        "WARM UP",
    )

    administrative = (
        "ACREDITACION",
        "ACREDITACIONES",
        "VERIFICACION TECNICA",
        "VERIFICACION ADMINISTRATIVA",
        "VERIFICACIÓN TÉCNICA",
        "VERIFICACIÓN ADMINISTRATIVA",
        "SORTEO",
        "SELLADO",
        "NEUMATICOS",
        "NEUMÁTICOS",
        "REUNION DE PILOTOS",
        "REUNIÓN DE PILOTOS",
        "BRIEFING",
        "AUTOGRAFOS",
        "AUTÓGRAFOS",
        "CONFERENCIA",
        "PARQUE CERRADO",
        "APERTURA DE BOXES",
        "CIERRE DE BOXES",
        "VUELTA PREVIA",
    )

    if not any(term in n for term in sporting):
        return False

    if any(term in n for term in administrative):
        return False

    return True


def parse_time(
    text: str,
) -> tuple[str | None, str | None]:

    text = (
        text
        .replace("–", "-")
        .replace("—", "-")
    )

    # 10:00 a 10:30
    match = re.search(
        r"\b(\d{1,2}[:.]\d{2})\s*"
        r"(?:A|-)\s*"
        r"(\d{1,2}[:.]\d{2})\b",
        text,
        flags=re.IGNORECASE,
    )

    if match:

        start = match.group(1).replace(".", ":")
        end = match.group(2).replace(".", ":")

        return start, end

    # 10:00 hs
    match = re.search(
        r"\b(\d{1,2}[:.]\d{2})\s*(?:HS)?\b",
        text,
        flags=re.IGNORECASE,
    )

    if match:

        start = match.group(1).replace(".", ":")

        return start, None

    return None, None


def session_type(text: str) -> str:

    n = normalize(text)

    if "SHAKEDOWN" in n:
        return "Shakedown"

    if (
        "PRACTICA" in n
        or "PRUEBA COMUNITARIA" in n
    ):
        return "Entrenamiento"

    if "CLASIFICACION" in n:
        return "Clasificación"

    if "SPRINT" in n:
        return "Sprint"

    if (
        "WARM-UP" in n
        or "WARM UP" in n
    ):
        return "Warm-up"

    if (
        "CARRERA" in n
        or "FINAL" in n
    ):
        return "Carrera"

    return "Actividad"


def extract_group(text: str) -> str | None:

    n = normalize(text)

    match = re.search(
        r"GRUPO\s*[“\"']?\s*([AB])",
        n,
    )

    if match:
        return f"Grupo {match.group(1)}"

    return None


def extract_sessions(
    text: str,
    article: dict,
    fallback_event: dict | None,
) -> list[dict]:

    lines = [
        clean(line)
        for line in text.splitlines()
        if clean(line)
    ]

    sessions = []

    # Intentamos identificar fecha/circuito
    # en el propio documento.
    document_date = extract_date(text)

    document_round = extract_round(
        article["title"] + " " + text
    )

    document_location = extract_location(
        article["title"] + " " + text
    )

    if not document_location and fallback_event:
        document_location = fallback_event.get(
            "circuito"
        )

    if not document_date and fallback_event:
        document_date = fallback_event.get(
            "fecha"
        )

    if not document_round and fallback_event:
        document_round = fallback_event.get(
            "round"
        )

    if not document_date:
        return []

    if not document_round:
        return []

    if not document_location:
        document_location = "Argentina"

    for line in lines:

        if not is_sporting_activity(line):
            continue

        start, end = parse_time(line)

        if not start:
            continue

        tipo = session_type(line)
        group = extract_group(line)

        slug = re.sub(
            r"[^a-z0-9]+",
            "-",
            normalize(line).lower(),
        ).strip("-")

        uid = (
            f"tc2000-{YEAR}-"
            f"{document_round:02d}-"
            f"{document_date}-"
            f"{start.replace(':', '')}-"
            f"{slug[:70]}"
        )

        sessions.append(
            {
                "uid": uid,
                "fecha": document_date,
                "hora_inicio": start,
                "hora_fin": end,
                "titulo": line,
                "campeonato": "TC2000",
                "categoria": "Argentina",
                "disciplina": "TC2000",
                "tipo": tipo,
                "grupo": group,
                "ronda": document_round,
                "circuito": document_location,
                "timezone": (
                    "America/Argentina/Buenos_Aires"
                ),
                "fuente": article["url"],
            }
        )

    # Elimina duplicados.
    unique = {}

    for event in sessions:

        key = (
            event["fecha"],
            event["hora_inicio"],
            event["titulo"],
        )

        unique[key] = event

    return list(unique.values())


def build_base_events(
    articles: list[dict],
) -> list[dict]:

    events = {}

    for article in articles:

        title = article["title"]

        round_number = extract_round(title)

        date = extract_date(title)

        location = extract_location(title)

        if not round_number:
            continue

        if not date:
            continue

        events[round_number] = {
            "round": round_number,
            "fecha": date,
            "circuito": location or "Argentina",
        }

    return list(events.values())


def main():

    print()
    print("=" * 50)
    print(f"TC2000 - {YEAR}")
    print("=" * 50)

    articles = discover_news()

    print()
    print(
        f"Noticias TC2000 encontradas: "
        f"{len(articles)}"
    )

    if not articles:
        print(
            "No se encontraron noticias."
        )
        return

    # Mostramos las más relevantes.
    ranked = sorted(
        articles,
        key=score_news,
        reverse=True,
    )

    print()
    print("Noticias candidatas:")

    for article in ranked[:20]:

        print(
            f"  {article['title']}"
        )
        print(
            f"    {article['url']}"
        )

    # --------------------------------------------------
    # Procesamos únicamente noticias relevantes.
    # --------------------------------------------------

    relevant = []

    for article in ranked:

        score = score_news(article)

        title = normalize(
            article["title"]
        )

        # Priorizamos horarios/cronogramas
        # y noticias específicas de fechas.
        if (
            score >= 30
            or "HORARIOS" in title
            or "CRONOGRAMA" in title
        ):
            relevant.append(article)

    # Evita recorrer cientos de páginas.
    relevant = relevant[:25]

    print()
    print(
        f"Noticias que se van a analizar: "
        f"{len(relevant)}"
    )

    all_events = []

    for article in relevant:

        print()
        print(
            f"Analizando: "
            f"{article['title']}"
        )

        result = get_page(
            article["url"]
        )

        if not result:
            continue

        html, soup = result

        pdfs = extract_pdf_urls(
            html,
            article["url"],
        )

        if pdfs:
            print(
                f"  PDFs encontrados: "
                f"{len(pdfs)}"
            )

        # Primero buscamos cronogramas PDF.
        for pdf_url in pdfs[:5]:

            print(
                f"  PDF: {pdf_url}"
            )

            response = get(
                pdf_url,
                timeout=40,
            )

            if not response:
                continue

            text = pdf_text(
                response.content
            )

            if not text:
                continue

            if "TC2000" not in normalize(text):
                continue

            sessions = extract_sessions(
                text=text,
                article=article,
                fallback_event=None,
            )

            if sessions:

                print(
                    f"    Sesiones: "
                    f"{len(sessions)}"
                )

                all_events.extend(
                    sessions
                )

        # Algunas noticias actuales pueden
        # contener los horarios directamente
        # en HTML y no necesitar PDF.
        page_text = soup.get_text(
            "\n",
            strip=True,
        )

        sessions = extract_sessions(
            text=page_text,
            article=article,
            fallback_event=None,
        )

        if sessions:

            print(
                f"  Sesiones HTML: "
                f"{len(sessions)}"
            )

            all_events.extend(
                sessions
            )

    # --------------------------------------------------
    # Dedupe final
    # --------------------------------------------------

    unique = {}

    for event in all_events:

        key = (
            event["fecha"],
            event["hora_inicio"],
            event["titulo"],
        )

        unique[key] = event

    all_events = list(
        unique.values()
    )

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
    print("=" * 50)
    print(
        f"ACTIVIDADES TC2000: "
        f"{len(all_events)}"
    )
    print("=" * 50)

    for event in all_events[:30]:

        print(
            f"{event['fecha']} "
            f"{event['hora_inicio']} - "
            f"{event['titulo']}"
        )

    if len(all_events) > 30:
        print(
            f"... y "
            f"{len(all_events) - 30} más"
        )

    print()
    print(
        f"Archivo generado: {OUTPUT}"
    )


if __name__ == "__main__":
    main()
