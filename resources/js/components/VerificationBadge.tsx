import { CheckCircle2, Shield } from 'lucide-react';
import { t } from '@/lib/i18n';

/**
 * Бейдж уровня проверки компании.
 *
 * Один компонент на витрину поставщиков, каталог компаний и визитку:
 * уровни и подписи обязаны совпадать везде, где бейдж показывается, —
 * иначе одна и та же компания читалась бы по-разному на разных страницах.
 */
export function VerificationBadge({ level }: { level: number }) {
    if (level >= 3)
        return (
            <span className="badge badge-gold" title={t('verification.gold_hint')}>
                <Shield aria-hidden className="size-3.5" /> {t('verification.gold')}
            </span>
        );

    if (level >= 2)
        return (
            <span className="badge badge-verified" title={t('verification.verified_hint')}>
                <CheckCircle2 aria-hidden className="size-3.5" /> {t('verification.verified')}
            </span>
        );

    return (
        <span className="badge badge-neutral" title={t('verification.none_hint')}>
            {t('verification.none')}
        </span>
    );
}
