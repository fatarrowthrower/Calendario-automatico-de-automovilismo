import re
from datetime import datetime
from html import unescape
from urllib.request import Request, urlopen


URL = (
    "https://aptpweb.com.ar/"
    "turismo-pista-y-actc-presentaron-el-calendario-2026-en-la-tv-publica/"
)


def fetch(url):
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(compatible; AutomovilismoCalendar/1.0)"
            )
        },
    )

    with urlopen(request, timeout=30) as response:
        return response.read().decode(
            "utf-8",
            errors="ignore",
        )


def clean_html(html):
    html = re.sub(
        r"<script\b[^>]*>.*?</script>",
        " ",
        html,
        flags=re.I | re.S,
    )

    html = re.sub(
        r"<style\b[^>]*>.*?</style>",
        " ",
        html,
        flags=re.I | re.S,
    )

    html = re.sub(
        r"<[^>]+>",
        " ",
        html,
    )

    html = unescape(html)

    html = html.replace(
        "\xa0",
        " ",
    )

    html = re.sub(
        r"\s+",
        " ",
        html,
    )

    return html.strip()


def main():

    print("Descargando artículo oficial de APTP...")
    print(URL)
    print()

    html = fetch(URL)

    print(
        f"HTML descargado: {len(html)} caracteres"
    )

    print()
    print("Buscando menciones de calendario...")

    text = clean_html(html)

    pattern = re.compile(
        r".{0,500}"
        r"(?:calendario|fecha\s+\d|"
        r"\d+\s*(?:°|º|o)?\s*fecha)"
        r".{0,1000}",
        re.I,
    )

    matches = pattern.findall(text)

    print(
        f"Bloques encontrados: {len(matches)}"
    )

    print()

    for number, block in enumerate(
        matches[:10],
        start=1,
    ):
        print(
            f"========== BLOQUE {number} =========="
        )
        print(block)
        print()

    print(
        "Fin del diagnóstico."
    )


if __name__ == "__main__":
    main()
