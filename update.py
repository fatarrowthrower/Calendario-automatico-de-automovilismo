from pathlib import Path
import csv
import json
import re
import subprocess
from datetime import datetime


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"

MOTOCAL_ICS = DATA / "motorsport.ics"
ACTC_JSON = DATA / "actc_events.json"
EVENTS_CSV = DATA / "events.csv"
EVENTS_JSON = DATA / "events.json"
FINAL_ICS = OUTPUT / "automovilismo.ics"

TIMEZONE = "America/Argentina/Buenos_Aires"


def current_year():
    """
    Devuelve automáticamente el año actual.
    De esta manera el calendario pasa de 2026 a 2027,
    2028, etc. sin modificar este archivo cada año.
    """
    return datetime.now().year


def classify(uid, name):
    u = uid.lower()
    n = name.lower()

    if "f1-academy" in u:
        return "Fórmula", "F1 Academy"

    if "formula-e" in u or "f1calendar-fe" in u:
        return "Fórmula", "Formula E"

    if "f1calendar-f1-" in u:
        return "Fórmula", "F1"

    if "f1calendar-f2-" in u:
        return "Fórmula", "F2"

    if "f1calendar-f3-" in u:
        return "Fórmula", "F3"

    if u.startswith("motogp-"):
        return "Motos", "MotoGP"

    if u.startswith("moto2-"):
        return "Motos", "Moto2"

    if u.startswith("moto3-"):
        return "Motos", "Moto3"

    if "worldsbk" in u:
        return "Motos", "WorldSBK"

    if u.startswith("wec-"):
        return "Endurance", "WEC"

    if "elms" in u:
        return "Endurance", "ELMS"

    if "mlmc" in u or "le-mans-cup" in u:
        return "Endurance", "Le Mans Cup"

    if "imsa" in u:
        return "Endurance", "IMSA"

    if "gtwc-europe" in u:
        return "GT", "GT World Challenge Europe"

    if "gtwc-america" in u:
        return "GT", "GT World Challenge America"

    if "gtwc-asia" in u:
        return "GT", "GT World Challenge Asia"

    if "igtc" in u:
        return "GT", "IGTC"

    if "super-gt" in u:
        return "GT", "Super GT"

    if any(
        x in u or x in n
        for x in [
            "turismo-carretera",
            "tc-pista",
            "tc-pick",
            "tc2000",
            "turismo-nacional",
            "turismo-pista",
            "top-race",
            "rally-argentino",
            "formula-nacional",
        ]
    ):
        return "Argentina", "Automovilismo argentino"

    if "nascar" in u or "nascar" in n:
        if "cup" in u or "cup" in n:
            return "NASCAR", "NASCAR Cup"
        if "xfinity" in u or "xfinity" in n:
            return "NASCAR", "NASCAR Xfinity"
        if "truck" in u or "truck" in n:
            return "NASCAR", "NASCAR Truck"
        return "NASCAR", "NASCAR"

    if "indycar" in u or "indycar" in n or "indy-500" in u:
        return "IndyCar", "IndyCar"

    if "wrc" in u or "wrc" in n:
        return "Rally", "WRC"

    if "dakar" in u or "dakar" in n:
        return "Rally", "Dakar"

    if "rallycross" in u or "rallycross" in n:
        return "Rally", "Rallycross"

    if "drift" in u or "drift" in n:
        return "Drift", "Formula Drift"

    return "Otros", "Otros"


def classify_session(name):
    text = name.lower()

    if "sprint" in text:
        return "Sprint"

    if any(
        x in text
        for x in [
            "qualifying",
            "qualification",
            "clasificación",
        ]
    ):
        return "Clasificación"

    if any(
        x in text
        for x in [
            "race",
            "carrera",
        ]
    ):
        return "Carrera"

    if any(
        x in text
        for x in [
            "practice",
            "free practice",
            "entrenamiento",
            "fp1",
            "fp2",
            "fp3",
        ]
    ):
        return "Entrenamiento"

    return "Evento"


def is_imperdible(campeonato, tipo):
    return (
        campeonato
        in {
            "F1",
            "MotoGP",
            "WEC",
            "Le Mans Cup",
            "Formula E",
            "IndyCar",
            "NASCAR Cup",
            "WRC",
            "Dakar",
            "TC",
            "TC Pista",
            "TC Pick Up",
        }
        and tipo == "Carrera"
    )


def parse_ics(path):
    text = path.read_text(
        encoding="utf-8",
        errors="ignore",
    )

    blocks = re.findall(
        r"BEGIN:VEVENT(.*?)END:VEVENT",
        text,
        re.S,
    )

    events = []

    for block in blocks:

        def get_value(field):
            match = re.search(
                rf"^{field}(?:;[^:]*)?:(.*)$",
                block,
                re.MULTILINE,
            )
            return match.group(1).strip() if match else ""

        uid = get_value("UID")
        summary = get_value("SUMMARY")
        location = get_value("LOCATION")
        description = get_value("DESCRIPTION")
        dtstart = get_value("DTSTART")
        dtend = get_value("DTEND")

        if not uid or not dtstart:
            continue

        categoria, campeonato = classify(
            uid,
            summary,
        )

        tipo = classify_session(summary)

        events.append(
            {
                "uid": uid,
                "categoria": categoria,
                "campeonato": campeonato,
                "tipo": tipo,
                "fecha_inicio": dtstart,
                "fecha_fin": dtend,
                "ubicacion": location,
                "descripcion": description,
                "prioridad": (
                    "alta"
                    if is_imperdible(
                        campeonato,
                        tipo,
                    )
                    else ""
                ),
            }
        )

    return events


def load_actc_events():
    if not ACTC_JSON.exists():
        return []

    try:
        events = json.loads(
            ACTC_JSON.read_text(
                encoding="utf-8",
            )
        )
    except Exception as exc:
        print(
            f"ERROR leyendo ACTC: {exc}"
        )
        return []

    normalized = []

    for event in events:
        event = dict(event)

        if "imperdible" in event:
            event["prioridad"] = (
                "alta"
                if event.get("imperdible")
                else ""
            )

            del event["imperdible"]

        normalized.append(event)

    return normalized


def ics_escape(value):
    if value is None:
        return ""

    return (
        str(value)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def actc_to_ics(event):
    uid = event["uid"]

    start = (
        event["fecha_inicio"]
        .replace("-", "")
        .replace(":", "")
    )

    end = (
        event["fecha_fin"]
        .replace("-", "")
        .replace(":", "")
    )

    start = start[:15]
    end = end[:15]

    return "\r\n".join(
        [
            "BEGIN:VEVENT",
            f"UID:{ics_escape(uid)}",
            f"DTSTART:{start}",
            f"DTEND:{end}",
            (
                "SUMMARY:"
                + ics_escape(
                    event.get(
                        "descripcion",
                        "",
                    )
                )
            ),
            (
                "LOCATION:"
                + ics_escape(
                    event.get(
                        "ubicacion",
                        "",
                    )
                )
            ),
            (
                "DESCRIPTION:"
                + ics_escape(
                    event.get(
                        "descripcion",
                        "",
                    )
                )
            ),
            "END:VEVENT",
        ]
    )


def merge_actc_into_events(
    events,
    actc_events,
):
    existing_uids = {
        event["uid"]
        for event in events
    }

    added = 0

    for event in actc_events:
        if event["uid"] in existing_uids:
            continue

        events.append(event)
        existing_uids.add(event["uid"])
        added += 1

    return added


def write_csv(events):
    fieldnames = [
        "uid",
        "categoria",
        "campeonato",
        "tipo",
        "fecha_inicio",
        "fecha_fin",
        "ubicacion",
        "descripcion",
        "prioridad",
    ]

    with EVENTS_CSV.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        for event in events:
            writer.writerow(
                {
                    field: event.get(
                        field,
                        "",
                    )
                    for field in fieldnames
                }
            )


def write_json(events):
    EVENTS_JSON.write_text(
        json.dumps(
            events,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def build_final_ics(events, year):
    OUTPUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Automovilismo Auto//ES",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:Automovilismo {year}",
        f"X-WR-TIMEZONE:{TIMEZONE}",
    ]

    for event in events:

        if event["uid"].startswith(
            "actc-"
        ):
            lines.append(
                actc_to_ics(event)
            )
            continue

        uid = ics_escape(
            event["uid"]
        )

        dtstart = event.get(
            "fecha_inicio",
            "",
        )

        dtend = event.get(
            "fecha_fin",
            "",
        )

        summary = (
            f"{event.get('campeonato', 'Automovilismo')} "
            f"- {event.get('tipo', 'Evento')}"
        )

        location = event.get(
            "ubicacion",
            "",
        )

        description = event.get(
            "descripcion",
            "",
        )

        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTART:{dtstart}",
                f"DTEND:{dtend}",
                (
                    "SUMMARY:"
                    + ics_escape(summary)
                ),
                (
                    "LOCATION:"
                    + ics_escape(location)
                ),
                (
                    "DESCRIPTION:"
                    + ics_escape(description)
                ),
                "END:VEVENT",
            ]
        )

    lines.append(
        "END:VCALENDAR"
    )

    FINAL_ICS.write_text(
        "\r\n".join(lines),
        encoding="utf-8",
    )


def main():
    year = current_year()

    print(
        f"Actualizando calendario para {year}..."
    )

    DATA.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    subprocess.run(
        [
            "motocal",
            "generate",
            str(year),
            str(MOTOCAL_ICS),
            "--refresh",
        ],
        check=True,
    )

    events = parse_ics(
        MOTOCAL_ICS
    )

    print(
        f"Motocal: {len(events)} eventos."
    )

    actc_events = load_actc_events()

    print(
        f"ACTC: incorporando "
        f"{len(actc_events)} eventos."
    )

    added = merge_actc_into_events(
        events,
        actc_events,
    )

    print(
        f"ACTC agregados al calendario: "
        f"{added}"
    )

    events.sort(
        key=lambda event: event.get(
            "fecha_inicio",
            "",
        )
    )

    write_csv(events)
    write_json(events)
    build_final_ics(
        events,
        year,
    )

    print()
    print(
        f"OK: {len(events)} eventos totales."
    )

    print(
        f"CSV: {EVENTS_CSV}"
    )

    print(
        f"JSON: {EVENTS_JSON}"
    )

    print(
        f"ICS: {FINAL_ICS}"
    )

    categories = {}

    for event in events:
        category = event.get(
            "categoria",
            "Otros",
        )

        categories[category] = (
            categories.get(
                category,
                0,
            )
            + 1
        )

    print()
    print("Categorías:")

    for category in sorted(
        categories
    ):
        print(
            f"  {category}: "
            f"{categories[category]}"
        )

    championships = {}

    for event in events:
        championship = event.get(
            "campeonato",
            "Otros",
        )

        championships[championship] = (
            championships.get(
                championship,
                0,
            )
            + 1
        )

    print()
    print("Campeonatos:")

    for championship in sorted(
        championships
    ):
        print(
            f"  {championship}: "
            f"{championships[championship]}"
        )


if __name__ == "__main__":
    main()
