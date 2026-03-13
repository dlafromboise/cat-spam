import os
import re
import requests
import datetime
from collections import defaultdict
from zoneinfo import ZoneInfo
from urllib.parse import urlparse

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]

HEADERS = {
    "Authorization": f"Bearer {SLACK_BOT_TOKEN}"
}

REPORT_HEADER = "*Rolling 7-Day Cat Spam Impact Report — #random-kuiper*"

CAT_KEYWORDS = [
    "cat",
    "cats",
    "kitty",
    "kitties",
    "kitten",
    "kittens",
    "feline",
    ":cat:",
    ":cat2:",
    ":catjam:",
    ":meow:",
]

GIPHY_DOMAINS = {
    "giphy.com",
    "www.giphy.com",
    "media.giphy.com",
    "gph.is",
}

URL_REGEX = re.compile(r"https?://[^\s>]+")
URL_METADATA_CACHE = {}


def slack_get(url: str, params: dict) -> dict:
    res = requests.get(url, headers=HEADERS, params=params, timeout=30).json()
    if not res.get("ok"):
        raise RuntimeError(f"Slack API failed for {url}: {res}")
    return res


def get_bot_user_id() -> str:
    url = "https://slack.com/api/auth.test"
    res = slack_get(url, {})
    return res["user_id"]


def get_channel_members() -> int:
    url = "https://slack.com/api/conversations.info"
    params = {
        "channel": CHANNEL_ID,
        "include_num_members": True,
    }
    res = slack_get(url, params)
    return res["channel"]["num_members"]


def get_messages() -> list:
    url = "https://slack.com/api/conversations.history"

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    one_week_ago = now_utc - datetime.timedelta(days=7)
    oldest = one_week_ago.timestamp()

    messages = []
    cursor = None

    while True:
        params = {
            "channel": CHANNEL_ID,
            "limit": 200,
            "oldest": oldest,
        }
        if cursor:
            params["cursor"] = cursor

        res = slack_get(url, params)
        messages.extend(res.get("messages", []))
        cursor = res.get("response_metadata", {}).get("next_cursor")

        if not cursor:
            break

    return messages


def already_posted_today(bot_user_id: str) -> bool:
    url = "https://slack.com/api/conversations.history"

    now_pt = datetime.datetime.now(ZoneInfo("America/Los_Angeles"))
    start_of_day_pt = now_pt.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_day_utc = start_of_day_pt.astimezone(datetime.timezone.utc)

    cursor = None

    while True:
        params = {
            "channel": CHANNEL_ID,
            "limit": 200,
            "oldest": start_of_day_utc.timestamp(),
        }
        if cursor:
            params["cursor"] = cursor

        res = slack_get(url, params)

        for msg in res.get("messages", []):
            if msg.get("user") == bot_user_id and REPORT_HEADER in msg.get("text", ""):
                return True

        cursor = res.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    return False


def contains_any_keyword(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def extract_urls_from_text(text: str) -> list[str]:
    return URL_REGEX.findall(text or "")


def collect_searchable_text(msg: dict) -> str:
    parts = []

    text = msg.get("text", "")
    if text:
        parts.append(text)

    for block in msg.get("blocks", []):
        parts.append(str(block))

    for attachment in msg.get("attachments", []):
        parts.append(str(attachment))

    for file_obj in msg.get("files", []):
        parts.append(file_obj.get("name", ""))
        parts.append(file_obj.get("title", ""))
        parts.append(file_obj.get("mimetype", ""))
        parts.append(file_obj.get("filetype", ""))
        parts.append(file_obj.get("pretty_type", ""))
        parts.append(file_obj.get("permalink", ""))
        parts.append(file_obj.get("url_private", ""))
        parts.append(file_obj.get("url_private_download", ""))

    return " ".join(parts).lower()


def collect_candidate_urls(msg: dict) -> list[str]:
    urls = []

    urls.extend(extract_urls_from_text(msg.get("text", "")))

    for attachment in msg.get("attachments", []):
        for key in ("from_url", "original_url", "title_link", "image_url", "thumb_url"):
            value = attachment.get(key)
            if value:
                urls.append(value)

    for file_obj in msg.get("files", []):
        for key in ("permalink", "url_private", "url_private_download"):
            value = file_obj.get(key)
            if value:
                urls.append(value)

    deduped = []
    seen = set()
    for url in urls:
        if url not in seen:
            seen.add(url)
            deduped.append(url)

    return deduped


def is_giphy_like_url(url: str) -> bool:
    try:
        hostname = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return hostname in GIPHY_DOMAINS or hostname.endswith(".giphy.com")


def extract_html_metadata(html: str) -> str:
    snippets = []

    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if title_match:
        snippets.append(title_match.group(1))

    meta_patterns = [
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+name=["\']twitter:title["\'][^>]+content=["\'](.*?)["\']',
        r'<meta[^>]+name=["\']twitter:description["\'][^>]+content=["\'](.*?)["\']',
    ]

    for pattern in meta_patterns:
        for match in re.findall(pattern, html, re.IGNORECASE | re.DOTALL):
            snippets.append(match)

    return " ".join(snippets).lower()


def fetch_url_metadata(url: str) -> str:
    if url in URL_METADATA_CACHE:
        return URL_METADATA_CACHE[url]

    metadata = ""
    try:
        response = requests.get(
            url,
            timeout=5,
            headers={"User-Agent": "cat-spam-bot/1.0"},
        )

        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" in content_type:
            metadata = extract_html_metadata(response.text[:200000])
        else:
            metadata = response.url.lower()
    except Exception:
        metadata = ""

    URL_METADATA_CACHE[url] = metadata
    return metadata


def is_cat_message(msg: dict) -> bool:
    searchable_text = collect_searchable_text(msg)

    if contains_any_keyword(searchable_text, CAT_KEYWORDS):
        return True

    candidate_urls = collect_candidate_urls(msg)
    inspected = 0

    for url in candidate_urls:
        if not is_giphy_like_url(url):
            continue

        inspected += 1
        if inspected > 3:
            break

        metadata = fetch_url_metadata(url)
        combined = f"{searchable_text} {metadata}"

        if any(word in combined for word in ["cat", "cats", "kitty", "kitties", "kitten", "kittens", "feline"]):
            return True

    for file_obj in msg.get("files", []):
        mimetype = file_obj.get("mimetype", "").lower()
        if mimetype.startswith("image/") and any(
            word in searchable_text for word in ["cat", "cats", "kitty", "kitties", "kitten", "kittens", "feline"]
        ):
            return True

    return False


def collect_cat_stats(messages: list) -> dict:
    counts = defaultdict(int)

    for msg in messages:
        user_id = msg.get("user")
        subtype = msg.get("subtype", "")

        if not user_id:
            continue

        if subtype in {"channel_join", "channel_leave", "message_deleted"}:
            continue

        if is_cat_message(msg):
            counts[user_id] += 1

    return counts


def get_username(user_id: str) -> str:
    url = "https://slack.com/api/users.info"
    params = {"user": user_id}
    res = slack_get(url, params)
    return res["user"].get("name", user_id)


def build_report(cat_counts: dict, member_count: int) -> str:
    top_users = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    total_interruptions = 0

    lines = []
    lines.append(REPORT_HEADER)
    lines.append("Window: last 7 days ending at report time")
    lines.append(f"Channel members at report time: {member_count:,}")
    lines.append("")

    if not top_users:
        lines.append("• No cat spam detected in the last 7 days.")
        lines.append("")
        lines.append("• Rolling 7-Day Channel Interruptions: 0")
        return "\n".join(lines)

    for user_id, count in top_users:
        interruptions = member_count * count
        total_interruptions += interruptions
        username = get_username(user_id)

        lines.append(f"• @{username}")
        lines.append(f"     o Cat Spam in Last 7 Days: {count}")
        lines.append(
            f"     o Interruptions: {member_count:,} people x {count} posts = {interruptions:,} feed disruptions"
        )
        lines.append("")

    lines.append(f"• Rolling 7-Day Channel Interruptions: {total_interruptions:,}")

    return "\n".join(lines)


def post_message(text: str) -> None:
    url = "https://slack.com/api/chat.postMessage"
    payload = {
        "channel": CHANNEL_ID,
        "text": text,
    }

    res = requests.post(url, headers=HEADERS, json=payload, timeout=30).json()
    if not res.get("ok"):
        raise RuntimeError(f"chat.postMessage failed: {res}")


def should_post_now() -> bool:
    now_pt = datetime.datetime.now(ZoneInfo("America/Los_Angeles"))
    return 16 <= now_pt.hour < 17


def run_daily_report() -> None:
    if not should_post_now():
        print("Not in 4:00 PM–5:00 PM America/Los_Angeles window. Exiting.")
        return

    bot_user_id = get_bot_user_id()
    if already_posted_today(bot_user_id):
        print("Report already posted today. Exiting.")
        return

    member_count = get_channel_members()
    messages = get_messages()
    cat_counts = collect_cat_stats(messages)
    report = build_report(cat_counts, member_count)
    post_message(report)
    print("Daily report posted successfully.")


if __name__ == "__main__":
    run_daily_report()
