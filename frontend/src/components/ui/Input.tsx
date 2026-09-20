import * as React from 'react'
import { cn } from '../../lib/utils'

export const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<'input'>>(({ className, ...props }, ref) => (
  <input ref={ref} className={cn('flex h-9 w-full rounded-md border border-input/90 bg-background px-3 py-1 text-sm shadow-[0_1px_1px_hsl(var(--foreground)/0.02)] outline-none transition-[border-color,box-shadow] placeholder:text-muted-foreground focus:border-primary/45 focus:ring-2 focus:ring-primary/15 focus:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-50', className)} {...props} />
))
Input.displayName = 'Input'

export function Field({ label, hint, error, children, className }: { label: React.ReactNode; hint?: React.ReactNode; error?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return <label className={cn('grid gap-1.5 text-sm font-medium text-foreground', className)}>{label}{children}{hint && <span className="text-xs font-normal text-muted-foreground">{hint}</span>}{error && <span className="text-xs font-normal text-destructive" role="alert">{error}</span>}</label>
}
