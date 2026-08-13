<?php

declare(strict_types=1);

namespace App\Services\Payments;

use App\Models\Payment;
use App\Models\PaymentMethod;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

/**
 * Договор платёжного провайдера.
 *
 * Всё, что зависит от конкретного провайдера, спрятано за этим
 * интерфейсом; остальное приложение (кнопка «Оплатить», обработчик
 * колбэков, автопродление) работает через него и провайдера не знает.
 * Добавить Payme или Click рядом с Uzum — значит написать ещё одну
 * реализацию, не трогая контроллеры и биллинг.
 */
interface PaymentGateway
{
    /** Код провайдера: uzum | payme | click. */
    public function provider(): string;

    /**
     * Начать онлайн-оплату счёта.
     *
     * Возвращает, куда отправить покупателя: у провайдеров с редиректом —
     * ссылку на платёжную страницу.
     *
     * @param  array<string, mixed>  $options
     * @return array{redirect_url?: string, payload?: array<string, mixed>}
     */
    public function createCheckout(Payment $payment, array $options = []): array;

    /** Проверить подлинность входящего колбэка (подпись/секрет/IP). */
    public function verifyCallback(Request $request): bool;

    /**
     * Разобрать колбэк в нормализованное событие.
     *
     * status: paid | failed | cancelled | pending | created.
     * reference — как в колбэке назван наш счёт (номер или external_id).
     *
     * @return array{
     *     status: string,
     *     reference: string|null,
     *     provider_transaction_id: string|null,
     *     amount_minor: int|null,
     *     raw: array<string, mixed>
     * }
     */
    public function parseCallback(Request $request): array;

    /**
     * Ответ провайдеру на колбэк в его формате (JSON-RPC / форма / текст).
     *
     * @param  array<string, mixed>  $event  результат parseCallback
     */
    public function callbackResponse(bool $accepted, array $event): Response;

    /**
     * Автосписание по привязанной карте — для автопродления подписки.
     *
     * @return array{ok: bool, message: string, provider_transaction_id?: string}
     */
    public function chargeSavedCard(Payment $payment, PaymentMethod $card): array;

    /**
     * Возврат средств по счёту.
     *
     * @return array{ok: bool, message: string}
     */
    public function refund(Payment $payment, int $amountMinor): array;
}
