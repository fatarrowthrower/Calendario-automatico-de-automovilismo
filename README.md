# 🏁 Automovilismo Auto

Calendario automático para seguir F1, F2, F3, WEC, ELMS, Le Mans Cup,
MotoGP/Moto2/Moto3 y GT World Challenge/IGTC, con extensión para categorías
argentinas.

## Qué hace

Cada día GitHub Actions ejecuta `update.py`, consulta las fuentes disponibles,
normaliza los eventos a `America/Argentina/Buenos_Aires` y genera:

- `data/events.csv`
- `output/automovilismo.ics`

El `.ics` puede publicarse con GitHub Pages y luego suscribirse desde Google
Calendar mediante "Otros calendarios → Desde URL".

## Instalación

1. Crear un repositorio de GitHub.
2. Subir todo este directorio.
3. Activar GitHub Actions.
4. Activar GitHub Pages apuntando a la rama principal.
5. Usar la URL pública del archivo `output/automovilismo.ics`.

## Categorías argentinas

Agregar eventos a `data/argentina.csv`. Encabezados:

fecha,hora_argentina,categoria,evento,sesion,circuito,pais,inicio_iso,fuente

Ejemplo:

2026-10-11,15:30,Fórmula Nacional Argentina,Fecha X,Carrera,Toay,Argentina,2026-10-11T15:30:00-03:00,Fórmula Nacional

Para evitar errores, los horarios argentinos deben ser ISO-8601 con -03:00
en `inicio_iso`.

## Importante

La automatización no asume que exista una API universal. Las fuentes de
cada campeonato se mantienen separadas para que un fallo en una categoría
no detenga las demás.
