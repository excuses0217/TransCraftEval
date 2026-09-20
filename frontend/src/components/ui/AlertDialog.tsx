import * as React from 'react'
import * as AlertDialogPrimitive from '@radix-ui/react-alert-dialog'
import { cn } from '../../lib/utils'

export const AlertDialog = AlertDialogPrimitive.Root
export const AlertDialogTrigger = AlertDialogPrimitive.Trigger
export const AlertDialogAction = AlertDialogPrimitive.Action
export const AlertDialogCancel = AlertDialogPrimitive.Cancel

export const AlertDialogContent = React.forwardRef<React.ElementRef<typeof AlertDialogPrimitive.Content>, React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Content>>(({ className, ...props }, ref) => (
  <AlertDialogPrimitive.Portal>
    <AlertDialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/50" />
    <AlertDialogPrimitive.Content ref={ref} className={cn('fixed left-1/2 top-1/2 z-50 grid w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 gap-4 rounded-lg border border-border bg-card p-6 text-card-foreground shadow-lg outline-none', className)} {...props} />
  </AlertDialogPrimitive.Portal>
))
AlertDialogContent.displayName = AlertDialogPrimitive.Content.displayName

export function AlertDialogHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) { return <div className={cn('space-y-2 text-left', className)} {...props} /> }
export function AlertDialogFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) { return <div className={cn('flex flex-col-reverse gap-2 sm:flex-row sm:justify-end', className)} {...props} /> }
export const AlertDialogTitle = React.forwardRef<React.ElementRef<typeof AlertDialogPrimitive.Title>, React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Title>>(({ className, ...props }, ref) => <AlertDialogPrimitive.Title ref={ref} className={cn('text-base font-semibold', className)} {...props} />)
AlertDialogTitle.displayName = AlertDialogPrimitive.Title.displayName
export const AlertDialogDescription = React.forwardRef<React.ElementRef<typeof AlertDialogPrimitive.Description>, React.ComponentPropsWithoutRef<typeof AlertDialogPrimitive.Description>>(({ className, ...props }, ref) => <AlertDialogPrimitive.Description ref={ref} className={cn('text-sm text-muted-foreground', className)} {...props} />)
AlertDialogDescription.displayName = AlertDialogPrimitive.Description.displayName
