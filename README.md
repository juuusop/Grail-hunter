# 🦅 Grail Hunter

Designer thrift scraper for Sellpy - find grails efficiently.

## Features

- **Brand Classification**: 60+ designer brands across 6 categories
- **Tier System**: Automatic grail detection (Tier 1 = instant alert)
- **Quality Filtering**: Trash detection, material analysis
- **Async Scraping**: Fast, efficient httpx-based scraper
- **REST API**: Full FastAPI backend with OpenAPI docs
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

```bash
# Install
pip install -e .

# Hunt for grails
grail-hunter hunt

# Search specific brand
grail-hunter search "Rick Owens"

# Start API server
grail-hunter serve
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/items` | List items with filtering |
| `GET /api/items/grails` | Top grail items |
| `GET /api/brands` | All tracked brands |
| `POST /api/scrape` | Trigger new scrape |
| `GET /api/stats` | Database statistics |

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

Copy `.env.example` to `.env` and adjust settings:

```bash
cp .env.example .env
```

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

## License

MIT
