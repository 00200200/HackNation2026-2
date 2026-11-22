# Pokaz na żywo: scenariusz na 2 minuty

Do slajdu 9. Pokaz ma trzy kroki: CLI na folderze, ten sam folder w GUI i nowa klasa z pliku TOML.
Profil bez LLM: zmienne `KIO_LLM_*` puste i bez pliku `.env` w katalogu repozytorium.

Klasa `accession`, flagi `--classes` i `--explain` są na `main` od scalenia #95.
Na wersji `a7dce92` sprawdziliśmy w CLI, że bez dodatkowej klasy przykładowe zgłoszenie daje
`{}`, a po jej dodaniu otrzymujemy sześć pól z poniższego przykładu i raport ze źródłami. W przeglądarce sprawdziliśmy również ponowną analizę po dodaniu pliku TOML.
ZIP pobrany z GUI zawierał sześć wyników identycznych bajt w bajt z CLI, a JSON skanu
odwołania zgadzał się ze wzorcem UZP.

## Przed wejściem

W katalogu repozytorium, w aktywnym środowisku (`. .venv/bin/activate`):

```sh
DEMO=$(mktemp -d "${TMPDIR:-/tmp}/doc2json-pokaz.XXXXXX")
mkdir -p "$DEMO"/sprawy/sprawa_01 "$DEMO"/sprawy/skany "$DEMO"/nowa_klasa "$DEMO"/klasy
cp data/uzp/dane/przyklad_04/*.pdf "$DEMO"/sprawy/sprawa_01/
cp data/uzp/dane/skany/odwolania/0001/0001.pdf "$DEMO"/sprawy/skany/odwolanie_skan.pdf
cp data/uzp/dane/skany/potwierdzenia/0002/0002.pdf "$DEMO"/sprawy/skany/potwierdzenie_skan.pdf
cp -R examples/input/sprawa-demo "$DEMO"/nowa_klasa/
printf 'Terminal 2: python -m kio2json.gui --classes "%s/klasy"\n' "$DEMO"
printf 'Foldery do GUI:\n%s/sprawy\n%s/nowa_klasa\n' "$DEMO" "$DEMO"
```

`sprawa_01` to cała sprawa z przykładów UZP: odwołanie, pełnomocnictwo, potwierdzenie przelewu i
jeden dokument spoza klas. `skany` to dwa skany UZP bez warstwy tekstu. Zgłoszenie przystąpienia w
`sprawa-demo` ma dane zmyślone. Katalog klas jest na początku pusty.

Potem:

1. Terminal 1 w katalogu repozytorium, powiększona czcionka.
2. Terminal 2, też w katalogu repozytorium i w aktywnym środowisku (pakiet `kio2json` nie jest
   instalowany, więc spoza repozytorium się nie uruchomi):
   wklej polecenie z linii „Terminal 2” wypisanej powyżej. Przeglądarka otworzy `127.0.0.1:8000`.
   GUI zostaje włączone do końca pokazu.
3. Przed pokazem przeanalizuj sześć PDF-ów komendą z kroku 0:00. Gdy na żywo OCR potrwa dłużej,
   można od razu pokazać wyniki z próby. Do pola w GUI wklejaj pełne ścieżki wypisane podczas przygotowań.

## Scenariusz

| Start | Na ekranie | Mówimy |
|---|---|---|
| 0:00 | Terminal 1: `python -m kio2json --input "$DEMO"/sprawy --output "$DEMO"/wyniki` | „Sześć PDF-ów: cała sprawa z przykładów UZP, w niej jeden dokument spoza klas, i dwa skany bez tekstu. Klasę program rozpoznaje z treści, nie z nazwy pliku.” |
| 0:15 | Wiersze `appeal`, `power_of_attorney`, `bank_transfer`, `other` | „Przy każdym pliku widać klasę. Dokument spoza klas dostaje {}.” |
| 0:25 | `cat "$DEMO"/wyniki/skany/odwolanie_skan.json` | „To był skan bez warstwy tekstu. Ten JSON jest identyczny ze wzorcem UZP.” |
| 0:40 | GUI: **Otwórz folder**, pełna ścieżka do folderu `sprawy`, **Analizuj dokumenty**, potem odwołanie z listy | „Ten sam folder w GUI. Po lewej strona PDF, po prawej JSON.” |
| 1:05 | W **Dokument do podglądu** skan potwierdzenia, potem **Pobierz wyniki (.zip)** | „Skany działają tak samo. Wyniki całej sprawy pobieramy jednym ZIP-em.” |
| 1:15 | GUI: pełna ścieżka do folderu `nowa_klasa`, **Analizuj dokumenty** | „A to zgłoszenie przystąpienia, pismo, którego program jeszcze nie zna. Wychodzi poza klasami.” |
| 1:30 | Terminal 1: `cp examples/classes/accession.toml "$DEMO"/klasy/`, potem w GUI **Analizuj dokumenty** | „Dokładamy jeden plik TOML. Bez kodu i bez restartu.” |
| 1:45 | GUI: klasa „Zgłoszenie przystąpienia”, frazy, które ją wybrały, i JSON | „Nowa klasa, z NIP i REGON sprawdzonymi sumą kontrolną. Tak samo dodamy kolejne pisma KIO.” |

Oczekiwany JSON w ostatnim kroku:

```json
{
  "sygnatura": "KIO 1234/26",
  "przystepujacy": "Miedziana Czapla Sp. z o.o.",
  "nip": "1234567883",
  "regon": "123456785",
  "strona": "Zamawiającego",
  "data_wezwania": "2026-03-11"
}
```

## Gdy GUI zawiedzie

Ostatni krok robimy w CLI. `--explain` zapisuje raport ze stroną i fragmentem tekstu dla odnalezionych wartości:

```sh
python -m kio2json --classes examples/classes --input "$DEMO"/nowa_klasa --output "$DEMO"/wynik_klasy --explain "$DEMO"/raport
cat "$DEMO"/wynik_klasy/sprawa-demo/zgloszenie_przystapienia.json
```

Bez `--classes` ten sam plik dostaje `{}`, bo bez tej flagi działają tylko trzy klasy UZP.

## Po pokazie

Zatrzymaj GUI w terminalu 2. Katalog tymczasowy pokazu wskazuje `printf '%s\n' "$DEMO"` w terminalu 1.
