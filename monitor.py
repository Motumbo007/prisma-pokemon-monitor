import requests
from bs4 import BeautifulSoup
import json
import os
import sys

# ── Config ──────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID        = '8001155433'
STATE_FILE     = 'state.json'

BASE_URL  = 'https://www.prisma.fi/tuotemerkit/pokemon/kategoria/1559/kerailykortit-ja-tuotteet'
PAGE_URL  = 'https://www.prisma.fi/kategoriat/1559/kerailykortit-ja-tuotteet?page={}'

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'fi-FI,fi;q=0.9',
}

# ── Scraping ─────────────────────────────────────────────────────────────────
def fetch_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f'[WARN] Could not fetch {url}: {e}')
        return None


def parse_products(html):
    """Return dict of {product_name: is_available (bool)}"""
    soup = BeautifulSoup(html, 'html.parser')
    products = {}

    # Prisma renders product cards — try several common selectors
    cards = (
        soup.select('div[class*="ProductCard"]') or
        soup.select('li[class*="product"]') or
        soup.select('article[class*="product"]') or
        soup.select('div[class*="product-card"]') or
        soup.select('div[class*="ProductItem"]')
    )

    if not cards:
        # Fallback: find all elements containing a price
        cards = soup.find_all(lambda tag: tag.name in ('div', 'li', 'article')
                              and tag.find(string=lambda s: s and '€' in s))

    for card in cards:
        # Name: first heading or strong inside the card
        name_el = (
            card.find(['h2', 'h3', 'h4', 'strong']) or
            card.find(class_=lambda c: c and 'name' in c.lower()) or
            card.find(class_=lambda c: c and 'title' in c.lower())
        )
        if not name_el:
            continue

        name = name_el.get_text(strip=True)
        if not name or len(name) < 5:
            continue

        # Availability: look for "Ei saatavilla" text anywhere in the card
        card_text = card.get_text()
        is_available = 'Ei saatavilla' not in card_text

        products[name] = is_available

    return products


def get_all_products():
    all_products = {}

    # Page 1
    html = fetch_page(BASE_URL)
    if html:
        all_products.update(parse_products(html))

    # Pages 2–5 (Prisma rarely has more than 3 pages of Pokemon)
    for page_num in range(2, 6):
        url  = PAGE_URL.format(page_num)
        html = fetch_page(url)
        if not html:
            break
        found = parse_products(html)
        if not found:
            break  # No more products — stop
        all_products.update(found)

    return all_products


# ── State ─────────────────────────────────────────────────────────────────────
def load_state():
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# ── Telegram ──────────────────────────────────────────────────────────────────
def send_telegram(message):
    if not TELEGRAM_TOKEN:
        print('[ERROR] TELEGRAM_TOKEN not set')
        return
    url  = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    data = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'HTML'}
    try:
        r = requests.post(url, data=data, timeout=10)
        r.raise_for_status()
        print('[OK] Telegram message sent')
    except Exception as e:
        print(f'[ERROR] Telegram send failed: {e}')


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print('Fetching Prisma Pokemon products...')
    old_state   = load_state()
    new_state   = get_all_products()

    if not new_state:
        print('[WARN] No products found — Prisma may have blocked the request or changed their HTML. Skipping.')
        sys.exit(0)

    print(f'Found {len(new_state)} products. Previously tracked: {len(old_state)}.')

    alerts = []

    for name, is_available in new_state.items():
        prev = old_state.get(name)

        if prev is None:
            # Brand new product we've never seen
            status_icon = '✅ Saatavilla' if is_available else '❌ Ei saatavilla'
            alerts.append(f'🆕 <b>UUSI TUOTE</b>\n{name}\n{status_icon}')

        elif is_available and not prev:
            # Was out of stock, now in stock
            alerts.append(
                f'🔄 <b>RESTOCK!</b>\n{name}\n✅ Nyt saatavilla!\n'
                f'🔗 <a href="{BASE_URL}">Osta nyt → Prisma</a>'
            )

    if alerts:
        message = '🎴 <b>Prisma Pokémon Alert</b>\n\n' + '\n\n'.join(alerts)
        send_telegram(message)
    else:
        print('No changes detected.')

    save_state(new_state)
    print('Done.')


if __name__ == '__main__':
    main()
