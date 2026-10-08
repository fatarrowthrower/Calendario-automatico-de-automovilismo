from bs4 import BeautifulSoup
from curl_cffi import requests


URL = "https://tc2000.com.ar/carreras.php?accion=cronograma&id=411"


def main():
    print("=== INSPECCIÓN TÉCNICA CRONOGRAMA TC2000 ===")
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

    print("=== IFRAMES ===")

    iframes = soup.find_all("iframe")

    print(f"Cantidad: {len(iframes)}")

    for iframe in iframes:
        print(
            "SRC:",
            iframe.get("src"),
        )

    print()

    print("=== SCRIPTS ===")

    scripts = soup.find_all("script")

    print(f"Cantidad: {len(scripts)}")

    for script in scripts:
        src = script.get("src")

        if src:
            print(f"SRC: {src}")

        contenido = script.get_text(
            " ",
            strip=True,
        )

        if contenido:
            texto = contenido.lower()

            if any(
                palabra in texto
                for palabra in (
                    "cronograma",
                    "ajax",
                    "schedule",
                    "horario",
                    "411",
                )
            ):
                print()
                print("SCRIPT RELEVANTE:")
                print(contenido[:5000])

    print()

    print("=== ENLACES RELACIONADOS ===")

    for link in soup.find_all(
        "a",
        href=True,
    ):
        texto = link.get_text(
            " ",
            strip=True,
        )

        href = link.get("href", "")

        contenido = (
            f"{texto} {href}"
        ).lower()

        if any(
            palabra in contenido
            for palabra in (
                "cronograma",
                "horario",
                "tiempo",
                "411",
            )
        ):
            print(
                f"TEXTO: {texto}"
            )
            print(
                f"HREF: {href}"
            )

    print()

    print("=== HTML QUE CONTIENE 'CRONOGRAMA' ===")

    html = response.text

    posicion = html.lower().find(
        "cronograma"
    )

    if posicion >= 0:
        inicio = max(
            0,
            posicion - 5000,
        )

        fin = min(
            len(html),
            posicion + 10000,
        )

        print(
            html[inicio:fin]
        )
    else:
        print(
            "No se encontró 'cronograma' "
            "en el HTML."
        )

    print()
    print("=== FIN INSPECCIÓN ===")


if __name__ == "__main__":
    main()
