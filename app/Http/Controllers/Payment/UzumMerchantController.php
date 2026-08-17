<?php

declare(strict_types=1);

namespace App\Http\Controllers\Payment;

use App\Http\Controllers\Controller;
use App\Models\Payment;
use App\Models\PaymentTransaction;
use App\Services\OrderService;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

/**
 * Merchant API Uzum: приём вызовов их процессинга.
 *
 * Это не вебхук «оплачено», а диалог, который ведёт сторона Uzum:
 *
 *   check   — есть ли такой счёт и можно ли его оплачивать;
 *   create  — завести транзакцию (деньги ещё не списаны);
 *   confirm — деньги списаны, начисляем купленное;
 *   reverse — отмена транзакции;
 *   status  — сверка состояния.
 *
 * Отдельный контроллер, а не реализация PaymentGateway: интерфейс
 * шлюза описывает провайдеров с одним вебхуком, а здесь у каждой
 * операции свои проверки и свой формат ответа. Payme и Click работают
 * по той же схеме — при подключении они получат свои контроллеры
 * рядом, с своими кодами ошибок.
 *
 * Идемпотентность держит уникальная пара (provider, transId) в
 * payment_transactions: повторный confirm не начислит тариф дважды,
 * повторный create не заведёт вторую транзакцию.
 *
 * Формат: JSON с полями serviceId/timestamp/transId, суммы в тийинах,
 * время в миллисекундах, ошибки — HTTP 400 с кодом из номенклатуры
 * Uzum, неавторизованный вызов — 401.
 */
class UzumMerchantController extends Controller
{
    // Коды ошибок Merchant API Uzum
    private const ERROR_AUTH = 10001;

    private const ERROR_BAD_OPERATION = 10003;

    private const ERROR_PARAMS_MISSING = 10005;

    private const ERROR_BAD_SERVICE_ID = 10006;

    private const ERROR_INVOICE_NOT_FOUND = 10007;

    private const ERROR_ALREADY_PAID = 10008;

    private const ERROR_INVOICE_CANCELLED = 10009;

    private const ERROR_TRANSACTION_EXISTS = 10010;

    private const ERROR_BAD_AMOUNT = 10011;

    private const ERROR_TRANSACTION_NOT_FOUND = 10014;

    private const ERROR_TRANSACTION_CANCELLED = 10015;

    private const ERROR_ALREADY_CONFIRMED = 10016;

    private const ERROR_CANNOT_REVERSE = 10017;

    private const ERROR_ALREADY_REVERSED = 10018;

    /** Состояние транзакции — во внешнее имя из протокола Uzum. */
    private const STATE_LABELS = [
        PaymentTransaction::STATE_CREATED => 'CREATED',
        PaymentTransaction::STATE_PERFORMED => 'CONFIRMED',
        PaymentTransaction::STATE_CANCELLED => 'REVERSED',
    ];

    public function handle(Request $request, string $operation): JsonResponse
    {
        // Выключенный провайдер — как будто маршрута нет
        abort_unless((bool) config('payments.providers.uzum.enabled'), 404);

        if (! $this->authorized($request)) {
            return $this->error($request, self::ERROR_AUTH, status: 401);
        }

        $configured = (string) config('payments.providers.uzum.service_id', '');

        if ($configured !== '' && (string) $request->input('serviceId') !== $configured) {
            return $this->error($request, self::ERROR_BAD_SERVICE_ID);
        }

        return match ($operation) {
            'check' => $this->check($request),
            'create' => $this->create($request),
            'confirm' => $this->confirm($request),
            'reverse' => $this->reverse($request),
            'status' => $this->status($request),
            default => $this->error($request, self::ERROR_BAD_OPERATION),
        };
    }

    /** Проверка счёта перед оплатой: существует и ждёт денег. */
    private function check(Request $request): JsonResponse
    {
        [$payment, $error] = $this->payableInvoice($request);

        if ($payment === null) {
            return $this->error($request, $error);
        }

        return response()->json([
            'serviceId' => $request->input('serviceId'),
            'timestamp' => $request->input('timestamp'),
            'status' => 'OK',
            'data' => $this->invoiceData($payment),
        ]);
    }

    /** Создание транзакции: Uzum резервирует оплату, деньги ещё не списаны. */
    private function create(Request $request): JsonResponse
    {
        $transId = (string) $request->input('transId');
        $amount = $request->input('amount');

        if ($transId === '' || ! is_numeric($amount)) {
            return $this->error($request, self::ERROR_PARAMS_MISSING);
        }

        // Повторный create с тем же transId — сетевой повтор, а не
        // новая покупка: отвечаем кодом «уже создана» со временем первой
        $existing = $this->transaction($transId);

        if ($existing !== null) {
            return $this->error($request, self::ERROR_TRANSACTION_EXISTS, [
                'transTime' => $existing->created_at->getTimestampMs(),
            ]);
        }

        [$payment, $error] = $this->payableInvoice($request);

        if ($payment === null) {
            return $this->error($request, $error);
        }

        if ((int) $amount !== $payment->amountMinor()) {
            return $this->error($request, self::ERROR_BAD_AMOUNT);
        }

        $tx = PaymentTransaction::create([
            'payment_id' => $payment->id,
            'provider' => 'uzum',
            'provider_transaction_id' => $transId,
            'state' => PaymentTransaction::STATE_CREATED,
            'amount_minor' => (int) $amount,
            'currency' => (string) config('payments.currency', 'UZS'),
            'payload' => $request->all(),
        ]);

        return response()->json([
            'serviceId' => $request->input('serviceId'),
            'transId' => $transId,
            'status' => 'CREATED',
            'transTime' => $tx->created_at->getTimestampMs(),
            'data' => $this->invoiceData($payment),
            'amount' => $tx->amount_minor,
        ]);
    }

    /** Подтверждение: деньги списаны — закрываем счёт и начисляем купленное. */
    private function confirm(Request $request): JsonResponse
    {
        $tx = $this->transaction((string) $request->input('transId'));

        if ($tx === null) {
            return $this->error($request, self::ERROR_TRANSACTION_NOT_FOUND);
        }

        if ($tx->state === PaymentTransaction::STATE_CANCELLED) {
            return $this->error($request, self::ERROR_TRANSACTION_CANCELLED);
        }

        if ($tx->state === PaymentTransaction::STATE_PERFORMED) {
            return $this->error($request, self::ERROR_ALREADY_CONFIRMED, [
                'confirmTime' => $tx->performed_at?->getTimestampMs(),
            ]);
        }

        // Просроченную транзакцию подтверждать нельзя — гасим её
        // и отвечаем «отменена», чтобы Uzum вернул деньги покупателю
        $timeout = (int) config('payments.providers.uzum.confirm_timeout_minutes', 30);

        if ($tx->created_at->addMinutes($timeout)->isPast()) {
            $tx->fill(['state' => PaymentTransaction::STATE_CANCELLED, 'cancelled_at' => now()])->save();

            return $this->error($request, self::ERROR_TRANSACTION_CANCELLED);
        }

        $payment = $tx->payment;

        // Счёт успели оплатить переводом, пока шла карточная оплата.
        // Начислять второй раз нельзя — отвечаем «уже оплачен», и Uzum
        // возвращает деньги по своей транзакции
        if ($payment === null || $payment->status === 'paid') {
            return $this->error($request, self::ERROR_ALREADY_PAID);
        }

        app(OrderService::class)->markPaid($payment, [
            'provider' => 'uzum',
            'external_id' => $tx->provider_transaction_id,
        ]);

        $tx->fill(['state' => PaymentTransaction::STATE_PERFORMED, 'performed_at' => now()])->save();

        return response()->json([
            'serviceId' => $request->input('serviceId'),
            'transId' => $tx->provider_transaction_id,
            'status' => 'CONFIRMED',
            'confirmTime' => $tx->performed_at->getTimestampMs(),
            'data' => $this->invoiceData($payment),
            'amount' => $tx->amount_minor,
        ]);
    }

    /**
     * Отмена транзакции со стороны Uzum.
     *
     * Отменяется транзакция, а не счёт: покупатель передумал платить
     * картой, но счёт остаётся — его можно оплатить переводом или
     * другой попыткой. Подтверждённую транзакцию не отменяем: тариф
     * уже начислен и работает, возврат — отдельная процедура через
     * поддержку, а не автоматический вызов.
     */
    private function reverse(Request $request): JsonResponse
    {
        $tx = $this->transaction((string) $request->input('transId'));

        if ($tx === null) {
            return $this->error($request, self::ERROR_TRANSACTION_NOT_FOUND);
        }

        if ($tx->state === PaymentTransaction::STATE_CANCELLED) {
            return $this->error($request, self::ERROR_ALREADY_REVERSED, [
                'reverseTime' => $tx->cancelled_at?->getTimestampMs(),
            ]);
        }

        if ($tx->state === PaymentTransaction::STATE_PERFORMED) {
            return $this->error($request, self::ERROR_CANNOT_REVERSE);
        }

        $tx->fill(['state' => PaymentTransaction::STATE_CANCELLED, 'cancelled_at' => now()])->save();

        return response()->json([
            'serviceId' => $request->input('serviceId'),
            'transId' => $tx->provider_transaction_id,
            'status' => 'REVERSED',
            'reverseTime' => $tx->cancelled_at->getTimestampMs(),
            'data' => $tx->payment !== null ? $this->invoiceData($tx->payment) : [],
            'amount' => $tx->amount_minor,
        ]);
    }

    /** Сверка: текущее состояние транзакции и времена переходов. */
    private function status(Request $request): JsonResponse
    {
        $tx = $this->transaction((string) $request->input('transId'));

        if ($tx === null) {
            return $this->error($request, self::ERROR_TRANSACTION_NOT_FOUND);
        }

        return response()->json([
            'serviceId' => $request->input('serviceId'),
            'transId' => $tx->provider_transaction_id,
            'status' => self::STATE_LABELS[$tx->state] ?? $tx->state,
            'transTime' => $tx->created_at->getTimestampMs(),
            'confirmTime' => $tx->performed_at?->getTimestampMs(),
            'reverseTime' => $tx->cancelled_at?->getTimestampMs(),
            'data' => $tx->payment !== null ? $this->invoiceData($tx->payment) : [],
            'amount' => $tx->amount_minor,
        ]);
    }

    // ── Общее ────────────────────────────────────────────────

    /**
     * Basic auth по логину и паролю, согласованным с Uzum.
     *
     * Пустые значения в конфиге запирают эндпойнты: сравнение с пустой
     * строкой не проходит никогда, а не «пускает всех».
     */
    private function authorized(Request $request): bool
    {
        $login = (string) config('payments.providers.uzum.callback_login', '');
        $password = (string) config('payments.providers.uzum.callback_password', '');

        return $login !== '' && $password !== ''
            && hash_equals($login, (string) $request->getUser())
            && hash_equals($password, (string) $request->getPassword());
    }

    /**
     * Счёт из params, если он существует и ждёт оплаты.
     *
     * @return array{0: Payment|null, 1: int}
     */
    private function payableInvoice(Request $request): array
    {
        $field = (string) config('payments.providers.uzum.account_field', 'invoice');
        $number = (string) $request->input("params.{$field}", '');

        if ($number === '') {
            return [null, self::ERROR_PARAMS_MISSING];
        }

        $payment = Payment::query()->where('number', $number)->first();

        if ($payment === null) {
            return [null, self::ERROR_INVOICE_NOT_FOUND];
        }

        if ($payment->status === 'paid') {
            return [null, self::ERROR_ALREADY_PAID];
        }

        if ($payment->status !== 'pending') {
            return [null, self::ERROR_INVOICE_CANCELLED];
        }

        return [$payment, 0];
    }

    /** @return array<string, mixed> */
    private function invoiceData(Payment $payment): array
    {
        return [
            'invoice' => $payment->number,
            'description' => $payment->description,
            'amount' => $payment->amountMinor(),
        ];
    }

    private function transaction(string $transId): ?PaymentTransaction
    {
        if ($transId === '') {
            return null;
        }

        return PaymentTransaction::query()
            ->where('provider', 'uzum')
            ->where('provider_transaction_id', $transId)
            ->first();
    }

    /** @param array<string, mixed> $extra */
    private function error(Request $request, int $code, array $extra = [], int $status = 400): JsonResponse
    {
        return response()->json([
            'serviceId' => $request->input('serviceId'),
            'timestamp' => $request->input('timestamp'),
            'transId' => $request->input('transId'),
            'status' => 'FAILED',
            'errorCode' => $code,
            ...$extra,
        ], $status);
    }
}
