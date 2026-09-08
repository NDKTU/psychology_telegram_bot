# 🌿 Psychology Telegram Bot System (Client & Worker)

A dual-bot Telegram system designed for psychological support, counseling, and customer interaction:
1. **`client_bot`**: The public-facing bot where clients send inquiries, messages, and voice notes.
2. **`worker_bot`**: The specialist-facing bot where psychologists and operators receive incoming client inquiries and can reply directly to them.

---

## 📁 Project Structure

```
psychology_telegram_bot/
├── .env                  # Your private bot tokens and settings (ignored by git)
├── .env.example          # Template configuration
├── requirements.txt      # Dependencies (aiogram, aiosqlite, etc.)
├── run.py                # Main script to run both bots simultaneously
├── run_client.py         # Standalone runner for client_bot only
├── run_worker.py         # Standalone runner for worker_bot only
├── common/               # Shared logic
│   ├── config.py         # Settings & environment validation
│   ├── database.py       # Async SQLite database (mappings, clients, workers)
│   └── models.py         # Data structures
├── client_bot/           # Client-facing bot logic
│   ├── bot.py            # Bot & Dispatcher setup
│   └── handlers.py       # Client handlers & message forwarding
├── worker_bot/           # Worker-facing bot logic
│   ├── bot.py            # Bot & Dispatcher setup
│   └── handlers.py       # Worker authorization, reply routing, and controls
└── data/                 # SQLite storage (bot.db generated automatically)
```

---

## 🚀 Quick Setup Guide

### Step 1: Create Telegram Bots via [@BotFather](https://t.me/botfather)

1. Open Telegram and search for `@BotFather`.
2. **Create Client Bot**:
   - Send `/newbot`.
   - Name it (e.g., `Psychology Support Bot`).
   - Give it a username ending in `bot` (e.g., `my_psy_client_bot`).
   - Copy the **HTTP API Token** provided.
3. **Create Worker Bot**:
   - Send `/newbot` again.
   - Name it (e.g., `Psychology Team Console`).
   - Give it a username (e.g., `my_psy_worker_bot`).
   - Copy this second **HTTP API Token**.

---

### Step 2: Configure Environment Variables

Open `.env` in this directory (or copy from `.env.example`) and fill in your tokens:

```env
# 1. Token for client_bot
CLIENT_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ

# 2. Token for worker_bot
WORKER_BOT_TOKEN=987654321:ZYXwvuTsRQPonMLkJIhGfeDCBA

# 3. Specialist / Admin Login & Password
#    Workers enter these in worker_bot to authorize and receive client messages
ADMIN_LOGIN=admin
ADMIN_PASSWORD=admin12345

# 4. PostgreSQL Database Settings (used automatically in Docker Compose)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=psychology_bot
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/psychology_bot

# 5. Fallback SQLite path (used when running standalone without Docker)
DATABASE_PATH=data/bot.db
```

---

### Step 3: Install Dependencies

Activate the pre-configured virtual environment:
```bash
# On Linux / macOS:
source .venv/bin/activate

# Install dependencies if not already installed:
pip install -r requirements.txt
```

---

### Step 4: Run the Bots

#### Option A: Using Docker Compose (Recommended for Production)

Start both `client_bot` and `worker_bot` in the background:
```bash
docker compose up -d
```

View logs:
```bash
# All logs
docker compose logs -f

# Worker bot logs only
docker compose logs -f worker_bot

# Client bot logs only
docker compose logs -f client_bot
```

Stop the containers:
```bash
docker compose down
```

#### Option B: Running Directly with Python

Run both bots concurrently using a single command:
```bash
python run.py
```

Or run each bot separately in individual terminals:
```bash
# Terminal 1:
python run_client.py

# Terminal 2:
python run_worker.py
```

---

## 💬 How It Works

1. **Specialist Login in `worker_bot`**:
   - Open `worker_bot` and press `/start`.
   - The bot prompts for your **Admin Login** and **Password** (or send `/login admin admin12345`).
   - Once logged in, your account is active and will immediately receive all incoming client messages!
   - To finish a shift and stop receiving messages, send `/logout`.

2. **Client Interaction**:
   - A client opens `client_bot` and presses `/start`.
   - The client sends a text message, voice note, photo, or document.
   - The bot acknowledges receipt: `✅ Your message has been received. A specialist will answer you soon.`

3. **Specialist Notification**:
   - The inquiry is delivered directly to all logged-in specialists in `worker_bot`:
     ```text
     📩 New message from Client
     👤 Name: John Doe
     🆔 Client ID: 123456789
     🔗 Username: @johndoe

     💬 Message:
     Hello, I have been feeling very stressed lately...
     [ ✍️ Reply to Client ]
     ```

3. **Replying to the Client (3 convenient options)**:
   - **Option 1 (Fastest):** Use Telegram's standard **Reply** feature directly on the forwarded message. Type your answer (or record a voice note) and send.
   - **Option 2:** Click the **[ ✍️ Reply to Client ]** inline button. The bot will prompt you to enter your answer.
   - **Option 3:** Send `/reply <client_id> <your response>`.

4. **Client Receives Answer**:
4. **Client Receives Answer & Status Transition**:
   - The answer is transmitted immediately to the client in `client_bot`:
     ```text
     💬 Response from Specialist:

     Hello John, take a deep breath. We are here to support you...
     ```
   - The database status changes from `not_answered` to **`answered`**, and records:
     - `answered_by`: Worker user ID
     - `answer_text`: Content of the response
     - `answered_at`: Exact timestamp
   - The specialist receives a delivery confirmation: `✅ Delivered to client (ID: 123456789)`.

5. **Viewing Unanswered Inquiries**:
   - Specialists can type `/unanswered` in `worker_bot` anytime to list all inquiries that have not received an answer yet.

