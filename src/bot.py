import os
import hmac
import hashlib 
import json
from urllib.parse import parse_qs
import requests
import telebot
from telebot import types
from src.config import API_TOKEN, CRYPTO_PAY_TOKEN

CRYPTO_PAY_API = "https://pay.crypt.bot/api"

bot = telebot.TeleBot(API_TOKEN)
user_lang = {}

texts = {
    'en': {
        'welcome': "Welcome! Please select your language:",
        'shop': "Welcome to the VPN Shop! Click the button below to open the catalog.",
        'pay': "You selected the {plan} plan (${price}).\nPay using the link below:"
    },
    'ru': {
        'welcome': "Добро пожаловать! Пожалуйста, выберите язык:",
        'shop': "Добро пожаловать в VPN магазин! Нажмите кнопку ниже, чтобы открыть каталог.",
        'pay': "Вы выбрали тариф {plan} (${price}).\nОплатите по ссылке ниже:"
    }
}

app = Flask(__name__, static_folder='static', template_folder='webapp')

def get_lang(message):
    return user_lang.get(message.from_user.id, 'en')

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(types.KeyboardButton("English"), types.KeyboardButton("Русский"))
    bot.send_message(message.chat.id, texts['en']['welcome'], reply_markup=markup)

@bot.message_handler(func=lambda message: message.text in ["English", "Русский"])
def set_language(message):
    lang = 'en' if message.text == "English" else 'ru'
    user_lang[message.from_user.id] = lang
    bot.send_message(message.chat.id, "✅!", reply_markup=types.ReplyKeyboardRemove())
    # Кнопка для открытия Mini App
    webapp_markup = types.InlineKeyboardMarkup()
    webapp_markup.add(
        types.InlineKeyboardButton(
            "🌐 Open VPN Shop" if lang == 'en' else "🌐 Открыть магазин",
            web_app=types.WebAppInfo(url="https://bot-tg-aai9.onrender.com/")  # Замените на свой URL!
        )
    )
    bot.send_message(
        message.chat.id,
        texts[lang]['shop'],
        reply_markup=webapp_markup
    )

@bot.message_handler(content_types=['web_app_data'])
def handle_web_app_data(message):
    try:
        print("Получены данные из Mini App:", message.web_app_data.data)
        lang = get_lang(message)
        data = json.loads(message.web_app_data.data)
        plan = data.get('plan')
        price = data.get('price')
        pay_url = create_crypto_pay_invoice(plan, price, message.from_user.id)
        if pay_url:
            bot.send_message(
                message.chat.id,
                texts[lang]['pay'].format(plan=plan, price=price) + f"\n{pay_url}"
            )
        else:
            bot.send_message(message.chat.id, "Ошибка при создании платежа. Попробуйте позже.")
    except Exception as e:
        print("Ошибка в обработчике web_app_data:", e)
        bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")

def verify_webapp_data(init_data: str, bot_token: str) -> bool:
    # https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app
    parsed = parse_qs(init_data, keep_blank_values=True)
    received_hash = parsed.get('hash', [''])[0]
    data_check_arr = []
    for k, v in parsed.items():
        if k == 'hash':
            continue
        # значения берём первое, WebApp всегда шлёт по одному значению
        data_check_arr.append(f"{k}={v[0]}")
    data_check_arr.sort()
    data_check_string = "\n".join(data_check_arr)

    secret_key = hmac.new(b'WebAppData', bot_token.encode(), hashlib.sha256).digest()
    calc_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calc_hash, received_hash)

def get_user_id_from_init(init_data: str) -> int | None:
    parsed = parse_qs(init_data, keep_blank_values=True)
    user_json = parsed.get('user', [''])[0]
    if not user_json:
        return None
    try:
        user = json.loads(user_json)
        return int(user.get('id'))
    except Exception:
        return None

def create_crypto_pay_invoice(plan: str, price: float, user_id: int) -> str | None:
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
        return j["result"]["pay_url"]
    except Exception:
        print("CryptoPay error:", r.text)
        return None

def send_telegram_message(chat_id: int, text: str) -> bool:
    url = f"https://api.telegram.org/bot{API_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)
    ok = r.ok and r.json().get("ok", False)
    if not ok:
        print("sendMessage error:", r.text)
    return ok

@app.route('/')
def index():
    return send_from_directory('webapp', 'index.html')

@app.route('/api/order', methods=['POST'])
def api_order():
    data = request.get_json(force=True, silent=True) or {}
    plan = data.get('plan')
    price = data.get('price')
    init_data = data.get('initData', '')

    if not plan or not price or not init_data:
        return jsonify(ok=False, error="Bad request"), 400

    if not verify_webapp_data(init_data, API_TOKEN):
        return jsonify(ok=False, error="Invalid initData"), 403

    user_id = get_user_id_from_init(init_data)
    if not user_id:
        return jsonify(ok=False, error="No user"), 400

    pay_url = create_crypto_pay_invoice(plan, price, user_id)
    if not pay_url:
        return jsonify(ok=False, error="Invoice failed"), 500

    msg = f"Вы выбрали тариф {plan} (${price}).\nОплатите по ссылке:\n{pay_url}"
    if not send_telegram_message(user_id, msg):
        return jsonify(ok=False, error="sendMessage failed"), 500

    return jsonify(ok=True)

if __name__ == "__main__":
    print("Бот запущен и ожидает события...")
    bot.polling(none_stop=True)
