# Hop & Barley — интернет-магазин на Django/DRF

Итоговый проект для третьего модуля обучения (Django): магазин товаров для домашнего пивоварения (хмель, солод, дрожжи, наборы).
Веб-интерфейс на Django-шаблонах с сессионной авторизацией, REST API с JWT для внешних
клиентов, GraphQL-аналитика для сотрудников, PostgreSQL и Docker Compose.


- **Техническое задание:** [06 Project M3-1.md](06%20Project%20M3-1.md)
- **Вёрстка:** адаптирован шаблон [Hop-and-Barley](https://github.com/MagicCodeGit/Hop-and-Barley)

## Содержание

- [Стек](#стек)
- [Быстрый старт (Docker)](#быстрый-старт-docker)
- [Где что находится](#где-что-находится)
- [REST API и JWT](#rest-api-и-jwt)
- [GraphQL-аналитика](#graphql-аналитика)
- [Тесты, линтеры, типы](#тесты-линтеры-типы)
- [Запуск без Docker](#запуск-без-docker)
- [Структура проекта](#структура-проекта)
- [Бизнес-правила и архитектурные решения](#бизнес-правила-и-архитектурные-решения)
- [Бонусы](#бонусы)
- [Чек-лист](#чек-лист)

## Стек

| Слой | Технологии |
|------|------------|
| Backend | Python 3.14, Django 6.1, Django REST Framework, SimpleJWT, django-filter |
| Документация API | drf-spectacular (Swagger UI, ReDoc) |
| GraphQL | graphene-django |
| База данных | PostgreSQL 17 |
| Инфраструктура | Docker, Docker Compose, Gunicorn, WhiteNoise |
| Зависимости | [uv](https://docs.astral.sh/uv/) (`pyproject.toml` + `uv.lock`) |
| Качество | pytest-django, pytest-cov, ruff, mypy + django-stubs, GitHub Actions |

## Быстрый старт (Docker)

Нужны Docker и Docker Compose.

```bash
git clone https://github.com/bagbiv775/BAGBIV775_M3.git hop-and-barley
cd hop-and-barley

# 1. Подготовить переменные окружения
cp .env.example .env
#    откройте .env и задайте свои DJANGO_SECRET_KEY и POSTGRES_PASSWORD
#    в Windows (PowerShell): copy .env.example .env

# 2. Собрать и запустить
docker compose up --build
```

Откройте http://localhost:8000.

При старте контейнер `web` сам выполняет `migrate`, `collectstatic` и, если в `.env`
указано `SEED_DEMO_DATA=1`, заполняет базу демо-данными. Повторный запуск ничего не дублирует.

**Миграции** лежат в репозитории (`*/migrations/`). Применить их вручную можно так:

```bash
docker compose exec web python manage.py migrate
```

**Демо-аккаунты** (создаются только при `SEED_DEMO_DATA=1`, только для локальной проверки):

| Роль | Логин | Пароль | Что есть |
|------|-------|--------|----------|
| Администратор | `admin` | `admin12345` | доступ в `/admin/`, аналитика, GraphQL |
| Покупатель | `demo` | `demo12345` | доставленный заказ (можно оставить отзыв на Citra и Pilsner) и заказ в статусе `pending` (можно отменить) |

Свой суперпользователь: `docker compose exec web python manage.py createsuperuser`.

Письма о новых заказах выводятся в лог: `docker compose logs -f web`.

## Где что находится

| URL | Что это |
|-----|---------|
| `/`, `/products/` | Каталог: поиск, фильтры по категории и цене, сортировка, пагинация |
| `/product/<slug>/` | Страница товара, средний рейтинг, отзывы, добавление в корзину |
| `/cart/` | Корзина (в сессии) |
| `/checkout/` | Оформление заказа (нужен вход) |
| `/account/` | Личный кабинет: заказы, профиль, адреса, смена пароля |
| `/account/register/`, `/account/login/` | Регистрация и вход |
| `/admin/` | Django Admin; аналитика — `/admin/orders/order/analytics/` |
| `/api/` | REST API (корень роутера) |
| `/api/docs/` | Swagger UI |
| `/api/redoc/` | ReDoc |
| `/api/schema/` | OpenAPI-схема (YAML) |
| `/graphql/` | GraphQL + GraphiQL (только персонал) |

## REST API и JWT

Веб-интерфейс использует сессии Django, а API — только JWT (SimpleJWT). Сессионная cookie
API не авторизует.

**Схема авторизации.** `POST /api/token/` по логину и паролю выдаёт пару токенов:

- `access` — короткоживущий (по умолчанию 30 минут, `JWT_ACCESS_MINUTES`), передаётся в
  каждом запросе: `Authorization: Bearer <access>`;
- `refresh` — долгоживущий (7 дней, `JWT_REFRESH_DAYS`), используется только для получения
  нового access через `POST /api/token/refresh/`.

Оба токена — подписанные JWT (HS256, ключ — `DJANGO_SECRET_KEY`), в payload лежат
`token_type`, `exp`, `iat`, `jti` и `user_id`.

| Метод | URL | Доступ | Описание |
|-------|-----|--------|----------|
| GET | `/api/products/` | все | Список: `?page=`, `?search=`, `?category=<slug>`, `?min_price=`, `?max_price=`, `?in_stock=true`, `?ordering=price\|-price\|created_at\|popularity\|name` |
| GET | `/api/products/<id>/` | все | Товар со средним рейтингом (`null`, если отзывов нет) |
| GET | `/api/products/<id>/reviews/` | все | Отзывы о товаре (бонус) |
| POST | `/api/products/<id>/reviews/` | JWT | Отзыв после доставленного заказа (бонус) |
| POST | `/api/orders/` | JWT | Создать заказ из позиций |
| GET | `/api/orders/` | JWT | Свои заказы |
| GET | `/api/orders/<id>/` | JWT | Свой заказ (чужой — 404) |
| POST | `/api/orders/<id>/cancel/` | JWT | Отмена своего заказа в статусе `pending` |
| POST | `/api/token/` | — | Получить access/refresh |
| POST | `/api/token/refresh/` | refresh | Новый access |
| POST | `/api/register/` | — | Регистрация, сразу возвращает токены (бонус) |

`PUT`, `PATCH` и `DELETE` для заказов возвращают `405`.

### Примеры (curl)

```bash
# Токены
curl -s -X POST http://localhost:8000/api/token/ \
  -H 'Content-Type: application/json' \
  -d '{"username": "demo", "password": "demo12345"}'
# {"refresh": "eyJhbGciOi...", "access": "eyJhbGciOi..."}

ACCESS=<access-токен из ответа>

# Каталог: хмель от $5, дорогие сначала
curl -s 'http://localhost:8000/api/products/?category=hops&min_price=5&ordering=-price'

# Создать заказ: только id товара и количество, цены и статус считает сервер
curl -s -X POST http://localhost:8000/api/orders/ \
  -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{
        "items": [{"product_id": 1, "quantity": 2}, {"product_id": 3, "quantity": 1}],
        "shipping_address": "Алматы, ул. Абая, 1",
        "payment_method": "card",
        "contact_name": "Иван Иванов",
        "contact_phone": "+7 700 123 45 67"
      }'

# Мои заказы и отмена
curl -s http://localhost:8000/api/orders/ -H "Authorization: Bearer $ACCESS"
curl -s -X POST http://localhost:8000/api/orders/5/cancel/ -H "Authorization: Bearer $ACCESS"

# Обновить access-токен
curl -s -X POST http://localhost:8000/api/token/refresh/ \
  -H 'Content-Type: application/json' -d '{"refresh": "<refresh-токен>"}'
```

Способы оплаты: `card`, `wallet`, `cash` (условные, деньги не списываются).
Ошибки бизнес-правил возвращаются как `400`, например:

```json
{"items": ["Недостаточно товара «Хмель Mosaic, 100 г»: запрошено 50, в наличии 20."]}
```

В Swagger UI (`/api/docs/`) нажмите **Authorize** и вставьте access-токен — после этого
можно вызывать защищённые методы прямо из браузера.

## GraphQL-аналитика

Единственный эндпоинт — `/graphql/`. Данные доступны только пользователям с `is_staff`:
либо войдите в `/admin/` и откройте `/graphql/` в браузере (GraphiQL), либо передайте
JWT администратора в заголовке `Authorization: Bearer <access>`.

```graphql
{
  salesSummary { revenue soldOrders averageOrderValue totalOrders }
  ordersByStatus { status label count }
  revenueTrend(days: 30) { day revenue orders }
  topProducts(limit: 5) { name category sold stock }
  lowStockProducts(threshold: 10) { name stock }
  customerActivity { registered withOrders buyers repeatBuyers }
  repeatCustomers(limit: 10) { username ordersCount totalSpent }
}
```

```bash
curl -s -X POST http://localhost:8000/graphql/ \
  -H "Authorization: Bearer $ADMIN_ACCESS" -H 'Content-Type: application/json' \
  -d '{"query": "{ salesSummary { revenue averageOrderValue } }"}'
```

Выручка, средний чек и «продано» считаются по заказам в статусах `paid`, `shipped`,
`delivered`.

## Тесты, линтеры, типы

Тесты используют PostgreSQL (как и проект). Проще всего запускать их на хосте против базы
из Compose — она опубликована на `127.0.0.1:5432`:

```bash
docker compose up -d db            # база из docker-compose
uv sync                            # зависимости, включая dev-группу
set -a; source .env; set +a        # переменные окружения (POSTGRES_HOST=localhost)

uv run pytest                      # 187 тестов
uv run pytest --cov                # с отчётом о покрытии (~99%)
uv run ruff check .                # линтер (аналог flake8)
uv run ruff format --check .       # форматирование
uv run mypy .                      # статическая проверка типов (django-stubs, drf-stubs)
```

Если на хосте порт 5432 занят, задайте в `.env` `POSTGRES_PUBLISHED_PORT=5433` и
`POSTGRES_PORT=5433`.

Что покрыто тестами: каталог (поиск, фильтры, сортировки, пагинация, число запросов),
страница товара и отзывы (запрет без доставленной покупки, повторный отзыв, валидация
рейтинга формой/моделью/сериализатором, средний рейтинг), корзина (остатки, сохранение после
входа), оформление заказа (транзакционность, остатки, письма), личный кабинет и доступ к
чужим заказам, все переходы статусов (разрешённые и запрещённые), однократный возврат
остатков при отмене, ограничения БД, Django Admin, REST API, JWT, GraphQL, демо-данные.

**CI** (`.github/workflows/ci.yml`) на каждый push: ruff, mypy, проверка миграций, pytest
с порогом покрытия 80%, затем сборка `docker compose up --build` и smoke-тест.

## Запуск без Docker

```bash
uv sync
cp .env.example .env               # POSTGRES_HOST=localhost, своя БД PostgreSQL
set -a; source .env; set +a
uv run python manage.py migrate
uv run python manage.py seed_demo  # демо-данные (необязательно)
uv run python manage.py runserver
```

## Структура проекта

```
.
├── config/              # settings (из переменных окружения), urls, api_urls, wsgi/asgi
├── core/                # общие компоненты: TimeStampedModel, стили форм, шаблонные фильтры
├── products/            # Category, Product (+ QuerySet с рейтингом и популярностью),
│   ├── api/             #   каталог, страница товара, API товаров, админка
│   ├── demo_data/       #   JSON и картинки для команды seed_demo
│   └── management/      #   команда seed_demo
├── reviews/             # Review, правила допуска к отзывам (services.py), форма, API-сериализатор
├── orders/              # Order, OrderItem, корзина в сессии, оформление, админка
│   ├── services.py      #   ★ общая бизнес-логика заказа: создание, переходы статусов, отмена
│   ├── cart.py          #   корзина (только веб)
│   ├── notifications.py #   email после коммита транзакции
│   └── api/             #   API заказов
├── users/               # регистрация, вход, личный кабинет, адреса доставки (Address), API регистрации
├── analytics/           # выборки для аналитики (selectors.py) и GraphQL-схема
├── templates/           # Django-шаблоны (base.html + наследники), шаблоны админки и писем
├── static/              # CSS/JS/картинки шаблона Hop & Barley + shop.css
├── tests/               # pytest-django
├── docker/entrypoint.sh # migrate + collectstatic + seed_demo при старте контейнера
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── pyproject.toml, uv.lock
```

## Бизнес-правила и архитектурные решения

- **Одна точка истины для заказов.** `orders/services.py` содержит `create_order`,
  `change_order_status` и `cancel_order_by_customer`. Их вызывают веб-оформление, REST API,
  карточка заказа в админке и массовые действия — правила не дублируются во views и
  serializers.
- **Транзакционность.** Заказ, все `OrderItem` и списание остатков выполняются в одном
  `transaction.atomic()`. Строки товаров блокируются `select_for_update()` (в порядке `pk`,
  чтобы параллельные заказы не продали больше остатка и не взаимоблокировались). Любая
  ошибка — и ничего не записано.
- **Цена — снимок.** `OrderItem.price` копируется из `Product.price` при оформлении; цены и
  итог никогда не берутся из запроса.
- **Статусы.** Разрешены только `pending → paid / cancelled`, `paid → shipped / cancelled`,
  `shipped → delivered`. Покупатель может отменить лишь свой `pending`-заказ. При смене
  статуса строка заказа блокируется, поэтому повторная отмена отклоняется и не возвращает
  остатки второй раз. В админке в выпадающем списке показываются только допустимые
  статусы, а сохранение идёт через тот же сервис.
- **Удаление запрещено.** Заказы нельзя удалить ни в админке, ни через API (`405`). Товар из
  заказов и пользователь с заказами защищены `on_delete=PROTECT`; товар снимается с продажи
  флагом `is_active`.
- **Популярность** — сумма `OrderItem.quantity` в заказах `paid/shipped/delivered`.
  Средний рейтинг считается через `Avg`, не хранится. Обе аннотации сделаны подзапросами,
  чтобы их можно было комбинировать без «размножения» строк JOIN-ами.
- **Ограничения в БД.** `CheckConstraint` на цену, остаток, сумму, количество и рейтинг;
  `UniqueConstraint` на пары `order+product` и `user+product`.
- **Корзина** хранит в сессии только `{id товара: количество}`; цены и остатки каждый раз
  читаются из базы. `login()` сохраняет данные сессии, поэтому корзина переживает вход и
  регистрацию.

**Отклонения от примерной структуры (п. 2.1 ТЗ):**

- В `Order` добавлены необязательные поля `contact_name` и `contact_phone` — их собирает
  форма оформления; в API они не обязательны.
- Добавлена модель `Address` (сохранённые адреса доставки, бонус личного кабинета).
  В заказе адрес хранится текстом (`shipping_address`), чтобы изменение или удаление
  сохранённого адреса не меняло историю заказов.
- Отзывы — отдельное приложение `reviews`; страница отзыва отправляется на
  `/product/<slug>/reviews/`.
- Интерфейс на русском языке; цены отображаются в долларах, как в исходном шаблоне.

## Бонусы

| Бонус | Где и как проверить |
|-------|---------------------|
| GraphQL-аналитика | `/graphql/` под администратором; `tests/test_graphql.py` |
| Покрытие тестами ≥ 80% | `uv run pytest --cov` — около 99% |
| Email-уведомления | после оформления заказа письма покупателю и админу в `docker compose logs web`; отправка через `transaction.on_commit`; `tests/test_order_services.py::test_emails_are_sent_after_commit` |
| Аналитика и массовые actions в админке | «Аналитика продаж» на странице заказов; actions «Отметить как оплаченные / отправленные / доставленные / Отменить» — недопустимые переходы пропускаются, отмена возвращает остатки |
| Расширенный личный кабинет | вкладки «Профиль», «Адреса», «Пароль»; фильтр заказов по статусу; сохранение адреса при оформлении и подстановка его в форму |
| Регистрация и отзывы через REST API | `POST /api/register/`, `GET/POST /api/products/<id>/reviews/` |
| Типизация, линтеры, статическая проверка | `uv run ruff check .`, `uv run mypy .` |
| CI | `.github/workflows/ci.yml` |
| Менеджер зависимостей | uv (`pyproject.toml`, `uv.lock`) |

## Чек-лист

- [x] Проект запускается через Docker Compose на чистой копии (`docker compose up --build`).
- [x] PostgreSQL используется.
- [x] Миграции находятся в репозитории и применяются по инструкции из README.
- [x] Приложен `.env.example` без реальных секретов; рабочий `.env` не добавлен в Git.
- [x] Каталог: фильтры, поиск, пагинация.
- [x] Страница товара: средний рейтинг, отзывы только после завершённой покупки, `ModelForm`,
      сообщения и добавление в корзину.
- [x] Корзина: управление, расчёт, проверка остатков.
- [x] Оформление заказа: транзакционное создание, валидация, изменение остатков, отмена по
      допустимым правилам и подтверждение пользователю.
- [x] Личный кабинет: регистрация, вход/выход, список и детали только своих заказов, отмена
      заказа в статусе `pending`.
- [x] REST API: JWT, документация, права.
- [x] Админка: модели зарегистрированы, настроены списки, поиск, фильтры и inline; заказы
      нельзя физически удалить.
- [x] Swagger/OpenAPI работает.
- [x] Код читаем, разделён по ответственности и не содержит неиспользуемых или
      закомментированных фрагментов.
- [x] Общая логика создания и отмены заказа не дублируется между веб-интерфейсом и REST API.
- [x] Базовые тесты проходят.
- [x] README полон и понятен.
- [x] Коммиты осмысленные.
- [x] Чек-лист приложен.
- [x] Бонусы перечислены в README вместе со способом их проверки.
