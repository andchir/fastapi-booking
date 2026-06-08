# fastapi-booking

REST API для бронирования дат на FastAPI + MySQL.

## Возможности

- общий API ключ для всех роутов через `X-API-Key`;
- создание объекта бронирования: `title`, загружаемое `image`, `description`, `booked_dates`, `uuid`;
- сохранение изображений в локальную папку и выдача публичного URL через `/uploads/...`;
- автоматическая выдача `access_key` при создании объекта;
- все операции с объектом выполняются через `uuid` объекта;
- редактирование объекта и замена дат защищены `access_key`;
- добавление новых дат требует только общий `X-API-Key` и `uuid` объекта;
- добавление одной даты или периода дат;
- замена полного массива забронированных дат;
- уникальность даты внутри объекта enforced на уровне MySQL.

## Запуск

Скопируйте настройки окружения:

```bash
cp .env.example .env
```

Поднимите MySQL:

```bash
docker compose up -d mysql
```

Установите зависимости и запустите API:

```bash
python -m venv venv
source venv/bin/activate
pip install -e .
uvicorn app.main:app --reload
```

Документация будет доступна на `http://127.0.0.1:8000/docs`.

## Переменные окружения

- `API_KEY` - общий ключ API, который нужно передавать в заголовке `X-API-Key`.
- `DATABASE_URL` - DSN MySQL в формате SQLAlchemy async, например `mysql+aiomysql://booking_user:booking_password@127.0.0.1:3306/booking_db`.
- `APP_NAME` - название приложения в OpenAPI.
- `UPLOAD_DIR` - локальная папка для загруженных изображений, по умолчанию `uploads`.

## Примеры

Создать объект:

```bash
curl -X POST http://127.0.0.1:8000/objects \
  -H "X-API-Key: change-me" \
  -F "title=Дом у озера" \
  -F "description=Тихое место для отдыха" \
  -F "booked_dates=2026-07-01" \
  -F "booked_dates=2026-07-02" \
  -F "image=@./house.jpg"
```

Ответ содержит `uuid`, `access_key` и `image` с готовым URL для доступа к загруженному файлу. `access_key` нужно сохранить: он используется для изменения конкретного объекта.

Добавить одну дату:

```bash
curl -X POST http://127.0.0.1:8000/objects/{uuid}/booked-dates \
  -H "X-API-Key: change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "date": "2026-07-03"
  }'
```

Добавить период дат включительно:

```bash
curl -X POST http://127.0.0.1:8000/objects/{uuid}/booked-dates \
  -H "X-API-Key: change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2026-07-10",
    "end_date": "2026-07-15"
  }'
```

Редактировать объект:

```bash
curl -X PATCH http://127.0.0.1:8000/objects/{uuid} \
  -H "X-API-Key: change-me" \
  -F "access_key={access_key}" \
  -F "title=Обновленное название" \
  -F "image=@./new-house.jpg"
```

Заменить все забронированные даты:

```bash
curl -X PUT http://127.0.0.1:8000/objects/{uuid}/booked-dates \
  -H "X-API-Key: change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "access_key": "{access_key}",
    "booked_dates": ["2026-08-01", "2026-08-02"]
  }'
```
