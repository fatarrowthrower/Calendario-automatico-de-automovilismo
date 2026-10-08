from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin
import json
import re

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
        round_element = box.select_one(
            "span.item-fechas"
        )

        date_element = box.select_one(
            "span.gris"
        )

        track_element = box.select_one(
            "h3"
        )

        if (
            not round_element
            or not date_element
            or not track_element
        ):
            continue

        round_text = clean_text(
            round_element.get_text(
                " ",
                strip=True,
            )
        )

        date_text = clean_text(
            date_element.get_text(
                " ",
                strip=True,
            )
        )

        track = clean_text(
            track_element.get_text(
                " ",
                strip=True,
            )
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

        date_string = date.strftime(
            "%Y-%m-%d"
        )

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
    print()
    print("Buscando cronograma:")
    print(history_url)

    html = get_page(history_url)

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    cronograma_link = soup.select_one(
        'a[href*="accion=cronograma"]'
    )

    if not cronograma_link:
        print(
            "No se encontró enlace al cronograma."
        )
        return None

    cronograma_url = urljoin(
        history_url,
        cronograma_link.get("href"),
    )

    print(
        "Página cronograma:"
    )

    print(
        cronograma_url
    )

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
            "No se encontró imagen "
            "del cronograma."
        )
        return None

    image_src = image.get(
        "src"
    )

    if not image_src:
        print(
            "La imagen no tiene src."
        )
        return None

    image_url = urljoin(
        cronograma_url,
        image_src,
    )

    print(
        "Imagen del cronograma:"
    )

    print(
        image_url
    )

    return image_url


def download_image(
    image_url,
    round_number,
):
    print()
    print(
        "Descargando imagen..."
    )

    response = requests.get(
        image_url,
        impersonate="chrome",
        timeout=30,
    )

    print(
        f"HTTP imagen: "
        f"{response.status_code}"
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
        / f"tc2000_cronograma_"
        f"{round_number:02d}.jpg"
    )

    output_file.write_bytes(
        response.content
    )

    print(
        f"Imagen guardada en: "
        f"{output_file}"
    )

    return output_file


def prepare_image(image):
    width, height = image.size

    image = image.resize(
        (
            width * 2,
            height * 2,
        )
    )

    image = image.convert(
        "L"
    )

    image = ImageEnhance.Contrast(
        image
    ).enhance(2.0)

    image = image.filter(
        ImageFilter.SHARPEN
    )

    return image


def run_ocr(image_file):
    print()
    print(
        "Ejecutando OCR..."
    )

    image = Image.open(
        image_file
    )

    prepared = prepare_image(
        image
    )

    text = pytesseract.image_to_string(
        prepared,
        lang="spa+eng",
        config="--psm 6",
    )

    return text


def normalize_ocr_text(text):
    replacements = {
        "TC2OOO": "TC2000",
        "TC2O00": "TC2000",
        "TC2000O": "TC2000",
        "TC 2000": "TC2000",
        "TC-2000": "TC2000",
        "TC 2OOO": "TC2000",
    }

    for old, new in replacements.items():
        text = text.replace(
            old,
            new,
        )

    return text


def extract_time(text):
    pattern = re.compile(
        r"\b([01]?\d|2[0-3])"
        r"\s*:\s*([0-5]\d)"
        r"\s*(?:hs?\.?)?",
        re.IGNORECASE,
    )

    match = pattern.search(
        text
    )

    if not match:
        return None

    hour = int(
        match.group(1)
    )

    minute = int(
        match.group(2)
    )

    return hour, minute


def extract_all_times(text):
    pattern = re.compile(
        r"\b([01]?\d|2[0-3])"
        r"\s*:\s*([0-5]\d)"
        r"\s*(?:hs?\.?)?",
        re.IGNORECASE,
    )

    results = []

    for match in pattern.finditer(
        text
    ):
        hour = int(
            match.group(1)
        )

        minute = int(
            match.group(2)
        )

        results.append(
            (
                hour,
                minute,
            )
        )

    return results


def is_tc2000_line(line):
    normalized = line.upper()

    return (
        "TC2000" in normalized
        or "TC 2000" in normalized
        or "TC2OOO" in normalized
    )


def clean_activity_name(line):
    line = normalize_ocr_text(
        line
    )

    times = extract_all_times(
        line
    )

    for hour, minute in times:
        patterns = [
            rf"\b{hour:02d}\s*:\s*"
            rf"{minute:02d}\s*hs?\.?",
            rf"\b{hour}\s*:\s*"
            rf"{minute:02d}\s*hs?\.?",
        ]

        for pattern in patterns:
            line = re.sub(
                pattern,
                " ",
                line,
                flags=re.IGNORECASE,
            )

    line = re.sub(
        r"\b\d+\s*min\.?",
        " ",
        line,
        flags=re.IGNORECASE,
    )

    line = re.sub(
        r"\s+",
        " ",
        line,
    )

    line = line.strip(
        " -|,.;:"
    )

    return line


def classify_activity(name):
    normalized = name.upper()

    if "CARRERA" in normalized:
        return "Carrera"

    if "CLASIFICACION" in normalized:
        return "Clasificación"

    if "WARM" in normalized:
        return "Warm-Up"

    if "SHAKEDOWN" in normalized:
        return "Shakedown"

    if "PRACTICA" in normalized:
        return "Práctica"

    if "PODIO" in normalized:
        return "Podio"

    if "GRID" in normalized:
        return "Grid"

    if "VUELTA PREVIA" in normalized:
        return "Vuelta previa"

    if "BOXES" in normalized:
        return "Boxes"

    return "Evento"


def find_day_from_text(
    line,
    current_date,
):
    normalized = line.upper()

    weekday_map = {
        "VIERNES": 0,
        "SABADO": 1,
        "SÁBADO": 1,
        "DOMINGO": 2,
    }

    for weekday, offset in weekday_map.items():
        if weekday in normalized:
            return current_date + timedelta(
                days=offset
            )

    return current_date


def parse_tc2000_events(
    ocr_text,
    base_date,
    track,
    round_number,
):
    text = normalize_ocr_text(
        ocr_text
    )

    lines = [
        clean_text(line)
        for line in text.splitlines()
    ]

    lines = [
        line
        for line in lines
        if line
    ]

    events = []

    current_date = base_date

    for line in lines:
        upper = line.upper()

        if "VIERNES" in upper:
            current_date = base_date

        elif (
            "SABADO" in upper
            or "SÁBADO" in upper
        ):
            current_date = (
                base_date
                + timedelta(days=1)
            )

        elif "DOMINGO" in upper:
            current_date = (
                base_date
                + timedelta(days=2)
            )

        if not is_tc2000_line(
            line
        ):
            continue

        times = extract_all_times(
            line
        )

        if not times:
            continue

        activity_name = clean_activity_name(
            line
        )

        if not activity_name:
            continue

        activity_name = re.sub(
            r"^TC2000\s*",
            "",
            activity_name,
            flags=re.IGNORECASE,
        )

        if not activity_name:
            continue

        start_hour, start_minute = (
            times[0]
        )

        if len(times) >= 2:
            end_hour, end_minute = (
                times[1]
            )
        else:
            end_hour = start_hour
            end_minute = (
                start_minute + 5
            )

            if end_minute >= 60:
                end_hour += 1
                end_minute -= 60

        start = current_date.replace(
            hour=start_hour,
            minute=start_minute,
            second=0,
            microsecond=0,
        )

        end = current_date.replace(
            hour=end_hour,
            minute=end_minute,
            second=0,
            microsecond=0,
        )

        if end <= start:
            end = start + timedelta(
                minutes=5
            )

        event_type = classify_activity(
            activity_name
        )

        uid = (
            f"tc2000-"
            f"{YEAR}-"
            f"{round_number:02d}-"
            f"{start.strftime('%Y%m%d-%H%M')}-"
            f"{event_type.lower().replace(' ', '-')}"
        )

        events.append(
            {
                "uid": uid,
                "categoria": "Argentina",
                "campeonato": "TC2000",
                "tipo": event_type,
                "fecha_inicio": start.strftime(
                    "%Y-%m-%dT%H:%M:%S"
                ),
                "fecha_fin": end.strftime(
                    "%Y-%m-%dT%H:%M:%S"
                ),
                "ubicacion": track,
                "descripcion": (
                    f"TC2000 - "
                    f"Fecha {round_number} - "
                    f"{activity_name}"
                ),
                "prioridad": (
                    "alta"
                    if event_type
                    == "Carrera"
                    else "media"
                ),
            }
        )

    return events


def process_race(race):
    print()
    print(
        "========================================"
    )

    print(
        f"TC2000 FECHA "
        f"{race['round']:02d}"
    )

    print(
        f"{race['date']} - "
        f"{race['track']}"
    )

    print(
        "========================================"
    )

    image_url = find_cronograma_image(
        race["history_url"]
    )

    if not image_url:
        return []

    image_file = download_image(
        image_url,
        race["round"],
    )

    try:
        ocr_text = run_ocr(
            image_file
        )

        print()
        print(
            "Texto OCR obtenido:"
        )
        print(
            ocr_text
        )

        base_date = datetime.strptime(
            race["date"],
            "%Y-%m-%d",
        )

        events = parse_tc2000_events(
            ocr_text,
            base_date,
            race["track"],
            race["round"],
        )

        print()
        print(
            f"Eventos TC2000 detectados: "
            f"{len(events)}"
        )

        for event in events:
            print(
                f"{event['fecha_inicio']} | "
                f"{event['fecha_fin']} | "
                f"{event['descripcion']}"
            )

        return events

    finally:
        if image_file.exists():
            image_file.unlink()

            print()
            print(
                f"Imagen temporal eliminada: "
                f"{image_file}"
            )


def main():
    print(
        f"=== TC2000 {YEAR} ==="
    )

    print()
    print(
        "Fuente oficial:"
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

    all_events = []

    for race in races:
        try:
            events = process_race(
                race
            )

            all_events.extend(
                events
            )

        except Exception as exc:
            print()
            print(
                f"ERROR procesando "
                f"Fecha {race['round']:02d}: "
                f"{exc}"
            )

    all_events.sort(
        key=lambda event:
        event["fecha_inicio"]
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
            all_events,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print(
        "========================================"
    )

    print(
        f"Eventos TC2000 totales: "
        f"{len(all_events)}"
    )

    print(
        f"Archivo generado: "
        f"{OUTPUT_FILE}"
    )

    print(
        "========================================"
    )

    print()
    print(
        "=== FIN TC2000 ==="
    )


if __name__ == "__main__":
    main()
