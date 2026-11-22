"""Date and reason of the first challenged act when the sentence that states it is reworded.

    uv run python -m evals.reword_action

The training appeals print that sentence as "Zamawiający w dniu D ...". This reads the text layer of each appeal,
rewrites the sentence four other ways and counts, per wording, the dates and the reasons that the text path gets
right, leaves empty or gets wrong. Three readings are compared:

- `wordings`: the text path as it is, `appeal.extract` and then `appeal.fill_action_date`.
- `fallback_only`: the same with the reworded opening disabled, so that only the generic fallback can date a
  reworded sentence.
- `baseline`: the reworded opening and the fallback both disabled, which is how the text path read the act before
  `REWORDED_ACTION_RE` and `fill_action_date` existed.

The four wordings are the ones the reworded opening was written for, so `wordings` is a regression check and
`fallback_only` is the reading that exercises the generic fallback. Every miss listed under `fallback_only` carries
the reading before this change under `before`. Scans and the model engines are not covered.
"""

import json
import re
from collections import Counter
from unittest.mock import patch

from evals.run import DATA, ROOT
from kio2json import appeal
from kio2json.pdf_text import join_pages, read_pages

RESULTS = ROOT / "evals" / "results" / "action-rewordings.json"
DATE = r"\d{1,2}\s+\w+\s+\d{4}(?:\s+(?:r\.|roku))?|\d{1,2}\.\d{2}\.\d{4}(?:\s+(?:r\.|roku))?"
PRINTED = re.compile(rf"Zamawiający\s+w\s+dniu\s+({DATE})\s+")
NEVER = re.compile(r"(?!x)x")
WORDINGS = {
    "printed": None,
    "W dniu D Zamawiający": r"W dniu \1 Zamawiający ",
    "Dnia D Zamawiający": r"Dnia \1 Zamawiający ",
    "Zamawiający dnia D": r"Zamawiający dnia \1 ",
    "Zamawiający, w dniu D,": r"Zamawiający, w dniu \1, ",
}


def read_action(text: str, fill: bool) -> tuple[str | None, int | None]:
    record = appeal.extract(text)
    if fill:
        appeal.fill_action_date(record, text)
    action = record["OdwolanieKIO"]
    return action["czynnosc_dzien"], action["czynnosc_powod_id"]


def verdict(got, gold) -> str:
    return "empty" if got is None else "right" if got == gold else "wrong"


def measure(
    appeals: list, fill: bool = True, list_misses: bool = True, readings: dict | None = None, before: dict | None = None
) -> dict:
    """Count the verdicts per wording. `readings` collects every (date, reason); `before` is such a collection from
    the reading before this change, attached to each miss."""
    wordings = {}
    for wording, replacement in WORDINGS.items():
        date, reason, misses = Counter(), Counter(), []
        for case, text, gold_date, gold_reason in appeals:
            day, why = read_action(PRINTED.sub(replacement, text) if replacement else text, fill)
            if readings is not None:
                readings[wording, case] = (day, why)
            date[verdict(day, gold_date)] += 1
            reason[verdict(why, gold_reason)] += 1
            if (day, why) != (gold_date, gold_reason):
                miss = {"case": case, "date": day, "gold_date": gold_date, "reason": why, "gold_reason": gold_reason}
                if before is not None:
                    miss["before"] = dict(zip(("date", "reason"), before[wording, case]))
                misses.append(miss)
        wordings[wording] = {"date": dict(date), "reason": dict(reason)}
        if list_misses:
            wordings[wording]["misses"] = misses
        print(f"{wording:24} date {dict(date)} reason {dict(reason)}")
    return wordings


def main() -> None:
    appeals = []
    for pdf in sorted(DATA.glob("przyklad_*/odwolanie.pdf")):
        gold = json.loads(pdf.with_suffix(".json").read_text(encoding="utf-8"))["OdwolanieKIO"]
        appeals.append(
            (pdf.parent.name, join_pages(read_pages(pdf)), gold["czynnosc_dzien"], gold["czynnosc_powod_id"])
        )
    report = {"appeals": len(appeals)}
    report["wordings"] = measure(appeals)
    with patch.object(appeal, "REWORDED_ACTION_RE", NEVER):
        print("Fallback disabled as well, the reading before this change:")
        before = {}
        baseline = measure(appeals, fill=False, list_misses=False, readings=before)
        print("Reworded opening disabled, so that only the generic fallback can date a reworded sentence:")
        report["fallback_only"] = measure(appeals, before=before)
        report["baseline"] = baseline
    RESULTS.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
