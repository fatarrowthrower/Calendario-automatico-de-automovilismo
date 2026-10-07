from datetime import datetime
from curl_cffi import requests
from bs4 import BeautifulSoup


URL = "https://www.tc2000.com.ar/"
YEAR = datetime.now().year


def main():
    print(f"=== DESCUBRIMIENTO TC2000 {YEAR} ===")
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
    print(soup.title.get_text(" ", strip=True) if soup.title else "Sin título")
    print()

    print("=== ENLACES RELACIONADOS ===")

    encontrados = set()

    palabras = (
        "calend",
        "fecha",
        "cronograma",
        "horario",
        "tc2000",
    )

    for link in soup.find_all("a", href=True):
        texto = link.get_text(" ", strip=True)
        href = link.get("href", "").strip()

        contenido = f"{texto} {href}".lower()

        if any(palabra in contenido for palabra in palabras):
            clave = (texto, href)

            if clave not in encontrados:
                encontrados.add(clave)
                print(f"TEXTO: {texto}")
                print(f"HREF:  {href}")
                print()

    print("=== ENCABEZADOS RELACIONADOS ===")

    for tag in soup.find_all(["h1", "h2", "h3"]):
        texto = tag.get_text(" ", strip=True)

        if any(
            palabra in texto.lower()
            for palabra in (
                "calend",
                "fecha",
                "cronograma",
                "tc2000",
                "2026",
                "2027",
            )
        ):
            print(f"{tag.name.upper()}: {texto}")

    print()
    print("=== TEXTO CON FECHAS / CALENDARIO ===")

    texto_completo = soup.get_text("\n", strip=True)

    lineas = texto_completo.splitlines()

    mostradas = 0

    for linea in lineas:
        linea = " ".join(linea.split())

        if not linea:
            continue

        linea_lower = linea.lower()

        if any(
            palabra in linea_lower
            for palabra in (
                "calendario",
                "fecha 1",
                "fecha 2",
                "fecha 3",
                "fecha 4",
                "fecha 5",
                "fecha 6",
                "fecha 7",
                "fecha 8",
                "fecha 9",
                "fecha 10",
                "fecha 11",
                "fecha 12",
                "2026",
                "2027",
            )
        ):
            print(linea)
            mostradas += 1

            if mostradas >= 100:
                break

    print()
    print("=== FIN DEL DESCUBRIMIENTO ===")


if __name__ == "__main__":
    main()
