import type { HTMLAttributes, TableHTMLAttributes, ThHTMLAttributes, TdHTMLAttributes } from 'react'
import { cn } from '../../lib/utils'

export function Table({ className, ...props }: TableHTMLAttributes<HTMLTableElement>) { return <div className="overflow-x-auto"><table className={cn('w-full min-w-[760px] caption-bottom text-sm', className)} {...props} /></div> }
export function TableHeader({ className, ...props }: HTMLAttributes<HTMLTableSectionElement>) { return <thead className={cn('border-b bg-muted/35 text-left text-xs text-muted-foreground', className)} {...props} /> }
export function TableBody(props: HTMLAttributes<HTMLTableSectionElement>) { return <tbody {...props} /> }
export function TableRow({ className, ...props }: HTMLAttributes<HTMLTableRowElement>) { return <tr className={cn('border-b transition-colors hover:bg-muted/35 data-[state=selected]:bg-muted/55 last:border-b-0', className)} {...props} /> }
export function TableHead({ className, ...props }: ThHTMLAttributes<HTMLTableCellElement>) { return <th className={cn('h-10 px-4 font-medium', className)} {...props} /> }
export function TableCell({ className, ...props }: TdHTMLAttributes<HTMLTableCellElement>) { return <td className={cn('px-4 py-3 align-middle', className)} {...props} /> }
