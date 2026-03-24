# Documentacion tecnica completa - WhatsApp RUT Extractor

## 1. Objetivo del script

`parse_whatsapp_to_excel.py` procesa dos fuentes de datos:

1. Un chat exportado de WhatsApp en formato TXT.
2. Una carpeta opcional con imagenes de carnet para OCR.

Luego genera un Excel con personas en formato:

- Nombre
- Apellido
- Rut

El script elimina duplicados por RUT y conserva el ultimo registro detectado.

---

## 2. Flujo general de ejecucion

1. Lee argumentos de linea de comandos.
2. Valida archivo de entrada y parametros.
3. Procesa el chat TXT y extrae registros de texto.
4. Si se entrega `--images-dir`, procesa imagenes con OCR.
5. Mezcla resultados (chat + imagenes), deduplicando por RUT.
6. Guarda salida en Excel (`.xlsx`).
7. Imprime total de registros y ruta final del archivo.

---

## 3. Dependencias

Definidas en `requirements.txt`:

- `pandas`: construccion y exportacion del DataFrame a Excel.
- `openpyxl`: motor para escritura de `.xlsx`.
- `easyocr`: OCR de imagenes de carnet.

Dependencias de libreria estandar usadas en el script:

- `argparse`, `datetime`, `pathlib`, `dataclasses`, `typing`
- `re`, `unicodedata`, `json`, `warnings`
- `threading`, `concurrent.futures`

---

## 4. Estructuras y constantes clave

## 4.1 Dataclass principal

`PersonRecord` representa un registro normalizado:

- `nombre: str`
- `apellido: str`
- `rut: str`

## 4.2 Regex principales

- `LINE_PREFIX_RE`: elimina prefijo de linea exportada de WhatsApp.
- `LINE_DATE_RE`: extrae fecha para aplicar filtro `--since-date`.
- `RUT_RE`: detecta candidatos de RUT con puntos y guion opcionales.
- `NAME_FIELD_RE`: detecta texto asociado a etiqueta `nombre`.
- `WORD_RE`: tokeniza solo palabras alfabeticas (sin numeros/guiones).

## 4.3 Conjuntos de palabras de ruido

- `STOP_WORDS`: palabras comunes a excluir al limpiar nombres desde chat.
- `ID_NOISE_WORDS`: ruido especifico de cedula/carnet para OCR.

## 4.4 Cache OCR

- `OCR_CACHE_FILE = ".ocr_cache.json"`
- Se guarda dentro de la carpeta de imagenes (`--images-dir`).

---

## 5. Modulo de RUT

## 5.1 `calculate_rut_dv(number_part: str) -> str`

Calcula digito verificador chileno (modulo 11) usando multiplicadores ciclicos 2..7.

## 5.2 `normalize_rut(raw_rut: str) -> Optional[str>`

Normaliza y valida RUT:

1. Limpia caracteres no validos.
2. Separa cuerpo numerico y DV.
3. Valida formato base.
4. Recalcula DV y compara.
5. Devuelve `numero-dv` (ejemplo: `12345678-5`) o `None`.

Impacto: evita falsos positivos de OCR/chat con RUT invalido.

---

## 6. Extraccion desde chat TXT

## 6.1 Parseo de lineas

- `parse_line_date`: intenta leer fecha de la linea con formatos `%d/%m/%Y` y `%d/%m/%y`.
- `parse_line_message`: quita metadata de WhatsApp (`fecha, hora - usuario:`) y deja solo mensaje.

## 6.2 Limpieza de texto para nombres

`extract_name_from_text`:

1. Prioriza segmento despues de `nombre` si existe.
2. Elimina RUT y etiqueta `rut`.
3. Limpia separadores comunes.
4. Tokeniza y filtra palabras de ruido.
5. Requiere al menos 2 tokens.

## 6.3 Separacion nombre/apellido

`split_name` aplica regla simple:

- Primer token => `Nombre`
- Resto => `Apellido`

## 6.4 Extraccion por linea

`extract_record_from_text`:

1. Busca RUT
2. Valida RUT
3. Obtiene nombre completo
4. Separa en nombre y apellido
5. Retorna `PersonRecord` o `None`

## 6.5 Recorrido del archivo

`extract_records(lines, since_date)`:

- Itera lineas del TXT.
- Aplica filtro por fecha si corresponde.
- Deduplica por RUT usando diccionario.

---

## 7. Extraccion desde imagenes (OCR)

## 7.1 Reader de EasyOCR por hilo

`get_easyocr_reader` usa `threading.local()` para tener un reader por worker y evitar conflictos.

Configuracion actual:

- Idioma: `es`
- `gpu=False`
- `verbose=False`

## 7.2 OCR por imagen

`ocr_image_to_text` usa parametros de velocidad:

- `detail=0`
- `paragraph=False`
- `decoder="greedy"`
- `beamWidth=1`

## 7.3 Extraccion estricta para carnet

`extract_record_from_id_text`:

1. Exige RUT valido.
2. Busca campos etiquetados `NOMBRES` y `APELLIDOS`.
3. Limpia tokens con `ID_NOISE_WORDS`.
4. Limita tokens por campo para evitar texto basura.
5. Si no cumple, devuelve `None`.

Nota: no usa fallback generico para carnet, para priorizar precision.

## 7.4 Cache OCR persistente

Funciones:

- `get_image_cache_key`: clave por ruta absoluta + tamano + mtime.
- `load_ocr_cache`: carga JSON si existe y es valido.
- `save_ocr_cache`: guarda JSON sin romper flujo si falla escritura.

Comportamiento:

- Imagen sin cambios: reutiliza OCR cacheado.
- Imagen nueva/modificada: recalcula OCR y actualiza cache.
- Limpia entradas obsoletas para evitar crecimiento infinito.

## 7.5 Paralelismo configurable

`extract_records_from_images(images_dir, ocr_workers=1)`:

- Si `ocr_workers=1`: procesamiento secuencial.
- Si `ocr_workers>1`: usa `ThreadPoolExecutor` para imagenes no cacheadas.
- Imagenes ya cacheadas no se recalculan.

---

## 8. CLI (argumentos)

- `--input` (obligatorio): ruta del TXT exportado.
- `--output` (opcional): ruta del Excel de salida. Default: `personas.xlsx`.
- `--since-date` (opcional): fecha minima `DD/MM/AAAA`.
- `--images-dir` (opcional): carpeta con imagenes para OCR.
- `--ocr-workers` (opcional): workers de OCR, minimo 1. Default: 1.

Ejemplos:

```powershell
python parse_whatsapp_to_excel.py --input chat.txt --output personas.xlsx
python parse_whatsapp_to_excel.py --input chat.txt --images-dir imagenes_carnet --output personas.xlsx
python parse_whatsapp_to_excel.py --input chat.txt --images-dir imagenes_carnet --output personas.xlsx --ocr-workers 4
python parse_whatsapp_to_excel.py --input chat.txt --output personas.xlsx --since-date 16/03/2026
```

---

## 9. Validaciones y manejo de errores

- Error CLI si `--input` no existe.
- Error CLI si `--images-dir` no existe o no es carpeta.
- Error CLI si `--ocr-workers < 1`.
- Error de tipo amigable para `--since-date` con formato invalido.
- OCR por imagen protegido con `try/except` para no detener lote completo.
- Escritura de cache protegida para no romper proceso principal.

---

## 10. Warnings y salida de consola

Se silencia este warning repetitivo de PyTorch/EasyOCR en CPU:

- `pin_memory argument is set as true but no accelerator is found`

Salida normal al terminar:

- `Registros encontrados: <N>`
- `Archivo generado: <ruta absoluta>`

---

## 11. Formato de salida Excel

Se crea DataFrame con columnas:

- `Nombre`
- `Apellido`
- `Rut`

Si hay datos, se ordena por:

1. `Apellido`
2. `Nombre`

Luego se exporta a `xlsx` sin indice.

---

## 12. Rendimiento

Fuentes principales de costo:

1. OCR de imagenes no cacheadas.
2. Inicializacion de modelos de EasyOCR (primera corrida).

Estrategias implementadas:

- Cache OCR persistente por metadata de archivo.
- OCR paralelo configurable (`--ocr-workers`).
- Parametros de inferencia orientados a velocidad.
- Reader por hilo para paralelismo seguro.

Recomendaciones:

- Usa `--ocr-workers` entre 2 y 6 en CPU.
- Reutiliza siempre la misma carpeta de imagenes para aprovechar cache.
- Evita reprocesar imagenes borrosas o con texto fuera de foco.

---

## 13. Privacidad y seguridad de datos

Este proyecto trabaja con informacion sensible (RUT, nombres, fotos de carnet).

Buenas practicas:

- No subir `chat.txt` ni imagenes reales al repositorio.
- Mantener `imagenes_carnet/` y archivos de salida en entorno controlado.
- Compartir `personas.xlsx` solo con quienes corresponda.

---

## 14. Limitaciones conocidas

- La separacion nombre/apellido usa una heuristica simple.
- OCR depende de calidad de imagen, iluminacion y enfoque.
- Si el carnet no contiene etiquetas detectables (`NOMBRES`/`APELLIDOS`), el registro puede descartarse.
- El parser del chat asume formato tipico de exportacion de WhatsApp.