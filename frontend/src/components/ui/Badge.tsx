import type { HTMLAttributes } from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '../../lib/utils'

const styles = cva('inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium leading-4 whitespace-nowrap [&_svg]:size-3 [&_svg]:shrink-0', {
  variants: {
    variant: {
      default: 'border-transparent bg-primary text-primary-foreground',
      secondary: 'border-transparent bg-muted text-muted-foreground',
      outline: 'border-border bg-background text-muted-foreground',
      info: 'border-info/20 bg-info/10 text-info',
      success: 'border-success/20 bg-success/10 text-success',
      warning: 'border-warning/25 bg-warning/10 text-amber-700',
      destructive: 'border-critical/20 bg-critical/10 text-critical'
    }
  },
  defaultVariants: { variant: 'secondary' }
})

export function Badge({ className, variant, ...props }: HTMLAttributes<HTMLSpanElement> & VariantProps<typeof styles>) {
  return <span className={cn(styles({ variant }), className)} {...props} />
}
