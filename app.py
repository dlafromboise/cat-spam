import os
import requests
import datetime
from collections import defaultdict

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]

headers = {
    "Authorization": f"Bearer {SLACK_BOT_TOKEN}"
}

CAT_KEYWORDS = [
    "cat", "kitty", "kitten", ":cat:", ":cat2:", ":catjam:"
]

def get_channel_members():
    url = "https://slack.com/api/conversations.members"
    params = {
        "channel": CHANNEL_ID,
        "limit": 1000
    }

    res = requests.get(url, headers=headers, params=params).json()
    return len(res.get("members", []))


def get_messages():
    url = "https://slack.com/api/conversations.history"

    one_week_ago = datetime.datetime.now() - datetime.timedelta(days=7)
    oldest = one_week_ago.timestamp()

    params = {
        "channel": CHANNEL_ID,
        "limit": 1000,
        "oldest": oldest
    }

    res = requests.get(url, headers=headers, params=params).json()
    return res.get("messages", [])


def is_cat_message(msg):

    text = msg.get("text", "").lower()

    for keyword in CAT_KEYWORDS:
        if keyword in text:
            return True

    if "files" in msg:
        for f in msg["files"]:
            name = f.get("name", "").lower()
            if "cat" in name:
                return True

    return False


def collect_cat_stats(messages):

    counts = defaultdict(int)

    for msg in messages:

        if "user" not in msg:
            continue

        if is_cat_message(msg):
            counts[msg["user"]] += 1

    return counts


def get_username(user_id):

    url = "https://slack.com/api/users.info"
    params = {"user": user_id}

    res = requests.get(url, headers=headers, params=params).json()

    if res.get("ok"):
        return res["user"]["name"]

    return user_id


def build_report(cat_counts, member_count):

    top_users = sorted(cat_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    total_interruptions = 0

    lines = []
    lines.append("*Cat Spam Weekly Impact Report — #random-kuiper*\n")

    for user_id, count in top_users:

        interruptions = member_count * count
        total_interruptions += interruptions

        username = get_username(user_id)

        lines.append(
            f"• @{username}\n"
            f"     o Cat Spam This Week: {count}\n"
            f"     o Interruptions: {member_count} people x {count} posts = {interruptions:,} feed disruptions\n"
        )

    lines.append(f"\n• Channel Interruptions this week: {total_interruptions:,}")

    return "\n".join(lines)


def post_message(text):

    url = "https://slack.com/api/chat.postMessage"

    payload = {
        "channel": CHANNEL_ID,
        "text": text
    }

    requests.post(url, headers=headers, json=payload)


def run():

    member_count = get_channel_members()

    messages = get_messages()

    cat_counts = collect_cat_stats(messages)

    report = build_report(cat_counts, member_count)

    post_message(report)


if __name__ == "__main__":
    run()
