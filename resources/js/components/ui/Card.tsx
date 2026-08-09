import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

export function Card({ children, className }: { children: ReactNode; className?: string }) {
    return (
        <div className={cn('bg-surface border-line rounded-card border p-6', className)}>{children}</div>
    );
}
