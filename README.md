# 🚀 GIG Marketplace — Production-Ready Backend

A scalable gig economy platform backend built with **Django 4.2**, **DRF**, **PostgreSQL**, **Redis**, and **Celery**. Connects employers with workers through a clean REST API with real-time chat, internal wallet, OTP authentication, and push notifications.

---

## 📋 Table of Contents

- [Architecture Overview](#architecture-overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
- [Key Design Decisions](#key-design-decisions)
- [Environment Variables](#environment-variables)
- [Running Tests](#running-tests)
- [Deployment](#deployment)

---

## 🏗 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                         Nginx                               │
│            (Rate limiting, static files, reverse proxy)     │
└───────────────────────┬─────────────────────────────────────┘
                        │
        ┌───────────────┼────────────────┐
        │               │                │
   HTTP/REST       WebSocket         Static/Media
        │         (Channels)             │
        ▼               ▼                ▼
┌───────────────────────────────────────────────┐
│              Django + DRF + Channels           │
│                                               │
│  ┌──────────┐ ┌──────┐ ┌──────────┐ ┌──────┐ │
│  │ accounts │ │ jobs │ │payments  │ │ chat │ │
│  └──────────┘ └──────┘ └──────────┘ └──────┘ │
│         │         │         │          │      │
│         └─────────┴────┬────┴──────────┘      │
│                        │                      │
│              ┌──────── core ────────┐          │
│              │ utils, exceptions,   │          │
│              │ permissions, models  │          │
│              └──────────────────────┘          │
└──────────────────────────┬────────────────────┘
                           │
        ┌──────────────────┼─────────────────┐
        │                  │                 │
        ▼                  ▼                 ▼
   PostgreSQL            Redis           Celery Workers
   (Primary DB)     (Cache, Sessions,  (OTP SMS, Push
                     Channel Layer,     Notifications,
                     Celery Broker)     Cleanup tasks)
```

### Clean Architecture — Service Layer Pattern

```
View  ──request──►  Serializer (validate)
                         │
                         ▼
                    Service Layer  ◄── Business logic lives here
                         │
                    ┌────┴────┐
                    │         │
                  Model    External
                  (ORM)    Provider
                            (SMS, Push, Payment)
```

Views are thin. **All business logic lives in `services.py`** inside each app.
This makes logic testable in isolation without HTTP overhead.

---

## 🛠 Tech Stack

| Component           | Technology               | Purpose                            |
|---------------------|--------------------------|------------------------------------|
| Web Framework       | Django 4.2               | Core MVC framework                 |
| REST API            | Django REST Framework    | Serializers, ViewSets, Auth        |
| Authentication      | JWT (SimpleJWT)          | Stateless auth with refresh tokens |
| Database            | PostgreSQL 15            | Primary data store                 |
| Cache / Sessions    | Redis 7                  | Caching, OTP storage, sessions     |
| Task Queue          | Celery 5                 | Async SMS, push notifications      |
| Message Broker      | Redis                    | Celery broker + result backend     |
| WebSocket           | Django Channels 4        | Real-time chat                     |
| Container           | Docker + Compose         | Local dev + production             |
| Reverse Proxy       | Nginx                    | SSL, rate limiting, static files   |
| API Docs            | drf-spectacular (Swagger)| Auto-generated OpenAPI 3.0         |
| SMS Provider        | Eskiz.uz / Mock          | OTP delivery (Uzbekistan)          |
| Push Notifications  | Firebase FCM / Mock      | Mobile push                        |
| Payment Gateways    | Payme + Click / Mock     | UZS deposits                       |

---

## 📁 Project Structure

```
gig_marketplace/
├── config/
│   ├── settings/
│   │   ├── base.py          # Shared settings
│   │   ├── development.py   # Dev overrides (DEBUG, no throttling)
│   │   └── production.py    # Prod (Sentry, HTTPS, WhiteNoise)
│   ├── urls.py              # Root URL router
│   ├── celery.py            # Celery app + beat schedule
│   ├── wsgi.py
│   └── asgi.py              # ASGI for HTTP + WebSocket
│
├── apps/
│   ├── core/                # Shared utilities (no models)
│   │   ├── models.py        # BaseModel, UUIDModel, SoftDeleteModel
│   │   ├── exceptions.py    # Custom exceptions + DRF handler
│   │   ├── permissions.py   # IsEmployer, IsWorker, IsOwnerOrAdmin
│   │   ├── renderers.py     # StandardJSONRenderer (success envelope)
│   │   ├── pagination.py    # StandardResultsPagination
│   │   ├── middleware.py    # RequestLoggingMiddleware
│   │   ├── utils.py         # OTP keys, Haversine, commission calc
│   │   └── logging.py       # JSONFormatter
│   │
│   ├── accounts/            # Auth + User management
│   │   ├── models.py        # User, OTPCode, DeviceToken
│   │   ├── serializers.py   # SendOTP, VerifyOTP, Profile, Rating
│   │   ├── services.py      # OTPService, AuthService, UserService
│   │   ├── views.py         # SendOTP, VerifyOTP, Profile, Logout
│   │   ├── tasks.py         # send_otp_sms_task, cleanup_expired_otps
│   │   ├── signals.py       # Auto-create wallet on user creation
│   │   ├── admin.py
│   │   └── urls/
│   │       ├── auth.py      # /auth/ endpoints
│   │       └── users.py     # /users/ endpoints
│   │
│   ├── jobs/                # Job lifecycle + discovery
│   │   ├── models.py        # Job, JobCategory, JobImage, JobReview
│   │   ├── serializers.py   # JobList, JobDetail, CreateJob, Filter
│   │   ├── services.py      # JobService, JobDiscoveryService
│   │   ├── views.py         # JobViewSet (create/accept/start/complete/cancel)
│   │   ├── admin.py
│   │   └── urls.py
│   │
│   ├── payments/            # Wallet + transactions + providers
│   │   ├── models.py        # Wallet, Transaction, PaymentRequest
│   │   ├── serializers.py
│   │   ├── services.py      # WalletService, DepositService
│   │   ├── views.py         # Wallet, Deposit, Webhooks
│   │   ├── admin.py
│   │   ├── providers/
│   │   │   └── payment_providers.py  # Mock, Payme, Click
│   │   └── urls/
│   │       ├── wallet.py    # /wallet/ endpoints
│   │       └── payments.py  # Webhook callbacks
│   │
│   ├── notifications/       # Push + in-app notifications
│   │   ├── models.py        # Notification (inbox record)
│   │   ├── services.py      # NotificationService (send, bulk)
│   │   ├── tasks.py         # Async notification tasks
│   │   ├── push.py          # Mock + Firebase FCM provider
│   │   ├── sms.py           # Mock + Eskiz SMS provider
│   │   ├── views.py
│   │   └── urls.py
│   │
│   └── chat/                # Real-time chat
│       ├── models.py        # ChatRoom, Message
│       ├── consumers.py     # AsyncWebsocketConsumer
│       ├── routing.py       # WebSocket URL patterns
│       ├── serializers.py
│       ├── views.py         # REST fallback (history)
│       ├── signals.py       # Auto-create room on job accept
│       └── urls.py
│
├── tests/
│   ├── conftest.py          # Fixtures (users, jobs, wallets)
│   ├── test_auth.py         # OTP, JWT, rate limiting
│   ├── test_jobs.py         # CRUD, race conditions, geo filters
│   └── test_payments.py     # Wallet, deposits, commission
│
├── scripts/
│   └── seed_data.py         # Demo data generator
│
├── docker/
│   ├── entrypoint.sh        # Wait-for-db + migrate
│   ├── nginx/nginx.conf     # Rate limiting, proxy, WebSocket
│   └── postgres/init.sql    # Extensions (uuid-ossp, pg_trgm)
│
├── requirements/
│   ├── base.txt
│   ├── development.txt
│   └── production.txt
│
├── Dockerfile               # Multi-stage (dev + prod)
├── docker-compose.yml
├── .env.example
├── manage.py
└── pytest.ini
```

---

## ⚡ Quick Start

### 1. Clone & Configure

```bash
git clone <repo>
cd gig_marketplace
cp .env.example .env
# Edit .env — set SECRET_KEY, DB credentials, etc.
```

### 2. Start with Docker Compose

```bash
# Start all services
docker-compose up --build

# In a separate terminal — seed demo data
docker-compose exec web python manage.py seed_data --users 20 --jobs 50

# Create admin user
docker-compose exec web python manage.py createsuperuser
```

### 3. Access the Services

| Service        | URL                           |
|----------------|-------------------------------|
| API            | http://localhost:8000/api/v1/ |
| Swagger UI     | http://localhost:8000/api/docs/ |
| Django Admin   | http://localhost:8000/admin/  |
| Celery Flower  | http://localhost:5555/        |
| Health Check   | http://localhost:8000/health/ |

### 4. Test the OTP Flow (Dev Mode)

```bash
# 1. Send OTP (always 123456 in dev)
curl -X POST http://localhost:8000/api/v1/auth/send-otp/ \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+998901234567", "role": "employer"}'

# 2. Verify OTP — get JWT tokens
curl -X POST http://localhost:8000/api/v1/auth/verify-otp/ \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+998901234567", "code": "123456"}'

# 3. Use the access token
curl http://localhost:8000/api/v1/users/me/ \
  -H "Authorization: Bearer <access_token>"
```

---

## 📡 API Reference

### Authentication

| Method | Endpoint                    | Auth | Description                        |
|--------|-----------------------------|------|------------------------------------|
| POST   | `/auth/send-otp/`           | No   | Send OTP SMS (rate: 5/hour)        |
| POST   | `/auth/verify-otp/`         | No   | Verify OTP → JWT tokens            |
| POST   | `/auth/token/refresh/`      | No   | Refresh access token               |
| POST   | `/auth/logout/`             | Yes  | Blacklist refresh token            |

### Users

| Method | Endpoint                    | Role       | Description                |
|--------|-----------------------------|------------|----------------------------|
| GET    | `/users/me/`                | Any        | Get own profile            |
| PATCH  | `/users/me/`                | Any        | Update name, avatar, bio   |
| GET    | `/users/{id}/`              | Any        | Public user profile        |
| POST   | `/users/{id}/rate/`         | Any        | Rate after job             |
| POST   | `/users/device-token/`      | Any        | Register FCM token         |

### Jobs

| Method | Endpoint                    | Role       | Description                        |
|--------|-----------------------------|------------|------------------------------------|
| GET    | `/jobs/`                    | Worker     | Discover available jobs            |
| POST   | `/jobs/`                    | Employer   | Create job (deducts balance)       |
| GET    | `/jobs/{id}/`               | Any        | Job details                        |
| GET    | `/jobs/my/`                 | Any        | My jobs (employer or worker)       |
| POST   | `/jobs/{id}/accept/`        | Worker     | Accept job (race-condition safe)   |
| POST   | `/jobs/{id}/start/`         | Worker     | Mark as in-progress                |
| POST   | `/jobs/{id}/complete/`      | Employer   | Complete + release payment         |
| POST   | `/jobs/{id}/cancel/`        | Employer/Worker | Cancel + refund             |
| GET    | `/jobs/categories/`         | Any        | List job categories                |

**Job Discovery Query Parameters:**

| Param       | Type    | Description                                |
|-------------|---------|--------------------------------------------|
| `lat`       | float   | Worker latitude for geo search             |
| `lon`       | float   | Worker longitude for geo search            |
| `radius_km` | float   | Search radius in km (default: 50)          |
| `category`  | string  | Category slug (e.g. `cleaning`)            |
| `min_price` | int     | Minimum price in tiyin                     |
| `max_price` | int     | Maximum price in tiyin                     |
| `sort_by`   | string  | `-created_at`, `price`, `-price`, `distance` |

### Wallet & Payments

| Method | Endpoint                       | Description                         |
|--------|--------------------------------|-------------------------------------|
| GET    | `/wallet/`                     | Balance + stats                     |
| POST   | `/wallet/deposit/`             | Initiate Payme/Click deposit        |
| GET    | `/wallet/transactions/`        | Paginated transaction history       |
| POST   | `/payments/webhook/payme/`     | Payme payment callback              |
| POST   | `/payments/webhook/click/`     | Click payment callback              |

### Notifications

| Method | Endpoint                          | Description              |
|--------|-----------------------------------|--------------------------|
| GET    | `/notifications/`                 | Notification inbox       |
| GET    | `/notifications/unread-count/`    | Unread badge count       |
| POST   | `/notifications/{id}/read/`       | Mark one as read         |
| POST   | `/notifications/read-all/`        | Mark all as read         |

### Chat

| Method | Endpoint                         | Description                    |
|--------|----------------------------------|--------------------------------|
| GET    | `/chat/`                         | List my chat rooms             |
| GET    | `/chat/{room_id}/`               | Room detail + message history  |
| POST   | `/chat/{room_id}/messages/`      | Send message (REST fallback)   |
| WS     | `ws://host/ws/chat/{room_id}/`   | Real-time WebSocket chat       |

---

## 🔑 Key Design Decisions

### 1. Phone-Only Authentication (no passwords)
Chosen for mobile-first UX in Central Asia where SMS-based login is universal. OTP codes are stored in Redis (fast, TTL auto-expiry) with DB records for audit.

### 2. Prices as Integers (tiyin)
All monetary values are stored as `PositiveBigIntegerField` in the smallest unit (tiyin, 1 UZS = 100 tiyin). This eliminates floating-point rounding errors in financial calculations — critical for a payment system.

### 3. Race Condition Prevention with `SELECT FOR UPDATE`
When a worker accepts a job, the row is locked with `select_for_update(nowait=True)`. If two workers try simultaneously, the second gets a lock conflict immediately (no queuing) and receives a 409 Conflict response. This is enforced at the DB level, not application level.

### 4. Escrow Payment Model
When an employer creates a job, the full price is immediately deducted from their balance and moved to `held_balance`. This ensures funds are reserved. On completion, 90% goes to the worker; on cancellation, 100% is refunded. No job can be created without sufficient funds.

### 5. Immutable Transaction Ledger
`Transaction` records are **never updated or deleted** — only created. Every money movement appends a new record with `balance_before` and `balance_after` for full auditability. The admin panel disables add/edit for this model.

### 6. Service Layer (No Fat Views/Models)
Views validate input (serializers) and call services. Services contain all business logic and can be tested without HTTP. Models are purely data — no business logic. This enables future migration to microservices by extracting services.

### 7. Bounding Box + Haversine Geo Search
PostgreSQL is used without PostGIS for simplicity. Geo search uses a lat/lon bounding box pre-filter (fast DB query) followed by a precise Haversine distance calculation in Python. For production with millions of records, swap in PostGIS or Elasticsearch with geo queries.

### 8. Provider Abstraction Pattern
SMS, push notifications, and payment providers all implement abstract base classes (`BaseSMSProvider`, `BasePushProvider`, `BasePaymentProvider`). Swapping from mock → real provider is a single env variable change. Adding a new provider requires only implementing the interface.

---

## ⚙️ Environment Variables

See `.env.example` for full list. Key variables:

```bash
SECRET_KEY=...                          # Django secret key
DEBUG=False                             # Never True in production
DB_HOST=db                              # PostgreSQL host
REDIS_URL=redis://redis:6379/0          # Redis connection
SMS_PROVIDER=mock                       # mock | eskiz
NOTIFICATION_PROVIDER=mock             # mock | firebase
PAYME_MERCHANT_ID=...                   # Payme credentials
CLICK_SERVICE_ID=...                    # Click credentials
PLATFORM_COMMISSION_PERCENT=10          # Platform fee %
USE_FIXED_OTP=True                      # Always 123456 in dev
```

---

## 🧪 Running Tests

```bash
# Inside Docker
docker-compose exec web pytest

# Locally
pip install -r requirements/development.txt
pytest

# With coverage report
pytest --cov=apps --cov-report=html

# Specific test file
pytest tests/test_jobs.py -v

# Skip slow tests
pytest -m "not slow"
```

---

## 🚢 Deployment

### Production Checklist

```bash
# 1. Set all required env vars
cp .env.example .env.production
# Edit: DEBUG=False, strong SECRET_KEY, real DB/Redis, Sentry DSN

# 2. Build production image
docker build --target production -t gig-marketplace:latest .

# 3. Run with production compose
docker-compose -f docker-compose.yml up -d

# 4. Apply migrations
docker-compose exec web python manage.py migrate

# 5. Collect static files
docker-compose exec web python manage.py collectstatic --noinput

# 6. Verify health
curl https://your-domain.com/health/
```

### Scaling Considerations

- **Celery workers**: Scale horizontally. Split queues: `otp`, `notifications`, `payments`
- **Database**: Add read replicas → use `DATABASE_ROUTERS`
- **Cache**: Redis Cluster for high availability
- **WebSocket**: Use Channels with Redis channel layer (already configured)
- **Microservices**: Each `apps/` module is already isolated with its own service layer — extract to separate services by moving `services.py` behind an internal gRPC or HTTP interface

---

## 📊 Database Schema Summary

```
accounts_users          ← Custom user (phone-based)
accounts_otp_codes      ← OTP audit log
accounts_device_tokens  ← FCM tokens (per device)

jobs_categories         ← Job categories
jobs_jobs               ← Core job entity
jobs_images             ← Job photo attachments
jobs_reviews            ← Post-completion reviews

payments_wallets        ← User balance (1-to-1 with User)
payments_transactions   ← Immutable financial ledger
payments_payment_requests ← External payment lifecycle

notifications_notifications ← In-app notification inbox

chat_rooms              ← 1-per-job chat room
chat_messages           ← Immutable message records
```
