import os
import json
import requests
import telebot
from telebot import types
from src.config import API_TOKEN, CRYPTO_PAY_TOKEN
import traceback

bot = telebot.TeleBot(API_TOKEN)
user_lang = {}

texts = {
    'ru': {
        'welcome': "Добро пожаловать! Пожалуйста, выберите язык:",
        'shop': "Добро пожаловать в VPN магазин! Нажмите кнопку ниже, чтобы открыть каталог.",
        'pay': "Вы выбрали тариф {plan} (${price}).\nОплатите по ссылке:"
    },
    'en': {
        'welcome': "Welcome! Please select your language:",
        'shop': "Welcome to the VPN Shop! Click the button below to open the catalog.",
        'pay': "You selected the {plan} plan (${price}).\nPay using the link below:"
    }
}

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
    bot.send_message(message.chat.id, "✅", reply_markup=types.ReplyKeyboardRemove())
    webapp_markup = types.InlineKeyboardMarkup()
    webapp_markup.add(
        types.InlineKeyboardButton(
            "🌐 Open VPN Shop" if lang == 'en' else "🌐 Открыть магазин",
            web_app=types.WebAppInfo(url="https://bot-tg-aai9.onrender.com/")
        )
    )
    bot.send_message(message.chat.id, texts[lang]['shop'], reply_markup=webapp_markup)

def create_crypto_pay_invoice(plan: str, price, user_id):
    try:
        payload = {
            "asset": "USDT",
            "amount": price,
            "description": f"VPN тариф: {plan}",
            "hidden_message": f"User ID: {user_id}"
        }
        print("Создаём инвойс CryptoPay, payload:", payload)
        resp = requests.post(
            "https://pay.crypt.bot/api/createInvoice",
            json=payload,
            headers={"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN},
            timeout=15
        )
        print("CryptoPay HTTP status:", resp.status_code)
        print("CryptoPay response text:", resp.text)
        try:
            j = resp.json()
        except Exception as e:
            print("Не удалось распарсить JSON от CryptoPay:", e)
            return None
        pay_url = j.get('result', {}).get('pay_url')
        return pay_url
    except Exception as e:
        print("Ошибка при create_crypto_pay_invoice:", e)
        print(traceback.format_exc())
        return None

@bot.message_handler(content_types=['web_app_data'])
def handle_web_app_data(message):
    try:
        raw = getattr(message, 'web_app_data', None)
        print("RAW web_app_data object:", raw)
        if not raw or not getattr(raw, 'data', None):
            print("Нет web_app_data.data в сообщении")
            bot.send_message(message.chat.id, "Не получены данные из Mini App. Откройте Mini App через кнопку в Telegram.")
            return

        print("Получены данные из Mini App:", message.web_app_data.data)
        lang = get_lang(message)
        data = json.loads(message.web_app_data.data)
        plan = data.get('plan')
        price = data.get('price')
        if not plan or price is None:
            print("Некорректные данные из Mini App:", data)
            bot.send_message(message.chat.id, "Некорректные данные. Попробуйте ещё раз.")
            return

        pay_url = create_crypto_pay_invoice(plan, price, message.from_user.id)
        if pay_url:
            bot.send_message(message.chat.id, texts[lang]['pay'].format(plan=plan, price=price) + f"\n{pay_url}")
        else:
            bot.send_message(message.chat.id, "Ошибка при создании платежа. Проверьте логи сервера.")
    except Exception as e:
        print("Ошибка в обработчике web_app_data:", e)
        print(traceback.format_exc())
        try:
            bot.send_message(message.chat.id, "Произошла ошибка. Попробуйте позже.")
        except:
            pass

if __name__ == "__main__":
    import time
    print("Подготовка к запуску polling...")
    try:
        # убедиться, что webhook снят
        try:
            bot.remove_webhook()
            print("Webhook removed (if existed).")
        except Exception as e:
            print("Не удалось явно удалить webhook:", e)

        # запуск polling в цикле с обработкой ошибок (например, 409)
        while True:
            try:
                print("Бот запущен и ожидает события...")
                bot.polling(none_stop=True)
            except Exception as e:
                print("Polling упал с исключением:", repr(e))
                # если это конфликт 409 — значит где-то ещё запущен polling/webhook
                # подождём и попытаемся снова (не форсировать)
                time.sleep(5)
    except KeyboardInterrupt:
        print("Остановка пользователем.")
