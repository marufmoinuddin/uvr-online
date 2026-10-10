"use client";

import * as React from "react";
import { MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Floating feedback control.
 *
 * Opens a real mailto: rather than an in-app form — this app has no backend to
 * receive one, and the 2026-09-16 audit removed a fake email capture for
 * exactly that reason. A form that silently does nothing is worse than a link
 * that hands the message to the user's own mail client.
 */
const FEEDBACK_EMAIL = "support@uvrlocal.app";

export function FeedbackButton({ className }: { className?: string }) {
  const subject = encodeURIComponent("UVR Local feedback");
  const body = encodeURIComponent(
    [
      "What were you doing?",
      "",
      "What happened?",
      "",
      "What did you expect?",
      "",
      "Browser / OS:",
    ].join("\n"),
  );
  const href = `mailto:${FEEDBACK_EMAIL}?subject=${subject}&body=${body}`;

  return (
    // Wrapped in a complementary landmark: a bare fixed-position link sits
    // outside every landmark, which trips axe `region` ("all page content
    // should be contained by landmarks") on every route.
    <aside
      aria-label="Feedback"
      className="fixed bottom-5 right-5 z-30"
    >
      <a
        href={href}
        aria-label="Send feedback by email"
        title="Send feedback by email"
        className={cn(
          "flex h-11 items-center gap-2 rounded-full border border-white/15 bg-[#12141A]/95 px-4 text-xs font-semibold text-foreground shadow-lg backdrop-blur transition-transform hover:scale-[1.03] focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50 motion-reduce:hover:scale-100",
          className,
        )}
      >
        <MessageSquare className="h-4 w-4" aria-hidden />
        <span className="hidden sm:inline">Feedback</span>
      </a>
    </aside>
  );
}