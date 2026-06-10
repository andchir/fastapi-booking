# Деплой на Ubuntu

Инструкция описывает продакшн-деплой FastAPI API на Ubuntu с `systemd`, MySQL и Nginx.

Примеры ниже используют:

- домен: `booking.example.com`;
- путь приложения: `/opt/fastapi-booking`;
- системного пользователя: `booking`;
- порт приложения внутри сервера: `127.0.0.1:8000`.

Замените эти значения на свои.

## 1. Подготовка сервера

Обновите систему и установите пакеты:

```bash
sudo apt update
sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git nginx mysql-server
```

Создайте пользователя для приложения:

```bash
sudo useradd --system --create-home --home-dir /opt/fastapi-booking --shell /usr/sbin/nologin booking
```

## 2. MySQL

Включите MySQL:

```bash
sudo systemctl enable --now mysql
```

Создайте базу и пользователя:

```bash
sudo mysql
```

```sql
CREATE DATABASE booking_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'booking_user'@'127.0.0.1' IDENTIFIED BY 'replace-with-strong-password';
GRANT ALL PRIVILEGES ON booking_db.* TO 'booking_user'@'127.0.0.1';
FLUSH PRIVILEGES;
EXIT;
```

`DATABASE_URL` для этого варианта:

```text
mysql+aiomysql://booking_user:replace-with-strong-password@127.0.0.1:3306/booking_db
```

## 3. Код приложения

Склонируйте репозиторий:

```bash
sudo git clone <repo-url> /opt/fastapi-booking
sudo chown -R booking:booking /opt/fastapi-booking
```

Создайте виртуальное окружение и установите зависимости:

```bash
sudo -u booking python3 -m venv /opt/fastapi-booking/venv
sudo -u booking /opt/fastapi-booking/venv/bin/pip install --upgrade pip
sudo -u booking /opt/fastapi-booking/venv/bin/pip install -e /opt/fastapi-booking
```

Создайте папку для загруженных изображений:

```bash
sudo -u booking mkdir -p /opt/fastapi-booking/uploads
```

## 4. Переменные окружения

Создайте файл окружения:

```bash
sudo nano /etc/fastapi-booking.env
```

Пример содержимого:

```env
APP_NAME=FastAPI Booking
API_KEY=replace-with-long-random-api-key
DATABASE_URL=mysql+aiomysql://booking_user:replace-with-strong-password@127.0.0.1:3306/booking_db
UPLOAD_DIR=/opt/fastapi-booking/uploads
IMAGE_MAX_SIZE_PX=1000
```

Сгенерировать `API_KEY`:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Закройте доступ к файлу окружения:

```bash
sudo chown root:booking /etc/fastapi-booking.env
sudo chmod 640 /etc/fastapi-booking.env
```

## 5. systemd сервис API

Создайте unit-файл:

```bash
sudo nano /etc/systemd/system/fastapi-booking.service
```

Содержимое:

```ini
[Unit]
Description=FastAPI Booking API
After=network.target mysql.service
Wants=mysql.service

[Service]
User=booking
Group=booking
WorkingDirectory=/opt/fastapi-booking
EnvironmentFile=/etc/fastapi-booking.env
ExecStart=/opt/fastapi-booking/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Запустите сервис:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now fastapi-booking
sudo systemctl status fastapi-booking
```

Проверка локально на сервере:

```bash
curl http://127.0.0.1:8000/health
```

Логи:

```bash
sudo journalctl -u fastapi-booking -f
```

## 6. Nginx

Создайте конфиг сайта:

```bash
sudo nano /etc/nginx/sites-available/fastapi-booking
```

Содержимое:

```nginx
server {
    listen 80;
    server_name booking.example.com;

    client_max_body_size 20m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Включите сайт:

```bash
sudo ln -s /etc/nginx/sites-available/fastapi-booking /etc/nginx/sites-enabled/fastapi-booking
sudo nginx -t
sudo systemctl reload nginx
```

Проверка:

```bash
curl http://booking.example.com/health
```

## 7. HTTPS

Установите Certbot:

```bash
sudo apt install -y certbot python3-certbot-nginx
```

Получите сертификат:

```bash
sudo certbot --nginx -d booking.example.com
```

Проверьте автообновление:

```bash
sudo certbot renew --dry-run
```

## 8. Firewall

Если используется `ufw`, откройте только SSH и Nginx:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status
```

Порт `8000` наружу открывать не нужно: приложение слушает только `127.0.0.1`, а внешний трафик принимает Nginx.

## 9. Обновление приложения

```bash
cd /opt/fastapi-booking
sudo -u booking git pull
sudo -u booking /opt/fastapi-booking/venv/bin/pip install -e /opt/fastapi-booking
sudo systemctl restart fastapi-booking
sudo systemctl status fastapi-booking
```

После обновления проверьте:

```bash
curl https://booking.example.com/health
```

## 10. Резервные копии

Минимальный backup MySQL:

```bash
mysqldump -u booking_user -p booking_db > booking_db_$(date +%F).sql
```

Также нужно сохранять папку загрузок:

```bash
tar -czf uploads_$(date +%F).tar.gz /opt/fastapi-booking/uploads
```

## 11. Частые проверки

Проверить сервис API:

```bash
sudo systemctl status fastapi-booking
```

Проверить Nginx:

```bash
sudo nginx -t
sudo systemctl status nginx
```

Проверить порт приложения:

```bash
ss -ltnp | grep 8000
```

Проверить доступность API через Nginx:

```bash
curl -i https://booking.example.com/health
```

Если API не стартует, сначала смотрите:

```bash
sudo journalctl -u fastapi-booking -n 100 --no-pager
```
