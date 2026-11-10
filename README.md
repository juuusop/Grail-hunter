# 🦅 Grail Hunter

Sellpy-sniperi, joka pyörii GitHub Actionsissa noin 10 minuutin välein ja kerää parhaat löydöt yhteen paikkaan:

- **[FINDS.md](FINDS.md)**: kaikki löydöt kuvineen, viikon parhaat ylimpänä.
- **Issue "🦅 Löydöt"**: jokainen uusi löytö kommentoidaan sinne. Paina issuessa **Subscribe**, niin GitHub-sovellus ilmoittaa puhelimeen.
- **[data/BRAND_REPORT.md](data/BRAND_REPORT.md)**: brändiraportti, eli miten Sellpy kirjoittaa kunkin brändin, montako on myynnissä ja mikä on hintataso.

Mitään avaimia ei tarvitse asettaa. Skripti lukee Sellpyn julkisen hakuavaimen Sellpyn omalta sivulta.

## Miten se löytää graileja

1. **Brändihaku palvelimella.** Kaikki brändit (`brands.yaml`) laitetaan suoraan Sellpyn hakuun filtteriksi uusimmat ensin, ja sivuja haetaan kunnes vastaan tulee jo nähty tuote. Mitään uutta ei jää väliin, vaikka brändejä olisi satoja.
2. **Pisteytys, ei hintakattoa.** `pisteet = arvioitu arvo / hinta`. Arvo lasketaan brändin `value`-luvusta, tuotetyypistä (nahkatakki ×2, takki ×1.6, kengät ×1.4 … t-paita ×0.5), kunnosta ja avainsanoista (esim. Rick Owens *geobasket* ×1.5, Margiela *tabi* ×1.6, *DRKSHDW* ×0.6). Hälytys tulee, kun pisteet ≥ 2 eli hinta on enintään puolet arvosta.
3. **Harvinaiset.** Harvinaiset brändit (CCP, Harnden, BBS, m.a+, Layer-0, Carpe Diem, Number (N)ine, Raf, CDG Homme Plus …) ja harvinaisuussanat (artisanal, runway, sample, prototype, shadow project, vanhat sesonkikoodit kuten AW04) hälyttävät jo, kun hinta on suunnilleen arvon verran.
4. **Väärin listatut.** Erilliset tekstihaut (`config.yaml` → `hunts`) etsivät tuotteita, joissa brändi on väärin tai "tuntematon", mutta tiedoissa lukee esim. *margiela*, *tabi*, *geobasket*, *hevosennahka* tai halpa *kashmir*.
5. **Hinnanpudotukset.** Kerran tunnissa koko brändilista käydään läpi. Jos hinta tippuu niin, että tuotteesta tulee diili, tulee 📉-hälytys.
6. **Roskat pois.** Lapset, hajuvedet, H&M- ja Uniqlo-kollabit, "-tyylinen", rikkinäiset ja kopiot hylätään.
7. **Sellpyn oma hintataso.** Jos hinta on brändin halvimmassa 25 %:ssa Sellpyssä, arvoon tulee pieni lisä.

## Säätäminen (onnistuu puhelimella GitHubin editorissa)

- **Brändi lisää / pois:** `brands.yaml`. Seuraava ajo hakee uusien brändien kirjoitusasut automaattisesti.
- **Liikaa hälytyksiä jostain brändistä:** laske sen `value`a. Brändiraportti näyttää ⚠️:n, jos arvo on selvästi yli Sellpyn mediaanin.
- **Koot, hintakatto, herkkyys:** `config.yaml` → `settings` (`sizes`, `max_price`, `min_score`).
- **Ajo heti:** Actions → Sniper → Run workflow.

## Tiedostot

| | |
|---|---|
| `sniper.py` | koko logiikka (`run` ja `discover`) |
| `brands.yaml` | brändit, arvot, aliakset, avainsanakertoimet |
| `config.yaml` | asetukset, kategoriat, kunto, harvinaisuussanat, poissulut, tekstihaut |
| `.github/workflows/sniper.yml` | 10 min välein |
| `.github/workflows/discover.yml` | brändihaku ja -arviointi maanantaisin (ja aina kun `brands.yaml` muuttuu) |
| `tests/` | offline-testit |

Vanha FastAPI/Tauri-versio löytyy git-historiasta.
