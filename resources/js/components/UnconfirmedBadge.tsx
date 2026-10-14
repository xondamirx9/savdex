import { MailWarning } from 'lucide-react';
import { t } from '@/lib/i18n';

/**
 * «Не подтверждено»: компания зарегистрирована без кода из письма
 * (страна с галочкой «Регистрация без кода»). Метку видят все — и сам
 * владелец, и покупатели; снимает её только подтверждение почты кодом.
 */
export function UnconfirmedBadge({ className = '' }: { className?: string }) {
    return (
        <span className={`badge badge-warning ${className}`.trim()} title={t('common.unconfirmed_hint')}>
            <MailWarning aria-hidden className="size-3.5" />
            {t('common.unconfirmed')}
        </span>
    );
}
