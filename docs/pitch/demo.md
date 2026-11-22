# Pokaz na żywo: scenariusz na 2 minuty

Do slajdu 8. Komendy sprawdziliśmy 22.11.2026 na `main` (macOS, Python 3.13, profil bez LLM:
zmienne `KIO_LLM_*` puste i bez pliku `.env` w katalogu repozytorium). Pokaz ma trzy kroki: CLI na
folderze, ten sam folder w GUI i nowa klasa z pliku TOML.

## Przed wejściem

W katalogu repozytorium, w aktywnym środowisku (`. .venv/bin/activate`):

```sh
rm -rf ~/demo   # czyści poprzednią próbę, inaczej cp -R config/classes trafi do podkatalogu
mkdir -p ~/demo/sprawy/sprawa_01 ~/demo/sprawy/skany ~/demo/nowa_klasa/karta
cp data/uzp/dane/przyklad_04/*.pdf ~/demo/sprawy/sprawa_01/
cp data/uzp/dane/skany/odwolania/0001/0001.pdf ~/demo/sprawy/skany/odwolanie_skan.pdf
cp data/uzp/dane/skany/potwierdzenia/0002/0002.pdf ~/demo/sprawy/skany/potwierdzenie_skan.pdf
cp docs/pitch/demo/karta-uczestnika.pdf ~/demo/nowa_klasa/karta/
cp -R config/classes ~/demo/klasy
```

`sprawa_01` to cała sprawa z przykładów UZP: odwołanie, pełnomocnictwo, potwierdzenie przelewu i
jeden dokument spoza klas. `skany` to dwa skany UZP bez warstwy tekstu. Karta uczestnika jest
zmyślona, jej źródło to `docs/pitch/demo/karta-uczestnika.html`.

Potem:

1. Terminal 1 w katalogu repozytorium, powiększona czcionka.
2. Terminal 2, też w katalogu repozytorium i w aktywnym środowisku (pakiet `kio2json` nie jest
   instalowany, więc spoza repozytorium się nie uruchomi):
   `KIO_CLASSES_DIR="$HOME/demo/klasy" python -m kio2json.gui`. Przeglądarka otworzy
   `127.0.0.1:8000`. GUI zostaje włączone do końca pokazu.
3. Edytor z plikiem `~/demo/klasy/participation.toml`, kursor na linii `enabled = false`.
4. Rozgrzewka: uruchom komendę z kroku 0:00 raz przed pokazem, potem `rm -rf ~/demo/wyniki`.
   Pierwsze uruchomienie po instalacji trwa dłużej.

Czasy z próby na Apple M1: CLI na sześciu PDF-ach około 15 s, analiza tego samego folderu w GUI
około 7 s.

## Scenariusz

| Start | Na ekranie | Mówimy |
|---|---|---|
| 0:00 | Terminal 1: `python -m kio2json --input ~/demo/sprawy --output ~/demo/wyniki` | „Sześć PDF-ów: cała sprawa z przykładów UZP, w niej jeden dokument spoza klas, i dwa skany bez tekstu. Klasę program rozpoznaje z treści, nie z nazwy pliku.” |
| 0:15 | Wiersze `appeal`, `power_of_attorney`, `bank_transfer`, `other` | „Przy każdym pliku widać klasę. Dokument spoza klas dostaje pusty wynik.” |
| 0:25 | `cat ~/demo/wyniki/skany/odwolanie_skan.json` | „To był skan bez warstwy tekstu. Ten JSON jest identyczny ze wzorcem UZP.” |
| 0:40 | GUI: **Otwórz folder**, ścieżka `~/demo/sprawy`, **Analizuj dokumenty**, potem odwołanie z listy | „Ten sam folder w GUI. Po lewej strona PDF, po prawej JSON.” |
| 1:05 | W **Dokument do podglądu** skan potwierdzenia, potem **Pobierz wyniki (.zip)** | „Skany działają tak samo. Wyniki całej sprawy pobieramy jednym ZIP-em.” |
| 1:15 | GUI: ścieżka `~/demo/nowa_klasa`, **Analizuj dokumenty** | „A to dokument, którego program nie zna: karta uczestnika. Na razie wychodzi poza klasami.” |
| 1:30 | Edytor: `enabled = true`, zapisz. GUI: **Analizuj dokumenty** | „Jedna linia w pliku TOML. Bez kodu i bez restartu.” |
| 1:45 | GUI: nagłówek „Karta uczestnika” i JSON | „Nowa klasa, a data od razu w formacie ISO. Tak samo dodamy kolejne pisma KIO.” |

Oczekiwany JSON w ostatnim kroku:

```json
{
  "participant": "Pracownia Brzozowa sp. z o.o.",
  "filed": "2026-11-21",
  "reference": "KIO-DEMO/2026/1"
}
```

## Gdy GUI zawiedzie

Ostatni krok robimy w CLI, po zmianie `enabled = true`:

```sh
KIO_CLASSES_DIR="$HOME/demo/klasy" python -m kio2json --input ~/demo/nowa_klasa --output ~/demo/wynik_klasy
cat ~/demo/wynik_klasy/karta/karta-uczestnika.json
```

Bez `KIO_CLASSES_DIR` ten sam plik dostaje pusty wynik, bo w repozytorium klasa jest wyłączona.

## Po pokazie

Usuń katalog `~/demo`. Pliki w repozytorium zostają bez zmian.
