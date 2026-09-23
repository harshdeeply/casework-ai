import * as React from 'react'
import { cn } from '@/lib/utils'
function Input({ className, ...props }: React.ComponentProps<'input'>) { return <input data-slot="input" className={cn('h-10 w-full rounded-lg border border-[#e8e8e8] bg-white px-3 text-sm text-[#282828] outline-none placeholder:text-[#a0a0a0] focus:border-[#a0a0a0] focus:ring-2 focus:ring-[#e8e8e8]', className)} {...props} /> }
export { Input }
