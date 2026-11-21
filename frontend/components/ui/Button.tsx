import React from "react";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "outline" | "danger" | "ghost";
  size?: "sm" | "md" | "lg";
  isLoading?: boolean;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = "primary",
  size = "md",
  isLoading = false,
  className = "",
  disabled,
  ...props
}) => {
  const base = "inline-flex items-center justify-center font-semibold rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-slate-900/15 focus:ring-offset-1 disabled:opacity-50 disabled:pointer-events-none";

  const variants = {
    primary: "bg-[#111827] text-white hover:bg-[#1F2937] active:bg-[#000000] border border-transparent shadow-xs",
    secondary: "bg-white text-[#111827] hover:bg-[#F9F9F9] border border-[#E5E5E5] shadow-xs",
    outline: "border border-[#E5E5E5] text-[#374151] hover:bg-[#F9F9F9] bg-transparent",
    danger: "bg-rose-600 text-white hover:bg-rose-700 shadow-xs",
    ghost: "text-[#4B5563] hover:bg-[#F3F3F3] hover:text-[#111827]",
  };

  const sizes = {
    sm: "px-2.5 py-1.5 text-xs font-medium leading-4 gap-1.5",
    md: "px-3.5 py-2 text-sm font-semibold leading-5 gap-2",
    lg: "px-4.5 py-2.5 text-sm font-semibold leading-5 gap-2",
  };

  return (
    <button
      className={`${base} ${variants[variant]} ${sizes[size]} ${className}`}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? (
        <span className="flex items-center gap-2">
          <svg className="animate-spin h-3.5 w-3.5 text-current" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <span>Loading...</span>
        </span>
      ) : (
        children
      )}
    </button>
  );
};
