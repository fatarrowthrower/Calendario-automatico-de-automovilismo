from bs4 import BeautifulSoup
from curl_cffi import requests


URL = "https://tc2000.com.ar/carreras.php?accion=historial&id=411&temp="


def main():
    print("=== INSPECCIÓN FECHA 1 TC2000 ===")
    print(f"URL: {URL}")
    print()

    response = requests.get(
        URL,
        impersonate="chrome",
        timeout=30,
    )

    print(f"HTTP: {response.status_code}")
    print(f"URL final: {response.url}")
    print(f"Bytes: {len(response.content)}")
    print()

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    print("=== TÍTULO ===")

    if soup.title:
        print(soup.title.get_text(" ", strip=True))

    print()

    print("=== TEXTO RELACIONADO CON HORARIOS ===")

    palabras = (
        "hora",
        "horario",
        "práctica",
        "entrenamiento",
        "clasificación",
        "clasificacion",
        "carrera",
        "sábado",
        "sabado",
        "domingo",
        "viernes",
    )

    encontrados = 0

    for element in soup.find_all(
        string=True
    ):
        texto = " ".join(element.split())

        if not texto:
            continue

        texto_lower = texto.lower()

        if any(
            palabra in texto_lower
            for palabra in palabras
        ):
            print(texto)
            encontrados += 1

            if encontrados >= 100:
                break

    print()
    print(f"Textos encontrados: {encontrados}")

    print()
    print("=== TABLAS ===")

    tablas = soup.find_all("table")

    print(f"Tablas encontradas: {len(tablas)}")

    for numero, tabla in enumerate(
        tablas,
        start=1,
    ):
        print()
        print(f"--- TABLA {numero} ---")
        print(
            " ".join(
                tabla.get_text(
                    " ",
                    strip=True
                ).split()
            )[:5000]
        )

    print()
    print("=== ENCABEZADOS ===")

    for tag in soup.find_all(
        ["h1", "h2", "h3", "h4"]
    ):
        texto = " ".join(
            tag.get_text(
                " ",
                strip=True
            ).split()
        )

        if texto:
            print(
                f"{tag.name.upper()}: {texto}"
            )

    print()
    print("=== FIN INSPECCIÓN ===")


if __name__ == "__main__":
    main()
