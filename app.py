import os
import requests
import datetime
from collections import defaultdict
from zoneinfo import ZoneInfo

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]

HEADERS = {
    "Authorization": f"Bearer {SLACK_BOT_TOKEN}"
}

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

GIPHY_HINTS = [
    "giphy",
    "giphy.com",
    "media.giphy.com",
    "gph.is",
]


def get_channel_members() -> int:
    url = "https://slack.com/api/conversations.info"
    params = {
        "channel": CHANNEL_ID,
        "include_num_members": True,
    }

    res = requests.get(url, headers=HEADERS, params=params, timeout=30).json()

    if not res.get("ok"):
        raise RuntimeError(f"conversations.info failed: {res}")

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

        res = requests.get(url, headers=HEADERS, params=params, timeout=30).json()

        if not res.get("ok"):
            raise RuntimeError(f"conversations.history failed: {res}")

        messages.extend(res.get("messages", []))
        cursor = res.get("response_metadata", {}).get("next_cursor")

        if not cursor:
            break

    return messages


def contains_any_keyword(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


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


def is_probable_giphy_message(searchable_text: str) -> bool:
    return any(hint in searchable_text for hint in GIPHY_HINTS)


def is_cat_message(msg: dict) -> bool:
    searchable_text = collect_searchable_text(msg)

    if contains_any_keyword(searchable_text, CAT_KEYWORDS):
        return True

    if is_probable_giphy_message(searchable_text):
        if any(word in searchable_text for word in ["cat", "cats", "kitty", "kitten", "feline"]):
            return True

    for file_obj in msg.get("files", []):
        mimetype = file_obj.get("mimetype", "").lower()
        if mimetype.startswith("image/") and any(
            word in searchable_text for word in ["cat", "cats", "kitty", "kitten", "feline"]
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

    res = requests.get(url, headers=HEADERS, params=params, timeout=30).json()

    if res.get("ok"):
        return res["user"].get("name", user_id)

    return user_id


def build_report(cat_counts: dict, member_count: int) -> str:
    top_users = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    total_interruptions = 0

    lines = []
    lines.append("*Rolling 7-Day Cat Spam Impact Report — #random-kuiper*")
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

    member_count = get_channel_members()
    messages = get_messages()
    cat_counts = collect_cat_stats(messages)
    report = build_report(cat_counts, member_count)
    post_message(report)
    print("Daily report posted successfully.")


if __name__ == "__main__":
    run_daily_report()
