"""Polish procurement pleadings. All example narratives and case evidence are synthetic."""

from datetime import date, timedelta

APPEALS = ("early-modular", "late-list")
MANDATES = (
    "early-paragraphs",
    "early-register",
    "early-procedural",
    "early-letterhead",
    "early-panels",
    "early-short",
    "late-company",
    "late-consortium",
    "late-trader",
)

_MONTHS = (
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
)

# Narrative sentence, late enumerated allegation, disputed evidence, proposed corrective act.
_ACTIONS = {
    1: (
        "odrzucił ofertę odwołującego",
        "odrzucenie oferty naszego klienta mimo wykazania zgodności świadczenia",
        "rubryka z wynikiem próby i karta badania, w których użyto różnych jednostek",
        "przywrócić ofertę do badania i przeliczyć wynik próby we wspólnej jednostce",
    ),
    2: (
        "ogłosił wybór najkorzystniejszej oferty",
        "wybór oferty konkurenta po błędnym zsumowaniu punktów",
        "wiersz arkusza oceny, w którym do wyniku końcowego dwukrotnie dodano tę samą premię",
        "usunąć powtórzoną pozycję i odtworzyć kolejność ofert według opublikowanych wag",
    ),
    3: (
        "wykluczył odwołującego z postępowania",
        "wykluczenie wykonawcy ze względu na rzekomą nierzetelność",
        "protokół odbioru i aneks wskazujący, kto odpowiadał za zmianę terminu",
        "uchylić wykluczenie i ocenić dokumenty dotyczące przyczyn zmiany terminu",
    ),
    4: (
        "opublikował specyfikację warunków zamówienia",
        "ogłoszenie SWZ zawierającej sprzeczne instrukcje kalkulacji",
        "tabela ilości oraz formularz ceny przewidujące odmienne okresy rozliczeniowe",
        "ujednolicić okres rozliczeniowy w specyfikacji i formularzu ofertowym",
    ),
    5: (
        "zmienił treść SWZ",
        "zmianę specyfikacji bez dostosowania załącznika cenowego",
        "nowa wersja opisu zakresu i pozostawiony w dokumentacji poprzedni formularz",
        "udostępnić skorygowany załącznik wraz z terminem pozwalającym na ponowną kalkulację",
    ),
    6: (
        "udzielił wyjaśnień treści SWZ",
        "udzielenie odpowiedzi, która przypisała temu samemu wymaganiu dwa znaczenia",
        "pytanie dotyczące rozliczeń i odpowiedź odsyłająca do dwóch różnych wierszy formularza",
        "jednoznacznie wskazać właściwy wariant i opublikować odpowiedź dla wszystkich zainteresowanych",
    ),
    7: (
        "zaniechał odrzucenia oferty konkurenta",
        "pozostawienie w ocenie oferty niespełniającej warunku minimalnego",
        "załącznik konkurenta deklarujący wartość poniżej granicy oznaczonej jako obowiązkowa",
        "zbadać zgodność zadeklarowanego parametru i rozstrzygnąć o odrzuceniu oferty",
    ),
    8: (
        "zaniechał wykluczenia innego wykonawcy",
        "zaniechanie wykluczenia konkurenta po ujawnieniu sprzeczności oświadczeń",
        "dwa oświadczenia o wykonaniu tej samej umowy zawierające odmienne daty odbioru",
        "ponownie zbadać podstawę wykluczenia przy uwzględnieniu obu oświadczeń",
    ),
    9: (
        "unieważnił postępowanie",
        "unieważnienie postępowania z powołaniem się na usuwalną wadę",
        "notatka komisji i jej załącznik pokazujący możliwość ponowienia wadliwej czynności",
        "uchylić unieważnienie i wrócić do ostatniej prawidłowo przeprowadzonej czynności",
    ),
    10: (
        "zaniechał unieważnienia postępowania",
        "dalsze prowadzenie procedury mimo wady wymagającej jej unieważnienia",
        "dwie udostępnione po terminie wersje obligatoryjnego załącznika o rozbieżnej treści",
        "ustalić nieusuwalność wady i unieważnić postępowanie",
    ),
    11: (
        "przedstawił opis przedmiotu zamówienia",
        "opisanie przedmiotu przez wskazanie rozwiązania jednego producenta",
        "karta cechy technicznej i pominięty w niej mierzalny parametr równoważności",
        "określić właściwość użytkową oraz sposób wykazania równoważności oferowanego rozwiązania",
    ),
    12: (
        "udostępnił projektowane postanowienia umowy",
        "ukształtowanie postanowień umownych przenoszących nieoznaczone ryzyko",
        "projekt umowy dopuszczający przesunięcie terminu odbioru bez rozliczenia kosztów gotowości",
        "oznaczyć granice przesunięcia odbioru i sposób rozliczenia udokumentowanych kosztów gotowości",
    ),
}


def _date(iso):
    d = date.fromisoformat(iso)
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year} r."


def _before(iso, days):
    return _date((date.fromisoformat(iso) - timedelta(days=days)).isoformat())


def _flow(page, y, *parts, x=52, width=490, size=10.5):
    """Keep tagged source phrases intact when possible, breaking at real spaces."""
    cursor = x
    bottom = y
    space = page.measure(" ", size=size)
    for part in parts:
        value, role = part if isinstance(part, tuple) else (part, None)
        if value is None or value == "":
            continue
        words = str(value).split()
        # A gold phrase stays in a single box if it fits on a fresh line.
        if role and page.measure(str(value), size=size) <= width:
            words = [str(value)]
        while words:
            line = []
            while words:
                candidate = " ".join([*line, words[0]])
                if cursor + page.measure(candidate, size=size) > x + width and (line or cursor > x):
                    break
                line.append(words.pop(0))
            if line:
                chunk = " ".join(line)
                bottom = page.text(cursor, y, chunk, size=size, width=page.measure(chunk, size=size) + 1.5, role=role)
                cursor += page.measure(chunk, size=size) + space
            if words:
                cursor, y = x, bottom
    return bottom


def _p(page, y, text, size=11, x=52, width=490):
    return page.text(x, y, text, size=size, width=width) + 7


def _heading(page, y, name, caption):
    page.section(name)
    return page.text(52, y, caption, bold=True, size=12.5, width=490) + 7


def _footer(page, index, total, procedure=None):
    page.section("footer")
    if procedure:
        page.text(52, 803, f"Odwołanie w sprawie {procedure}", size=8, width=365, role="footer.procedure")
    page.text(435, 803, f"Strona {index} z {total}", width=107, size=8, role="footer.pagination")


def _identifier_parts(record, prefix):
    parts = []
    for key in ("krs", "nip", "regon"):
        if record.get(key):
            parts.extend([key.upper(), (record[key], f"{prefix}.{key}")])
    return parts


def _party(page, case, y, side, late):
    a = case["appeal"]
    appellant = side == "Odwolujacy"
    headings = ("Odwołujący:", "Zamawiający:")
    if late and case["index"] % 3 != 0:
        headings = ("Dane odwołującego", "Dane zamawiającego")
    page.section(side)
    y = page.text(52, y, headings[0 if appellant else 1], size=10.5, bold=True)
    for i, record in enumerate(a[side]):
        base = f"{side}.{i}"
        leader = record.get("prowadzacy_postepowanie")
        if leader is not None:
            y = page.text(
                52,
                y,
                "Prowadzący postępowanie" if leader else "Pozostały zamawiający",
                size=9,
                role=base + ".prowadzacy_postepowanie",
            )
        y = page.text(52, y, record["nazwa"], size=10.5, role=base + ".nazwa")
        street = "ul. Łąkowa" if appellant else "ul. Spacerowa"
        town = (
            (case["appeal"]["OdwolanieKIO"].get("miejscowosc") or "Tarnów")
            if appellant
            else record["nazwa"].split()[-1]
        )
        y = page.text(52, y, f"{street} {9 + (case['index'] + i) % 47}, {town}", size=9.5, role=f"party-address.{base}")
        y = _flow(page, y, *_identifier_parts(record, base), size=9.5)
        if appellant and late:
            for n, member in enumerate(case["mandate"]["mocodawca"][1:], 1):
                partner = member["data"]
                y = _flow(page, y, "Partner konsorcjum:", (partner["nazwa"], f"consortium.partner.{n}.name"))
                if partner.get("nip"):
                    y = _flow(page, y, "NIP partnera", (partner["nip"], f"consortium.partner.{n}.nip"), size=9.5)
        if appellant and record.get("pelnomocnik"):
            counsel = record["pelnomocnik"]
            y = _flow(
                page,
                y,
                ("Reprezentowany przez:", base + ".przez-pelnomocnika"),
                "r. pr.",
                (counsel["imie_nazwisko"], base + ".pelnomocnik.imie_nazwisko"),
            )
            if counsel.get("nazwa"):
                y = _flow(page, y, "Adres do korespondencji:", (counsel["nazwa"], base + ".pelnomocnik.nazwa"))
            if counsel.get("mail"):
                y = _flow(page, y, "e-mail:", (counsel["mail"], base + ".pelnomocnik.mail"))
    return y + 9


def _subject(page, case, y, late):
    proc = case["appeal"]["ZamowieniePubliczne"]
    page.section("procurement")
    y = page.text(
        52,
        y,
        "Dotyczy postępowania o udzielenie zamówienia publicznego pn." if late else "Dotyczy:",
        bold=True,
        size=10,
    )
    y = page.text(52, y, f"„{proc['tytul']}”", size=10.5, role="ZamowieniePubliczne.tytul")
    for key, label in (
        ("numer_postepowania", "Nr referencyjny"),
        ("numer_bzp", "Ogłoszenie BZP"),
        ("numer_ted", "Ogłoszenie TED"),
    ):
        if proc.get(key):
            y = _flow(page, y, label, (proc[key], "ZamowieniePubliczne." + key), size=9.5)
    return y + 9


_EARLY_ORDER = (
    "RACHT",
    "RCATH",
    "HRATC",
    "RACTH",
    "RTACH",
    "HARCT",
    "RHCAT",
    "ARCTH",
    "RCHAT",
    "TRACH",
    "RHATC",
)


def _opening(page, case, late):
    appeal = case["appeal"]["OdwolanieKIO"]
    idx = case["index"]
    y = 42
    page.section("filing")
    locality = appeal.get("miejscowosc")
    if locality or appeal.get("data"):
        parts = [(locality, "OdwolanieKIO.miejscowosc")]
        if appeal.get("data"):
            parts.extend(["dnia", (_date(appeal["data"]), "OdwolanieKIO.data")])
        y = _flow(page, y, *parts, x=282, width=260) + 12
    order = ("RCATH" if idx % 2 else "RACTH") if late else _EARLY_ORDER[idx % len(_EARLY_ORDER)]
    for block in order:
        if block == "R":
            page.section("addressee")
            y = (
                page.text(
                    283 if idx % 2 else 52,
                    y,
                    "Prezes Krajowej Izby Odwoławczej\nul. Postępu 17A\n02-676 Warszawa",
                    size=10,
                    width=260,
                )
                + 8
            )
        elif block in ("A", "C"):
            y = _party(page, case, y, "Odwolujacy" if block == "A" else "Zamawiajacy", late)
            if late and block == "C" and appeal["czynnosc_powod_id"] in (2, 7, 8):
                page.section("competing-bidder")
                y = _p(
                    page,
                    y,
                    f"Wykonawca, którego oferty dotyczy zarzut:\nPracownia Pomiarów Równoległych {idx} sp. z o.o.",
                    size=10,
                )
        elif block == "T":
            y = _subject(page, case, y, late)
            if late:
                receipt = case["receipt"]["przelew_bankowy"]
                fee = receipt["kwota"] if case["payment_purpose"] == "appeal" else 7500
                y = (
                    page.text(
                        52,
                        y,
                        f"Wpis od odwołania: {fee:,.2f} zł".replace(",", " ").replace(".", ","),
                        size=10,
                        role="appeal-entry-fee",
                    )
                    + 6
                )
        else:
            page.section("appeal-heading")
            y = (
                page.text(
                    205, y, "ODWOŁANIE" if late or idx % 2 else "O D W O Ł A N I E", size=15, bold=True, width=310
                )
                + 11
            )
    return y


def _action_info(case):
    a = case["appeal"]["OdwolanieKIO"]
    return a, _ACTIONS[a["czynnosc_powod_id"]]


def _action(page, case, y, late):
    a, words = _action_info(case)
    head = "1) Jako pierwszą czynność zaskarżamy:" if late else "Zamawiający"
    parts = [head]
    if not late and a.get("czynnosc_dzien"):
        parts.extend(["w dniu", (_date(a["czynnosc_dzien"]), "OdwolanieKIO.czynnosc_dzien")])
    parts.append((case.get("challenge_text", words[1]) if late else words[0], "OdwolanieKIO.czynnosc_powod_id"))
    if late and a.get("czynnosc_dzien"):
        parts.extend(
            ["– o tej czynności powzięto wiadomość w dniu", (_date(a["czynnosc_dzien"]), "OdwolanieKIO.czynnosc_dzien")]
        )
    return _flow(page, y, *parts, size=11) + 7


def _signature(page, case, y):
    page.section("appeal-signature")
    name = case["appeal"]["Odwolujacy"][0].get("pelnomocnik") or {}
    if name.get("imie_nazwisko"):
        y = _p(page, y, "W imieniu odwołującego", size=10)
        y = page.text(52, y, name["imie_nazwisko"], size=11, role="Odwolujacy.0.pelnomocnik.imie_nazwisko")
    return _p(page, y + 3, "Podpis złożono elektronicznie.", size=9)


def _early(page, case):
    idx = case["index"]
    total = 3 if idx % 5 == 0 else 2
    _, words = _action_info(case)
    y = _opening(page, case, False)
    page.section("challenged-action")
    y = _p(
        page,
        y,
        "W imieniu wykonawcy wnoszę odwołanie do Izby. Pełnomocnictwo obejmujące tę sprawę "
        "załączam do pisma. Przedmiotem zaskarżenia jest opisana poniżej czynność zamawiającego.",
    )
    y = _action(page, case, y, False)
    y = _heading(page, y, "charge-one", "Zarzut pierwszy")
    y = _p(
        page,
        y,
        f"Stanowisko zamawiającego nie uwzględnia pełnej treści akt. Rozbieżność ujawnia następujący materiał: "
        f"{words[2]}. Żadna z przekazanych wykonawcy informacji nie wyjaśnia, dlaczego przyjęto tylko jeden sposób "
        "odczytania tego materiału.",
    )
    _footer(page, 1, total)
    page.new_page()
    y = _heading(page, 52, "charge-two", "Zarzut drugi – pominięcie istotnej części dokumentacji")
    y = _p(
        page,
        y,
        "Zespół przygotowujący ofertę zestawił źródłowe dokumenty z treścią komunikatu. "
        "Fragment przywołany w komunikacie kończy się przed zastrzeżeniem, które ogranicza jego zastosowanie. "
        "Dopiero odczytanie obu części razem pozwala ustalić znaczenie spornego zapisu.",
    )
    y = _p(
        page,
        y,
        "Wykonawcy otrzymali tę samą dokumentację. Każdy powinien móc przewidzieć, które dane będą "
        "rozstrzygające. Dopisanie do opublikowanych warunków niewyrażonego w nich założenia zmienia ciężar "
        "przygotowania oferty i może wpłynąć na wynik postępowania.",
    )
    y = _heading(page, y, "relief", "Wnioski odwołania")
    y = _p(
        page,
        y,
        f"1. Wnoszę o uwzględnienie odwołania i nakazanie zamawiającemu, aby w ramach usunięcia naruszenia "
        f"podjął następujące czynności: {words[3]}.",
    )
    y = _p(page, y, "2. Wnoszę o rozpoznanie sprawy na rozprawie i zasądzenie kosztów według złożonego rachunku.")
    y = _heading(page, y, "evidence", "Dowody i okoliczności wymagające ustalenia")
    y = _flow(
        page,
        y,
        "Wnoszę o dopuszczenie plików z platformy na okoliczność tego, że zamawiający",
        (words[0] + ".", "OdwolanieKIO.czynnosc_opis"),
    )
    y = _p(
        page,
        y,
        "Potwierdzenie pobrania dokumentów załączono wyłącznie dla wykazania "
        "ich pochodzenia. Data zapisania wyciągu nie oznacza daty zaskarżonej czynności.",
    )
    if total == 3:
        _footer(page, 2, total)
        page.new_page()
        y = _heading(page, 52, "service", "Doręczenie odpisu i wykaz załączników")
        y = _p(
            page,
            y,
            "Odpis pisma z kompletem załączników przekazano zamawiającemu przez platformę. W wykazie "
            "plików wskazano osobno dokument obejmujący umocowanie i potwierdzenie płatności. Oryginał archiwum "
            "dowodowego pozostaje dostępny na potrzeby oględzin.",
        )
    else:
        y = _heading(page, y, "annexes", "Załączniki")
    y = _p(
        page,
        y,
        "a) pełnomocnictwo do występowania przed KIO,\n"
        "b) wyciąg z dokumentacji wraz z komunikatem zamawiającego,\nc) potwierdzenie przekazania odpisu odwołania.",
    )
    _signature(page, case, y + 10)
    _footer(page, total, total)


# Each page addresses a different question. Braced terms refer to evidence in this case.
_LONG_BRIEF = (
    (
        "evidence-motions",
        "I. Wnioski dowodowe",
        (
            (
                "Zakres materiału",
                "Wnosimy o zażądanie pełnego elektronicznego tomu dotyczącego sprawy {ref}. W przekazanym stronom wyciągu widoczny jest komunikat końcowy, lecz brak historii załącznika, z którego zaczerpnięto przesłankę rozstrzygnięcia. Izba powinna mieć dostęp zarówno do poprzedniej wersji pliku, jak i do wersji, do której prowadzi obecny odsyłacz.",
            ),
            (
                "Dowód nr 1 – paczka opublikowana na platformie",
                "Wnosimy o otwarcie paczki w pierwotnym układzie folderów. Lista nazw i rozmiarów pozwala stwierdzić, czy załącznik stanowił część ogłoszonego kompletu. Sam wydruk jednej strony nie pozwala rozstrzygnąć tej kwestii, ponieważ jego nagłówek powstał dopiero podczas drukowania.",
            ),
            (
                "Dowód nr 2 – korespondencja",
                "W pliku z wiadomościami zaznaczono wypowiedź zespołu zakupowego i pytanie, którego dotyczyła. Wnosimy o odczytanie obu fragmentów łącznie. Odczytanie odpowiedzi bez pytania sugeruje szerszy zakres stanowiska, niż rzeczywiście wynika z wymiany zdań.",
            ),
            (
                "Dowód nr 3 – porównanie dokumentów",
                "Źródłem rozbieżności jest {exhibit}. Sporządzona przez wykonawcę tabela wskazuje dla każdego cytowanego miejsca numer załącznika i rubrykę, a obok podaje wynik odczytu po uwzględnieniu dalszej części dokumentu. Tabela ułatwia odnalezienie materiału źródłowego, który podlega samodzielnej ocenie Izby.",
            ),
            (
                "Sposób przeprowadzenia dowodu",
                "Na rozprawie pliki można okazać bez łączenia się z platformą. W razie zakwestionowania kompletności kopii wnosimy o porównanie jej z plikiem przechowywanym przez administratora i odnotowanie w protokole, które strony były dostępne dla wykonawców.",
            ),
        ),
    ),
    (
        "chronology",
        "II. Przebieg postępowania i obieg informacji",
        (
            (
                "Przedmiot sprawy",
                "Postępowaniu nadano znak {ref}. Jego przedmiot określono jako „{title}”. Dokumentacja obejmuje opis świadczenia, formularz do wypełnienia przez wykonawcę oraz instrukcję przekazania plików. Dla sporu istotne jest, że wskazane części opublikowano we wspólnej paczce i przypisano im odrębne nazwy.",
            ),
            (
                "Pierwszy zapis w aktach",
                "W dniu {older} zamieszczono informację techniczną o sposobie dostępu do plików. Komunikat mówił o konieczności ponownego zalogowania i zawierał odnośnik do strony głównej. Nie rozstrzygał żadnej z kwestii objętych odwołaniem. Wykonawca zachował go, gdyż wyjaśnia przerwę w historii pobierania dokumentacji.",
            ),
            (
                "Kontrola dokumentacji",
                "Dnia {nearer} pracownik odpowiedzialny za analizę dokumentów zestawił podpisy plików z wykazem zamieszczonym na stronie. Zapisał wynik w roboczej notatce. Taki zapis pochodzi z wewnętrznego obiegu wykonawcy i wskazuje jedynie dzień porządkowania akt; nie potwierdza doręczenia późniejszej czynności.",
            ),
            (
                "Powzięcie wiadomości",
                "Właściwy przedmiot skargi określono w punkcie pierwszym wykazu czynności. Oświadczenie dotarło na konto przypisane do postępowania. Zespół zachował oryginalny plik oraz potwierdzenie, które wiąże go z kontem wykonawcy. Z tego względu można ustalić, jaka dokładnie treść była dostępna adresatowi.",
            ),
            (
                "Rozdzielenie dokumentów",
                "Kolejne ustalenia zespołu prawnego nie zmieniły treści doręczonej informacji. Pracownicy sporządzili porównanie załączone do pisma na podstawie danych już zapisanych w systemie. Wykaz operacji informatycznych służy ustaleniu kolejności zapisów, a nie zastąpieniu treści doręczanego dokumentu.",
            ),
        ),
    ),
    (
        "interest",
        "III. Interes wykonawcy i możliwość poniesienia szkody",
        (
            (
                "Pozycja skarżącego",
                "Podmiot wskazany w komparycji działa we własnym interesie gospodarczym. Na potrzeby postępowania wyznaczył zespół przygotowujący kalkulację i zarezerwował czas specjalistów. Rezultat procedury wpływa na możliwość wykorzystania tych zasobów przy realizacji objętego nią świadczenia.",
            ),
            (
                "Związek z zamówieniem",
                "Przedmiot zamówienia odpowiada zakresowi działalności prowadzonej przez wykonawcę. W dokumentacji roboczej przyporządkowano poszczególne zadania osobom odpowiedzialnym za ich realizację. Dołączony wyciąg pokazuje związek prac przygotowawczych z tym postępowaniem, ponieważ zawiera jego znak {ref}.",
            ),
            (
                "Mechanizm szkody",
                "Jeśli wadliwe stanowisko utrzyma się, wykonawca utraci możliwość ubiegania się o zamówienie na podstawie tych samych, sprawdzalnych zasad co pozostali zainteresowani. Przywrócenie takiej możliwości jest wartością samodzielną. Ostateczny wynik procedury będzie zależał również od dalszych czynności zamawiającego.",
            ),
            (
                "Zakres żądania",
                "Skarżący nie żąda przyznania mu kontraktu w orzeczeniu. Domaga się usunięcia przeszkody na etapie, na którym powstała. Rozstrzygnięcie może zatem poprawić jego sytuację bez przesądzania kwestii, które w dalszym toku postępowania pozostają do oceny zamawiającego.",
            ),
            (
                "Związek przyczynowy",
                "Zestawienie obu wariantów przedstawiamy w dalszym uzasadnieniu. W pierwszym utrzymuje się skutek wynikający z jednostronnego odczytania spornego materiału. W drugim przywraca się kontrolę nad podstawą czynności. Różnica dotyczy rzeczywistego dostępu do zamówienia i daje się sprawdzić w aktach tej konkretnej sprawy.",
            ),
        ),
    ),
    (
        "first-ground",
        "IV. Uzasadnienie zarzutu pierwszego",
        (
            (
                "Przedmiot oceny",
                "Pierwszy zarzut dotyczy czynności wskazanej w petitum pisma. Zawiadomienie przytacza wynik rozumowania zamawiającego, lecz nie wskazuje, jak rozwiązano rozbieżność dostrzeżoną przez wykonawcę. Uzasadnienie przesłane uczestnikom pozwala odnaleźć w aktach jedynie jeden z dokumentów odnoszących się do tej okoliczności.",
            ),
            (
                "Sporny dokument",
                "W aktach znajduje się {exhibit}. Zestawienie ma znaczenie, gdyż w żadnym miejscu zawiadomienia nie wskazano, że pominięty fragment dotyczy innej części zamówienia albo że zastąpiono go później nową wersją. Do czasu wyjaśnienia tej kwestii nie można zachować samego wyniku z pominięciem przesłanek jego przyjęcia.",
            ),
            (
                "Stanowisko komisji",
                "W przywołanej notatce komisja posłużyła się skróconym opisem. Skrót mógł służyć wewnętrznej wymianie informacji, jednak jego treść nie zastępuje wskazania konkretnej rubryki źródłowej. Wykonawca nie miał dostępu do roboczych ustaleń osób tworzących notatkę i może opierać swoje stanowisko wyłącznie na dokumentach, które mu udostępniono.",
            ),
            (
                "Kontrola ustalenia",
                "Należy prześledzić drogę od zapisu źródłowego do rozstrzygnięcia i wskazać moment, w którym pojawia się dodatkowe założenie. Jeżeli po odjęciu tego założenia wniosek przestaje wynikać z akt, nie można utrzymać go wyłącznie na podstawie zapewnienia o starannym przebiegu prac komisji.",
            ),
            (
                "Skutek uchybienia",
                "Wnosimy więc, by zamawiającemu nakazać: {remedy}. Wniosek dotyczy wyniku konkretnej czynności i może zostać wykonany przy wykorzystaniu dokumentacji przechowywanej w aktach. Nie wymaga on od Izby zastąpienia komisji w czynnościach powierzonych jej po wydaniu orzeczenia.",
            ),
        ),
    ),
    (
        "second-ground",
        "V. Uzasadnienie zarzutu dotyczącego przejrzystości",
        (
            (
                "Adresat informacji",
                "Dokumenty przeznaczono dla wykonawców działających samodzielnie, z różnym doświadczeniem w korzystaniu z platformy. Każdy z nich powinien móc ustalić znaczenie opublikowanej treści bez dostępu do wyjaśnień przekazywanych indywidualnie w rozmowie telefonicznej. Instrukcja nie wskazywała, że w spornym miejscu stosuje się inne zasady lektury.",
            ),
            (
                "Odtwarzalność wyniku",
                "Skarżący powierzył dwóm członkom zespołu niezależne odczytanie tej samej części akt. Pierwsza osoba zaczęła od instrukcji, druga od formularza. W arkuszu porównania zachowano oba przebiegi pracy, w tym miejsca, w których konieczne stało się poczynienie dodatkowego założenia. Materiał ten ilustruje charakter sprzeczności.",
            ),
            (
                "Granice uznania",
                "Zamawiający może wyznaczyć potrzebny mu rezultat i wskazać sposób potwierdzenia, że rezultat ten da się osiągnąć. Uzasadnienie powinno jednak pozwalać powiązać wymaganie z opisanym celem. W spornej części akt pominięto właśnie ten etap i równocześnie przypisano wykonawcom znajomość końcowej interpretacji.",
            ),
            (
                "Równy dostęp",
                "Dostęp do tej samej strony internetowej nie przesądza jeszcze o jednakowych warunkach ubiegania się o zamówienie. Znaczenie ma również to, czy opublikowane wyjaśnienie usuwa rozbieżność dla każdego użytkownika dokumentacji. Gdy niezbędne okazują się dodatkowe dane robocze, przewagę uzyskuje osoba znająca wcześniej sposób działania zespołu zakupowego.",
            ),
            (
                "Weryfikacja przez Izbę",
                "Wnosimy o porównanie treści obowiązującej w chwili czynności z treścią przywołaną w odpowiedzi na odwołanie. Element uzasadnienia przedstawiony po raz pierwszy na rozprawie może wyjaśnić stanowisko strony. Nie zmieni jednak zakresu informacji, który był dostępny wszystkim wykonawcom w toku postępowania.",
            ),
        ),
    ),
    (
        "objections",
        "VI. Odniesienie do przewidywanych zastrzeżeń",
        (
            (
                "Twierdzenie o omyłce technicznej",
                "Uznanie spornego zapisu za oczywistą omyłkę wymagałoby wskazania jednej poprawnej treści możliwej do ustalenia wprost z dokumentu. W tym przypadku alternatywne odczytanie daje inny wynik, a obie ścieżki mają oparcie w opublikowanych materiałach. Spór dotyczy wobec tego skutku przyjęcia określonej interpretacji.",
            ),
            (
                "Argument o przyjętej praktyce",
                "Przywołanie poprzednich postępowań nie usuwa rozbieżności. W tamtych procedurach mogły obowiązywać inne formularze, a wykonawcy mogli otrzymać inne wyjaśnienia. Jeżeli strona przeciwna powoła się na wcześniejszą praktykę, wnosimy o wskazanie zapisu przenoszącego ją do dokumentacji sprawy {ref}.",
            ),
            (
                "Znaczenie pełnego kontekstu",
                "Pojedyncze zdanie przytoczone z załącznika należy zestawić z nagłówkiem jego kolumny i objaśnieniem pod tabelą. Każdy z tych elementów pełni inną funkcję. Pominięcie któregoś z nich może zamienić dopuszczalny wariant w wymaganie bezwzględne lub przesłankę zastosowaną wobec jednego podmiotu w regułę ogólną.",
            ),
            (
                "Ciężar przygotowania odpowiedzi",
                "Odwołujący wskazuje fakty, z których wywodzi żądanie, oraz dokumenty do ich sprawdzenia. Jeżeli zamawiający dysponuje innym kompletem źródeł, powinien go zidentyfikować w sposób umożliwiający stronie odniesienie się do treści. Samo zapewnienie o posiadaniu bardziej szczegółowych danych nie rozstrzyga o ich związku ze sprawą.",
            ),
            (
                "Zakres istotnej rozbieżności",
                "Drobne różnice redakcyjne nie uzasadniają powtarzania czynności. Z tego względu w zestawieniu wyróżniono tylko miejsca wpływające na wniosek końcowy. Pozostałe różnice, takie jak numeracja stron po eksporcie czy skróty nazw plików, pozostawiono w wykazie wyłącznie po to, by można było odszukać oryginały.",
            ),
        ),
    ),
    (
        "corrective-steps",
        "VII. Wpływ uchybienia na wynik i sposób jego usunięcia",
        (
            (
                "Punkt wyjścia",
                "Środek naprawczy powinien przywrócić prawidłowy tok postępowania od etapu obarczonego wadą. Zachowanie wcześniejszych prawidłowych czynności skraca czas niezbędny do ponownego rozpoznania sprawy i ogranicza zakres ponownej pracy zarówno po stronie zamawiającego, jak i wykonawców.",
            ),
            (
                "Czynność do powtórzenia",
                "Właściwy sposób wykonania wniosku przedstawia się następująco: {remedy}. Dla kontroli wykonania orzeczenia należy zachować w aktach informację, jaka wersja dokumentu była punktem wyjścia i jaki element wymagał zmiany.",
            ),
            (
                "Warunek jawności",
                "Informacja o podjętym działaniu powinna zostać udostępniona tym samym kanałem, którym podano sporną wiadomość. W ten sposób każdy wykonawca dowie się o zmianie na jednakowych zasadach. Gdy poprawiony dokument składa się z kilku załączników, oznaczenie wyłącznie nazwy archiwum nie wystarczy do ustalenia, którego pliku dotyczy zmiana.",
            ),
            (
                "Zakres kontroli",
                "Nie ma potrzeby ponownego rozstrzygania zagadnień wykraczających poza oznaczony przedmiot sporu. Zamiast tego odpowiednia osoba powinna podpisać zestawienie czynności podjętych w wykonaniu orzeczenia i dołączyć źródła, które pozwalają zweryfikować wynik. Odwołujący będzie mógł wówczas ocenić, czy usunięto konkretną przeszkodę.",
            ),
            (
                "Rozliczenie kosztów",
                "Zgłaszamy wniosek o zwrot uzasadnionych kosztów postępowania. Rachunek pełnomocnika zostanie przedłożony na rozprawie. Dokument potwierdzający opłatę od umocowania i rozliczenie wpisu pełnią w aktach odmienne funkcje. W ewidencji załączników przewidziano dla nich odrębne pozycje.",
            ),
        ),
    ),
    (
        "annex-index",
        "VIII. Wykaz załączników i oświadczenia końcowe",
        (
            (
                "A. Dokumenty reprezentacji",
                "Do odwołania dołączono dokument umocowania osób działających w imieniu wykonawcy. Podpisy na nim należy odczytywać w związku z oznaczeniem podmiotu, w którego imieniu zostały złożone. Osobno wskazano adres korespondencyjny pełnomocnika na potrzeby doręczeń w niniejszej sprawie.",
            ),
            (
                "B. Materiał z postępowania",
                "Kopie udostępnione przez skarżącego zawierają komunikat, wykaz jego załączników i zestawienie różnic ze źródłami. W spisie zachowano oryginalne nazwy oraz kolejność plików. Dzięki temu wydruk można skonfrontować z wersją elektroniczną bez korzystania z numeracji nadanej po scaleniu dokumentów.",
            ),
            (
                "C. Potwierdzenie przekazania odpisu",
                "Osobny plik zawiera pokwitowanie transmisji wraz z listą elementów przesyłki. Poświadcza ono, co przekazano drugiej stronie. Do ustalenia treści poszczególnych zarzutów służy podpisane odwołanie i dokumenty, do których odnosi się każdy wniosek dowodowy.",
            ),
            (
                "D. Dostępność dokumentów",
                "W razie potrzeby wykonawca przedstawi źródłowe pliki w ich pierwotnym formacie. Wersje wydrukowane przygotowano dla ułatwienia korzystania z nich podczas posiedzenia. Warstwa wizualna wydruku może nie pokazywać metadanych widocznych przy otwarciu oryginału.",
            ),
            (
                "Oświadczenie",
                "Podtrzymujemy żądania w granicach punktów wymienionych na początku pisma. Wnosimy o doręczenie zawiadomienia o terminie posiedzenia na adres pełnomocnika wykazany w części wstępnej i o umożliwienie stronie wypowiedzenia się co do dowodów dołączonych później przez pozostałych uczestników.",
            ),
        ),
    ),
)


# Entries from the work papers accompany the argument to which they relate.
_EXHIBITS = {
    "evidence-motions": (
        "Indeks dowodów przekazanych w postaci elektronicznej",
        (
            (
                "A-1 / archiwum",
                "Komplet udostępnionych plików z zachowaniem oryginalnych nazw. Pozwala ustalić powiązania między dokumentami.",
            ),
            (
                "A-2 / wiadomości",
                "Eksport korespondencji dotyczącej sprawy {ref} wraz z nadawcami i godzinami przekazania.",
            ),
            (
                "A-3 / porównanie",
                "Arkusz wykonawcy. W ostatniej kolumnie wskazano, które założenie trzeba przyjąć, aby uzyskać wynik komisji.",
            ),
        ),
    ),
    "chronology": (
        "Wyciąg z rejestru udostępnień",
        (
            (
                "{older}",
                "Administrator opublikował komunikat informacyjny w części technicznej platformy. Zawiadomienie nie miało załączników.",
            ),
            (
                "{nearer}",
                "Zespół wykonawcy zapisał dostępny pakiet i porównał go z listą plików. Potwierdzenie zapisano razem z notatką.",
            ),
            (
                "Wiadomość w sprawie",
                "Treść rozstrzygnięcia zapisano pod odrębnym identyfikatorem. To do niej odsyła pierwszy punkt żądania.",
            ),
        ),
    ),
    "interest": (
        "Zestawienie nakładów bezpośrednio związanych ze sprawą",
        (
            (
                "Analiza zadania",
                "Przegląd wymagań powierzono osobie, która miała odpowiadać za organizację świadczenia. W aktach pozostaje jej karta robocza.",
            ),
            (
                "Kalkulacja",
                "Zespół zebrał informacje niezbędne do porównania wariantów realizacji. Ich przydatność zależy od przyjętej interpretacji warunków.",
            ),
            (
                "Dyspozycyjność",
                "W kalendarzu zespołu zarezerwowano czas na czynności związane z tym zamówieniem. Rezerwacja dotyczy okresu realizacji wskazanego w dokumentacji.",
            ),
        ),
    ),
    "first-ground": (
        "Zestawienie stanowisk co do materiału źródłowego",
        (
            (
                "Zakres sporu",
                "Wykonawca kwestionuje wniosek wywiedziony z części materiału. Potwierdza autentyczność dokumentów zamieszczonych na platformie.",
            ),
            (
                "Dalsza przesłanka",
                "Należy ustalić relację dwóch fragmentów: czy jeden doprecyzowuje drugi, czy ich jednoczesne zastosowanie prowadzi do sprzeczności.",
            ),
            (
                "Skutek dla sprawy",
                "Od odpowiedzi zależy dostępność środka naprawczego wskazanego w petitum. Dla obu wariantów podano te same źródła.",
            ),
        ),
    ),
    "second-ground": (
        "Porównanie dwóch sposobów lektury dokumentacji",
        (
            (
                "Od instrukcji",
                "Czytelnik zaczyna od warunku ogólnego. Dalsze rubryki traktuje jako jego konkretyzację i sięga po załącznik wskazany w głównym tekście.",
            ),
            (
                "Od formularza",
                "Czytelnik zaczyna od pola wymagającego uzupełnienia. Jego objaśnienia kierują do pomocniczej tabeli, która nie odsyła do zastrzeżenia w instrukcji.",
            ),
            (
                "Moment rozbieżności",
                "W obu przebiegach wykonano nakazane czynności, lecz nie odnaleziono zapisu rozstrzygającego pierwszeństwo kolidujących informacji.",
            ),
        ),
    ),
    "objections": (
        "Okoliczności bezsporne i wymagające wykazania",
        (
            (
                "Bezsporne",
                "Dokumenty pochodzą z tego samego postępowania i były umieszczone w katalogu udostępnionym wykonawcom.",
            ),
            (
                "Sporne",
                "Z opublikowanej treści obie strony wyprowadzają odmienne skutki. Rozbieżność zachodzi przed etapem formułowania wniosków o sposobie jej usunięcia.",
            ),
            (
                "Do ustalenia",
                "Wnosimy o oznaczenie zapisów przesądzających o przyjętym wyniku oraz sprawdzenie ich dostępności dla uczestników.",
            ),
        ),
    ),
    "corrective-steps": (
        "Czynności związane z wykonaniem orzeczenia",
        (
            (
                "Etap pierwszy",
                "Zidentyfikowanie wadliwej pozycji w dokumentacji. Oznaczenie źródła powinno pozwalać odszukać plik także po publikacji kolejnej wersji.",
            ),
            (
                "Etap drugi",
                "Ponowienie niezbędnych ustaleń. Informacja zamawiającego powinna odnosić się do każdego elementu, który wpłynął na rozstrzygnięcie.",
            ),
            (
                "Etap trzeci",
                "Poinformowanie uczestników o podjętych działaniach z podaniem miejsca udostępnienia poprawionych dokumentów i ich oznaczeń.",
            ),
        ),
    ),
    "annex-index": (
        "Sposób identyfikacji plików przesyłki",
        (
            ("Pakiet główny", "Odwołanie wraz ze spisem dowodów i wskazaniem żądanych czynności naprawczych."),
            (
                "Dokumenty towarzyszące",
                "Umocowanie, dowody powołane w piśmie i potwierdzenie przekazania kompletu drugiej stronie.",
            ),
        ),
    ),
}


def _exhibit(page, y, section, facts):
    caption, rows = _EXHIBITS[section]
    page.section(section + "-exhibit")
    y = page.text(52, y + 4, caption, size=11.5, bold=True) + 7
    for label, content in rows:
        page.line(52, y, 541, y)
        left = page.text(54, y + 5, label.format(**facts), width=122, size=9.5, bold=True)
        right = page.text(186, y + 5, content.format(**facts), width=349, size=10.5)
        y = max(left, right) + 7
    page.line(52, y, 541, y)
    return y + 8


def _late(page, case):
    a, words = _action_info(case)
    proc = case["appeal"]["ZamowieniePubliczne"]
    reference = proc["numer_postepowania"]
    total = 10 + case["index"] % 2
    y = _opening(page, case, True)
    page.section("scope")
    y = _p(
        page,
        y,
        "Jako pełnomocnik wykonawcy wnoszę odwołanie od czynności i zaniechań w postępowaniu "
        "wskazanym powyżej. Kwestionuję sposób odczytania dokumentacji i wynikający z niego skutek "
        "dla sytuacji mojego mocodawcy. Kolejność zaskarżonych czynności określam poniżej.",
    )
    _footer(page, 1, total, reference)
    page.new_page()
    y = _heading(page, 46, "challenged-actions", "Zaskarżone czynności i zaniechania")
    y = _action(page, case, y, True)
    y = _p(
        page,
        y,
        "2) Zaskarżamy również brak podania źródła ustalenia przyjętego przez komisję. "
        "Informacja na platformie nie pozwala ustalić, którą wersję materiału uwzględniono i gdzie "
        "umieszczono podstawę pozwalającą zweryfikować wniosek.",
    )
    y = _heading(page, y, "numbered-charges", "Zarzuty")
    y = _flow(
        page, y, "1. Zamawiający", (words[0], "OdwolanieKIO.czynnosc_opis"), "w oparciu o niepełną podstawę faktyczną."
    )
    y = _p(
        page,
        y,
        f"Przy rozstrzyganiu pominięto dokument dostępny komisji i istotny dla sprawy. "
        f"Sporny materiał stanowi {words[2]}.",
    )
    y = _p(
        page,
        y,
        "2. Naruszenie przejrzystości postępowania przez ujęcie wyniku w sposób, który uniemożliwia "
        "wykonawcy odtworzenie kolejnych przesłanek. Brakuje wskazania, jak usunięto rozbieżność między "
        "powiązanymi załącznikami i dlaczego odrzucono drugą możliwą interpretację.",
    )
    y = _heading(page, y, "requests", "Żądania i wnioski")
    y = _p(
        page,
        y,
        f"I. Wnosimy o uwzględnienie odwołania w zakresie obydwu zarzutów. Zamawiającemu należy nakazać, "
        f"aby podjął następujące działania: {words[3]}.",
    )
    y = _p(
        page,
        y,
        "II. Wnosimy o zobowiązanie zamawiającego do przekazania Izbie kompletnych akt i o "
        "dopuszczenie dowodów wymienionych w części pierwszej uzasadnienia. Uczestnicy powinni mieć "
        "możliwość odniesienia się do źródłowych wersji plików.",
    )
    _p(
        page,
        y,
        "III. Wnosimy o przeprowadzenie rozprawy i rozliczenie kosztów według rachunków złożonych "
        "przed zamknięciem rozprawy.",
    )
    _footer(page, 2, total, reference)
    anchor = a.get("czynnosc_dzien") or case["issue_date"]
    evidence = {
        "ref": reference,
        "title": proc["tytul"],
        "exhibit": words[2],
        "remedy": words[3],
        "older": _before(anchor, 19),
        "nearer": _before(anchor, 8),
    }
    for number, (section, title, paragraphs) in enumerate(_LONG_BRIEF, 3):
        page.new_page()
        y = _heading(page, 48, section, title)
        for subhead, paragraph in paragraphs:
            y = page.text(52, y + 3, subhead, bold=True, size=11.5) + 2
            y = _p(page, y, paragraph.format(**evidence), size=11.4)
        y = _exhibit(page, y, section, evidence)
        if number == total:
            _signature(page, case, y + 8)
        _footer(page, number, total, reference)
    if total == 11:
        page.new_page()
        page.section("certification")
        y = _p(
            page,
            65,
            "Za zgodność spisu z dokumentami przekazanymi wraz z odwołaniem odpowiada osoba "
            "podpisująca pismo w imieniu wykonawcy. Podpis odnosi się do odwołania w całości.",
        )
        _signature(page, case, y + 20)
        _footer(page, total, total, reference)


def render_appeal(page, case, family):
    if family == APPEALS[0]:
        _early(page, case)
    elif family == APPEALS[1]:
        _late(page, case)
    else:
        raise ValueError(f"Unknown appeal family {family!r}")


_EARLY_POWERS = (
    "wniesienia odwołania i przedstawienia stanowiska na posiedzeniu oraz rozprawie przed Krajową Izbą Odwoławczą",
    "zgłaszania dowodów, odbierania odpisów pism oraz zapoznawania się z aktami sprawy",
    "sporządzania odpowiedzi na pisma pozostałych uczestników oraz odbioru zawiadomień o terminach",
    "wniesienia skargi na orzeczenie Izby i reprezentowania mocodawcy przed sądem zamówień publicznych",
    "udzielenia dalszego umocowania adwokatowi lub radcy prawnemu na potrzeby tej sprawy",
)
_LATE_POWERS = (
    "podpisać i wnieść odwołanie, przedstawić jego uzasadnienie i przekazać odpis pozostałym stronom",
    "uczestniczyć w posiedzeniach oraz rozprawach, wypowiadać się co do dowodów i zadawać pytania świadkom",
    "odbierać zawiadomienia, przeglądać akta i zamawiać odpisy rozstrzygnięć dotyczących wskazanego zamówienia",
    "zaskarżyć orzeczenie Izby, złożyć odpowiedź na skargę i zastępować wykonawcę przed sądem",
    "powierzyć wykonanie czynności innemu radcy prawnemu albo adwokatowi w granicach niniejszego umocowania",
)


def _principal(page, y, principal, index, *, prefix=None, x=52, width=490):
    d = principal["data"]
    base = f"mocodawca.{index}.data"
    parts = [prefix] if prefix else []
    if d.get("imie_nazwisko"):
        parts += [(d["imie_nazwisko"], base + ".imie_nazwisko"), ("– działalność gospodarcza pod firmą", base + ".typ")]
    if d.get("nazwa"):
        parts.append((d["nazwa"], base + ".nazwa"))
    if d.get("typ") == "osoba_prawna":
        parts.append(("– spółka wpisana do rejestru przedsiębiorców", base + ".typ"))
    y = _flow(page, y, *parts, x=x, width=width)
    return _flow(page, y, *_identifier_parts(d, base), x=x, width=width, size=9.5)


def _attorneys(page, case, y, *, x=52, width=490, registration=False):
    for i, person in enumerate(case["mandate"]["pelnomocnicy"]):
        base = f"pelnomocnicy.{i}"
        parts = ["r. pr.", (person["imie_nazwisko"], base + ".imie_nazwisko")]
        if person.get("pesel"):
            parts += ["PESEL", (person["pesel"], base + ".pesel")]
        elif registration:
            parts += ["– nr wpisu", f"ŁD/{820 + 3 * case['index'] + i}"]
        y = _flow(page, y, *parts, x=x, width=width)
    return y


def _signatories(page, case, y, *, acceptance=False):
    page.section("principal-signatures")
    for i, principal in enumerate(case["mandate"]["mocodawca"]):
        d = principal["data"]
        y = page.text(
            52, y + 7, f"W imieniu {d['nazwa']}:" if d.get("nazwa") else "Podpis mocodawcy:", size=9.5, bold=True
        )
        for j, signer in enumerate(principal["podpisujacy"]):
            name = signer["imie_nazwisko"]
            page.line(52, y + 7, 235, y + 7)
            y = page.text(52, y + 9, name, size=10.5, role=f"mocodawca.{i}.podpisujacy.{j}.imie_nazwisko")
            if d.get("typ") == "osoba_prawna":
                y = page.text(52, y, "Osoba uprawniona do reprezentacji", size=8.5)
    if acceptance:
        page.section("counsel-acceptance")
        y = page.text(52, y + 7, "Pełnomocnictwo przyjmuję:", bold=True, size=9.5)
        y = _attorneys(page, case, y)
    return y


def _mandate_date(page, case, y, x=320):
    page.section("grant-date")
    return page.text(x, y, _date(case["issue_date"]), size=10, width=215, role="grant.issue_date") + 8


def _grant_title(page, y, text):
    page.section("mandate-heading")
    return page.text(102, y, text, size=15.5, width=444, bold=True) + 14


def _grant_subject(page, case, y):
    page.section("grant-procedure")
    proc = case["appeal"]["ZamowieniePubliczne"]
    authority = ", ".join(row["nazwa"] for row in case["appeal"]["Zamawiajacy"])
    y = _flow(
        page,
        y,
        "Postępowanie pn.",
        (f"„{proc['tytul']}”", "grant.procedure_title"),
        "– numer postępowania:",
        (proc["numer_postepowania"], "grant.procedure_number"),
    )
    return _flow(page, y, "Zamawiający:", (authority, "grant.authority")) + 8


def _powers(page, y, items, numbering):
    page.section("grant-scope")
    for i, item in enumerate(items):
        marker = {"letters": f"{chr(97 + i)})", "numbers": f"{i + 1}.", "bullets": "•"}[numbering]
        y = page.text(64, y, f"{marker} {item}.", size=10.5, width=475) + 3
    return y + 4


def _early_grant(page, case, family):
    principals = case["mandate"]["mocodawca"]
    idx = case["index"]
    powers = (_EARLY_POWERS[0], _EARLY_POWERS[1 + idx % 3], _EARLY_POWERS[4])
    y = 52
    if family == "early-panels":
        page.section("grant-participant-panels")
        page.line(50, y, 545, y)
        left = page.text(52, y + 8, "MOCODAWCA", bold=True, size=11)
        right = page.text(310, y + 8, "PEŁNOMOCNIK", bold=True, size=11, width=231)
        for i, principal in enumerate(principals):
            left = _principal(page, left, principal, i, width=242)
        right = _attorneys(page, case, right, x=310, width=231, registration=True)
        y = max(left, right) + 10
        page.line(50, y, 545, y)
        y = _grant_title(page, y + 26, "Pełnomocnictwo")
        y = _p(
            page,
            y,
            "Udzielam wskazanym wyżej osobom pełnomocnictwa do podejmowania czynności w imieniu "
            "mocodawcy w następującej sprawie.",
        )
        y = _grant_subject(page, case, y)
        y = _powers(page, y, powers, "numbers")
        y = _mandate_date(page, case, y + 8)
    elif family == "early-register":
        y = _grant_title(page, y, "P E Ł N O M O C N I C T W O")
        rows = ("Mocodawca", "Pełnomocnicy", "Postępowanie", "Zakres", "Data")
        for label in rows:
            page.section("grant-register-" + label)
            page.line(50, y, 543, y)
            y += 7
            bottom = page.text(52, y, label, size=10, bold=True, width=115)
            if label == "Mocodawca":
                for i, principal in enumerate(principals):
                    y = _principal(page, y, principal, i, x=174, width=363)
            elif label == "Pełnomocnicy":
                y = _attorneys(page, case, y, x=174, width=363, registration=True)
            elif label == "Postępowanie":
                proc = case["appeal"]["ZamowieniePubliczne"]
                y = page.text(174, y, proc["tytul"], width=363, role="grant.procedure_title")
                y = page.text(174, y, "Nr " + proc["numer_postepowania"], width=363, role="grant.procedure_number")
                y = page.text(174, y, case["appeal"]["Zamawiajacy"][0]["nazwa"], width=363, role="grant.authority")
            elif label == "Zakres":
                y = page.text(174, y, "Umocowanie do:\n" + "\n".join("• " + p for p in powers), width=363)
            else:
                y = _mandate_date(page, case, y, x=174)
            y = max(y, bottom) + 7
        page.line(50, y, 543, y)
    elif family == "early-paragraphs":
        y = _grant_title(page, y, "PEŁNOMOCNICTWO")
        y = _mandate_date(page, case, y)
        y = _heading(page, y, "grant-principal", "§ 1. Mocodawca")
        for i, principal in enumerate(principals):
            y = _principal(page, y, principal, i, prefix="Niniejszego umocowania udziela")
        y = _heading(page, y + 5, "grant-attorneys", "§ 2. Pełnomocnicy")
        y = _attorneys(page, case, y, registration=True)
        y = _heading(page, y + 5, "grant-procedure", "§ 3. Oznaczenie sprawy")
        y = _grant_subject(page, case, y)
        y = _heading(page, y, "grant-scope", "§ 4. Zakres umocowania")
        y = _powers(page, y, powers, "bullets")
        y = _heading(page, y, "grant-duration", "§ 5. Czas obowiązywania")
        y = _p(
            page,
            y,
            "Umocowanie wygasa z chwilą zakończenia postępowania w tej sprawie lub wcześniejszego "
            "odwołania przez mocodawcę.",
            size=10,
        )
    else:
        if family == "early-letterhead":
            page.section("principal-letterhead")
            for i, principal in enumerate(principals):
                y = _principal(page, y, principal, i)
            page.line(52, y + 4, 541, y + 4)
            y = _mandate_date(page, case, y + 17)
            y = _grant_title(page, y, "P E Ł N O M O C N I C T W O")
            y = _p(
                page,
                y,
                "Działając jako osoba uprawniona do reprezentacji przedsiębiorcy wymienionego "
                "w nagłówku, ustanawiam pełnomocnikami następujące osoby.",
            )
        else:
            if family == "early-procedural":
                y = _mandate_date(page, case, y)
            y = _grant_title(page, y, "PEŁNOMOCNICTWO PROCESOWE")
            page.section("grant-declaration")
            for i, principal in enumerate(principals):
                y = _principal(page, y, principal, i, prefix="Wykonawca")
            y = _p(page, y, "udziela pełnomocnictwa do zastępstwa w sprawie następującym osobom:", size=10.5)
        page.section("appointed-counsel")
        y = _attorneys(page, case, y, registration=True) + 8
        y = _grant_subject(page, case, y)
        if family == "early-short":
            y = _p(
                page,
                y,
                "Upoważnienie obejmuje wniesienie odwołania, odbiór pism i występowanie na "
                "rozprawie. Oświadczenia złożone w granicach umocowania wiążą mocodawcę. Każda z wymienionych "
                "osób może działać samodzielnie.",
                size=10.5,
            )
            y = _mandate_date(page, case, y)
        else:
            y = _p(page, y, "Zakres pełnomocnictwa obejmuje uprawnienie do:", size=10.5)
            y = _powers(page, y, powers, "bullets" if family == "early-letterhead" else "letters")
    _signatories(page, case, y + 10, acceptance=family == "early-paragraphs")


def _late_grant(page, case, family):
    y = _mandate_date(page, case, 46)
    y = _grant_title(page, y, "PEŁNOMOCNICTWO")
    principals = case["mandate"]["mocodawca"]
    page.section("principal-declaration")
    if family == "late-consortium":
        y = _p(
            page,
            y,
            "Wykonawcy wspólnie ubiegający się o udzielenie zamówienia, działając jako konsorcjum "
            "reprezentowane przez osoby podpisane poniżej, składają wspólne oświadczenie.",
            size=10.5,
        )
    for i, principal in enumerate(principals):
        prefix = {"late-company": "Mocodawca:", "late-consortium": f"{i + 1})", "late-trader": "Ja,"}[family]
        y = _principal(page, y, principal, i, prefix=prefix)
    grant = {
        "late-company": "Spółka, reprezentowana zgodnie z zasadami ujawnionymi w rejestrze, udziela pełnomocnictwa:",
        "late-consortium": "Umocowania udzielają łącznie wszyscy wymienieni wykonawcy. Ustanawiają pełnomocnikami:",
        "late-trader": "Jako przedsiębiorca wpisany do Centralnej Ewidencji i Informacji o Działalności "
        "Gospodarczej udzielam pełnomocnictwa:",
    }[family]
    y = _p(page, y + 5, grant, size=10.5)
    page.section("appointed-counsel")
    y = _attorneys(page, case, y, registration=True) + 8
    y = _p(
        page,
        y,
        "Powyższe umocowanie dotyczy udziału w sprawie o udzielenie zamówienia publicznego "
        "oraz postępowań wywołanych środkami ochrony prawnej dotyczącymi tej sprawy.",
        size=10.5,
    )
    y = _grant_subject(page, case, y)
    y = _p(page, y, "W granicach umocowania każdy pełnomocnik może samodzielnie:", size=10.5)
    y = _powers(page, y, _LATE_POWERS, "numbers")
    y = _p(
        page,
        y,
        "Umocowanie trwa do chwili prawomocnego zakończenia sprawy, chyba że mocodawca odwoła je wcześniej.",
        size=10.5,
    )
    _signatories(page, case, y, acceptance=True)


def render_mandate(page, case, family):
    if family not in MANDATES:
        raise ValueError(f"Unknown mandate family {family!r}")
    if family.startswith("late-"):
        _late_grant(page, case, family)
    else:
        _early_grant(page, case, family)
