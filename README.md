# WhatsApp RUT Extractor

Convierte un chat exportado de WhatsApp y fotos de carnet en un archivo Excel con personas registradas.

Ideal para cuando necesitas consolidar datos de forma rapida, sin copiar y pegar manualmente.

## Que hace

- Lee un archivo TXT exportado desde WhatsApp.
- Detecta RUT, nombre y apellido en los mensajes.
- Opcionalmente procesa imagenes de carnet con OCR (EasyOCR).
- Genera un Excel con columnas: `Nombre`, `Apellido`, `Rut`.
- Elimina duplicados por RUT (mantiene el ultimo registro encontrado).

## Requisitos

- Python 3.10 o superior.
- Dependencias en `requirements.txt`.

## Instalacion

1. Clona este repositorio.
2. Entra a la carpeta del proyecto.
3. Instala dependencias:

```powershell
pip install -r requirements.txt
```

## Uso rapido

### 1) Exporta el chat de WhatsApp

1. Abre el chat en WhatsApp.
2. Ve a `Menu > Mas > Exportar chat`.
3. Elige `Sin archivos multimedia`.
4. Guarda el TXT (por ejemplo, `chat.txt`) en tu equipo.

### 2) Ejecuta el script

Solo chat TXT:

```powershell
python parse_whatsapp_to_excel.py --input chat.txt --output personas.xlsx
```

Chat + imagenes de carnet:

```powershell
python parse_whatsapp_to_excel.py --input chat.txt --images-dir imagenes_carnet --output personas.xlsx
```

Chat + imagenes de carnet con OCR paralelo (lotes grandes):

```powershell
python parse_whatsapp_to_excel.py --input chat.txt --images-dir imagenes_carnet --output personas.xlsx --ocr-workers 4
```

Con filtro por fecha minima:

```powershell
python parse_whatsapp_to_excel.py --input chat.txt --output personas.xlsx --since-date 16/03/2026
```

## Argumentos disponibles

- `--input` (obligatorio): ruta al TXT exportado de WhatsApp.
- `--output` (opcional): ruta del Excel de salida. Por defecto: `personas.xlsx`.
- `--since-date` (opcional): filtra mensajes desde una fecha minima (`DD/MM/AAAA`).
- `--images-dir` (opcional): carpeta con imagenes de carnet para OCR.
- `--ocr-workers` (opcional): cantidad de workers para OCR de imagenes. Por defecto: `1`.

## Formato de salida

Se crea un archivo Excel con:

- `Nombre`
- `Apellido`
- `Rut`

Ejemplo de entrada en chat:

```text
Nombre: Maria Jose Gonzalez Rut: 12.345.678-5
```

Ejemplo de salida:

- Nombre: Maria
- Apellido: Jose Gonzalez
- Rut: 12345678-5

## Consideraciones importantes

- El script valida el digito verificador del RUT.
- En OCR de carnet, se priorizan campos etiquetados como `NOMBRES` y `APELLIDOS` para reducir errores.
- La primera ejecucion con OCR puede tardar mas, porque EasyOCR prepara modelos.
- Se guarda un cache OCR en `imagenes_carnet/.ocr_cache.json` para acelerar ejecuciones posteriores.
- `--ocr-workers` acelera imagenes no cacheadas; un valor entre `2` y `6` suele funcionar bien en CPU.
- Si una imagen no tiene texto legible o esta borrosa, puede no extraerse ningun registro.

## Privacidad

- Los archivos de chat y fotos de carnet pueden contener datos sensibles.
- Se recomienda no subirlos al repositorio.
- La carpeta `imagenes_carnet/` esta pensada para uso local.

## Solucion de problemas

- `No se encontro el archivo de entrada`: revisa la ruta en `--input`.
- `No se encontro la carpeta de imagenes`: revisa la ruta en `--images-dir`.
- Error con `--since-date`: usa formato `DD/MM/AAAA`.

## Estructura del proyecto

```text
parse_whatsapp_to_excel.py   # Script principal
requirements.txt             # Dependencias Python
imagenes_carnet/             # Carpeta local para imagenes
```

## Licencia

MIT
