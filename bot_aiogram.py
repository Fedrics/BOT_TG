import os
import logging
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

API_TOKEN = os.environ.get("API_TOKEN")  # тот же токен бота
HOST_URL = os.environ.get("HOST_URL", "")  # https://yourhost.example
INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Pre-checkout (обязательное подтверждение по платежам Bot API)
@dp.pre_checkout_query_handler(lambda query: True)
async def process_pre_checkout_query(pre_checkout_q: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_q.id, ok=True)

# Обработка успешного платежа (Bot Payments)
@dp.message_handler(content_types=types.ContentType.SUCCESSFUL_PAYMENT)
async def successful_payment_handler(message: types.Message):
    pay: types.SuccessfulPayment = message.successful_payment
    user_id = message.from_user.id
    # invoice_payload обычно содержит произвольную нагрузку — используем как plan
    plan = pay.invoice_payload if getattr(pay, "invoice_payload", None) else "1 месяц"
    # total_amount в самой маленькой единице валюты (например cents)
    try:
        amount = float(pay.total_amount) / 100.0
    except Exception:
        amount = float(pay.total_amount or 0)

    await message.reply("Платёж получен — идёт выдача доступа...")

    # Вызов вашего endpoint для выдачи ключей
    if not HOST_URL:
        await message.reply("Ошибка конфигурации сервера (HOST_URL не задан).")
        return

    try:
        resp = requests.post(
            f"{HOST_URL.rstrip('/')}/api/confirm_stars",
            json={"user_id": user_id, "plan": plan, "amount": amount},
            headers={"X-Internal-Secret": INTERNAL_SECRET} if INTERNAL_SECRET else {},
            timeout=15
        )
        j = resp.json() if resp.ok else {"ok": False, "status": resp.status_code, "text": resp.text[:200]}
        if resp.ok and j.get("ok"):
            await message.reply("Готово — ключ отправлен в личные сообщения.")
        else:
            await message.reply(f"Ошибка выдачи ключа: {j}")
    except Exception as e:
        await message.reply(f"Ошибка при обращении к серверу: {e}")

# Админ команда для ручного подтв. (пример)
@dp.message_handler(commands=["confirm_stars"])
async def cmd_confirm_stars(message: types.Message):
    # usage: /confirm_stars <user_id> <plan> [amount]
    if not message.from_user: 
        return
    parts = message.get_args().split()
    if len(parts) < 2:
        await message.reply("Использование: /confirm_stars <user_id> <plan> [amount]")
        return
    user_id = int(parts[0])
    plan = parts[1]
    amount = float(parts[2]) if len(parts) >= 3 else 0
    try:
        resp = requests.post(
            f"{HOST_URL.rstrip('/')}/api/confirm_stars",
            json={"user_id": user_id, "plan": plan, "amount": amount},
            headers={"X-Internal-Secret": INTERNAL_SECRET} if INTERNAL_SECRET else {},
            timeout=15
        )
        if resp.ok and resp.json().get("ok"):
            await message.reply("OK: ключ выдан.")
        else:
            await message.reply(f"Ошибка сервера: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        await message.reply(f"Ошибка: {e}")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)