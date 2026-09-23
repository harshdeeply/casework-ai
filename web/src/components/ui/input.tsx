import * as React from 'react'
import { cn } from '@/lib/utils'
function Input({ className, ...props }: React.ComponentProps<'input'>) { return <input data-slot="input" className={cn('h-10 w-full rounded-lg border border-[#dfe6e0] bg-white px-3 text-sm text-[#1d3027] outline-none placeholder:text-[#9ba7a0] focus:border-[#79b09b] focus:ring-2 focus:ring-[#d8eee4]', className)} {...props} /> }
export { Input }
