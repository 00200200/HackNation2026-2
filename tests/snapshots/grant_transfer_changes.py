"""Expected grant and receipt changes from integration base e051dfa."""

from copy import deepcopy

NATIVE_IMPROVEMENTS = {"task11/Xacc", "task11/Tb", "new/bank-archive-third", "new/appeal-mask-in-title"}
ABSENT = object()  # distinct from a printed field whose base value is null

REVIEW_SENDER = "46137900000000000000471362"
REVIEW_RECIPIENT = "97298300000000000000836412"
SENDER = "70182600000000000000673815"
RECIPIENT = "96481100000000000000942673"


def receipt(date, amount, sender, recipient, reference, title, reason):
    """A newly routed document introduces a class and six individually specified fields."""
    return [
        ("class", None, "bank_transfer", reason),
        ("przelew_bankowy.data_operacji", ABSENT, date, reason),
        ("przelew_bankowy.kwota", ABSENT, amount, reason),
        ("przelew_bankowy.na_rachunek", ABSENT, recipient, reason),
        ("przelew_bankowy.numer_transakcji", ABSENT, reference, reason),
        ("przelew_bankowy.tytul", ABSENT, title, reason),
        ("przelew_bankowy.z_rachunku", ABSENT, sender, reason),
    ]


def signer(name):
    return {"imie_nazwisko": name}


def attorney(name, pesel=None):
    return {"imie_nazwisko": name, "pesel": pesel}


def company(name, krs=None, signers=()):
    return {
        "data": {"imie_nazwisko": None, "krs": krs, "nazwa": name, "nip": None, "typ": "osoba_prawna"},
        "podpisujacy": [signer(person) for person in signers],
    }


def grant(principal, lawyer, reason):
    return [
        ("class", None, "power_of_attorney", reason),
        ("mocodawca", ABSENT, [principal], reason),
        ("pelnomocnicy", ABSENT, [attorney(lawyer)], reason),
    ]


def bound_pair(sender, recipient):
    return [
        (
            "przelew_bankowy.na_rachunek",
            None,
            recipient,
            "The recipient field identifies the beneficiary despite a third account elsewhere.",
        ),
        (
            "przelew_bankowy.z_rachunku",
            None,
            sender,
            "The sender field identifies the payer despite a third account elsewhere.",
        ),
    ]


# case id -> (field path, integration-base value, intended value, evidence).
# A +index inserts a previously absent list member without replacing an existing one.
INTENDED_CHANGES = {
    "new/appeal-mask-in-title": [
        ("ZamowieniePubliczne.tytul", None, "Przędza XXXX i akcesoria", "Nazwa zamówienia explicitly labels the title.")
    ],
    "task11/Xacc": [
        (
            "przelew_bankowy.na_rachunek",
            "84848484848484848484848484",
            None,
            "The only other printed account is explicitly for a refund, so the transfer destination is unknown.",
        )
    ],
    "task11/Tb": receipt(
        None,
        27.34,
        "73737373737373737373737373",
        "84848484848484848484848484",
        None,
        "Status prawny nieruchomości",
        "The confirmation names both parties and the amount; the wrapped title is a noun phrase under its own label.",
    ),
    "task32/T1": [("przelew_bankowy.kwota", None, 782.14, "Amount occupies the right-hand cell beside the date.")],
    "task32/T2": receipt(
        "2026-06-09",
        782.14,
        REVIEW_SENDER,
        REVIEW_RECIPIENT,
        "QJ684291",
        "Dostawa magnesów",
        "A posted debit binds the holder and counterparty to a single dated payment.",
    ),
    "task32/T5": receipt(
        "2026-06-09",
        782.14,
        REVIEW_SENDER,
        REVIEW_RECIPIENT,
        "QJ684291",
        "Dostawa magnesów",
        "The bank attests to debiting and transferring funds and states the reference and payment text.",
    ),
    "task32/T6": receipt(
        "2026-06-09",
        782.14,
        None,
        REVIEW_RECIPIENT,
        "QJ684291",
        "Dostawa magnesów",
        "The executed payment has a partial payer mask and a full payee account.",
    ),
    "new/bank-archive-third": bound_pair("71932700000000000000000027", "87432198765432198765432123"),
    "task32/C3": bound_pair(REVIEW_SENDER, REVIEW_RECIPIENT),
    "task32/public-C3": bound_pair(REVIEW_SENDER, REVIEW_RECIPIENT),
    "task32/P1": [
        (
            "pelnomocnicy.+0",
            ABSENT,
            attorney("Aldona Mgielna", "92020367898"),
            "The grant and the labelled nominative restate one appointment.",
        )
    ],
    "task32/P2": [
        ("mocodawca.0.podpisujacy.+0", ABSENT, signer("Zenon Kruchy"), "The second officer acts for Jasny Puch."),
        (
            "mocodawca.+0",
            ABSENT,
            company("Miedziany Wir S.A.", "0000786194", ["Eliza Falista"]),
            "The first numbered officer grants authority for a distinct registered company.",
        ),
    ],
    "task32/P3": [
        (
            "mocodawca.0.podpisujacy.+0",
            ABSENT,
            signer("Laura Migotliwa"),
            "A named electronic signature belongs to the identified grantor.",
        )
    ],
    "task32/P4": grant(
        company("Bursztynowy Splot sp. z o.o.", signers=["Laura Migotliwa"]),
        "Iwonie Rytmicznej",
        "The sole named officer grants the power before the notary and the deed expressly records signing.",
    ),
    "invented/transfer-directional-account-labels": [
        (
            "przelew_bankowy.na_rachunek",
            None,
            REVIEW_RECIPIENT,
            "The account labelled as the payment destination is explicit.",
        ),
        ("przelew_bankowy.z_rachunku", None, REVIEW_SENDER, "The account labelled as the source of funds is explicit."),
    ],
    "invented/transfer-refund-after-parties": bound_pair(SENDER, RECIPIENT),
    "invented/transfer-commission-before-parties": bound_pair(SENDER, RECIPIENT),
    "invented/transfer-booking-date-first": [
        ("przelew_bankowy.data_operacji", "2031-02-12", "2031-02-11", "The operation date is explicitly labelled.")
    ],
    "invented/transfer-negative-debit": [
        ("przelew_bankowy.kwota", None, 918.73, "The amount label gives the outgoing debit magnitude.")
    ],
    "invented/transfer-only-daily": [
        ("przelew_bankowy.numer_transakcji", None, "81", "The daily sequence is the only printed identifier.")
    ],
    "invented/transfer-interleaved-cells": [
        ("przelew_bankowy.data_operacji", None, "2031-02-11", "Date occupies the right-hand cell beside the amount.")
    ],
    "invented/transfer-masked-recipient": receipt(
        "2031-02-11",
        918.73,
        SENDER,
        None,
        "TWQ641803",
        "Próbniki pigmentów",
        "A headed confirmation pairs the verified sender with the partially masked payee.",
    ),
    "invented/transfer-masked-payer-with-dashes": receipt(
        "2031-02-11",
        918.73,
        None,
        RECIPIENT,
        "TWQ641803",
        "Próbniki pigmentów",
        "A headed confirmation pairs the partially masked payer with a verified recipient.",
    ),
    "invented/grant-numbered-heading": grant(
        company("Srebrny Kil S.A."),
        "Oliwie Łagodnej",
        "A numbered heading introduces the named principal and its lawyer.",
    ),
    "invented/grant-deed-with-active-grant": grant(
        company("Lniana Baszta sp. z o.o."),
        "Oliwie Łagodnej",
        "A notarial grant states the acting principal and expressly appoints the lawyer.",
    ),
    "invented/grant-labelled-nominative": [
        (
            "pelnomocnicy.+0",
            ABSENT,
            attorney("Wanda Lnista", "90050714569"),
            "One appointee is restated with her labelled nominative and PESEL.",
        )
    ],
    "invented/grant-two-different-appointees": [
        ("pelnomocnicy.+0", ABSENT, attorney("Wandzie Lnistej"), "The grant appoints this person directly."),
        (
            "pelnomocnicy.+1",
            ABSENT,
            attorney("Basia Szeroka", "93040797245"),
            "A distinct person is explicitly labelled as an attorney.",
        ),
    ],
    "invented/grant-explicit-electronic": [
        ("mocodawca.0.podpisujacy.+0", ABSENT, signer("Lena Wrzosowa"), "Electronic signature names the signer.")
    ],
    "invented/grant-explicit-electronic-on-next-row": [
        (
            "mocodawca.0.podpisujacy.+0",
            ABSENT,
            signer("Lena Wrzosowa"),
            "The electronic signer's name occupies the next row in the named grantor block.",
        )
    ],
    "invented/grant-unreadable-mark": [
        ("mocodawca.0.podpisujacy.+0", ABSENT, signer(None), "One grantor signature is explicitly illegible.")
    ],
    "review52/transfer-after-booking": [
        (
            "przelew_bankowy.data_operacji",
            "2035-08-08",
            "2035-08-07",
            "The bank states it executed the transfer on August 7 and booked it on August 8.",
        )
    ],
}


def expected_result(case, original):
    """Apply the enumerated changes to a copy; fail if an asserted old value has drifted."""
    label, payload = deepcopy(original)
    document = {"class": label, **payload}
    for path, before, after, reason in INTENDED_CHANGES.get(case, []):
        assert reason and before != after
        *parents, field = path.split(".")
        target = document
        for part in parents:
            target = target[int(part)] if isinstance(target, list) else target.setdefault(part, {})
        if field.startswith("+"):
            index = int(field[1:])
            assert isinstance(target, list) and index <= len(target) and before is ABSENT
            target.insert(index, deepcopy(after))
        else:
            key = int(field) if isinstance(target, list) else field
            actual = target[key] if isinstance(target, list) else target.get(key, ABSENT)
            assert actual == before, (case, path, actual, before)
            if after is ABSENT:
                del target[key]
            else:
                target[key] = deepcopy(after)
    return [document.pop("class"), document]
