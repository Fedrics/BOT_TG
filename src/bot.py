import telebot
from telebot import types
from config import API_TOKEN, CRYPTO_PAY_TOKEN
import requests
import json

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
    # Кнопка для открытия Mini App
    webapp_markup = types.InlineKeyboardMarkup()
    webapp_markup.add(
        types.InlineKeyboardButton(
            "🌐 Open VPN Shop" if lang == 'en' else "🌐 Открыть магазин",
            web_app=types.WebAppInfo(url="https://bot-tg-b2bs.onrender.com/")  # Замените на свой URL!
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

def create_crypto_pay_invoice(plan, price, user_id):
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {"Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN}
    data = {
        "asset": "USDT",
        "amount": price,
        "description": f"VPN тариф: {plan}",
        "hidden_message": f"User ID: {user_id}"
    }
    resp = requests.post(url, json=data, headers=headers)
    print("Ответ Crypto Pay:", resp.text)
    try:
        invoice = resp.json()
        return invoice['result']['pay_url']
    except Exception as e:
        print("Ошибка при разборе ответа Crypto Pay:", e)
        return None

if __name__ == "__main__":
    print("Бот запущен и ожидает события...")
    bot.polling(none_stop=True)