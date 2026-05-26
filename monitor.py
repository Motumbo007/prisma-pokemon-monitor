import requests
from bs4 import BeautifulSoup
import json
import os
import sys

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID        = '8001155433'
STATE_FILE     = 'state.json'

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'fi-FI,fi;q=0.9',
}

SOURCES = [
    {
        'label':        'Pokemon TCG -kategoria',
        'base_url':     'https://www.prisma.fi/tuotemerkit/pokemon/kategoria/1559/kerailykortit-ja-tuotteet',
        'page_url':     'https://www.prisma.fi/kategoriat/1559/kerailykortit-ja-tuotteet?page={}',
        'max_pages':    6,
        'pokemon_only': False,
    },
    {
        'label':        'Elektroniikan uutuudet',
        'base_url':     'https://www.prisma.fi/kategoriat/3120/elektroniikan-uutuudet',
        'page_url':     'https://www.prisma.fi/kategoriat/3120/elektroniikan-uutuudet?page={}',
        'max_pages':    10,
        'pokemon_only': True,
    },
]

# ── Scraping ──────────────────────────────────────────────────────────────────
def fetch_page(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f'[WARN] Could not fetch {url}: {e}')
        return None


def parse_products(html, pokemon_only=False):
    """
    Each product is an <a href="/tuotteet/..."> inside a <li>.
    The <li> may contain 'Ei saatavilla' if out of stock.
    """
    soup = BeautifulSoup(html, 'html.parser')
    products = {}

    product_links = soup.find_all('a', href=lambda h: h and '/tuotteet/' in h)

    for link in product_links:
        name = link.get_text(strip=True)

        if not name or len(name) < 5:
            continue

        if pokemon_only and 'okemon' not in name:
            continue

        # Find the nearest <li> parent — that's the product card
        li = link.find_parent('li')
        if li:
            is_available = 'Ei saatavilla' not in li.get_text()
        else:
            # Fallback: check just the link's immediate parent
            is_available = 'Ei saatavilla' not in link.parent.get_text()

        product_url = 'https://www.prisma.fi' + link['href'].split('?')[0]
        products[name] = {'available': is_available, 'url': product_url}

    return products


def get_all_products():
    all_products = {}

    for source in SOURCES:
        print(f"Checking: {source['label']}")
        found_on_source = 0

        for page_num in range(1, source['max_pages'] + 1):
            url  = source['base_url'] if page_num == 1 else source['page_url'].format(page_num)
            html = fetch_page(url)

            if not html:
                break

            page_products = parse_products(html, pokemon_only=source['pokemon_only'])

            if not page_products:
                break

            found_on_source += len(page_products)
            all_products.update(page_products)

        print(f"  -> {found_on_source} products found")

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
        print('[OK] Telegram alert sent')
    except Exception as e:
        print(f'[ERROR] Telegram failed: {e}')


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print('=== Prisma Pokemon Monitor ===')
    old_state = load_state()
    new_state = get_all_products()

    if not new_state:
        print('[WARN] No products found — Prisma may have blocked the scraper.')
        sys.exit(0)

    print(f'Total products found: {len(new_state)} | Previously tracked: {len(old_state)}')

    alerts = []

    for name, info in new_state.items():
        prev      = old_state.get(name)
        available = info['available']
        url       = info['url']

        if prev is None:
            status = '✅ Saatavilla' if available else '❌ Ei saatavilla'
            alerts.append(
                f'🆕 <b>UUSI TUOTE</b>\n{name}\n{status}\n'
                f'🔗 <a href="{url}">Katso Prismasta</a>'
            )
        elif available and not prev.get('available'):
            alerts.append(
                f'🔄 <b>RESTOCK!</b>\n{name}\n✅ Nyt saatavilla!\n'
                f'🔗 <a href="{url}">Osta nyt</a>'
            )

    if alerts:
        print(f'Sending {len(alerts)} alerts...')
        for i in range(0, len(alerts), 5):
            batch   = alerts[i:i+5]
            message = '🎴 <b>Prisma Pokémon Alert</b>\n\n' + '\n\n'.join(batch)
            send_telegram(message)
    else:
        print('No changes detected.')

    save_state(new_state)
    print('Done.')


if __name__ == '__main__':
    main()
