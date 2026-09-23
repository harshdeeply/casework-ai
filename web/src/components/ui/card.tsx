import * as React from 'react'
import { cn } from '@/lib/utils'
function Card({ className, ...props }: React.ComponentProps<'div'>) { return <div data-slot="card" className={cn('rounded-2xl border border-[#e8e8e8] bg-white shadow-[0_3px_20px_rgba(21,48,36,.035)]', className)} {...props} /> }
function CardHeader({ className, ...props }: React.ComponentProps<'div'>) { return <div data-slot="card-header" className={cn('flex flex-col gap-1 px-6 pt-6', className)} {...props} /> }
function CardTitle({ className, ...props }: React.ComponentProps<'h3'>) { return <h3 data-slot="card-title" className={cn('font-semibold tracking-[-.02em]', className)} {...props} /> }
function CardDescription({ className, ...props }: React.ComponentProps<'p'>) { return <p data-slot="card-description" className={cn('text-sm text-[#808080]', className)} {...props} /> }
function CardContent({ className, ...props }: React.ComponentProps<'div'>) { return <div data-slot="card-content" className={cn('px-6 pb-6', className)} {...props} /> }
export { Card, CardHeader, CardTitle, CardDescription, CardContent }
