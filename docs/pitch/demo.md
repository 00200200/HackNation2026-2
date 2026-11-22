# Pokaz na żywo: scenariusz na 2 minuty

Do slajdu 8. Pokaz ma trzy kroki: CLI na folderze, ten sam folder w GUI i nowa klasa z pliku TOML.
Profil bez LLM: zmienne `KIO_LLM_*` puste i bez pliku `.env` w katalogu repozytorium.

Krok 3 korzysta z `--classes` i przykładu `examples/classes/accession.toml` z #76, więc wymaga
scalenia #76. Kroki 1 i 2 sprawdziliśmy 22.11.2026 w CLI na `main` po #54, #57, #58, #77 i #79, a w
przeglądarce na wcześniejszym `main`. Krok 3 sprawdziliśmy na gałęzi #76: CLI z `--classes` i
`--explain` oraz przeładowanie klas w GUI przy każdej analizie. Przed finałem trzeba przejść cały
scenariusz raz na `main` po scaleniu #76.

## Przed wejściem

W katalogu repozytorium, w aktywnym środowisku (`. .venv/bin/activate`):

```sh
rm -rf ~/demo   # czyści poprzednią próbę
mkdir -p ~/demo/sprawy/sprawa_01 ~/demo/sprawy/skany ~/demo/nowa_klasa ~/demo/klasy
cp data/uzp/dane/przyklad_04/*.pdf ~/demo/sprawy/sprawa_01/
cp data/uzp/dane/skany/odwolania/0001/0001.pdf ~/demo/sprawy/skany/odwolanie_skan.pdf
cp data/uzp/dane/skany/potwierdzenia/0002/0002.pdf ~/demo/sprawy/skany/potwierdzenie_skan.pdf
cp -R examples/input/sprawa-demo ~/demo/nowa_klasa/
```

`sprawa_01` to cała sprawa z przykładów UZP: odwołanie, pełnomocnictwo, potwierdzenie przelewu i
jeden dokument spoza klas. `skany` to dwa skany UZP bez warstwy tekstu. Zgłoszenie przystąpienia w
`sprawa-demo` ma dane zmyślone. Katalog `~/demo/klasy` jest na początku pusty.

Potem:

1. Terminal 1 w katalogu repozytorium, powiększona czcionka.
2. Terminal 2, też w katalogu repozytorium i w aktywnym środowisku (pakiet `kio2json` nie jest
   instalowany, więc spoza repozytorium się nie uruchomi):
   `python -m kio2json.gui --classes ~/demo/klasy`. Przeglądarka otworzy `127.0.0.1:8000`. GUI
   zostaje włączone do końca pokazu.
3. Rozgrzewka: uruchom komendę z kroku 0:00 raz przed pokazem, potem `rm -rf ~/demo/wyniki`.
   Pierwsze uruchomienie po instalacji trwa dłużej.

Czasy z naszej próby na Apple M1, niezapisane w `evals/` i tylko do planowania pokazu: CLI na sześciu
PDF-ach około 15 s, analiza tego samego folderu w GUI około 7 s.

## Scenariusz

| Start | Na ekranie | Mówimy |
|---|---|---|
| 0:00 | Terminal 1: `python -m kio2json --input ~/demo/sprawy --output ~/demo/wyniki` | „Sześć PDF-ów: cała sprawa z przykładów UZP, w niej jeden dokument spoza klas, i dwa skany bez tekstu. Klasę program rozpoznaje z treści, nie z nazwy pliku.” |
| 0:15 | Wiersze `appeal`, `power_of_attorney`, `bank_transfer`, `other` | „Przy każdym pliku widać klasę. Dokument spoza klas dostaje {}.” |
| 0:25 | `cat ~/demo/wyniki/skany/odwolanie_skan.json` | „To był skan bez warstwy tekstu. Ten JSON jest identyczny ze wzorcem UZP.” |
| 0:40 | GUI: **Otwórz folder**, ścieżka `~/demo/sprawy`, **Analizuj dokumenty**, potem odwołanie z listy | „Ten sam folder w GUI. Po lewej strona PDF, po prawej JSON.” |
| 1:05 | W **Dokument do podglądu** skan potwierdzenia, potem **Pobierz wyniki (.zip)** | „Skany działają tak samo. Wyniki całej sprawy pobieramy jednym ZIP-em.” |
| 1:15 | GUI: ścieżka `~/demo/nowa_klasa`, **Analizuj dokumenty** | „A to zgłoszenie przystąpienia, pismo, którego program jeszcze nie zna. Wychodzi poza klasami.” |
| 1:30 | Terminal 1: `cp examples/classes/accession.toml ~/demo/klasy/`, potem w GUI **Analizuj dokumenty** | „Dokładamy jeden plik TOML. Bez kodu i bez restartu.” |
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

Ostatni krok robimy w CLI. `--explain` zapisuje raport ze stroną i linią źródła każdego pola:

```sh
python -m kio2json --classes examples/classes --input ~/demo/nowa_klasa --output ~/demo/wynik_klasy --explain ~/demo/raport
cat ~/demo/wynik_klasy/sprawa-demo/zgloszenie_przystapienia.json
```

Bez `--classes` ten sam plik dostaje `{}`, bo bez tej flagi działają tylko trzy klasy UZP.

## Jeśli #76 nie jest scalony

Bez #76 nie ma `--classes`, `--explain` ani katalogu `examples/`. Krok 3 pokazujemy wtedy na
wyłączonej klasie `participation` z `config/classes/` i zmyślonej karcie uczestnika. Ten wariant
sprawdziliśmy w przeglądarce na wcześniejszym `main`.

Przed wejściem, zamiast ostatniej linii przygotowania (`cp -R examples/input/sprawa-demo ...`):

```sh
mkdir -p ~/demo/nowa_klasa/karta
cp docs/pitch/demo/karta-uczestnika.pdf ~/demo/nowa_klasa/karta/
cp -R config/classes ~/demo/klasy-stare
```

GUI w terminalu 2: `KIO_CLASSES_DIR="$HOME/demo/klasy-stare" python -m kio2json.gui`. Edytor z plikiem
`~/demo/klasy-stare/participation.toml`, kursor na linii `enabled = false`.

| Start | Na ekranie | Mówimy |
|---|---|---|
| 1:15 | GUI: ścieżka `~/demo/nowa_klasa`, **Analizuj dokumenty** | „A to formularz, którego program nie zna: karta uczestnika. Wychodzi poza klasami.” |
| 1:30 | Edytor: `enabled = true`, zapisz. GUI: **Analizuj dokumenty** | „Jedna linia w pliku TOML. Bez kodu i bez restartu.” |
| 1:45 | GUI: nagłówek „Karta uczestnika” i JSON | „Nowa klasa, a data od razu w formacie ISO.” |

Oczekiwany JSON:

```json
{
  "participant": "Pracownia Brzozowa sp. z o.o.",
  "filed": "2026-11-21",
  "reference": "KIO-DEMO/2026/1"
}
```

W tym wariancie trzeba też zmienić slajdy, bo opisują #76: slajd 7 (wersja z `participation.toml` z
commitu `afc2c30`), krok 03 na slajdzie 8, wiersze 3 i 5 na slajdzie 9 oraz punkty 03 i 04 na slajdzie
10 z notatkami.

## Po pokazie

Usuń katalog `~/demo`. Pliki w repozytorium zostają bez zmian.
