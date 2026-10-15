import '../../../css/ilmora.css';
import { usePage } from '@inertiajs/react';
import { ArrowRight } from 'lucide-react';
import { IlmoraLogo } from '@/components/ilmora/IlmoraLogo';
import { Link } from '@/components/ui/Link';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';
import type { SharedProps } from '@/types';

/**
 * Кнопка-плашка «Регистрация в ILMORA» на первом шаге регистрации Savdex:
 * светлая полупрозрачная на тёмной панели, со знаком ILMORA. Ведёт на
 * свою форму ILMORA (/register/ilmora-register) — с языком, как все ссылки.
 * У ILMORA два языка — русский и узбекский: на en, tr и zh кнопки нет.
 */
export function IlmoraRegisterLink() {
    const { locale } = usePage<SharedProps>().props;

    if (locale !== 'ru' && locale !== 'uz') return null;

    return (
        <Link href={routes.ilmoraRegister} className="ilmora-cta">
            <IlmoraLogo compact />
            <span className="ilmora-cta__text">
                <span className="ilmora-cta__title">{t('ilmora.cta')}</span>
                <span className="ilmora-cta__hint">{t('ilmora.cta_hint')}</span>
            </span>
            <ArrowRight aria-hidden className="ilmora-cta__arrow size-4" />
        </Link>
    );
}
