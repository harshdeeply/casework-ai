import * as React from 'react'
import { cn } from '@/lib/utils'
function Badge({ className, ...props }: React.ComponentProps<'span'>) { return <span data-slot="badge" className={cn('inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-[11px] font-semibold tracking-[.02em]', className)} {...props} /> }
export { Badge }
