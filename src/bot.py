import telebot
from telebot import types
from config import API_TOKEN, CRYPTO_PAY_TOKEN, CRYPTO_PAY_API

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
            web_app=types.WebAppInfo(url="https://your-webapp-url.com")  # Замените на свой URL!
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

bot.polling()