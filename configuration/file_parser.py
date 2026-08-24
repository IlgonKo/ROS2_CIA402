from pathlib import Path
import re


INDEXED_LIST_ITEM_RE = re.compile(r"^\s*\d+\s*:\s*(.+)$")
INDEXED_LIST_ITEM_WITH_INDEX_RE = re.compile(r"^\s*(\d+)\s*:\s*(.+)$")


def logical_config_lines(path):
    path = Path(path)
    if not path.exists():
        return []

    lines = []
    pending = ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not pending and (not line or line.startswith("#")):
            continue

        continued = line.endswith("\\")
        if continued:
            line = line[:-1].strip()

        pending += line
        if continued:
            continue

        if pending:
            lines.append(pending)
        pending = ""

    if pending:
        lines.append(pending)
    return lines


def read_key_value_config(path):
    values = {}
    for line in logical_config_lines(path):
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = unquote_config_value(value.strip())
    return values


def unquote_config_value(value):
    value = str(value).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def split_config_list(value, strip_index_labels=False):
    items = []
    for raw_item in str(value or "").split(","):
        item = raw_item.strip()
        if not item:
            continue
        if strip_index_labels:
            item = strip_index_label(item)
        items.append(item)
    return items


def split_indexed_config_list(value, default_start=1):
    items = []
    next_index = int(default_start)
    for raw_item in str(value or "").split(","):
        item = raw_item.strip()
        if not item:
            continue
        match = INDEXED_LIST_ITEM_WITH_INDEX_RE.match(item)
        if match:
            index = int(match.group(1))
            item_value = match.group(2).strip()
        else:
            index = next_index
            item_value = item
        items.append((index, item_value))
        next_index = index + 1
    return items


def strip_index_label(item):
    match = INDEXED_LIST_ITEM_RE.match(str(item or ""))
    if match:
        return match.group(1).strip()
    return str(item or "").strip()
