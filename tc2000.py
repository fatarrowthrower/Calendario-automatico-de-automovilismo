from datetime import datetime
from pathlib import Path
import json
import re

from bs4 import BeautifulSoup
from curl_cffi import requests


YEAR = datetime.now().year

URL = "https://tc2000.com.ar/carreras.php?evento=calendario"

DATA_DIR = Path("data")
OUTPUT_FILE = DATA_DIR / "tc2000_events.json"


def get_page():
    response = requests.get(
        URL,
        impersonate="chrome",
        timeout=30,
    )

    print(f"HTTP: {response.status_code}")
    print(f"URL final: {response.url}")
    print(f"Bytes: {len(response.content)}")

    response.raise_for_status()

    return response.text


def clean_text(text):
    return " ".join(text.split())


def extract_date(text):
    """
    Busca fechas argentinas del tipo:
    12/04/2026
    12-04-2026
    12.04.2026
    """

    match = re.search(
        r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b",
        text,
    )

    if not match:
        return None

    day = int(match.group(1))
    month = int(match.group(2))
    year = int(match.group(3))

    if year != YEAR:
        return None

    try:
        return datetime(year, month, day).strftime("%Y-%m-%d")
    except ValueError:
        return None


def extract_round(text):
    """
    Busca:
    1° Fecha
    2° Fecha
    10° Fecha
    """

    match = re.search(
        r"\b(\d{1,2})[°ºo]?\s*Fecha\b",
        text,
        re.IGNORECASE,
    )

    if match:
        return int(match.group(1))

    return None


def extract_events(html):
    soup = BeautifulSoup(html, "html.parser")

    events = []
    seen = set()

    # Primero buscamos bloques que contengan "Fecha".
    candidates = soup.find_all(
        string=re.compile(r"\bFecha\b", re.IGNORECASE)
    )

    for text_node in candidates:
        parent = text_node.parent

        if parent is None:
            continue

        # Subimos algunos niveles para intentar encontrar
        # el bloque completo de la fecha.
        block = parent

        for _ in range(4):
            if block.parent is None:
                break

            candidate_text = clean_text(
                block.get_text(" ", strip=True)
            )

            if len(candidate_text) > 20:
                break

            block = block.parent

        text = clean_text(
            block.get_text(" ", strip=True)
        )

        if not text:
            continue

        round_number = extract_round(text)

        if round_number is None:
            continue

        date = extract_date(text)

        # Si el bloque no contiene fecha, intentamos buscarla
        # en el bloque padre inmediato.
        if date is None and block.parent is not None:
            parent_text = clean_text(
                block.parent.get_text(" ", strip=True)
            )
            date = extract_date(parent_text)

        if date is None:
            continue

        # Intentamos obtener un nombre limpio.
        name_match = re.search(
            r"\d{1,2}[°ºo]?\s*Fecha\s+(.+?)\s+20\d{2}",
            text,
            re.IGNORECASE,
        )

        if name_match:
            location = clean_text(name_match.group(1))
        else:
            location = f"Fecha {round_number}"

        # Limpiamos algunos textos que puedan haber quedado pegados.
        location = re.sub(
            r"\bRESULTADOS\b.*$",
            "",
            location,
            flags=re.IGNORECASE,
        )

        location = clean_text(location)

        uid = f"tc2000-{YEAR}-{round_number:02d}"

        if uid in seen:
            continue

        seen.add(uid)

        events.append(
            {
                "uid": uid,
                "categoria": "Argentina",
                "campeonato": "TC2000",
                "tipo": "Carrera",
                "fecha_inicio": f"{date}T12:00:00",
                "fecha_fin": f"{date}T18:00:00",
                "ubicacion": location,
                "descripcion": f"TC2000 - Fecha {round_number}",
                "prioridad": "alta",
            }
        )

    events.sort(
        key=lambda event: event["fecha_inicio"]
    )

    return events


def main():
    print(f"=== TC2000 {YEAR} ===")
    print(f"Fuente oficial: {URL}")
    print()

    html = get_page()

    events = extract_events(html)

    print()
    print(f"Fechas detectadas: {len(events)}")
    print()

    for event in events:
        print(
            f'{event["descripcion"]} | '
            f'{event["fecha_inicio"]} | '
            f'{event["ubicacion"]}'
        )

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            events,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print(f"Archivo generado: {OUTPUT_FILE}")
    print("=== FIN TC2000 ===")


if __name__ == "__main__":
    main()
