from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from difflib import get_close_matches

from datetime import datetime, timedelta

import json

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

import asyncpg

import os
from dotenv import load_dotenv

load_dotenv()

async def connect_to_db():
    return await asyncpg.create_pool(
        user=os.getenv("DB_USER"), 
        password=os.getenv("DB_PASSWORD"), 
        database=os.getenv("DB_NAME"), 
        host=os.getenv("DB_HOST")
    )

async def save_client(pool, email):
    async with pool.acquire() as conn:
        client_id = await conn.fetchval(
            "INSERT INTO clients (email) VALUES ($1) ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email RETURNING id",
            email
        )
        return client_id

async def save_order(pool, client_id, delivery_date, items, total_price):
    # Преобразуем список items в строку JSON
    if isinstance(items, list):
        items = json.dumps(items)
    
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO orders (client_id, delivery_date, items, total_price) VALUES ($1, $2, $3, $4)",
            client_id, delivery_date, items, total_price
        )




async def get_categories_and_products(pool):
    async with pool.acquire() as conn:
        categories = await conn.fetch("""
            SELECT 
                c.name AS category_name, 
                json_agg(json_build_object('name', p.name, 'price', p.price)) AS products
            FROM categories c
            LEFT JOIN products p ON c.id = p.category_id
            GROUP BY c.name
        """)

        # Преобразуем результаты в ожидаемый формат
        categories_dict = {}
        for row in categories:
            category_name = row["category_name"]
            products = row["products"]  # json_agg возвращает список JSON-объектов
            if products is not None:  # Проверяем, что продукты существуют
                categories_dict[category_name] = {
                    product["name"]: product["price"] for product in json.loads(products)
                }
            else:
                categories_dict[category_name] = {}  # Если продуктов нет, создаем пустую категорию

        return categories_dict

async def startup(app):
    pool = await connect_to_db()
    global CATEGORIES
    CATEGORIES = await get_categories_and_products(pool)
    await pool.close()    


# Функция для генерации дат на ближайший месяц, исключая текущий день
def generate_dates_for_month():
    today = datetime.now()
    days_in_month = 30
    return [
        (today + timedelta(days=i)).strftime("%d.%m.%Y")
        for i in range(1, days_in_month + 1)  # Начинаем с i=1, чтобы исключить сегодня
    ]
    
    
def send_email_with_pdf(to_email, pdf_path):
    # Настройки SMTP
    # введите свои данные
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT"))
    sender_email = os.getenv("SMTP_EMAIL")
    sender_password = os.getenv("SMTP_PASSWORD")

    # Формирование email
    subject = "Чек интернет-кафе"
    body = "Спасибо за ваш заказ! Ваш чек во вложении."

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    # Прикрепление PDF
    with open(pdf_path, "rb") as attachment:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment.read())
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition",
        f"attachment; filename={pdf_path}",
    )
    msg.attach(part)

    # Отправка email
    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
    
    
def generate_pdf_receipt(context):
    # Получение данных заказа
    selected_items = context.user_data.get("selected_items", [])
    delivery_dates = context.user_data.get("delivery_dates", [])
    total_price = context.user_data.get("final_price", 0)

    pdf_path = "receipt.pdf"
    
    # Регистрируем шрифт с поддержкой кириллицы
    pdfmetrics.registerFont(TTFont("DejaVuSans", "DejaVuSans.ttf"))

    # Генерация PDF
    c = canvas.Canvas(pdf_path, pagesize=letter)
    c.setFont("DejaVuSans", 12)
    c.drawString(100, 750, "Чек интернет-кафе")
    c.drawString(100, 730, "=============================")

    y = 700
    for item in selected_items:
        c.drawString(100, y, f"{item['name']}: {item['price']} сом")
        y -= 20

    c.drawString(100, y - 20, f"Итого за один день: {sum(item['price'] for item in selected_items)} сом")
    c.drawString(100, y - 40, f"Количество дней доставки: {len(delivery_dates)}")
    c.drawString(100, y - 60, f"Общая сумма: {total_price} сом")
    c.drawString(100, y - 80, f"Дни доставки: {', '.join(delivery_dates)}")
    c.drawString(100, y - 120, "Спасибо за ваш заказ!")

    c.save()
    return pdf_path

    
async def start(update: Update, context):
    text = (
        "Добро пожаловать в наше интернет-кафе!\n\n"
        "Здесь вы можете заказать напитки, горячие блюда, десерты и многое другое.\n\n"
        "Выберите, что хотите сделать:"
    )

    keyboard = [
        [InlineKeyboardButton("Продолжить", callback_data="continue")],
        [InlineKeyboardButton("Отмена", callback_data="cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(text, reply_markup=reply_markup)


async def handle_choice(update: Update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "continue":
        category_list = ", ".join(CATEGORIES.keys())
        await query.edit_message_text(
            "Вы выбрали: Продолжить. Ожидайте следующее сообщение..."
        )
        await query.message.reply_text(
            f"Отлично, вы можете выбрать что-то из этой категории: {category_list}.\n\n"
            "Напишите название категории вручную."
        )
    elif query.data == "cancel":
        await query.message.reply_text("Вы выбрали: Отмена. До свидания!")


async def handle_text(update: Update, context):
    # Проверяем, ожидается ли ввод email
    if context.user_data.get("awaiting_email"):
        email = update.message.text.strip()
        context.user_data["email"] = email
        context.user_data["awaiting_email"] = False  # Сбрасываем флаг
        delivery_dates = context.user_data.get("delivery_dates", [])
        selected_items = context.user_data.get("selected_items", [])
        total_price = context.user_data.get("final_price", 0)

        # Подключаемся к базе данных
        pool = await connect_to_db()

        # Сохраняем клиента
        client_id = await save_client(pool, email)

        # Сохраняем заказы для каждого дня
        for date in delivery_dates:
            if isinstance(date, str):
                date = datetime.strptime(date, "%d.%m.%Y").date()
            await save_order(pool, client_id, date, selected_items, total_price / len(delivery_dates))

        # Закрываем подключение
        await pool.close()

        pdf_path = generate_pdf_receipt(context)

        send_email_with_pdf(email, pdf_path)

        await update.message.reply_text(
            f"Чек был отправлен на ваш email: {email}. Спасибо за заказ! Если захотите еще что-нибудь заказать, введите /start."
        )
        return  # Выходим, чтобы избежать дальнейшей обработки текста

    # Если email не ожидается, продолжаем обработку как выбор категории
    user_input = update.message.text.strip()
    closest_match = get_close_matches(user_input, CATEGORIES.keys(), n=1, cutoff=0.6)

    if closest_match:
        chosen_category = closest_match[0]
        context.user_data["category"] = chosen_category  
        context.user_data["selected_items"] = []  
        await update.message.reply_text(
            f"Вы выбрали категорию: {chosen_category}.",
        )

        # Отправляем кнопки с элементами выбранной категории
        items = CATEGORIES[chosen_category]
        keyboard = [[InlineKeyboardButton(item, callback_data=f"test_item_{item}")] for item in items]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "Выберите один из следующих товаров:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "Извините, я не нашел подходящую категорию. Пожалуйста, выберите одну из: Напитки, Горячие блюда, Десерты."
        )



# Обработка выбора товара
async def handle_item_selection(update: Update, context):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("test_item_"):
        item_name = query.data.replace("test_item_", "")
        category = context.user_data.get("category")

        if category:
            price = CATEGORIES[category].get(item_name)

            if price:
                # Сохраняем выбранный товар в историю
                selected_items = context.user_data.setdefault("selected_items", [])
                selected_items.append({"name": item_name, "price": price})

                # Формируем сообщение с историей покупок
                items_list = "\n".join(
                    [f"{item['name']}: {item['price']} сом" for item in selected_items]
                )
                total_price = sum(item['price'] for item in selected_items)
                message = f"Вы выбрали товар: {item_name}\nЦена: {price} сом.\n\n" \
                          f"Ваши покупки:\n{items_list}\nИтого: {total_price} сом."

                # Отправляем сообщение
                await query.message.reply_text(message)

                # Показываем кнопки товаров и кнопку "Далее"
                items = CATEGORIES[category]
                keyboard = [[InlineKeyboardButton(item, callback_data=f"test_item_{item}")] for item in items]
                keyboard.append([InlineKeyboardButton("Далее", callback_data="next_step")]) 
                reply_markup = InlineKeyboardMarkup(keyboard)

                await query.message.reply_text(
                    "Выберите один из следующих товаров или нажмите 'Далее':",
                    reply_markup=reply_markup
                )
            else:
                await query.message.reply_text("Произошла ошибка, попробуйте снова.")
        else:
            await query.message.reply_text("Категория не выбрана. Попробуйте снова.")


# Обработка кнопки "Далее"
async def handle_next_step(update: Update, context):
    query = update.callback_query
    await query.answer()

    # Получаем список выбранных товаров
    selected_items = context.user_data.get("selected_items", [])

    if selected_items:
        # Формируем сообщение с итогами
        items_list = "\n".join(
            [f"{item['name']}: {item['price']} сом" for item in selected_items]
        )
        total_price = sum(item['price'] for item in selected_items)
        message = f"Ваши покупки:\n{items_list}\n\nИтого: {total_price} сом."

        await query.message.reply_text(message)

        keyboard = [[InlineKeyboardButton("Выбрать дни доставки", callback_data="choose_days")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.reply_text(
            "Теперь выберите дни доставки:",
            reply_markup=reply_markup
        )
    else:
        await query.message.reply_text("Вы ещё не выбрали товары. Пожалуйста, выберите хотя бы один.")

async def handle_choose_dates(update: Update, context):
    query = update.callback_query
    await query.answer()

    # Генерируем кнопки с датами, исключая сегодняшний день
    dates = generate_dates_for_month()
    keyboard = [[InlineKeyboardButton(date, callback_data=f"date_{date}")] for date in dates]

    keyboard.append([InlineKeyboardButton("Подтвердить", callback_data="confirm_dates")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.message.reply_text(
        "Выберите даты доставки (вы не можете выбрать сегодняшнюю дату):",
        reply_markup=reply_markup
    )


# Обработка выбора конкретной даты
async def handle_date_selection(update: Update, context):
    query = update.callback_query
    await query.answer()

    # Получаем выбранную дату
    selected_date = query.data.replace("date_", "")
    selected_dates = context.user_data.setdefault("delivery_dates", [])

    # Добавляем дату, если она еще не выбрана
    if selected_date not in selected_dates:
        selected_dates.append(selected_date)
        await query.message.reply_text(f"Вы выбрали дату: {selected_date}")
    else:
        await query.message.reply_text(f"Дата {selected_date} уже выбрана.")


# Обработка подтверждения выбора дат доставки
async def handle_confirm_dates(update: Update, context):
    query = update.callback_query
    await query.answer()

    # Получаем список выбранных дат
    selected_dates = context.user_data.get("delivery_dates", [])
    selected_items = context.user_data.get("selected_items", [])

    if selected_dates and selected_items:
        items_list = "\n".join(
            [f"{item['name']}: {item['price']} сом" for item in selected_items]
        )
        total_price = sum(item['price'] for item in selected_items)

        # Учитываем количество дней доставки
        days_count = len(selected_dates)
        full_price = total_price * days_count

        context.user_data["final_price"] = full_price

        dates_list = ", ".join(selected_dates)
        message = (
            f"Ваш заказ:\n{items_list}\n\n"
            f"Итого за один день: {total_price} сом.\n"
            f"Количество дней: {days_count}\n"
            f"Общая сумма: {full_price} сом.\n\n"
            f"Выбранные дни доставки: {dates_list}"
        )
#here
        keyboard = [
            [InlineKeyboardButton("Выполнить заказ", callback_data="confirm_order")],
            [InlineKeyboardButton("Отменить", callback_data="cancel_order")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.reply_text(message, reply_markup=reply_markup)
    else:
        await query.message.reply_text("Вы не выбрали товары или даты доставки.")


# Обработка выполнения заказа
async def handle_confirm_order(update: Update, context):
    query = update.callback_query
    await query.answer()

    await query.message.reply_text(
        "Пожалуйста, введите ваш email для получения чека."
    )

    # Устанавливаем флаг для следующего сообщения
    context.user_data["awaiting_email"] = True


# Обработка отмены заказа
async def handle_cancel_order(update: Update, context):
    query = update.callback_query
    await query.answer()

    # Сбрасываем данные пользователя
    context.user_data.clear()

    await query.message.reply_text("Ваш заказ отменён. Если захотите начать заново, введите /start.")


# Сохранение заказа в базу данных
async def handle_email_input(update: Update, context):
    if context.user_data.get("awaiting_email"):
        email = update.message.text.strip()
        context.user_data["email"] = email
        context.user_data["awaiting_email"] = False  # Сбрасываем флаг

        delivery_dates = context.user_data.get("delivery_dates", [])
        selected_items = context.user_data.get("selected_items", [])
        total_price = context.user_data.get("final_price", 0)

        pool = await connect_to_db()

        # Сохраняем клиента
        client_id = await save_client(pool, email)

        # Сохраняем заказы для каждого дня
        for date in delivery_dates:
            if isinstance(date, str):
                date = datetime.strptime(date, "%d.%m.%Y").date()
            await save_order(pool, client_id, date, selected_items, total_price / len(delivery_dates))

        await pool.close()
        
        pdf_path = generate_pdf_receipt(context)
        
        send_email_with_pdf(email, pdf_path)

        await update.message.reply_text(
            f"Чек был отправлен на ваш email: {email}. Спасибо за заказ!"
        )
    else:
        await update.message.reply_text("Пожалуйста, завершите текущий процесс перед вводом нового email.")



if __name__ == "__main__":
    app = ApplicationBuilder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()

    app.post_init = startup
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_choice, pattern="^(continue|cancel)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_next_step, pattern="^next_step$"))
    app.add_handler(CallbackQueryHandler(handle_item_selection, pattern="^test_item_"))
    app.add_handler(CallbackQueryHandler(handle_choose_dates, pattern="^choose_days$"))
    app.add_handler(CallbackQueryHandler(handle_date_selection, pattern="^date_"))
    app.add_handler(CallbackQueryHandler(handle_confirm_dates, pattern="^confirm_dates$"))
    app.add_handler(CallbackQueryHandler(handle_confirm_order, pattern="^confirm_order$"))
    app.add_handler(CallbackQueryHandler(handle_cancel_order, pattern="^cancel_order$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_email_input))


    print("Бот запущен!")
    app.run_polling()