import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
from curl_cffi import requests as curl_requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUT = DATA / "tc2000_events.json"

YEAR = datetime.now().year

CALENDAR_URL = "https://www.tc2000.com.ar/carreras.php?evento=calendario"

MONTHS = {
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

WEEKDAYS = {
    "LUNES": 0,
    "MARTES": 1,
    "MIERCOLES": 2,
    "JUEVES": 3,
    "VIERNES": 4,
    "SABADO": 5,
    "DOMINGO": 6,
}


def clean_text(text):
    replacements = {
        "\xa0": " ",
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
        "SÁBADO": "SABADO",
        "SÁBADOS": "SABADOS",
        "DOMINGO": "DOMINGO",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = text.replace("I4", "14")
    text = text.replace("IS", "15")

    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def current_year():
    return datetime.now().year


def get_session():
    return curl_requests.Session(
        impersonate="chrome",
        timeout=30,
    )


def fetch(url):
    session = get_session()

    response = session.get(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0 Safari/537.36"
            )
        },
    )

    response.raise_for_status()
    return response


def parse_calendar():
    print(f"TC2000: consultando calendario oficial {YEAR}")

    response = fetch(CALENDAR_URL)
    soup = BeautifulSoup(response.text, "html.parser")

    races = []

    for box in soup.select("div.box-fechas"):
        # El número de fecha está en:
        # <span class="item-fechas">01</span>
        round_span = box.select_one("span.item-fechas")

        if not round_span:
            continue

        round_text = clean_text(
            round_span.get_text(" ", strip=True)
        )

        if not round_text.isdigit():
            continue

        round_number = int(round_text)

        # La fecha está en:
        # <span class="gris">15-03</span>
        date_span = box.select_one("span.gris")

        if not date_span:
            print(
                f"TC2000: Fecha {round_number:02d}: "
                "no se encontró fecha"
            )
            continue

        date_text = clean_text(
            date_span.get_text(" ", strip=True)
        )

        date_match = re.search(
            r"(\d{1,2})-(\d{1,2})",
            date_text,
        )

        if not date_match:
            print(
                f"TC2000: Fecha {round_number:02d}: "
                f"fecha inválida: {date_text}"
            )
            continue

        day = int(date_match.group(1))
        month = int(date_match.group(2))

        try:
            base_date = datetime(
                YEAR,
                month,
                day,
            ).date()
        except ValueError as exc:
            print(
                f"TC2000: Fecha {round_number:02d}: "
                f"fecha inválida {date_text}: {exc}"
            )
            continue

        # Nombre del circuito.
        track = ""

        track_heading = box.find("h3")

        if track_heading:
            track = clean_text(
                track_heading.get_text(
                    " ",
                    strip=True,
                )
            )

        if not track:
            track = f"TC2000 Fecha {round_number:02d}"

        # Buscamos el enlace al historial.
        history_link = None

        for link in box.find_all("a", href=True):
            href = link["href"]

            if (
                "carreras.php" in href
                and "accion=historial" in href
                and "id=" in href
            ):
                history_link = href
                break

        # Fallback: cualquier enlace de historial.
        if not history_link:
            for link in box.find_all("a", href=True):
                href = link["href"]

                if (
                    "historial" in href.lower()
                    and "id=" in href.lower()
                ):
                    history_link = href
                    break

        if not history_link:
            print(
                f"TC2000: Fecha {round_number:02d}: "
                "no se encontró página histórica"
            )
            continue

        if history_link.startswith("/"):
            history_link = (
                "https://www.tc2000.com.ar"
                + history_link
            )

        elif history_link.startswith("carreras.php"):
            history_link = (
                "https://www.tc2000.com.ar/"
                + history_link
            )

        races.append(
            {
                "round": round_number,
                "base_date": base_date.isoformat(),
                "track": track,
                "history_url": history_link,
            }
        )

        print(
            f"TC2000: Fecha {round_number:02d} - "
            f"{base_date.isoformat()} - {track}"
        )

    races.sort(
        key=lambda race: race["round"]
    )

    print(
        f"TC2000: {len(races)} fechas encontradas"
    )

    return races


def find_cronograma_url(history_url):
    response = fetch(history_url)
    soup = BeautifulSoup(response.text, "html.parser")

    candidates = []

    for link in soup.find_all("a", href=True):
        href = link["href"]
        text = clean_text(link.get_text(" ", strip=True))

        if "cronograma" in text.lower() or "cronograma" in href.lower():
            candidates.append(href)

    for href in candidates:
        if href.startswith("/"):
            return "https://www.tc2000.com.ar" + href

        if href.startswith("http"):
            return href

    # Fallback: buscar directamente la acción de cronograma
    match = re.search(
        r"carreras\.php\?accion=cronograma&id=(\d+)",
        response.text,
        re.IGNORECASE,
    )

    if match:
        return (
            "https://www.tc2000.com.ar/"
            f"carreras.php?accion=cronograma&id={match.group(1)}"
        )

    return None


def find_cronograma_image(cronograma_url):
    response = fetch(cronograma_url)

    soup = BeautifulSoup(response.text, "html.parser")

    candidates = []

    # Primero buscamos imágenes del contenido principal.
    for img in soup.find_all("img"):
        src = img.get("src")

        if not src:
            continue

        src = src.strip()

        if src.lower().startswith("file://"):
            continue

        if src.startswith("//"):
            src = "https:" + src

        elif src.startswith("/"):
            src = "https://www.tc2000.com.ar" + src

        elif not src.startswith("http"):
            src = "https://www.tc2000.com.ar/" + src

        candidates.append(src)

    # También revisamos og:image.
    for meta in soup.find_all("meta"):
        prop = (
            meta.get("property")
            or meta.get("name")
            or ""
        ).lower()

        content = meta.get("content")

        if content and prop in (
            "og:image",
            "twitter:image",
        ):
            content = content.strip()

            if content.lower().startswith("file://"):
                continue

            if content.startswith("//"):
                content = "https:" + content
            elif content.startswith("/"):
                content = "https://www.tc2000.com.ar" + content

            candidates.append(content)

    # Priorizamos imágenes que parezcan cronogramas.
    scored = []

    for url in candidates:
        lower = url.lower()

        score = 0

        if "cronograma" in lower:
            score += 10

        if "noticias" in lower:
            score += 5

        if lower.endswith(".jpg"):
            score += 2

        if lower.endswith(".jpeg"):
            score += 2

        if lower.endswith(".png"):
            score += 1

        scored.append((score, url))

    scored.sort(reverse=True)

    for _, url in scored:
        if url.startswith("http"):
            return url

    return None


def download_image(url, destination):
    response = fetch(url)

    destination.write_bytes(response.content)

    return destination


def preprocess_image(path):
    image = Image.open(path)

    # Escalamos para mejorar OCR.
    width, height = image.size

    if width < 1800:
        factor = 1800 / width
        image = image.resize(
            (
                int(width * factor),
                int(height * factor),
            )
        )

    image = image.convert("L")

    image = ImageEnhance.Contrast(image).enhance(2.0)

    image = image.filter(ImageFilter.SHARPEN)

    return image


def ocr_image(path):
    image = preprocess_image(path)

    text = pytesseract.image_to_string(
        image,
        lang="spa+eng",
        config="--psm 6",
    )

    return text


def normalize_ocr(text):
    text = clean_text(text)

    replacements = {
        "TC2OOO": "TC2000",
        "TC2OO0": "TC2000",
        "TC200O": "TC2000",
        "TC 2000": "TC2000",
        "CLASIFICACI6N": "CLASIFICACION",
        "CLASIFICACI0N": "CLASIFICACION",
        "PRACTICA": "PRACTICA",
        "PRACTlCA": "PRACTICA",
        "SHAKED0WN": "SHAKEDOWN",
        "WARM-UP": "WARM UP",
        "WARMUP": "WARM UP",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


def normalize_dotted_times(text):
    """
    Convierte:
        10.50 -> 10:50
        13.40 -> 13:40

    Solo acepta minutos 00-59 para evitar convertir números
    que no son horarios.
    """

    def replace(match):
        hour = int(match.group(1))
        minute = int(match.group(2))

        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"

        return match.group(0)

    return re.sub(
        r"(?<!\d)(\d{1,2})[.](\d{2})(?!\d)",
        replace,
        text,
    )


def extract_times(text):
    text = normalize_dotted_times(text)

    matches = re.findall(
        r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)",
        text,
    )

    result = []

    for hour, minute in matches:
        value = f"{int(hour):02d}:{minute}"

        if value not in result:
            result.append(value)

    return result


def parse_header_dates(text, base_date):
    """
    Determina qué días contiene el cronograma.

    El calendario oficial del TC2000 usa como fecha base normalmente
    el domingo de la competencia.

    Por eso:
      VIERNES -> base_date - 2
      SABADO  -> base_date - 1
      DOMINGO -> base_date

    No dependemos de que OCR lea correctamente 13/14/15.
    """

    upper = normalize_ocr(text[:5000]).upper()

    found = []

    for weekday, number in WEEKDAYS.items():
        if re.search(rf"\b{weekday}\b", upper):
            found.append((number, weekday))

    dates = {}

    for weekday_number, weekday_name in found:
        if weekday_number == 6:
            date = base_date

        elif weekday_number == 5:
            date = base_date - timedelta(days=1)

        elif weekday_number == 4:
            date = base_date - timedelta(days=2)

        else:
            # Para cualquier otro día buscamos la fecha más cercana
            # anterior a la fecha oficial.
            delta = (base_date.weekday() - weekday_number) % 7

            if delta == 0:
                date = base_date
            else:
                date = base_date - timedelta(days=delta)

        dates[weekday_name] = date

    # Orden natural del cronograma.
    ordered = []

    for weekday in (
        "LUNES",
        "MARTES",
        "MIERCOLES",
        "JUEVES",
        "VIERNES",
        "SABADO",
        "DOMINGO",
    ):
        if weekday in dates:
            ordered.append(
                {
                    "weekday": weekday,
                    "date": dates[weekday],
                }
            )

    # Normalmente solo nos interesan los últimos días encontrados.
    if "DOMINGO" in dates:
        if "VIERNES" in dates:
            ordered = [
                x
                for x in ordered
                if x["weekday"] in (
                    "VIERNES",
                    "SABADO",
                    "DOMINGO",
                )
            ]

        elif "SABADO" in dates:
            ordered = [
                x
                for x in ordered
                if x["weekday"] in (
                    "SABADO",
                    "DOMINGO",
                )
            ]

    return ordered


def split_schedule_blocks(lines):
    """
    Intenta separar el OCR en bloques por día.

    Los cronogramas del TC2000 normalmente arrancan cada día con:
      APERTURA DE ACREDITACIONES
    o:
      ENTRADA DE LOS SERVICIOS DE PISTA

    Esto permite separar viernes/sábado/domingo sin inventar
    fechas basándonos simplemente en la posición de la línea.
    """

    starts = []

    for index, line in enumerate(lines):
        normalized = normalize_ocr(line).upper()

        if (
            "APERTURA DE ACREDITACIONES" in normalized
            or "APERTURA DE ACREDITACION" in normalized
            or "ENTRADA DE LOS SERVICIOS DE PISTA" in normalized
            or "ENTRADA DE LOS SERVICIOS DE PISTA" in normalized.replace(
                "  ", " "
            )
            or "ENTRADA DE SERVICIOS DE PISTA" in normalized
        ):
            starts.append(index)

    # Evitamos duplicados muy cercanos.
    filtered = []

    for index in starts:
        if not filtered or index - filtered[-1] > 3:
            filtered.append(index)

    if not filtered:
        return [lines]

    blocks = []

    for i, start in enumerate(filtered):
        end = (
            filtered[i + 1]
            if i + 1 < len(filtered)
            else len(lines)
        )

        block = lines[start:end]

        if block:
            blocks.append(block)

    return blocks


def is_shared_activity(line):
    upper = normalize_ocr(line).upper()

    # Actividades administrativas o compartidas que NO son
    # una sesión propia del TC2000.
    excluded_phrases = [
        "VERIFICACION TECNICA",
        "VERIFICACION ADMINISTRATIVA",
        "INSCRIPCION",
        "INSCRIPCIÓN",
        "AAV",
        "ACREDITACION",
        "ACREDITACIONES",
        "SORTEO DE NEUMATICOS",
        "SORTEO DE NEUMÁTICOS",
        "REUNION DE PILOTOS",
        "REUNIÓN DE PILOTOS",
        "RECINTO TECNICO",
        "RECINTO TÉCNICO",
        "RETIRO DE SERVICIOS",
        "CONFERENCIA",
        "PRENSA",
        "ENTREVISTAS",
    ]

    for phrase in excluded_phrases:
        if phrase in upper:
            return True

    # Si aparecen varias categorías juntas, normalmente es una
    # actividad compartida y no una sesión de TC2000.
    other_categories = [
        "TOP RACE",
        "FORMULA NACIONAL",
        "F.N.A",
        "FNA",
        "FIAT",
        "TR SERIES",
        "TR JUNIOR",
        "CATEGORIA COMPARTIDA",
    ]

    if "//" in upper:
        return True

    found_other = sum(
        1
        for category in other_categories
        if category in upper
    )

    if found_other >= 1:
        return True

    return False


def is_tc2000_line(line):
    upper = normalize_ocr(line).upper()

    return (
        "TC2000" in upper
        or "TC 2000" in upper
        or "TC2OOO" in upper
    )


def classify_activity(name):
    upper = normalize_ocr(name).upper()

    if "CARRERA" in upper:
        return "Carrera"

    if "CLASIFIC" in upper or "QUALY" in upper:
        return "Clasificación"

    if "WARM" in upper:
        return "Warm-Up"

    if "SHAKEDOWN" in upper:
        return "Shakedown"

    if "PRACTICA" in upper:
        return "Práctica"

    if "GRID SHOW" in upper:
        return "Grid"

    if "PODIO" in upper:
        return "Podio"

    if "VUELTA PREVIA" in upper:
        return "Carrera"

    return "Sesión"


def clean_activity_name(line):
    text = normalize_ocr(line)

    # Quitamos horarios.
    text = normalize_dotted_times(text)

    text = re.sub(
        r"(?<!\d)([01]?\d|2[0-3]):[0-5]\d(?!\d)",
        "",
        text,
    )

    # Quitamos duraciones comunes.
    text = re.sub(
        r"\b\d+\s*(?:MIN|MINUTOS|M|HS|HORA|HORAS)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Buscamos desde TC2000 para eliminar ruido OCR previo.
    upper = text.upper()

    position = upper.find("TC2000")

    if position >= 0:
        text = text[position + len("TC2000"):]

    text = text.replace("TC 2000", "")
    text = text.replace("TC2OOO", "")

    # Limpiamos separadores.
    text = re.sub(r"[/|]+", " ", text)
    text = re.sub(r"\s+", " ", text)

    text = text.strip(" -_:;.,|/")

    return text


def parse_line(line):
    if not is_tc2000_line(line):
        return None

    if is_shared_activity(line):
        return None

    times = extract_times(line)

    if not times:
        return None

    name = clean_activity_name(line)

    if not name:
        return None

    # Si quedaron otros campeonatos en el nombre, no es una
    # sesión limpia de TC2000.
    upper = name.upper()

    for other in (
        "TOP RACE",
        "FORMULA NACIONAL",
        "F.N.A",
        "FIAT",
    ):
        if other in upper:
            return None

    activity_type = classify_activity(name)

    return {
        "name": name,
        "type": activity_type,
        "times": times,
    }


def create_event(round_number, track, session_date, parsed):
    times = parsed["times"]

    start_time = times[0]

    if len(times) >= 2:
        end_time = times[1]
    else:
        # No inventamos una duración real.
        # Usamos un minuto técnico para representar un evento
        # cuyo cronograma oficial solo informa hora de inicio.
        hour, minute = map(int, start_time.split(":"))

        start_dt = datetime(
            session_date.year,
            session_date.month,
            session_date.day,
            hour,
            minute,
        )

        end_dt = start_dt + timedelta(minutes=1)

        end_time = end_dt.strftime("%H:%M")

    uid_name = re.sub(
        r"[^a-z0-9]+",
        "-",
        parsed["name"].lower(),
    ).strip("-")

    uid = (
        f"tc2000-"
        f"{YEAR}-"
        f"{round_number:02d}-"
        f"{session_date.isoformat()}-"
        f"{start_time.replace(':', '')}-"
        f"{uid_name}"
    )

    return {
        "uid": uid,
        "fecha": session_date.isoformat(),
        "inicio": start_time,
        "fin": end_time,
        "categoria": "Argentina",
        "campeonato": "TC2000",
        "tipo": parsed["type"],
        "nombre": parsed["name"],
        "circuito": track,
        "fuente": "https://www.tc2000.com.ar/",
        "round": round_number,
    }


def parse_schedule(
    ocr_text,
    base_date,
    round_number,
    track,
):
    normalized = normalize_ocr(ocr_text)

    lines = [
        line.strip()
        for line in normalized.splitlines()
        if line.strip()
    ]

    dates = parse_header_dates(
        normalized,
        base_date,
    )

    print(
        f"TC2000: Fecha {round_number:02d}: "
        f"días detectados = "
        f"{', '.join(x['weekday'] for x in dates)}"
    )

    blocks = split_schedule_blocks(lines)

    # Si la cantidad de bloques coincide con la cantidad de días,
    # tenemos una asignación segura.
    if len(blocks) == len(dates):
        assigned_blocks = list(zip(dates, blocks))

    else:
        print(
            f"TC2000: Fecha {round_number:02d}: "
            f"bloques detectados={len(blocks)}, "
            f"días={len(dates)}"
        )

        # Si no podemos asignar con seguridad, intentamos una
        # estrategia conservadora.
        if len(dates) == 1:
            assigned_blocks = [
                (
                    dates[0],
                    lines,
                )
            ]

        elif len(blocks) >= len(dates):
            assigned_blocks = list(
                zip(
                    dates,
                    blocks[:len(dates)],
                )
            )

        else:
            print(
                f"TC2000: Fecha {round_number:02d}: "
                "no se pudo determinar con seguridad "
                "la fecha de cada bloque."
            )

            return []

    events = []

    for day_info, block in assigned_blocks:
        session_date = day_info["date"]

        for line in block:
            parsed = parse_line(line)

            if not parsed:
                continue

            event = create_event(
                round_number=round_number,
                track=track,
                session_date=session_date,
                parsed=parsed,
            )

            events.append(event)

    return events


def process_race(race):
    round_number = race["round"]
    base_date = datetime.fromisoformat(
        race["base_date"]
    ).date()

    track = race["track"]
    history_url = race["history_url"]

    print(
        f"\nTC2000: procesando Fecha "
        f"{round_number:02d} - {track}"
    )

    cronograma_url = find_cronograma_url(
        history_url
    )

    if not cronograma_url:
        print(
            f"TC2000: Fecha {round_number:02d}: "
            "no se encontró cronograma"
        )
        return []

    print(
        f"TC2000: cronograma: {cronograma_url}"
    )

    image_url = find_cronograma_image(
        cronograma_url
    )

    if not image_url:
        print(
            f"TC2000: Fecha {round_number:02d}: "
            "no se encontró imagen externa del cronograma"
        )
        return []

    print(
        f"TC2000: imagen: {image_url}"
    )

    temp_image = DATA / (
        f"tc2000_cronograma_{round_number:02d}.jpg"
    )

    try:
        download_image(
            image_url,
            temp_image,
        )

        ocr_text = ocr_image(temp_image)

        events = parse_schedule(
            ocr_text=ocr_text,
            base_date=base_date,
            round_number=round_number,
            track=track,
        )

        print(
            f"TC2000: Fecha {round_number:02d}: "
            f"{len(events)} eventos"
        )

        return events

    finally:
        if temp_image.exists():
            temp_image.unlink()


def main():
    DATA.mkdir(parents=True, exist_ok=True)

    races = parse_calendar()

    all_events = []

    for race in races:
        try:
            events = process_race(race)
            all_events.extend(events)

        except Exception as exc:
            print(
                f"TC2000: ERROR en Fecha "
                f"{race['round']:02d}: {exc}"
            )

    # Eliminamos duplicados por UID.
    unique = {}

    for event in all_events:
        unique[event["uid"]] = event

    all_events = list(unique.values())

    all_events.sort(
        key=lambda event: (
            event["fecha"],
            event["inicio"],
            event["round"],
            event["nombre"],
        )
    )

    OUTPUT.write_text(
        json.dumps(
            all_events,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"\nTC2000: total final = "
        f"{len(all_events)} eventos"
    )

    print(
        f"TC2000: archivo generado: {OUTPUT}"
    )


if __name__ == "__main__":
    main()
