import os
import requests
import datetime
from collections import defaultdict
from zoneinfo import ZoneInfo

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]

headers = {
    "Authorization": f"Bearer {SLACK_BOT_TOKEN}"
}

CAT_KEYWORDS = [
    "cat",
    "kitty",
    "kitten",
    ":cat:",
    ":cat2:",
    ":catjam:",
    ":meow:",
    "giphy",
]


def get_channel_members() -> int:
    url = "https://slack.com/api/conversations.members"
    members = []
    cursor = None

    while True:
        params = {
            "channel": CHANNEL_ID,
            "limit": 1000,
        }
        if cursor:
            params["cursor"] = cursor

        res = requests.get(url, headers=headers, params=params, timeout=30).json()

        if not res.get("ok"):
            raise RuntimeError(f"conversations.members failed: {res}")

        members.extend(res.get("members", []))
        cursor = res.get("response_metadata", {}).get("next_cursor")

        if not cursor:
            break

    return len(members)


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
            "limit": 1000,
            "oldest": oldest,
        }
        if cursor:
            params["cursor"] = cursor

        res = requests.get(url, headers=headers, params=params, timeout=30).json()

        if not res.get("ok"):
            raise RuntimeError(f"conversations.history failed: {res}")

        messages.extend(res.get("messages", []))
        cursor = res.get("response_metadata", {}).get("next_cursor")

        if not cursor:
            break

    return messages


def is_cat_message(msg: dict) -> bool:
    text = msg.get("text", "").lower()

    for keyword in CAT_KEYWORDS:
        if keyword in text:
            return True

    for block in msg.get("blocks", []):
        block_text = str(block).lower()
        for keyword in CAT_KEYWORDS:
            if keyword in block_text:
                return True

    if "files" in msg:
        for f in msg["files"]:
            file_name = f.get("name", "").lower()
            title = f.get("title", "").lower()
            mimetype = f.get("mimetype", "").lower()
            filetype = f.get("filetype", "").lower()

            searchable = f"{file_name} {title} {mimetype} {filetype}"

            if "cat" in searchable or "kitty" in searchable or "kitten" in searchable:
                return True

            if mimetype.startswith("image/") and (
                "cat" in text or "kitty" in text or "kitten" in text
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

    res = requests.get(url, headers=headers, params=params, timeout=30).json()

    if res.get("ok"):
        return res["user"].get("name", user_id)

    return user_id


def build_report(cat_counts: dict, member_count: int) -> str:
    top_users = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    total_interruptions = 0

    lines = []
    lines.append("*Cat Spam Weekly Impact Report — #random-kuiper*")
    lines.append(f"Channel members at report time: {member_count:,}")
    lines.append("")

    if not top_users:
        lines.append("• No cat spam detected in the last 7 days.")
        lines.append("")
        lines.append("• Channel Interruptions this week: 0")
        return "\n".join(lines)

    for user_id, count in top_users:
        interruptions = member_count * count
        total_interruptions += interruptions
        username = get_username(user_id)

        lines.append(f"• @{username}")
        lines.append(f"     o Cat Spam This Week: {count}")
        lines.append(
            f"     o Interruptions: {member_count:,} people x {count} posts = {interruptions:,} feed disruptions"
        )
        lines.append("")

    lines.append(f"• Channel Interruptions this week: {total_interruptions:,}")

    return "\n".join(lines)


def post_message(text: str) -> None:
    url = "https://slack.com/api/chat.postMessage"

    payload = {
        "channel": CHANNEL_ID,
        "text": text,
    }

    res = requests.post(url, headers=headers, json=payload, timeout=30).json()

    if not res.get("ok"):
        raise RuntimeError(f"chat.postMessage failed: {res}")


def should_post_now() -> bool:
    now_pt = datetime.datetime.now(ZoneInfo("America/Los_Angeles"))
    return now_pt.hour == 17


def run() -> None:
    if not should_post_now():
        print("Not 5 PM America/Los_Angeles yet. Exiting.")
        return

    member_count = get_channel_members()
    messages = get_messages()
    cat_counts = collect_cat_stats(messages)
    report = build_report(cat_counts, member_count)
    post_message(report)
    print("Daily report posted successfully.")


if __name__ == "__main__":
    run()
