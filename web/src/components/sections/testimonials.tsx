"use client";

import * as React from "react";
import { Star } from "lucide-react";
import { cn } from "@/lib/utils";

const TESTIMONIALS = [
  {
    name: "Maya R.",
    role: "Music producer",
    quote:
      "The BS-RoFormer models are insanely clean. I stopped paying for cloud separation entirely.",
  },
  {
    name: "Jonas K.",
    role: "Karaoke host",
    quote:
      "Runs on my gaming laptop faster than realtime. The karaoke maker is my daily driver now.",
  },
  {
    name: "Priya S.",
    role: "Podcast editor",
    quote:
      "Noise removal is magic. My interviews sound studio-clean in one pass.",
  },
  {
    name: "Diego M.",
    role: "DJ / remixer",
    quote:
      "The ensemble builder gives me stems that actually hold up on big speakers.",
  },
  {
    name: "Anna L.",
    role: "YouTuber",
    quote:
      "I upload directly from my phone and get 4 stems back in minutes. Huge time saver.",
  },
  {
    name: "Tom W.",
    role: "Audio engineer",
    quote:
      "Finally a tool that respects my privacy — everything stays on my machine.",
  },
];

export function Testimonials({ className }: { className?: string }) {
  const doubled = [...TESTIMONIALS, ...TESTIMONIALS];
  return (
    <section className={cn("mx-auto max-w-container px-4 py-16", className)}>
      <div className="mx-auto mb-10 max-w-2xl text-center">
        <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
          Loved by creators everywhere
        </h2>
        <p className="mt-3 text-muted-foreground">
          Join thousands separating vocals on their own hardware.
        </p>
      </div>
      <div className="relative overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_10%,black_90%,transparent)]">
        <div className="flex w-max animate-marquee gap-4 hover:[animation-play-state:paused]">
          {doubled.map((t, i) => (
            <figure
              key={`${t.name}-${i}`}
              className="glass-card w-80 shrink-0 p-5"
            >
              <div className="flex gap-0.5 text-amber-400">
                {Array.from({ length: 5 }).map((_, j) => (
                  <Star key={j} className="h-3.5 w-3.5 fill-current" />
                ))}
              </div>
              <blockquote className="mt-3 text-sm leading-relaxed">
                “{t.quote}”
              </blockquote>
              <figcaption className="mt-4 flex items-center gap-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary">
                  {t.name[0]}
                </span>
                <div>
                  <p className="text-sm font-medium">{t.name}</p>
                  <p className="text-xs text-muted-foreground">{t.role}</p>
                </div>
              </figcaption>
            </figure>
          ))}
        </div>
      </div>
    </section>
  );
}