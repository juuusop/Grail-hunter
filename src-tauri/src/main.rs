// Prevents additional console window on Windows in release
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::process::Command;
use tauri::Manager;

const API_BASE: &str = "http://localhost:8000/api";

#[derive(Debug, Serialize, Deserialize)]
struct Item {
    object_id: String,
    title: String,
    brand: Option<String>,
    price: f64,
    original_price: Option<f64>,
    discount_pct: Option<i32>,
    condition: Option<String>,
    size: Option<String>,
    category: Option<String>,
    image_url: String,
    item_url: String,
    brand_tier: Option<String>,
    brand_category: Option<String>,
    item_score: i32,
    detected_materials: Vec<String>,
    filter_status: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct ItemsResponse {
    items: Vec<Item>,
    total: i32,
    page: i32,
    per_page: i32,
    pages: i32,
}

#[derive(Debug, Serialize, Deserialize)]
struct ScrapeResult {
    status: String,
    total_items: i32,
    new_items: i32,
    grails_found: i32,
    trash_filtered: i32,
    message: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct ArbitrageData {
    sellpy_price_eur: f64,
    grailed_data: Option<PriceData>,
    ebay_data: Option<PriceData>,
    estimated_market_value: Option<f64>,
    potential_profit: Option<f64>,
    profit_margin_pct: Option<f64>,
    deal_rating: String,
    confidence_score: f64,
}

#[derive(Debug, Serialize, Deserialize)]
struct PriceData {
    min: Option<f64>,
    avg: Option<f64>,
    max: Option<f64>,
    count: i32,
}

#[derive(Debug, Serialize, Deserialize)]
struct Stats {
    total_items: i32,
    grails_count: i32,
    brands_tracked: i32,
}

#[derive(Debug, Deserialize)]
struct Filters {
    tier: Option<String>,
    brand: Option<String>,
    min_price: Option<f64>,
    max_price: Option<f64>,
    min_score: Option<i32>,
    category: Option<String>,
}

/// Fetch items from Python backend
#[tauri::command]
async fn fetch_items(filters: Filters) -> Result<Vec<Item>, String> {
    let client = reqwest::Client::new();

    let mut url = format!("{}/items?", API_BASE);

    if let Some(tier) = &filters.tier {
        url.push_str(&format!("tier={}&", tier));
    }
    if let Some(brand) = &filters.brand {
        url.push_str(&format!("brand={}&", brand));
    }
    if let Some(min_score) = filters.min_score {
        url.push_str(&format!("min_score={}&", min_score));
    }

    let response = client
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("Request failed: {}", e))?;

    let data: ItemsResponse = response
        .json()
        .await
        .map_err(|e| format!("Parse failed: {}", e))?;

    Ok(data.items)
}

/// Trigger a new scrape
#[tauri::command]
async fn trigger_scrape(category: String, max_pages: i32) -> Result<ScrapeResult, String> {
    let client = reqwest::Client::new();

    let url = format!("{}/scrape?category={}&max_pages={}", API_BASE, category, max_pages);

    let response = client
        .post(&url)
        .send()
        .await
        .map_err(|e| format!("Request failed: {}", e))?;

    let result: ScrapeResult = response
        .json()
        .await
        .map_err(|e| format!("Parse failed: {}", e))?;

    Ok(result)
}

/// Analyze arbitrage for an item
#[tauri::command]
async fn analyze_arbitrage(object_id: String) -> Result<ArbitrageData, String> {
    let client = reqwest::Client::new();

    let url = format!("{}/arbitrage/{}", API_BASE, object_id);

    let response = client
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("Request failed: {}", e))?;

    let data: ArbitrageData = response
        .json()
        .await
        .map_err(|e| format!("Parse failed: {}", e))?;

    Ok(data)
}

/// Fetch grail items
#[tauri::command]
async fn fetch_grails(limit: i32) -> Result<Vec<Item>, String> {
    let client = reqwest::Client::new();

    let url = format!("{}/items/grails?limit={}", API_BASE, limit);

    let response = client
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("Request failed: {}", e))?;

    let items: Vec<Item> = response
        .json()
        .await
        .map_err(|e| format!("Parse failed: {}", e))?;

    Ok(items)
}

/// Get stats
#[tauri::command]
async fn get_stats() -> Result<Stats, String> {
    let client = reqwest::Client::new();

    let url = format!("{}/stats", API_BASE);

    let response = client
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("Request failed: {}", e))?;

    let stats: Stats = response
        .json()
        .await
        .map_err(|e| format!("Parse failed: {}", e))?;

    Ok(stats)
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            fetch_items,
            trigger_scrape,
            analyze_arbitrage,
            fetch_grails,
            get_stats
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
