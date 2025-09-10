import telebot
from telebot import types
from config import API_TOKEN, CRYPTO_PAY_TOKEN, CRYPTO_PAY_API
import requests
import json

bot = telebot.TeleBot(API_TOKEN)

# Store user language preferences
user_lang = {}
user_cart = {}

# Language dictionaries
texts = {
    'en': {
        'welcome': "Welcome to the Mini Telegram Bot!",
        'commands': "Available commands:\n/start - Start the bot\n/help - Get help",
        'cart_empty': "Your cart is empty.",
        'cart': "Your cart:\n",
        'add': "ADD",
        'checkout': "Checkout"
    },
    'ru': {
        'welcome': "Добро пожаловать в Мини Телеграм Бот!",
        'commands': "Доступные команды:\n/start - Запустить бота\n/help - Получить помощь",
        'cart_empty': "Ваша корзина пуста.",
        'cart': "Ваша корзина:\n",
        'add': "ДОБАВИТЬ",
        'checkout': "Оформить заказ"
    }
}

def get_lang(message):
    return user_lang.get(message.from_user.id, 'en')

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(types.KeyboardButton("English"), types.KeyboardButton("Русский"))
    bot.send_message(message.chat.id, texts['en']['welcome'], reply_markup=markup)

    # Кнопка для открытия Mini App
    webapp_markup = types.InlineKeyboardMarkup()
    webapp_markup.add(
        types.InlineKeyboardButton(
            "🌐 Open Mini App",
            web_app=types.WebAppInfo(url="https://bot-tg-b2bs.onrender.com/")  # Замените на свой URL!
        )
    )
    bot.send_message(
        message.chat.id,
        "Open Mini App:",
        reply_markup=webapp_markup
    )

@bot.message_handler(func=lambda message: message.text in ["English", "Русский"])
def set_language(message):
    lang = 'en' if message.text == "English" else 'ru'
    user_lang[message.from_user.id] = lang
    user_cart[message.from_user.id] = {}
    bot.send_message(message.chat.id, "✅", reply_markup=types.ReplyKeyboardRemove())
    bot.send_message(message.chat.id, texts[lang]['commands'])

@bot.message_handler(commands=['help'])
def send_help(message):
    lang = get_lang(message)
    bot.send_message(message.chat.id, texts[lang]['commands'])

@bot.message_handler(content_types=['web_app_data'])
def handle_web_app_data(message):
    print("Получены данные из Mini App:", message.web_app_data.data)  # <--- добавьте эту строку
    data = json.loads(message.web_app_data.data)
    plan = data.get('plan')
    price = data.get('price')
    # Создаем счет через Crypto Pay API
    pay_url = create_crypto_pay_invoice(plan, price, message.from_user.id)
    bot.send_message(
        message.chat.id,
        f"Вы выбрали тариф: {plan} (${price})\n\nОплатите по ссылке:\n{pay_url}"
    )

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
    print("Ответ Crypto Pay:", resp.text)  # <--- добавьте эту строку
    invoice = resp.json()
    return invoice['result']['pay_url']

if __name__ == "__main__":
    bot.polling(none_stop=True)