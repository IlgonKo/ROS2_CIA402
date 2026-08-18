from pathlib import Path
import re


def normalized_file_key(value):
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def find_unique_xml_file(directory, key, label):
    directory = Path(directory)
    wanted = normalized_file_key(key)
    exact_matches = []
    prefix_matches = []

    for path in directory.glob("*.xml"):
        candidate = normalized_file_key(path.stem)
        if candidate == wanted:
            exact_matches.append(path)
        elif candidate.startswith(wanted):
            prefix_matches.append(path)

    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        raise ValueError(
            ambiguous_file_message(label, key, exact_matches)
        )

    if len(prefix_matches) == 1:
        return prefix_matches[0]
    if len(prefix_matches) > 1:
        raise ValueError(
            ambiguous_file_message(label, key, prefix_matches)
        )

    raise FileNotFoundError(
        f"No {label} XML file matching {key!r} found in {directory}"
    )


def ambiguous_file_message(label, key, paths):
    choices = ", ".join(path.name for path in sorted(paths, key=lambda item: item.name.lower()))
    return (
        f"Multiple {label} XML files match {key!r}: {choices}. "
        "Use a more specific file key."
    )
