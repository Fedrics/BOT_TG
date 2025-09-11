from flask import Flask, request, jsonify, send_from_directory
import os, hmac, hashlib, json, requests
from urllib.parse import parse_qs

app = Flask(__name__, static_folder='static', template_folder='webapp')

API_TOKEN = os.environ.get("API_TOKEN", "")
CRYPTO_PAY_TOKEN = os.environ.get("CRYPTO_PAY_TOKEN", "")
CRYPTO_PAY_API = "https://pay.crypt.bot/api"

@app.route('/')
def index():
    return send_from_directory('webapp', 'index.html')

def verify_webapp_data(init_data: str, bot_token: str) -> bool:
    # https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app
    parsed = parse_qs(init_data, keep_blank_values=True)
    received_hash = parsed.get('hash', [''])[0]
    data_check_arr = []
    for k, v in parsed.items():
        if k == 'hash':
            continue
        data_check_arr.append(f"{k}={v[0]}")
    data_check_arr.sort()
    data_check_string = "\n".join(data_check_arr)
    secret_key = hmac.new(b'WebAppData', bot_token.encode(), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calc_hash, received_hash)

def get_user_id_from_init(init_data: str):
    parsed = parse_qs(init_data, keep_blank_values=True)
    user_json = parsed.get('user', [''])[0]
    if not user_json:
        return None
    try:
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
        j = r.json()
        return j.get('result', {}).get('pay_url')
    except Exception as e:
        print("create_invoice error:", e)
        return None

def send_telegram_message(chat_id: int, text: str) -> bool:
    try:
        url = f"https://api.telegram.org/bot{API_TOKEN}/sendMessage"
        r = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)
        return r.ok and r.json().get("ok", False)
    except Exception as e:
        print("sendMessage error:", e)
        return False

@app.route('/api/order', methods=['POST'])
def api_order():
    data = request.get_json(force=True, silent=True) or {}
    plan = data.get('plan')
    price = data.get('price')
    init_data = data.get('initData', '')

    if not plan or price is None or not init_data:
        return jsonify(ok=False, error="bad_request"), 400

    if not verify_webapp_data(init_data, API_TOKEN):
        return jsonify(ok=False, error="invalid_initData"), 403

    user_id = get_user_id_from_init(init_data)
    if not user_id:
        return jsonify(ok=False, error="no_user"), 400

    pay_url = create_crypto_pay_invoice(plan, price, user_id)
    if not pay_url:
        return jsonify(ok=False, error="invoice_failed"), 500

    text = f"Вы выбрали тариф {plan} (${price}).\nОплатите по ссылке:\n{pay_url}"
    if not send_telegram_message(user_id, text):
        return jsonify(ok=False, error="send_failed"), 500

    return jsonify(ok=True, pay_url=pay_url)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)