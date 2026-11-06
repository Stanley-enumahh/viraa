# Vira

Vira is a voice assistant for crypto. Say what you want, Vira drafts the request, and nothing happens until you click approve.

Built for the Roqqu hackathon. **All prices, balances and transactions are simulated.** No real funds or Roqqu services are involved.

## Status

| Batch | Scope | State |
|---|---|---|
| 1 | Backend foundation and auth | Done |
| 2 | Market simulator | Done |
| 3 | Wallets and transactions | Done |
| 4 | Voice backend (Claude, ElevenLabs, drafts and approval) | Done |
| 5 | Next.js frontend foundation | Done |
| 6 | Voice interface | Done |
| 7 | Demo polish | Planned |

## Run the backend

Requires Python 3.14. From the `backend` folder, on Windows:

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

In `.env`, set `DJANGO_SECRET_KEY` to a long random string, and add `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` for voice features. Then:

```bash
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py runserver
```

The API runs at `http://127.0.0.1:8000/api/`.

Run the tests with:

```bash
.venv\Scripts\python.exe manage.py test
```

## Run the frontend

Requires Node.js 22. Keep the backend running, then from the `frontend` folder:

```bash
npm install
npm run dev
```

Open `http://localhost:3000`. To use a backend somewhere else, set `NEXT_PUBLIC_API_URL`, for example to `https://your-backend.example/api`.

## Hosting

The database runs on Aiven (PostgreSQL), the backend on Render, and the frontend on Vercel.

| Host | Setting | Value |
|---|---|---|
| Render | Root directory | `backend` |
| Render | Build command | `pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate` |
| Render | Start command | `gunicorn config.wsgi:application --worker-class gthread --workers 1 --threads 8 --timeout 90` |
| Render | Health check path | `/api/health/` |
| Render | Environment | `DATABASE_URL`, `DJANGO_SECRET_KEY`, `CORS_ALLOWED_ORIGINS`, `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` |
| Vercel | Root directory | `frontend` |
| Vercel | Environment | `NEXT_PUBLIC_API_URL`, ending in `/api` |

## API

Endpoints need an `Authorization: Bearer <access token>` header unless marked public.

### Auth

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/auth/register/` | Create an account with starting funds (public) |
| POST | `/api/auth/login/` | Get tokens with email and password (public) |
| POST | `/api/auth/refresh/` | Get a new access token (public) |
| GET | `/api/auth/me/` | Current user |

### Market (public)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/market/prices/` | All coins; prices update every 5 seconds |
| GET | `/api/market/prices/<symbol>/` | One coin |
| GET | `/api/market/prices/<symbol>/history/?range=24h` | Chart data; ranges are `1h`, `24h`, `7d` and `30d` |

### Wallets

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/wallets/` | Balances and portfolio value |
| GET | `/api/wallets/networks/` | Networks and current fees for each coin |
| POST | `/api/wallets/trades/quote/` | Price a buy, sell or swap without executing it |
| POST | `/api/wallets/trades/` | Execute a buy, sell or swap |
| POST | `/api/wallets/send/quote/` | Price a send without executing it |
| POST | `/api/wallets/send/` | Send to a Vira username or an external address |
| GET | `/api/wallets/transactions/` | History; filter with `kind`, `asset` and `limit` |
| GET | `/api/wallets/transactions/<reference>/` | One transaction |

A trade takes `kind`, `from_asset`, `to_asset` and `amount`. Add `amount_asset` to give the amount in the asset being received:

```json
{ "kind": "buy", "from_asset": "NGN", "to_asset": "BTC", "amount": "20000" }
```

A send takes `asset`, `amount`, either `recipient` or `address`, and `network` for a coin with more than one:

```json
{ "asset": "USDT", "amount": "50", "recipient": "tunde", "network": "TRC20" }
```

### Customers

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/customers/` | Your saved customers |
| POST | `/api/customers/` | Save a Vira user by `username` |
| GET | `/api/customers/lookup/?username=` | See whose username it is before saving |
| DELETE | `/api/customers/<id>/` | Remove a customer |

Refused requests return HTTP 400 with a message that can be shown to the user:

```json
{ "detail": "You need 99,000,000 NGN but only have 480,000.", "code": "insufficient_funds" }
```

### Assistant

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/assistant/voice/` | Send a recording as multipart field `audio`; returns the transcript and result. Add `wake_word=true` for hands-free mode |
| POST | `/api/assistant/command/` | Send typed `text`; returns the same result |
| POST | `/api/assistant/speak/` | Send `text`; returns MP3 audio of Vira's reply |
| GET | `/api/assistant/drafts/` | Recent drafts |
| POST | `/api/assistant/drafts/` | Lock the price for a buy, sell or swap from the Trade page; takes the same fields as a trade |
| POST | `/api/assistant/drafts/send/` | Prepare a send for approval from the Customers page; takes the same fields as a send |
| GET | `/api/assistant/drafts/<reference>/` | One draft |
| POST | `/api/assistant/drafts/<reference>/approve/` | Execute a draft at its locked price |
| POST | `/api/assistant/drafts/<reference>/reject/` | Cancel a draft |

`voice` and `command` return:

```json
{
  "transcript": "buy 20k naira of bitcoin",
  "type": "draft",
  "reply": "Buy 0.0001341 BTC with 20,000 NGN, including a 100 NGN fee. Tap approve to confirm.",
  "parser": "claude",
  "draft": { "reference": "...", "status": "pending", "expires_at": "...", "quote": {} },
  "data": null
}
```

`type` is `draft` (show approve and reject), `answer`, `question` (Vira needs more detail, and the next command continues the conversation), `refused`, `listening` (the user only said "hey Vira") or `ignored`.

With `wake_word=true`, speech that doesn't start with "Vira" or "hey Vira" returns `ignored`. It isn't stored or sent to Claude.

### How approval stays safe

- Claude only describes what the user asked for. It has no way to execute anything.
- Our code checks the request, prices it and writes the reply, so spoken amounts match what will happen.
- Funds move only when the draft's owner calls the approve endpoint. Saying "yes" never approves.
- Drafts lock the price for 60 seconds, and a double click executes only once.
- If Claude can't be reached, a rule-based parser keeps the main commands working.

## Simulated rules

- New users start with 500,000 NGN, 250 USDT, 0.005 BTC, 0.1 ETH and 2 SOL.
- Trades cost 0.5%, taken from the amount paid.
- Crypto sends go on a chosen network, which sets a made-up fee: USDT costs the equivalent of $1 on TRON, $0.30 on BNB Chain and $5 on Ethereum. Other coins have one network each.
- Naira has no network. It only moves between Vira users, for free.
