# Unified Qwen & DeepSeek Free API

> **Unite [FreeQwenApi](https://github.com/y13sint/FreeQwenApi) and [DeepSeek-Api-Free](https://github.com/zDEBRYrp/DeepSeek-Api-Free) into a single high-performance OpenAI-compatible server with 1 Unified API Key, automatic model routing, multi-account rotation, and a built-in modern Dashboard.**

---

## 🚀 Key Features

* 🔑 **1 API Key for Everything**: Use a single `Authorization: Bearer <API_KEY>` for all models across both providers. No separate ports, separate proxies, or token juggling.
* 🤖 **Automatic Model Routing**: Send requests to `/v1/chat/completions` with any model name:
  * **DeepSeek Models** (`deepseek-chat`, `deepseek-think`, `deepseek-reasoner`, `deepseek-r1`, `deepseek-search`) automatically route to the persistent DeepSeek browser automation pool.
  * **Qwen Models** (`qwen3.7-max`, `qwen3.7-plus`, `qwen3-coder-plus`, `qwq-32b`, `qvq-72b`, etc.) automatically route to the high-speed Qwen direct API stream.
* 🖥️ **Built-in Modern Dashboard (`/dashboard`)**:
  * **Live AI Playground**: Test streaming responses, collapsible DeepThink reasoning accordion (`reasoning_content`), and web search citations in real time.
  * **Account Manager**: Visual dashboard for Qwen Bearer tokens and DeepSeek browser profiles with live status, cooldown timers, and manual addition.
  * **Model Catalog**: Complete reference of all 34+ models, capabilities (Chat, Reasoning, Code, Vision, Search), and aliases.
  * **Text-to-Image Studio**: Generate images directly using Qwen Wanx (`/v1/images/generations`).
* 🔄 **Multi-Account Rotation & Health Checks**:
  * Qwen multi-token round-robin with automatic rate-limit detection and cooldown queuing.
  * DeepSeek multi-profile browser session pool with shared context tabs and SQLite encryption.
* ⚡ **100% OpenAI Compatible**:
  * Works out-of-the-box with **Open WebUI**, **Cursor**, **Continue**, **NextChat**, **LangChain**, **LlamaIndex**, and the official `openai` Python/Node SDKs.
* 🐳 **Production-Ready Deployment**:
  * Run locally with Python 3.11+, or run via **Docker** and **Docker Compose** with headless Chromium and `xvfb`.

---

## 📐 Architecture

```text
                               +------------------------------------------+
                               |        Client / Open WebUI / Cursor      |
                               +------------------------------------------+
                                                    |
                                    Authorization: Bearer <API_KEY>
                                                    v
                               +------------------------------------------+
                               |     Unified FastAPI Server (Port 8000)   |
                               |    - Security & Single API Key Auth      |
                               |    - Rate Limiter & CORS                 |
                               |    - Built-in Dashboard (/dashboard)     |
                               +------------------------------------------+
                                                    |
                                         detect_provider(model)
                                        /                      \
             If model is "deepseek-*"  /                        \  If model is "qwen-*" or "qwq-*"
                                      v                          v
                      +-----------------------------+   +-----------------------------+
                      |   DeepSeek Provider Engine  |   |    Qwen Provider Engine     |
                      | - Playwright Browser Pool   |   | - Direct Async HTTP Client  |
                      | - Multi-Profile Isolation   |   | - Multi-Token Rotation      |
                      | - DeepThink Reasoning Extr. |   | - Auto Cooldown Recovery    |
                      | - SQLite Fernet Encryption  |   | - Image Generation (t2i)    |
                      +-----------------------------+   +-----------------------------+
                                      |                                  |
                                      v                                  v
                             chat.deepseek.com                   chat.qwen.ai
```

---

## 🛠️ Quick Start

### 1. Installation

Clone the repository and install dependencies:

```bash
cd qwen-deepseek-api
pip install -r requirements.txt
playwright install --with-deps chromium
```

### 2. Configuration

Copy the example environment file:

```bash
cp .env.example .env
```

Open `.env` and set your desired unified API key:

```env
# Unified API Key used by all clients and tools
API_KEY=sk-unified-free-key

# Default fallback model
DEFAULT_MODEL=qwen3.7-max

# Server binding
HOST=0.0.0.0
PORT=8000
```

### 3. Account Authorization

Use the included `login.py` CLI to authorize your accounts:

#### Check current accounts status
```bash
python login.py --status
```

#### Add Qwen Account
* **Option A: Interactive Browser Login** (opens a browser, sign in, token detected and saved automatically):
  ```bash
  python login.py --qwen
  ```
* **Option B: Direct Token Paste** (copy `token` from `chat.qwen.ai` DevTools -> Application -> Local Storage):
  ```bash
  python login.py --qwen-token "eyJhbGciOi..."
  ```

#### Add DeepSeek Profile
* Opens a browser to sign in to `chat.deepseek.com` and saves persistent session cookies to encrypted storage:
  ```bash
  python login.py --deepseek
  ```
* For multi-account pool, specify profile name:
  ```bash
  python login.py --deepseek --profile account2
  ```

#### 🍪 Auto-Cookie Adding (Zero Manual Setup)
You can import cookies automatically in any format (Raw HTTP `Cookie:` header, Netscape `cookies.txt`, or JSON array from extensions):

* **1-Click Auto-Scan** (scans your Downloads folder and workspace for exported cookie files):
  ```bash
  python login.py --auto-cookies
  ```
* **Import from File**:
  ```bash
  python login.py --cookie-file ~/Downloads/cookies.txt
  ```
* **Paste Raw Cookie String or Header**:
  ```bash
  python login.py --add-cookies "userToken=xyz...; ds_session=abc..."
  ```
* **Via Dashboard (`/dashboard`)**:
  Go to the **Accounts & Sessions** tab and use the built-in **Auto-Cookie Importer** (supports direct paste, drag & drop file upload, or the 1-click Auto-Scan button).

### 4. Start the Server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser and visit:
👉 **`http://localhost:8000/dashboard`**

---

## 🐳 Docker Deployment

You can run the entire unified stack in Docker without installing Python or browser binaries locally:

```bash
# Start container in background
docker compose up -d

# View server logs
docker compose logs -f
```

To run interactive login inside Docker:
```bash
docker compose exec qwen-deepseek-api python login.py --status
```

---

## 📋 Supported Models & Routing

List all models dynamically via `python login.py --list-models` or `GET /v1/models`.

### DeepSeek Models (Routed to Browser Automation Engine)

| Model Name | DeepThink Reasoning | Web Search | Description |
| :--- | :---: | :---: | :--- |
| `deepseek-chat` | ❌ | ❌ | Standard fast dialogue and generation |
| `deepseek-think` | ✅ | ❌ | Chain-of-thought with `reasoning_content` |
| `deepseek-reasoner` | ✅ | ❌ | Official API alias for `deepseek-think` (R1) |
| `deepseek-r1` | ✅ | ❌ | Alias for DeepSeek R1 reasoning |
| `deepseek-search` | ❌ | ✅ | Live web search with citation sources |
| `deepseek-think-search` | ✅ | ✅ | Combined DeepThink reasoning + Web Search |

### Qwen Models (Routed to High-Speed Direct Stream Engine)

| Model Name | Capabilities | Description |
| :--- | :---: | :--- |
| `qwen3.7-max` *(Default)* | Chat, Reasoning | Flagship top-intelligence Qwen model |
| `qwen3.7-plus` | Chat | High-efficiency balanced 3.7 tier |
| `qwen3.6-plus` | Chat | High capability generation model |
| `qwen3.5-plus` / `qwen3.5-flash` | Chat | Low-latency everyday assistant models |
| `qwen3-coder-plus` | Code, Chat | Specialized coding & refactoring assistant |
| `qwq-32b` | Reasoning | Specialized open reasoning rivaling o1 |
| `qvq-72b-preview-0310` | Vision, Reasoning | Multimodal visual reasoning |
| `qwen3-vl-plus` | Vision, Chat | Vision-language multimodal model |
| `qwen2.5-coder-32b-instruct` | Code, Chat | Open code instruction model |
| `qwen2.5-72b-instruct` | Chat | Open 72B instruction model |

### Model Aliases
Convenient shorthand aliases are automatically mapped:
* `qwen` -> `qwen3.7-max`
* `qwen-plus` -> `qwen3.7-plus`
* `qwen-coder` -> `qwen3-coder-plus`
* `qwq` -> `qwq-32b`
* `deepseek-reasoner` / `deepseek-r1` -> `deepseek-think`

---

## 🔌 Client Integrations

All clients connect to a **single endpoint URL** with your **single API key**.

### 1. Python `openai` SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="sk-unified-free-key",  # Your API_KEY from .env
)

# Call DeepSeek with DeepThink Reasoning:
response = client.chat.completions.create(
    model="deepseek-reasoner",
    messages=[{"role": "user", "content": "Explain quantum entanglement in simple terms."}],
    stream=True,
)

for chunk in response:
    # DeepSeek R1 reasoning output
    if hasattr(chunk.choices[0].delta, "reasoning_content") and chunk.choices[0].delta.reasoning_content:
        print(f"[Think]: {chunk.choices[0].delta.reasoning_content}", end="")
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")

# Call Qwen 3.7 Max with the same client:
qwen_response = client.chat.completions.create(
    model="qwen3.7-max",
    messages=[{"role": "user", "content": "Write a FastAPI route for uploading images."}],
)
print(qwen_response.choices[0].message.content)
```

### 2. cURL Examples

#### Non-streaming Chat Completion
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-unified-free-key" \
  -d '{
    "model": "qwen3.7-max",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

#### Streaming DeepSeek R1 Reasoning
```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-unified-free-key" \
  -d '{
    "model": "deepseek-reasoner",
    "messages": [{"role": "user", "content": "Solve the Monty Hall problem."}],
    "stream": true
  }'
```

#### Image Generation (Wanx Text-to-Image)
```bash
curl -X POST http://localhost:8000/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-unified-free-key" \
  -d '{
    "prompt": "A futuristic cybernetic laboratory in neon colors, 8k",
    "size": "1024x1024"
  }'
```

### 3. Open WebUI Setup
1. Open **Open WebUI** Settings -> **Connections** -> **OpenAI API**.
2. Set **API Base URL**: `http://localhost:8000/v1` (or `http://host.docker.internal:8000/v1` if in Docker).
3. Set **API Key**: `sk-unified-free-key`.
4. Click **Verify Connection** and all 34+ Qwen & DeepSeek models will appear in your model dropdown!

### 4. Cursor / VS Code (Continue / Cline) Setup
* **Base URL**: `http://localhost:8000/v1`
* **API Key**: `sk-unified-free-key`
* **Model**: `qwen3-coder-plus` or `deepseek-reasoner`

---

## 🧵 Intelligent Chat & Task Management (1 Chat per Task/Theme)

In traditional OpenAI proxies, follow-up messages cause massive chat fragmentation: because standard OpenAI `/v1/chat/completions` clients send full message history without passing upstream conversation IDs, the backend would create a brand new chat on `chat.qwen.ai` and `chat.deepseek.com` on every single turn.

This service introduces **Intelligent Task & Chat Affinity**:

* 🎯 **Theme & Task Fingerprinting**: System prompts and follow-up prompts sharing the same core task are hashed into a persistent fingerprint (`task_hash`). Follow-up questions automatically continue in the **exact same upstream chat thread**.
* 🔄 **Upstream Conversation State**:
  * **Qwen**: Retains the `chat_id` and advances `parent_id` (the `response_id` of previous assistant answers), keeping conversations neatly organized on `chat.qwen.ai`.
  * **DeepSeek**: Locks the browser automation page to the persistent chat session URL (`/a/chat/s/{chat_id}`), appending turns directly to the existing thread on `chat.deepseek.com`.
* ➕ **Explicit New Chat Control**:
  * Pass `"new_chat": true` (or `"newChat": true`) in your completion request payload to deliberately begin a clean thread.
  * Send `X-Conversation-Id: <ID>` or pass `"conversation_id": "<ID>"` to explicitly target a thread.
* 🖥️ **Dashboard & REST Management**:
  * `GET /api/chats`: Inspect all active managed chat threads, turn counters, upstream chat IDs, and last activity timestamps.
  * `POST /api/chats/new`: 1-click reset of active task affinity.
  * `POST /api/chats/{task_id}/active`: Reactivate an older thread.
  * `DELETE /api/chats/{task_id}`: Remove thread from registry.
  * **Interactive Chat Playground**: Features a live `🧵 Current Thread` indicator and a `➕ New Task / Topic` button.

---

## 📊 Modern Dashboard Overview

Navigate to `http://localhost:8000/dashboard` to access:

1. **Dashboard KPI Bar**: Real-time view of active accounts, total supported models, server uptime, and system status.
2. **Interactive Chat Playground**:
   * Switch between any Qwen and DeepSeek model on the fly.
   * Full SSE streaming output.
   * Expandable **DeepThink Reasoning accordion** displaying live chain-of-thought tokens.
   * Real-time search citations indicator.
3. **Accounts & Sessions Tab**:
   * Inspect all Qwen JWT tokens, expiration times, and active cooldown status.
   * Quick-add Bearer tokens via modal.
   * Inspect DeepSeek browser profile directories.
4. **Models Catalog Tab**:
   * Search and filter through all 34 models.
   * Capability tags (`Reasoning`, `Code`, `Vision`, `Search`).
5. **Image Generator Studio**:
   * Create artwork with prompt input, aspect ratio selection, and instant preview.

---

## ⚙️ Environment Configuration Reference

| Variable | Default | Description |
| :--- | :--- | :--- |
| `API_KEY` | `sk-unified-free-key` | **Single unified API key** for all client requests |
| `DEFAULT_MODEL` | `qwen3.7-max` | Model used when `model` is omitted in request |
| `HOST` | `0.0.0.0` | Server bind host address |
| `PORT` | `8000` | Server listening port |
| `ALLOWED_ORIGINS` | `*` | CORS allowed origins (comma-separated) |
| `HEADLESS` | `true` | Run DeepSeek browser automation in headless mode |
| `USER_DATA_DIR` | `./data/pw_profile` | Directory for persistent DeepSeek browser session |
| `SESSION_DIR` | `./session` | Directory storing Qwen tokens (`tokens.json`) |
| `RATE_LIMIT_PER_MINUTE` | `120` | Requests per minute allowed per client IP |
| `POOL_COOLDOWN_SECONDS` | `300` | Cooldown period when a provider session hits a limit |
| `TABS_PER_PROFILE` | `1` | Number of concurrent tabs per browser profile |

---

## ⚖️ Legal Notice & Why This Project Is Lawful

This project is an open-source research and interoperability adapter created to provide a standard OpenAI-compatible API interface for user-authorized accounts. It operates strictly within well-established international legal frameworks governing software interoperability, reverse engineering, and personal fair use.

### 1. Right to Interoperability & Protocol Adaptation
* **United States Law (17 U.S.C. § 1201(f))**: The Digital Millennium Copyright Act (DMCA) contains explicit exemptions allowing reverse engineering, protocol analysis, and the creation of interface adapters when performed solely for the purpose of enabling **interoperability** between independently created computer programs and existing platforms.
* **Judicial Precedent (*Google LLC v. Oracle America, Inc.*, 2021 & *Sega v. Accolade*, 1992)**: The United States Supreme Court affirmed that software interfaces and functional declarations exist to foster compatibility, and reimplementing functional protocol interfaces to allow programs to speak to each other constitutes protected **Fair Use**.
* **European Union Law (Directive 2009/24/EC, Article 6)**: The EU Software Directive guarantees developers the right to inspect, analyze, and translate protocol interfaces without the rights holder's prior consent, provided it is strictly necessary to achieve interoperability with an independently created program.

### 2. No Circumvention of Paywalls or DRM Controls
* **Zero Access Bypass**: This tool does **not** crack, bypass, or circumvent any encryption, paywall, access control, or Digital Rights Management (DRM) mechanisms.
* **User-Authorized Sessions**: The software cannot operate without valid credentials or session tokens actively belonging to the end-user. It functions simply as a localized automated user agent (analogous to a custom browser or web automation script) acting on direct command of the authenticated user.
* **Zero Credential Sharing**: This project is not a hosted public proxy. All session tokens, cookies, and encryption keys are stored exclusively on the user's local machine inside private SQLite and JSON files.

### 3. Non-Commercial Educational & Research Scope
* This software is distributed completely free of charge under the open-source **MIT License** for academic research, personal workflow automation, and compatibility testing.
* It is not a commercial product, does not sell or broker API access, and does not charge any fees for third-party compute or intelligence services.

### 4. Platform Respect & Responsible Fair Usage
* Users remain responsible for their individual usage and are encouraged to abide by the respective Terms of Service, Acceptable Use Policies, and guidelines of Alibaba Cloud (Qwen) and DeepSeek.
* The built-in request queuing, cooldown tracking, and rate limiters are explicitly engineered to maintain polite traffic patterns and avoid server strain.
* **Nominative Fair Use**: All product names, trademarks, and registered marks (including "DeepSeek", "Qwen", "Alibaba", "OpenAI") belong to their respective holders. Their use in this documentation and codebase is strictly nominative to describe software compatibility and functional interoperability.

---

## 📄 License

MIT License. Developed for seamless unified AI inference.
