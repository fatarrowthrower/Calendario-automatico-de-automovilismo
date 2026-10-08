import json
import re
from datetime import datetime, date
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


def clean(text):
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize(text):
    text = clean(text).lower()

    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
        "ñ": "n",
    }

    for a, b in replacements.items():
        text = text.replace(a, b)

    return text


def parse_date(text):
    text = clean(text)

    # 25/10/2026
    match = re.search(
        r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b",
        text,
    )

    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))

        if year < 100:
            year += 2000

        try:
            return date(year, month, day)
        except ValueError:
            pass

    # 25 de octubre de 2026
    match = re.search(
        r"\b(\d{1,2})\s+de\s+"
        r"(enero|febrero|marzo|abril|mayo|junio|julio|agosto|"
        r"septiembre|setiembre|octubre|noviembre|diciembre)"
        r"\s+(?:de\s+)?(\d{4})\b",
        normalize(text),
    )

    if match:
        day = int(match.group(1))
        month = MONTHS[match.group(2)]
        year = int(match.group(3))

        try:
            return date(year, month, day)
        except ValueError:
            pass

    return None


def parse_date_from_block(text):
    """
    ACTC actualmente muestra muchos calendarios
    con bloques donde aparecen día/mes/año por separado.

    Probamos varias formas.
    """

    text = clean(text)

    # Primero formato completo.
    result = parse_date(text)

    if result:
        return result

    # Buscar cualquier fecha 2026 cercana.
    match = re.search(
        r"\b(\d{1,2})\s*[/.-]\s*(\d{1,2})"
        r"(?:\s*[/.-]\s*(\d{4}))?\b",
        text,
    )

    if match:
        day = int(match.group(1))
        month = int(match.group(2))

        year = (
            int(match.group(3))
            if match.group(3)
            else YEAR
        )

        try:
            return date(year, month, day)
        except ValueError:
            pass

    return None


def is_confirmed(block):
    n = normalize(block)

    forbidden = [
        "a confirmar",
        "por confirmar",
        "fecha a confirmar",
        "lugar a confirmar",
    ]

    return not any(x in n for x in forbidden)


def extract_location(block):
    """
    Intenta sacar el nombre del circuito/ciudad
    sin depender de una posición fija.
    """

    text = clean(block)

    # Sacamos basura habitual.
    text = re.sub(
        r"Fecha\s+\d+",
        "",
        text,
        flags=re.I,
    )

    text = re.sub(
        r"Ver resultados",
        "",
        text,
        flags=re.I,
    )

    text = clean(text)

    # Buscamos lugares conocidos por patrones.
    # Si no encontramos nada, devolvemos el bloque
    # reducido, nunca un dato inventado.
    for separator in [
        " - ",
        " — ",
        " | ",
        "–",
        "—",
    ]:
        parts = [
            clean(x)
            for x in text.split(separator)
            if clean(x)
        ]

        if len(parts) >= 2:
            candidate = parts[-1]

            if len(candidate) <= 100:
                return candidate

    return ""


def extract_round(text):
    match = re.search(
        r"Fecha\s+(\d+)",
        text,
        re.I,
    )

    if match:
        return int(match.group(1))

    return None


def find_calendar_blocks(page):
    """
    Esta es la parte importante.

    NO buscamos los datos con requests.

    Dejamos que Chromium ejecute ACTC y después
    analizamos el DOM que realmente ve el navegador.
    """

    blocks = []

    # --------------------------------------------------------
    # 1. Elementos que contienen "Fecha N"
    # --------------------------------------------------------

    locators = page.locator(
        "text=/Fecha\\s+[0-9]+/i"
    )

    count = locators.count()

    for i in range(count):

        try:
            element = locators.nth(i)

            text = clean(
                element.evaluate(
                    """
                    el => {
                        let node = el;

                        for (let i = 0; i < 6; i++) {
                            if (!node) break;

                            const t =
                                node.innerText ||
                                node.textContent ||
                                "";

                            if (
                                /Fecha\\s+[0-9]+/i.test(t) &&
                                t.length >= 20 &&
                                t.length <= 1000
                            ) {
                                return t;
                            }

                            node = node.parentElement;
                        }

                        return (
                            el.innerText ||
                            el.textContent ||
                            ""
                        );
                    }
                    """
                )
            )

        except Exception:
            continue

        if text:
            blocks.append(text)

    # --------------------------------------------------------
    # 2. Si no encontramos nada así, recorrer tarjetas
    # --------------------------------------------------------

    if not blocks:

        selectors = [
            ".card",
            ".item",
            ".evento",
            ".event",
            "article",
            "li",
            "tr",
        ]

        for selector in selectors:

            try:
                items = page.locator(selector)

                count = min(
                    items.count(),
                    500,
                )

            except Exception:
                continue

            for i in range(count):

                try:
                    text = clean(
                        items.nth(i).inner_text()
                    )
                except Exception:
                    continue

                if not text:
                    continue

                if not re.search(
                    r"Fecha\s+\d+",
                    text,
                    re.I,
                ):
                    continue

                if not parse_date_from_block(text):
                    continue

                if len(text) > 1200:
                    continue

                blocks.append(text)

            if blocks:
                break

    # --------------------------------------------------------
    # Deduplicar
    # --------------------------------------------------------

    result = []
    seen = set()

    for block in blocks:

        key = normalize(block)

        if key in seen:
            continue

        seen.add(key)
        result.append(block)

    return result


def get_calendar(page, category):
    slug = CATEGORIES[category]["slug"]

    url = f"{BASE_URL}/{slug}/calendario"

    print()
    print(f"[{category}] Calendario:")
    print(url)

    page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=60000,
    )

    # ACTC carga contenido dinámicamente.
    page.wait_for_timeout(5000)

    # Scroll para forzar carga de elementos.
    page.evaluate(
        """
        async () => {
            window.scrollTo(0, document.body.scrollHeight);
            await new Promise(
                r => setTimeout(r, 2000)
            );
            window.scrollTo(0, 0);
        }
        """
    )

    page.wait_for_timeout(2000)

    blocks = find_calendar_blocks(page)

    events = []

    for block in blocks:

        round_number = extract_round(block)

        if round_number is None:
            continue

        event_date = parse_date_from_block(block)

        if not event_date:
            continue

        if event_date.year != YEAR:
            continue

        # No inventamos una fecha/lugar confirmado.
        confirmed = is_confirmed(block)

        location = extract_location(block)

        if not confirmed:
            location = "A confirmar"

        events.append({
            "categoria": category,
            "campeonato": CATEGORIES[category]["name"],
            "round": round_number,
            "fecha": event_date.isoformat(),
            "ubicacion": location,
            "circuito": location,
            "fuente": url,
            "horarios_url": None,
            "confirmado": confirmed,
        })

    # Deduplicar por fecha/fecha de campeonato.
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
        f"[{category}] Fechas encontradas: "
        f"{len(events)}"
    )

    for event in events:
        print(
            f"  Fecha {event['round']}: "
            f"{event['fecha']} - "
            f"{event['ubicacion']}"
        )

    return events


def find_cronograma_url(page):
    """
    Busca dinámicamente enlaces ACTC que apunten
    a /cronogramas/... o /carrera-online/...
    """

    urls = []

    try:
        anchors = page.locator("a")

        count = anchors.count()

        for i in range(count):

            try:
                href = anchors.nth(i).get_attribute(
                    "href"
                )

                text = clean(
                    anchors.nth(i).inner_text()
                )

            except Exception:
                continue

            if not href:
                continue

            full = urljoin(
                BASE_URL,
                href,
            )

            n = normalize(
                f"{text} {full}"
            )

            if (
                "/cronogramas/" in full
                or "/carrera-online/" in full
                or "cronograma" in n
            ):
                if full not in urls:
                    urls.append(full)

    except Exception:
        pass

    return urls


def extract_times_from_page(
    page,
    category,
):
    """
    Intenta extraer horarios visibles del
    cronograma ya renderizado.

    No fabrica sesiones.
    """

    text = clean(
        page.locator("body").inner_text()
    )

    lines = [
        clean(x)
        for x in text.splitlines()
        if clean(x)
    ]

    sessions = []

    time_pattern = re.compile(
        r"\b(\d{1,2}:\d{2})\b"
    )

    for i, line in enumerate(lines):

        matches = time_pattern.findall(line)

        if not matches:
            continue

        normalized = normalize(line)

        # Evitar fechas/horarios que no sean sesiones.
        forbidden = [
            "contacto",
            "telefono",
            "copyright",
            "whatsapp",
        ]

        if any(x in normalized for x in forbidden):
            continue

        # ----------------------------------------------------
        # Una hora.
        # ----------------------------------------------------

        if len(matches) == 1:

            start = matches[0]

            name = time_pattern.sub(
                "",
                line,
            )

            name = clean(name)

            if not name:
                # Mirar línea siguiente.
                if i + 1 < len(lines):
                    name = lines[i + 1]

            if not name:
                continue

            sessions.append({
                "inicio": start,
                "fin": None,
                "nombre": name,
            })

        # ----------------------------------------------------
        # Dos o más horas.
        # ----------------------------------------------------

        else:

            start = matches[0]
            end = matches[1]

            name = time_pattern.sub(
                "",
                line,
            )

            name = clean(name)

            if not name:
                name = "Sesión"

            sessions.append({
                "inicio": start,
                "fin": end,
                "nombre": name,
            })

    # --------------------------------------------------------
    # Limpiar nombres.
    # --------------------------------------------------------

    result = []

    seen = set()

    for session in sessions:

        name = clean(
            session["nombre"]
        )

        if not name:
            continue

        key = (
            session["inicio"],
            session["fin"],
            normalize(name),
        )

        if key in seen:
            continue

        seen.add(key)

        result.append({
            "inicio": session["inicio"],
            "fin": session["fin"],
            "nombre": name,
        })

    return result


def discover_schedule_for_event(
    browser,
    category,
    event,
):
    """
    Busca el cronograma sin hardcodear IDs.

    Primero entra al calendario.
    Después busca enlaces reales que ACTC haya generado.
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

        page.wait_for_timeout(5000)

        # ----------------------------------------------------
        # Intentar hacer click en la Fecha correspondiente.
        # ----------------------------------------------------

        round_number = event["round"]

        clicked = False

        candidates = page.locator(
            f"text=Fecha {round_number}"
        )

        count = candidates.count()

        for i in range(count):

            try:
                candidates.nth(i).click(
                    timeout=3000
                )

                clicked = True

                page.wait_for_timeout(3000)

                break

            except Exception:
                continue

        # ----------------------------------------------------
        # Buscar enlaces.
        # ----------------------------------------------------

        urls = find_cronograma_url(page)

        # ----------------------------------------------------
        # Si encontramos URLs, probarlas.
        # ----------------------------------------------------

        for url in urls:

            schedule_page = browser.new_page(
                viewport={
                    "width": 1440,
                    "height": 1200,
                }
            )

            try:

                schedule_page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )

                schedule_page.wait_for_timeout(
                    5000
                )

                sessions = extract_times_from_page(
                    schedule_page,
                    category,
                )

                if sessions:

                    print(
                        f"    Cronograma: {url}"
                    )

                    print(
                        f"    Sesiones: "
                        f"{len(sessions)}"
                    )

                    return sessions, url

            except Exception as exc:

                print(
                    f"    Error cronograma "
                    f"{url}: {exc}"
                )

            finally:

                try:
                    schedule_page.close()
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
    start_part = (
        start.replace(":", "")
        if start
        else "all-day"
    )

    safe_name = re.sub(
        r"[^a-zA-Z0-9]+",
        "-",
        normalize(name),
    ).strip("-")

    return (
        f"actc-{category.lower()}-"
        f"{YEAR}-{round_number}-"
        f"{event_date}-{start_part}-"
        f"{safe_name}"
    )


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
        # SIN HORARIOS
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
        # CON HORARIOS
        # ----------------------------------------------------

        for session in sessions:

            start = session["inicio"]
            end = session["fin"]

            if not end:
                end = start

            name = session["nombre"]

            normalized = normalize(name)

            if (
                "clasif" in normalized
            ):
                tipo = "Clasificación"

            elif (
                "entrenamiento" in normalized
                or "practica" in normalized
            ):
                tipo = "Práctica"

            elif (
                "serie" in normalized
                or "carrera" in normalized
                or "final" in normalized
            ):
                tipo = "Carrera"

            else:
                tipo = "Sesión"

            imperdible = (
                tipo == "Carrera"
            )

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
                    f"{event['fecha']}T{start}:00"
                ),
                "fecha_fin": (
                    f"{event['fecha']}T{end}:00"
                ),
                "ubicacion": event["ubicacion"],
                "descripcion": (
                    f"{event['campeonato']} - "
                    f"Fecha {event['round']}"
                ),
                "imperdible": imperdible,
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

            # ------------------------------------------------
            # 1. CALENDARIOS
            # ------------------------------------------------

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

            # ------------------------------------------------
            # 2. DEDUPLICAR
            # ------------------------------------------------

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

            # ------------------------------------------------
            # 3. CRONOGRAMAS
            # ------------------------------------------------

            schedules = {}

            for event in calendar_events:

                print(
                    f"\n[{event['categoria']}] "
                    f"Fecha {event['round']} - "
                    f"{event['fecha']} - "
                    f"{event['ubicacion']}"
                )

                sessions, source = (
                    discover_schedule_for_event(
                        browser,
                        event["categoria"],
                        event,
                    )
                )

                if sessions:

                    schedules[
                        (
                            event["categoria"],
                            event["round"],
                            event["fecha"],
                        )
                    ] = sessions

                    print(
                        f"  Horarios encontrados: "
                        f"{len(sessions)}"
                    )

                else:

                    print(
                        "  Sin horarios publicados."
                    )

        finally:
            browser.close()

    # --------------------------------------------------------
    # 4. GENERAR JSON
    # --------------------------------------------------------

    events = build_events(
        calendar_events,
        schedules,
    )

    # --------------------------------------------------------
    # 5. DEDUPLICAR UID
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # 6. RESUMEN
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("RESUMEN ACTC")
    print("=" * 70)

    for category in CATEGORIES:

        dates = sum(
            1
            for x in calendar_events
            if x["categoria"] == category
        )

        sessions = sum(
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
            for x in calendar_events
            if x["categoria"] == category
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
