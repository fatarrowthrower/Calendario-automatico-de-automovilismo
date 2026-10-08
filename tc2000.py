from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin
import json

from bs4 import BeautifulSoup
from curl_cffi import requests


YEAR = datetime.now().year

CALENDAR_URL = "https://tc2000.com.ar/carreras.php?evento=calendario"

DATA_DIR = Path("data")
OUTPUT_FILE = DATA_DIR / "tc2000_events.json"


def clean_text(text):
    return " ".join(text.split())


def get_page(url):
    response = requests.get(
        url,
        impersonate="chrome",
        timeout=30,
    )

    print(f"HTTP: {response.status_code}")
    print(f"URL final: {response.url}")
    print(f"Bytes: {len(response.content)}")

    response.raise_for_status()

    return response.text


def extract_calendar(html):
    soup = BeautifulSoup(html, "html.parser")

    events = []

    boxes = soup.select("div.box-fechas")

    print(f"Bloques de carreras encontrados: {len(boxes)}")
    print()

    for box in boxes:
        round_element = box.select_one("span.item-fechas")
        date_element = box.select_one("span.gris")
        track_element = box.select_one("h3")

        if not round_element or not date_element or not track_element:
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

        parts = date_text.split("-")

        if len(parts) != 2:
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
            continue

        date_string = date.strftime("%Y-%m-%d")

        history_link = box.select_one(
            'a[href*="accion=historial"]'
        )

        if not history_link:
            continue

        history_url = urljoin(
            CALENDAR_URL,
            history_link.get("href"),
        )

        events.append(
            {
                "round": round_number,
                "date": date_string,
                "track": track,
                "history_url": history_url,
            }
        )

    events.sort(
        key=lambda event: event["date"]
    )

    return events


def find_cronograma_image(history_url):
    print(f"Buscando cronograma:")
    print(history_url)

    html = get_page(history_url)

    soup = BeautifulSoup(html, "html.parser")

    cronograma_link = soup.select_one(
        'a[href*="accion=cronograma"]'
    )

    if not cronograma_link:
        print("No se encontró enlace al cronograma.")
        return None

    cronograma_url = urljoin(
        history_url,
        cronograma_link.get("href"),
    )

    print(f"Página cronograma:")
    print(cronograma_url)

    cronograma_html = get_page(cronograma_url)

    cronograma_soup = BeautifulSoup(
        cronograma_html,
        "html.parser",
    )

    image = cronograma_soup.select_one(
        ".texto-cronograma img"
    )

    if not image:
        image = cronograma_soup.select_one(
            'img[src*="noticias"]'
        )

    if not image:
        print("No se encontró imagen del cronograma.")
        return None

    image_src = image.get("src")

    if not image_src:
        print("La imagen no tiene src.")
        return None

    image_url = urljoin(
        cronograma_url,
        image_src,
    )

    print("Imagen del cronograma:")
    print(image_url)

    return image_url


def download_image(image_url, round_number):
    print()
    print("Descargando imagen...")

    response = requests.get(
        image_url,
        impersonate="chrome",
        timeout=30,
    )

    print(f"HTTP imagen: {response.status_code}")
    print(
        f"Content-Type: "
        f"{response.headers.get('content-type')}"
    )
    print(
        f"Tamaño: "
        f"{len(response.content)} bytes"
    )

    response.raise_for_status()

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = (
        DATA_DIR
        / f"tc2000_cronograma_{round_number:02d}.jpg"
    )

    output_file.write_bytes(
        response.content
    )

    print(
        f"Imagen guardada en: {output_file}"
    )

    return output_file


def main():
    print(f"=== TC2000 {YEAR} ===")
    print()

    print("Calendario oficial:")
    print(CALENDAR_URL)
    print()

    calendar_html = get_page(
        CALENDAR_URL
    )

    print()

    races = extract_calendar(
        calendar_html
    )

    print(
        f"Fechas detectadas: {len(races)}"
    )
    print()

    for race in races:
        print(
            f"Fecha {race['round']:02d} | "
            f"{race['date']} | "
            f"{race['track']}"
        )

    print()
    print(
        "=== PROBANDO CRONOGRAMA FECHA 01 ==="
    )
    print()

    if races:
        first_race = races[0]

        image_url = find_cronograma_image(
            first_race["history_url"]
        )

        if image_url:
            download_image(
                image_url,
                first_race["round"],
            )

    print()
    print("=== FIN PRUEBA TC2000 ===")


if __name__ == "__main__":
    main()
