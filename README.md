# 🦅 Grail Hunter

Designer thrift scraper for Sellpy with **arbitrage analysis**. Find underpriced grails by comparing prices across Grailed and eBay.

## Features

- **Brand Classification**: 60+ designer brands across 6 categories
- **Tier System**: Automatic grail detection (Tier 1 = instant alert)
- **Quality Filtering**: Trash detection, material analysis
- **Arbitrage Analysis**: Compare Sellpy prices to Grailed & eBay market values
- **Deal Rating**: INSANE / GREAT / GOOD / FAIR / OVERPRICED
- **Async Scraping**: Fast, efficient httpx-based scrapers
- **REST API**: Full FastAPI backend with OpenAPI docs
- **Tauri Desktop App**: Modern Svelte UI with real-time updates
- **CLI**: Command-line hunting tools

## Brand Categories

| Category | Examples |
|----------|----------|
| ARTISANAL_DARK | Rick Owens, Carol Christian Poell, Guidi |
| JAPAN_AVANTGARDE | Comme des Garçons, Yohji Yamamoto, Kapital |
| EURO_LUXURY | Maison Margiela, Raf Simons, Prada |
| STREET_MODERN | Supreme, Off-White, Fear of God |
| TECH_GORP | Arc'teryx, Stone Island, Salomon |
| WORKWEAR_DENIM | Vintage Levi's, Carhartt |

## Quick Start

### Python Backend

```bash
# Install Python dependencies
pip install -e .

# Start the API server
grail-hunter serve

# Hunt for grails (CLI)
grail-hunter hunt

# Search specific brand
grail-hunter search "Rick Owens"
```

### Tauri Desktop App

```bash
# Install Node dependencies
npm install

# Run in development mode
npm run tauri:dev

# Build for production
npm run tauri:build
```

## Architecture

```
grail_hunter/           # Python backend
├── scrapers/
│   ├── sellpy.py       # Sellpy Algolia scraper
│   ├── grailed.py      # Grailed price scraper
│   └── ebay.py         # eBay price scraper
├── services/
│   └── arbitrage.py    # Price comparison & deal rating
├── api/
│   └── routes.py       # FastAPI endpoints
└── cli.py              # Command-line interface

src/                    # Svelte frontend
├── lib/
│   ├── components/     # UI components
│   ├── stores/         # State management
│   └── api.ts          # API client
└── App.svelte          # Main app

src-tauri/              # Rust Tauri backend
└── src/main.rs         # Native commands
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/items` | List items with filtering |
| `GET /api/items/grails` | Top grail items |
| `GET /api/brands` | All tracked brands |
| `POST /api/scrape` | Trigger new scrape |
| `GET /api/stats` | Database statistics |
| `GET /api/arbitrage/{id}` | Analyze single item |
| `POST /api/arbitrage/batch` | Analyze multiple items |

## Arbitrage System

The arbitrage service compares Sellpy prices against market values:

```python
# Deal ratings based on price difference
INSANE:     60%+ below market   🔥
GREAT:      40-60% below        💰
GOOD:       20-40% below        ✅
FAIR:       0-20% below         ➖
OVERPRICED: Above market        ❌
```

Data sources:
- **Grailed**: Designer resale marketplace (weighted higher)
- **eBay**: Broader market data + sold listings

## CLI Commands

```bash
# List all tracked brands
grail-hunter brands

# Show Tier 1 grails only
grail-hunter grails

# Hunt with options
grail-hunter hunt --pages 5 --category "Miehet"

# Start server
grail-hunter serve --port 8000 --reload
```

## Configuration

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Key settings:
- `DATABASE_URL` - SQLite or PostgreSQL connection
- `SCRAPE_INTERVAL_SECONDS` - Auto-scan frequency
- `MAX_PRICE` - Price filter ceiling

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Type checking
mypy grail_hunter

# Linting
ruff check grail_hunter
```

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, SQLAlchemy 2.0, httpx
- **Frontend**: Svelte, TailwindCSS, TypeScript
- **Desktop**: Tauri (Rust)
- **Database**: SQLite (dev) / PostgreSQL (prod)

## License

MIT
