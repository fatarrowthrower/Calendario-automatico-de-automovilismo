from bs4 import BeautifulSoup
from curl_cffi import requests


URL = "https://tc2000.com.ar/carreras.php?accion=cronograma&id=411"


def clean_text(text):
    return " ".join(text.split())


def main():
    print("=== INSPECCIÓN CRONOGRAMA TC2000 FECHA 1 ===")
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
        print(
            soup.title.get_text(
                " ",
                strip=True,
            )
        )

    print()

    print("=== TEXTO DE LA PÁGINA ===")

    texto = clean_text(
        soup.get_text(
            " ",
            strip=True,
        )
    )

    print(texto[:15000])

    print()
    print("=== TABLAS ===")

    tablas = soup.find_all("table")

    print(f"Cantidad de tablas: {len(tablas)}")

    for numero, tabla in enumerate(
        tablas,
        start=1,
    ):
        print()
        print(f"--- TABLA {numero} ---")
        print(
            clean_text(
                tabla.get_text(
                    " ",
                    strip=True,
                )
            )[:10000]
        )

    print()
    print("=== ENCABEZADOS ===")

    for tag in soup.find_all(
        [
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
        ]
    ):
        texto = clean_text(
            tag.get_text(
                " ",
                strip=True,
            )
        )

        if texto:
            print(
                f"{tag.name.upper()}: {texto}"
            )

    print()
    print("=== FIN INSPECCIÓN ===")


if __name__ == "__main__":
    main()
