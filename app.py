import os, re, requests
from flask import Flask, request

app = Flask(__name__)

# ---------------- ENV ----------------
SLACK_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SHOPIFY_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
SHOP = os.getenv("SHOPIFY_SHOP")
CHANNEL_ID = "C0A02M2VCTB"  # #order

# STRICT MATCH: ONLY "ST.order #1234"
ORDER_REGEX = re.compile(r"\bST\.order\s+#(\d+)\b")

# In-memory store (OK for now)
order_threads = {}

# ✅ DUPLICATE PREVENTION STORE
processed_orders = set()

print("🚀 App started")
print("🏪 Shopify shop:", SHOP)
print("📢 Slack channel:", CHANNEL_ID)

# --------------------------------------------------
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
        match = ORDER_REGEX.search(text)
        if match and match.group(1) == order_number:
            print(f"✅ Found Slack message: {text}")
            return msg["ts"]

    print(f"❌ No Slack message found for order #{order_number}")
    return None


# --------------------------------------------------
def add_stock_reaction(thread_ts):
    print("📦 Adding stock available reaction")

    resp = requests.post(
        "https://slack.com/api/reactions.add",
        headers={
            "Authorization": f"Bearer {SLACK_TOKEN}",
            "Content-Type": "application/json"
        },
        json={
            "channel": CHANNEL_ID,
            "timestamp": thread_ts,
            "name": "package"
        }
    )

    if resp.ok and resp.json().get("ok"):
        print("✅ 📦 Reaction added")
    else:
        print("❌ Reaction add failed:", resp.text)


# --------------------------------------------------
@app.route("/webhook/order-updated", methods=["POST"])
def order_updated():
    print("\n📩 Shopify webhook received")

    data = request.json
    order_number = str(data.get("name", "")).replace("#", "")
    order_id = data.get("id")

    print(f"🆔 Order number: {order_number}")
    print(f"🆔 Order ID: {order_id}")

    url = f"https://{SHOP}.myshopify.com/admin/api/2024-01/orders/{order_id}/metafields.json"
    print("🌐 Fetching metafields:", url)

    r = requests.get(url, headers={"X-Shopify-Access-Token": SHOPIFY_TOKEN})

    if not r.ok:
        print("❌ Failed to fetch metafields:", r.text)
        return "Metafield fetch failed", 200

    metafields = r.json().get("metafields", [])
    print(f"🧾 Metafields count: {len(metafields)}")

    stock = next(
        (
            m["value"]
            for m in metafields
            if m["namespace"] == "custom" and m["key"] == "stock_status"
        ),
        None
    )

    print(f"📌 stock_status raw value: {stock}")

    normalized_stock = stock.strip().lower().replace(" ", "_") if stock else None
    print(f"🔄 Normalized value: {normalized_stock}")

    if normalized_stock != "stock_available":
        print("⏭️ Stock not available yet — ignoring")
        return "Ignored", 200

    print("✅ Stock is AVAILABLE")

    # --------------------------------------------------
    # ✅ DUPLICATE PREVENTION (FIXED)
    # --------------------------------------------------
    dedup_key = f"{order_number}:{normalized_stock}"

    if dedup_key in processed_orders:
        print("⛔ Duplicate webhook ignored for", dedup_key)
        return "Duplicate ignored", 200

    print("🆕 First time processing", dedup_key)

    # Find Slack thread
    thread_ts = order_threads.get(order_number) or find_thread_ts(order_number)

    if not thread_ts:
        print("❌ Slack thread not found")
        return "Thread not found", 200

    order_threads[order_number] = thread_ts

    add_stock_reaction(thread_ts)

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
            "text": "📦 Stock available"
        }
    )

    if slack_resp.ok and slack_resp.json().get("ok"):
        print("✅ Slack thread reply sent")
        processed_orders.add(dedup_key)
        print("🧠 Stored in processed list:", processed_orders)
    else:
        print("❌ Slack message failed:", slack_resp.text)

    return "OK", 200
