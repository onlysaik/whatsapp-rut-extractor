import argparse
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

import easyocr
import pandas as pd


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
ID_NAMES_RE = re.compile(r"(?i)\bnombres?\b\s*[:\-]?\s*([^\n\r]+)")
ID_LASTNAMES_RE = re.compile(r"(?i)\bapellidos?\b\s*[:\-]?\s*([^\n\r]+)")
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


@dataclass
class PersonRecord:
    nombre: str
    apellido: str
    rut: str


_EASYOCR_READER: Optional[easyocr.Reader] = None


def normalize_rut(raw_rut: str) -> Optional[str]:
    cleaned = re.sub(r"[^\dkK]", "", raw_rut)
    if len(cleaned) < 2:
        return None

    number_part = cleaned[:-1]
    dv = cleaned[-1].upper()

    if not number_part.isdigit() or not (dv.isdigit() or dv == "K"):
        return None

    number_part = str(int(number_part))
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


def extract_name_from_text(text: str, rut_match: str) -> Optional[str]:
    name_field = NAME_FIELD_RE.search(text)
    candidate_text = name_field.group(1) if name_field else text

    candidate_text = candidate_text.replace(rut_match, " ")
    candidate_text = re.sub(r"(?i)\brut\b\s*[:\-]?", " ", candidate_text)
    candidate_text = re.sub(r"[|,;]", " ", candidate_text)

    words = [w for w in WORD_RE.findall(candidate_text) if w.lower() not in STOP_WORDS]

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

    names_match = ID_NAMES_RE.search(text)
    lastnames_match = ID_LASTNAMES_RE.search(text)

    if names_match and lastnames_match:
        nombre = " ".join(WORD_RE.findall(names_match.group(1))).title()
        apellido = " ".join(WORD_RE.findall(lastnames_match.group(1))).title()
        if nombre:
            return PersonRecord(nombre=nombre, apellido=apellido, rut=rut)

    generic = extract_record_from_text(text)
    if generic:
        return generic

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
    global _EASYOCR_READER

    if _EASYOCR_READER is None:
        _EASYOCR_READER = easyocr.Reader(["es", "en"], gpu=False, verbose=False)

    return _EASYOCR_READER


def ocr_image_to_text(image_path: Path) -> str:
    reader = get_easyocr_reader()
    lines = reader.readtext(str(image_path), detail=0, paragraph=True)
    return "\n".join(lines)


def extract_records_from_images(images_dir: Path) -> List[PersonRecord]:
    records_by_rut: dict[str, PersonRecord] = {}

    image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
    image_paths = [p for p in images_dir.rglob("*") if p.suffix.lower() in image_extensions]

    for image_path in image_paths:
        try:
            text = ocr_image_to_text(image_path)
        except Exception:
            continue

        record = extract_record_from_id_text(text)
        if not record:
            continue

        records_by_rut[record.rut] = record

    return list(records_by_rut.values())


def save_to_excel(records: List[PersonRecord], output_path: Path) -> None:
    df = pd.DataFrame(
        [{"Nombre": r.nombre, "Apellido": r.apellido, "Rut": r.rut} for r in records]
    )

    if not df.empty:
        df = df.sort_values(by=["Apellido", "Nombre"]).reset_index(drop=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(output_path, index=False)


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
        type=str,
        default=None,
        help="Fecha minima para filtrar mensajes del chat (formato DD/MM/AAAA).",
    )
    parser.add_argument(
        "--images-dir",
        type=Path,
        default=None,
        help="Carpeta con fotos de carnet para extraer datos por OCR.",
    )

    args = parser.parse_args()

    since_date = None
    if args.since_date:
        try:
            since_date = datetime.strptime(args.since_date, "%d/%m/%Y")
        except ValueError as exc:
            raise ValueError("El parametro --since-date debe tener formato DD/MM/AAAA") from exc

    if not args.input.exists():
        raise FileNotFoundError(f"No se encontro el archivo de entrada: {args.input}")

    with args.input.open("r", encoding="utf-8", errors="ignore") as f:
        records = extract_records(f, since_date=since_date)

    if args.images_dir:
        if not args.images_dir.exists() or not args.images_dir.is_dir():
            raise FileNotFoundError(
                f"No se encontro la carpeta de imagenes: {args.images_dir}"
            )

        image_records = extract_records_from_images(args.images_dir)
        records_by_rut = {r.rut: r for r in records}
        for record in image_records:
            records_by_rut[record.rut] = record
        records = list(records_by_rut.values())

    save_to_excel(records, args.output)

    print(f"Registros encontrados: {len(records)}")
    print(f"Archivo generado: {args.output.resolve()}")


if __name__ == "__main__":
    main()
