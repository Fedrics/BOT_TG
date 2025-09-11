import os
import time
import json
import traceback
import requests
import telebot
from telebot import types
from src.config import API_TOKEN, CRYPTO_PAY_TOKEN, CRYPTO_PAY_API

bot = telebot.TeleBot(API_TOKEN, parse_mode='HTML')
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
    try:
        bot.send_message(message.chat.id, "✅", reply_markup=types.ReplyKeyboardRemove())
    except Exception:
        pass
    webapp_markup = types.InlineKeyboardMarkup()
    webapp_markup.add(
        types.InlineKeyboardButton(
            "🌐 Open VPN Shop" if lang == 'en' else "🌐 Открыть магазин",
            web_app=types.WebAppInfo(url=os.environ.get("MINI_APP_URL", "https://bottg-production-90b1.up.railway.app/"))
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
            f"{CRYPTO_PAY_API}/createInvoice",
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
            try:
                bot.send_message(message.chat.id, "Не получены данные из Mini App. Откройте Mini App через кнопку в Telegram.")
            except Exception:
                pass
            return

        print("Получены данные из Mini App:", message.web_app_data.data)
        lang = get_lang(message)
        try:
            data = json.loads(message.web_app_data.data)
        except Exception as e:
            print("JSON parse error:", e)
            bot.send_message(message.chat.id, "Неправильный формат данных из Mini App.")
            return

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

@bot.message_handler(commands=['testpay'])
def cmd_testpay(message):
    # тестовый вызов инвойса для проверки работы CryptoPay и токена
    try:
        bot.send_message(message.chat.id, "Запускаю тестовый createInvoice...")
        pay_url = create_crypto_pay_invoice("TestPlan", 0.01, message.from_user.id)
        bot.send_message(message.chat.id, f"Результат create_invoice: {pay_url or 'None — смотрите логи'}")
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка теста: {e}")

# опционально: лог всех входящих сообщений, чтобы увидеть web_app_data, если он приходит
@bot.message_handler(func=lambda m: True, content_types=['text', 'web_app_data', 'photo', 'document', 'audio'])
def log_all(m):
    try:
        print("INCOMING MESSAGE:", repr(m))
    except Exception:
        pass

if __name__ == "__main__":
    print("Подготовка к запуску бота...")
    # удаляем webhook, если был установлен
    try:
        bot.remove_webhook()
        print("Webhook removed (if existed).")
    except Exception as e:
        print("Не удалось удалить webhook явно:", e)

    # защитный цикл для polling с логированием
    while True:
        try:
            print("Бот запущен и ожидает события...")
            bot.polling(none_stop=True)
        except Exception as e:
            err = repr(e)
            print("Polling упал с исключением:", err)
            # конфликт 409 (webhook или другой polling) — логируем и ждем
            if '409' in err or 'Conflict' in err:
                print("Конфликт getUpdates/webhook. Убедитесь, что не запущен другой инстанс и webhook удалён.")
            time.sleep(5)
