"""
Web3 Jobs & Opportunities Bot — @justtakenbot
Monitors: CoinMarketCap, CryptoRank, DeFiLlama, X feeds
Chains: ETH, SOL, BNB, SUI
Roles: Community Manager, Mod, Ambassador
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
BOT_TOKEN   = "8598884979:AAEMCDzsY7U8vBP84SKtwf6n5llZtAgoAZo"
CHAT_ID     = "1836559698"
SEEN_FILE   = "seen_jobs_cache.json"

DATA_INTERVAL_HOURS = 12   # CoinMarketCap, CryptoRank, DeFiLlama
X_INTERVAL_MINUTES  = 60   # X feeds every 1 hour

CHAINS = ["eth", "ethereum", "sol", "solana", "bnb", "bsc", "sui"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ─── X RSS FEEDS ──────────────────────────────────────────
X_FEEDS = [
    ("X: CM/Mod/Ambassador",  "https://rss.app/feeds/mjeFNMSf9uLyamJK.xml"),
    ("X: Early Protocols",    "https://rss.app/feeds/adzhPZBeWutbdnmA.xml"),
    ("X: Community/Memecoin", "https://rss.app/feeds/7H90BEOdSgoyw8be.xml"),
]

# ─── KEYWORDS ─────────────────────────────────────────────
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

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[logging.FileHandler("jobs_bot.log"), logging.StreamHandler()]
)
log = logging.getLogger(__name__)

# ─── CYCLE ALERT TRACKER ──────────────────────────────────
cycle_alerts = []

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
    t = text.lower()
    return any(c in t for c in CHAINS)

def matches(text, keywords):
    t = text.lower()
    return any(k in t for k in keywords)

def categorize_x(text):
    if matches(text, JOB_KEYWORDS):      return "job"
    if matches(text, AIRDROP_KEYWORDS):  return "airdrop"
    if matches(text, MEMECOIN_KEYWORDS): return "memecoin"
    return "x_alert"

CATEGORY_META = {
    "job":         ("💼", "WEB3 JOB OPPORTUNITY"),
    "airdrop":     ("🪂", "AIRDROP / EARLY ACCESS"),
    "memecoin":    ("🐸", "MEMECOIN ALERT"),
    "protocol":    ("⚙️", "NEW PROTOCOL"),
    "newlisting":  ("🆕", "NEW LISTING"),
    "x_alert":     ("🐦", "X COMMUNITY ALERT"),
    "defi":        ("🦙", "NEW DEFI PROTOCOL"),
}

def send(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False
        }, timeout=10)
        r.raise_for_status()
    except Exception as e:
        log.error(f"Send error: {e}")

def alert(category, title, url, source, snippet="", followers=None):
    emoji, label = CATEGORY_META.get(category, ("📢", "ALERT"))
    snip = f"\n_{snippet[:180]}..._" if snippet else ""
    fol  = f"\n👥 Followers: `{followers}`" if followers else ""
    msg = (
        f"{emoji} *{label}*\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"*{title[:120]}*"
        f"{snip}{fol}\n\n"
        f"🔗 [View]({url})\n"
        f"📡 `{source}`\n"
        f"⏰ `{datetime.now().strftime('%H:%M • %d %b %Y')}`"
    )
    send(msg)
    cycle_alerts.append({"category": category, "label": label, "title": title, "source": source})
    log.info(f"Alerted [{category}] {title[:60]}")

def send_cycle_summary(cycle_name="Scan"):
    if not cycle_alerts:
        send(f"📋 *{cycle_name} Summary:* No new alerts this cycle. Watching closely... 👀")
        cycle_alerts.clear()
        return

    total  = len(cycle_alerts)
    counts = {}
    for a in cycle_alerts:
        counts[a["label"]] = counts.get(a["label"], 0) + 1

    breakdown  = ", ".join([f"*{v}* {k}" for k, v in counts.items()])
    highlights = "\n".join([f"• {a['title'][:70]} _({a['source']})_" for a in cycle_alerts[:5]])
    more       = f"\n_...and {total - 5} more._" if total > 5 else ""

    summary = (
        f"📋 *{cycle_name} Summary — {datetime.now().strftime('%H:%M • %d %b %Y')}*\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"Found *{total} new alert(s)*: {breakdown}.\n\n"
        f"*Top picks:*\n{highlights}{more}\n\n"
        f"_Move fast on job/airdrop opportunities!_ 🚀"
    )
    send(summary)
    cycle_alerts.clear()

# ─── MONITOR 1: COINMARKETCAP NEW LISTINGS ────────────────
def check_coinmarketcap():
    log.info("Checking CoinMarketCap new listings...")
    try:
        r = requests.get(
            "https://coinmarketcap.com/new/",
            headers=HEADERS, timeout=15
        )
        soup = BeautifulSoup(r.text, "html.parser")
        rows = soup.select("table tbody tr")
        for row in rows[:20]:
            name_el = row.find("a", href=True)
            if not name_el:
                continue
            name = name_el.get_text(strip=True)
            href = name_el.get("href", "")
            link = f"https://coinmarketcap.com{href}" if href.startswith("/") else href
            text = row.get_text(separator=" ", strip=True).lower()
            if not is_on_chain(text) and not is_on_chain(name):
                continue
            if not is_new(f"cmc_{name}"):
                continue
            alert(
                "newlisting",
                f"New Listing: {name}",
                link,
                "CoinMarketCap",
                f"Newly listed token — potential early community opportunity on {text[:100]}"
            )
    except Exception as ex:
        log.warning(f"CoinMarketCap error: {ex}")

# ─── MONITOR 2: CRYPTORANK NEW PROJECTS ───────────────────
def check_cryptorank():
    log.info("Checking CryptoRank new projects...")
    try:
        r = requests.get(
            "https://cryptorank.io/upcoming-ico",
            headers=HEADERS, timeout=15
        )
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("a[href]")
        seen_slugs = set()
        for card in cards[:30]:
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
                "New project listed — check for ambassador/airdrop opportunities"
            )
    except Exception as ex:
        log.warning(f"CryptoRank error: {ex}")

# ─── MONITOR 3: DEFILLAMA NEW PROTOCOLS ───────────────────
def check_defillama():
    log.info("Checking DeFiLlama new protocols...")
    try:
        r = requests.get(
            "https://api.llama.fi/protocols",
            headers={**HEADERS, "Accept": "application/json"},
            timeout=15
        )
        protocols = r.json()
        # Sort by date added, get newest
        recent = sorted(
            [p for p in protocols if p.get("dateAdded")],
            key=lambda x: x.get("dateAdded", 0),
            reverse=True
        )[:15]

        for p in recent:
            name   = p.get("name", "")
            chain  = p.get("chain", "").lower()
            slug   = p.get("slug", "")
            tvl    = p.get("tvl", 0)
            link   = f"https://defillama.com/protocol/{slug}"

            # Only target our 4 chains
            if not any(c in chain for c in ["ethereum", "solana", "bsc", "sui"]):
                continue
            if not is_new(f"llama_{slug}"):
                continue

            chain_label = chain.upper()
            tvl_str = f"${tvl:,.0f}" if tvl else "N/A"
            alert(
                "defi",
                f"New Protocol: {name} ({chain_label})",
                link,
                "DeFiLlama",
                f"TVL: {tvl_str} — Early protocol, check for community/mod roles"
            )
    except Exception as ex:
        log.warning(f"DeFiLlama error: {ex}")

# ─── MONITOR 4: X RSS FEEDS (every 1 hour) ────────────────
def check_x_feeds():
    log.info("Checking X feeds for jobs & opportunities...")
    for name, url in X_FEEDS:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:20]:
                title   = e.get("title", "")
                link    = e.get("link", "")
                summary = BeautifulSoup(e.get("summary", ""), "html.parser").get_text()
                full    = f"{title} {summary}"

                if not is_new(link or title):
                    continue
                if not is_fresh(e, hours=2):
                    continue

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
            send("💼 *Scanning for Web3 job opportunities...*")
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
                "🟢 *Web3 Jobs Bot: ONLINE*\n\n"
                f"⏰ Time: `{datetime.now().strftime('%H:%M • %d %b %Y')}`\n"
                f"📦 Seen cache: `{len(seen)} entries`\n"
                f"⏱ Data sources: every `12 hrs`\n"
                f"🐦 X feeds: every `60 mins`\n"
                f"⛓ Chains: ETH, SOL, BNB, SUI"
            )

        elif text == "/help":
            send(
                "🤖 *Web3 Jobs Bot Commands:*\n\n"
                "/jobs — Scan X for CM/mod/ambassador roles\n"
                "/newprotocols — New protocols on DeFiLlama\n"
                "/memecoins — New memecoins & fair launches\n"
                "/listings — New listings on CMC & CryptoRank\n"
                "/status — Bot health & schedule\n"
                "/help — This menu"
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
    log.info("Running data cycle (12hr)...")
    check_coinmarketcap()
    check_cryptorank()
    check_defillama()
    send_cycle_summary("12hr Data Scan")
    log.info("Data cycle complete.")

def run_x_cycle():
    log.info("Running X cycle (1hr)...")
    check_x_feeds()
    send_cycle_summary("X Feed Scan")
    log.info("X cycle complete.")

def main():
    log.info("Web3 Jobs Bot starting...")
    set_bot_commands()
    send(
        "🤖 *Web3 Jobs & Opportunities Bot is online!*\n\n"
        "Monitoring:\n"
        "💼 CM/Mod/Ambassador roles from X (every 1hr)\n"
        "🪂 Airdrop & early access opportunities\n"
        "🆕 New listings on CoinMarketCap\n"
        "📊 Upcoming projects on CryptoRank\n"
        "🦙 New protocols on DeFiLlama\n"
        "⛓ Chains: ETH, SOL, BNB, SUI\n\n"
        "Commands: /jobs /newprotocols /memecoins /listings /status /help"
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
