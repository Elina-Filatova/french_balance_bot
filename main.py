import os
from datetime import datetime

import psycopg2
from aiogram import Bot, Dispatcher, executor, types
from dotenv import load_dotenv

DAYS_RUSSIAN = {
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


class BalanceDB:
    """
    Класс для работы с базой данных.
    Отвечает за создание таблицы, получение записей,
    добавление новой записи и удаление записи по дате.
    """

    def __init__(self):
        self.db_config = {
            "dbname": os.getenv("DB_NAME"),
            "user": os.getenv("DB_USER"),
            "password": os.getenv("DB_PASSWORD"),
            "host": os.getenv("DB_HOST"),
            "port": os.getenv("DB_PORT"),
        }

    def get_connection(self):
        """Устанавливает соединение с базой данных."""
        return psycopg2.connect(**self.db_config)

    def create_balance_table(self):
        """Создаёт таблицу balance, если её ещё нет."""
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS balance (
                date DATE PRIMARY KEY,
                day_of_week VARCHAR(20),
                price NUMERIC,
                balance NUMERIC
            );
            """
        )
        conn.commit()
        cur.close()
        conn.close()

    def get_all_balance_entries(self):
        """
        Получает все записи баланса, отсортированные по дате.
        Вычисляет накопительный баланс в пределах каждого месяца.
        """
        conn = self.get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 
                date, 
                day_of_week, 
                price, 
                SUM(price) OVER (
                    PARTITION BY DATE_TRUNC('month', date)
                    ORDER BY date
                ) AS monthly_balance
            FROM balance
            ORDER BY date;
            """
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows

    def add_balance_entry(self, date=None):
        """
        Добавляет новую запись баланса для указанной даты (или для сегодняшней, если не передана).
        Теперь баланс рассчитывается на лету для каждого месяца, поэтому не обновляем последующие записи.

        Возвращает:
            tuple: (успех: bool, сообщение: str)
        """
        conn = self.get_connection()
        cur = conn.cursor()

        if not date:
            date_obj = datetime.today().date()
            day_of_week = date_obj.strftime("%A")
        else:
            date_obj = datetime.strptime(date, "%Y-%m-%d").date()
            day_of_week = date_obj.strftime("%A")

        day_of_week_ru = DAYS_RUSSIAN.get(day_of_week, day_of_week)
        cur.execute("SELECT date FROM balance WHERE date = %s", (date_obj,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return False, f"🤗 Баланс за {date_obj} уже обновлен!"

        cur.execute(
            """
            INSERT INTO balance (date, day_of_week, price, balance)
            VALUES (%s, %s, %s, %s);
            """,
            (date_obj, day_of_week_ru, 20, 20),
        )
        conn.commit()
        cur.close()
        conn.close()
        return True, "Баланс успешно обновлен!"

    def delete_balance_entry_by_date(self, date):
        """
        Удаляет запись баланса за указанную дату.

        Args:
            date (str): Дата в формате YYYY-MM-DD.

        Returns:
            tuple: (успех: bool, сообщение: str)
        """
        if not date:
            return (
                False,
                "Дата должна быть в формате: ГГГГ-ММ-ДД. Например: /delete_balance 2025-02-02",
            )

        try:
            conn = self.get_connection()
            cur = conn.cursor()

            cur.execute("SELECT date FROM balance WHERE date = %s", (date,))
            if not cur.fetchone():
                cur.close()
                conn.close()
                return False, "Данные за это число не найдены!"

            cur.execute("DELETE FROM balance WHERE date = %s;", (date,))
            conn.commit()
            cur.close()
            conn.close()
            return True, f"Данные за {date} успешно удалены!"

        except Exception as e:
            if conn:
                conn.close()
            return False, f"Ошибка при удалении: {str(e)}"


class BalanceBot:
    """
    Класс для Telegram-бота.
    Отвечает за обработку команд и взаимодействие с базой данных через класс BalanceDB.
    """

    def __init__(self, token, db: BalanceDB):
        self.bot = Bot(token=token)
        self.dp = Dispatcher(self.bot)
        self.db = db
        self.register_handlers()

    def register_handlers(self):
        """Регистрирует обработчики команд для бота."""
        self.dp.register_message_handler(self.intro, commands=["start"])
        self.dp.register_message_handler(self.send_balance, commands=["balance"])
        self.dp.register_message_handler(
            self.update_balance, commands=["update_balance"]
        )
        self.dp.register_message_handler(
            self.delete_balance, commands=["delete_balance"]
        )

    async def intro(self, message: types.Message):
        """Обработчик команды /start."""
        text = (
            "Bonjour, девочки! Я ваш верный помощник Франсис 🥰 и вот что я умею:\n\n"
            "📊 Управление балансом:\n"
            "/balance - показать текущий баланс\n"
            "/update_balance - обновить баланс\n"
            "/delete_balance YYYY-MM-DD - удалить запись\n\n"
        )
        await message.reply(text)

    async def send_balance(self, message: types.Message):
        """Обработчик команды /balance. Отправляет текущую таблицу баланса."""
        entries = self.db.get_all_balance_entries()
        if not entries:
            await message.reply(
                "⚠️ Баланс не найден. Добавьте данные с помощью /update_balance."
            )
            return

        text = "📊 Текущая таблица баланса (накопительный баланс по месяцам):\n\n"
        for row in entries:
            # row: (date, day_of_week, price, monthly_balance)
            text += (
                f"📅 Дата: {row[0]} ({row[1]})\n"
                f"💰 Цена: {row[2]}€\n"
                f"📈 Баланс за месяц: {row[3]}€\n"
                "➖➖➖➖➖➖➖➖➖\n"
            )
        await message.reply(text)

    async def update_balance(self, message: types.Message):
        """Обработчик команды /update_balance. Добавляет новую запись баланса."""
        date_arg = message.get_args().strip()
        try:
            if date_arg:
                success, msg = self.db.add_balance_entry(date_arg)
            else:
                success, msg = self.db.add_balance_entry()

            if success:
                balance_table_text = self.format_balance_table()
                await message.reply(f"✅ {msg}\n\n{balance_table_text}")
            else:
                await message.reply(f"⚠️ {msg}")
        except Exception as e:
            await message.reply(f"❌ Ошибка: {e}")

    async def delete_balance(self, message: types.Message):
        """Обработчик команды /delete_balance. Удаляет запись по дате."""
        date = message.get_args()
        success, msg = self.db.delete_balance_entry_by_date(date)
        if success:
            balance_table_text = self.format_balance_table()
            await message.reply(f"✅ {msg}\n\n{balance_table_text}")
        else:
            await message.reply(f"❌ {msg}")

    def format_balance_table(self):
        """Форматирует таблицу баланса для отправки в Telegram."""
        entries = self.db.get_all_balance_entries()
        if not entries:
            return "Нет данных о балансе."
        text = "📊 Текущая таблица баланса (накопительный баланс по месяцам):\n\n"
        for row in entries:
            text += (
                f"📅 Дата: {row[0]} ({row[1]})\n"
                f"💰 Цена: {row[2]}€\n"
                f"📈 Баланс за месяц: {row[3]}€\n"
                "➖➖➖➖➖➖➖➖➖\n"
            )
        return text

    def run(self):
        """Запускает бота."""
        executor.start_polling(self.dp, skip_updates=True)


if __name__ == "__main__":
    db = BalanceDB()
    db.create_balance_table()

    balance_bot = BalanceBot(API_TOKEN, db)
    balance_bot.run()
