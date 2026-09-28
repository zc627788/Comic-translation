"""Ground truth must be independent of detector output. Unknown metrics remain null."""

import re
import unicodedata

from services.worker.bubble_vision import area, intersection


def normalize(text, *, remove_spaces=False):
    text = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()
    return text.replace(" ", "") if remove_spaces else text


def distance(reference, hypothesis):
    previous = list(range(len(hypothesis) + 1))
    for i, a in enumerate(reference, 1):
        current = [i]
        for j, b in enumerate(hypothesis, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + (a != b)))
        previous = current
    return previous[-1]


def score_regions(annotations, predictions):
    if annotations is None:
        return None
    truth = [row for row in annotations if row.get("legible") and row["role"] == "dialogue"]
    candidates = {i: sorted(
        [j for j, p in enumerate(predictions)
         if intersection(g["box"], p["box"]) / max(1, area(g["box"])) >= .9],
        key=lambda j: area(predictions[j]["box"])) for i, g in enumerate(truth)}
    # Maximum bipartite matching: one huge detection cannot count as multiple true positives.
    owner = {}

    def match(i, visited):
        for j in candidates[i]:
            if j in visited:
                continue
            visited.add(j)
            if j not in owner or match(owner[j], visited):
                owner[j] = i
                return True
        return False

    for i in range(len(truth)):
        match(i, set())
    mapping = {i: j for j, i in owner.items()}
    chars = errors = matched_chars = matched_errors = no_space_chars = no_space_errors = 0
    for i, g in enumerate(truth):
        reference = normalize(g["text"])
        predicted = normalize(predictions[mapping[i]].get("text", "")) if i in mapping else ""
        edit = distance(reference, predicted)
        chars += len(reference)
        errors += edit
        if i in mapping:
            matched_chars += len(reference)
            matched_errors += edit
        no_space_chars += len(reference.replace(" ", ""))
        no_space_errors += distance(reference.replace(" ", ""), predicted.replace(" ", ""))
    return {
        "truth_regions": len(truth), "matched_regions": len(mapping),
        "missed_regions": len(truth) - len(mapping),
        "unmatched_predictions": len(predictions) - len(mapping),
        "reference_characters": chars, "edit_errors": errors,
        "matched_reference_characters": matched_chars, "matched_edit_errors": matched_errors,
        "no_space_reference_characters": no_space_chars, "no_space_edit_errors": no_space_errors,
        "detection_recall": len(mapping) / len(truth) if truth else None,
        "end_to_end_cer": errors / chars if chars else None,
        "conditional_cer": matched_errors / matched_chars if matched_chars else None,
        "end_to_end_cer_without_spaces": (no_space_errors / no_space_chars
                                         if no_space_chars else None),
    }
