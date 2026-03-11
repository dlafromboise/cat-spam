import os
import re
from collections import Counter

import emoji
from flask import Flask, request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler

BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]

TARGET_CHANNEL = "random-kuiper"

app = App(token=BOT_TOKEN, signing_secret=SIGNING_SECRET)
flask_app = Flask(__name__)
handler = SlackRequestHandler(app)

emoji_pattern = r":[a-zA-Z0-9_+-]+:"


def extract_emojis(text):
    slack_emojis = re.findall(emoji_pattern, text)
    unicode_emojis = [c for c in text if c in emoji.EMOJI_DATA]
    return slack_emojis + unicode_emojis


def emoji_spam(text):
    emojis = extract_emojis(text)
    counts = Counter(emojis)
    return any(count > 3 for count in counts.values())


@app.event("message")
def handle_message(body, client):

    event = body["event"]

    if "bot_id" in event:
        return

    text = event.get("text", "")
    ts = event["ts"]
    channel = event["channel"]

    # Emoji spam check
    if emoji_spam(text):

        client.chat_postMessage(
            channel=channel,
            thread_ts=ts,
            text="Too many emojis! 🛑"
        )

    # Check for uploaded images
    if "files" in event:

        for file in event["files"]:

            if file["mimetype"].startswith("image"):

                image_url = file["url_private"]

                client.chat_postMessage(
                    channel=channel,
                    thread_ts=ts,
                    text="Nice cat. This belongs in #leo-kitty-cats-meow 🐱"
                )

                client.chat_postMessage(
                    channel="#leo-kitty-cats-meow",
                    text=image_url
                )


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)


@flask_app.route("/", methods=["GET"])
def health():
    return "cat-spam running"


if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
