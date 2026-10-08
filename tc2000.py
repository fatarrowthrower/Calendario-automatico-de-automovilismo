from bs4 import BeautifulSoup
from curl_cffi import requests


URL = "https://tc2000.com.ar/carreras.php?accion=historial&id=411&temp="


def clean_text(text):
    return " ".join(text.split())


def main():
    print("=== INSPECCIÓN CRONOGRAMA FECHA 1 TC2000 ===")
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

    print("=== ELEMENTOS CON 'CRONOGRAMA' ===")

    encontrados = 0

    for element in soup.find_all(
        string=lambda text: (
            text is not None
            and "cronograma" in text.lower()
        )
    ):
        parent = element.parent

        if parent is None:
            continue

        print()
        print(f"TAG: {parent.name}")
        print(
            f"TEXTO: {clean_text(parent.get_text(' ', strip=True))}"
        )
        print("HTML:")
        print(str(parent)[:5000])

        if parent.parent is not None:
            print()
            print("HTML PADRE:")
            print(str(parent.parent)[:10000])

        encontrados += 1

        if encontrados >= 10:
            break

    print()
    print(f"Elementos encontrados: {encontrados}")

    print()
    print("=== ELEMENTOS CON HORARIOS ===")

    encontrados_hora = 0

    for element in soup.find_all(
        string=lambda text: (
            text is not None
            and any(
                caracter in text
                for caracter in (
                    ":00",
                    ":15",
                    ":30",
                    ":45",
                )
            )
        )
    ):
        texto = clean_text(element)

        if not texto:
            continue

        print()
        print(f"TEXTO: {texto}")
        print(f"TAG: {element.parent.name}")
        print(
            f"HTML: {str(element.parent)[:3000]}"
        )

        encontrados_hora += 1

        if encontrados_hora >= 50:
            break

    print()
    print(
        f"Elementos con posibles horarios: "
        f"{encontrados_hora}"
    )

    print()
    print("=== FIN INSPECCIÓN ===")


if __name__ == "__main__":
    main()
