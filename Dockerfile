# syntax=docker/dockerfile:1

# --- Зависимости PHP -------------------------------------------------------
# Стадия идёт первой: vendor нужен не только серверу, но и сборке фронтенда —
# app.css и тема Filament ссылаются на файлы пакетов через @source/@import.
# Расширения (intl и прочие) стоят в финальном образе, а не здесь,
# поэтому платформенные требования на этой стадии не проверяются.
FROM composer:2 AS vendor
WORKDIR /app
COPY composer.json composer.lock ./
RUN composer install --no-dev --prefer-dist --no-interaction --no-progress \
        --no-scripts --ignore-platform-reqs
COPY . .
RUN composer dump-autoload --optimize --no-scripts

# --- Фронтенд: собираем Vite-бандл ----------------------------------------
FROM node:22-alpine AS assets
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY vite.config.ts tsconfig.json ./
COPY resources ./resources
COPY public ./public
COPY app ./app
COPY --from=vendor /app/vendor ./vendor
RUN mkdir -p storage/framework/views && npm run build

# --- Рабочий образ: Apache + mod_php ---------------------------------------
FROM php:8.3-apache

RUN apt-get update && apt-get install -y --no-install-recommends \
        libicu-dev libzip-dev libpng-dev libjpeg62-turbo-dev libfreetype6-dev libwebp-dev libpq-dev \
    && docker-php-ext-configure gd --with-freetype --with-jpeg --with-webp \
    && docker-php-ext-install -j"$(nproc)" intl zip gd bcmath exif opcache pdo_pgsql \
    && a2enmod rewrite headers \
    && mv "$PHP_INI_DIR/php.ini-production" "$PHP_INI_DIR/php.ini" \
    && rm -rf /var/lib/apt/lists/*

# Лимиты загрузки. Стандартный php.ini-production разрешает файлы
# до 2 МБ — любое фото с телефона больше, и загрузка логотипа или
# фотографий объявления умирала в PHP раньше, чем её видел Laravel.
# Приложение принимает изображения до 8 МБ и документы до 20 МБ
# (валидация в контроллерах), объявление шлёт до 10 фото за раз —
# отсюда цифры. Память — под GD: декодирование снимка в 48 Мп
# не помещается в стандартные 128 МБ.
RUN { \
        echo 'upload_max_filesize = 21M'; \
        echo 'post_max_size = 90M'; \
        echo 'memory_limit = 512M'; \
        echo 'max_execution_time = 120'; \
    } > "$PHP_INI_DIR/conf.d/zz-uploads.ini"

ENV APACHE_DOCUMENT_ROOT=/var/www/html/public
RUN sed -ri -e 's!/var/www/html!${APACHE_DOCUMENT_ROOT}!g' /etc/apache2/sites-available/*.conf \
    && sed -ri -e 's!/var/www/!${APACHE_DOCUMENT_ROOT}!g' /etc/apache2/apache2.conf /etc/apache2/conf-available/*.conf

WORKDIR /var/www/html
COPY --from=vendor --chown=www-data:www-data /app ./
COPY --from=assets --chown=www-data:www-data /app/public/build ./public/build
COPY docker/render-entrypoint.sh /usr/local/bin/render-entrypoint
RUN chmod +x /usr/local/bin/render-entrypoint

ENV APP_ENV=production \
    APP_DEBUG=false \
    LOG_CHANNEL=stderr

ENTRYPOINT ["render-entrypoint"]
CMD ["apache2-foreground"]
