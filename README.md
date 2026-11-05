# Vira

Vira is a voice assistant for crypto. Say what you want, Vira drafts the request, and nothing happens until you click approve.

Built for the Roqqu hackathon. **All prices, balances and transactions are simulated.** No real funds or Roqqu services are involved.

## Status

| Batch | Scope | State |
|---|---|---|
| 1 | Backend foundation and auth | Done |
| 2 | Market simulator | Done |
| 3 | Wallets and transactions | Done |
| 4 | Voice backend (Claude, ElevenLabs, drafts and approval) | Planned |
| 5 | Next.js frontend foundation | Planned |
| 6 | Voice interface | Planned |
| 7 | Demo polish | Planned |

## Run the backend

Requires Python 3.14. From the `backend` folder, on Windows:

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
```

Set `DJANGO_SECRET_KEY` in `.env` to a long random string, then:

```bash
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py runserver
```

The API runs at `http://127.0.0.1:8000/api/`.

Run the tests with:

```bash
.venv\Scripts\python.exe manage.py test
```

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

A send takes `asset`, `amount`, and either `recipient` or `address`:

```json
{ "asset": "USDT", "amount": "50", "recipient": "tunde" }
```

Refused requests return HTTP 400 with a message that can be shown to the user:

```json
{ "detail": "You need 99,000,000 NGN but only have 480,000.", "code": "insufficient_funds" }
```

## Simulated rules

- New users start with 500,000 NGN, 250 USDT, 0.005 BTC, 0.1 ETH and 2 SOL.
- Trades cost 0.5%, taken from the amount paid.
- Sends to Vira users are free. Sends to external addresses cost the equivalent of $1.
