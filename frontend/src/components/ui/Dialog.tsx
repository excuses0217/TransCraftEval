import * as React from 'react'
import * as Primitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { cn } from '../../lib/utils'
import { Button } from './Button'

export const Dialog = Primitive.Root
export const DialogTrigger = Primitive.Trigger
export const DialogClose = Primitive.Close
export const DialogTitle = ({ className, ...props }: React.ComponentProps<typeof Primitive.Title>) => <Primitive.Title className={cn('text-lg font-semibold tracking-tight', className)} {...props} />
export const DialogDescription = ({ className, ...props }: React.ComponentProps<typeof Primitive.Description>) => <Primitive.Description className={cn('mt-1 text-sm text-muted-foreground', className)} {...props} />

export function DialogContent({ className, children, size = 'md', ...props }: React.ComponentProps<typeof Primitive.Content> & { size?: 'sm' | 'md' | 'lg' }) {
  const width = { sm: 'max-w-md', md: 'max-w-2xl', lg: 'max-w-5xl' }[size]
  return <Primitive.Portal><Primitive.Overlay className="fixed inset-0 z-50 bg-black/50" /><Primitive.Content className={cn('fixed left-1/2 top-1/2 z-50 flex max-h-[90dvh] w-[calc(100vw-2rem)] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-lg border border-border bg-background shadow-xl outline-none', width, className)} {...props}>{children}<Primitive.Close asChild><Button variant="ghost" size="icon-sm" className="absolute right-3 top-3" aria-label="关闭"><X className="size-4" /></Button></Primitive.Close></Primitive.Content></Primitive.Portal>
}
export function DialogHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) { return <div className={cn('border-b border-border px-5 py-4 pr-14', className)} {...props} /> }
export function DialogBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) { return <div className={cn('min-h-0 overflow-y-auto px-5 py-5', className)} {...props} /> }
export function DialogFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) { return <div className={cn('flex justify-end gap-2 border-t border-border px-5 py-4', className)} {...props} /> }
