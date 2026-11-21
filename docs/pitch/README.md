# Pitch doc2json (finał HackNation 2026)

Kopia prezentacji z claude.ai (Artifact typu Slides, wersja z 22.11.2026), zapisana przed zmianą konta.
Prezentacja ma 9 slajdów, jest czarno-biała, w stylu Linear i Tailscale, z czcionkami Geist i Geist Mono.

| Plik | Co to jest |
|---|---|
| `doc2json-pitch.pdf` | eksport PDF, 9 stron 1920×1080 |
| `index.html` | wszystkie slajdy na jednej stronie. Otwórz w przeglądarce. Czcionki bierze z `frontend/public/fonts/` |
| `project/deck.json`, `project/deck.css`, `project/slides/*.html` | źródło slajdów w formacie typu Slides. Notatki prelegenta są w `<aside>` |
| `assets/demo-app.png` | zrzut doc2json.pl z 21.11.2026, użyty na slajdzie 7 |

Po zmianie slajdu odbuduj `index.html` i PDF. W `index.html` każdy slajd jest kopią pliku z `project/slides/`,
a adres `/_blob/...` obrazka zamieniono na `assets/demo-app.png`. PDF drukuje headless Chrome z `index.html`
(`--print-to-pdf`, rozmiar strony ustawia `@page`).

## Placeholdery do uzupełnienia

- Slajd 5 „Liczymy F1 tak jak jury”: dwa wyniki `[ __ ]` (F1 dla wszystkich dokumentów i F1 dla holdoutu 51-60)
  oraz `[commit __]` w stopce. Liczby wpisz tylko z `evals/results/latest.json`, z podpisem „dane treningowe (syntetyczne)”.
- Slajd 6 „Nowa klasa to nowy plik”: przykład pliku klasy jest poglądowy, a jego format nie jest jeszcze ustalony.
  Stopka ma dopisek „Plan”. W notatkach są `[model: __]` i `[dostawca: __]`.
- Slajd 7 „doc2json.pl”: w notatkach jest `[komenda CLI: __]`.
- Slajd 9: sprawdź, czy repo github.com/00200200/HackNation2026-2 jest publiczne. Kod QR prowadzi do https://doc2json.pl.
  Kod nie był skanowany telefonem.

Wagi na slajdzie 8 (50/30/20) pochodzą z opisu wyzwania, sekcja 8. README organizatora podaje 50% za
elastyczność, a jury nie potwierdziło, który podział obowiązuje.
