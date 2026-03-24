import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import re
import threading
import unicodedata
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

import easyocr
import pandas as pd


warnings.filterwarnings(
    "ignore",
    message=r".*pin_memory.*no accelerator is found.*",
    category=UserWarning,
)


LINE_PREFIX_RE = re.compile(
    r"^\d{1,2}/\d{1,2}/\d{2,4},\s+\d{1,2}:\d{2}(?:\s?[ap]\.?\s?m\.?)?\s+-\s+",
    re.IGNORECASE,
)
LINE_DATE_RE = re.compile(
    r"^(\d{1,2}/\d{1,2}/\d{2,4}),\s+\d{1,2}:\d{2}(?:\s?[ap]\.?\s?m\.?)?\s+-\s+",
    re.IGNORECASE,
)
RUT_RE = re.compile(r"(?<!\d)(\d{1,2}\.?\d{3}\.?\d{3}-?[\dkK])(?!\w)")
NAME_FIELD_RE = re.compile(
    r"(?i)\bnombre(?:s)?\b\s*[:\-]?\s*(.+?)(?=(?:\brut\b|$))"
)
WORD_RE = re.compile(r"\b[^\W\d_]+\b", re.UNICODE)

STOP_WORDS = {
    "hola",
    "favor",
    "por",
    "para",
    "registro",
    "registrar",
    "enrolar",
    "enrolamiento",
    "nombre",
    "nombres",
    "rut",
    "persona",
    "personas",
}

ID_NOISE_WORDS = {
    "republica",
    "chile",
    "cedula",
    "identidad",
    "documento",
    "nacionalidad",
    "nacional",
    "sexo",
    "firma",
    "fecha",
    "nacimiento",
    "vencimiento",
    "serie",
    "numero",
    "run",
    "rut",
    "nombres",
    "apellidos",
}


@dataclass
class PersonRecord:
    nombre: str
    apellido: str
    rut: str


_EASYOCR_READER: Optional[easyocr.Reader] = None
_THREAD_LOCAL = threading.local()
OCR_CACHE_FILE = ".ocr_cache.json"


def calculate_rut_dv(number_part: str) -> str:
    total = 0
    multiplier = 2

    for digit in reversed(number_part):
        total += int(digit) * multiplier
        multiplier += 1
        if multiplier > 7:
            multiplier = 2

    remainder = 11 - (total % 11)
    if remainder == 11:
        return "0"
    if remainder == 10:
        return "K"
    return str(remainder)


def normalize_rut(raw_rut: str) -> Optional[str]:
    cleaned = re.sub(r"[^\dkK]", "", raw_rut)
    if len(cleaned) < 2:
        return None

    number_part = cleaned[:-1]
    dv = cleaned[-1].upper()

    if not number_part.isdigit() or not (dv.isdigit() or dv == "K"):
        return None

    number_part = str(int(number_part))
    if calculate_rut_dv(number_part) != dv:
        return None

    return f"{number_part}-{dv}"


def parse_line_message(line: str) -> str:
    line = line.strip()
    line = LINE_PREFIX_RE.sub("", line)

    if ": " in line:
        _, message = line.split(": ", 1)
        return message.strip()

    return line


def parse_line_date(line: str) -> Optional[datetime]:
    match = LINE_DATE_RE.match(line.strip())
    if not match:
        return None

    date_str = match.group(1)
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def normalize_word(word: str) -> str:
    normalized = unicodedata.normalize("NFD", word)
    normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return normalized.lower()


def clean_name_tokens(raw_text: str, extra_stop_words: Optional[set[str]] = None) -> List[str]:
    stop_words = set(STOP_WORDS)
    if extra_stop_words:
        stop_words.update(extra_stop_words)

    cleaned: List[str] = []
    for token in WORD_RE.findall(raw_text):
        normalized = normalize_word(token)
        if len(normalized) < 2:
            continue
        if normalized in stop_words:
            continue
        cleaned.append(token.title())

    return cleaned


def extract_labeled_field(text: str, label_pattern: str) -> Optional[str]:
    lines = [line.strip() for line in text.splitlines()]

    for i, line in enumerate(lines):
        if not line:
            continue

        match = re.search(label_pattern, line, re.IGNORECASE)
        if not match:
            continue

        after_label = line[match.end() :].lstrip(" :-")
        if after_label:
            return after_label

        for next_line in lines[i + 1 :]:
            if next_line:
                return next_line
            
    return None


def extract_name_from_text(text: str, rut_match: str) -> Optional[str]:
    name_field = NAME_FIELD_RE.search(text)
    candidate_text = name_field.group(1) if name_field else text

    candidate_text = candidate_text.replace(rut_match, " ")
    candidate_text = re.sub(r"(?i)\brut\b\s*[:\-]?", " ", candidate_text)
    candidate_text = re.sub(r"[|,;]", " ", candidate_text)

    words = clean_name_tokens(candidate_text)

    if len(words) < 2:
        return None

    return " ".join(words)


def split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0].title(), ""

    nombre = parts[0].title()
    apellido = " ".join(parts[1:]).title()
    return nombre, apellido


def extract_record_from_text(text: str) -> Optional[PersonRecord]:
    rut_match_obj = RUT_RE.search(text)
    if not rut_match_obj:
        return None

    rut_match = rut_match_obj.group(1)
    rut = normalize_rut(rut_match)
    if not rut:
        return None

    full_name = extract_name_from_text(text, rut_match)
    if not full_name:
        return None

    nombre, apellido = split_name(full_name)
    if not nombre:
        return None

    return PersonRecord(nombre=nombre, apellido=apellido, rut=rut)


def extract_record_from_id_text(text: str) -> Optional[PersonRecord]:
    rut_match_obj = RUT_RE.search(text)
    if not rut_match_obj:
        return None

    rut = normalize_rut(rut_match_obj.group(1))
    if not rut:
        return None

    nombres_raw = extract_labeled_field(text, r"\bnombres?\b")
    apellidos_raw = extract_labeled_field(text, r"\bapellidos?\b")

    if nombres_raw and apellidos_raw:
        nombre_tokens = clean_name_tokens(nombres_raw, extra_stop_words=ID_NOISE_WORDS)
        apellido_tokens = clean_name_tokens(apellidos_raw, extra_stop_words=ID_NOISE_WORDS)

        if nombre_tokens and apellido_tokens and len(nombre_tokens) <= 4 and len(apellido_tokens) <= 4:
            nombre = " ".join(nombre_tokens)
            apellido = " ".join(apellido_tokens)
            return PersonRecord(nombre=nombre, apellido=apellido, rut=rut)

    return None


def extract_records(lines: Iterable[str], since_date: Optional[datetime] = None) -> List[PersonRecord]:
    records_by_rut: dict[str, PersonRecord] = {}

    for raw_line in lines:
        line_date = parse_line_date(raw_line)
        if since_date and line_date and line_date.date() < since_date.date():
            continue

        message = parse_line_message(raw_line)
        record = extract_record_from_text(message)
        if not record:
            continue

        records_by_rut[record.rut] = record

    return list(records_by_rut.values())


def get_easyocr_reader() -> easyocr.Reader:
    reader = getattr(_THREAD_LOCAL, "easyocr_reader", None)
    if reader is None:
        reader = easyocr.Reader(["es"], gpu=False, verbose=False)
        _THREAD_LOCAL.easyocr_reader = reader
    return reader


def ocr_image_to_text(image_path: Path) -> str:
    reader = get_easyocr_reader()
    lines = reader.readtext(str(image_path), detail=0, paragraph=False, decoder="greedy", beamWidth=1)
    return "\n".join(lines)


def get_image_cache_key(image_path: Path) -> Optional[str]:
    try:
        stat = image_path.stat()
    except OSError:
        return None
    return f"{image_path.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"


def load_ocr_cache(cache_path: Path) -> dict[str, str]:
    if not cache_path.exists():
        return {}

    try:
        with cache_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(data, dict):
        return {}

    return {str(k): str(v) for k, v in data.items()}


def save_ocr_cache(cache_path: Path, cache: dict[str, str]) -> None:
    try:
        with cache_path.open("w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except OSError:
        # No interrumpir el flujo principal si falla el cache.
        return


def process_image_with_ocr(image_path: Path) -> Optional[str]:
    try:
        return ocr_image_to_text(image_path)
    except Exception:
        return None


def extract_records_from_images(images_dir: Path, ocr_workers: int = 1) -> List[PersonRecord]:
    records_by_rut: dict[str, PersonRecord] = {}
    cache_path = images_dir / OCR_CACHE_FILE
    ocr_cache = load_ocr_cache(cache_path)
    used_cache_keys: set[str] = set()
    cache_updated = False

    image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
    image_paths = [p for p in images_dir.rglob("*") if p.suffix.lower() in image_extensions]

    uncached: list[tuple[Path, str]] = []

    for image_path in image_paths:
        cache_key = get_image_cache_key(image_path)
        if not cache_key:
            continue

        used_cache_keys.add(cache_key)

        text = ocr_cache.get(cache_key)
        if text is None:
            uncached.append((image_path, cache_key))
            continue

        record = extract_record_from_id_text(text)
        if not record:
            continue

        records_by_rut[record.rut] = record

    if uncached:
        max_workers = max(1, ocr_workers)
        if max_workers == 1:
            for image_path, cache_key in uncached:
                text = process_image_with_ocr(image_path)
                if text is None:
                    continue
                ocr_cache[cache_key] = text
                cache_updated = True

                record = extract_record_from_id_text(text)
                if not record:
                    continue

                records_by_rut[record.rut] = record
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_meta = {
                    executor.submit(process_image_with_ocr, image_path): (image_path, cache_key)
                    for image_path, cache_key in uncached
                }

                for future in as_completed(future_to_meta):
                    _, cache_key = future_to_meta[future]
                    text = future.result()
                    if text is None:
                        continue

                    ocr_cache[cache_key] = text
                    cache_updated = True

                    record = extract_record_from_id_text(text)
                    if not record:
                        continue

                    records_by_rut[record.rut] = record

    # Limpia entradas antiguas para que el cache no crezca indefinidamente.
    stale_keys = [k for k in ocr_cache if k not in used_cache_keys]
    if stale_keys:
        for key in stale_keys:
            ocr_cache.pop(key, None)
        cache_updated = True

    if cache_updated:
        save_ocr_cache(cache_path, ocr_cache)

    return list(records_by_rut.values())


def save_to_excel(records: List[PersonRecord], output_path: Path) -> None:
    df = pd.DataFrame(
        [{"Nombre": r.nombre, "Apellido": r.apellido, "Rut": r.rut} for r in records]
    )

    if not df.empty:
        df = df.sort_values(by=["Apellido", "Nombre"]).reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(output_path, index=False)


def parse_cli_date(date_str: str) -> datetime:
    try:
        return datetime.strptime(date_str, "%d/%m/%Y")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "El parametro --since-date debe tener formato DD/MM/AAAA"
        ) from exc


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extrae nombre, apellido y RUT desde un chat exportado de WhatsApp y crea un Excel."
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Ruta al archivo TXT exportado del chat de WhatsApp.",
    )
    parser.add_argument(
        "--output",
        default=Path("personas.xlsx"),
        type=Path,
        help="Ruta del archivo Excel de salida.",
    )
    parser.add_argument(
        "--since-date",
        type=parse_cli_date,
        default=None,
        help="Fecha minima para filtrar mensajes del chat (formato DD/MM/AAAA).",
    )
    parser.add_argument(
        "--images-dir",
        type=Path,
        default=None,
        help="Carpeta con fotos de carnet para extraer datos por OCR.",
    )
    parser.add_argument(
        "--ocr-workers",
        type=int,
        default=1,
        help="Cantidad de workers para OCR de imagenes (1 = sin paralelismo).",
    )

    args = parser.parse_args()
    since_date = args.since_date

    if not args.input.exists():
        parser.error(f"No se encontro el archivo de entrada: {args.input}")

    with args.input.open("r", encoding="utf-8-sig", errors="ignore") as f:
        records = extract_records(f, since_date=since_date)

    if args.images_dir:
        if not args.images_dir.exists() or not args.images_dir.is_dir():
            parser.error(f"No se encontro la carpeta de imagenes: {args.images_dir}")

        if args.ocr_workers < 1:
            parser.error("El parametro --ocr-workers debe ser mayor o igual a 1")

        image_records = extract_records_from_images(args.images_dir, ocr_workers=args.ocr_workers)
        records_by_rut = {r.rut: r for r in records}
        for record in image_records:
            records_by_rut[record.rut] = record
        records = list(records_by_rut.values())

    save_to_excel(records, args.output)

    print(f"Registros encontrados: {len(records)}")
    print(f"Archivo generado: {args.output.resolve()}")


if __name__ == "__main__":
    main()
