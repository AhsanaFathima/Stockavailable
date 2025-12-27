import os, re, requests
from flask import Flask, request

app = Flask(__name__)

SLACK_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
SHOP = os.getenv("SHOPIFY_SHOP")
CHANNEL_ID = "C0A068PHZMY"  # #shopify-slack

ORDER_REGEX = re.compile(r"\bST\.order\s+#(\d+)\b")

# Simple memory store
order_threads = {}

print("🚀 App started")
print("🏪 Shopify shop:", SHOP)
print("📢 Slack channel:", CHANNEL_ID)

def find_thread_ts(order_number):
    print(f"🔍 Searching Slack thread for order #{order_number}")

    headers = {"Authorization": f"Bearer {SLACK_TOKEN}"}
    r = requests.get(
        "https://slack.com/api/conversations.history",
        headers=headers,
        params={"channel": CHANNEL_ID, "limit": 100}
    )

    if not r.ok:
        print("❌ Slack API error:", r.text)
        return None

    for msg in r.json().get("messages", []):
        text = msg.get("text", "")
        m = ORDER_REGEX.search(text)
        if m:
            print(f"🧵 Found Slack message: {text}")
        if m and m.group(1) == order_number:
            print(f"✅ Thread matched for order #{order_number}")
            return msg["ts"]

    print(f"❌ No Slack thread found for order #{order_number}")
    return None

@app.route("/webhook/order-updated", methods=["POST"])
def order_updated():
    print("\n📩 Shopify webhook received")

    data = request.json
    print("📦 Raw webhook payload received")

    order_number = str(data.get("name", "")).replace("#", "")
    order_id = data.get("id")

    print(f"🆔 Order number: {order_number}")
    print(f"🆔 Order ID: {order_id}")

    # Fetch metafields
    url = f"https://{SHOP}.myshopify.com/admin/api/2024-01/orders/{order_id}/metafields.json"
    print("🌐 Fetching order metafields:", url)

    r = requests.get(url, headers={
        "X-Shopify-Access-Token": SHOPIFY_TOKEN
    })

    if not r.ok:
        print("❌ Failed to fetch metafields:", r.text)
        return "Metafield fetch failed", 200

    metafields = r.json().get("metafields", [])
    print(f"🧾 Total metafields found: {len(metafields)}")

    stock = next(
        (m["value"] for m in metafields
         if m["namespace"] == "custom" and m["key"] == "stock_status"),
        None
    )

    print(f"📌 stock_status metafield value: {stock}")

    if not stock or stock.strip().lower().replace(" ", "_") != "stock_available":

        print("⏭️ Stock not available yet — ignoring")
        return "Ignored", 200

    print("✅ Stock is AVAILABLE — proceeding to Slack reply")

    thread_ts = order_threads.get(order_number)
    if thread_ts:
        print(f"📎 Thread timestamp found in memory: {thread_ts}")
    else:
        print("📎 Thread not in memory — searching Slack")
        thread_ts = find_thread_ts(order_number)

    if not thread_ts:
        print("❌ Cannot reply — Slack thread not found")
        return "Thread not found", 200

    order_threads[order_number] = thread_ts

    print(f"💬 Sending Slack thread reply for order #{order_number}")

    slack_resp = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={
            "Authorization": f"Bearer {SLACK_TOKEN}",
            "Content-Type": "application/json"
        },
        json={
            "channel": CHANNEL_ID,
            "thread_ts": thread_ts,
            "text": "Stock available"
        }
    )

    if slack_resp.ok:
        print("✅ Slack thread reply sent successfully")
    else:
        print("❌ Slack API error:", slack_resp.text)

    return "OK", 200
