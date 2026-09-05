import { cva, type VariantProps } from 'class-variance-authority';
import type { ComponentProps } from 'react';

import { cn } from '@/lib/utils';

const alertVariants = cva('rounded-md border px-4 py-3 text-sm', {
  variants: {
    variant: {
      default: 'border-border bg-muted text-foreground',
      warning: 'border-warning/50 bg-warning/10 text-warning',
      destructive: 'border-destructive/50 bg-destructive/10 text-destructive',
    },
  },
  defaultVariants: {
    variant: 'default',
  },
});

type AlertProps = ComponentProps<'div'> & VariantProps<typeof alertVariants>;

/** `role="alert"` — сообщение об ошибке должно объявляться, а не только показываться. */
export function Alert({ className, variant, ...props }: AlertProps) {
  return <div role="alert" className={cn(alertVariants({ variant }), className)} {...props} />;
}

export type { AlertProps };
