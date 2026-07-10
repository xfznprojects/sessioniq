import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";

import { cn } from "../lib/utils";

const cardVariants = cva("rounded-lg border bg-card text-card-foreground", {
  variants: {
    elevation: {
      flat: "",
      raised: "elevate",
      high: "elevate-lg"
    }
  },
  defaultVariants: { elevation: "raised" }
});

export function Card({
  className,
  elevation,
  ...props
}: HTMLAttributes<HTMLDivElement> & VariantProps<typeof cardVariants>) {
  return <div className={cn(cardVariants({ elevation }), className)} {...props} />;
}

const buttonVariants = cva(
  cn(
    "inline-flex items-center justify-center gap-2 rounded-md font-medium",
    "whitespace-nowrap outline-none",
    // Press feedback + color transitions; transform stays snappy (150ms) so the
    // button feels like it's truly listening. Only transform/color animate.
    "transition-[transform,background-color,color,border-color] duration-150 active:scale-[0.98]",
    "focus-visible:ring-2 focus-visible:ring-ring",
    "disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100"
  ),
  {
    variants: {
      variant: {
        primary:
          "bg-accent text-accent-foreground hover:bg-accent-hover shadow-[0_1px_2px_rgba(0,0,0,0.25)]",
        soft: "bg-accent-soft text-accent hover:bg-accent-soft/70 border border-accent/25",
        outline: "border border-border-strong bg-transparent hover:bg-muted text-foreground",
        ghost: "bg-transparent hover:bg-muted text-foreground",
        subtle: "bg-muted text-foreground hover:bg-elevated border border-border",
        danger: "bg-danger text-white hover:bg-danger/90 shadow-[0_1px_2px_rgba(0,0,0,0.25)]"
      },
      size: {
        sm: "h-8 px-2.5 text-xs",
        md: "h-9 px-3.5 text-sm",
        lg: "h-10 px-5 text-sm",
        icon: "size-8 p-0"
      }
    },
    defaultVariants: { variant: "subtle", size: "md" }
  }
);

export function Button({
  className,
  variant,
  size,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants>) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
  {
    variants: {
      tone: {
        neutral: "border-border bg-muted text-muted-foreground",
        accent: "border-accent/30 bg-accent-soft text-accent",
        green: "border-success/30 text-success bg-[color-mix(in_oklab,var(--success)_14%,transparent)]",
        amber: "border-warning/30 text-warning bg-[color-mix(in_oklab,var(--warning)_14%,transparent)]",
        red: "border-danger/30 text-danger bg-[color-mix(in_oklab,var(--danger)_14%,transparent)]",
        blue: "border-accent/30 bg-accent-soft text-accent"
      }
    },
    defaultVariants: { tone: "neutral" }
  }
);

export function Badge({
  className,
  tone,
  ...props
}: HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

export function SectionTitle({
  icon,
  title,
  subtitle,
  actions
}: {
  icon?: ReactNode;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="flex items-start gap-2.5">
        {icon && <span className="mt-0.5 text-accent">{icon}</span>}
        <div>
          <h2 className="text-base font-semibold tracking-tight">{title}</h2>
          {subtitle && <p className="mt-0.5 text-sm text-muted-foreground">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({
  label,
  value,
  hint
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <div className="rounded-md border border-border bg-elevated/60 px-3 py-2.5">
      <div className="text-lg font-semibold tracking-tight">{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
      {hint && <div className="mt-0.5 text-[0.7rem] text-muted-foreground/70">{hint}</div>}
    </div>
  );
}
