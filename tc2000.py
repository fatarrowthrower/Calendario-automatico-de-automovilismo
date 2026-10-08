from datetime import datetime
from pathlib import Path
import re

from bs4 import BeautifulSoup
from curl_cffi import requests


YEAR = datetime.now().year
URL = "https://tc2000.com.ar/carreras.php?evento=calendario"


def clean_text(text):
    return " ".join(text.split())


def main():
    print(f"=== INSPECCIÓN CALENDARIO TC2000 {YEAR} ===")
    print(f"URL: {URL}")
    print()

    response = requests.get(
        URL,
        impersonate="chrome",
        timeout=30,
    )

    print(f"HTTP: {response.status_code}")
    print(f"Bytes: {len(response.content)}")
    print()

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    print("=== TÍTULO ===")
    print(
        soup.title.get_text(" ", strip=True)
        if soup.title
        else "Sin título"
    )
    print()

    print("=== ELEMENTOS QUE CONTIENEN 'FECHA' ===")

    encontrados = 0

    for element in soup.find_all(
        string=re.compile(r"fecha", re.IGNORECASE)
    ):
        parent = element.parent

        if parent is None:
            continue

        texto = clean_text(parent.get_text(" ", strip=True))

        if not texto:
            continue

        print()
        print(f"TAG: {parent.name}")
        print(f"TEXTO: {texto}")

        # Mostramos el HTML del elemento y su contenedor
        # para descubrir cómo está armado el calendario.
        print("HTML ELEMENTO:")
        print(str(parent)[:2000])

        if parent.parent is not None:
            print("HTML PADRE:")
            print(str(parent.parent)[:4000])

        encontrados += 1

        if encontrados >= 20:
            break

    print()
    print(f"Elementos mostrados: {encontrados}")

    print()
    print("=== TABLAS ===")

    tablas = soup.find_all("table")

    print(f"Cantidad de tablas: {len(tablas)}")

    for i, tabla in enumerate(tablas[:10], start=1):
        print()
        print(f"--- TABLA {i} ---")
        print(clean_text(tabla.get_text(" ", strip=True))[:3000])

    print()
    print("=== ENLACES DEL CALENDARIO ===")

    for link in soup.find_all("a", href=True):
        texto = clean_text(link.get_text(" ", strip=True))
        href = link.get("href", "")

        contenido = f"{texto} {href}".lower()

        if any(
            palabra in contenido
            for palabra in (
                "fecha",
                "calendario",
                "carrera",
                "san juan",
                "junin",
                "toay",
                "salta",
                "nicolas",
            )
        ):
            print(f"TEXTO: {texto}")
            print(f"HREF:  {href}")
            print()

    print("=== FIN INSPECCIÓN ===")


if __name__ == "__main__":
    main()
