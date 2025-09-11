from flask import Flask, request, jsonify, send_from_directory
import os, hmac, hashlib, json, requests, time
from urllib.parse import parse_qs
from collections import deque

app = Flask(__name__, static_folder='static', template_folder='webapp')

API_TOKEN = os.environ.get("API_TOKEN", "")
CRYPTO_PAY_TOKEN = os.environ.get("CRYPTO_PAY_TOKEN", "")
CRYPTO_PAY_API = "https://pay.crypt.bot/api"

# lightweight in-memory server logs (most recent first)
LOGS = deque(maxlen=300)
def srv_log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    line = f"{ts} | {msg}"
    try:
        print(line, flush=True)
    except:
        pass
    LOGS.appendleft(line)

@app.route('/')
def index():
    return send_from_directory('webapp', 'index.html')

@app.route('/api/logs', methods=['GET'])
def api_logs():
    # return last logs as JSON
    return jsonify(logs=list(LOGS))

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
        srv_log(f"verify_webapp_data: data_check_string={data_check_string}")
        srv_log(f"verify_webapp_data: received_hash={received_hash} calc_hash={calc_hash}")
        return hmac.compare_digest(calc_hash, received_hash)
    except Exception as e:
        srv_log(f"verify_webapp_data error: {e}")
        return False

def get_user_id_from_init(init_data: str):
    try:
        parsed = parse_qs(init_data, keep_blank_values=True)
        user_json = parsed.get('user', [''])[0]
        if not user_json:
            return None
        user = json.loads(user_json)
        return int(user.get('id'))
    except Exception as e:
        srv_log(f"get_user_id_from_init error: {e} raw={init_data[:200]}")
        return None

def create_crypto_pay_invoice(plan: str, price, user_id: int):
    try:
        payload = {
            "asset": "USDT",
            "amount": price,
            "description": f"VPN тариф: {plan}",
            "hidden_message": f"User ID: {user_id}"
        }
        srv_log(f"create_crypto_pay_invoice: payload={payload}")
        r = requests.post(f"{CRYPTO_PAY_API}/createInvoice",
                          json=payload,
                          headers={"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN},
                          timeout=15)
        srv_log(f"create_crypto_pay_invoice: HTTP {r.status_code}")
        srv_log(f"create_crypto_pay_invoice: response_text={r.text[:1500]}")
        try:
            j = r.json()
        except Exception as e:
            srv_log(f"create_crypto_pay_invoice: json parse error: {e}")
            return None
        pay_url = j.get('result', {}).get('pay_url')
        srv_log(f"create_crypto_pay_invoice: pay_url={pay_url}")
        return pay_url
    except Exception as e:
        srv_log(f"create_crypto_pay_invoice error: {e}")
        return None

def send_telegram_message(chat_id: int, text: str) -> bool:
    try:
        url = f"https://api.telegram.org/bot{API_TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": text}
        srv_log(f"send_telegram_message: chat_id={chat_id} payload={payload}")
        r = requests.post(url, json=payload, timeout=15)
        srv_log(f"send_telegram_message: HTTP {r.status_code} response={r.text[:1000]}")
        ok = False
        try:
            ok = r.ok and r.json().get("ok", False)
        except:
            ok = False
        srv_log(f"send_telegram_message: ok={ok}")
        return ok
    except Exception as e:
        srv_log(f"send_telegram_message error: {e}")
        return False

@app.route('/api/order', methods=['POST'])
def api_order():
    data = request.get_json(force=True, silent=True) or {}
    plan = data.get('plan')
    price = data.get('price')
    init_data = data.get('initData', '')

    srv_log(f"api_order received: plan={plan} price={price} init_len={len(init_data)}")

    if not plan or price is None or not init_data:
        srv_log("api_order: bad_request")
        return jsonify(ok=False, error="bad_request"), 400

    verified = False
    try:
        verified = verify_webapp_data(init_data, API_TOKEN)
    except Exception as e:
        srv_log(f"verify_webapp_data raised: {e}")

    user_id = get_user_id_from_init(init_data)
    srv_log(f"api_order: plan={plan} price={price} verified={verified} user_id={user_id}")

    if not user_id:
        srv_log("api_order: no_user")
        return jsonify(ok=False, error="no_user"), 400

    if not verified:
        srv_log("WARNING: initData verification failed — proceeding in fallback (UNVERIFIED).")

    pay_url = create_crypto_pay_invoice(plan, price, user_id)
    if not pay_url:
        srv_log("api_order: invoice_failed")
        return jsonify(ok=False, error="invoice_failed"), 500

    text = f"Вы выбрали тариф {plan} (${price}).\nОплатите по ссылке:\n{pay_url}"
    if not send_telegram_message(user_id, text):
        srv_log("api_order: send_failed")
        return jsonify(ok=False, error="send_failed"), 500

    srv_log(f"api_order: success send pay_url to {user_id}")
    return jsonify(ok=True, pay_url=pay_url, verified=bool(verified))

@app.route('/testinvoice', methods=['POST'])
def test_invoice():
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get('user_id')
    plan = data.get('plan', 'TestPlan')
    price = data.get('price', 0.01)
    if not user_id:
        srv_log("test_invoice: no_user_id")
        return jsonify(ok=False, error="no_user_id"), 400
    pay_url = create_crypto_pay_invoice(plan, price, user_id)
    if not pay_url:
        srv_log("test_invoice: invoice_failed")
        return jsonify(ok=False, error="invoice_failed"), 500
    text = f"Test invoice {plan} ${price}\n{pay_url}"
    sent = send_telegram_message(int(user_id), text)
    srv_log(f"test_invoice: pay_url={pay_url} sent={sent}")
    return jsonify(ok=True, pay_url=pay_url, sent=bool(sent))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    srv_log("Starting web service")
    app.run(host="0.0.0.0", port=port)