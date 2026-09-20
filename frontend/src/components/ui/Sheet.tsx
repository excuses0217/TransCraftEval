import * as React from 'react'
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { Button } from './Button'
import { cn } from '../../lib/utils'

export const Sheet = DialogPrimitive.Root
export const SheetTrigger = DialogPrimitive.Trigger
export const SheetClose = DialogPrimitive.Close
export const SheetTitle = DialogPrimitive.Title
export const SheetDescription = DialogPrimitive.Description

export const SheetContent = React.forwardRef<React.ElementRef<typeof DialogPrimitive.Content>, React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> & { closeLabel?: string }>(({ className, children, closeLabel = '关闭', ...props }, ref) => (
  <DialogPrimitive.Portal>
    <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/50 md:hidden" />
    <DialogPrimitive.Content ref={ref} className={cn('fixed inset-y-0 left-0 z-50 flex w-[min(20rem,85vw)] flex-col border-r border-border bg-background text-foreground shadow-lg outline-none md:hidden', className)} {...props}>
      {children}
      <DialogPrimitive.Close asChild><Button type="button" variant="ghost" size="icon-sm" className="absolute right-3 top-3" aria-label={closeLabel}><X className="size-4" aria-hidden="true" /></Button></DialogPrimitive.Close>
    </DialogPrimitive.Content>
  </DialogPrimitive.Portal>
))
SheetContent.displayName = DialogPrimitive.Content.displayName
