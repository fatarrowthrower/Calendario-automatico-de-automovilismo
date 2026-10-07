#!/usr/bin/env python3
"""
Automovilismo Auto v2
- Uses motorsport-calendar's supported multi-provider command.
- Converts the resulting ICS to a normalized CSV.
- Merges optional Argentine events from data/argentina.csv.
- Generates output/automovilismo.ics.
- Fails loudly if no events were obtained.
"""
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import csv
import subprocess
import sys

from icalendar import Calendar, Event

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "output"
DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

YEAR = 2026
TZ = ZoneInfo("America/Argentina/Buenos_Aires")
SOURCE_ICS = DATA / "motorsport.ics"
OUTPUT_ICS = OUT / "automovilismo.ics"
OUTPUT_CSV = DATA / "events.csv"

def run_motocal():
    cmd = [
        "motocal", "generate", str(YEAR), str(SOURCE_ICS), "--refresh"
    ]
    print("Ejecutando:", " ".join(cmd))
    result = subprocess.run(cmd, text=True, capture_output=True)

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)

    if result.returncode != 0:
        raise RuntimeError(
            f"motocal terminó con código {result.returncode}. "
            "Revisá el bloque 'Ejecutando motocal' de este workflow."
        )

    if not SOURCE_ICS.exists() or SOURCE_ICS.stat().st_size == 0:
        raise RuntimeError("motocal terminó sin generar data/motorsport.ics.")

def as_local(dt):
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=TZ)
        return dt.astimezone(TZ)
    # All-day events are converted to midnight Argentina.
    return datetime(dt.year, dt.month, dt.day, tzinfo=TZ)

def first_text(component, key, default=""):
    value = component.get(key)
    if value is None:
        return default
    return str(value)

def parse_source_ics():
    cal = Calendar.from_ical(SOURCE_ICS.read_bytes())
    events = []

    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        start = component.get("DTSTART")
        if start is None:
            continue

        dt = as_local(start.dt)
        summary = first_text(component, "SUMMARY", "Automovilismo")

        # motocal emits useful championship/session information in SUMMARY.
        description = first_text(component, "DESCRIPTION", "")
        location = first_text(component, "LOCATION", "")

        events.append({
            "fecha": dt.strftime("%Y-%m-%d"),
            "hora_argentina": dt.strftime("%H:%M"),
            "categoria": infer_category(summary),
            "evento": summary,
            "sesion": "",
            "circuito": location,
            "pais": "",
            "inicio_iso": dt.isoformat(),
            "fuente": "motorsport-calendar",
            "_description": description,
        })
    return events

def infer_category(summary):
    s = summary.lower()
    rules = [
        ("f1", "F1"),
        ("formula 1", "F1"),
        ("f2", "F2"),
        ("formula 2", "F2"),
        ("f3", "F3"),
        ("formula 3", "F3"),
        ("wec", "WEC"),
        ("elms", "ELMS"),
        ("le mans cup", "Le Mans Cup"),
        ("motogp", "MotoGP"),
        ("moto2", "Moto2"),
        ("moto3", "Moto3"),
        ("gt world challenge europe", "GT World Challenge Europe"),
        ("gt world challenge america", "GT World Challenge America"),
        ("gt world challenge asia", "GT World Challenge Asia"),
        ("intercontinental gt", "IGTC"),
    ]
    for needle, label in rules:
        if needle in s:
            return label
    return "Automovilismo internacional"

def load_argentina():
    path = DATA / "argentina.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return [r for r in rows if r.get("inicio_iso")]

def normalize_argentina(rows):
    result = []
    for r in rows:
        try:
            dt = datetime.fromisoformat(r["inicio_iso"]).astimezone(TZ)
        except Exception:
            continue
        result.append({
            "fecha": dt.strftime("%Y-%m-%d"),
            "hora_argentina": dt.strftime("%H:%M"),
            "categoria": r.get("categoria", ""),
            "evento": r.get("evento", ""),
            "sesion": r.get("sesion", ""),
            "circuito": r.get("circuito", ""),
            "pais": r.get("pais", "Argentina"),
            "inicio_iso": dt.isoformat(),
            "fuente": r.get("fuente", ""),
        })
    return result

def dedupe_and_sort(events):
    seen = set()
    clean = []
    for e in events:
        key = (
            e.get("inicio_iso", ""),
            e.get("categoria", ""),
            e.get("evento", ""),
            e.get("sesion", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        clean.append(e)
    clean.sort(key=lambda e: e.get("inicio_iso", ""))
    return clean

def write_csv(events):
    fields = [
        "fecha", "hora_argentina", "categoria", "evento", "sesion",
        "circuito", "pais", "inicio_iso", "fuente"
    ]
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: e.get(k, "") for k in fields} for e in events)

def build_output_ics(events):
    cal = Calendar()
    cal.add("prodid", "-//Automovilismo Auto//AR//")
    cal.add("version", "2.0")
    cal.add("X-WR-CALNAME", "🏁 Automovilismo")
    cal.add("X-WR-TIMEZONE", "America/Argentina/Buenos_Aires")

    for i, e in enumerate(events):
        try:
            start = datetime.fromisoformat(e["inicio_iso"])
        except Exception:
            continue

        item = Event()
        uid_base = f"{start.strftime('%Y%m%dT%H%M%S')}-{e.get('categoria','')}-{e.get('evento','')}"
        uid = "".join(c if c.isalnum() or c in "-_." else "-" for c in uid_base)
        item.add("uid", f"{uid}@automovilismo-auto")
        item.add("dtstamp", datetime.now(TZ))
        item.add("dtstart", start)
        item.add("dtend", start + timedelta(minutes=90))
        item.add(
            "summary",
            " — ".join(x for x in [e.get("categoria", ""), e.get("evento", "")] if x)
        )

        details = []
        if e.get("sesion"):
            details.append(f"Sesión: {e['sesion']}")
        if e.get("circuito"):
            details.append(f"Circuito: {e['circuito']}")
        if e.get("pais"):
            details.append(f"País: {e['pais']}")
        if e.get("fuente"):
            details.append(f"Fuente: {e['fuente']}")
        item.add("description", "\n".join(details))
        cal.add_component(item)

    OUTPUT_ICS.write_bytes(cal.to_ical())

def main():
    run_motocal()
    international = parse_source_ics()
    argentina = normalize_argentina(load_argentina())
    events = dedupe_and_sort(international + argentina)

    if not events:
        raise RuntimeError(
            "Se generó el ICS de origen pero no contiene eventos. "
            "El workflow se detiene para evitar publicar un calendario vacío."
        )

    write_csv(events)
    build_output_ics(events)

    print(f"OK: {len(events)} eventos.")
    print(f"CSV: {OUTPUT_CSV}")
    print(f"ICS: {OUTPUT_ICS}")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
