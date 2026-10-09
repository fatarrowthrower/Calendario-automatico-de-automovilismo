import json
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright


YEAR = datetime.now().year
BASE_URL = "https://actc.org.ar"
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


MONTHS = {
    "ene": 1,
    "enero": 1,
    "feb": 2,
    "febrero": 2,
    "mar": 3,
    "marzo": 3,
    "abr": 4,
    "abril": 4,
    "may": 5,
    "mayo": 5,
    "jun": 6,
    "junio": 6,
    "jul": 7,
    "julio": 7,
    "ago": 8,
    "agosto": 8,
    "sep": 9,
    "sept": 9,
    "septiembre": 9,
    "setiembre": 9,
    "oct": 10,
    "octubre": 10,
    "nov": 11,
    "noviembre": 11,
    "dic": 12,
    "diciembre": 12,
}


def clean(text):
    if not text:
        return ""

    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def normalize(text):
    text = clean(text).lower()

    text = unicodedata.normalize(
        "NFD",
        text,
    )

    text = "".join(
        c
        for c in text
        if unicodedata.category(c) != "Mn"
    )

    return text


def parse_actc_date(text):
    """
    ACTC actualmente muestra fechas así:

    dom, 25 oct 2026
    dom, 08 mar 2026
    """

    text = normalize(text)

    match = re.search(
        r"\b"
        r"(?:lun|mar|mie|jue|vie|sab|dom)"
        r",?\s+"
        r"(\d{1,2})\s+"
        r"([a-z]+)\s+"
        r"(\d{4})"
        r"\b",
        text,
    )

    if not match:
        return None

    day = int(match.group(1))
    month_name = match.group(2)
    year = int(match.group(3))

    month = MONTHS.get(month_name)

    if not month:
        return None

    try:
        from datetime import date

        return date(
            year,
            month,
            day,
        )

    except ValueError:
        return None


def extract_round(text):
    match = re.search(
        r"\bFecha\s+(\d+)\b",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None

    return int(match.group(1))


def extract_calendar_events(body_text, category, source_url):
    """
    Parser basado en el texto visible de la página.

    No depende de:
      - clases CSS
      - tarjetas
      - estructura HTML
      - selectores text=/.../

    Esto permite que ACTC cambie el diseño sin romper
    automáticamente el descubrimiento de fechas.
    """

    text = clean(body_text)

    # --------------------------------------------------------
    # Cada carrera comienza con "Fecha N"
    # --------------------------------------------------------

    matches = list(
        re.finditer(
            r"(?im)^\s*Fecha\s+(\d+)\b",
            text,
        )
    )

    events = []

    for index, match in enumerate(matches):

        round_number = int(match.group(1))

        start = match.start()

        if index + 1 < len(matches):
            end = matches[index + 1].start()
        else:
            end = len(text)

        block = clean(
            text[start:end]
        )

        # No dejar que un bloque gigante arrastre
        # contenido de navegación.
        if len(block) > 2500:
            block = block[:2500]

        event_date = parse_actc_date(block)

        if not event_date:
            continue

        if event_date.year != YEAR:
            continue

        # ----------------------------------------------------
        # Primera línea:
        #
        # Fecha 13 — ROSARIO
        # ----------------------------------------------------

        first_line = block.splitlines()[0]

        first_line = clean(
            first_line
        )

        location = ""

        location_match = re.search(
            r"Fecha\s+\d+\s*[—–-]\s*(.+)",
            first_line,
            re.IGNORECASE,
        )

        if location_match:
            location = clean(
                location_match.group(1)
            )

        # ----------------------------------------------------
        # Línea del autódromo:
        #
        # Juan Manuel Fangio-ROSARIO —
        # Rosario, Santa Fe
        # ----------------------------------------------------

        circuit = ""

        lines = [
            clean(x)
            for x in block.splitlines()
            if clean(x)
        ]

        for line in lines:

            if (
                " — " in line
                and not line.lower().startswith("fecha")
            ):
                candidate = clean(
                    line.split(" — ")[0]
                )

                if (
                    len(candidate) > 3
                    and len(candidate) < 150
                    and "dom," not in normalize(candidate)
                ):
                    circuit = candidate
                    break

        # ----------------------------------------------------
        # A CONFIRMAR
        # ----------------------------------------------------

        normalized_block = normalize(block)

        if "a confirmar" in normalized_block:
            location = "A confirmar"
            circuit = "A confirmar"

        events.append({
            "categoria": category,
            "campeonato": CATEGORIES[category]["name"],
            "round": round_number,
            "fecha": event_date.isoformat(),
            "ubicacion": location,
            "circuito": circuit,
            "fuente": source_url,
            "horarios_url": None,
        })

    # --------------------------------------------------------
    # Deduplicar
    # --------------------------------------------------------

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

    return events


def get_calendar(page, category):
    slug = CATEGORIES[category]["slug"]

    url = (
        f"{BASE_URL}/{slug}/calendario"
    )

    print()
    print(
        f"[{category}] Calendario:"
    )
    print(url)

    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=60000,
    )

    # ACTC puede terminar de cargar contenido
    # después del DOM inicial.
    page.wait_for_timeout(5000)

    # --------------------------------------------------------
    # Forzar carga de todo el documento.
    # --------------------------------------------------------

    try:
        page.evaluate(
            """
            window.scrollTo(
                0,
                document.body.scrollHeight
            );
            """
        )

        page.wait_for_timeout(2000)

        page.evaluate(
            """
            window.scrollTo(0, 0);
            """
        )

        page.wait_for_timeout(1000)

    except Exception:
        pass

    # --------------------------------------------------------
    # ESTA ES LA DIFERENCIA IMPORTANTE:
    #
    # No buscamos elementos "Fecha N".
    # Leemos el texto completo que ve Chromium.
    # --------------------------------------------------------

    body_text = page.locator(
        "body"
    ).inner_text()

    body_text = clean(body_text)

    events = extract_calendar_events(
        body_text,
        category,
        url,
    )

    print(
        f"[{category}] Fechas encontradas: "
        f"{len(events)}"
    )

    for event in events:

        print(
            f"  Fecha {event['round']}: "
            f"{event['fecha']} - "
            f"{event['ubicacion']} - "
            f"{event['circuito']}"
        )

    return events


def discover_result_links(page):
    """
    Obtiene los enlaces "Ver resultados" del calendario.

    Los IDs de esos enlaces cambian cada año,
    por eso jamás los hardcodeamos.
    """

    result = []

    try:

        anchors = page.locator(
            "a"
        )

        count = anchors.count()

        for i in range(count):

            try:

                anchor = anchors.nth(i)

                text = clean(
                    anchor.inner_text()
                )

                href = anchor.get_attribute(
                    "href"
                )

            except Exception:
                continue

            if not href:
                continue

            if "resultado" not in normalize(
                text
            ):
                continue

            result.append(
                urljoin(
                    BASE_URL,
                    href,
                )
            )

    except Exception:
        pass

    # Deduplicar.
    unique = []

    for url in result:

        if url not in unique:
            unique.append(url)

    return unique


def find_schedule_links(page):
    """
    Busca enlaces dinámicos a cronogramas.

    ACTC ha utilizado:
      /cronogramas/<id>
      /carrera-online/.../cronograma/...

    No se hardcodea ningún ID.
    """

    result = []

    try:

        anchors = page.locator(
            "a"
        )

        count = anchors.count()

        for i in range(count):

            try:

                anchor = anchors.nth(i)

                href = anchor.get_attribute(
                    "href"
                )

                text = clean(
                    anchor.inner_text()
                )

            except Exception:
                continue

            if not href:
                continue

            full = urljoin(
                BASE_URL,
                href,
            )

            normalized = normalize(
                f"{text} {full}"
            )

            if (
                "/cronogramas/" in full
                or "/cronograma/" in full
                or "cronograma" in normalized
            ):
                if full not in result:
                    result.append(full)

    except Exception:
        pass

    return result


def parse_time(text):
    match = re.search(
        r"\b(\d{1,2}):(\d{2})\b",
        text,
    )

    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))

    if hour > 23 or minute > 59:
        return None

    return (
        f"{hour:02d}:{minute:02d}"
    )


def parse_time_pair(text):
    times = re.findall(
        r"\b(\d{1,2}:\d{2})\b",
        text,
    )

    if not times:
        return None, None

    start = times[0]

    if len(times) >= 2:
        end = times[1]
    else:
        end = None

    return start, end


def clean_session_name(text):
    text = re.sub(
        r"\b\d{1,2}:\d{2}\b",
        "",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    text = re.sub(
        r"^[\s|•\-–—:]+",
        "",
        text,
    )

    text = re.sub(
        r"[\s|•\-–—:]+$",
        "",
        text,
    )

    return clean(text)


def parse_schedule_text(
    body_text,
    category,
):
    """
    Intenta extraer sesiones de un cronograma
    visible.

    Importante:
    si no encuentra sesiones, devuelve [].
    Nunca inventa 12:00.
    """

    text = clean(body_text)

    lines = [
        clean(line)
        for line in text.splitlines()
        if clean(line)
    ]

    sessions = []

    # Palabras que indican una actividad de pista.
    activity_words = [
        "entrenamiento",
        "practica",
        "práctica",
        "clasificacion",
        "clasificación",
        "serie",
        "carrera",
        "final",
        "warm up",
        "warm-up",
        "tanque lleno",
        "clasificatorio",
    ]

    for index, line in enumerate(lines):

        normalized = normalize(line)

        if not any(
            word in normalized
            for word in activity_words
        ):
            continue

        start, end = parse_time_pair(
            line
        )

        # Si la hora está en una línea anterior,
        # probar combinación con esa línea.
        if not start and index > 0:

            previous = lines[index - 1]

            previous_start, previous_end = (
                parse_time_pair(previous)
            )

            if previous_start:
                start = previous_start
                end = previous_end

        if not start:
            continue

        name = clean_session_name(
            line
        )

        if not name:
            continue

        # Evitar textos que no sean sesiones.
        forbidden = [
            "horario de tv",
            "transmision",
            "transmisión",
            "live",
            "streaming",
            "youtube",
        ]

        if any(
            x in normalize(name)
            for x in forbidden
        ):
            continue

        sessions.append({
            "inicio": start,
            "fin": end,
            "nombre": name,
        })

    # --------------------------------------------------------
    # Deduplicar
    # --------------------------------------------------------

    unique = {}

    for session in sessions:

        key = (
            session["inicio"],
            session["fin"],
            normalize(session["nombre"]),
        )

        unique[key] = session

    return list(unique.values())


def discover_schedule(
    browser,
    category,
    event,
):
    """
    Busca el cronograma dinámicamente.

    Estrategia:

    1. abrir calendario
    2. buscar enlace de resultados correspondiente
    3. abrir resultados
    4. buscar cronograma
    5. abrir cronograma
    6. extraer sesiones
    """

    slug = CATEGORIES[category]["slug"]

    calendar_url = (
        f"{BASE_URL}/{slug}/calendario"
    )

    page = browser.new_page(
        viewport={
            "width": 1440,
            "height": 1200,
        }
    )

    try:

        page.goto(
            calendar_url,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        page.wait_for_timeout(4000)

        print("\n--- DIAGNÓSTICO ACTC ---")
print("URL:", page.url)
print("TÍTULO:", page.title())
print("ENLACES DE LA PÁGINA:")

for link in page.locator("a").all():
    try:
        href = link.get_attribute("href")
        text = link.inner_text().strip()

        if href:
            print(f"{text[:100]} | {href}")
    except Exception:
        pass

print("--- FIN DIAGNÓSTICO ---\n")

        # ----------------------------------------------------
        # Buscar el bloque de la fecha.
        # ----------------------------------------------------

        target_round = event["round"]

        # Primero buscamos los enlaces de resultados.
        result_links = (
            discover_result_links(page)
        )

        # ACTC suele ordenar los resultados igual
        # que las fechas. Para robustez, también
        # buscamos por href/texto en el bloque.
        candidate_links = []

        anchors = page.locator(
            "a"
        )

        count = anchors.count()

        for i in range(count):

            try:

                anchor = anchors.nth(i)

                text = clean(
                    anchor.inner_text()
                )

                href = anchor.get_attribute(
                    "href"
                )

            except Exception:
                continue

            if not href:
                continue

            full = urljoin(
                BASE_URL,
                href,
            )

            if (
                "resultado" in normalize(text)
                or "/resultados" in full
                or "/resultado" in full
            ):
                candidate_links.append(
                    full
                )

        # Deduplicar.
        all_links = []

        for url in (
            candidate_links
            + result_links
        ):
            if url not in all_links:
                all_links.append(url)

        # ----------------------------------------------------
        # La fecha N normalmente corresponde al N-1
        # de los enlaces de resultados.
        # ----------------------------------------------------

        preferred = []

        index = target_round - 1

        if (
            index >= 0
            and index < len(all_links)
        ):
            preferred.append(
                all_links[index]
            )

        for url in all_links:
            if url not in preferred:
                preferred.append(url)

        # ----------------------------------------------------
        # Probar resultados.
        # ----------------------------------------------------

        for result_url in preferred:

            result_page = browser.new_page(
                viewport={
                    "width": 1440,
                    "height": 1200,
                }
            )

            try:

                result_page.goto(
                    result_url,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )

                result_page.wait_for_timeout(
                    3500
                )

                schedule_links = (
                    find_schedule_links(
                        result_page
                    )
                )

                # ------------------------------------------------
                # Si hay enlace explícito.
                # ------------------------------------------------

                for schedule_url in schedule_links:

                    schedule_page = (
                        browser.new_page(
                            viewport={
                                "width": 1440,
                                "height": 1200,
                            }
                        )
                    )

                    try:

                        schedule_page.goto(
                            schedule_url,
                            wait_until="domcontentloaded",
                            timeout=60000,
                        )

                        schedule_page.wait_for_timeout(
                            4000
                        )

                        body = clean(
                            schedule_page.locator(
                                "body"
                            ).inner_text()
                        )

                        sessions = (
                            parse_schedule_text(
                                body,
                                category,
                            )
                        )

                        if sessions:

                            print(
                                f"    Cronograma: "
                                f"{schedule_url}"
                            )

                            return (
                                sessions,
                                schedule_url,
                            )

                    except Exception as exc:

                        print(
                            "    Error leyendo "
                            f"cronograma: {exc}"
                        )

                    finally:

                        try:
                            schedule_page.close()
                        except Exception:
                            pass

                # ------------------------------------------------
                # A veces el propio resultado contiene
                # texto del cronograma.
                # ------------------------------------------------

                body = clean(
                    result_page.locator(
                        "body"
                    ).inner_text()
                )

                sessions = (
                    parse_schedule_text(
                        body,
                        category,
                    )
                )

                if sessions:

                    return (
                        sessions,
                        result_url,
                    )

            except Exception as exc:

                print(
                    f"    Error resultados: "
                    f"{exc}"
                )

            finally:

                try:
                    result_page.close()
                except Exception:
                    pass

        return [], None

    finally:

        try:
            page.close()
        except Exception:
            pass


def make_uid(
    category,
    round_number,
    event_date,
    start,
    name,
):
    if start:
        start_part = start.replace(
            ":",
            "",
        )
    else:
        start_part = "all-day"

    safe_name = re.sub(
        r"[^a-zA-Z0-9]+",
        "-",
        normalize(name),
    ).strip("-")

    return (
        f"actc-{category.lower()}-"
        f"{YEAR}-{round_number}-"
        f"{event_date}-"
        f"{start_part}-"
        f"{safe_name}"
    )


def classify_session(name):
    normalized = normalize(name)

    if (
        "clasificacion" in normalized
        or "clasificatoria" in normalized
    ):
        return "Clasificación"

    if (
        "entrenamiento" in normalized
        or "practica" in normalized
    ):
        return "Práctica"

    if (
        "serie" in normalized
        or "carrera" in normalized
        or "final" in normalized
    ):
        return "Carrera"

    return "Sesión"


def build_events(
    calendar_events,
    schedules,
):
    result = []

    for event in calendar_events:

        key = (
            event["categoria"],
            event["round"],
            event["fecha"],
        )

        sessions = schedules.get(
            key,
            [],
        )

        # ----------------------------------------------------
        # Si ACTC todavía no publicó horarios:
        #
        # conservar la carrera como evento de día completo.
        # ----------------------------------------------------

        if not sessions:

            uid = make_uid(
                event["categoria"],
                event["round"],
                event["fecha"],
                None,
                "carrera",
            )

            result.append({
                "uid": uid,
                "categoria": "Argentina",
                "campeonato": event["campeonato"],
                "tipo": "Carrera",
                "fecha_inicio": event["fecha"],
                "fecha_fin": event["fecha"],
                "ubicacion": event["ubicacion"],
                "descripcion": (
                    f"{event['campeonato']} - "
                    f"Fecha {event['round']}"
                ),
                "imperdible": True,
                "fuente": event["fuente"],
                "round": event["round"],
            })

            continue

        # ----------------------------------------------------
        # Horarios reales.
        # ----------------------------------------------------

        for session in sessions:

            start = session["inicio"]
            end = session["fin"]
            name = session["nombre"]

            tipo = classify_session(
                name
            )

            # Si ACTC solo publicó hora inicial,
            # no inventamos una duración.
            #
            # En ese caso dejamos 1 minuto como
            # duración técnica para que el evento
            # sea válido en el ICS.
            if not end:

                try:

                    start_dt = datetime.strptime(
                        start,
                        "%H:%M",
                    )

                    end_dt = (
                        start_dt
                        + timedelta(
                            minutes=1
                        )
                    )

                    end = end_dt.strftime(
                        "%H:%M"
                    )

                except Exception:

                    end = start

            uid = make_uid(
                event["categoria"],
                event["round"],
                event["fecha"],
                start,
                name,
            )

            result.append({
                "uid": uid,
                "categoria": "Argentina",
                "campeonato": event["campeonato"],
                "tipo": tipo,
                "fecha_inicio": (
                    f"{event['fecha']}T"
                    f"{start}:00"
                ),
                "fecha_fin": (
                    f"{event['fecha']}T"
                    f"{end}:00"
                ),
                "ubicacion": event["ubicacion"],
                "descripcion": (
                    f"{event['campeonato']} - "
                    f"Fecha {event['round']}"
                ),
                "imperdible": (
                    tipo == "Carrera"
                ),
                "fuente": event["fuente"],
                "round": event["round"],
            })

    return result


def main():

    print("=" * 70)
    print("ACTC - CALENDARIO AUTOMÁTICO")
    print(f"Año detectado: {YEAR}")
    print("=" * 70)

    calendar_events = []

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True,
        )

        try:

            # ====================================================
            # 1. CALENDARIOS
            # ====================================================

            for category in CATEGORIES:

                page = browser.new_page(
                    viewport={
                        "width": 1440,
                        "height": 1200,
                    }
                )

                try:

                    events = get_calendar(
                        page,
                        category,
                    )

                    calendar_events.extend(
                        events
                    )

                except Exception as exc:

                    print(
                        f"[{category}] ERROR: "
                        f"{exc}"
                    )

                finally:

                    try:
                        page.close()
                    except Exception:
                        pass

            # ====================================================
            # 2. DEDUPLICAR FECHAS
            # ====================================================

            unique = {}

            for event in calendar_events:

                key = (
                    event["categoria"],
                    event["round"],
                    event["fecha"],
                )

                unique[key] = event

            calendar_events = list(
                unique.values()
            )

            calendar_events.sort(
                key=lambda x: (
                    x["fecha"],
                    x["categoria"],
                    x["round"],
                )
            )

            print()
            print(
                f"Fechas ACTC totales: "
                f"{len(calendar_events)}"
            )

            # ====================================================
            # 3. HORARIOS
            # ====================================================

            schedules = {}

            for event in calendar_events:

                print()
                print(
                    f"[{event['categoria']}] "
                    f"Fecha {event['round']} - "
                    f"{event['fecha']} - "
                    f"{event['ubicacion']}"
                )

                sessions, source = (
                    discover_schedule(
                        browser,
                        event["categoria"],
                        event,
                    )
                )

                if sessions:

                    key = (
                        event["categoria"],
                        event["round"],
                        event["fecha"],
                    )

                    schedules[key] = sessions

                    event["horarios_url"] = source

                    print(
                        f"  Sesiones encontradas: "
                        f"{len(sessions)}"
                    )

                else:

                    print(
                        "  Sin horarios publicados."
                    )

        finally:

            browser.close()

    # ========================================================
    # 4. GENERAR EVENTOS
    # ========================================================

    events = build_events(
        calendar_events,
        schedules,
    )

    # ========================================================
    # 5. DEDUPLICAR UID
    # ========================================================

    unique = {}

    for event in events:
        unique[event["uid"]] = event

    events = list(
        unique.values()
    )

    events.sort(
        key=lambda x: (
            x["fecha_inicio"],
            x["campeonato"],
            x["tipo"],
        )
    )

    # ========================================================
    # 6. ESCRIBIR JSON
    # ========================================================

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT.write_text(
        json.dumps(
            events,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # ========================================================
    # 7. RESUMEN
    # ========================================================

    print()
    print("=" * 70)
    print("RESUMEN ACTC")
    print("=" * 70)

    for category in CATEGORIES:

        dates = sum(
            1
            for event in calendar_events
            if event["categoria"] == category
        )

        sessions = sum(
            len(
                schedules.get(
                    (
                        category,
                        event["round"],
                        event["fecha"],
                    ),
                    [],
                )
            )
            for event in calendar_events
            if event["categoria"] == category
        )

        print(
            f"{category}: "
            f"{dates} fechas, "
            f"{sessions} sesiones"
        )

    print()
    print(
        f"Eventos escritos: {len(events)}"
    )

    print(
        f"Archivo: {OUTPUT}"
    )


if __name__ == "__main__":
    main()
