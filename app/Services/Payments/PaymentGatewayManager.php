<?php

declare(strict_types=1);

namespace App\Services\Payments;

/**
 * Выбор платёжного шлюза по коду провайдера.
 *
 * Одна точка, где код провайдера превращается в реализацию. Провайдер,
 * которого нет в реестре или который выключен в конфиге, наружу не
 * выдаётся — вызывающий получит исключение, а не «тихо ничего».
 */
class PaymentGatewayManager
{
    /** Реестр провайдеров: код → класс реализации. */
    private const GATEWAYS = [
        'uzum' => UzumGateway::class,
        // 'payme' => PaymeGateway::class,
        // 'click' => ClickGateway::class,
    ];

    /** Включён ли провайдер в конфиге (есть ключи, поднят флаг). */
    public function enabled(string $provider): bool
    {
        return (bool) config("payments.providers.{$provider}.enabled", false);
    }

    /** Шлюз по умолчанию — из payments.default. */
    public function default(): PaymentGateway
    {
        return $this->for((string) config('payments.default', 'uzum'));
    }

    public function for(string $provider): PaymentGateway
    {
        $class = self::GATEWAYS[$provider] ?? null;

        if ($class === null) {
            throw new PaymentGatewayException("Неизвестный платёжный провайдер: {$provider}");
        }

        if (! $this->enabled($provider)) {
            throw new PaymentGatewayException("Провайдер {$provider} выключен — включите его в конфигурации и задайте ключи");
        }

        /** @var array<string, mixed> $config */
        $config = config("payments.providers.{$provider}", []);

        return new $class($config);
    }
}
