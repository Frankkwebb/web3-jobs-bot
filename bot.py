"""
Web3 Jobs & Opportunities Bot v3 — @justtakenbot
- Digest format: one clean summary per cycle
- English-only filter for X posts
- Dual Chat ID support
"""

import time
import hashlib
import logging
import json
import os
import re
import schedule
import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# ─── CONFIG ───────────────────────────────────────────────
BOT_TOKEN           = "8598884979:AAEMCDzsY7U8vBP84SKtwf6n5llZtAgoAZo"
CHAT_IDS            = ["1836559698", "6343548108", "6788177449"]
SEEN_FILE           = "seen_jobs_cache.json"
DATA_INTERVAL_HOURS = 12
X_INTERVAL_MINUTES  = 60
CHAINS              = ["eth", "ethereum", "sol", "solana", "bnb", "bsc", "sui"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

X_FEEDS = [
    ("X: CM/Mod/Ambassador",  "https://rss.app/feeds/mjeFNMSf9uLyamJK.xml"),
    ("X: Early Protocols",    "https://rss.app/feeds/adzhPZBeWutbdnmA.xml"),
    ("X: Community/Memecoin", "https://rss.app/feeds/7H90BEOdSgoyw8be.xml"),
]

JOB_KEYWORDS = [
    "community manager", "ambassador", "mod ", "moderator",
    "hiring", "apply now", "we are hiring", "join our team",
    "community lead", "discord mod", "telegram mod", "community role"
]
AIRDROP_KEYWORDS = [
    "airdrop", "testnet", "early access", "whitelist", "coming soon",
    "launching soon", "join our discord", "join our telegram",
    "fair launch", "stealth launch", "new protocol", "just launched"
]
MEMECOIN_KEYWORDS = [
    "memecoin", "meme coin", "fair launch", "stealth launch",
    "new token", "just launched", "1000x", "gem", "low cap"
]

CATEGORY_META = {
    "job":        ("💼", "WEB3 JOB"),
    "airdrop":    ("🪂", "AIRDROP / EARLY ACCESS"),
    "memecoin":   ("🐸", "MEMECOIN"),
    "newlisting": ("🆕", "NEW LISTING"),
    "x_alert":    ("🐦", "X COMMUNITY ALERT"),
    "defi":       ("🦙", "NEW DEFI PROTOCOL"),
}

NON_ENGLISH_PATTERNS = [
    r'[\u4e00-\u9fff]', r'[\u3040-\u30ff]', r'[\uac00-\ud7af]',
    r'[\u0600-\u06ff]', r'[\u0400-\u04ff]', r'[\u0e00-\u0e7f]',
    r'[\u0900-\u097f]',
]

def is_english(text):
    for pattern in NON_ENGLISH_PATTERNS:
        if re.search(pattern, text):
            return False
    english_chars = len(re.findall(r'[a-zA-Z]', text))
    total_chars   = len(text.replace(" ", ""))
    if total_chars == 0:
        return True
    return (english_chars / total_chars) >= 0.5

def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r") as f:
                return set(json.load(f))
        except:
            pass
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen)[-3000:], f)

seen   = load_seen()
digest = {}

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler("jobs_bot.log"), logging.StreamHandler()]
)
log = logging.getLogger(__name__)

def is_new(text):
    h = hashlib.md5(text.encode()).hexdigest()
    if h in seen:
        return False
    seen.add(h)
    save_seen(seen)
    return True

def is_fresh(entry, hours=24):
    for field in ["published", "updated"]:
        val = entry.get(field)
        if val:
            try:
                pub = parsedate_to_datetime(val)
                if pub.tzinfo is None:
                    pub = pub.replace(tzinfo=timezone.utc)
                age = (datetime.now(timezone.utc) - pub).total_seconds() / 3600
                return age <= hours
            except:
                pass
    return True

def is_on_chain(text):
    return any(c in text.lower() for c in CHAINS)

def matches(text, keywords):
    return any(k in text.lower() for k in keywords)

def categorize_x(text):
    if matches(text, JOB_KEYWORDS):      return "job"
    if matches(text, AIRDROP_KEYWORDS):  return "airdrop"
    if matches(text, MEMECOIN_KEYWORDS): return "memecoin"
    return "x_alert"

def shorten(url):
    try:
        r = requests.get(f"https://tinyurl.com/api-create.php?url={url}", timeout=5)
        if r.status_code == 200 and r.text.startswith("http"):
            return r.text.strip()
    except:
        pass
    return url

def send(text, chat_id=None):
    targets = [chat_id] if chat_id else CHAT_IDS
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for cid in targets:
        try:
            r = requests.post(api_url, json={
                "chat_id": cid,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True
            }, timeout=10)
            r.raise_for_status()
        except Exception as e:
            log.error(f"Send error to {cid}: {e}")

def add_to_digest(category, title, url, source, snippet=""):
    emoji, label = CATEGORY_META.get(category, ("📢", "ALERT"))
    short_url    = shorten(url)
    key          = f"{emoji} {label}"
    if key not in digest:
        digest[key] = []
    digest[key].append({
        "title": title[:80],
        "url": short_url,
        "source": source,
        "snippet": snippet[:100]
    })
    log.info(f"Buffered [{category}] {title[:60]}")

def send_digest(cycle_name="Scan"):
    now   = datetime.now().strftime("%H:%M • %d %b %Y")
    total = sum(len(v) for v in digest.values())

    if not digest or total == 0:
        send(
            f"📋 *{cycle_name} — {now}*\n"
            f"{'━' * 18}\n"
            "No new alerts this cycle. Watching all sources — you'll be notified the moment a relevant opportunity drops. 👀\n"
            f"{'─' * 18}"
        )
        digest.clear()
        return

    msg = (
        f"📋 *{cycle_name} Digest — {now}*\n"
        f"{'━' * 18}\n"
        f"Found *{total} opportunit(y/ies)* across *{len(digest)} categories*\n\n"
    )

    for label, items in digest.items():
        msg += f"{label} *({len(items)})*\n"
        for item in items:
            msg += f"• {item['title']}\n  {item['url']}\n"
        msg += "\n"

    msg += f"{'─' * 18}\n"
    if "💼 WEB3 JOB" in digest:
        msg += f"💼 *{len(digest['💼 WEB3 JOB'])} job(s)* found — apply before spots fill up!\n"
    if "🪂 AIRDROP / EARLY ACCESS" in digest:
        msg += f"🪂 *{len(digest['🪂 AIRDROP / EARLY ACCESS'])} airdrop(s)* — act within hours!\n"
    if "🐸 MEMECOIN" in digest:
        msg += f"🐸 *{len(digest['🐸 MEMECOIN'])} memecoin(s)* — DYOR before engaging.\n"
    msg += "\n_First movers get the best roles. Move fast!_ 🚀"

    send(msg)
    digest.clear()

# ─── MONITORS ─────────────────────────────────────────────
def check_coinmarketcap():
    log.info("Checking CMC...")
    try:
        r    = requests.get("https://coinmarketcap.com/new/", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        for row in soup.select("table tbody tr")[:20]:
            name_el = row.find("a", href=True)
            if not name_el: continue
            name = name_el.get_text(strip=True)
            href = name_el.get("href", "")
            link = f"https://coinmarketcap.com{href}" if href.startswith("/") else href
            text = row.get_text(separator=" ", strip=True)
            if not is_on_chain(text) and not is_on_chain(name): continue
            if not is_new(f"cmc_{name}"): continue
            add_to_digest("newlisting", f"New Listing: {name}", link, "CoinMarketCap", "Newly listed — early community opportunity")
    except Exception as ex:
        log.warning(f"CMC error: {ex}")

def check_cryptorank():
    log.info("Checking CryptoRank...")
    try:
        r    = requests.get("https://cryptorank.io/upcoming-ico", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        seen_slugs = set()
        for card in soup.select("a[href]")[:30]:
            href = card.get("href", "")
            if "/currency/" not in href and "/ico/" not in href: continue
            text = card.get_text(separator=" ", strip=True)
            if len(text) < 3: continue
            slug = href.split("/")[-1]
            if slug in seen_slugs: continue
            seen_slugs.add(slug)
            full_url = f"https://cryptorank.io{href}" if href.startswith("/") else href
            if not is_new(f"cr_{slug}"): continue
            add_to_digest("airdrop", f"Upcoming: {text[:80]}", full_url, "CryptoRank", "Check for ambassador/airdrop roles")
    except Exception as ex:
        log.warning(f"CryptoRank error: {ex}")

def check_defillama():
    log.info("Checking DeFiLlama...")
    try:
        r = requests.get("https://api.llama.fi/protocols", headers={**HEADERS, "Accept": "application/json"}, timeout=15)
        recent = sorted(
            [p for p in r.json() if p.get("dateAdded")],
            key=lambda x: x.get("dateAdded", 0), reverse=True
        )[:15]
        for p in recent:
            name  = p.get("name", "")
            chain = p.get("chain", "").lower()
            slug  = p.get("slug", "")
            tvl   = p.get("tvl", 0)
            link  = f"https://defillama.com/protocol/{slug}"
            if not any(c in chain for c in ["ethereum", "solana", "bsc", "sui"]): continue
            if not is_new(f"llama_{slug}"): continue
            tvl_str = f"${tvl:,.0f}" if tvl else "N/A"
            add_to_digest("defi", f"New Protocol: {name} ({chain.upper()})", link, "DeFiLlama", f"TVL: {tvl_str} — check for community roles")
    except Exception as ex:
        log.warning(f"DeFiLlama error: {ex}")

def check_x_feeds():
    log.info("Checking X feeds...")
    for name, url in X_FEEDS:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:20]:
                title   = e.get("title", "")
                link    = e.get("link", "")
                summary = BeautifulSoup(e.get("summary", ""), "html.parser").get_text()
                full    = f"{title} {summary}"
                if not is_new(link or title): continue
                if not is_fresh(e, hours=2):  continue
                if not is_english(full):       continue
                cat = categorize_x(full)
                add_to_digest(cat, title[:120], link, name, summary[:150])
        except Exception as ex:
            log.warning(f"X feed error ({name}): {ex}")

# ─── COMMAND HANDLER ──────────────────────────────────────
last_update_id = None

def get_updates(offset=None):
    url    = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 5}
    if offset: params["offset"] = offset
    try:
        r = requests.get(url, params=params, timeout=10)
        return r.json().get("result", [])
    except:
        return []

def handle_commands():
    global last_update_id
    updates = get_updates(offset=last_update_id + 1 if last_update_id else None)
    for update in updates:
        last_update_id = update["update_id"]
        msg     = update.get("message", {})
        text    = msg.get("text", "").strip().lower()
        user_id = str(msg.get("chat", {}).get("id", ""))
        if user_id not in CHAT_IDS: continue

        if text == "/jobs":
            send("💼 *Scanning for Web3 jobs...*", chat_id=user_id)
            check_x_feeds()
            send_digest("Jobs Scan")

        elif text == "/newprotocols":
            send("⚙️ *Fetching new protocols...*", chat_id=user_id)
            check_defillama()
            send_digest("Protocols Scan")

        elif text == "/memecoins":
            send("🐸 *Scanning for memecoins...*", chat_id=user_id)
            check_x_feeds()
            send_digest("Memecoin Scan")

        elif text == "/listings":
            send("🆕 *Checking CMC & CryptoRank...*", chat_id=user_id)
            check_coinmarketcap()
            check_cryptorank()
            send_digest("Listings Scan")

        elif text == "/status":
            send(
                f"🟢 *Web3 Jobs Bot: ONLINE*\n"
                f"{'━' * 18}\n"
                f"⏰ `{datetime.now().strftime('%H:%M • %d %b %Y')}`\n"
                f"📦 Cache: `{len(seen)} entries`\n"
                f"⏱ Data scan: every `12 hrs`\n"
                f"🐦 X scan: every `60 mins`\n"
                f"⛓ Chains: `ETH | SOL | BNB | SUI`\n"
                f"👥 Users: `{len(CHAT_IDS)}`\n"
                f"{'─' * 18}",
                chat_id=user_id
            )

        elif text == "/help":
            send(
                "🤖 *Web3 Jobs Bot — Commands*\n"
                f"{'━' * 18}\n"
                "/jobs — CM/mod/ambassador roles\n"
                "/newprotocols — New protocols\n"
                "/memecoins — New memecoins\n"
                "/listings — CMC & CryptoRank\n"
                "/status — Bot health\n"
                "/help — This menu\n"
                f"{'─' * 18}",
                chat_id=user_id
            )

def set_bot_commands():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setMyCommands"
    commands = [
        {"command": "jobs",         "description": "Scan for CM/mod/ambassador roles"},
        {"command": "newprotocols", "description": "New protocols on DeFiLlama"},
        {"command": "memecoins",    "description": "New memecoins & launches"},
        {"command": "listings",     "description": "New listings CMC & CryptoRank"},
        {"command": "status",       "description": "Bot health"},
        {"command": "help",         "description": "Show all commands"},
    ]
    try:
        requests.post(url, json={"commands": commands}, timeout=10)
    except Exception as e:
        log.warning(f"Could not set commands: {e}")

def run_data_cycle():
    log.info("Running 12hr data cycle...")
    check_coinmarketcap()
    check_cryptorank()
    check_defillama()
    send_digest("12hr Data Scan")

def run_x_cycle():
    log.info("Running 1hr X cycle...")
    check_x_feeds()
    send_digest("X Feed Scan")

def main():
    log.info("Web3 Jobs Bot v3 starting...")
    set_bot_commands()
    send(
        "🤖 *Web3 Jobs & Opportunities Bot v3*\n"
        f"{'━' * 18}\n"
        "Monitoring:\n"
        "💼 CM/Mod/Ambassador roles from X _(every 1hr)_\n"
        "🪂 Airdrop & early access\n"
        "🆕 New listings — CMC & CryptoRank _(every 12hrs)_\n"
        "🦙 New protocols — DeFiLlama _(every 12hrs)_\n"
        "⛓ Chains: `ETH | SOL | BNB | SUI`\n"
        "📋 Digest format — one clean summary per cycle\n"
        "🇬🇧 English-only X filter active\n"
        f"{'─' * 18}\n"
        "_First movers get the best roles!_ 🚀"
    )
    run_data_cycle()
    run_x_cycle()
    schedule.every(DATA_INTERVAL_HOURS).hours.do(run_data_cycle)
    schedule.every(X_INTERVAL_MINUTES).minutes.do(run_x_cycle)
    schedule.every(1).minutes.do(handle_commands)
    while True:
        schedule.run_pending()
        time.sleep(10)

if __name__ == "__main__":
    main()
