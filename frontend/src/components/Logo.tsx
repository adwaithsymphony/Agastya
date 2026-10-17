import { useState } from "react";
import { cn } from "./ui";

/**
 * Brand mark. The supplied emblem (public/assets/agastya-logo.svg) is used as-is; it has its own
 * cream background, so it sits in a rounded tile on both light and dark surfaces. If the file is
 * missing, a neutral monogram tile is shown instead.
 */
const LOGO_SRC = "/assets/agastya-logo.svg";

export function Logo({ tone = "dark", size = 32, wordmark = true, className }: { tone?: "dark" | "light"; size?: number; wordmark?: boolean; className?: string }) {
  const [missing, setMissing] = useState(false);
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      {!missing ? (
        <img
          src={LOGO_SRC}
          alt={wordmark ? "" : "AGASTYA"}
          width={size}
          height={size}
          className={cn("block shrink-0 rounded-[22%] object-contain", tone === "light" && "ring-1 ring-white/15")}
          style={{ width: size, height: size }}
          onError={() => setMissing(true)}
        />
      ) : (
        <span
          aria-hidden="true"
          className={cn(
            "grid shrink-0 place-items-center rounded-md border text-[13px] font-extrabold",
            tone === "light" ? "border-white/40 text-white" : "border-forest/40 text-forest",
          )}
          style={{ width: size, height: size }}
        >
          A
        </span>
      )}
      {wordmark && (
        <span className={cn("text-[17px] font-extrabold tracking-[0.14em]", tone === "light" ? "text-white" : "text-forest-ink")}>AGASTYA</span>
      )}
    </span>
  );
}
