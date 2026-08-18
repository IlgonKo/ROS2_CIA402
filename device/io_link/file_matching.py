from pathlib import Path
import re


def find_unique_xml_file(directory, key, label):
    directory = Path(directory)
    normalized_key = normalized_file_key(key)
    candidates = [
        path
        for path in directory.glob("*.xml")
        if file_matches_key(path, normalized_key)
    ]
    if not candidates:
        raise FileNotFoundError(
            f"No {label} XML file matching {key!r} in {directory}"
        )
    exact_matches = [
        path
        for path in candidates
        if normalized_file_key(path.stem) == normalized_key
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(candidates) == 1:
        return candidates[0]
    names = ", ".join(path.name for path in candidates)
    raise ValueError(
        f"Ambiguous {label} XML file prefix {key!r} in {directory}: {names}"
    )


def file_matches_key(path, normalized_key):
    stem = normalized_file_key(Path(path).stem)
    return stem == normalized_key or stem.startswith(normalized_key)


def normalized_file_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())
