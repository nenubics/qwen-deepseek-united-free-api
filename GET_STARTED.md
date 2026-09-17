# 🚀 Complete Beginner & Getting Started Guide

Welcome to the **Unified Qwen & DeepSeek Free API**! This guide walks you through setup in under 5 minutes, even if you have never run a local AI proxy before.

---

## 📑 Table of Contents
1. [What is this?](#-what-is-this)
2. [Prerequisites](#-prerequisites)
3. [5-Minute Quick Start](#-5-minute-quick-start)
   * [Method A: Docker (Recommended, zero setup)](#method-a-docker-recommended)
   * [Method B: Local Python](#method-b-local-python)
4. [Connecting Your Free Accounts](#-connecting-your-free-accounts)
   * [Method 1: 🍪 1-Click Auto-Cookie Import (Easiest)](#method-1--1-click-auto-cookie-import-easiest)
   * [Method 2: 📋 Copy-Paste Cookies or Token](#method-2--copy-paste-cookies-or-token)
   * [Method 3: 🌐 Interactive Browser Login](#method-3--interactive-browser-login)
5. [Connecting to Your Favorite Apps](#-connecting-to-your-favorite-apps)
   * [Cursor & Windsurf](#cursor--windsurf)
   * [Open WebUI](#open-webui)
   * [NextChat (ChatGPT-Next-Web)](#nextchat-chatgpt-next-web)
   * [Continue & Cline (VS Code)](#continue--cline-vs-code)
   * [Python & Node.js Code](#python--nodejs-code)
6. [Understanding 1-Chat Task Management](#-understanding-1-chat-task-management)
7. [Troubleshooting & FAQ](#-troubleshooting--faq)

---

## 💡 What is this?

This project unites **[FreeQwenApi](https://github.com/y13sint/FreeQwenApi)** and **[DeepSeek-Api-Free](https://github.com/zDEBRYrp/DeepSeek-Api-Free)** into a **single OpenAI-compatible API server**:

* **1 Unified API Key**: One key (`sk-unified-free-key`) works for all 34+ models.
* **Automatic Routing**: Mention `deepseek-*` and it uses DeepSeek. Mention `qwen-*` or `qwq-*` and it uses Qwen.
* **1-Chat Management**: System prompts and follow-up turns stay inside **1 clean chat thread** on `chat.qwen.ai` and `chat.deepseek.com`, eliminating duplicate chats.
* **Modern Dashboard**: A visual web interface at `http://localhost:8000/dashboard` with live chat playground, account manager, and cookie importer.

---

## 📋 Prerequisites

Before starting, ensure you have:
1. Either **[Docker Desktop](https://www.docker.com/products/docker-desktop/)** installed **OR** **Python 3.10+** (with `pip`).
2. A free account on:
   * **[chat.qwen.ai](https://chat.qwen.ai)** (for Qwen models)
   * **[chat.deepseek.com](https://chat.deepseek.com)** (for DeepSeek V3 / R1 reasoning)

---

## ⚡ 5-Minute Quick Start

### Method A: Docker (Recommended)
No local Python or browser dependencies required! Headless Chromium and `xvfb` run inside Docker automatically.

```bash
# 1. Clone the repository
git clone https://github.com/nenubics/qwen-deepseek-united-free-api.git
cd qwen-deepseek-united-free-api

# 2. Copy the environment configuration
cp .env.example .env

# 3. Start the container
docker compose up -d
```

Open your browser and navigate to:
👉 **`http://localhost:8000/dashboard`**

---

### Method B: Local Python

For macOS, Linux, or Windows:

```bash
# 1. Clone the repository
git clone https://github.com/nenubics/qwen-deepseek-united-free-api.git
cd qwen-deepseek-united-free-api

# 2. Create and activate a virtual environment (optional but recommended)
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies and Chromium
pip install -r requirements.txt
playwright install --with-deps chromium

# 4. Copy configuration
cp .env.example .env

# 5. Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser and navigate to:
👉 **`http://localhost:8000/dashboard`**

---

## 🔑 Connecting Your Free Accounts

The server needs your session to access free models. You can connect in any of these 3 easy ways:

### Method 1: 🍪 1-Click Auto-Cookie Import (Easiest)
If you have exported cookies or Netscape `cookies.txt`:

1. Install a free Chrome/Firefox extension such as **Get cookies.txt locally** or **Cookie-Editor**.
2. Visit `chat.deepseek.com` and `chat.qwen.ai` while logged in, and export your cookies to your Downloads folder.
3. Open the Dashboard -> **Accounts & Sessions** tab.
4. Click **"🔍 1-Click Auto-Scan"** (or run `python login.py --auto-cookies`).
5. The server automatically detects the files, decrypts the session, and activates your accounts!

---

### Method 2: 📋 Copy-Paste Cookies or Token

#### For Qwen:
1. Open [chat.qwen.ai](https://chat.qwen.ai) in your browser and log in.
2. Press `F12` (or `Cmd+Option+I` on Mac) to open DevTools.
3. Go to **Application** (or **Storage**) -> **Local Storage** -> `https://chat.qwen.ai`.
4. Copy the value of the key named **`token`** (starts with `eyJ...`).
5. In the Dashboard under **Accounts & Sessions** -> **Qwen Accounts**, paste it into **Paste Qwen JWT Token** and click **Add Token**!

#### For DeepSeek:
1. In the Dashboard under **Accounts & Sessions** -> **Auto-Cookie Importer**, paste your raw cookies string (e.g. `userToken=...; ds_session=...`).
2. Select target provider **DeepSeek** and click **Apply Cookies**.

---

### Method 3: 🌐 Interactive Browser Login

If you want the proxy to open a visible browser on your machine to sign in:

* **For Qwen**: Run `python login.py --qwen` (or click "Open Browser Login" in the dashboard).
* **For DeepSeek**: Run `python login.py --deepseek` (or click "Open Visible Browser for Login" in the dashboard).

Log in to the webpage in the browser window that opens. The script captures the session and closes the browser automatically!

---

## 📱 Connecting to Your Favorite Apps

All client software connects using the exact same standard OpenAI parameters:

* **Base URL**: `http://localhost:8000/v1`
* **API Key**: `sk-unified-free-key` (or the key you specified in your `.env`)

---

### Cursor & Windsurf
1. Open Cursor **Settings** -> **Models** -> **OpenAI API Key**.
2. Toggle **Override OpenAI Base URL**:
   * Set Base URL: `http://localhost:8000/v1`
   * Set API Key: `sk-unified-free-key`
3. Add the models you want to use in the models list:
   * `qwen3.7-max` (Coding & general tasks)
   * `deepseek-think` (R1 deep reasoning)
   * `qwen3-coder-plus` (Agentic code generation)

---

### Open WebUI
1. Open Open WebUI and log in as Admin.
2. Navigate to **Admin Panel** -> **Settings** -> **Connections** -> **OpenAI API**.
3. Click the **+** button to add a connection:
   * **URL**: `http://localhost:8000/v1` (or `http://host.docker.internal:8000/v1` if Open WebUI runs in Docker)
   * **Key**: `sk-unified-free-key`
4. Click **Verify Connection** & **Save**.
5. All 34+ models will automatically appear in your model selection dropdown!

---

### NextChat (ChatGPT-Next-Web)
1. Open NextChat **Settings**.
2. Set **Model Provider**: `OpenAI`.
3. Set **API URL (Base URL)**: `http://localhost:8000/v1`
4. Set **API Key**: `sk-unified-free-key`
5. Custom Models: `qwen3.7-max,deepseek-think,deepseek-chat,qwen3-coder-plus`

---

### Continue & Cline (VS Code)
Add this to your `config.json`:

```json
{
  "models": [
    {
      "title": "DeepSeek R1 (Free)",
      "provider": "openai",
      "model": "deepseek-think",
      "apiBase": "http://localhost:8000/v1",
      "apiKey": "sk-unified-free-key"
    },
    {
      "title": "Qwen 3.7 Max (Free)",
      "provider": "openai",
      "model": "qwen3.7-max",
      "apiBase": "http://localhost:8000/v1",
      "apiKey": "sk-unified-free-key"
    }
  ]
}
```

---

### Python & Node.js Code

#### Python (Official `openai` package):
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="sk-unified-free-key",
)

# Test Qwen:
response_qwen = client.chat.completions.create(
    model="qwen3.7-max",
    messages=[{"role": "user", "content": "Hello Qwen!"}],
)
print("Qwen:", response_qwen.choices[0].message.content)

# Test DeepSeek with R1 reasoning:
response_ds = client.chat.completions.create(
    model="deepseek-think",
    messages=[{"role": "user", "content": "Explain why 0.1 + 0.2 != 0.3 in IEEE 754 float."}],
)
print("DeepSeek:", response_ds.choices[0].message.content)
```

#### Node.js / TypeScript:
```typescript
import OpenAI from "openai";

const openai = new OpenAI({
  baseURL: "http://localhost:8000/v1",
  apiKey: "sk-unified-free-key",
});

async function main() {
  const completion = await openai.chat.completions.create({
    model: "qwen3.7-max",
    messages: [{ role: "user", content: "Hello from Node.js!" }],
  });
  console.log(completion.choices[0].message.content);
}
main();
```

---

## 🧵 Understanding 1-Chat Task Management

Normally, calling OpenAI-compatible APIs causes **chat fragmentation**: standard clients send full chat history without upstream IDs, causing typical proxies to spawn a brand new chat on `chat.qwen.ai` and `chat.deepseek.com` on every single follow-up prompt.

### How this project solves it:
1. **Automatic Theme Fingerprinting**: Your system prompt and initial task are hashed. All consecutive prompts with the same context stay in **1 unified chat thread**.
2. **Clean Web UI**: When you open `chat.qwen.ai` or `chat.deepseek.com`, you will see clean single threads for each task rather than hundreds of single-message fragments.
3. **Starting a New Chat**:
   * In the Dashboard: Click the **"➕ New Task / Topic"** button above the chat box.
   * In API code: Pass `"new_chat": true` in your request body.
   * In Dashboard **Tasks & Chats** tab: Inspect, switch between, or delete tracked sessions anytime.

---

## ❓ Troubleshooting & FAQ

### 1. "DeepSeek is showing Cloudflare verification (captcha)"
* **Cause**: Cloudflare occasionally triggers verification checks.
* **Solution**: Click "Open Visible Browser for Login" in the dashboard, complete the verification checkbox in the browser window, and you're good to go!

### 2. "Port 8000 is already in use"
* Change `PORT=8000` to `PORT=8080` in `.env` and restart the server (`uvicorn app.main:app --port 8080`).

### 3. "No active Qwen accounts found"
* Follow [Method 1 (Cookie Scan)](#method-1--1-click-auto-cookie-import-easiest) or [Method 2 (Token Paste)](#method-2--copy-paste-cookies-or-token) to add your account. You can verify it works by clicking "Verify" in the dashboard.

### 4. "Can I change or disable the API Key?"
* Yes! In `.env`, set `API_KEY=your-custom-key`. If you want to disable authentication entirely for local use, leave `API_KEY=` blank. You can also update the key live in the Dashboard **API Key & Settings** tab.

---

🎉 **You are now completely set up! Enjoy unlimited free access to Qwen & DeepSeek models!**
