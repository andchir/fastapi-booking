# fastapi-booking

REST API для бронирования дат на FastAPI + MySQL.

## Возможности

- общий API ключ для всех роутов через `X-API-Key`;
- сообщения ошибок на русском и английском языках через заголовок языка;
- создание объекта бронирования: `title`, опциональные `image` и `description`, `booked_dates`, `uuid`;
- сохранение загруженных изображений в локальную папку и выдача публичного URL через `/uploads/...`;
- автоматическая выдача `access_key` при создании объекта;
- все операции с объектом выполняются через `uuid` объекта;
- редактирование объекта, замена дат и просмотр заметок к датам защищены `access_key`;
- добавление новых дат требует только общий `X-API-Key` и `uuid` объекта;
- добавление одной даты или периода дат;
- замена полного массива забронированных дат;
- обновление заметки одной забронированной даты;
- удаление одной забронированной даты;
- короткая заметка `note` для забронированной даты, которая не попадает в публичный вывод объекта;
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

## Язык сообщений

API поддерживает сообщения ошибок на русском и английском языках. Передайте `X-Language: en` или `X-Language: ru`; также поддерживается стандартный `Accept-Language`, например `Accept-Language: en-US`. Если заголовок не передан или язык не поддерживается, используется русский.

## Сгенерировать АПИ ключ
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## Примеры

Создать объект:

```bash
curl -X POST http://127.0.0.1:8000/objects \
  -H "X-API-Key: change-me" \
  -F "title=Дом у озера" \
  -F "booked_dates=2026-07-01" \
  -F "booked_dates=2026-07-02"
```

Если передать `-F "image=@./house.jpg"`, ответ содержит `image` с готовым URL для доступа к загруженному файлу. Без файла `image` будет `null`. `access_key` нужно сохранить: он используется для изменения конкретного объекта.

Добавить одну дату:

```bash
curl -X POST http://127.0.0.1:8000/objects/{uuid}/booked-dates \
  -H "X-API-Key: change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "date": "2026-07-03",
    "note": "Предоплата внесена"
  }'
```

Поле `date` также принимает диапазон дат строкой, границы включаются:

```bash
curl -X POST http://127.0.0.1:8000/objects/{uuid}/booked-dates \
  -H "X-API-Key: change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "date": "2026-06-06 - 2026-06-09",
    "note": "Закрыто для обслуживания"
  }'
```

Добавить период дат включительно:

```bash
curl -X POST http://127.0.0.1:8000/objects/{uuid}/booked-dates \
  -H "X-API-Key: change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "2026-07-10",
    "end_date": "2026-07-15",
    "note": "Закрыто для обслуживания"
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

Заменить все забронированные даты. Этот запрос удаляет старый набор дат объекта и записывает новый:

```bash
curl -X PUT http://127.0.0.1:8000/objects/{uuid}/booked-dates \
  -H "X-API-Key: change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "access_key": "{access_key}",
    "booked_dates": [
      {"date": "2026-08-01", "note": "Гость подтвердил"},
      {"date": "2026-08-02", "note": null}
    ]
  }'
```

Старый формат без заметок тоже поддерживается:

```json
{
  "access_key": "{access_key}",
  "booked_dates": ["2026-08-01", "2026-08-02"]
}
```

Обновить заметку одной даты:

```bash
curl -X PATCH http://127.0.0.1:8000/objects/{uuid}/booked-dates/2026-08-01 \
  -H "X-API-Key: change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "access_key": "{access_key}",
    "note": "Гость перенес время заезда"
  }'
```

Чтобы очистить заметку, передайте `"note": null`.

Удалить одну дату:

```bash
curl -X DELETE "http://127.0.0.1:8000/objects/{uuid}/booked-dates/2026-08-01?access_key={access_key}" \
  -H "X-API-Key: change-me"
```

Удалить диапазон дат включительно:

```bash
curl -X DELETE "http://127.0.0.1:8000/objects/{uuid}/booked-dates?access_key={access_key}&start_date=2026-08-01&end_date=2026-08-07" \
  -H "X-API-Key: change-me"
```

Получить даты с заметками:

```bash
curl "http://127.0.0.1:8000/objects/{uuid}/booked-dates?access_key={access_key}&start_date=2026-08-01&end_date=2026-08-31" \
  -H "X-API-Key: change-me"
```

Публичный `GET /objects/{uuid}` по-прежнему возвращает только массив дат без заметок.
