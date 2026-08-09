import { AlertCircle, AlertTriangle, CheckCircle2, Info } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

export type AlertTone = 'info' | 'success' | 'warning' | 'danger';

const TONES: Record<AlertTone, { box: string; icon: typeof Info }> = {
    info: { box: 'bg-primary-50 text-primary-900', icon: Info },
    success: { box: 'bg-success-bg text-green-900', icon: CheckCircle2 },
    warning: { box: 'bg-warning-bg text-amber-900', icon: AlertTriangle },
    danger: { box: 'bg-danger-bg text-red-900', icon: AlertCircle },
};

/**
 * Сообщение о состоянии.
 * Тон передаётся не только цветом, но и иконкой — правило 3 из §1 QA.md.
 */
export function Alert({
    tone = 'info',
    children,
    className,
}: {
    tone?: AlertTone;
    children: ReactNode;
    className?: string;
}) {
    const { box, icon: Icon } = TONES[tone];

    return (
        <div
            role={tone === 'danger' ? 'alert' : 'status'}
            className={cn('rounded-btn flex gap-3 px-4 py-3.5 text-sm leading-relaxed', box, className)}
        >
            <Icon aria-hidden className="mt-0.5 size-5 shrink-0" />
            <div>{children}</div>
        </div>
    );
}
