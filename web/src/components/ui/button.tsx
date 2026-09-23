import * as React from 'react'
import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const buttonVariants = cva('inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-500 disabled:pointer-events-none disabled:opacity-45 [&_svg]:size-4', {
  variants: {
    variant: {
      default: 'bg-[#181818] text-white hover:bg-[#303030]',
      secondary: 'bg-[#f0f0f0] text-[#484848] hover:bg-[#e8e8e8]',
      outline: 'border border-[#e0e0e0] bg-white text-[#303030] hover:bg-[#f8f8f8]',
      ghost: 'text-[#606060] hover:bg-[#f0f0f0] hover:text-[#303030]',
      destructive: 'bg-[#606060] text-white hover:bg-[#505050]',
    },
    size: { default: 'h-10 px-4 py-2', sm: 'h-9 px-3', lg: 'h-11 px-5', icon: 'size-10' },
  }, defaultVariants: { variant: 'default', size: 'default' },
})
function Button({ className, variant, size, asChild = false, ...props }: React.ComponentProps<'button'> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : 'button'
  return <Comp data-slot="button" className={cn(buttonVariants({ variant, size, className }))} {...props} />
}
export { Button }
