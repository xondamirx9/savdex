<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Company;
use App\Models\Wallet;
use App\Models\WalletTransaction;
use Illuminate\Foundation\Testing\RefreshDatabase;
use InvalidArgumentException;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Списание с кошелька.
 *
 * Остаток проверяется условием самого UPDATE, а не отдельным чтением:
 * «прочитать баланс, сравнить, записать» пропускает второго между
 * чтением и записью, и два одновременных раскрытия контакта списывали
 * один кредит дважды. lockForUpdate для этого не годился — на SQLite
 * он не блокирует ничего.
 *
 * Гонку в тесте не воспроизвести (нужны два соединения и точное
 * попадание в окно), поэтому проверяется наблюдаемое поведение
 * условного UPDATE: нехватка средств не меняет ни остаток, ни историю.
 */
class WalletSpendTest extends TestCase
{
    use RefreshDatabase;

    private function wallet(int $credits = 0, int $promoUnits = 0): Wallet
    {
        return Wallet::create([
            'company_id' => Company::factory()->create()->id,
            'credits' => $credits,
            'promo_units' => $promoUnits,
        ]);
    }

    #[Test]
    public function списание_уменьшает_остаток_и_пишет_историю(): void
    {
        $wallet = $this->wallet(credits: 5);

        $this->assertTrue($wallet->spend('credits', 2, 'unlock'));

        $this->assertSame(3, $wallet->fresh()->credits);
        $this->assertSame(3, $wallet->credits, 'модель в памяти обязана совпасть с базой');

        $entry = WalletTransaction::query()->latest('id')->firstOrFail();

        $this->assertSame(-2, $entry->amount);
        $this->assertSame(3, $entry->balance_after, 'остаток в истории — после списания');
    }

    #[Test]
    public function нехватка_средств_не_трогает_ни_остаток_ни_историю(): void
    {
        $wallet = $this->wallet(credits: 1);

        $this->assertFalse($wallet->spend('credits', 2, 'unlock'));

        $this->assertSame(1, $wallet->fresh()->credits);
        $this->assertSame(0, WalletTransaction::query()->count());
    }

    /**
     * Ровный остаток расходуется целиком: `>=`, а не `>`. Условие со
     * строгим сравнением оставляло бы последний кредит неизрасходуемым.
     */
    #[Test]
    public function остаток_расходуется_до_нуля(): void
    {
        $wallet = $this->wallet(credits: 2);

        $this->assertTrue($wallet->spend('credits', 2, 'unlock'));
        $this->assertSame(0, $wallet->fresh()->credits);

        $this->assertFalse($wallet->spend('credits', 1, 'unlock'));
    }

    #[Test]
    public function начисление_увеличивает_остаток(): void
    {
        $wallet = $this->wallet(promoUnits: 1);

        $wallet->grant('promo_units', 4, 'pack');

        $this->assertSame(5, $wallet->fresh()->promo_units);
        $this->assertSame(5, WalletTransaction::query()->latest('id')->firstOrFail()->balance_after);
    }

    /**
     * Имя счёта подставляется в SQL как имя колонки. Список закрытый:
     * произвольная строка от вызывающего до запроса не доходит.
     */
    #[Test]
    public function неизвестный_счёт_отклоняется(): void
    {
        $wallet = $this->wallet(credits: 5);

        $this->expectException(InvalidArgumentException::class);

        $wallet->spend('credits; drop table wallets', 1, 'test');
    }
}
