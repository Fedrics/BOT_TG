from flask import Flask, request, jsonify, send_from_directory
import os, hmac, hashlib, json, requests, time
from urllib.parse import parse_qs

app = Flask(__name__, static_folder='static', template_folder='webapp')

API_TOKEN = os.environ.get("API_TOKEN", "")
CRYPTO_PAY_TOKEN = os.environ.get("CRYPTO_PAY_TOKEN", "")
CRYPTO_PAY_API = "https://pay.crypt.bot/api"

@app.route('/')
def index():
    return send_from_directory('webapp', 'index.html')

def verify_webapp_data(init_data: str, bot_token: str) -> bool:
    try:
        parsed = parse_qs(init_data, keep_blank_values=True)
        received_hash = parsed.get('hash', [''])[0]
        data_check_arr = []
        for k in sorted(parsed.keys()):
            if k == 'hash':
                continue
            v = parsed[k][0]
            data_check_arr.append(f"{k}={v}")
        data_check_string = "\n".join(data_check_arr)
        secret_key = hashlib.sha256(bot_token.encode()).digest()
        calc_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(calc_hash, received_hash)
    except Exception:
        return False

def get_user_id_from_init(init_data: str):
    try:
        parsed = parse_qs(init_data, keep_blank_values=True)
        user_json = parsed.get('user', [''])[0]
        if not user_json:
            return None
        user = json.loads(user_json)
        return int(user.get('id'))
    except Exception:
        return None

def create_crypto_pay_invoice(plan: str, price, user_id: int):
    try:
        payload = {
            "asset": "USDT",
            "amount": price,
            "description": f"VPN тариф: {plan}",
            "hidden_message": f"User ID: {user_id}"
        }
        r = requests.post(f"{CRYPTO_PAY_API}/createInvoice",
                          json=payload,
                          headers={"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN},
                          timeout=15)
        try:
            j = r.json()
        except Exception:
            return None
        return j.get('result', {}).get('pay_url')
    except Exception:
        return None

def send_telegram_message(chat_id: int, text: str) -> bool:
    try:
        url = f"https://api.telegram.org/bot{API_TOKEN}/sendMessage"
        r = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)
        try:
            return r.ok and r.json().get("ok", False)
        except Exception:
            return False
    except Exception:
        return False

# idempotency store: query_id -> (pay_url, ts)
PROCESSED = {}
IDEMPOTENCY_TTL = 300  # seconds

def cleanup_processed():
    now = time.time()
    to_del = [k for k,v in PROCESSED.items() if now - v[1] > IDEMPOTENCY_TTL]
    for k in to_del:
        PROCESSED.pop(k, None)

def get_query_id_from_init(init_data: str):
    try:
        parsed = parse_qs(init_data, keep_blank_values=True)
        return parsed.get('query_id', [''])[0] or None
    except Exception:
        return None

@app.route('/api/order', methods=['POST'])
def api_order():
    data = request.get_json(force=True, silent=True) or {}
    plan = data.get('plan')
    price = data.get('price')
    init_data = data.get('initData', '')

    if not plan or price is None or not init_data:
        return jsonify(ok=False, error="bad_request"), 400

    # clean expired entries
    cleanup_processed()

    query_id = get_query_id_from_init(init_data)
    if query_id and query_id in PROCESSED:
        # already processed — return existing pay_url (idempotent)
        existing_pay_url = PROCESSED[query_id][0]
        return jsonify(ok=True, pay_url=existing_pay_url, duplicate=True)

    verified = verify_webapp_data(init_data, API_TOKEN)
    user_id = get_user_id_from_init(init_data)
    if not user_id:
        return jsonify(ok=False, error="no_user"), 400

    pay_url = create_crypto_pay_invoice(plan, price, user_id)
    if not pay_url:
        return jsonify(ok=False, error="invoice_failed"), 500

    # store result for idempotency keyed by query_id (if present)
    if query_id:
        PROCESSED[query_id] = (pay_url, time.time())

    text = f"Вы выбрали тариф {plan} (${price}).\nОплатите по ссылке:\n{pay_url}"
    if not send_telegram_message(user_id, text):
        return jsonify(ok=False, error="send_failed"), 500

    return jsonify(ok=True, pay_url=pay_url, verified=bool(verified), duplicate=False)

# keep a small test endpoint for manual checks
@app.route('/testinvoice', methods=['POST'])
def test_invoice():
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get('user_id')
    plan = data.get('plan', 'TestPlan')
    price = data.get('price', 0.01)
    if not user_id:
        return jsonify(ok=False, error="no_user_id"), 400
    pay_url = create_crypto_pay_invoice(plan, price, user_id)
    if not pay_url:
        return jsonify(ok=False, error="invoice_failed"), 500
    text = f"Test invoice {plan} ${price}\n{pay_url}"
    sent = send_telegram_message(int(user_id), text)
    return jsonify(ok=True, pay_url=pay_url, sent=bool(sent))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)