from pathlib import Path
import csv
import re
import subprocess

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"

MOTOCAL_ICS = DATA / "motorsport.ics"
EVENTS_CSV = DATA / "events.csv"
FINAL_ICS = OUTPUT / "automovilismo.ics"

DATA.mkdir(exist_ok=True)
OUTPUT.mkdir(exist_ok=True)


def classify(uid, name, location):
    """Clasifica el evento usando principalmente su UID."""

    u = uid.lower()
    n = name.lower()
    l = location.lower()

    # =========================
    # FÓRMULA
    # =========================

    if "f1-academy" in u:
        categoria = "Fórmula"
        campeonato = "F1 Academy"

    elif "formula-e" in u or "f1calendar-fe" in u:
        categoria = "Fórmula"
        campeonato = "Formula E"

    elif "f1calendar-f1-" in u:
        categoria = "Fórmula"
        campeonato = "F1"

    elif "f1calendar-f2-" in u:
        categoria = "Fórmula"
        campeonato = "F2"

    elif "f1calendar-f3-" in u:
        categoria = "Fórmula"
        campeonato = "F3"

    # =========================
    # MOTOS
    # =========================

    elif u.startswith("motogp-"):
        categoria = "Motos"
        campeonato = "MotoGP"

    elif u.startswith("moto2-"):
        categoria = "Motos"
        campeonato = "Moto2"

    elif u.startswith("moto3-"):
        categoria = "Motos"
        campeonato = "Moto3"

    elif "worldsbk" in u:
        categoria = "Motos"
        campeonato = "WorldSBK"

    # =========================
    # ENDURANCE
    # =========================

    elif u.startswith("wec-"):
        categoria = "Endurance"
        campeonato = "WEC"

    elif "elms" in u:
        categoria = "Endurance"
        campeonato = "ELMS"

    elif "mlmc" in u or "le-mans-cup" in u:
        categoria = "Endurance"
        campeonato = "Le Mans Cup"

    elif "imsa" in u:
        categoria = "Endurance"
        campeonato = "IMSA"

    # =========================
    # GT
    # =========================

    elif "gtwc-europe" in u:
        categoria = "GT"
        campeonato = "GT World Challenge Europe"

    elif "gtwc-america" in u:
        categoria = "GT"
        campeonato = "GT World Challenge America"

    elif "gtwc-asia" in u:
        categoria = "GT"
        campeonato = "GT World Challenge Asia"

    elif "igtc" in u:
        categoria = "GT"
        campeonato = "IGTC"

    elif "super-gt" in u:
        categoria = "GT"
        campeonato = "Super GT"

    # =========================
    # ARGENTINA
    # =========================

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

    # =========================
    # NASCAR
    # =========================

    elif "nascar" in u or "nascar" in n:
        categoria = "NASCAR"

        if "xfinity" in u or "xfinity" in n:
            campeonato = "NASCAR Xfinity"
        elif "truck" in u or "truck" in n:
            campeonato = "NASCAR Truck"
        else:
            campeonato = "NASCAR Cup"

    # =========================
    # INDYCAR
    # =========================

    elif "indycar" in u or "indycar" in n or "indy-500" in u:
        categoria = "IndyCar"
        campeonato = "IndyCar"

    # =========================
    # RALLY
    # =========================

    elif "wrc" in u or "wrc" in n:
        categoria = "Rally"
        campeonato = "WRC"

    elif "dakar" in u or "dakar" in n:
        categoria = "Rally"
        campeonato = "Dakar"

    elif "rallycross" in u or "rallycross" in n:
        categoria = "Rally"
        campeonato = "Rallycross"

    # =========================
    # DRIFT
    # =========================

    elif "drift" in u or "drift" in n:
        categoria = "Drift"
        campeonato = "Formula Drift"

    # =========================
    # RESPALDO
    # =========================

    else:
        categoria = "Otros"
        campeonato = "Otros"

    # =========================
    # TIPO DE SESIÓN
    # =========================

    if any(x in n for x in [
        "race",
        "carrera",
    ]):
        tipo = "Carrera"

    elif any(x in n for x in [
        "qualifying",
        "qualification",
        "clasificación",
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

    # =========================
    # IMPERDIBLES
    # =========================

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

    # Unfold de líneas ICS
    text = re.sub(r"\r?\n[ \t]", "", text)

    events = []
    blocks = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S)

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
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(events)


def main():

    print("Ejecutando: motocal generate 2026 --refresh")

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

    FINAL_ICS.write_text(
        MOTOCAL_ICS.read_text(
            encoding="utf-8"
        ),
        encoding="utf-8"
    )

    write_csv(events)

    print()
    print(f"OK: {len(events)} eventos.")
    print(f"CSV: {EVENTS_CSV}")
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

    for category, count in sorted(categories.items()):
        print(f"  {category}: {count}")

    print()
    print("Campeonatos:")

    for championship, count in sorted(
        championships.items()
    ):
        print(f"  {championship}: {count}")


if __name__ == "__main__":
    main()
