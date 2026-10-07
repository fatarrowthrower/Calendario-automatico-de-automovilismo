#!/usr/bin/env python3
"""
Automovilismo Auto
Actualiza calendarios y genera:
  - data/events.csv
  - output/automovilismo.ics

Las fuentes estructuradas provienen de motorsport-calendar.
Las categorías argentinas pueden agregarse a data/argentina.csv con el mismo
formato del CSV generado por este proyecto.

Ejecutar:
    python update.py
"""
from pathlib import Path
import subprocess
import csv
import re
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "output"
DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

YEAR = 2026
TZ = ZoneInfo("America/Argentina/Buenos_Aires")
ICS = OUT / "automovilismo.ics"

providers = [
    ("f1", "F1"), ("f2", "F2"), ("f3", "F3"),
    ("wec", "WEC"), ("elms", "ELMS"), ("mlmc", "Le Mans Cup"),
    ("motogp", "MotoGP"), ("moto2", "Moto2"), ("moto3", "Moto3"),
    ("gtwc-europe", "GT World Challenge Europe"),
    ("gtwc-america", "GT World Challenge America"),
    ("gtwc-asia", "GT World Challenge Asia"),
    ("igtc", "Intercontinental GT Challenge"),
]

def run_provider(pid, label):
    target = DATA / f"{pid}.ics"
    cmd = ["motocal", f"generate-{pid}", str(YEAR), str(target), "--refresh"]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        return target
    except Exception as e:
        print(f"[WARN] {label}: {e}")
        return None

def parse_ics(path, championship):
    # Minimal RFC5545 parser for VEVENT fields emitted by motocal.
    text = path.read_text(encoding="utf-8", errors="ignore")
    blocks = re.split(r"BEGIN:VEVENT", text)[1:]
    events = []
    for block in blocks:
        fields = {}
        for line in block.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fields[k] = v.strip()
        if "SUMMARY" not in fields or "DTSTART" not in fields:
            continue
        dt = fields["DTSTART"]
        # Handle UTC timestamps and floating timestamps.
        try:
            if dt.endswith("Z"):
                d = datetime.strptime(dt[:-1], "%Y%m%dT%H%M%S").replace(tzinfo=ZoneInfo("UTC")).astimezone(TZ)
            elif "T" in dt:
                d = datetime.strptime(dt[:15], "%Y%m%dT%H%M%S").replace(tzinfo=TZ)
            else:
                d = datetime.strptime(dt[:8], "%Y%m%d").replace(tzinfo=TZ)
            events.append({
                "fecha": d.strftime("%Y-%m-%d"),
                "hora_argentina": "" if "T" not in dt else d.strftime("%H:%M"),
                "categoria": championship,
                "evento": fields.get("SUMMARY",""),
                "sesion": "",
                "circuito": "",
                "pais": "",
                "inicio_iso": d.isoformat(),
                "fuente": "motorsport-calendar",
            })
        except Exception:
            pass
    return events

def load_argentina():
    p = DATA / "argentina.csv"
    if not p.exists():
        return []
    with p.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def write_csv(events):
    import pandas as pd
    df = pd.DataFrame(events)
    if df.empty:
        return
    df["inicio_dt"] = pd.to_datetime(df["inicio_iso"], errors="coerce")
    df = df.sort_values("inicio_dt").drop(columns=["inicio_dt"])
    df.to_csv(DATA / "events.csv", index=False, encoding="utf-8-sig")

def build_ics(events):
    # Uses icalendar for standards-compliant output.
    from icalendar import Calendar, Event
    from datetime import timedelta
    cal = Calendar()
    cal.add("prodid", "-//Automovilismo Auto//AR//")
    cal.add("version", "2.0")
    cal.add("X-WR-CALNAME", "🏁 Automovilismo — Argentina")
    cal.add("X-WR-TIMEZONE", "America/Argentina/Buenos_Aires")
    for i, e in enumerate(events):
        if not e.get("inicio_iso"):
            continue
        try:
            start = datetime.fromisoformat(e["inicio_iso"])
        except Exception:
            continue
        ev = Event()
        ev.add("uid", f"auto-{start.strftime('%Y%m%d%H%M')}-{i}@automovilismo-auto")
        ev.add("dtstart", start)
        ev.add("dtend", start + timedelta(minutes=90))
        ev.add("summary", f"{e.get('categoria','')} — {e.get('evento','')}")
        desc = f"Sesión: {e.get('sesion','')}\nFuente: {e.get('fuente','')}"
        ev.add("description", desc)
        cal.add_component(ev)
    ICS.write_bytes(cal.to_ical())

def main():
    all_events = []
    for pid, label in providers:
        p = run_provider(pid, label)
        if p and p.exists():
            all_events.extend(parse_ics(p, label))
    all_events.extend(load_argentina())
    write_csv(all_events)
    build_ics(all_events)
    print(f"OK: {len(all_events)} eventos. {ICS}")

if __name__ == "__main__":
    main()
