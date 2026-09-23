import * as React from 'react'
import { cn } from '@/lib/utils'
function Textarea({ className, ...props }: React.ComponentProps<'textarea'>) { return <textarea data-slot="textarea" className={cn('min-h-28 w-full resize-y rounded-lg border border-[#e8e8e8] bg-white px-3 py-2.5 text-sm leading-6 text-[#282828] outline-none focus:border-[#a0a0a0] focus:ring-2 focus:ring-[#e8e8e8]', className)} {...props} /> }
export { Textarea }
