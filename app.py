import os
import re
from collections import Counter

import emoji
from flask import Flask, request
from openai import OpenAI
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler

BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

TARGET_CHANNEL = "cat-spam-test-2"
CAT_CHANNEL = "cat-spam-random-kuiper"

app = App(token=BOT_TOKEN, signing_secret=SIGNING_SECRET)
flask_app = Flask(__name__)
handler = SlackRequestHandler(app)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

emoji_pattern = r":[a-zA-Z0-9_+-]+:"


def extract_emojis(text):
    slack_emojis = re.findall(emoji_pattern, text)
    unicode_emojis = [c for c in text if c in emoji.EMOJI_DATA]
    return slack_emojis + unicode_emojis


def emoji_spam(text):
    emojis = extract_emojis(text)
    counts = Counter(emojis)
    return any(count > 3 for count in counts.values())


def is_cat_image(image_url):
    """
    Returns True only if the image clearly contains a real cat.
    Returns False for non-cat images, drawings, unclear images, or API errors.
    """
    try:
        response = openai_client.responses.create(
            model="gpt-4.1-mini",
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Look at this image and answer with ONLY one word: "
                                "YES if this image clearly contains a real cat. "
                                "Answer NO for anything else, including dogs, people, "
                                "objects, memes, cartoons, drawings, text-only images, "
                                "or if you are unsure."
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": image_url,
                        },
                    ],
                }
            ],
        )

        answer = response.output_text.strip().upper()
        return answer == "YES"

    except Exception as e:
        print(f"OpenAI image check failed: {e}")
        return False


@app.event("message")
def handle_message(body, client):
    event = body["event"]

    if "bot_id" in event:
        return

    text = event.get("text", "")
    ts = event["ts"]
    channel = event["channel"]

    # Only watch the target channel
    if channel != TARGET_CHANNEL:
        return

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
            mimetype = file.get("mimetype", "")
            if not mimetype.startswith("image"):
                continue

            image_url = file.get("url_private")
            if not image_url:
                continue

            if is_cat_image(image_url):
                client.chat_postMessage(
                    channel=channel,
                    thread_ts=ts,
                    text="Nice cat. This belongs in #cat-spam-random-kuiper 🐱"
                )

                client.chat_postMessage(
                    channel=CAT_CHANNEL,
                    text=image_url
                )
            else:
                print("Image was not a cat. Leaving it alone.")


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)


@flask_app.route("/", methods=["GET"])
def health():
    return "cat-spam running"


if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
