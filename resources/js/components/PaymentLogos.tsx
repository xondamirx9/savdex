/**
 * Логотипы платёжных систем для подвала и платёжных страниц.
 *
 * Требование банка-эквайера: на сайте, принимающем оплату картами,
 * должны быть видны логотипы НПС (Uzcard, Humo) и МПС (Visa, Mastercard)
 * вместе с упоминанием 3-D Secure. Знаки нарисованы упрощённо, инлайном:
 * тянуть фирменные комплекты ради четырёх плашек в подвале незачем,
 * а белая плашка обеспечивает контраст на тёмном фоне.
 */

interface BadgeProps {
    label: string;
    children: React.ReactNode;
}

function Badge({ label, children }: BadgeProps) {
    return (
        <span className="pay-badge" role="img" aria-label={label} title={label}>
            {children}
        </span>
    );
}

export function PaymentBadges() {
    return (
        <div className="pay-badges">
            <Badge label="Uzcard">
                <svg viewBox="0 0 56 16" height="12" aria-hidden>
                    <text x="0" y="13" fontFamily="Arial, Helvetica, sans-serif" fontWeight="800" fontSize="13" letterSpacing=".4" fill="#0E4C90">
                        UZ
                        <tspan fill="#29AAE2">CARD</tspan>
                    </text>
                </svg>
            </Badge>
            <Badge label="Humo">
                <svg viewBox="0 0 46 16" height="12" aria-hidden>
                    <text x="0" y="13" fontFamily="Arial, Helvetica, sans-serif" fontWeight="800" fontSize="13" letterSpacing=".4" fill="#164194">
                        HUMO
                    </text>
                    <circle cx="43" cy="4" r="2.4" fill="#F58220" />
                </svg>
            </Badge>
            <Badge label="Visa">
                <svg viewBox="0 0 40 14" height="12" aria-hidden>
                    <text x="0" y="12" fontFamily="Arial, Helvetica, sans-serif" fontWeight="800" fontStyle="italic" fontSize="14" letterSpacing="1" fill="#1434CB">
                        VISA
                    </text>
                </svg>
            </Badge>
            <Badge label="Mastercard">
                <svg viewBox="0 0 38 24" height="17" aria-hidden>
                    <circle cx="13" cy="12" r="11" fill="#EB001B" />
                    <circle cx="25" cy="12" r="11" fill="#F79E1B" />
                    <path
                        d="M19 3.9c2.5 2 4.1 5 4.1 8.1s-1.6 6.1-4.1 8.1c-2.5-2-4.1-5-4.1-8.1s1.6-6.1 4.1-8.1Z"
                        fill="#FF5F00"
                    />
                </svg>
            </Badge>
            <Badge label="3-D Secure">
                <svg viewBox="0 0 66 16" height="12" aria-hidden>
                    <text x="0" y="13" fontFamily="Arial, Helvetica, sans-serif" fontWeight="800" fontSize="12" letterSpacing=".2" fill="#C8102E">
                        3D Secure
                    </text>
                </svg>
            </Badge>
        </div>
    );
}
