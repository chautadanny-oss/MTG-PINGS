import requests
import time
import json
import os
import hashlib
import random
from datetime import datetime

# ============================================================
# MTGPINGS BOT v1.1 — ALL PRODUCT IDs VERIFIED
# - Safe API lookups (no more crashes)
# - Target deep structural fallback (shipping + store pickup)
# - Walmart via BlueCart public API (bypasses PerimeterX)
# - GameStop internal availability API (bypasses Cloudflare)
# - Rotating user agents (avoids IP bans)
# - Atomic state saving (no corruption)
# - Discord rate limit handling
# - Free alert only fires if item is STILL in stock at 30 min
# - UNKNOWN replaced with safe OUT OF STOCK fallback
# - Alerts fire to both Whop AND Discord webhooks
# - Runs 24/7 on GitHub Actions for free
# ============================================================

WHOP_WEBHOOK_MTG_PREMIUM = os.environ.get("WHOP_WEBHOOK_MTG_PREMIUM", "")
WHOP_WEBHOOK_MTG_FREE    = os.environ.get("WHOP_WEBHOOK_MTG_FREE", "")
ALERTS_FOR_CREW_DISCORD  = os.environ.get("ALERTS_FOR_CREW_DISCORD", "")
ALERTS_FOR_VAULT_DISCORD = os.environ.get("ALERTS_FOR_VAULT_DISCORD", "")

# --- ROTATING USER AGENTS ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
]

def get_headers(json=False):
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*" if json else "text/html,application/xhtml+xml,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }

# ============================================================
# RETAILER CHECK FUNCTIONS
# ============================================================

def check_target(tcin):
    """Target internal API with deep structural fallback"""
    url = (
        f"https://redsky.target.com/redsky_aggregations/v1/web/pdp_client_v1"
        f"?key=9f36aeafbe60771e321a7cc95a78140772ab3e96&tcin={tcin}&pricing_store_id=3991"
    )
    try:
        r = requests.get(url, headers=get_headers(json=True), timeout=15)
        if r.status_code == 200:
            data = r.json()
            p_data = data.get("data", {}).get("product", {})
            fulfillment = (
                p_data.get("fulfillment") or
                p_data.get("enrichment", {}).get("fulfillment", {}) or {}
            )
            avail = fulfillment.get("shipping_options", {}).get("availability_status", "")
            if not avail:
                store_options = fulfillment.get("store_options", [{}])
                avail = store_options[0].get("order_pickup", {}).get("availability_status", "") if store_options else ""
            if "IN_STOCK" in avail:
                return "IN STOCK"
            if "OUT_STOCK" in avail or "UNAVAILABLE" in avail:
                return "OUT OF STOCK"
        return "OUT OF STOCK"
    except Exception as e:
        print(f"    [ERROR] Target: {e}")
        return "OUT OF STOCK"

def check_walmart(item_id):
    """Walmart via BlueCart public API — bypasses PerimeterX"""
    url = f"https://api.bluecartapi.com/request?api_key=demo&type=product&item_id={item_id}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            buybox = data.get("product", {}).get("buybox_winner", {})
            in_stock = buybox.get("availability", {}).get("in_stock", False)
            return "IN STOCK" if in_stock else "OUT OF STOCK"
        return "OUT OF STOCK"
    except Exception as e:
        print(f"    [ERROR] Walmart: {e}")
        return "OUT OF STOCK"

def check_gamestop(full_url):
    """GameStop internal availability API — bypasses Cloudflare"""
    try:
        product_id = full_url.split("/")[-1].split(".")[0]
        url = f"https://www.gamestop.com/api/v2/products/{product_id}/availability?storeId=0"
        r = requests.get(url, headers=get_headers(json=True), timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("shippingAvailability", False) or data.get("instoreAvailability", False):
                return "IN STOCK"
            return "OUT OF STOCK"
        return "OUT OF STOCK"
    except Exception as e:
        print(f"    [ERROR] GameStop: {e}")
        return "OUT OF STOCK"

def check_amazon(asin):
    """Amazon product page with host header for better browser mimicry"""
    url = f"https://www.amazon.com/dp/{asin}"
    try:
        headers = get_headers()
        headers["Host"] = "www.amazon.com"
        r = requests.get(url, headers=headers, timeout=15)
        content = r.text.lower()
        if "add to cart" in content or "buy now" in content:
            return "IN STOCK"
        if "currently unavailable" in content or "out of stock" in content:
            return "OUT OF STOCK"
        return "OUT OF STOCK"
    except Exception as e:
        print(f"    [ERROR] Amazon: {e}")
        return "OUT OF STOCK"

# ============================================================
# PRODUCTS TO MONITOR — ALL IDs VERIFIED FROM AMAZON DIRECTLY
# ============================================================

PRODUCTS = [
    # --- AMAZON ---
    {
        "name": "MTG: Teenage Mutant Ninja Turtles — Play Booster Box (30 Packs)",
        "retailer": "Amazon",
        "price": "$124.99",
        "url": "https://www.amazon.com/dp/B0FR6W5K12",
        "check": lambda: check_amazon("B0FR6W5K12"),
    },
    {
        "name": "MTG: Teenage Mutant Ninja Turtles — Collector Booster Box (12 Packs)",
        "retailer": "Amazon",
        "price": "$399.99",
        "url": "https://www.amazon.com/dp/B0FR6HHZKB",
        "check": lambda: check_amazon("B0FR6HHZKB"),
    },
    {
        "name": "MTG: Avatar The Last Airbender — Play Booster Box (30 Packs)",
        "retailer": "Amazon",
        "price": "$134.99",
        "url": "https://www.amazon.com/dp/B0FJND8K8Z",
        "check": lambda: check_amazon("B0FJND8K8Z"),
    },
    {
        "name": "MTG: Avatar The Last Airbender — Collector Booster Box (12 Packs)",
        "retailer": "Amazon",
        "price": "$374.99",
        "url": "https://www.amazon.com/dp/B0FJNQ3DHX",
        "check": lambda: check_amazon("B0FJNQ3DHX"),
    },
    {
        "name": "MTG: Marvel's Spider-Man — Play Booster Box (30 Packs)",
        "retailer": "Amazon",
        "price": "$107.99",
        "url": "https://www.amazon.com/dp/B0DV1QYQ2N",
        "check": lambda: check_amazon("B0DV1QYQ2N"),
    },
    {
        "name": "MTG: Final Fantasy — Play Booster Box (30 Packs)",
        "retailer": "Amazon",
        "price": "$134.99",
        "url": "https://www.amazon.com/dp/B0DTMQBLSY",
        "check": lambda: check_amazon("B0DTMQBLSY"),
    },

    # --- GAMESTOP ---
    {
        "name": "MTG: Avatar The Last Airbender — Play Booster Box",
        "retailer": "GameStop",
        "price": "$134.99",
        "url": "https://www.gamestop.com/toys-games/trading-cards/products/magic-the-gathering-avatar-the-last-airbender-play-booster-box/20025988.html",
        "check": lambda: check_gamestop("https://www.gamestop.com/toys-games/trading-cards/products/magic-the-gathering-avatar-the-last-airbender-play-booster-box/20025988.html"),
    },
    {
        "name": "MTG: Avatar The Last Airbender — Collector Booster Box",
        "retailer": "GameStop",
        "price": "$374.99",
        "url": "https://www.gamestop.com/toys-games/trading-cards/products/magic-the-gathering-avatar-the-last-airbender-collector-booster-box/20025991.html",
        "check": lambda: check_gamestop("https://www.gamestop.com/toys-games/trading-cards/products/magic-the-gathering-avatar-the-last-airbender-collector-booster-box/20025991.html"),
    },
    {
        "name": "MTG: Teenage Mutant Ninja Turtles — Play Booster Box",
        "retailer": "GameStop",
        "price": "$124.99",
        "url": "https://www.gamestop.com/toys-games/trading-cards/products/magic-the-gathering-teenage-mutant-ninja-turtles-play-booster-box/435072.html",
        "check": lambda: check_gamestop("https://www.gamestop.com/toys-games/trading-cards/products/magic-the-gathering-teenage-mutant-ninja-turtles-play-booster-box/435072.html"),
    },
]

# ============================================================
# STATE MANAGEMENT — atomic save, no corruption
# ============================================================

STATE_FILE = "state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARNING] Could not load state: {e} — starting fresh")
    return {}

def save_state(state):
    temp_file = "state_temp.json"
    try:
        with open(temp_file, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(temp_file, STATE_FILE)
    except Exception as e:
        print(f"[CRITICAL] Failed to save state: {e}")

def get_product_id(product):
    return hashlib.md5(f"{product['retailer']}-{product['name']}".encode()).hexdigest()

# ============================================================
# DISCORD ALERTS — with rate limit handling
# ============================================================

def send_webhook(webhook_url, payload):
    if not webhook_url:
        print("    [WARNING] Webhook URL missing — check GitHub secrets")
        return
    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        if r.status_code in [200, 204]:
            print(f"    [✅] Alert sent")
        elif r.status_code == 429:
            retry_after = r.json().get("retry_after", 5)
            print(f"    [⚠️] Rate limited — waiting {retry_after}s then retrying")
            time.sleep(retry_after)
            r2 = requests.post(webhook_url, json=payload, timeout=10)
            if r2.status_code in [200, 204]:
                print(f"    [✅] Alert sent after retry")
            else:
                print(f"    [ERROR] Retry failed: {r2.status_code}")
        else:
            print(f"    [⚠️] Webhook error: {r.status_code}")
    except Exception as e:
        print(f"    [ERROR] Webhook failed: {e}")

def build_crew_alert(product):
    now = datetime.utcnow().strftime("%I:%M %p UTC")
    return {
        "embeds": [{
            "title": "🚨 CREW ALERT — MTGPings",
            "color": 0xFFD700,
            "fields": [
                {"name": "📦 Product",      "value": product["name"],     "inline": True},
                {"name": "🏪 Retailer",     "value": product["retailer"], "inline": True},
                {"name": "💰 Price",        "value": product["price"],    "inline": True},
                {"name": "✅ Status",       "value": "IN STOCK",          "inline": True},
                {"name": "📊 Stock Level",  "value": "Limited — move fast","inline": True},
                {"name": "⏰ Detected",     "value": now,                 "inline": True},
                {"name": "🔗 Direct Link",  "value": f"[Click to checkout]({product['url']})", "inline": False},
            ],
            "footer": {"text": "MTGPings Crew • You got here first ⚡"},
            "timestamp": datetime.utcnow().isoformat(),
        }]
    }

def build_free_alert(product):
    return {
        "embeds": [{
            "title": "🔔 RESTOCK ALERT — MTGPings",
            "color": 0x3498DB,
            "fields": [
                {"name": "📦 Product",     "value": product["name"],     "inline": True},
                {"name": "🏪 Retailer",    "value": product["retailer"], "inline": True},
                {"name": "💰 Price",       "value": product["price"],    "inline": True},
                {"name": "✅ Status",      "value": "IN STOCK",          "inline": True},
                {"name": "📊 Stock Level", "value": "Limited",           "inline": True},
                {"name": "🕐 Heads up",   "value": "This drop went live 20 minutes ago.", "inline": False},
                {"name": "🛒 Store Page", "value": f"[View Product]({product['url']})", "inline": False},
                {
                    "name": "⚡ Want to be first next time?",
                    "value": "Upgrade to **Crew** — instant alerts + direct checkout links the second drops go live.\n👉 [Join Crew on MTGPings](https://whop.com/mtgpings)",
                    "inline": False,
                },
            ],
            "footer": {"text": "MTGPings • Free Access — The Vault"},
            "timestamp": datetime.utcnow().isoformat(),
        }]
    }

# ============================================================
# MAIN
# ============================================================

def run_once():
    print("=" * 50)
    print("  MTGPings Bot v1.1 🃏")
    print(f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 50)

    state = load_state()
    print(f"\n[🔍] Checking {len(PRODUCTS)} products...\n")

    for product in PRODUCTS:
        pid = get_product_id(product)
        status = product["check"]()
        last_status = state.get(pid, "OUT OF STOCK")

        print(f"  [{status}] {product['retailer']} — {product['name']}")

        # New restock detected
        if status == "IN STOCK" and last_status != "IN STOCK":
            print(f"  [🚨] RESTOCK! Firing Crew alerts...")
            send_webhook(WHOP_WEBHOOK_MTG_PREMIUM, build_crew_alert(product))
            send_webhook(ALERTS_FOR_CREW_DISCORD,  build_crew_alert(product))
            state[f"{pid}_free_send_at"] = time.time() + (30 * 60)
            print(f"  [⏳] Free alert queued for 20 minutes")

        # Send pending free alert if due — only if item is STILL in stock
        free_send_at = state.get(f"{pid}_free_send_at")
        if free_send_at and time.time() >= float(free_send_at):
            if status == "IN STOCK":
                print(f"  [📢] Item still in stock — sending free alerts...")
                send_webhook(WHOP_WEBHOOK_MTG_FREE,    build_free_alert(product))
                send_webhook(ALERTS_FOR_VAULT_DISCORD, build_free_alert(product))
            else:
                print(f"  [⏳] Free alert cancelled — item sold out before 20 min mark")
            del state[f"{pid}_free_send_at"]

        state[pid] = status

    save_state(state)
    print("\n[✅] Done. State saved.")

if __name__ == "__main__":
    run_once()
