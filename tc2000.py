from datetime import datetime
from pathlib import Path
import json

from bs4 import BeautifulSoup
from curl_cffi import requests


YEAR = datetime.now().year

URL = "https://tc2000.com.ar/carreras.php?evento=calendario"

DATA_DIR = Path("data")
OUTPUT_FILE = DATA_DIR / "tc2000_events.json"


def clean_text(text):
    return " ".join(text.split())


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


def extract_events(html):
    soup = BeautifulSoup(html, "html.parser")

    events = []

    # Cada carrera está dentro de:
    #
    # <div class="box-fechas">
    #
    # y contiene:
    #
    # <span class="item-fechas">01</span>
    # <span class="gris">15-03</span>
    # <h3>Callejero de Buenos Aires</h3>

    boxes = soup.select("div.box-fechas")

    print(f"Bloques de carreras encontrados: {len(boxes)}")
    print()

    for box in boxes:
        round_element = box.select_one("span.item-fechas")
        date_element = box.select_one("span.gris")
        track_element = box.select_one("h3")

        if not round_element:
            continue

        if not date_element:
            continue

        if not track_element:
            continue

        round_text = clean_text(
            round_element.get_text(" ", strip=True)
        )

        date_text = clean_text(
            date_element.get_text(" ", strip=True)
        )

        track = clean_text(
            track_element.get_text(" ", strip=True)
        )

        try:
            round_number = int(round_text)
        except ValueError:
            continue

        # El sitio utiliza DD-MM.
        parts = date_text.split("-")

        if len(parts) != 2:
            print(
                f"Fecha inválida en Fecha {round_number}: "
                f"{date_text}"
            )
            continue

        try:
            day = int(parts[0])
            month = int(parts[1])

            date = datetime(
                YEAR,
                month,
                day,
            )
        except ValueError:
            print(
                f"Fecha inválida en Fecha {round_number}: "
                f"{date_text}"
            )
            continue

        date_string = date.strftime("%Y-%m-%d")

        uid = f"tc2000-{YEAR}-{round_number:02d}"

        event = {
            "uid": uid,
            "categoria": "Argentina",
            "campeonato": "TC2000",
            "tipo": "Carrera",
            "fecha_inicio": f"{date_string}T12:00:00",
            "fecha_fin": f"{date_string}T18:00:00",
            "ubicacion": track,
            "descripcion": (
                f"TC2000 - Fecha {round_number} "
                f"- {track}"
            ),
            "prioridad": "alta",
        }

        events.append(event)

    events.sort(
        key=lambda event: event["fecha_inicio"]
    )

    return events


def main():
    print(f"=== TC2000 {YEAR} ===")
    print(f"Fuente oficial: {URL}")
    print()

    html = get_page()

    print()

    events = extract_events(html)

    print()
    print(f"Fechas detectadas: {len(events)}")
    print()

    for event in events:
        print(
            f'{event["descripcion"]} | '
            f'{event["fecha_inicio"]}'
        )

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

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
