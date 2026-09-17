"use client";

import * as React from "react";
import Link from "next/link";
import { AudioWaveform } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";

const COLUMNS: { title: string; links: { label: string; href: string }[] }[] = [
  {
    title: "Tools",
    links: [
      { label: "Vocal Remover", href: "/tools/vocal-remover" },
      { label: "Extract Vocals", href: "/tools/extract-vocals" },
      { label: "Karaoke Maker", href: "/tools/karaoke" },
      { label: "Stem Splitter", href: "/tools/stem-splitter" },
      { label: "Noise Removal", href: "/tools/denoise" },
      { label: "Acapella Extractor", href: "/tools/acapella" },
    ],
  },
  {
    title: "Product",
    links: [
      { label: "Explore models", href: "/explore" },
      { label: "Free & open", href: "/pricing" },
    ],
  },
  {
    title: "Support",
    links: [{ label: "FAQ", href: "/faq" }],
  },
];

export function Footer() {
  return (
    <footer className="glass-surface border-t border-glass-border">
      <div className="mx-auto max-w-container px-4 py-12">
        {/* Desktop: 7-column grid */}
        <div className="hidden grid-cols-12 gap-8 lg:grid">
          <div className="col-span-3">
            <Link href="/" className="flex items-center gap-2 font-semibold">
              <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-primary text-primary-foreground">
                <AudioWaveform className="h-4 w-4" />
              </span>
              UVR Local
            </Link>
            <p className="mt-3 max-w-xs text-sm text-muted-foreground">
              Professional vocal &amp; music separation, running 100% on your own
              GPU. No uploads, no limits.
            </p>
          </div>
          {COLUMNS.map((col) => (
            <div key={col.title} className="col-span-2">
              <h2 className="text-sm font-semibold">{col.title}</h2>
              <ul className="mt-3 flex flex-col gap-2">
                {col.links.map((l) => (
                  <li key={l.label}>
                    <Link
                      href={l.href}
                      className="text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-indigo-500/50 rounded"
                    >
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          <div className="col-span-1" aria-hidden />
        </div>

        {/* Mobile: accordion */}
        <div className="lg:hidden">
          <Accordion type="single" collapsible>
            {COLUMNS.map((col) => (
              <AccordionItem key={col.title} value={col.title}>
                <AccordionTrigger>{col.title}</AccordionTrigger>
                <AccordionContent>
                  <ul className="flex flex-col gap-2">
                    {col.links.map((l) => (
                      <li key={l.label}>
                        <Link
                          href={l.href}
                          className="text-sm text-muted-foreground hover:text-foreground"
                        >
                          {l.label}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </div>

        <div className="mt-10 flex flex-col items-center justify-between gap-3 border-t border-glass-border pt-6 text-xs text-muted-foreground sm:flex-row">
          <p>© {new Date().getFullYear()} UVR Local. All rights reserved.</p>
          <p className={cn("flex items-center gap-1.5")}>
            <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
            All processing happens on your machine
          </p>
        </div>
      </div>
    </footer>
  );
}