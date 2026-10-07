from pathlib import Path
import csv
import json
import re
import subprocess
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"

MOTOCAL_ICS = DATA / "motorsport.ics"
ACTC_JSON = DATA / "actc_events.json"
EVENTS_CSV = DATA / "events.csv"
EVENTS_JSON = DATA / "events.json"
FINAL_ICS = OUTPUT / "automovilismo.ics"

DATA.mkdir(exist_ok=True)
OUTPUT.mkdir(exist_ok=True)


def classify(uid, name, location):
    u = uid.lower()
    n = name.lower()

    if "f1-academy" in u:
        categoria, campeonato = "Fórmula", "F1 Academy"
    elif "formula-e" in u or "f1calendar-fe" in u:
        categoria, campeonato = "Fórmula", "Formula E"
    elif "f1calendar-f1-" in u:
        categoria, campeonato = "Fórmula", "F1"
    elif "f1calendar-f2-" in u:
        categoria, campeonato = "Fórmula", "F2"
    elif "f1calendar-f3-" in u:
        categoria, campeonato = "Fórmula", "F3"

    elif u.startswith("motogp-"):
        categoria, campeonato = "Motos", "MotoGP"
    elif u.startswith("moto2-"):
        categoria, campeonato = "Motos", "Moto2"
    elif u.startswith("moto3-"):
        categoria, campeonato = "Motos", "Moto3"
    elif "worldsbk" in u:
        categoria, campeonato = "Motos", "WorldSBK"

    elif u.startswith("wec-"):
        categoria, campeonato = "Endurance", "WEC"
    elif "elms" in u:
        categoria, campeonato = "Endurance", "ELMS"
    elif "mlmc" in u or "le-mans-cup" in u:
        categoria, campeonato = "Endurance", "Le Mans Cup"
    elif "imsa" in u:
        categoria, campeonato = "Endurance", "IMSA"

    elif "gtwc-europe" in u:
        categoria, campeonato = "GT", "GT World Challenge Europe"
    elif "gtwc-america" in u:
        categoria, campeonato = "GT", "GT World Challenge America"
    elif "gtwc-asia" in u:
        categoria, campeonato = "GT", "GT World Challenge Asia"
    elif "igtc" in u:
        categoria, campeonato = "GT", "IGTC"
    elif "super-gt" in u:
        categoria, campeonato = "GT", "Super GT"

    elif any(x in u or x in n for x in [
        "turismo-carretera",
        "tc-pista",
        "tc-pick",
        "tc2000",
        "turismo-nacional",
        "turismo-pista",
        "top-race",
        "rally-argentino",
        "formula-nacional",
    ]):
        categoria = "Argentina"

        if "turismo-carretera" in u or "turismo carretera" in n:
            campeonato = "Turismo Carretera"
        elif "tc-pista" in u or "tc pista" in n:
            campeonato = "TC Pista"
        elif "tc-pick" in u or "tc pick" in n:
            campeonato = "TC Pick Up"
        elif "tc2000" in u or "tc2000" in n:
            campeonato = "TC2000"
        elif "turismo-nacional" in u or "turismo nacional" in n:
            campeonato = "Turismo Nacional"
        elif "turismo-pista" in u or "turismo pista" in n:
            campeonato = "Turismo Pista"
        elif "top-race" in u or "top race" in n:
            campeonato = "Top Race"
        elif "rally-argentino" in u or "rally argentino" in n:
            campeonato = "Rally Argentino"
        else:
            campeonato = "Fórmula Argentina"

    elif "nascar" in u or "nascar" in n:
        categoria = "NASCAR"

        if "xfinity" in u or "xfinity" in n:
            campeonato = "NASCAR Xfinity"
        elif "truck" in u or "truck" in n:
            campeonato = "NASCAR Truck"
        else:
            campeonato = "NASCAR Cup"

    elif "indycar" in u or "indycar" in n or "indy-500" in u:
        categoria, campeonato = "IndyCar", "IndyCar"

    elif "wrc" in u or "wrc" in n:
        categoria, campeonato = "Rally", "WRC"
    elif "dakar" in u or "dakar" in n:
        categoria, campeonato = "Rally", "Dakar"
    elif "rallycross" in u or "rallycross" in n:
        categoria, campeonato = "Rally", "Rallycross"

    elif "drift" in u or "drift" in n:
        categoria, campeonato = "Drift", "Formula Drift"

    else:
        categoria, campeonato = "Otros", "Otros"

    if any(x in n for x in ["race", "carrera"]):
        tipo = "Carrera"
    elif any(x in n for x in [
        "qualifying",
        "qualification",
        "clasificación"
    ]):
        tipo = "Clasificación"
    elif "sprint" in n:
        tipo = "Sprint"
    elif any(x in n for x in [
        "practice",
        "free practice",
        "entrenamiento",
        "fp1",
        "fp2",
        "fp3",
    ]):
        tipo = "Entrenamiento"
    else:
        tipo = "Evento"

    if (
        campeonato in [
            "F1",
            "MotoGP",
            "WEC",
            "Le Mans Cup",
            "Formula E",
            "IndyCar",
            "NASCAR Cup",
            "WRC",
            "Dakar",
        ]
        and tipo == "Carrera"
    ):
        prioridad = "Imperdible"
    else:
        prioridad = "Normal"

    return categoria, campeonato, tipo, prioridad


def parse_ics(path):
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"\r?\n[ \t]", "", text)

    events = []
    blocks = re.findall(
        r"BEGIN:VEVENT(.*?)END:VEVENT",
        text,
        re.S
    )

    for block in blocks:

        def get_field(field):
            match = re.search(
                rf"^{field}(?:;[^:]*)?:(.*)$",
                block,
                re.M
            )
            return match.group(1).strip() if match else ""

        uid = get_field("UID")
        summary = get_field("SUMMARY")
        dtstart = get_field("DTSTART")
        dtend = get_field("DTEND")
        location = get_field("LOCATION")
        description = get_field("DESCRIPTION")

        categoria, campeonato, tipo, prioridad = classify(
            uid,
            summary,
            location
        )

        events.append({
            "uid": uid,
            "fecha_inicio": dtstart,
            "fecha_fin": dtend,
            "evento": summary,
            "categoria": categoria,
            "campeonato": campeonato,
            "tipo": tipo,
            "prioridad": prioridad,
            "ubicacion": location,
            "descripcion": description,
        })

    return events


def load_actc_events():
    if not ACTC_JSON.exists():
        print("ACTC: no existe actc_events.json. Se continúa sin ACTC.")
        return []

    try:
        events = json.loads(
            ACTC_JSON.read_text(encoding="utf-8")
        )

        if not isinstance(events, list):
            raise ValueError("Formato ACTC inválido.")

        print(
            f"ACTC: incorporando {len(events)} eventos."
        )

        return events

    except Exception as exc:
        raise SystemExit(
            f"ERROR leyendo ACTC: {exc}"
        )


def ics_escape(value):
    value = str(value or "")
    value = value.replace("\\", "\\\\")
    value = value.replace(";", "\\;")
    value = value.replace(",", "\\,")
    value = value.replace("\n", "\\n")
    return value


def actc_to_ics(event):
    start = event["fecha_inicio"]
    end = event["fecha_fin"]

    start_dt = datetime.strptime(
        start,
        "%Y-%m-%dT%H:%M:%S"
    )

    end_dt = datetime.strptime(
        end,
        "%Y-%m-%dT%H:%M:%S"
    )

    uid = event["uid"]

    summary = (
        f'{event["campeonato"]} - '
        f'{event["tipo"]}'
    )

    description = event.get(
        "descripcion",
        ""
    )

    location = event.get(
        "ubicacion",
        ""
    )

    lines = [
        "BEGIN:VEVENT",
        f"UID:{ics_escape(uid)}",
        f"DTSTART;TZID=America/Argentina/Buenos_Aires:"
        f"{start_dt.strftime('%Y%m%dT%H%M%S')}",
        f"DTEND;TZID=America/Argentina/Buenos_Aires:"
        f"{end_dt.strftime('%Y%m%dT%H%M%S')}",
        f"SUMMARY:{ics_escape(summary)}",
        f"LOCATION:{ics_escape(location)}",
        f"DESCRIPTION:{ics_escape(description)}",
        "END:VEVENT",
    ]

    return "\r\n".join(lines)


def merge_actc_into_ics(base_ics, actc_events):
    if not actc_events:
        return base_ics

    if "END:VCALENDAR" not in base_ics:
        raise SystemExit(
            "ERROR: el ICS principal no tiene END:VCALENDAR."
        )

    blocks = []

    for event in actc_events:
        blocks.append(
            actc_to_ics(event)
        )

    addition = "\r\n".join(blocks)

    return base_ics.replace(
        "END:VCALENDAR",
        addition + "\r\nEND:VCALENDAR"
    )


def write_csv(events):
    fields = [
        "uid",
        "fecha_inicio",
        "fecha_fin",
        "evento",
        "categoria",
        "campeonato",
        "tipo",
        "prioridad",
        "ubicacion",
        "descripcion",
    ]

    with EVENTS_CSV.open(
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fields
        )

        writer.writeheader()
        writer.writerows(events)


def write_json(events):
    with EVENTS_JSON.open(
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            events,
            f,
            ensure_ascii=False,
            indent=2
        )


def main():

    print(
        "Ejecutando: motocal generate 2026 --refresh"
    )

    result = subprocess.run(
        [
            "motocal",
            "generate",
            "2026",
            str(MOTOCAL_ICS),
            "--refresh",
        ],
        text=True,
    )

    if result.returncode != 0:
        raise SystemExit(
            "ERROR: motocal no pudo generar el calendario."
        )

    if not MOTOCAL_ICS.exists():
        raise SystemExit(
            "ERROR: no se creó data/motorsport.ics"
        )

    events = parse_ics(MOTOCAL_ICS)

    if not events:
        raise SystemExit(
            "ERROR: no se encontraron eventos."
        )

    print(
        f"Motocal: {len(events)} eventos."
    )

    # Incorporar eventos ACTC
    actc_events = load_actc_events()

    existing_uids = {
        event["uid"]
        for event in events
    }

    added_actc = 0

for event in actc_events:
    if event["uid"] not in existing_uids:

        # ACTC usa "imperdible"; el calendario general usa "prioridad"
        if "imperdible" in event:
            event["prioridad"] = (
                "Imperdible"
                if event.pop("imperdible")
                else "Normal"
            )

        events.append(event)
        existing_uids.add(event["uid"])
        added_actc += 1

    events.sort(
        key=lambda event: event["fecha_inicio"]
    )

    print(
        f"ACTC agregados al calendario: {added_actc}"
    )

    # Crear ICS final
    base_ics = MOTOCAL_ICS.read_text(
        encoding="utf-8"
    )

    final_ics = merge_actc_into_ics(
        base_ics,
        actc_events
    )

    FINAL_ICS.write_text(
        final_ics,
        encoding="utf-8"
    )

    # Crear JSON y CSV generales
    write_csv(events)
    write_json(events)

    print()
    print(f"OK: {len(events)} eventos totales.")
    print(f"CSV: {EVENTS_CSV}")
    print(f"JSON: {EVENTS_JSON}")
    print(f"ICS: {FINAL_ICS}")

    categories = {}
    championships = {}

    for event in events:

        category = event["categoria"]
        championship = event["campeonato"]

        categories[category] = (
            categories.get(category, 0) + 1
        )

        championships[championship] = (
            championships.get(championship, 0) + 1
        )

    print()
    print("Categorías:")

    for category, count in sorted(
        categories.items()
    ):
        print(f"  {category}: {count}")

    print()
    print("Campeonatos:")

    for championship, count in sorted(
        championships.items()
    ):
        print(f"  {championship}: {count}")


if __name__ == "__main__":
    main()
