"""Case-linked transfers following the public organizer's 7 early, 1 late and 5 scan layouts."""

from datetime import date

BANKS = ("Bank Rzeczny S.A.", "Bank Zatoki S.A.", "Bank Kotliny S.A.", "Bank Jeziorny S.A.")
FIELDS = {"z_rachunku", "na_rachunek", "kwota", "data_operacji", "tytul", "numer_transakcji"}
FOOTER = "Dokument wygenerowany elektronicznie przez system bankowy. Potwierdzenie nie wymaga podpisu ani pieczęci."


def _account(value, grouped):
    if not value or not grouped:
        return value
    prefix = "PL" if value.startswith("PL") else ""
    digits = value.removeprefix(prefix)
    return prefix + digits[:2] + " " + " ".join(digits[i : i + 4] for i in range(2, len(digits), 4))


class _Receipt:
    def __init__(self, page, case):
        self.page = page
        self.index = case["index"]
        self.bank = BANKS[self.index % len(BANKS)]
        self.v = dict(case["receipt"]["przelew_bankowy"])
        self.v.update(payer=case["payer"], payee=case["payee"])
        self.v["printed"] = date.fromisoformat(case["issue_date"]).strftime("%d.%m.%Y")
        execution = self.v["data_operacji"]
        if execution:
            self.v["data_operacji"] = date.fromisoformat(execution).strftime(("%d.%m.%Y", "%Y-%m-%d")[self.index % 2])
        self.v["kwota"] = f"{self.v['kwota']:,.2f}".replace(",", " ").replace(".", ",") + " PLN"
        for key in ("z_rachunku", "na_rachunek"):
            self.v[key] = _account(self.v[key], self.index % 4 != 1)
        self.v.update(status="Zrealizowano", fee="0,00 PLN", channel="Bankowość elektroniczna")
        self.payer_label = ("Płatnik", "Nadawca", "Zleceniodawca")[self.index % 3]
        self.payee_label = ("Odbiorca", "Beneficjent", "Adresat przelewu")[self.index % 3]

    def value(self, x, y, key, **style):
        value = self.v[key]
        if value is None:
            return y
        role = f"przelew_bankowy.{key}" if key in FIELDS else None
        return self.page.text(x, y, value, role=role, **style)

    def rows(self, y, entries, *, left=48, split=195, right=545, size=10, rules=False, border=False):
        """A label gutter followed by a wrapping value cell; null rows are absent."""
        start = y
        for label, key in entries:
            if self.v[key] is None:
                continue
            if rules or border:
                self.page.line(left - 4, y - 3, right + 4, y - 3)
            label_end = self.page.text(left, y, label, width=split - left - 8, size=size, bold=True)
            end = self.value(split, y, key, size=size, width=right - split)
            y = max(label_end, end) + 8
        if border:
            self.page.line(left - 4, y - 3, right + 4, y - 3)
            for x in (left - 4, split - 5, right + 4):
                self.page.line(x, start - 3, x, y - 3)
        return y

    def stack(self, x, y, label, key, *, width=470, size=10, mono=False):
        if self.v[key] is None:
            return y
        y = self.page.text(x, y, label, size=size - 1, bold=True, width=width, mono=mono)
        return self.value(x, y + 2, key, width=width, size=size, mono=mono) + 5

    def heading(self, title, *, left=48, y=50, centered=False, size=15):
        self.page.section("heading")
        if centered:
            left = (self.page.width - self.page.measure(title, size=size, bold=True)) / 2
        return self.page.text(left, y, title, bold=True, size=size, width=520)

    def footer(self, y):
        self.page.section("footer")
        self.page.text(48, y, FOOTER, size=8)


def _early_order(r):
    p = r.page
    y = r.heading("POLECENIE PRZELEWU")
    p.text(48, y + 4, "Potwierdzenie wykonania dyspozycji · " + r.bank)
    y += 48
    for section, name, party, label, account in (
        ("payer", r.payer_label, "payer", "Rachunek obciążany", "z_rachunku"),
        ("payee", r.payee_label, "payee", "Rachunek odbiorcy", "na_rachunek"),
    ):
        p.section(section)
        p.line(48, y - 5, 546, y - 5)
        y = max(r.stack(48, y, name, party, width=225), r.stack(294, y, label, account, width=250)) + 16
    p.section("settlement")
    y = max(r.stack(48, y, "Kwota operacji", "kwota"), r.stack(294, y, "Data transakcji", "data_operacji")) + 13
    p.section("description")
    y = r.stack(48, y, "Opis", "tytul")
    y = r.stack(48, y + 5, "Nr ref.", "numer_transakcji")
    r.value(48, y + 7, "status", bold=True)
    r.footer(y + 54)


def _early_cards(r):
    p = r.page
    y = r.heading("Potwierdzenie przelewu krajowego")
    p.text(48, y + 3, r.bank + " · wydrukowano " + r.v["printed"])
    y += 46
    bottoms = []
    for x, section, label, party, account in (
        (48, "payer_card", r.payer_label, "payer", "z_rachunku"),
        (311, "payee_card", r.payee_label, "payee", "na_rachunek"),
    ):
        p.section(section)
        p.line(x, y - 4, x + 235, y - 4)
        end = r.stack(x, y + 3, label, party, width=225)
        bottoms.append(r.value(x, end + 5, account, size=9, width=230))
    p.section("transfer_summary")
    y = r.rows(
        max(bottoms) + 28,
        [
            ("Kwota operacji", "kwota"),
            ("Data operacji", "data_operacji"),
            ("Numer referencyjny", "numer_transakcji"),
            ("Tytuł przelewu", "tytul"),
            ("Kanał", "channel"),
        ],
        split=174,
    )
    r.footer(y + 24)


def _early_thermal(r):
    p = r.page
    x, width, size = 96, 402, 9
    p.section("thermal_header")
    y = p.text(x, 60, r.bank.upper(), size=12, bold=True, mono=True)
    y = p.text(x, y, "POTWIERDZENIE REALIZACJI POLECENIA PRZELEWU", size=size, mono=True)
    divider = "-" * 65

    def dotted(y, label, key):
        if r.v[key] is None:
            return y
        gap = 65 - len(label) - len(r.v[key]) - 2
        p.text(x, y, label + " " + "." * max(1, gap), size=size, mono=True)
        end = x + p.measure(divider, size=size, mono=True)
        return r.value(end - p.measure(r.v[key], size=size, mono=True), y, key, size=size, mono=True)

    p.section("amount_and_time")
    y = p.text(x, y, divider, size=size, mono=True)
    y = dotted(y, "KWOTA PRZELEWU", "kwota")
    y = dotted(y, "DATA REALIZACJI", "data_operacji")
    y = p.text(x, y, divider, size=size, mono=True)
    p.section("accounts")
    y = r.stack(x, y, "RACHUNEK NADAWCY", "z_rachunku", mono=True)
    y = r.stack(x, y, "RACHUNEK ODBIORCY", "na_rachunek", mono=True)
    y = r.value(x, y, "payee", size=size, mono=True, width=width)
    p.section("payment_description")
    y = p.text(x, y, divider, size=size, mono=True)
    y = r.stack(x, y, "OPIS:", "tytul", mono=True, size=size, width=width - 48)
    y = dotted(y, "NUMER REFERENCYJNY", "numer_transakcji")
    y = dotted(y, "STATUS", "status")
    y = dotted(y, "KANAŁ", "channel")
    p.text(x, y, divider + "\n*** DZIĘKUJEMY ***", size=size, mono=True)


def _early_summary(r):
    p = r.page
    y = r.heading("Potwierdzenie transakcji")
    p.text(48, y + 3, f"Nr klienta   {710000 + r.index}")
    p.section("transaction")
    y = r.stack(48, y + 39, "Tytuł", "tytul", width=490)
    for label, key in (
        ("Kwota", "kwota"),
        ("Data transakcji", "data_operacji"),
        ("Numer referencyjny", "numer_transakcji"),
    ):
        y = r.stack(48, y + 3, label, key)
    for section, name, party, label, account in (
        ("sender", r.payer_label, "payer", "Rachunek zleceniodawcy", "z_rachunku"),
        ("recipient", r.payee_label, "payee", "Rachunek beneficjenta", "na_rachunek"),
    ):
        p.section(section)
        y = r.stack(48, y + 11, name, party)
        y = r.rows(y, [(label, account)], split=177)
    p.section("costs")
    y = r.rows(y + 10, [("Kanał", "channel"), ("Opłata", "fee")])
    r.footer(y + 18)


def _early_letter(r):
    p = r.page
    p.section("letterhead")
    p.text(54, 52, r.bank + "\nCentrum Obsługi Klienta", bold=True)
    p.text(375, 58, "Warszawa, " + r.v["printed"])
    p.section("addressee")
    y = r.value(324, 124, "payer", width=220)
    p.section("confirmation_letter")
    y = p.text(54, y + 45, "Dotyczy: potwierdzenie przelewu krajowego", size=12, bold=True) + 20

    # Set each paragraph as running prose; keep field fragments on the same baseline as their labels.
    def paragraph(y, fragments):
        x = 54
        space = p.measure(" ")
        for literal, key in fragments:
            value = r.v[key] if key else literal
            if not value:
                continue
            role = f"przelew_bankowy.{key}" if key in FIELDS else None
            words = []
            for word in value.split():
                candidate = " ".join([*words, word])
                if x + p.measure(candidate) > 540:
                    if words:
                        p.text(x, y, " ".join(words), role=role, width=490)
                    x, y, words = 54, y + 13, []
                words.append(word)
            if words:
                run = " ".join(words)
                p.text(x, y, run, role=role, width=490)
                x += p.measure(run) + space
        return y + 23

    opening = [("Bank potwierdza wykonanie przelewu", None)]
    if r.v["data_operacji"]:
        opening.extend([("w dniu", None), (None, "data_operacji")])
    y = paragraph(
        y,
        opening
        + [
            ("z rachunku nr", None),
            (None, "z_rachunku"),
            ("prowadzonego dla", None),
            (None, "payer"),
            ("w kwocie", None),
            (None, "kwota"),
            ("na rachunek nr", None),
            (None, "na_rachunek"),
            ("prowadzony dla", None),
            (r.v["payee"] + ".", None),
        ],
    )
    y = paragraph(y, [("Tytuł przelewu:", None), (None, "tytul")])
    if r.v["numer_transakcji"]:
        y = paragraph(y, [("Numer transakcji operacji:", None), (None, "numer_transakcji")])
    p.section("signature")
    p.text(54, y + 16, "Z poważaniem,\nDział Rozliczeń")


def _early_sections(r):
    p = r.page
    p.section("masthead")
    p.text(44, 42, r.bank.upper(), size=11, bold=True)
    p.text(332, 42, "Potwierdzenie transakcji", size=14, bold=True)
    y = 102
    for name, heading, items in (
        ("sender_details", "Dane nadawcy", [("Nazwa", "payer"), ("Rachunek obciążany", "z_rachunku")]),
        ("recipient_details", "Dane odbiorcy", [("Nazwa", "payee"), ("Rachunek beneficjenta", "na_rachunek")]),
        (
            "operation_details",
            "Szczegóły operacji",
            [
                ("Kwota operacji", "kwota"),
                ("Data wykonania", "data_operacji"),
                ("Numer referencyjny", "numer_transakcji"),
                ("Tytuł", "tytul"),
                ("Status", "status"),
                ("Opłata", "fee"),
                ("Data wydruku", "printed"),
            ],
        ),
    ):
        p.section(name)
        p.line(44, y - 6, 545, y - 6)
        y = p.text(44, y, heading, bold=True, size=13) + 7
        y = r.rows(y, items, left=54, split=182, size=9) + 14
    r.footer(y + 12)


def _early_register(r):
    p = r.page
    p.section("bank")
    p.text(43, 52, r.bank, bold=True)
    p.text(378, 52, "Wydrukowano: " + r.v["printed"])
    y = r.heading("Potwierdzenie realizacji polecenia przelewu", left=43, y=82)
    p.section("transfer_register")
    y = r.rows(
        y + 19,
        [
            (r.payer_label, "payer"),
            ("Rachunek zleceniodawcy", "z_rachunku"),
            ("Dane odbiorcy", "payee"),
            ("Rachunek uznawany", "na_rachunek"),
            ("Wartość", "kwota"),
            ("Data operacji", "data_operacji"),
            ("Tytuł", "tytul"),
            ("Numer referencyjny", "numer_transakcji"),
            ("Kanał", "channel"),
        ],
        left=44,
        split=179,
        size=9,
    )
    r.footer(y + 23)


def _late_table(r):
    p = r.page
    y = r.heading("POTWIERDZENIE WYKONANIA PRZELEWU", y=70, centered=True)
    issuer = r.bank + " · wygenerowano " + r.v["printed"]
    p.text((p.width - p.measure(issuer)) / 2, y + 6, issuer)
    p.section("bank_table")
    y = r.rows(
        129,
        [
            ("Zleceniodawca", "payer"),
            ("Rachunek zleceniodawcy", "z_rachunku"),
            ("Odbiorca", "payee"),
            ("Rachunek odbiorcy", "na_rachunek"),
            ("Kwota", "kwota"),
            ("Data operacji", "data_operacji"),
            ("Tytuł przelewu", "tytul"),
            ("Numer referencyjny", "numer_transakcji"),
            ("Status", "status"),
            ("Opłata/prowizja", "fee"),
        ],
        left=68.4,
        split=210.1,
        right=530,
        size=8.5,
        rules=True,
    )
    r.footer(y + 10)


def _scan_participants(r):
    p = r.page
    p.section("stationery")
    p.text(33, 47, r.bank, size=15, bold=True)
    p.text(409, 44, "Obsługa klientów firmowych\nCentrum rozliczeniowe", size=8)
    p.line(33, 80, 560, 80)
    r.rows(95, [("Nazwa firmy", "payer")], left=34, split=104, size=8)
    y = r.heading("Potwierdzenie transakcji", left=33, y=141)
    p.section("transaction_details")
    y = r.stack(34, y + 13, "Opis", "tytul", size=9, width=519)
    ends = [
        r.stack(x, y + 6, label, key, width=width, size=9)
        for x, width, label, key in (
            (34, 134, "Kwota", "kwota"),
            (210, 133, "Data transakcji", "data_operacji"),
            (395, 161, "Numer referencyjny transakcji", "numer_transakcji"),
        )
    ]
    y = p.text(34, max(ends) + 8, "Typ transakcji / Kod\n225  PRZELEW INTERNETOWY", size=8) + 15
    for section, title, party, account in (
        ("sender_panel", "Dane nadawcy", "payer", "z_rachunku"),
        ("recipient_panel", "Dane odbiorcy", "payee", "na_rachunek"),
    ):
        p.section(section)
        y = p.text(34, y, title, bold=True, size=12) + 5
        p.line(34, y - 1, 560, y - 1)
        name_end = r.stack(34, y + 3, "Nazwa i adres", party, width=157, size=8)
        acct_end = r.stack(210, y + 3, "Numer rachunku", account, width=183, size=8)
        p.text(413, y + 3, "Nazwa banku", size=7, bold=True)
        p.text(413, y + 16, r.bank, size=8)
        y = max(name_end, acct_end) + 19
    r.footer(y + 8)


def _scan_history(r):
    p = r.page
    p.section("statement_header")
    p.text(38, 45, r.bank, size=18, bold=True)
    p.text(38, 92, "Data wydruku:  " + r.v["printed"] + "   godz. 17:24", size=9)
    p.section("history_columns")
    for x, label in ((38, "Data"), (154, "Opis"), (496, "Kwota")):
        p.text(x, 133, label, size=10, bold=True)
    p.line(38, 151, 564, 151)
    p.section("dates")
    y = r.stack(38, 158, "Data operacji", "data_operacji", width=105, size=9)
    r.stack(38, y + 9, "Data księgowania", "printed", width=105, size=9)
    p.section("details")
    y = p.text(154, 158, "PRZELEW ELIXIR – ONLINE", size=10, bold=True) + 6
    for label, key, party in (("Z rachunku", "z_rachunku", "payer"), ("Na rachunek", "na_rachunek", "payee")):
        y = r.stack(154, y, label, key, width=312, size=9)
        y = r.value(154, y, party, width=312, size=9) + 8
    y = r.stack(154, y, "Tytuł:", "tytul", width=307, size=9)
    r.stack(154, y, "Identyfikator transakcji", "numer_transakcji", size=9)
    p.section("debit")
    p.text(484, 158, "−", size=9)
    r.value(490, 158, "kwota", size=9, width=80)
    r.footer(733)


def _scan_order(r):
    p = r.page
    p.section("bank_brand")
    p.text(44, 49, r.bank, size=16, bold=True)
    y = r.heading("Przelew krajowy", left=44, y=91)
    p.text(44, y + 2, "Transakcja złożona za pośrednictwem systemu bankowości internetowej", size=8)
    p.section("order_header")
    y = p.text(44, y + 28, "Szczegóły zlecenia", bold=True, size=13)
    y = p.text(44, y + 3, "Typ zlecenia        Przelew krajowy\nStan zlecenia       Wykonane", size=8) + 10
    for name, title, items in (
        (
            "ordering_customer",
            "Dane zleceniodawcy",
            [("Rachunek zleceniodawcy", "z_rachunku"), ("Nazwa zleceniodawcy", "payer")],
        ),
        ("counterparty", "Dane kontrahenta", [("Rachunek kontrahenta", "na_rachunek"), ("Nazwa kontrahenta", "payee")]),
        (
            "payment_order",
            "Dane zlecenia",
            [
                ("Kwota", "kwota"),
                ("Zlecona data wykonania", "data_operacji"),
                ("Szczegóły płatności", "tytul"),
                ("Numer referencyjny", "numer_transakcji"),
            ],
        ),
    ):
        p.section(name)
        y = p.text(44, y, title, size=12, bold=True) + 2
        y = r.rows(y, items, left=44, split=180, size=8.5) + 7
    p.section("signature_caption")
    p.text(
        44, 713, "Dokument podpisany elektronicznie przez " + r.bank + "\nData wystawienia: " + r.v["printed"], size=8
    )
    r.footer(765)


def _scan_operation(r):
    p = r.page
    p.section("issuer")
    p.text(54, 44, r.bank + "\nSerwis klientów firmowych", size=9)
    p.section("account_owner")
    y = r.rows(93, [("Właściciel rachunku", "payer"), ("Data wydruku", "printed")], left=119, split=239, size=9)
    p.line(48, y, 543, y)
    p.section("operation_details")
    y = p.text(50, y + 9, "Przelew z rachunku        Szczegóły transakcji", bold=True, size=12) + 11
    y = r.rows(
        y,
        [("Numer rachunku", "z_rachunku"), ("Data waluty", "printed"), ("Data operacji", "data_operacji")],
        left=51,
        split=204,
        size=9,
    )
    p.section("description")
    p.text(51, y + 8, "Opis", bold=True, size=9)
    y = r.stack(204, y + 8, "Rachunek odbiorcy:", "na_rachunek", size=9, width=312)
    y = r.stack(204, y + 5, "Nazwa odbiorcy:", "payee", size=9, width=312)
    y = r.stack(204, y + 5, "Tytuł:", "tytul", size=9, width=312)
    y = r.stack(204, y + 5, "Nr transakcji:", "numer_transakcji", size=9, width=312)
    p.section("settlement")
    p.text(51, y + 8, "Typ transakcji", size=9, bold=True)
    p.text(204, y + 8, "Przelew z rachunku", size=9)
    r.rows(y + 31, [("Kwota", "kwota")], left=51, split=204, size=9)
    r.footer(759)


def _scan_bordered(r):
    p = r.page
    p.section("issuer")
    p.text(32, 48, r.bank, size=16, bold=True)
    y = r.heading("Transakcja złożona poprzez usługi bankowości elektronicznej", left=32, y=108, size=11)
    p.section("transaction_grid")
    r.rows(
        y + 11,
        [
            ("Rachunek nadawcy", "z_rachunku"),
            ("Dane nadawcy", "payer"),
            ("Rachunek odbiorcy", "na_rachunek"),
            ("Dane odbiorcy", "payee"),
            ("Tytułem", "tytul"),
            ("Kwota przelewu", "kwota"),
            ("Data wykonania", "data_operacji"),
            ("Kanał", "channel"),
            ("Numer transakcji", "numer_transakcji"),
        ],
        left=36,
        split=124,
        right=444,
        size=8.5,
        border=True,
    )
    r.footer(751)


_RENDERERS = {
    "early_order": _early_order,
    "early_cards": _early_cards,
    "early_thermal": _early_thermal,
    "early_summary": _early_summary,
    "early_letter": _early_letter,
    "early_sections": _early_sections,
    "early_register": _early_register,
    "late_table": _late_table,
    "scan_participants": _scan_participants,
    "scan_history": _scan_history,
    "scan_order": _scan_order,
    "scan_operation": _scan_operation,
    "scan_bordered": _scan_bordered,
}
RECEIPTS = tuple(_RENDERERS)


def render_receipt(page, case, family):
    _RENDERERS[family](_Receipt(page, case))
