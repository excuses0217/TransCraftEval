import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '../../lib/utils'

const styles = cva(
  'inline-flex shrink-0 items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-sm font-medium transition-[background-color,border-color,color,box-shadow,transform] duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground shadow-sm hover:bg-primary/90 active:translate-y-px',
        outline: 'border border-input bg-background text-foreground shadow-[0_1px_1px_hsl(var(--foreground)/0.025)] hover:border-primary/25 hover:bg-accent',
        ghost: 'text-muted-foreground hover:bg-accent hover:text-accent-foreground',
        link: 'h-auto px-0 text-primary underline-offset-4 hover:underline',
        destructive: 'bg-destructive text-white hover:bg-destructive/90',
        success: 'bg-success text-white hover:bg-success/90'
      },
      size: {
        default: 'h-9 px-3.5',
        sm: 'h-8 px-2.5 text-xs [&_svg]:size-3.5',
        lg: 'h-10 px-4',
        icon: 'size-9',
        'icon-sm': 'size-8'
      }
    },
    defaultVariants: { variant: 'default', size: 'default' }
  }
)

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof styles> { asChild?: boolean }

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, asChild = false, ...props }, ref) => {
  const Comp = asChild ? Slot : 'button'
  return <Comp ref={ref} className={cn(styles({ variant, size }), className)} {...props} />
})
Button.displayName = 'Button'
