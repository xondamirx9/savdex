<?php

declare(strict_types=1);

namespace App\Console\Commands;

use App\Services\Payments\PaymentGatewayException;
use App\Services\Payments\PaymentGatewayManager;
use App\Services\Payments\UzumGateway;
use Illuminate\Console\Command;

/**
 * Проверка связи с Uzum Checkout без реального платежа.
 *
 * Показывает, какие переменные заданы, и делает один запрос к API
 * (статус несуществующего заказа). По ответу видно, где затык:
 * сеть (белый список IP), ключи или конфигурация.
 */
class UzumPing extends Command
{
    protected $signature = 'savdex:uzum-ping';

    protected $description = 'Проверить доступ к API Uzum Checkout и ключи, не проводя платёж';

    public function handle(PaymentGatewayManager $gateways): int
    {
        $config = (array) config('payments.providers.uzum', []);

        $this->line('Конфигурация:');
        $this->line('  PAYMENTS_UZUM_ENABLED           = '.($config['enabled'] ? 'true' : 'false'));
        $this->line('  PAYMENTS_UZUM_CHECKOUT_ENABLED  = '.($config['checkout'] ? 'true' : 'false'));
        $this->line('  PAYMENTS_UZUM_SANDBOX           = '.($config['sandbox'] ? 'true' : 'false'));
        $this->line('  PAYMENTS_UZUM_BASE_URL          = '.((string) ($config['base_url'] ?? '') ?: '(пусто)'));
        $this->line('  PAYMENTS_UZUM_TERMINAL_ID       = '.self::mask((string) ($config['terminal_id'] ?? '')));
        $this->line('  PAYMENTS_UZUM_SECRET_KEY        = '.self::mask((string) ($config['secret_key'] ?? '')));
        $this->line('  PAYMENTS_UZUM_CALLBACK_LOGIN    = '.self::mask((string) ($config['callback_login'] ?? '')));
        $this->line('  PAYMENTS_UZUM_CALLBACK_PASSWORD = '.self::mask((string) ($config['callback_password'] ?? '')));
        $this->line('  PAYMENTS_UZUM_PROXY             = '.self::maskProxy((string) ($config['proxy'] ?? '')));
        $this->line('  PAYMENTS_UZUM_SPIC              = '.((string) ($config['fiscal']['spic'] ?? '') ?: '(пусто — корзина не передаётся)'));
        $this->line('  PAYMENTS_UZUM_PACKAGE_CODE      = '.((string) ($config['fiscal']['package_code'] ?? '') ?: '(пусто)'));
        $this->line('  PAYMENTS_UZUM_VAT_PERCENT       = '.(string) ($config['fiscal']['vat_percent'] ?? ''));
        $this->newLine();

        if (! $config['enabled']) {
            $this->error('Провайдер выключен: задайте PAYMENTS_UZUM_ENABLED=true');

            return self::FAILURE;
        }

        try {
            $gateway = $gateways->for('uzum');
        } catch (PaymentGatewayException $e) {
            $this->error($e->getMessage());

            return self::FAILURE;
        }

        if (! $gateway instanceof UzumGateway) {
            $this->error('Шлюз uzum не является UzumGateway');

            return self::FAILURE;
        }

        $result = $gateway->probe();

        if ($result['ok']) {
            $this->info('OK: '.$result['message']);

            if (! $config['checkout']) {
                $this->warn('Кнопка «Оплатить» пока выключена: задайте PAYMENTS_UZUM_CHECKOUT_ENABLED=true');
            }

            return self::SUCCESS;
        }

        $this->error('СБОЙ: '.$result['message']);

        return self::FAILURE;
    }

    /** Адрес прокси печатается без пароля: host:port виден, пароль — нет. */
    private static function maskProxy(string $value): string
    {
        if ($value === '') {
            return '(пусто — прямое соединение)';
        }

        return (string) preg_replace('~//([^:@/]+):[^@]*@~', '//$1:***@', $value);
    }

    /** Секреты в выводе не печатаются целиком — только край. */
    private static function mask(string $value): string
    {
        if ($value === '') {
            return '(пусто)';
        }

        return mb_strlen($value) <= 6
            ? str_repeat('*', mb_strlen($value))
            : mb_substr($value, 0, 3).str_repeat('*', max(3, mb_strlen($value) - 6)).mb_substr($value, -3);
    }
}
