import json
import re
import unicodedata
from datetime import datetime, date, time, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


YEAR = datetime.now().year

BASE = "https://actc.org.ar"
TIMEZONE = "America/Argentina/Buenos_Aires"

OUTPUT = Path("data/actc_events.json")

CATEGORIES = {
    "TC": {
        "slug": "tc",
        "name": "Turismo Carretera",
    },
    "TCP": {
        "slug": "tcp",
        "name": "TC Pista",
    },
    "TCPK": {
        "slug": "tcpk",
        "name": "TC Pick Up",
    },
}


# ------------------------------------------------------------
# UTILIDADES
# ------------------------------------------------------------

def clean_text(value):
    if not value:
        return ""

    value = unicodedata.normalize("NFKC", value)
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize(value):
    value = clean_text(value)

    value = unicodedata.normalize("NFD", value)
    value = "".join(
        c for c in value
        if unicodedata.category(c) != "Mn"
    )

    return value.lower()


def slugify(value):
    value = normalize(value)
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def parse_date(text):
    """
    Busca fechas argentinas dentro de texto.
    Ejemplos:
      25.10.26
      25/10/2026
      25 de octubre de 2026
    """

    text = clean_text(text)

    m = re.search(
        r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b",
        text
    )

    if m:
        day = int(m.group(1))
        month = int(m.group(2))
        year = int(m.group(3))

        if year < 100:
            year += 2000

        try:
            return date(year, month, day)
        except ValueError:
            pass

    months = {
        "enero": 1,
        "febrero": 2,
        "marzo": 3,
        "abril": 4,
        "mayo": 5,
        "junio": 6,
        "julio": 7,
        "agosto": 8,
        "septiembre": 9,
        "setiembre": 9,
        "octubre": 10,
        "noviembre": 11,
        "diciembre": 12,
    }

    m = re.search(
        r"\b(\d{1,2})\s+de\s+"
        r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
        r"septiembre|setiembre|octubre|noviembre|diciembre)"
        r"\s+(?:de\s+)?(\d{4})\b",
        normalize(text),
    )

    if m:
        day = int(m.group(1))
        month = months[m.group(2)]
        year = int(m.group(3))

        try:
            return date(year, month, day)
        except ValueError:
            pass

    return None


def parse_time(value):
    """
    Convierte:
      09:30
      9:30
      09.30
      9 hs
    a time().
    """

    if not value:
        return None

    value = value.strip().lower()
    value = value.replace(".", ":")
    value = value.replace("hs", "")
    value = value.strip()

    m = re.search(r"\b(\d{1,2}):(\d{2})\b", value)

    if not m:
        return None

    hour = int(m.group(1))
    minute = int(m.group(2))

    if hour > 23 or minute > 59:
        return None

    return time(hour, minute)


def duration_for_session(session_type):
    """
    Duraciones conservadoras.
    Si ACTC publica horario de inicio y fin,
    se usa el fin real.
    """

    t = normalize(session_type)

    if "entrenamiento" in t:
        return timedelta(minutes=30)

    if "clasificacion" in t or "clasificatoria" in t:
        return timedelta(minutes=15)

    if "serie" in t:
        return timedelta(minutes=20)

    if "final" in t or "carrera" in t:
        return timedelta(minutes=45)

    return timedelta(minutes=30)


def make_uid(category, round_number, event_date, start_time, session_name):
    raw = (
        f"actc-{category}-{YEAR}-{round_number}-"
        f"{event_date.isoformat()}-"
        f"{start_time.strftime('%H%M') if start_time else 'all-day'}-"
        f"{slugify(session_name)}"
    )

    return slugify(raw)


# ------------------------------------------------------------
# HTTP
# ------------------------------------------------------------

def requests_session():
    session = requests.Session()

    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0 Safari/537.36"
        ),
        "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    })

    return session


# ------------------------------------------------------------
# CALENDARIO OFICIAL
# ------------------------------------------------------------

def get_calendar(category, session):
    slug = CATEGORIES[category]["slug"]

    url = f"{BASE}/{slug}/calendario"

    print(f"\n[{category}] Calendario:")
    print(url)

    response = session.get(url, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    text = clean_text(soup.get_text(" ", strip=True))

    events = []

    # --------------------------------------------------------
    # Método principal:
    # localizar bloques "Fecha N"
    # --------------------------------------------------------

    headings = soup.find_all(
        string=re.compile(r"Fecha\s+\d+", re.I)
    )

    for heading in headings:
        raw_heading = clean_text(heading)

        match = re.search(
            r"Fecha\s+(\d+)",
            raw_heading,
            re.I,
        )

        if not match:
            continue

        round_number = int(match.group(1))

        # Subimos unos niveles para encontrar el bloque completo.
        container = heading.parent

        for _ in range(5):
            if container is None:
                break

            candidate = clean_text(
                container.get_text(" ", strip=True)
            )

            if (
                "2026" in candidate
                or str(YEAR) in candidate
            ):
                if len(candidate) < 1200:
                    break

            container = container.parent

        if container is None:
            continue

        block = clean_text(
            container.get_text(" ", strip=True)
        )

        event_date = parse_date(block)

        if not event_date:
            continue

        if event_date.year != YEAR:
            continue

        # ----------------------------------------------------
        # Evitar "A CONFIRMAR"
        # ----------------------------------------------------

        normalized_block = normalize(block)

        location = ""

        # Intentamos encontrar circuito + ciudad.
        parts = [
            clean_text(x)
            for x in re.split(r"—|-", block)
        ]

        if len(parts) >= 2:
            location = parts[-1]

        if (
            "a confirmar" in normalized_block
            or "por confirmar" in normalized_block
        ):
            location = "A confirmar"

        if not location:
            location = CATEGORIES[category]["name"]

        # Limpiamos ruido.
        location = re.sub(
            r"\bVer resultados\b.*$",
            "",
            location,
            flags=re.I,
        )

        location = clean_text(location)

        # ----------------------------------------------------
        # Circuito
        # ----------------------------------------------------

        circuit = ""

        circuit_match = re.search(
            r"(?:—|-)\s*([^—|-]+?)\s*—\s*"
            r"[^—|-]+,\s*[^—|-]+",
            block,
        )

        if circuit_match:
            circuit = clean_text(circuit_match.group(1))

        if not circuit:
            circuit = location

        events.append({
            "categoria": category,
            "campeonato": CATEGORIES[category]["name"],
            "round": round_number,
            "fecha": event_date.isoformat(),
            "ubicacion": location,
            "circuito": circuit,
            "fuente": url,
            "horarios_url": None,
        })

    # --------------------------------------------------------
    # Segundo método de respaldo:
    # analizar todo el texto cuando el HTML cambia.
    # --------------------------------------------------------

    if not events:

        pattern = re.compile(
            r"Fecha\s+(\d+).*?"
            r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})",
            re.I,
        )

        for match in pattern.finditer(text):

            round_number = int(match.group(1))
            day = int(match.group(2))
            month = int(match.group(3))
            year = int(match.group(4))

            if year < 100:
                year += 2000

            if year != YEAR:
                continue

            try:
                event_date = date(year, month, day)
            except ValueError:
                continue

            window = text[
                match.start():
                match.start() + 700
            ]

            events.append({
                "categoria": category,
                "campeonato": CATEGORIES[category]["name"],
                "round": round_number,
                "fecha": event_date.isoformat(),
                "ubicacion": "",
                "circuito": "",
                "fuente": url,
                "horarios_url": None,
            })

    # Deduplicar.
    unique = {}

    for event in events:
        key = (
            event["categoria"],
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

    print(
        f"[{category}] Fechas encontradas: {len(events)}"
    )

    return events


# ------------------------------------------------------------
# DESCUBRIR CRONOGRAMA
# ------------------------------------------------------------

def discover_cronograma(page, event):
    """
    Busca cualquier enlace relacionado con cronograma
    dentro de la página oficial de la categoría.

    No depende de un ID fijo.
    """

    links = page.locator("a").all()

    candidates = []

    for link in links:
        try:
            href = link.get_attribute("href")
            text = clean_text(link.inner_text())
        except Exception:
            continue

        if not href:
            continue

        absolute = urljoin(BASE, href)

        combined = normalize(
            f"{text} {absolute}"
        )

        if "cronograma" in combined:
            candidates.append(absolute)

    # Eliminar duplicados preservando orden.
    result = []

    for url in candidates:
        if url not in result:
            result.append(url)

    if result:
        return result[0]

    return None


# ------------------------------------------------------------
# NOTICIAS ACTC
# ------------------------------------------------------------

def get_news_candidates(category, session, event):
    """
    Busca noticias oficiales relacionadas con la fecha.

    No depende de un ID concreto.
    """

    slug = CATEGORIES[category]["slug"]

    url = f"{BASE}/{slug}/noticias"

    try:
        response = session.get(
            url,
            timeout=30,
        )

        if response.status_code != 200:
            return []

    except Exception:
        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    target_city = normalize(
        event.get("ubicacion", "")
    )

    candidates = []

    for anchor in soup.find_all("a", href=True):

        href = urljoin(BASE, anchor["href"])
        title = clean_text(anchor.get_text(" ", strip=True))

        combined = normalize(
            f"{title} {href}"
        )

        if not any(
            word in combined
            for word in (
                "horarios",
                "cronograma",
                "horario",
            )
        ):
            continue

        # Priorizamos la ciudad.
        score = 0

        if target_city and target_city != "a confirmar":
            if normalize(target_city) in combined:
                score += 10

        if event["fecha"]:
            dt = datetime.fromisoformat(
                event["fecha"]
            ).date()

            date_forms = [
                dt.strftime("%d/%m"),
                dt.strftime("%d-%m"),
                dt.strftime("%d.%m"),
            ]

            if any(
                form in combined
                for form in date_forms
            ):
                score += 5

        candidates.append(
            (score, href, title)
        )

    candidates.sort(
        key=lambda x: x[0],
        reverse=True,
    )

    return [
        {
            "url": href,
            "title": title,
        }
        for score, href, title in candidates[:10]
    ]


# ------------------------------------------------------------
# EXTRAER HORARIOS DE TEXTO
# ------------------------------------------------------------

TIME_RANGE_RE = re.compile(
    r"\b"
    r"(\d{1,2}[:.]\d{2})"
    r"\s*(?:a|-|–|—)\s*"
    r"(\d{1,2}[:.]\d{2})"
    r"(?:\s*hs?\.?)?"
    r"\b",
    re.I,
)

SINGLE_TIME_RE = re.compile(
    r"\b"
    r"(\d{1,2}[:.]\d{2})"
    r"(?:\s*hs?\.?)?"
    r"\b",
    re.I,
)


def extract_session_name(text):
    """
    Intenta convertir una línea de cronograma
    en un nombre de sesión.
    """

    text = clean_text(text)

    # Eliminamos prefijos de hora.
    text = TIME_RANGE_RE.sub("", text)
    text = SINGLE_TIME_RE.sub("", text)

    text = re.sub(
        r"^\s*[-|:]\s*",
        "",
        text,
    )

    text = clean_text(text)

    # Eliminamos indicaciones de duración.
    text = re.sub(
        r"\(?\s*\d+\s*(?:min|mins|minutos|vueltas).*?\)?",
        "",
        text,
        flags=re.I,
    )

    return clean_text(text)


def category_matches_line(category, line):
    """
    Determina si una línea pertenece a TC, TCP o TCPK.
    """

    n = normalize(line)

    if category == "TCPK":
        return (
            "tcpk" in n
            or "tc pick up" in n
            or "tc pickup" in n
        )

    if category == "TCP":
        if "tcpk" in n:
            return False

        return (
            re.search(r"\btcp\b", n) is not None
            or "tc pista" in n
        )

    if category == "TC":
        if "tcpk" in n:
            return False

        if re.search(r"\btcp\b", n):
            return False

        return (
            re.search(r"\btc\b", n) is not None
            or "turismo carretera" in n
        )

    return False


def parse_schedule_text(
    text,
    category,
    event,
):
    """
    Extrae sesiones de texto visible.

    Soporta formatos como:

    TCP - 08:30 a 08:40 Hs. 1er Entrenamiento

    TC - 11:05 a 11:25 Hs. 2do Entrenamiento

    TCPK | 09:30 a 10:10 Hs. 1er Entrenamiento

    TCPK | 11:10 Hs. 1ra Serie
    """

    lines = [
        clean_text(x)
        for x in text.splitlines()
    ]

    # Si la página devuelve todo en una sola línea,
    # intentamos separarlo por categorías.
    if len(lines) < 5:
        lines = [
            clean_text(x)
            for x in re.split(
                r"(?=(?:TC|TCP|TCPK)\s*[-|:])",
                text,
                flags=re.I,
            )
            if clean_text(x)
        ]

    sessions = []

    current_date = event["fecha"]

    for line in lines:

        if not line:
            continue

        if not category_matches_line(
            category,
            line,
        ):
            continue

        range_match = TIME_RANGE_RE.search(line)

        if range_match:
            start = parse_time(
                range_match.group(1)
            )
            end = parse_time(
                range_match.group(2)
            )
        else:
            single_match = SINGLE_TIME_RE.search(line)

            if not single_match:
                continue

            start = parse_time(
                single_match.group(1)
            )

            end = None

        if not start:
            continue

        session_name = extract_session_name(line)

        if not session_name:
            session_name = "Actividad"

        # Evitar capturar horarios de TV.
        if "horario de tv" in normalize(session_name):
            continue

        sessions.append({
            "fecha": current_date,
            "inicio": start.strftime("%H:%M"),
            "fin": (
                end.strftime("%H:%M")
                if end
                else (
                    datetime.combine(
                        date.today(),
                        start,
                    )
                    + duration_for_session(
                        session_name
                    )
                ).strftime("%H:%M")
            ),
            "nombre": session_name,
        })

    # Deduplicar.
    unique = {}

    for session in sessions:
        key = (
            session["fecha"],
            session["inicio"],
            normalize(session["nombre"]),
        )

        unique[key] = session

    return list(unique.values())


# ------------------------------------------------------------
# PLAYWRIGHT
# ------------------------------------------------------------

def render_page(browser, url):
    page = browser.new_page(
        viewport={
            "width": 1440,
            "height": 1200,
        }
    )

    try:
        print(f"  Abriendo: {url}")

        page.goto(
            url,
            wait_until="networkidle",
            timeout=60000,
        )

        page.wait_for_timeout(3000)

        text = page.locator("body").inner_text(
            timeout=15000
        )

        html = page.content()

        return page, text, html

    except Exception as exc:
        print(
            f"  Error cargando {url}: {exc}"
        )

        try:
            page.close()
        except Exception:
            pass

        return None, "", ""


# ------------------------------------------------------------
# BUSCAR HORARIOS
# ------------------------------------------------------------

def find_schedule(
    browser,
    session,
    category,
    event,
):
    """
    Estrategia completa:

    1. cronograma desde página oficial
    2. noticias oficiales
    3. página principal de la carrera
    """

    slug = CATEGORIES[category]["slug"]

    urls = []

    # --------------------------------------------------------
    # Página principal de categoría
    # --------------------------------------------------------

    urls.append(
        f"{BASE}/{slug}"
    )

    # --------------------------------------------------------
    # Página de noticias
    # --------------------------------------------------------

    urls.append(
        f"{BASE}/{slug}/noticias"
    )

    # --------------------------------------------------------
    # Noticias descubiertas por requests
    # --------------------------------------------------------

    for candidate in get_news_candidates(
        category,
        session,
        event,
    ):
        urls.append(candidate["url"])

    # Deduplicar.
    unique_urls = []

    for url in urls:
        if url not in unique_urls:
            unique_urls.append(url)

    # --------------------------------------------------------
    # Abrir páginas
    # --------------------------------------------------------

    for url in unique_urls:

        page, text, html = render_page(
            browser,
            url,
        )

        if not page:
            continue

        try:
            # ------------------------------------------------
            # 1. Buscar enlaces a cronograma
            # ------------------------------------------------

            cronograma_url = discover_cronograma(
                page,
                event,
            )

            if cronograma_url:
                print(
                    f"  Cronograma encontrado: "
                    f"{cronograma_url}"
                )

                if cronograma_url not in unique_urls:
                    page2, text2, html2 = render_page(
                        browser,
                        cronograma_url,
                    )

                    if page2:
                        sessions = parse_schedule_text(
                            text2,
                            category,
                            event,
                        )

                        page2.close()

                        if sessions:
                            page.close()
                            return (
                                sessions,
                                cronograma_url,
                            )

            # ------------------------------------------------
            # 2. Buscar horarios en página actual
            # ------------------------------------------------

            sessions = parse_schedule_text(
                text,
                category,
                event,
            )

            if sessions:
                page.close()
                return (
                    sessions,
                    url,
                )

        finally:
            try:
                page.close()
            except Exception:
                pass

    return [], None


# ------------------------------------------------------------
# EVENTOS FINALES
# ------------------------------------------------------------

def build_events(
    calendar_events,
    schedules,
):
    output = []

    for event in calendar_events:

        category = event["categoria"]
        round_number = event["round"]
        event_date = date.fromisoformat(
            event["fecha"]
        )

        sessions = schedules.get(
            (
                category,
                round_number,
                event["fecha"],
            ),
            [],
        )

        # ----------------------------------------------------
        # Si no hay horarios:
        # evento de día completo.
        # ----------------------------------------------------

        if not sessions:

            uid = make_uid(
                category,
                round_number,
                event_date,
                None,
                "carrera",
            )

            description = (
                f"{event['campeonato']} - "
                f"Fecha {round_number}"
            )

            output.append({
                "uid": uid,
                "categoria": "Argentina",
                "campeonato": event["campeonato"],
                "tipo": "Carrera",
                "fecha_inicio": event["fecha"],
                "fecha_fin": event["fecha"],
                "ubicacion": event["ubicacion"],
                "descripcion": description,
                "imperdible": True,
                "fuente": event["fuente"],
                "round": round_number,
            })

            continue

        # ----------------------------------------------------
        # Con horarios reales
        # ----------------------------------------------------

        for session_data in sessions:

            start = session_data["inicio"]
            end = session_data["fin"]
            name = session_data["nombre"]

            uid = make_uid(
                category,
                round_number,
                event_date,
                datetime.strptime(
                    start,
                    "%H:%M",
                ).time(),
                name,
            )

            normalized_name = normalize(name)

            if (
                "final" in normalized_name
                or "carrera" in normalized_name
                or "serie" in normalized_name
            ):
                tipo = "Carrera"
            elif (
                "clasif" in normalized_name
            ):
                tipo = "Clasificación"
            elif (
                "entrenamiento" in normalized_name
                or "practica" in normalized_name
            ):
                tipo = "Práctica"
            else:
                tipo = "Sesión"

            imperdible = (
                tipo == "Carrera"
                or "final" in normalized_name
            )

            description = (
                f"{event['campeonato']} - "
                f"Fecha {round_number}"
            )

            output.append({
                "uid": uid,
                "categoria": "Argentina",
                "campeonato": event["campeonato"],
                "tipo": tipo,
                "fecha_inicio": (
                    f"{event['fecha']}T{start}:00"
                ),
                "fecha_fin": (
                    f"{event['fecha']}T{end}:00"
                ),
                "ubicacion": event["ubicacion"],
                "descripcion": description,
                "imperdible": imperdible,
                "fuente": event["fuente"],
                "round": round_number,
            })

    return output


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():

    print("=" * 70)
    print("ACTC - CALENDARIO AUTOMÁTICO")
    print(f"Año detectado: {YEAR}")
    print("=" * 70)

    session = requests_session()

    all_calendar_events = []

    # --------------------------------------------------------
    # CALENDARIOS
    # --------------------------------------------------------

    for category in CATEGORIES:

        try:
            events = get_calendar(
                category,
                session,
            )

            all_calendar_events.extend(events)

        except Exception as exc:
            print(
                f"[{category}] ERROR calendario: {exc}"
            )

    # --------------------------------------------------------
    # DEDUPLICAR CALENDARIO
    # --------------------------------------------------------

    unique_calendar = {}

    for event in all_calendar_events:

        key = (
            event["categoria"],
            event["round"],
            event["fecha"],
        )

        unique_calendar[key] = event

    all_calendar_events = list(
        unique_calendar.values()
    )

    all_calendar_events.sort(
        key=lambda x: (
            x["fecha"],
            x["categoria"],
            x["round"],
        )
    )

    print(
        f"\nFechas ACTC totales: "
        f"{len(all_calendar_events)}"
    )

    # --------------------------------------------------------
    # PLAYWRIGHT
    # --------------------------------------------------------

    schedules = {}

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True
        )

        try:

            for event in all_calendar_events:

                # ------------------------------------------------
                # No perder tiempo con carreras viejas:
                # los horarios de las fechas pasadas no son
                # necesarios para el calendario futuro.
                #
                # PERO dejamos posibilidad de recuperarlos si
                # ya están publicados.
                # ------------------------------------------------

                category = event["categoria"]

                print(
                    "\n"
                    f"[{category}] "
                    f"Fecha {event['round']} - "
                    f"{event['fecha']} - "
                    f"{event['ubicacion']}"
                )

                sessions_found, source = find_schedule(
                    browser,
                    session,
                    category,
                    event,
                )

                if sessions_found:

                    schedules[
                        (
                            category,
                            event["round"],
                            event["fecha"],
                        )
                    ] = sessions_found

                    event["horarios_url"] = source

                    print(
                        f"  Sesiones encontradas: "
                        f"{len(sessions_found)}"
                    )

                else:

                    print(
                        "  Horarios todavía no "
                        "encontrados."
                    )

        finally:
            browser.close()

    # --------------------------------------------------------
    # CONSTRUIR JSON
    # --------------------------------------------------------

    final_events = build_events(
        all_calendar_events,
        schedules,
    )

    # --------------------------------------------------------
    # DEDUPLICAR EVENTOS FINALES
    # --------------------------------------------------------

    unique_final = {}

    for event in final_events:

        uid = event["uid"]

        unique_final[uid] = event

    final_events = list(
        unique_final.values()
    )

    final_events.sort(
        key=lambda x: (
            x["fecha_inicio"],
            x["campeonato"],
            x["tipo"],
            x["uid"],
        )
    )

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT.write_text(
        json.dumps(
            final_events,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # RESUMEN
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("RESUMEN ACTC")
    print("=" * 70)

    for category in CATEGORIES:

        calendar_count = sum(
            1
            for x in all_calendar_events
            if x["categoria"] == category
        )

        session_count = sum(
            len(
                schedules.get(
                    (
                        category,
                        x["round"],
                        x["fecha"],
                    ),
                    [],
                )
            )
            for x in all_calendar_events
            if x["categoria"] == category
        )

        print(
            f"{category}: "
            f"{calendar_count} fechas, "
            f"{session_count} sesiones"
        )

    print(
        f"\nEventos escritos: "
        f"{len(final_events)}"
    )

    print(
        f"Archivo: {OUTPUT}"
    )


if __name__ == "__main__":
    main()
