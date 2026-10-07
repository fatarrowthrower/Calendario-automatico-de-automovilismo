from pathlib import Path
import csv
import re
import subprocess
from datetime import datetime

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUT = ROOT / "output"

MOTOCAL_ICS = DATA / "motorsport.ics"
EVENTS_CSV = DATA / "events.csv"
FINAL_ICS = OUTPUT / "automovilismo.ics"

DATA.mkdir(exist_ok=True)
OUTPUT.mkdir(exist_ok=True)


def classify(name):
    """Clasifica automáticamente cada evento."""

    n = name.lower()

    # Motos
    if any(x in n for x in [
        "motogp", "moto2", "moto3", "worldsbk",
        "superbike", "superbike world"
    ]):
        categoria = "Motos"
        if "motogp" in n:
            campeonato = "MotoGP"
        elif "moto2" in n:
            campeonato = "Moto2"
        elif "moto3" in n:
            campeonato = "Moto3"
        else:
            campeonato = "WorldSBK"

    # Fórmula
    elif any(x in n for x in [
        "formula 1", "formula1", "f1 ", "grand prix",
        "formula 2", "formula2", "f2 ",
        "formula 3", "formula3", "f3 ",
        "formula e", "f1 academy", "formula academy"
    ]):
        categoria = "Fórmula"

        if "formula 1" in n or "formula1" in n or "f1 " in n or "grand prix" in n:
            campeonato = "F1"
        elif "formula 2" in n or "formula2" in n or "f2 " in n:
            campeonato = "F2"
        elif "formula 3" in n or "formula3" in n or "f3 " in n:
            campeonato = "F3"
        elif "formula e" in n:
            campeonato = "Formula E"
        else:
            campeonato = "F1 Academy"

    # Endurance
    elif any(x in n for x in [
        "wec", "world endurance", "le mans",
        "elms", "le mans cup", "mlmc",
        "imsa", "nürburgring", "nurburgring",
        "nls", "24h", "24 hours", "endurance"
    ]):
        categoria = "Endurance"

        if "imsa" in n:
            campeonato = "IMSA"
        elif "wec" in n or "world endurance" in n:
            campeonato = "WEC"
        elif "le mans" in n:
            campeonato = "Le Mans"
        elif "elms" in n:
            campeonato = "ELMS"
        elif "nürburgring" in n or "nurburgring" in n:
            campeonato = "Nürburgring"
        else:
            campeonato = "Endurance"

    # GT
    elif any(x in n for x in [
        "gt world", "gtwc", "gt3", "igtc",
        "intercontinental gt", "super gt"
    ]):
        categoria = "GT"

        if "super gt" in n:
            campeonato = "Super GT"
        elif "igtc" in n or "intercontinental gt" in n:
            campeonato = "IGTC"
        else:
            campeonato = "GT World Challenge"

    # IndyCar
    elif any(x in n for x in [
        "indycar", "indy 500", "indianapolis 500"
    ]):
        categoria = "IndyCar"
        campeonato = "IndyCar"

    # NASCAR
    elif any(x in n for x in [
        "nascar", "cup series", "xfinity", "truck series"
    ]):
        categoria = "NASCAR"

        if "xfinity" in n:
            campeonato = "NASCAR Xfinity"
        elif "truck" in n:
            campeonato = "NASCAR Truck"
        else:
            campeonato = "NASCAR Cup"

    # Rally
    elif any(x in n for x in [
        "wrc", "world rally", "rally",
        "dakar", "rallycross"
    ]):
        categoria = "Rally"

        if "dakar" in n:
            campeonato = "Dakar"
        elif "wrc" in n or "world rally" in n:
            campeonato = "WRC"
        else:
            campeonato = "Rally"

    # Argentina
    elif any(x in n for x in [
        "turismo carretera", "tc pista", "tc pick",
        "tc2000", "turismo nacional", "turismo pista",
        "top race", "rally argentino", "formula nacional",
        "formula uno argentina"
    ]):
        categoria = "Argentina"

        if "turismo carretera" in n:
            campeonato = "Turismo Carretera"
        elif "tc pista" in n:
            campeonato = "TC Pista"
        elif "tc pick" in n:
            campeonato = "TC Pick Up"
        elif "tc2000" in n:
            campeonato = "TC2000"
        elif "turismo nacional" in n:
            campeonato = "Turismo Nacional"
        elif "turismo pista" in n:
            campeonato = "Turismo Pista"
        elif "top race" in n:
            campeonato = "Top Race"
        elif "rally argentino" in n:
            campeonato = "Rally Argentino"
        else:
            campeonato = "Fórmula Argentina"

    # Drift
    elif any(x in n for x in [
        "formula drift", "drift"
    ]):
        categoria = "Drift"
        campeonato = "Formula Drift"

    else:
        categoria = "Otros"
        campeonato = "Otros"

    # Tipo de sesión
    if any(x in n for x in ["race", "carrera", "grand prix", "24h", "24 hours"]):
        tipo = "Carrera"
    elif any(x in n for x in ["qualifying", "qualification", "clasificación"]):
        tipo = "Clasificación"
    elif "sprint" in n:
        tipo = "Sprint"
    elif any(x in n for x in ["practice", "entrenamiento", "free practice"]):
        tipo = "Entrenamiento"
    else:
        tipo = "Evento"

    # Prioridad
    if any(x in n for x in [
        "formula 1", "formula1", "f1 ",
        "motogp", "wec", "le mans",
        "indy 500", "indianapolis 500",
        "dakar", "24h", "24 hours"
    ]):
        prioridad = "Imperdible"
    else:
        prioridad = "Normal"

    return categoria, campeonato, tipo, prioridad


def parse_ics(path):
    """Lee eventos del archivo ICS generado por motocal."""

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

        categoria, campeonato, tipo, prioridad = classify(summary)

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

    with EVENTS_CSV.open("w", newline="", encoding="utf-8") as f:
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
        raise SystemExit("ERROR: motocal no pudo generar el calendario.")

    if not MOTOCAL_ICS.exists():
        raise SystemExit("ERROR: no se creó data/motorsport.ics")

    events = parse_ics(MOTOCAL_ICS)

    if not events:
        raise SystemExit("ERROR: no se encontraron eventos.")

    # Copiamos el ICS original como calendario final.
    FINAL_ICS.write_text(
        MOTOCAL_ICS.read_text(encoding="utf-8"),
        encoding="utf-8"
    )

    write_csv(events)

    print()
    print(f"OK: {len(events)} eventos.")
    print(f"CSV: {EVENTS_CSV}")
    print(f"ICS: {FINAL_ICS}")

    # Resumen de categorías
    categories = {}
    for event in events:
        categories[event["categoria"]] = categories.get(
            event["categoria"], 0
        ) + 1

    print()
    print("Categorías:")
    for category, count in sorted(categories.items()):
        print(f"  {category}: {count}")


if __name__ == "__main__":
    main()
