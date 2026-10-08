import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytesseract
from bs4 import BeautifulSoup
from curl_cffi import requests as curl_requests
from PIL import Image, ImageEnhance, ImageFilter


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUT = DATA / "tc2000_events.json"

YEAR = datetime.now().year

CALENDAR_URL = (
    "https://www.tc2000.com.ar/"
    "carreras.php?evento=calendario"
)


# ============================================================
# UTILIDADES
# ============================================================

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
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


def normalize_ocr(text):
    text = clean_text(text)

    replacements = {
        "TC2OOO": "TC2000",
        "TC2OO0": "TC2000",
        "TC200O": "TC2000",
        "TC 2000": "TC2000",
        "CLASIFICACI6N": "CLASIFICACION",
        "CLASIFICACI0N": "CLASIFICACION",
        "PRACTlCA": "PRACTICA",
        "SHAKED0WN": "SHAKEDOWN",
        "WARM-UP": "WARM UP",
        "WARMUP": "WARM UP",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


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


# ============================================================
# CALENDARIO OFICIAL
# ============================================================

def parse_calendar():
    print(f"TC2000: consultando calendario oficial {YEAR}")

    response = fetch(CALENDAR_URL)

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    races = []

    for box in soup.select("div.box-fechas"):

        # Ejemplo:
        # <span class="item-fechas">01</span>
        round_span = box.select_one(
            "span.item-fechas"
        )

        if not round_span:
            continue

        round_text = clean_text(
            round_span.get_text(
                " ",
                strip=True,
            )
        )

        if not round_text.isdigit():
            continue

        round_number = int(round_text)

        # Ejemplo:
        # <span class="gris">15-03</span>
        date_span = box.select_one(
            "span.gris"
        )

        if not date_span:
            print(
                f"TC2000: Fecha {round_number:02d}: "
                "no se encontró fecha"
            )
            continue

        date_text = clean_text(
            date_span.get_text(
                " ",
                strip=True,
            )
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
                f"fecha inválida: {exc}"
            )
            continue

        # Circuito.
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
            track = (
                f"TC2000 Fecha "
                f"{round_number:02d}"
            )

        # Buscamos el historial oficial.
        history_link = None

        for link in box.find_all(
            "a",
            href=True,
        ):
            href = link["href"]

            if (
                "carreras.php" in href
                and "accion=historial" in href
                and "id=" in href
            ):
                history_link = href
                break

        # Fallback.
        if not history_link:
            for link in box.find_all(
                "a",
                href=True,
            ):
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

        elif history_link.startswith(
            "carreras.php"
        ):
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


# ============================================================
# CRONOGRAMA
# ============================================================

def find_cronograma_url(history_url):
    response = fetch(history_url)

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    candidates = []

    for link in soup.find_all(
        "a",
        href=True,
    ):
        href = link["href"]

        text = clean_text(
            link.get_text(
                " ",
                strip=True,
            )
        )

        if (
            "cronograma" in text.lower()
            or "cronograma" in href.lower()
        ):
            candidates.append(href)

    for href in candidates:

        if href.startswith("/"):
            return (
                "https://www.tc2000.com.ar"
                + href
            )

        if href.startswith("http"):
            return href

        if href.startswith(
            "carreras.php"
        ):
            return (
                "https://www.tc2000.com.ar/"
                + href
            )

    # Fallback por HTML.
    match = re.search(
        r"carreras\.php\?accion=cronograma&id=(\d+)",
        response.text,
        re.IGNORECASE,
    )

    if match:
        return (
            "https://www.tc2000.com.ar/"
            "carreras.php?accion=cronograma"
            f"&id={match.group(1)}"
        )

    return None


def find_cronograma_image(
    cronograma_url,
):
    response = fetch(cronograma_url)

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    candidates = []

    # --------------------------------------------------------
    # IMG
    # --------------------------------------------------------

    for img in soup.find_all("img"):

        possible_urls = []

        for attr in (
            "src",
            "data-src",
            "data-original",
        ):
            value = img.get(attr)

            if value:
                possible_urls.append(value)

        srcset = img.get("srcset")

        if srcset:
            for item in srcset.split(","):
                possible_urls.append(
                    item.strip().split(" ")[0]
                )

        for src in possible_urls:

            src = src.strip()

            if not src:
                continue

            if src.lower().startswith(
                "file://"
            ):
                continue

            lower = src.lower()

            # Nunca usar logos, sponsors, redes sociales, etc.
            if any(
                bad in lower
                for bad in (
                    "logo",
                    "sponsor",
                    "facebook",
                    "instagram",
                    "twitter",
                    "whatsapp",
                )
            ):
                continue

            if src.startswith("//"):
                src = "https:" + src

            elif src.startswith("/"):
                src = (
                    "https://www.tc2000.com.ar"
                    + src
                )

            elif not src.startswith("http"):
                src = (
                    "https://www.tc2000.com.ar/"
                    + src
                )

            candidates.append(src)

    # --------------------------------------------------------
    # META OG IMAGE
    # --------------------------------------------------------

    for meta in soup.find_all("meta"):

        prop = (
            meta.get("property")
            or meta.get("name")
            or ""
        ).lower()

        content = meta.get("content")

        if not content:
            continue

        if prop not in (
            "og:image",
            "twitter:image",
        ):
            continue

        content = content.strip()

        if content.lower().startswith(
            "file://"
        ):
            continue

        lower = content.lower()

        if any(
            bad in lower
            for bad in (
                "logo",
                "sponsor",
            )
        ):
            continue

        if content.startswith("//"):
            content = "https:" + content

        elif content.startswith("/"):
            content = (
                "https://www.tc2000.com.ar"
                + content
            )

        candidates.append(content)

    # --------------------------------------------------------
    # LINKS A IMÁGENES
    # --------------------------------------------------------

    for link in soup.find_all(
        "a",
        href=True,
    ):
        href = link["href"].strip()

        if href.lower().startswith(
            "file://"
        ):
            continue

        lower = href.lower()

        if not lower.endswith(
            (
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
            )
        ):
            continue

        if any(
            bad in lower
            for bad in (
                "logo",
                "sponsor",
            )
        ):
            continue

        if href.startswith("//"):
            href = "https:" + href

        elif href.startswith("/"):
            href = (
                "https://www.tc2000.com.ar"
                + href
            )

        candidates.append(href)

    # --------------------------------------------------------
    # PUNTUACIÓN
    # --------------------------------------------------------

    scored = []

    for url in candidates:

        lower = url.lower()

        score = 0

        if "cronograma" in lower:
            score += 20

        if "noticias" in lower:
            score += 10

        if lower.endswith(".jpg"):
            score += 5

        if lower.endswith(".jpeg"):
            score += 5

        if lower.endswith(".png"):
            score += 1

        # El logo ya fue filtrado, pero mantenemos
        # esta defensa adicional.
        if "logo-tc2000" in lower:
            continue

        if "sponsors" in lower:
            continue

        scored.append(
            (
                score,
                url,
            )
        )

    scored.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    for _, url in scored:

        if url.startswith("http"):
            return url

    return None


# ============================================================
# IMAGEN + OCR
# ============================================================

def download_image(
    url,
    destination,
):
    response = fetch(url)

    destination.write_bytes(
        response.content
    )

    return destination


def preprocess_image(path):
    image = Image.open(path)

    width, height = image.size

    # Mejoramos resolución para OCR.
    if width < 1800:

        factor = 1800 / width

        image = image.resize(
            (
                int(width * factor),
                int(height * factor),
            )
        )

    image = image.convert("L")

    image = ImageEnhance.Contrast(
        image
    ).enhance(2.0)

    image = image.filter(
        ImageFilter.SHARPEN
    )

    return image


def ocr_image(path):
    image = preprocess_image(path)

    text = pytesseract.image_to_string(
        image,
        lang="spa+eng",
        config="--psm 6",
    )

    return text


# ============================================================
# HORARIOS
# ============================================================

def normalize_dotted_times(text):
    """
    Convierte:

        10.50 -> 10:50
        13.40 -> 13:40

    pero solamente cuando los minutos están
    entre 00 y 59.
    """

    def replace(match):
        hour = int(match.group(1))
        minute = int(match.group(2))

        if (
            0 <= hour <= 23
            and 0 <= minute <= 59
        ):
            return (
                f"{hour:02d}:{minute:02d}"
            )

        return match.group(0)

    return re.sub(
        r"(?<!\d)(\d{1,2})[.](\d{2})(?!\d)",
        replace,
        text,
    )


def extract_times(text):
    text = normalize_dotted_times(
        text
    )

    matches = re.findall(
        r"(?<!\d)"
        r"([01]?\d|2[0-3]):"
        r"([0-5]\d)"
        r"(?!\d)",
        text,
    )

    result = []

    for hour, minute in matches:

        value = (
            f"{int(hour):02d}:"
            f"{minute}"
        )

        if value not in result:
            result.append(value)

    return result


# ============================================================
# BLOQUES POR DÍA
# ============================================================

def split_schedule_blocks(lines):
    """
    Separa el OCR en bloques de días.

    Buscamos los comienzos típicos:

      APERTURA DE ACREDITACIONES

      ENTRADA DE LOS SERVICIOS DE PISTA

    El último bloque se asigna al día oficial
    de la carrera.
    """

    starts = []

    for index, line in enumerate(lines):

        normalized = (
            normalize_ocr(line)
            .upper()
        )

        is_start = False

        if (
            "APERTURA DE ACREDITACIONES"
            in normalized
        ):
            is_start = True

        elif (
            "APERTURA DE ACREDITACION"
            in normalized
        ):
            is_start = True

        elif (
            "ENTRADA DE LOS SERVICIOS DE PISTA"
            in normalized
        ):
            is_start = True

        elif (
            "ENTRADA DE SERVICIOS DE PISTA"
            in normalized
        ):
            is_start = True

        elif (
            "ENTRADA DE LOS SERVICIOS A PISTA"
            in normalized
        ):
            is_start = True

        if is_start:
            starts.append(index)

    # Eliminamos detecciones repetidas
    # demasiado cercanas.
    filtered = []

    for index in starts:

        if (
            not filtered
            or index - filtered[-1] > 3
        ):
            filtered.append(index)

    if not filtered:
        return [lines]

    blocks = []

    for i, start in enumerate(
        filtered
    ):

        if i + 1 < len(filtered):
            end = filtered[i + 1]
        else:
            end = len(lines)

        block = lines[start:end]

        if block:
            blocks.append(block)

    return blocks


# ============================================================
# FILTROS TC2000
# ============================================================

def is_shared_activity(line):
    upper = normalize_ocr(line).upper()

    # Actividades que NO queremos en el calendario principal.
    excluded_phrases = [
        "VERIFICACION TECNICA",
        "VERIFICACION ADMINISTRATIVA",
        "VERIFICACION TECNICO",
        "INSCRIPCION",
        "ACREDITACION",
        "ACREDITACIONES",
        "SORTEO DE NEUMATICOS",
        "SORTEO DE NEUMÁTICOS",
        "REUNION DE PILOTOS",
        "REUNIÓN DE PILOTOS",
        "RECINTO TECNICO",
        "RECINTO TÉCNICO",
        "CONFERENCIA",
        "ENTREVISTAS",
        "PRENSA",

        # Actividades operativas que no son una sesión
        # deportiva que queramos mostrar.
        "APERTURA DE BOX",
        "APERTURA DE BOXES",
        "CIERRE DE BOX",
        "CIERRE DE BOXES",
        "DESPEJE DE GRILLA",
        "INICIO TRANSMISION",
        "FINAL TRANSMISION",
        "PARQUE CERRADO",
        "PILOTOS AUTORIZADOS",
    ]

    for phrase in excluded_phrases:
        if phrase in upper:
            return True

    # Si aparecen varias categorías juntas,
    # normalmente es una actividad compartida.
    if "//" in upper:
        return True

    other_categories = [
        "TOP RACE",
        "FORMULA NACIONAL",
        "F.N.A",
        "FNA",
        "FIAT COMPETIZIONE",
        "TR SERIES",
        "TR JUNIOR",
    ]

    for category in other_categories:
        if category in upper:
            return True

    return False

def is_tc2000_line(line):
    upper = normalize_ocr(line).upper()

    return (
        "TC2000" in upper
        or "TC 2000" in upper
        or "TC2OOO" in upper
    )


# ============================================================
# NOMBRE Y TIPO DE SESIÓN
# ============================================================

def classify_activity(name):
    upper = normalize_ocr(name).upper()

    if "CARRERA" in upper:
        return "Carrera"

    if (
        "CLASIFIC" in upper
        or "QUALY" in upper
    ):
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

    text = normalize_dotted_times(
        text
    )

    # Quitamos horarios.
    text = re.sub(
        r"(?<!\d)"
        r"([01]?\d|2[0-3]):[0-5]\d"
        r"(?!\d)",
        "",
        text,
    )

    # Quitamos duraciones.
    text = re.sub(
        r"\b\d+\s*"
        r"(?:MIN|MINUTOS|M|HS|HORA|HORAS)"
        r"\b",
        "",
        text,
        flags=re.IGNORECASE,
    )

    upper = text.upper()

    position = upper.find(
        "TC2000"
    )

    if position >= 0:
        text = text[
            position
            + len("TC2000"):
        ]

    text = text.replace(
        "TC 2000",
        "",
    )

    text = text.replace(
        "TC2OOO",
        "",
    )

    text = re.sub(
        r"[/|]+",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    text = text.strip(
        " -_:;.,|/"
    )

    return text


def parse_line(line):
    if not is_tc2000_line(line):
        return None

    if is_shared_activity(line):
        return None

    times = extract_times(line)

    if not times:
        return None

    name = clean_activity_name(
        line
    )

    if not name:
        return None

    upper = name.upper()

    for other in (
        "TOP RACE",
        "FORMULA NACIONAL",
        "F.N.A",
        "FIAT",
        "TR SERIES",
        "TR JUNIOR",
    ):
        if other in upper:
            return None

    return {
        "name": name,
        "type": classify_activity(
            name
        ),
        "times": times,
    }


# ============================================================
# CREACIÓN DE EVENTOS
# ============================================================

def create_event(
    round_number,
    track,
    session_date,
    parsed,
):
    times = parsed["times"]

    start_time = times[0]

    if len(times) >= 2:

        end_time = times[1]

    else:
        # Cuando el cronograma oficial solamente
        # publica una hora, usamos un evento técnico
        # de 1 minuto. La hora de inicio sí es oficial.
        hour, minute = map(
            int,
            start_time.split(":"),
        )

        start_dt = datetime(
            session_date.year,
            session_date.month,
            session_date.day,
            hour,
            minute,
        )

        end_dt = (
            start_dt
            + timedelta(minutes=1)
        )

        end_time = (
            end_dt.strftime("%H:%M")
        )

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
        "fuente": (
            "https://www.tc2000.com.ar/"
        ),
        "round": round_number,
    }


# ============================================================
# PARSEAR CRONOGRAMA
# ============================================================

def parse_schedule(
    ocr_text,
    base_date,
    round_number,
    track,
):
    normalized = normalize_ocr(
        ocr_text
    )

    lines = [
        line.strip()
        for line in normalized.splitlines()
        if line.strip()
    ]

    # --------------------------------------------------------
    # Separar por bloques/días.
    #
    # El último bloque siempre es el día
    # de la carrera publicado en el calendario.
    # --------------------------------------------------------

    blocks = split_schedule_blocks(
        lines
    )

    print(
        f"TC2000: Fecha {round_number:02d}: "
        f"bloques detectados = {len(blocks)}"
    )

    if not blocks:
        print(
            f"TC2000: Fecha {round_number:02d}: "
            "no se detectaron bloques"
        )
        return []

    assigned_blocks = []

    for index, block in enumerate(
        blocks
    ):

        days_back = (
            len(blocks)
            - 1
            - index
        )

        session_date = (
            base_date
            - timedelta(
                days=days_back
            )
        )

        assigned_blocks.append(
            (
                session_date,
                block,
            )
        )

    print(
        f"TC2000: Fecha {round_number:02d}: "
        f"rango de fechas "
        f"{assigned_blocks[0][0].isoformat()} "
        f"-> "
        f"{assigned_blocks[-1][0].isoformat()}"
    )

    events = []

    for session_date, block in (
        assigned_blocks
    ):

        for line in block:

            parsed = parse_line(
                line
            )

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


# ============================================================
# PROCESAR UNA FECHA
# ============================================================

def process_race(race):
    round_number = race["round"]

    base_date = datetime.fromisoformat(
        race["base_date"]
    ).date()

    track = race["track"]

    history_url = race[
        "history_url"
    ]

    print(
        f"\nTC2000: procesando Fecha "
        f"{round_number:02d} - {track}"
    )

    cronograma_url = (
        find_cronograma_url(
            history_url
        )
    )

    if not cronograma_url:

        print(
            f"TC2000: Fecha {round_number:02d}: "
            "no se encontró cronograma"
        )

        return []

    print(
        f"TC2000: cronograma: "
        f"{cronograma_url}"
    )

    image_url = (
        find_cronograma_image(
            cronograma_url
        )
    )

    if not image_url:

        print(
            f"TC2000: Fecha {round_number:02d}: "
            "no se encontró imagen válida "
            "del cronograma"
        )

        return []

    print(
        f"TC2000: imagen: "
        f"{image_url}"
    )

    temp_image = DATA / (
        f"tc2000_cronograma_"
        f"{round_number:02d}.jpg"
    )

    try:

        download_image(
            image_url,
            temp_image,
        )

        ocr_text = ocr_image(
            temp_image
        )

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


# ============================================================
# MAIN
# ============================================================

def main():
    DATA.mkdir(
        parents=True,
        exist_ok=True,
    )

    races = parse_calendar()

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

            print(
                f"TC2000: ERROR en Fecha "
                f"{race['round']:02d}: "
                f"{exc}"
            )

    # Eliminamos duplicados.
    unique = {}

    for event in all_events:
        unique[event["uid"]] = event

    all_events = list(
        unique.values()
    )

    # Orden cronológico.
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
        f"TC2000: archivo generado: "
        f"{OUTPUT}"
    )


if __name__ == "__main__":
    main()
