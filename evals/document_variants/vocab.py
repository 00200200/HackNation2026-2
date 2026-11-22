"""How a fact can be printed (dates, amounts, account numbers, registry ids) and a seeded chooser that tags each choice.

The tags travel with every generated PDF, so the report can slice F1 by "date=long" or "layout=letter".
"""

import random
from datetime import date

MONTHS = [
    "stycznia",
    "lutego",
    "marca",
    "kwietnia",
    "maja",
    "czerwca",
    "lipca",
    "sierpnia",
    "września",
    "października",
    "listopada",
    "grudnia",
]
NBSP = " "


class Defaults(random.Random):
    """Takes the place of the generator in faithful mode: every draw returns the first or the smallest value, and
    `random()` returns 1.0 so that no probability test succeeds."""

    def random(self) -> float:
        return 1.0

    def randint(self, a, b):
        return a

    def choice(self, seq):
        return seq[0]

    def sample(self, population, k, *, counts=None):
        return list(population)[:k]


class Pick:
    """Seeded chooser that records what it chose. `options` are strings or (tag, value) pairs.

    The first option is the default: the most common wording or layout among the 60 training documents of that class
    where it is known. With `faithful=True` every choice takes its default, which renders a document in the majority
    wording of the training set (no single training template). Otherwise `deviations / calls` is the share of choices
    that left the default, so a report can show how the score falls as a document drifts from it.
    """

    def __init__(self, rng: random.Random, faithful: bool = False):
        self.rng = Defaults() if faithful else rng
        self.faithful = faithful
        self.tags: dict[str, str] = {}
        self.calls = 0
        self.deviations = 0

    def __call__(self, name: str, options, weights=None):
        options = list(options)
        index = 0 if self.faithful else self.rng.choices(range(len(options)), weights)[0]
        self.calls += 1
        self.deviations += index != 0
        tag, value = options[index] if isinstance(options[index], tuple) else (options[index], options[index])
        self.tags[name] = str(tag)
        return value

    def chance(self, name: str, p: float) -> bool:
        hit = not self.faithful and self.rng.random() < p
        self.calls += 1
        self.deviations += hit
        self.tags[name] = "yes" if hit else "no"
        return hit

    def result(self) -> dict[str, str]:
        """The tags, plus how far the document drifted from the default template."""
        share = self.deviations / max(self.calls, 1)
        buckets = ((0.25, "<25%"), (0.4, "25-40%"), (0.55, "40-55%"))
        label = "none" if self.faithful else next((text for limit, text in buckets if share < limit), ">55%")
        return {**self.tags, "variation": label}


def fmt_date(d: date, style: str) -> str:
    long = f"{d.day} {MONTHS[d.month - 1]} {d.year}"
    return {
        "iso": f"{d:%Y-%m-%d}",
        "dot": f"{d:%d.%m.%Y}",
        "dot_r": f"{d:%d.%m.%Y} r.",
        "dash": f"{d:%d-%m-%Y}",
        "slash": f"{d:%d/%m/%Y}",
        "long": long,
        "long_r": f"{long} r.",
        "long_roku": f"{long} roku",
    }[style]


# thousands separator, decimal separator, template
AMOUNT_STYLES = {
    "space_comma_zl": (" ", ",", "{n} zł"),
    "space_comma_pln": (" ", ",", "{n} PLN"),
    "nbsp_comma_pln": (NBSP, ",", "{n} PLN"),
    "plain_dot_pln": ("", ".", "{n} PLN"),
    "plain_comma_zl": ("", ",", "{n} zł"),
    "pln_first": (" ", ",", "PLN {n}"),
    "bare_comma": ("", ",", "{n}"),
    "debit_sign": (" ", ",", "-{n} PLN"),
}


def fmt_amount(value: float, style: str) -> str:
    thousands, decimal, template = AMOUNT_STYLES[style]
    cents = round(value * 100)
    whole, frac = divmod(cents, 100)
    digits = f"{whole:,}".replace(",", thousands) if thousands else str(whole)
    return template.format(n=f"{digits}{decimal}{frac:02d}")


def group4(number: str, lead: int = 2) -> str:
    """Account number in the usual blocks: 2 check digits, then groups of 4."""
    return " ".join([number[:lead], *(number[i : i + 4] for i in range(lead, len(number), 4))])


def fmt_account(account: str, style: str) -> tuple[str, str]:
    """(printed form, JSON form) for an account given as country code + digits, e.g. PL6843...

    The JSON form is the printed number without whitespace, with the country code only when it is printed (#58).
    """
    code, digits = account[:2], account[2:]
    printed = {
        "bare": digits,
        "grouped": group4(digits),
        "code_bare": code + digits,
        "code_grouped": code + group4(digits),
        "code_space_grouped": f"{code} {group4(digits)}",
    }[style]
    return printed, "".join(printed.split())


def fmt_nip(nip: str, style: str) -> str:
    return {
        "plain": nip,
        "dashed": f"{nip[:3]}-{nip[3:6]}-{nip[6:8]}-{nip[8:]}",
        "spaced": f"{nip[:3]} {nip[3:6]} {nip[6:8]} {nip[8:]}",
    }[style]


def fmt_ted(number: int, year: int, issue: int, style: str) -> tuple[str, str]:
    """(printed, JSON form). The JSON form is always NNNNNN-YYYY; `issue` is the Official Journal S issue."""
    printed = {
        "nnnnnn_yyyy": f"{number:06d}-{year}",
        "yyyy_s_nnnnnn": f"{year}/S {issue:03d}-{number:06d}",
        "yyyy_s_compact": f"{year}/S{issue:03d}-{number:06d}",
    }[style]
    return printed, f"{number:06d}-{year}"
