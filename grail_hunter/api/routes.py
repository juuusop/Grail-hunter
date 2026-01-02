"""FastAPI API routes for Grail Hunter."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from grail_hunter.brands import BrandClassifier, TIER_1_GRAILS, ALL_BRANDS
from grail_hunter.database import get_session
from grail_hunter.models import Item, ScrapeRun
from grail_hunter.scrapers import SellpyScraper
from grail_hunter.scrapers.sellpy import SellpyItem
from grail_hunter.services.arbitrage import ArbitrageService

router = APIRouter()


# Pydantic models for API responses
class ItemResponse(BaseModel):
    """API response for a single item."""

    object_id: str
    title: str
    brand: str | None
    price: float
    original_price: float | None
    discount_pct: int | None
    condition: str | None
    size: str | None
    category: str | None
    image_url: str
    item_url: str
    brand_tier: str | None
    brand_category: str | None
    item_score: int
    detected_materials: list[str]
    filter_status: str
    first_seen_at: datetime | None = None

    class Config:
        from_attributes = True


class ItemListResponse(BaseModel):
    """Paginated list of items."""

    items: list[ItemResponse]
    total: int
    page: int
    per_page: int
    pages: int


class ScrapeResponse(BaseModel):
    """Response after a scrape operation."""

    status: str
    total_items: int
    new_items: int
    grails_found: int
    trash_filtered: int
    message: str


class StatsResponse(BaseModel):
    """Database statistics."""

    total_items: int
    grails_count: int
    brands_tracked: int
    newest_item_date: datetime | None
    last_scrape: datetime | None


class BrandInfo(BaseModel):
    """Information about a tracked brand."""

    name: str
    category: str
    tier: str
    items_count: int


class PriceDataResponse(BaseModel):
    """Price data from a platform."""

    min: float | None
    avg: float | None
    max: float | None
    count: int


class ArbitrageResponse(BaseModel):
    """Arbitrage analysis response."""

    sellpy_price_eur: float
    grailed_data: PriceDataResponse | None
    ebay_data: PriceDataResponse | None
    estimated_market_value: float | None
    potential_profit: float | None
    profit_margin_pct: float | None
    deal_rating: str
    confidence_score: float


# Dependency
async def get_db() -> AsyncSession:
    """Get database session dependency."""
    async for session in get_session():
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy", "service": "grail-hunter"}


@router.get("/brands", response_model=list[BrandInfo])
async def list_brands(session: SessionDep) -> list[BrandInfo]:
    """List all tracked brands with item counts."""
    classifier = BrandClassifier()
    brands_info: list[BrandInfo] = []

    for brand in sorted(ALL_BRANDS):
        match = classifier.classify(brand)

        # Count items for this brand
        count_result = await session.execute(
            select(func.count(Item.id)).where(Item.brand == brand)
        )
        count = count_result.scalar() or 0

        brands_info.append(
            BrandInfo(
                name=brand,
                category=match.category.value,
                tier=match.tier.value,
                items_count=count,
            )
        )

    return brands_info


@router.get("/items", response_model=ItemListResponse)
async def list_items(
    session: SessionDep,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    tier: str | None = Query(None, description="Filter by tier (TIER_1, TIER_2, TIER_3)"),
    brand: str | None = Query(None, description="Filter by brand name"),
    min_score: int | None = Query(None, description="Minimum item score"),
    status: str = Query("valid", description="Filter status (valid, trash, all)"),
) -> ItemListResponse:
    """List items with pagination and filtering."""
    query = select(Item)

    # Apply filters
    if tier:
        query = query.where(Item.brand_tier == tier)
    if brand:
        query = query.where(Item.brand.ilike(f"%{brand}%"))
    if min_score:
        query = query.where(Item.item_score >= min_score)
    if status != "all":
        query = query.where(Item.filter_status == status)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate and order
    query = query.order_by(Item.item_score.desc(), Item.first_seen_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await session.execute(query)
    items = result.scalars().all()

    return ItemListResponse(
        items=[
            ItemResponse(
                object_id=item.object_id,
                title=item.title,
                brand=item.brand,
                price=item.price,
                original_price=item.original_price,
                discount_pct=item.discount_pct,
                condition=item.condition,
                size=item.size,
                category=item.category,
                image_url=item.image_url,
                item_url=item.item_url,
                brand_tier=item.brand_tier,
                brand_category=item.brand_category,
                item_score=item.item_score,
                detected_materials=(
                    item.detected_materials.split(",") if item.detected_materials else []
                ),
                filter_status=item.filter_status,
                first_seen_at=item.first_seen_at,
            )
            for item in items
        ],
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page,
    )


@router.get("/items/grails", response_model=list[ItemResponse])
async def list_grails(
    session: SessionDep,
    limit: int = Query(50, ge=1, le=200),
) -> list[ItemResponse]:
    """Get top grail items (Tier 1 brands, highest scores)."""
    query = (
        select(Item)
        .where(Item.brand_tier == "TIER_1")
        .where(Item.filter_status == "valid")
        .order_by(Item.item_score.desc(), Item.first_seen_at.desc())
        .limit(limit)
    )

    result = await session.execute(query)
    items = result.scalars().all()

    return [
        ItemResponse(
            object_id=item.object_id,
            title=item.title,
            brand=item.brand,
            price=item.price,
            original_price=item.original_price,
            discount_pct=item.discount_pct,
            condition=item.condition,
            size=item.size,
            category=item.category,
            image_url=item.image_url,
            item_url=item.item_url,
            brand_tier=item.brand_tier,
            brand_category=item.brand_category,
            item_score=item.item_score,
            detected_materials=(
                item.detected_materials.split(",") if item.detected_materials else []
            ),
            filter_status=item.filter_status,
            first_seen_at=item.first_seen_at,
        )
        for item in items
    ]


@router.get("/items/{object_id}", response_model=ItemResponse)
async def get_item(object_id: str, session: SessionDep) -> ItemResponse:
    """Get a single item by object_id."""
    result = await session.execute(
        select(Item).where(Item.object_id == object_id)
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    return ItemResponse(
        object_id=item.object_id,
        title=item.title,
        brand=item.brand,
        price=item.price,
        original_price=item.original_price,
        discount_pct=item.discount_pct,
        condition=item.condition,
        size=item.size,
        category=item.category,
        image_url=item.image_url,
        item_url=item.item_url,
        brand_tier=item.brand_tier,
        brand_category=item.brand_category,
        item_score=item.item_score,
        detected_materials=(
            item.detected_materials.split(",") if item.detected_materials else []
        ),
        filter_status=item.filter_status,
        first_seen_at=item.first_seen_at,
    )


@router.post("/scrape", response_model=ScrapeResponse)
async def trigger_scrape(
    session: SessionDep,
    category: str = Query("Miehet", description="Category to scrape"),
    max_pages: int = Query(5, ge=1, le=20, description="Maximum pages to fetch"),
) -> ScrapeResponse:
    """Trigger a new scrape of Sellpy."""
    # Create scrape run record
    scrape_run = ScrapeRun(status="running")
    session.add(scrape_run)
    await session.commit()

    try:
        async with SellpyScraper() as scraper:
            items = await scraper.fetch_all_pages(
                category=category,
                max_pages=max_pages,
            )

        # Process and save items
        new_items = 0
        grails_found = 0
        trash_filtered = 0

        for scraped_item in items:
            # Check if exists
            existing = await session.execute(
                select(Item).where(Item.object_id == scraped_item.object_id)
            )
            if existing.scalar_one_or_none():
                continue

            # Count stats
            if scraped_item.filter_status == "trash":
                trash_filtered += 1
                continue

            if scraped_item.brand_tier == "TIER_1":
                grails_found += 1

            # Create new item
            db_item = Item(
                object_id=scraped_item.object_id,
                title=scraped_item.title,
                brand=scraped_item.brand,
                price=scraped_item.price,
                original_price=scraped_item.original_price,
                discount_pct=scraped_item.discount_pct,
                condition=scraped_item.condition,
                description=scraped_item.description,
                size=scraped_item.size,
                color=scraped_item.color,
                category=scraped_item.category,
                image_url=scraped_item.image_url,
                item_url=scraped_item.item_url,
                brand_tier=scraped_item.brand_tier,
                brand_category=scraped_item.brand_category,
                item_score=scraped_item.item_score,
                detected_materials=(
                    ",".join(scraped_item.detected_materials)
                    if scraped_item.detected_materials
                    else None
                ),
                filter_status=scraped_item.filter_status,
                sale_started_at=scraped_item.sale_started_at,
            )
            session.add(db_item)
            new_items += 1

        # Update scrape run
        scrape_run.status = "completed"
        scrape_run.completed_at = datetime.utcnow()
        scrape_run.total_items = len(items)
        scrape_run.new_items = new_items
        scrape_run.grails_found = grails_found
        scrape_run.trash_filtered = trash_filtered

        await session.commit()

        return ScrapeResponse(
            status="completed",
            total_items=len(items),
            new_items=new_items,
            grails_found=grails_found,
            trash_filtered=trash_filtered,
            message=f"Scrape completed! Found {new_items} new items, {grails_found} grails.",
        )

    except Exception as e:
        scrape_run.status = "failed"
        scrape_run.error_message = str(e)
        scrape_run.completed_at = datetime.utcnow()
        await session.commit()

        raise HTTPException(status_code=500, detail=f"Scrape failed: {str(e)}")


@router.get("/stats", response_model=StatsResponse)
async def get_stats(session: SessionDep) -> StatsResponse:
    """Get database statistics."""
    # Total items
    total_result = await session.execute(
        select(func.count(Item.id)).where(Item.filter_status == "valid")
    )
    total = total_result.scalar() or 0

    # Grails count
    grails_result = await session.execute(
        select(func.count(Item.id)).where(
            Item.brand_tier == "TIER_1",
            Item.filter_status == "valid",
        )
    )
    grails = grails_result.scalar() or 0

    # Unique brands
    brands_result = await session.execute(
        select(func.count(func.distinct(Item.brand))).where(Item.filter_status == "valid")
    )
    brands = brands_result.scalar() or 0

    # Newest item
    newest_result = await session.execute(
        select(func.max(Item.first_seen_at))
    )
    newest = newest_result.scalar()

    # Last scrape
    last_scrape_result = await session.execute(
        select(func.max(ScrapeRun.completed_at)).where(ScrapeRun.status == "completed")
    )
    last_scrape = last_scrape_result.scalar()

    return StatsResponse(
        total_items=total,
        grails_count=grails,
        brands_tracked=brands,
        newest_item_date=newest,
        last_scrape=last_scrape,
    )


@router.get("/arbitrage/{object_id}", response_model=ArbitrageResponse)
async def analyze_arbitrage(object_id: str, session: SessionDep) -> ArbitrageResponse:
    """
    Analyze arbitrage opportunity for a specific item.

    Compares Sellpy price against Grailed and eBay market prices.
    """
    # Get item from database
    result = await session.execute(
        select(Item).where(Item.object_id == object_id)
    )
    db_item = result.scalar_one_or_none()

    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")

    # Convert to SellpyItem for arbitrage service
    sellpy_item = SellpyItem(
        object_id=db_item.object_id,
        title=db_item.title,
        brand=db_item.brand,
        price=db_item.price,
        original_price=db_item.original_price,
        discount_pct=db_item.discount_pct,
        condition=db_item.condition,
        description=db_item.description,
        size=db_item.size,
        color=db_item.color,
        category=db_item.category,
        image_url=db_item.image_url,
        item_url=db_item.item_url,
        sale_started_at=db_item.sale_started_at,
    )

    # Run arbitrage analysis
    async with ArbitrageService() as service:
        analysis = await service.analyze_item(sellpy_item)

    return ArbitrageResponse(
        sellpy_price_eur=analysis.sellpy_price_eur,
        grailed_data=PriceDataResponse(
            min=analysis.grailed_data.min_price,
            avg=analysis.grailed_data.avg_price,
            max=analysis.grailed_data.max_price,
            count=analysis.grailed_data.sample_count,
        ) if analysis.grailed_data else None,
        ebay_data=PriceDataResponse(
            min=analysis.ebay_data.min_price,
            avg=analysis.ebay_data.avg_price,
            max=analysis.ebay_data.max_price,
            count=analysis.ebay_data.sample_count,
        ) if analysis.ebay_data else None,
        estimated_market_value=analysis.estimated_market_value,
        potential_profit=analysis.potential_profit,
        profit_margin_pct=analysis.profit_margin_pct,
        deal_rating=analysis.deal_rating.value,
        confidence_score=analysis.confidence_score,
    )


@router.post("/arbitrage/batch")
async def analyze_arbitrage_batch(
    session: SessionDep,
    limit: int = Query(10, ge=1, le=50, description="Max items to analyze"),
    tier: str = Query("TIER_1", description="Filter by tier"),
) -> list[dict]:
    """
    Analyze arbitrage for multiple items at once.

    Returns top deals sorted by profit margin.
    """
    # Get items from database
    query = (
        select(Item)
        .where(Item.brand_tier == tier)
        .where(Item.filter_status == "valid")
        .order_by(Item.item_score.desc())
        .limit(limit)
    )

    result = await session.execute(query)
    db_items = result.scalars().all()

    # Convert to SellpyItems
    sellpy_items = [
        SellpyItem(
            object_id=item.object_id,
            title=item.title,
            brand=item.brand,
            price=item.price,
            original_price=item.original_price,
            discount_pct=item.discount_pct,
            condition=item.condition,
            description=item.description,
            size=item.size,
            color=item.color,
            category=item.category,
            image_url=item.image_url,
            item_url=item.item_url,
            sale_started_at=item.sale_started_at,
        )
        for item in db_items
    ]

    # Run arbitrage analysis
    async with ArbitrageService() as service:
        deals = await service.find_deals(sellpy_items)

    return [deal.to_dict() for deal in deals]
