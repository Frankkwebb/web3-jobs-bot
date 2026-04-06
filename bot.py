"""
Web3 Jobs & Opportunities Bot v2 — @justtakenbot
- Improved UI with cleaner formatting
- Shortened links via TinyURL
- Detailed paragraph summary after each scan
Chains: ETH, SOL, BNB, SUI
Schedule: Data sources every 12hrs | X feeds every 1hr
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
CHAT_ID             = "1836559698"
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
    "job":        ("💼", "WEB3 JOB OPPORTUNITY"),
    "airdrop":    ("🪂", "AIRDROP / EARLY ACCESS"),
    "memecoin":   ("🐸", "MEMECOIN ALERT"),
    "protocol":   ("⚙️", "NEW PROTOCOL"),
    "newlisting": ("🆕", "NEW LISTING"),
    "x_alert":    ("🐦", "X COMMUNITY ALERT"),
    "defi":       ("🦙", "NEW DEFI PROTOCOL"),
}

# ─── SEEN CACHE ───────────────────────────────────────────
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

seen = load_seen()
cycle_alerts = []

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler("jobs_bot.log"), logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# ─── LINK SHORTENER ───────────────────────────────────────
def shorten(url):
    try:
        r = requests.get(
            f"https://tinyurl.com/api-create.php?url={url}",
            timeout=5
        )
        if r.status_code == 200 and r.text.startswith("http"):
            return r.text.strip()
    except:
        pass
    return url

# ─── HELPERS ──────────────────────────────────────────────
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
    if matches(text, JOB_KEYWORDS):     return "job"
    if matches(text, AIRDROP_KEYWORDS): return "airdrop"
    if matches(text, MEMECOIN_KEYWORDS): return "memecoin"
    return "x_alert"

# ─── SEND ─────────────────────────────────────────────────
def send(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }, timeout=10)
        r.raise_for_status()
    except Exception as e:
        log.error(f"Send error: {e}")

# ─── IMPROVED ALERT UI ────────────────────────────────────
def alert(category, title, url, source, snippet="", extra=""):
    emoji, label = CATEGORY_META.get(category, ("📢", "ALERT"))
    short_url    = shorten(url)
    snip         = f"\n📝 _{snippet[:160]}..._" if snippet else ""
    ext          = f"\n{extra}" if extra else ""
    now          = datetime.now().strftime("%H:%M • %d %b %Y")

    msg = (
        f"{emoji} *{label}*\n"
        f"{'━' * 18}\n"
        f"📌 *{title[:110]}*"
        f"{snip}{ext}\n\n"
        f"🔗 {short_url}\n"
        f"📡 `{source}`  •  ⏰ `{now}`\n"
        f"{'─' * 18}"
    )
    send(msg)
    cycle_alerts.append({
        "category": category,
        "label": label,
        "title": title,
        "source": source,
        "url": short_url,
        "snippet": snippet[:100]
    })
    log.info(f"Alerted [{category}] {title[:60]}")

# ─── DETAILED SUMMARY ─────────────────────────────────────
def send_cycle_summary(cycle_name="Scan"):
    now = datetime.now().strftime("%H:%M • %d %b %Y")

    if not cycle_alerts:
        send(
            f"📋 *{cycle_name} Complete — {now}*\n"
            f"{'━' * 18}\n"
            f"No new alerts found this cycle. The bot is actively watching all sources and will notify you the moment something relevant drops. Stay ready! 👀\n"
            f"{'─' * 18}"
        )
        cycle_alerts.clear()
        return

    total  = len(cycle_alerts)
    counts = {}
    for a in cycle_alerts:
        counts[a["label"]] = counts.get(a["label"], 0) + 1

    # Build breakdown line
    breakdown = " | ".join([f"{v}x {k}" for k, v in counts.items()])

    # Build detailed highlights
    highlights = ""
    for i, a in enumerate(cycle_alerts[:5], 1):
        highlights += (
            f"\n*{i}.* {a['title'][:65]}\n"
            f"   _{a['source']}_ — {a['url']}\n"
        )
    more = f"\n_...and {total - 5} more alerts above._" if total > 5 else ""

    # Build summary paragraph
    categories_found = list(counts.keys())
    if len(categories_found) == 1:
        cat_text = categories_found[0].lower()
    else:
        cat_text = ", ".join(categories_found[:-1]).lower() + f" and {categories_found[-1].lower()}"

    paragraph = (
        f"This scan picked up *{total} fresh alert(s)* across {cat_text}. "
    )
    if "WEB3 JOB OPPORTUNITY" in counts:
        paragraph += f"There are *{counts.get('WEB3 JOB OPPORTUNITY', 0)} job opening(s)* — move fast as community roles fill up quickly. "
    if "AIRDROP / EARLY ACCESS" in counts:
        paragraph += f"*{counts.get('AIRDROP / EARLY ACCESS', 0)} airdrop/early access opportunity(s)* were found — these are best acted on within hours of posting. "
    if "MEMECOIN ALERT" in counts:
        paragraph += f"*{counts.get('MEMECOIN ALERT', 0)} memecoin(s)* flagged — do your own research before engaging. "
    if "NEW DEFI PROTOCOL" in counts:
        paragraph += f"*{counts.get('NEW DEFI PROTOCOL', 0)} new DeFi protocol(s)* listed on DeFiLlama — check for early contributor roles. "

    summary = (
        f"📋 *{cycle_name} Summary — {now}*\n"
        f"{'━' * 18}\n"
        f"🗂 *{breakdown}*\n\n"
        f"{paragraph}\n\n"
        f"*Top Picks:*{highlights}{more}\n"
        f"{'─' * 18}\n"
        f"_Tip: Act fast on job & airdrop alerts — first movers win!_ 🚀"
    )
    send(summary)
    cycle_alerts.clear()

# ─── MONITOR 1: COINMARKETCAP ─────────────────────────────
def check_coinmarketcap():
    log.info("Checking CoinMarketCap...")
    try:
        r = requests.get("https://coinmarketcap.com/new/", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        rows = soup.select("table tbody tr")
        for row in rows[:20]:
            name_el = row.find("a", href=True)
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            href = name_el.get("href", "")
            link = f"https://coinmarketcap.com{href}" if href.startswith("/") else href
            text = row.get_text(separator=" ", strip=True)
            if not is_on_chain(text) and not is_on_chain(name):
                continue
            if not is_new(f"cmc_{name}"):
                continue
            alert(
                "newlisting",
                f"New Listing: {name}",
                link,
                "CoinMarketCap",
                f"Newly listed on CMC — early community opportunity",
                f"⛓ Chain detected in: _{text[:60]}_"
            )
    except Exception as ex:
        log.warning(f"CoinMarketCap error: {ex}")

# ─── MONITOR 2: CRYPTORANK ────────────────────────────────
def check_cryptorank():
    log.info("Checking CryptoRank...")
    try:
        r = requests.get("https://cryptorank.io/upcoming-ico", headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        seen_slugs = set()
        for card in soup.select("a[href]")[:30]:
            href = card.get("href", "")
            if "/currency/" not in href and "/ico/" not in href:
                continue
            text = card.get_text(separator=" ", strip=True)
            if len(text) < 3:
                continue
            slug = href.split("/")[-1]
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            full_url = f"https://cryptorank.io{href}" if href.startswith("/") else href
            if not is_new(f"cr_{slug}"):
                continue
            alert(
                "airdrop",
                f"Upcoming Project: {text[:80]}",
                full_url,
                "CryptoRank",
                "Upcoming ICO/IDO — check for ambassador & airdrop roles"
            )
    except Exception as ex:
        log.warning(f"CryptoRank error: {ex}")

# ─── MONITOR 3: DEFILLAMA ─────────────────────────────────
def check_defillama():
    log.info("Checking DeFiLlama...")
    try:
        r = requests.get(
            "https://api.llama.fi/protocols",
            headers={**HEADERS, "Accept": "application/json"},
            timeout=15
        )
        protocols = r.json()
        recent = sorted(
            [p for p in protocols if p.get("dateAdded")],
            key=lambda x: x.get("dateAdded", 0),
            reverse=True
        )[:15]
        for p in recent:
            name  = p.get("name", "")
            chain = p.get("chain", "").lower()
            slug  = p.get("slug", "")
            tvl   = p.get("tvl", 0)
            link  = f"https://defillama.com/protocol/{slug}"
            if not any(c in chain for c in ["ethereum", "solana", "bsc", "sui"]):
                continue
            if not is_new(f"llama_{slug}"):
                continue
            tvl_str     = f"${tvl:,.0f}" if tvl else "N/A"
            chain_label = chain.upper()
            alert(
                "defi",
                f"New Protocol: {name} ({chain_label})",
                link,
                "DeFiLlama",
                f"New protocol on {chain_label} — look for community/mod roles",
                f"💰 TVL: `{tvl_str}`"
            )
    except Exception as ex:
        log.warning(f"DeFiLlama error: {ex}")

# ─── MONITOR 4: X FEEDS ───────────────────────────────────
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
                cat = categorize_x(full)
                alert(cat, title[:120], link, name, summary[:200])
        except Exception as ex:
            log.warning(f"X feed error ({name}): {ex}")

# ─── COMMAND HANDLER ──────────────────────────────────────
last_update_id = None

def get_updates(offset=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 5}
    if offset:
        params["offset"] = offset
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
        if user_id != CHAT_ID:
            continue

        if text == "/jobs":
            send("💼 *Scanning X for Web3 job opportunities...*")
            check_x_feeds()
            send_cycle_summary("Jobs Scan")

        elif text == "/newprotocols":
            send("⚙️ *Fetching new protocols from DeFiLlama...*")
            check_defillama()
            send_cycle_summary("Protocols Scan")

        elif text == "/memecoins":
            send("🐸 *Scanning for new memecoins & launches...*")
            check_x_feeds()
            send_cycle_summary("Memecoin Scan")

        elif text == "/listings":
            send("🆕 *Checking CoinMarketCap & CryptoRank...*")
            check_coinmarketcap()
            check_cryptorank()
            send_cycle_summary("Listings Scan")

        elif text == "/status":
            send(
                "🟢 *Web3 Jobs Bot: ONLINE*\n"
                f"{'━' * 18}\n"
                f"⏰ `{datetime.now().strftime('%H:%M • %d %b %Y')}`\n"
                f"📦 Cache: `{len(seen)} entries`\n"
                f"⏱ Data scan: every `12 hrs`\n"
                f"🐦 X scan: every `60 mins`\n"
                f"⛓ Chains: `ETH | SOL | BNB | SUI`\n"
                f"{'─' * 18}"
            )

        elif text == "/help":
            send(
                "🤖 *Web3 Jobs Bot — Commands*\n"
                f"{'━' * 18}\n"
                "/jobs — Scan X for CM/mod/ambassador roles\n"
                "/newprotocols — New protocols on DeFiLlama\n"
                "/memecoins — New memecoins & fair launches\n"
                "/listings — New listings on CMC & CryptoRank\n"
                "/status — Bot health & schedule\n"
                "/help — This menu\n"
                f"{'─' * 18}"
            )

# ─── SET BOT COMMANDS ─────────────────────────────────────
def set_bot_commands():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setMyCommands"
    commands = [
        {"command": "jobs",         "description": "Scan for CM/mod/ambassador roles"},
        {"command": "newprotocols", "description": "New protocols on DeFiLlama"},
        {"command": "memecoins",    "description": "New memecoins & fair launches"},
        {"command": "listings",     "description": "New listings on CMC & CryptoRank"},
        {"command": "status",       "description": "Bot health & schedule"},
        {"command": "help",         "description": "Show all commands"},
    ]
    try:
        requests.post(url, json={"commands": commands}, timeout=10)
        log.info("Bot commands set.")
    except Exception as e:
        log.warning(f"Could not set commands: {e}")

# ─── MAIN CYCLES ──────────────────────────────────────────
def run_data_cycle():
    log.info("=" * 40)
    log.info("Running 12hr data cycle...")
    check_coinmarketcap()
    check_cryptorank()
    check_defillama()
    send_cycle_summary("12hr Data Scan")

def run_x_cycle():
    log.info("Running 1hr X cycle...")
    check_x_feeds()
    send_cycle_summary("X Feed Scan")

def main():
    log.info("Web3 Jobs Bot v2 starting...")
    set_bot_commands()
    send(
        "🤖 *Web3 Jobs & Opportunities Bot v2*\n"
        f"{'━' * 18}\n"
        "Now monitoring:\n"
        "💼 CM/Mod/Ambassador roles from X _(every 1hr)_\n"
        "🪂 Airdrop & early access alerts\n"
        "🆕 New listings — CoinMarketCap\n"
        "📊 Upcoming projects — CryptoRank\n"
        "🦙 New protocols — DeFiLlama\n"
        "⛓ Chains: `ETH | SOL | BNB | SUI`\n\n"
        "Commands: /jobs /newprotocols /memecoins /listings /status\n"
        f"{'─' * 18}\n"
        "_First movers get the best roles. Let's go!_ 🚀"
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
