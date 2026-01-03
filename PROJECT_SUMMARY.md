# Grail Hunter - Designer Thrift Scraper

## Projektin Kuvaus

Grail Hunter on Python-pohjainen designer-vaatteiden etsintätyökalu, joka skannaa käytettyjen vaatteiden markkinapaikkoja (Sellpy, Grailed, eBay, Vinted) ja löytää arvokkaat "grail"-löydöt automaattisesti.

## Arkkitehtuuri

```
grail_hunter/
├── cli.py                 # Typer CLI (grail-hunter komento)
├── main.py                # FastAPI backend
├── config.py              # Pydantic Settings (.env konfiguraatio)
├── logging.py             # Structlog JSON-loggaus
├── __init__.py            # Versio 2.0.0
│
├── scrapers/              # Markkinapaikka-scraperit
│   ├── base.py            # BaseScraper (retry, rate limiting)
│   ├── sellpy.py          # Sellpy Algolia API
│   ├── grailed.py         # Grailed Algolia API
│   ├── ebay.py            # eBay HTML scraping
│   └── vinted.py          # Vinted API (11 maata)
│
├── brands/                # Brändiluokittelu
│   ├── categories.py      # 60+ brändiä, 6 kategoriaa
│   └── classifier.py      # TIER_1/TIER_2/TIER_3 luokittelu
│
├── filters/               # Laadunsuodatus
│   └── quality.py         # Trash-regex, materiaalifiltterit
│
├── services/              # Bisneslogiikka
│   ├── arbitrage.py       # Hintavertailu (INSANE/GREAT/GOOD/FAIR)
│   ├── notifications.py   # Telegram-ilmoitukset
│   └── scheduler.py       # APScheduler automaattiajo
│
├── models/                # SQLAlchemy mallit
│   └── item.py            # Item-tietokantamalli
│
├── database/              # Tietokanta
│   └── connection.py      # Async SQLite/PostgreSQL
│
└── api/                   # REST API
    └── routes.py          # FastAPI reitit
```

## Teknologiat

| Komponentti | Teknologia |
|-------------|------------|
| CLI | Typer + Rich |
| Backend | FastAPI + Uvicorn |
| Tietokanta | SQLAlchemy 2.0 + aiosqlite |
| HTTP | httpx (async) |
| Retry | tenacity (exponential backoff) |
| Scheduler | APScheduler |
| Ilmoitukset | python-telegram-bot |
| Loggaus | structlog (JSON) |
| Konfiguraatio | pydantic-settings (.env) |

## Brändihierarkia

### TIER_1 - Grails (Välitön hälytys)
- Rick Owens, Maison Margiela, Raf Simons
- Carol Christian Poell, Guidi, Paul Harnden
- Visvim, Kapital, Saint Michael

### TIER_2 - Hype
- Comme des Garçons, Yohji Yamamoto, Issey Miyake
- Balenciaga, Vetements, Acne Studios
- Stone Island, C.P. Company, Our Legacy

### TIER_3 - Tunnetut
- Burberry, Prada, Gucci, Louis Vuitton, jne.

## Käyttö

```bash
# Asennus
pip install -e .
cp .env.example .env

# CLI-komennot
python -m grail_hunter.cli grails          # Näytä TIER_1 brändit
python -m grail_hunter.cli brands          # Kaikki brändit
python -m grail_hunter.cli hunt            # Etsi graileja
python -m grail_hunter.cli search "Rick Owens"

# Scheduler
python -m grail_hunter.cli scheduler start -f   # Automaattiajo
python -m grail_hunter.cli scheduler status

# API-palvelin
python -m grail_hunter.cli serve
```

## Konfiguraatio (.env)

```env
# Sellpy
SELLPY_APP_ID=50lbqu2i4a
SELLPY_API_KEY=your_key

# Grailed
GRAILED_APP_ID=MNRWEFSS2Q
GRAILED_API_KEY=your_key

# Telegram (valinnainen)
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789

# Asetukset
MIN_PRICE=10
MAX_PRICE=500
SCRAPE_INTERVAL_MINUTES=5
```

## Arbitraasisysteemi

Vertaa Sellpy-hintoja Grailed/eBay-hintoihin:

| Rating | Säästö | Kuvaus |
|--------|--------|--------|
| INSANE | 60%+ | Välitön osto |
| GREAT | 40-60% | Erinomainen diili |
| GOOD | 20-40% | Hyvä diili |
| FAIR | 0-20% | OK hinta |
| OVERPRICED | <0% | Liian kallis |

## Scrapereiden Toiminta

### BaseScraper (base.py)
- Tenacity retry: 3 yritystä, exponential backoff
- Rate limiting: asyncio.Semaphore (max 5 concurrent)
- Automaattinen headers/cookies hallinta

### Sellpy (sellpy.py)
- Algolia Search API
- Hakee kategorioittain (Miehet, Naiset)
- Suodattaa brändin ja hinnan mukaan

### Vinted (vinted.py)
- Tukee 11 maata: FR, DE, IT, ES, NL, BE, AT, PL, CZ, LT, UK
- OAuth-sessio automaattisesti
- Valmiit brand ID:t grail-brändeille

---

## KEHITYSIDEAT

### 1. Kriittiset Korjaukset

#### 1.1 API-avainten Haku
Sellpy ja Grailed API-avaimet vanhenevat. Tarvitaan:
```python
async def refresh_algolia_keys(self):
    """Hae uudet API-avaimet Sellpy-sivulta."""
    resp = await self._fetch("https://www.sellpy.fi")
    # Parsii script-tageista: window.__INITIAL_STATE__
    # Palauttaa uudet appId ja apiKey
```

#### 1.2 Proxy-tuki
```python
class ScraperConfig:
    proxy_url: Optional[str] = None
    rotate_proxies: bool = False
    proxy_list: list[str] = []
```

#### 1.3 Captcha-käsittely
- Cloudflare bypass (undetected-chromedriver)
- 2captcha/anticaptcha integraatio

### 2. Uudet Ominaisuudet

#### 2.1 Lisää Markkinapaikkoja
- **Depop** - UK/US nuorten markkina
- **Vestiaire Collective** - Luksusvaatteet
- **TheRealReal** - Autentikoidut luksustuotteet
- **Tori.fi** - Suomen markkinat
- **Facebook Marketplace** - Paikalliset löydöt

#### 2.2 Kuvantunnistus (AI)
```python
from transformers import pipeline

class BrandDetector:
    """Tunnista brändi kuvasta kun title ei kerro."""

    def __init__(self):
        self.classifier = pipeline("image-classification",
                                   model="fashion-brand-detector")

    async def detect_brand(self, image_url: str) -> str:
        # Lataa kuva, aja malli, palauta brändi
```

#### 2.3 Hintahistoria & Trendit
```python
class PriceTracker:
    """Seuraa brändin hintakehitystä."""

    async def get_price_trend(self, brand: str, item_type: str):
        # Palauttaa keskihinnan, min, max, trendi (nouseva/laskeva)
```

#### 2.4 Discord Bot
```python
import discord

class GrailHunterBot(discord.Client):
    """Discord-ilmoitukset Telegramin lisäksi."""

    async def notify_grail(self, item):
        channel = self.get_channel(CHANNEL_ID)
        embed = discord.Embed(title=f"🏆 {item.brand}")
        await channel.send(embed=embed)
```

#### 2.5 Desktop App (Tauri)
Projekti sisältää aloitetun Tauri-sovelluksen:
- `src/` - Svelte frontend
- `src-tauri/` - Rust backend
- Tarvitsee: UI viimeistely, real-time updates

### 3. Parannukset

#### 3.1 Testit
```bash
# Puuttuvat testit
pytest tests/
├── test_scrapers.py      # Mock API responses
├── test_brands.py        # Luokittelutestit
├── test_arbitrage.py     # Hintavertailutestit
└── test_filters.py       # Suodatustestit
```

#### 3.2 Docker
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -e .
CMD ["python", "-m", "grail_hunter.cli", "scheduler", "start", "-f"]
```

#### 3.3 CI/CD
```yaml
# .github/workflows/ci.yml
- Lint: ruff, mypy
- Test: pytest
- Build: Docker image
- Deploy: Railway/Render
```

#### 3.4 Parempi Hakualgoritmi
```python
class SmartSearch:
    """Älykkäämpi haku joka oppii."""

    def __init__(self):
        self.successful_searches = []  # Mitkä haut tuottivat ostoja

    def optimize_keywords(self, brand: str) -> list[str]:
        # "Rick Owens" -> ["rick owens", "rickowens", "RO", "drkshdw"]
```

### 4. Monetisointi-ideat

1. **Premium-tilaus**: Reaaliaikaiset ilmoitukset, enemmän brändejä
2. **Affiliate-linkit**: Komissio jokaisesta myynnistä
3. **API-palvelu**: Myy dataa muille resellereille
4. **Koulutus**: "Grail Hunting 101" -kurssi

---

## Tiedossa Olevat Ongelmat

1. **"No grails found"** - Sellpy API-avaimet voivat olla vanhentuneet
2. **Telegram import error** - cryptography-kirjasto vaatii cffi:n
3. **Rate limiting** - Jotkut sivustot blokkaavat liian nopeat pyynnöt

## Repositorio

```
Branch: claude/designer-thrift-scraper-KF3Wi
GitHub: https://github.com/juuusop/Grail-hunter
```

---

*Luotu: 2026-01-03*
