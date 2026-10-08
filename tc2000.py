from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin
import json

from bs4 import BeautifulSoup
from curl_cffi import requests
from PIL import Image, ImageEnhance, ImageFilter
import pytesseract


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
    print("Buscando cronograma:")
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

    print("Página cronograma:")
    print(cronograma_url)

    cronograma_html = get_page(
        cronograma_url
    )

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
        print(
            "No se encontró imagen del cronograma."
        )
        return None

    image_src = image.get("src")

    if not image_src:
        print(
            "La imagen no tiene src."
        )
        return None

    image_url = urljoin(
        cronograma_url,
        image_src,
    )

    print()
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

    print(
        f"HTTP imagen: {response.status_code}"
    )

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


def prepare_image(image):
    """
    Prepara la imagen para mejorar la lectura OCR.
    """

    # Escala la imagen para darle más resolución al OCR.
    width, height = image.size

    image = image.resize(
        (
            width * 2,
            height * 2,
        )
    )

    # Convierte a escala de grises.
    image = image.convert("L")

    # Aumenta el contraste.
    image = ImageEnhance.Contrast(
        image
    ).enhance(2.0)

    # Suaviza pequeños artefactos.
    image = image.filter(
        ImageFilter.SHARPEN
    )

    return image


def run_ocr(image_file):
    print()
    print("=== OCR TC2000 ===")
    print()

    print(
        f"Archivo: {image_file}"
    )

    image = Image.open(
        image_file
    )

    print(
        f"Tamaño original: "
        f"{image.size[0]}x{image.size[1]}"
    )

    prepared = prepare_image(
        image
    )

    print(
        f"Tamaño para OCR: "
        f"{prepared.size[0]}x{prepared.size[1]}"
    )

    print()
    print("Ejecutando Tesseract...")
    print()

    text = pytesseract.image_to_string(
        prepared,
        lang="spa+eng",
        config="--psm 6",
    )

    print(
        "========== TEXTO OCR =========="
    )

    print(text)

    print(
        "======== FIN TEXTO OCR ========"
    )

    return text


def main():
    print(
        f"=== TC2000 {YEAR} - PRUEBA OCR ==="
    )

    print()

    print(
        "Calendario oficial:"
    )

    print(
        CALENDAR_URL
    )

    print()

    calendar_html = get_page(
        CALENDAR_URL
    )

    print()

    races = extract_calendar(
        calendar_html
    )

    print(
        f"Fechas detectadas: "
        f"{len(races)}"
    )

    print()

    for race in races:
        print(
            f"Fecha {race['round']:02d} | "
            f"{race['date']} | "
            f"{race['track']}"
        )

    if not races:
        print(
            "No se encontraron fechas."
        )
        return

    print()
    print(
        "=== PROBANDO OCR FECHA 01 ==="
    )
    print()

    first_race = races[0]

    image_url = find_cronograma_image(
        first_race["history_url"]
    )

    if not image_url:
        print(
            "No se pudo encontrar "
            "la imagen del cronograma."
        )
        return

    image_file = download_image(
        image_url,
        first_race["round"],
    )

    run_ocr(
        image_file
    )

    print()
    print(
        "=== FIN PRUEBA OCR ==="
    )


if __name__ == "__main__":
    main()
