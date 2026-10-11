import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-accent text-app hover:bg-accent/90 disabled:bg-accent/40 font-medium",
  secondary:
    "bg-raised text-ink border border-line hover:border-ink-faint disabled:opacity-50",
  ghost:
    "text-ink-dim hover:text-ink hover:bg-raised disabled:opacity-50",
  danger:
    "text-down border border-down/40 hover:bg-down/10 disabled:opacity-50",
};

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  children: ReactNode;
}

export function Button({
  variant = "secondary",
  className = "",
  children,
  ...rest
}: Props) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors disabled:cursor-not-allowed ${VARIANTS[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
