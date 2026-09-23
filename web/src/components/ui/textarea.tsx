import * as React from 'react'
import { cn } from '@/lib/utils'
function Textarea({ className, ...props }: React.ComponentProps<'textarea'>) { return <textarea data-slot="textarea" className={cn('min-h-28 w-full resize-y rounded-lg border border-[#dfe6e0] bg-white px-3 py-2.5 text-sm leading-6 text-[#1d3027] outline-none focus:border-[#79b09b] focus:ring-2 focus:ring-[#d8eee4]', className)} {...props} /> }
export { Textarea }
