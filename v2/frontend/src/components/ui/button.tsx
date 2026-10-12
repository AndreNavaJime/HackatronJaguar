import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';

/**
 * shadcn/ui Button pattern (Radix Slot + CVA), themed with the existing
 * PantheraLAB CSS instead of adding a second, conflicting Tailwind reset.
 */
const buttonVariants = cva('ui-button', {
  variants: {
    variant: {
      default: 'ui-button-default',
      ghost: 'ui-button-ghost',
      outline: 'ui-button-outline',
    },
    size: {
      default: 'ui-button-size-default',
      sm: 'ui-button-size-sm',
      icon: 'ui-button-size-icon',
    },
  },
  defaultVariants: { variant: 'default', size: 'default' },
});

type ButtonProps = React.ComponentProps<'button'> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean };

function Button({
  className,
  variant = 'default',
  size = 'default',
  asChild = false,
  ...props
}: ButtonProps) {
  const Component = asChild ? Slot : 'button';

  return <Component
    data-slot="button"
    className={[buttonVariants({ variant, size }), className].filter(Boolean).join(' ')}
    {...props}
  />;
}

export { Button, buttonVariants };
