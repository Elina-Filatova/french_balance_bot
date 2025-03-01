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

MONTHS_RUSSIAN = {
    1: "январь ❄️",
    2: "февраль 💘",
    3: "март 🌷",
    4: "апрель 🌼",
    5: "май 🪻",
    6: "июнь ☀️",
    7: "июль 🌞",
    8: "август 🏖️",
    9: "сентябрь 🍁",
    10: "октябрь 🎃",
    11: "ноябрь 🍂",
    12: "декабрь 🎄",
}


CURRENT_MONTH = datetime.today().month

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

    def get_all_balance_entries(self, month=None):
        if month is None or not month:
            month = datetime.today().month
        else:
            try:
                month = int(month)
                if month < 1 or month > 12:
                    return "Месяц должен быть в диапазоне от 1 до 12. Пример: '/balance 2' - покажет данные за февраль."
            except ValueError:
                return "Неверный формат месяца. Введите число от 1 до 12. Пример: '/balance 2' - покажет данные за февраль."

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
            WHERE EXTRACT(MONTH FROM date) = %s
            ORDER BY date;
            """,
            (month,),
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
        self.dp.register_message_handler(self.updates, commands=["updates"])

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

    async def updates(self, message: types.Message):
        """Обработчик команды /updates."""
        text = (
            "Привет, девочки! Готовы к обновлениям? 🥰\n\n"
            "✨ *Новые возможности* ✨\n\n"
            "📅 *1. Баланс за каждый месяц*\n"
            "   👉 Теперь баланс рассчитывается отдельно для каждого месяца.\n"
            "   👉 Например, введите `/balance 2`, чтобы увидеть данные за февраль.\n"
            "   👉 Если не указать месяц, будет показан баланс за текущий месяц 🪄.\n\n"
            "💡 *Важно:* Указывайте месяц в числовом формате от 1 до 12.\n\n"
            "📅 *2. Обновление таблицы после удаления*\n"
            "   👉 При удалении баланса за определенную дату теперь автоматически выводится обновленная таблица за соответствующий месяц ✅.\n\n"
            "😘 Bizouu! 🎉"
        )
        await message.reply(text)

    async def send_balance(self, message: types.Message):
        month_arg = message.get_args().strip()
        month = month_arg if month_arg else None

        entries = self.db.get_all_balance_entries(month)
        if not entries:
            await message.reply(
                "⚠️ Баланс не найден. Добавьте данные с помощью /update_balance."
            )
            return

        # text = "📊 Текущая таблица баланса:\n\n"
        # for row in entries:
        #     text += (
        #         f"📅 Дата: {row[0]} ({row[1]})\n"
        #         f"💰 Цена: {row[2]}€\n"
        #         f"📈 Баланс за месяц: {row[3]}€\n"
        #         "➖➖➖➖➖➖➖➖➖\n"
        #     )
        text = self.format_balance_table(month)
        await message.reply(text)

    async def update_balance(self, message: types.Message):
        """Обработчик команды /update_balance. Добавляет новую запись баланса."""
        date_arg = message.get_args().strip()
        try:
            if date_arg:
                success, msg = self.db.add_balance_entry(date_arg)
                month = date_arg.split("-")[1]
                balance_table_text = self.format_balance_table(month)
            else:
                success, msg = self.db.add_balance_entry()
                balance_table_text = self.format_balance_table()

            if success:
                await message.reply(f"✅ {msg}\n\n{balance_table_text}")
            else:
                await message.reply(f"⚠️ {msg}")
        except Exception as e:
            await message.reply(f"❌ Ошибка: {e}")

    async def delete_balance(self, message: types.Message):
        """Обработчик команды /delete_balance. Удаляет запись по дате."""
        date = message.get_args()
        success, msg = self.db.delete_balance_entry_by_date(date)
        month = date.split("-")[1]
        if success:
            balance_table_text = self.format_balance_table(month)
            await message.reply(f"✅ {msg}\n\n{balance_table_text}")
        else:
            await message.reply(f"❌ {msg}")

    def format_balance_table(self, month=None):
        month_num = int(month) if month else CURRENT_MONTH

        entries = self.db.get_all_balance_entries(month=month_num)
        if not entries:
            return "Нет данных о балансе."

        month_rus = MONTHS_RUSSIAN.get(month_num, MONTHS_RUSSIAN.get(CURRENT_MONTH))
        text = f"📊 Текущая таблица баланса за {month_rus}:\n\n"
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
