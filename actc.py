import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urljoin


ACTC_SOURCES = {
    "TC": "https://actc.org.ar/tc/calendario",
    "TC Pista": "https://actc.org.ar/tcp/calendario",
    "TC Pick Up": "https://actc.org.ar/tcpk/calendario",
}

OUTPUT = Path("data/actc_events.json")


def current_year():
    return datetime.now().year


def fetch(url):
    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )
        },
    )

    with urlopen(
        req,
        timeout=30,
    ) as response:
        return response.read().decode(
            "utf-8",
            errors="ignore",
        )


def clean(text):
    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def strip_html(html):
    html = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        html,
        flags=re.I | re.S,
    )

    html = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        html,
        flags=re.I | re.S,
    )

    html = re.sub(
        r"<[^>]+>",
        " ",
        html,
    )

    return clean(html)


def parse_date(text):
    months = {
        "ene": 1,
        "feb": 2,
        "mar": 3,
        "abr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "ago": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dic": 12,
    }

    match = re.search(
        r"(\d{1,2})\s+([a-záéíóú]+)\s+(\d{4})",
        text.lower(),
    )

    if not match:
        return None

    day = int(match.group(1))
    month_name = match.group(2)[:3]
    year = int(match.group(3))

    month = months.get(
        month_name
    )

    if not month:
        return None

    return (
        f"{year:04d}-"
        f"{month:02d}-"
        f"{day:02d}"
    )


def slugify(text):
    text = text.lower()

    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
        "ñ": "n",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(
        r"[^a-z0-9]+",
        "-",
        text,
    )

    return text.strip("-")


def parse_calendar(
    html,
    championship,
):
    events = []

    # Buscamos bloques que contengan "Fecha N".
    # El HTML oficial puede variar, por eso usamos
    # un parser deliberadamente flexible.
    pattern = re.compile(
        r"Fecha\s+(\d+)",
        re.IGNORECASE,
    )

    matches = list(
        pattern.finditer(html)
    )

    if not matches:
        # Segundo intento sobre el texto limpio.
        text = strip_html(html)

        matches = list(
            pattern.finditer(text)
        )

        source_for_matches = text
    else:
        source_for_matches = html

    for index, match in enumerate(matches):

        round_number = int(
            match.group(1)
        )

        block_start = match.start()

        if index + 1 < len(matches):
            block_end = matches[
                index + 1
            ].start()
        else:
            block_end = min(
                len(source_for_matches),
                block_start + 3000,
            )

        block = source_for_matches[
            block_start:block_end
        ]

        block_text = strip_html(
            block
        )

        date_match = re.search(
            r"(\d{1,2}\s+"
            r"[A-Za-zÁÉÍÓÚáéíóú]+"
            r"\s+\d{4})",
            block_text,
        )

        if not date_match:
            continue

        date = parse_date(
            date_match.group(1)
        )

        if not date:
            continue

        # Intentamos obtener el circuito desde el bloque.
        location = extract_location(
            block_text
        )

        # Buscamos el enlace oficial carrera-online.
        cronograma_url = find_cronograma_url(
            block,
            championship,
        )

        # Fallback: intentamos encontrar cualquier enlace
        # carrera-online dentro del HTML completo cercano.
        if not cronograma_url:
            cronograma_url = find_cronograma_url(
                source_for_matches[
                    max(0, block_start - 500):
                    min(
                        len(source_for_matches),
                        block_end + 500,
                    )
                ],
                championship,
            )

        # Evento de respaldo de la fecha.
        events.append(
            {
                "uid": (
                    "actc-"
                    f"{championship.lower().replace(' ', '-')}-"
                    f"{date[:4]}-"
                    f"{round_number:02d}"
                ),
                "categoria": "Argentina",
                "campeonato": championship,
                "tipo": "Carrera",
                "fecha_inicio": (
                    f"{date}T12:00:00"
                ),
                "fecha_fin": (
                    f"{date}T23:59:00"
                ),
                "ubicacion": location,
                "descripcion": (
                    f"{championship} - "
                    f"Fecha {round_number}"
                ),
                "imperdible": True,
            }
        )

        if cronograma_url:
            print(
                f"  Fecha {round_number}: "
                f"cronograma encontrado"
            )

            try:
                cronograma_html = fetch(
                    cronograma_url
                )

                session_events = parse_cronograma(
                    cronograma_html,
                    championship,
                    round_number,
                    date,
                    location,
                )

                events.extend(
                    session_events
                )

                print(
                    f"  Fecha {round_number}: "
                    f"{len(session_events)} sesiones "
                    f"con horario"
                )

            except Exception as exc:
                print(
                    f"  Fecha {round_number}: "
                    f"ERROR cronograma: {exc}"
                )

        else:
            print(
                f"  Fecha {round_number}: "
                f"no se encontró cronograma"
            )

    return events


def extract_location(text):
    text = clean(text)

    # Intentamos encontrar el texto que aparece
    # inmediatamente después de la fecha.
    match = re.search(
        r"\d{1,2}\s+"
        r"[A-Za-zÁÉÍÓÚáéíóú]+\s+"
        r"\d{4}\s+"
        r"(.{1,150})",
        text,
    )

    if match:
        location = clean(
            match.group(1)
        )

        location = re.split(
            r"\bFecha\b",
            location,
            flags=re.I,
        )[0]

        location = re.split(
            r"\bVenta\b",
            location,
            flags=re.I,
        )[0]

        if location:
            return location[:100]

    return "Argentina"


def find_cronograma_url(
    html,
    championship,
):
    """
    Busca cualquier enlace relacionado con la carrera
    dentro del HTML de ACTC.

    Por ahora mostramos los enlaces encontrados en el log
    para descubrir exactamente cómo está construida la
    página oficial.
    """

    all_links = re.findall(
        r'href=["\']([^"\']+)["\']',
        html,
        flags=re.I,
    )

    interesting = []

    for href in all_links:
        href = href.replace(
            "&amp;",
            "&",
        )

        lower = href.lower()

        if (
            "carrera-online" in lower
            or "cronograma" in lower
            or "calendario" in lower
        ):
            full_url = urljoin(
                "https://actc.org.ar/",
                href,
            )

            if full_url not in interesting:
                interesting.append(
                    full_url
                )

    if interesting:
        print(
            "    Enlaces ACTC encontrados:"
        )

        for url in interesting[:20]:
            print(
                f"      {url}"
            )

        # Preferimos directamente una URL de cronograma.
        for url in interesting:
            if "cronograma" in url.lower():
                return url

        # Segundo intento: carrera-online.
        for url in interesting:
            if "carrera-online" in url.lower():
                return url

    return None
    matches = re.findall(
        r'href=["\']([^"\']*carrera-online[^"\']*)["\']',
        html,
        flags=re.I,
    )

    if not matches:
        return None

    for href in matches:
        href = href.replace(
            "&amp;",
            "&",
        )

        if "cronograma" in href.lower():
            return urljoin(
                "https://actc.org.ar/",
                href,
            )

    # Si encontramos carrera-online pero no
    # aparece "cronograma", usamos el primero.
    return urljoin(
        "https://actc.org.ar/",
        matches[0],
    )


def normalize_session_name(name):
    text = clean(name)

    # Eliminamos palabras que no describen
    # una sesión de pista.
    text = re.sub(
        r"\bresultados\b",
        "",
        text,
        flags=re.I,
    )

    text = clean(text)

    return text


def classify_actc_session(name):
    text = name.lower()

    # Primero carrera/final.
    if (
        "final" in text
        and "parcial" not in text
    ):
        return "Carrera"

    # Series.
    if (
        "serie" in text
        and "parcial" not in text
        and "grilla" not in text
    ):
        return "Serie"

    # Clasificación.
    if (
        "clasific" in text
        and "parcial" not in text
        and "grilla" not in text
    ):
        return "Clasificación"

    # Entrenamientos.
    if (
        "entrenamiento" in text
        and "parcial" not in text
    ):
        return "Entrenamiento"

    return None


def parse_time(text):
    match = re.search(
        r"\b([01]?\d|2[0-3]):([0-5]\d)\b",
        text,
    )

    if not match:
        return None

    hour = int(
        match.group(1)
    )

    minute = int(
        match.group(2)
    )

    return (
        f"{hour:02d}:"
        f"{minute:02d}"
    )


def session_duration(tipo):
    if tipo == "Entrenamiento":
        return timedelta(
            minutes=60
        )

    if tipo == "Clasificación":
        return timedelta(
            minutes=60
        )

    if tipo == "Serie":
        return timedelta(
            minutes=30
        )

    if tipo == "Carrera":
        return timedelta(
            hours=2
        )

    return timedelta(
        hours=1
    )


def parse_cronograma(
    html,
    championship,
    round_number,
    race_date,
    location,
):
    """
    Extrae únicamente sesiones que tengan una
    hora explícita publicada por ACTC.

    No inventa horarios.
    """

    text = strip_html(
        html
    )

    events = []

    # Capturamos segmentos alrededor de cada hora.
    # Las páginas oficiales tienen formatos como:
    #
    # 09:00 1º Entrenamiento
    # 11:05 2º Entrenamiento
    # 13:15 3º Entrenamiento
    #
    time_pattern = re.compile(
        r"\b"
        r"([01]?\d|2[0-3])"
        r":"
        r"([0-5]\d)"
        r"\b"
        r"(.{0,180})",
        re.I,
    )

    for match in time_pattern.finditer(
        text
    ):
        hour = int(
            match.group(1)
        )

        minute = int(
            match.group(2)
        )

        following = clean(
            match.group(3)
        )

        # Cortamos el texto en separadores
        # habituales del HTML convertido a texto.
        following = re.split(
            r"\b(?:Resultados|Grillas|Material Previo|Grupos|Campeonato)\b",
            following,
            maxsplit=1,
            flags=re.I,
        )[0]

        following = clean(
            following
        )

        if not following:
            continue

        tipo = classify_actc_session(
            following
        )

        if not tipo:
            continue

        # Evitamos resultados parciales.
        lower = following.lower()

        if "parcial" in lower:
            continue

        if "grilla" in lower:
            continue

        if "resultados" in lower:
            continue

        nombre = normalize_session_name(
            following
        )

        # Evitamos textos demasiado largos.
        if len(nombre) > 100:
            nombre = nombre[:100]

        start_dt = datetime.strptime(
            f"{race_date} "
            f"{hour:02d}:{minute:02d}",
            "%Y-%m-%d %H:%M",
        )

        end_dt = (
            start_dt
            + session_duration(tipo)
        )

        uid = (
            "actc-"
            f"{championship.lower().replace(' ', '-')}-"
            f"{race_date}-"
            f"{hour:02d}{minute:02d}-"
            f"{slugify(nombre)}"
        )

        events.append(
            {
                "uid": uid,
                "categoria": "Argentina",
                "campeonato": championship,
                "tipo": tipo,
                "fecha_inicio": (
                    start_dt.strftime(
                        "%Y-%m-%dT%H:%M:%S"
                    )
                ),
                "fecha_fin": (
                    end_dt.strftime(
                        "%Y-%m-%dT%H:%M:%S"
                    )
                ),
                "ubicacion": location,
                "descripcion": (
                    f"{championship} - "
                    f"Fecha {round_number} - "
                    f"{nombre}\n"
                    f"Fuente oficial ACTC"
                ),
                "imperdible": (
                    tipo == "Carrera"
                ),
            }
        )

    # Eliminamos duplicados.
    unique = {}

    for event in events:
        unique[
            event["uid"]
        ] = event

    return list(
        unique.values()
    )


def main():
    year = current_year()

    print(
        f"Consultando ACTC para {year}..."
    )

    all_events = []

    for championship, url in ACTC_SOURCES.items():

        print()
        print(
            f"Consultando ACTC: "
            f"{championship}"
        )

        try:
            html = fetch(
                url
            )

            events = parse_calendar(
                html,
                championship,
            )

            print(
                f"  Encontrados: "
                f"{len(events)} eventos/sesiones"
            )

            all_events.extend(
                events
            )

        except Exception as exc:
            print(
                f"  ERROR: {exc}"
            )

    unique = {}

    for event in all_events:
        unique[
            event["uid"]
        ] = event

    events = list(
        unique.values()
    )

    events.sort(
        key=lambda x: (
            x.get(
                "fecha_inicio",
                "",
            ),
            x.get(
                "campeonato",
                "",
            ),
            x.get(
                "tipo",
                "",
            ),
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

    print()
    print(
        f"ACTC: {len(events)} "
        f"eventos guardados en {OUTPUT}"
    )

    print()
    print("Resumen por campeonato:")

    championships = {}

    for event in events:
        championship = event.get(
            "campeonato",
            "Otros",
        )

        championships[
            championship
        ] = (
            championships.get(
                championship,
                0,
            )
            + 1
        )

    for championship in sorted(
        championships
    ):
        print(
            f"  {championship}: "
            f"{championships[championship]}"
        )

    print()
    print("Resumen por tipo:")

    types = {}

    for event in events:
        tipo = event.get(
            "tipo",
            "Evento",
        )

        types[tipo] = (
            types.get(
                tipo,
                0,
            )
            + 1
        )

    for tipo in sorted(
        types
    ):
        print(
            f"  {tipo}: "
            f"{types[tipo]}"
        )


if __name__ == "__main__":
    main()
