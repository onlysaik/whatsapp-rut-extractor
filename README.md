# WspImport — Automatizar WhatsApp a Excel

> Extrae nombres y RUTs desde chats exportados de WhatsApp y/o fotos de carnet, y genera un archivo Excel listo para usar.

## Estructura del proyecto

```
parse_whatsapp_to_excel.py   # Script principal
requirements.txt             # Dependencias Python
imagenes_carnet/             # Carpeta para fotos de carnet (no se sube al repo)
```

---

Este script toma un chat exportado de WhatsApp (TXT), detecta registros con nombre y RUT, y crea un Excel con columnas:

- Nombre
- Apellido
- Rut

## 1) Exportar chat de WhatsApp

1. En WhatsApp abre el chat.
2. Menu > Mas > Exportar chat.
3. Elige "Sin archivos multimedia".
4. Guarda el archivo TXT en este proyecto (por ejemplo `chat.txt`).

## 2) Instalar dependencias

En PowerShell, dentro de esta carpeta:

```powershell
pip install -r requirements.txt
```

## 3) Ejecutar

```powershell
python parse_whatsapp_to_excel.py --input chat.txt --output personas.xlsx --since-date 16/03/2026
```

Si tambien quieres leer fotos de carnet desde una carpeta (`imagenes_carnet`):

```powershell
python parse_whatsapp_to_excel.py --input chat.txt --images-dir imagenes_carnet --output personas.xlsx --since-date 16/03/2026
```

## 3.1) OCR con EasyOCR

La lectura de imagenes ahora usa `EasyOCR`.

- No necesita `tesseract.exe`.
- No necesita configurar `PATH` en Windows.
- Basta con instalar lo de `requirements.txt`.

## 4) Resultado

Se crea `personas.xlsx` con las columnas `Nombre`, `Apellido`, `Rut`.

## Notas

- Si un RUT aparece repetido, se deja el ultimo registro encontrado.
- El script intenta detectar lineas con formato tipico de WhatsApp exportado.
- El filtro `--since-date` aplica a los mensajes del chat TXT.
- Para nombres compuestos, se guarda:
  - Nombre: primera palabra
  - Apellido: resto del nombre
- Para imagenes de carnet, EasyOCR intenta detectar campos `NOMBRES`, `APELLIDOS` y `RUT`.
- La primera ejecucion con OCR puede tardar mas porque EasyOCR descarga o prepara sus modelos.

## Ejemplo rapido

Mensaje en chat:

```text
Nombre: Maria Jose Gonzalez Rut: 12.345.678-5
```

Resultado en Excel:

- Nombre: Maria
- Apellido: Jose Gonzalez
- Rut: 12345678-5

## Privacidad

Las fotos de carnet y los archivos de chat **no se suben al repositorio** (están excluidos por `.gitignore`).
La carpeta `imagenes_carnet/` existe en el repo pero su contenido es ignorado.

## Licencia

MIT
