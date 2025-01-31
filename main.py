import os
from datetime import datetime

import pandas as pd
from aiogram import Bot, Dispatcher, executor, types
from dotenv import load_dotenv

days_russian = {
    "Monday": "Понедельник",
    "Tuesday": "Вторник",
    "Wednesday": "Среда",
    "Thursday": "Четверг",
    "Friday": "Пятница",
    "Saturday": "Суббота",
    "Sunday": "Воскресенье",
}


load_dotenv()
API_TOKEN = os.getenv("API_TOKEN")
day_of_week_en = datetime.today().strftime("%A")


bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# File for storing balance data
DATA_FILE = "balance_data.csv"

try:
    balance_data = pd.read_csv(DATA_FILE)
    if balance_data.empty:
        raise FileNotFoundError
except (FileNotFoundError, pd.errors.EmptyDataError):
    balance_data = pd.DataFrame(columns=["Date", "Day of Week", "Price", "Balance"])
    balance_data.to_csv(DATA_FILE, index=False)


def print_balance_table():
    """Форматирует таблицу для отправки в Telegram"""
    if balance_data.empty:
        return "⚠️ Баланс не найден. Добавьте данные с помощью /update_balance."

    text = "📊 Текущая таблица баланса:\n\n"
    for _, row in balance_data.iterrows():
        text += (
            f"📅 Дата: {row['Date']} ({row['Day of Week']})\n"
            f"💰 Цена: {row['Price']}€\n"
            f"📈 Баланс: {row['Balance']}€\n"
            "➖➖➖➖➖➖➖➖➖\n"
        )
    return text


@dp.message_handler(commands=["start"])
async def send_balance(message: types.Message):
    """Выводит текущий баланс"""
    await message.reply("🤗 Welcome my dear friend!")


@dp.message_handler(commands=["balance"])
async def send_balance(message: types.Message):
    """Выводит текущий баланс"""
    await message.reply(print_balance_table())


@dp.message_handler(commands=["update_balance"])
async def update_balance(message: types.Message):
    """Обновляет таблицу баланса"""
    try:
        date = datetime.today().strftime("%Y-%B-%d")
        day = days_russian[day_of_week_en]
        price = 20

        global balance_data
        if balance_data.empty:
            balance = 0
        else:
            balance = balance_data["Balance"].iloc[-1] + float(price)

        new_row = pd.DataFrame(
            [[date, day, price, balance]], columns=balance_data.columns
        )
        balance_data = pd.concat([balance_data, new_row], ignore_index=True)

        balance_data.to_csv(DATA_FILE, index=False)
        await message.reply(f"✅ Баланс за {date} обновлен!\n\n{print_balance_table()}")

    except ValueError as e:
        await message.reply(f"❌ Ошибка: {e}")


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
