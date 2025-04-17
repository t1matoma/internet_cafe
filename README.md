# Telegram Cafe Bot  
**A Telegram bot for ordering food/drinks with scheduled delivery.**  
Features:  
- Browse menu by categories (drinks, hot meals, desserts).  
- Select delivery dates (excluding the current day).  
- Receive PDF receipts via email.  
- PostgreSQL database integration for orders.  

## Technologies  
- **Python 3.10+**  
- **Aiogram 3.x** (async Telegram Bot API framework)  
- **PostgreSQL** (orders, clients, menu storage)  
- **ReportLab** (PDF receipt generation)  
- **SMTP** (email sending)  

---

##  Setup & Launch  

### 1. Clone the repository  
```bash
git clone https://github.com/t1matoma/internet_cafe.git
cd internet_cafe
```

### 2. Configure environment  
Create `.env` file (see `.env.example`):  
```ini
BOT_TOKEN=your_bot_token_from_BotFather
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_EMAIL=your@gmail.com
SMTP_PASSWORD=yourpassword
DB_HOST=localhost
DB_USER=username
DB_PASSWORD=yourdbpassword
DB_NAME=tg_cafe_bot
```

### 2. Create virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
.\.venv\Scripts\activate   # Windows
```

### 3. Install dependencies  
```bash
pip3 install -r requirements.txt
```

### 4. Run the bot  
```bash
python3 main.py
```

---

## Admin Panel 
**Web interface for managing menu/orders**:  
→ [Admin Panel Repository](https://github.com/t1matoma/admin_panel_for_tg_cafe_bot)  

**Features:**  
- Add/edit categories and products.  
- View orders (date, client, items).  
- Filter orders by date.  

**Key Notes:**  
- Connects to the **same PostgreSQL DB** as the Telegram bot.  
- Menu changes in the admin panel **instantly reflect** in the bot.  

---

## Bot Commands & Flow  
- **Commands:**  
  - `/start` — begin order.  
  - `/cancel` — cancel current order.  

- **Order process:**  
  1. Select a category (e.g., "Drinks").  
  2. Choose items (inline buttons).  
  3. Pick delivery dates (up to 30 days ahead).  
  4. Confirm order and enter email.  
  5. Receive PDF receipt via email.  
