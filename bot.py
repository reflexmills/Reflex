import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
import aiohttp
import openai
import os
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")  # Заменено имя переменной
CRYPTOBOT_BOT_USERNAME = "@CryptoBot"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OWNER_ID = int(os.getenv("OWNER_ID"))

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

openai.api_key = OPENAI_API_KEY

SERVICES = {
    'presentation': {'name': 'Презентация', 'price': 5},
    'website': {'name': 'Сайт', 'price': 10},
}

user_orders = {}

@dp.message(F.text == "/start")
async def start(message: Message):
    kb = InlineKeyboardBuilder()
    for key, value in SERVICES.items():
        kb.button(text=f"{value['name']} - ${value['price']}", callback_data=key)
    kb.adjust(1)
    await message.answer("Выберите услугу:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.in_(SERVICES.keys()))
async def ask_description(callback: CallbackQuery):
    service = callback.data
    user_orders[callback.from_user.id] = {'service': service}
    await callback.message.answer(f"Введите описание для {SERVICES[service]['name']}:")
    await callback.answer()

@dp.message(F.text)
async def handle_description(message: Message):
    user_id = message.from_user.id
    if user_id not in user_orders or 'description' in user_orders[user_id]:
        return
    user_orders[user_id]['description'] = message.text
    service = user_orders[user_id]['service']
    price = SERVICES[service]['price']

    invoice = await create_invoice(user_id, price, f"Оплата за {SERVICES[service]['name']}")
    if invoice:
        pay_url = invoice['result']['pay_url']
        user_orders[user_id]['invoice_id'] = invoice['result']['invoice_id']
        kb = InlineKeyboardBuilder()
        kb.button(text="Оплатить в CryptoBot", url=pay_url)
        await message.answer("Ссылка для оплаты:", reply_markup=kb.as_markup())
    else:
        await message.answer("Ошибка при создании счёта. Попробуйте позже.")

@dp.message(F.text == "/check")
async def check_payment(message: Message):
    user_id = message.from_user.id
    order = user_orders.get(user_id)
    if not order or 'invoice_id' not in order:
        await message.answer("Нет активных заказов.")
        return

    status = await check_invoice(order['invoice_id'])
    if status == 'paid':
        await message.answer("Оплата получена! Генерирую...")
        await send_result(message, order)
    else:
        await message.answer("Оплата не найдена. Попробуйте позже или проверьте позже командой /check")

async def send_result(message: Message, order):
    service = order['service']
    description = order['description']

    if service == 'presentation':
        content = await generate_content(f"Сделай план презентации по теме: {description}")
        await message.answer_document(types.InputFile.from_buffer(content.encode(), filename="presentation.txt"))
    elif service == 'website':
        html_code = await generate_content(f"Создай HTML код лендинга по описанию: {description}. Сделай современный дизайн.")
        image_url = await generate_image(description)
        if image_url:
            html_code = html_code.replace("<body>", f"<body><img src='{image_url}' alt='Generated Image' style='width:100%;'>")
        await message.answer_document(types.InputFile.from_buffer(html_code.encode(), filename="website.html"))

async def generate_content(prompt):
    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты помогаешь с созданием цифрового контента."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Ошибка генерации: {e}"

async def generate_image(prompt):
    try:
        response = await openai.Image.acreate(
            prompt=prompt,
            n=1,
            size="1024x1024"
        )
        return response['data'][0]['url']
    except Exception:
        return None

async def create_invoice(user_id, amount, desc):
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN}  # заменён ключ
    payload = {
        "asset": "USDT",
        "amount": amount,
        "description": desc,
        "hidden_message": "Спасибо за оплату!",
        "paid_btn_name": "openBot",
        "paid_btn_url": f"https://t.me/{CRYPTOBOT_BOT_USERNAME.lstrip('@')}",
        "payload": str(user_id),
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            return await resp.json()

async def check_invoice(invoice_id):
    url = f"https://pay.crypt.bot/api/getInvoices?invoice_ids={invoice_id}"
    headers = {"Crypto-Pay-API-Token": CRYPTOBOT_TOKEN}  # заменён ключ
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            data = await resp.json()
            return data['result'][0]['status'] if data['result'] else None

if __name__ == '__main__':
    asyncio.run(dp.start_polling(bot))
