import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva('inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 disabled:pointer-events-none disabled:opacity-45 [&_svg]:size-4', {
  variants: {
    variant: {
      default: 'bg-[#16624c] text-white hover:bg-[#0f4e3b]',
      secondary: 'bg-[#ebf2ef] text-[#165743] hover:bg-[#dce9e3]',
      outline: 'border border-[#d9dfdb] bg-white text-[#23342e] hover:bg-[#f4f7f5]',
      ghost: 'text-[#52615a] hover:bg-[#eef2ef] hover:text-[#20382f]',
      destructive: 'bg-[#b9483e] text-white hover:bg-[#943b32]',
    },
    size: { default: 'h-10 px-4 py-2', sm: 'h-9 px-3', lg: 'h-11 px-5', icon: 'size-10' },
  }, defaultVariants: { variant: 'default', size: 'default' },
})
function Button({ className, variant, size, asChild = false, ...props }: React.ComponentProps<'button'> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : 'button'
  return <Comp data-slot="button" className={cn(buttonVariants({ variant, size, className }))} {...props} />
}
export { Button }
