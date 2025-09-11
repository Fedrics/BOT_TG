from flask import Flask, request, jsonify, send_from_directory
import os, hmac, hashlib, json, requests, time
from urllib.parse import parse_qs
import secrets
import uuid
from datetime import datetime, timedelta

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

# helper: generate hidify VPN credentials (mock / extend for real Hidify API)
def generate_hidify_credentials(plan: str, user_id: int):
    """
    Возвращает dict с параметрами подключения.
    Для production замените на реальный вызов Hidify API.
    """
    # map plan -> days
    mapping = {
        "1 месяц": 30,
        "3 месяца": 90,
        "6 месяцев": 180,
        "12 месяцев": 365,
        "Basic": 30, "Premium": 90, "Ultimate": 365
    }
    days = mapping.get(plan, 30)
    expire_at = (datetime.utcnow() + timedelta(days=days)).isoformat() + "Z"
    # generate credentials
    config_id = str(uuid.uuid4())
    secret = secrets.token_urlsafe(24)
    vpn_user = f"user_{secrets.token_hex(4)}"
    vpn_password = secrets.token_urlsafe(12)
    return {
        "config_id": config_id,
        "username": vpn_user,
        "password": vpn_password,
        "secret": secret,
        "plan": plan,
        "expires_at": expire_at,
        "notes": f"Generated for user {user_id}"
    }

def send_vpn_credentials(chat_id: int, creds: dict) -> bool:
    text = (
        f"🎉 Оплата подтверждена — ваш VPN доступ готов.\n\n"
        f"Конфиг ID: {creds.get('config_id')}\n"
        f"Username: {creds.get('username')}\n"
        f"Password: {creds.get('password')}\n"
        f"Expires at: {creds.get('expires_at')}\n\n"
        "Инструкция: используйте эти данные для подключения через Hidify client.\n"
        "Если нужен отдельный конфиг — напишите в поддержку."
    )
    return send_telegram_message(chat_id, text)

# CryptoPay webhook: CryptoPay должен POST JSON с info о инвойсе.
# Укажите этот URL в настройках CryptoPay (https://<HOST>/cryptopay/webhook).
@app.route('/cryptopay/webhook', methods=['POST'])
def cryptopay_webhook():
    data = request.get_json(force=True, silent=True) or {}
    # Пример полей: invoice_id, status, hidden_message, payload...
    status = data.get('status') or data.get('invoice', {}).get('status')
    hidden = data.get('hidden_message') or data.get('invoice', {}).get('hidden_message') or ''
    invoice_id = data.get('invoice_id') or data.get('invoice', {}).get('invoice_id')
    # basic token check if CryptoPay sends header 'Crypto-Pay-API-Token'
    token_header = (request.headers.get('Crypto-Pay-API-Token') or request.headers.get('X-CryptoPay-Token') or '')
    if CRYPTO_PAY_TOKEN and token_header and token_header != CRYPTO_PAY_TOKEN:
        return jsonify(ok=False, error="bad_token"), 403

    # try extract user_id из hidden_message ("User ID: 6263...")
    user_id = None
    try:
        if hidden:
            # expected format: "User ID: 6263683504"
            if "User ID" in hidden:
                user_id = int(''.join(ch for ch in hidden if ch.isdigit()))
    except Exception:
        user_id = None

    # only react on paid
    if status and str(status).lower() in ("paid", "success", "confirmed", "active"):
        if not user_id:
            # cannot deliver credentials without user id
            return jsonify(ok=False, error="no_user"), 400
        # optionally dedupe by invoice_id (use existing PROCESSED store)
        if invoice_id:
            cleanup_processed()
            if invoice_id in PROCESSED:
                return jsonify(ok=True, note="already_processed")
            # mark invoice_id to prevent double-issuing
            PROCESSED[invoice_id] = ("issued", time.time())

        # generate credentials and send
        # If you want to tie plan to invoice, try parse description from payload
        plan = data.get('description') or data.get('invoice', {}).get('description') or "1 месяц"
        creds = generate_hidify_credentials(plan, user_id)
        sent = send_vpn_credentials(user_id, creds)
        return jsonify(ok=True, sent=bool(sent), creds_id=creds.get('config_id'))
    return jsonify(ok=True, status=status)

# endpoint for marking paid via Telegram Stars (manual / bot integration)
# Bot or admin can POST here to grant credentials after receiving stars.
@app.route('/api/confirm_stars', methods=['POST'])
def confirm_stars():
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get('user_id')
    plan = data.get('plan', '1 месяц')
    amount = data.get('amount', 0)
    # validate caller: for production require secret token/header
    secret = request.headers.get('X-Internal-Secret') or ''
    if os.environ.get("INTERNAL_SECRET") and secret != os.environ.get("INTERNAL_SECRET"):
        return jsonify(ok=False, error="unauthorized"), 403
    if not user_id:
        return jsonify(ok=False, error="no_user"), 400
    creds = generate_hidify_credentials(plan, user_id)
    sent = send_vpn_credentials(user_id, creds)
    return jsonify(ok=True, sent=bool(sent), creds_id=creds.get('config_id'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)