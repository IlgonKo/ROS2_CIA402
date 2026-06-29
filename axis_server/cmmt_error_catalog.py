import json
import re
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANUAL_PATH = (
    PROJECT_ROOT / "Reference" / "CMMT-AS-_-S1_manual_2026-02o_8249086g1.pdf"
)
DEFAULT_CATALOG_PATH = PROJECT_ROOT / "Reference" / "cmmt_error_catalog.json"
MESSAGE_PAGE_FIRST = 512
MESSAGE_PAGE_LAST = 565


def load_cmmt_error_catalog(
    manual_path=DEFAULT_MANUAL_PATH,
    catalog_path=DEFAULT_CATALOG_PATH,
):
    catalog = load_cmmt_error_catalog_json(catalog_path)
    if catalog:
        return catalog

    if not Path(manual_path).exists():
        return {}

    try:
        result = subprocess.run(
            [
                "pdftotext",
                "-f",
                str(MESSAGE_PAGE_FIRST),
                "-l",
                str(MESSAGE_PAGE_LAST),
                "-layout",
                str(manual_path),
                "-",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return {}

    return parse_cmmt_error_catalog(result.stdout)


def load_cmmt_error_catalog_json(catalog_path=DEFAULT_CATALOG_PATH):
    if not Path(catalog_path).exists():
        return {}

    try:
        with open(catalog_path, "r", encoding="utf-8") as catalog_file:
            raw_catalog = json.load(catalog_file)
    except (OSError, json.JSONDecodeError):
        return {}

    catalog = {}
    for code, entry in raw_catalog.items():
        try:
            numeric_code = int(code)
        except (TypeError, ValueError):
            continue
        catalog[numeric_code] = _normalize_entry(dict(entry))
    return catalog


def parse_cmmt_error_catalog(text):
    catalog = {}
    current = None
    current_field = "description"

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        start = re.match(r"^(\d{2}) \| (\d{2}) \| (\d{5})\b", line.strip())
        if start:
            if current is not None:
                _store_entry(catalog, current)

            main_group = int(start.group(1))
            subgroup = int(start.group(2))
            error_number = int(start.group(3))
            message, description = _split_start_line(line, start.end())
            current = {
                "code": (main_group << 24) | (subgroup << 16) | error_number,
                "id": f"{main_group:02d} | {subgroup:02d} | {error_number:05d}",
                "message": message,
                "description": description,
                "remedy": "",
                "classification": "",
            }
            current_field = "description"
            continue

        if current is None:
            continue

        if line.startswith("("):
            message_text, content = _split_parenthetical_line(line)
            if message_text:
                current["message"] = _join_text(current["message"], message_text)
        else:
            content = _content_text(line)

        current_field = _append_content(current, content, current_field)

    if current is not None:
        _store_entry(catalog, current)

    return catalog


def _store_entry(catalog, entry):
    catalog[entry["code"]] = _normalize_entry(entry)


def _normalize_entry(entry):
    for key in ("message", "description", "remedy", "classification"):
        entry[key] = _clean_text(entry.get(key, ""))
    entry["classification"] = _default_classification(entry["classification"])
    return entry


def _column(line, start, end):
    if len(line) <= start:
        return ""
    if end is None:
        return line[start:].strip()
    return line[start:end].strip()


def _split_start_line(line, content_start):
    tail = line[content_start:].strip()
    parts = re.split(r"\s{2,}", tail, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return _column(line, 28, 64), _column(line, 64, None)


def _split_parenthetical_line(line):
    content = re.sub(r"^\(\d+\)\s*", "", line)
    label_index = _first_label_index(content)
    if label_index is None:
        return content.strip(), ""
    return content[:label_index].strip(), content[label_index:].strip()


def _content_text(line):
    label_index = _first_label_index(line)
    if label_index is not None:
        return line[label_index:].strip()

    content = line.strip()
    ignored_prefixes = (
        "Diagnostics and fault clearance",
        "ID Dx.",
        "Festo ",
        "Tab. ",
        "Fig. ",
    )
    if content.startswith(ignored_prefixes):
        return ""
    if re.fullmatch(r"\d+", content):
        return ""
    return content


def _first_label_index(text):
    indices = [
        text.find(label)
        for label in ("Remedy", "Classification", "Error memory")
        if text.find(label) >= 0
    ]
    if not indices:
        return None
    return min(indices)


def _append_content(entry, content, current_field):
    content = content.strip()
    if not content:
        return current_field

    if "Remedy" in content:
        before, after = content.split("Remedy", 1)
        if before.strip():
            entry["description"] = _join_text(entry["description"], before.strip())
        entry["remedy"] = _join_text(entry["remedy"], after.strip())
        return "remedy"
    if "Classification" in content:
        before, after = content.split("Classification", 1)
        if before.strip() and current_field == "remedy":
            entry["remedy"] = _join_text(entry["remedy"], before.strip())
        elif before.strip():
            entry["description"] = _join_text(entry["description"], before.strip())
        entry["classification"] = _join_text(
            entry["classification"],
            after.strip(),
        )
        return "classification"
    if "Error memory" in content:
        return "error_memory"

    if current_field in {"description", "remedy", "classification"}:
        entry[current_field] = _join_text(entry[current_field], content)
    return current_field


def _join_text(left, right):
    if not right:
        return left
    if not left:
        return right
    return f"{left} {right}"


def _clean_text(text):
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace(" – ", "; ")
    text = text.replace("– ", "; ")
    text = re.sub(r"^(;\s*)+", "", text)
    return text


def _default_classification(text):
    match = re.search(r"Default:\s*(.*?)(?:\s+Can be parameterised:|$)", text)
    if match:
        return f"Default: {match.group(1).strip()}"
    return text
