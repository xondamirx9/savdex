import { Mail, Phone } from 'lucide-react';
import { t } from '@/lib/i18n';

export interface CardData {
    kind: 'photo' | 'generated';
    image: string | null;
    company_name: string | null;
    full_name: string | null;
    email: string | null;
    phone: string | null;
}

/**
 * Визитка: фото настоящей или собранная площадкой из полей.
 *
 * Собранная — в пропорциях бумажной (90×50 мм): так она привычно
 * читается и не теряется на экране телефона. Почта и телефон —
 * ссылки: отсканировавший QR звонит и пишет одним нажатием.
 */
export function BusinessCard({ card, links = false }: { card: CardData; links?: boolean }) {
    const name = card.full_name ?? card.company_name ?? '';

    if (card.kind === 'photo' && card.image) {
        return <img src={card.image} alt={t('cards.card_alt', { name })} className="biz-card-photo" />;
    }

    const phone = card.phone ?? '';
    const email = card.email ?? '';

    return (
        <div className="biz-card" role="img" aria-label={t('cards.card_alt', { name })}>
            <div className="biz-card-company">{card.company_name}</div>
            <div className="biz-card-bottom">
                <div className="biz-card-name">{card.full_name}</div>
                <div className="biz-card-contacts">
                    {phone &&
                        (links ? (
                            <a href={`tel:${phone.replace(/[^\d+]/g, '')}`}>
                                <Phone aria-hidden className="size-3.5" /> {phone}
                            </a>
                        ) : (
                            <span>
                                <Phone aria-hidden className="size-3.5" /> {phone}
                            </span>
                        ))}
                    {email &&
                        (links ? (
                            <a href={`mailto:${email}`}>
                                <Mail aria-hidden className="size-3.5" /> {email}
                            </a>
                        ) : (
                            <span>
                                <Mail aria-hidden className="size-3.5" /> {email}
                            </span>
                        ))}
                </div>
            </div>
        </div>
    );
}
