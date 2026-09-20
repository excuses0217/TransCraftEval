import * as React from 'react'
import * as CheckboxPrimitive from '@radix-ui/react-checkbox'
import { Check, Minus } from 'lucide-react'
import { cn } from '../../lib/utils'

export const Checkbox = React.forwardRef<React.ElementRef<typeof CheckboxPrimitive.Root>, React.ComponentPropsWithoutRef<typeof CheckboxPrimitive.Root>>(({ className, ...props }, ref) => (
  <CheckboxPrimitive.Root ref={ref} className={cn('peer grid size-4 shrink-0 place-items-center rounded border border-input bg-background shadow-sm outline-none transition-colors focus-visible:ring-2 focus-visible:ring-primary/25 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=checked]:text-primary-foreground data-[state=indeterminate]:border-primary data-[state=indeterminate]:bg-primary data-[state=indeterminate]:text-primary-foreground', className)} {...props}>
    <CheckboxPrimitive.Indicator>{props.checked === 'indeterminate' ? <Minus className="size-3" aria-hidden="true" /> : <Check className="size-3" aria-hidden="true" />}</CheckboxPrimitive.Indicator>
  </CheckboxPrimitive.Root>
))
Checkbox.displayName = CheckboxPrimitive.Root.displayName
