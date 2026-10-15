import '../../../css/ilmora.css';
import { ArrowRight } from 'lucide-react';
import { IlmoraLogo } from '@/components/ilmora/IlmoraLogo';
import { Link } from '@/components/ui/Link';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

/**
 * Кнопка-плашка «Регистрация в ILMORA» на первом шаге регистрации Savdex:
 * светлая полупрозрачная на тёмной панели, со знаком ILMORA. Ведёт на
 * свою форму ILMORA (/register/ilmora-register) — с языком, как все ссылки.
 */
export function IlmoraRegisterLink() {
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
