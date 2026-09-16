"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";

const FAQS = [
  {
    q: "Is my audio uploaded anywhere?",
    a: "No. UVR Local runs entirely on your own GPU. Your files never leave your machine — separation, ensemble and downloads all happen locally.",
  },
  {
    q: "What hardware do I need?",
    a: "Any NVIDIA GPU with at least 4 GB VRAM works well. An RTX 2060 (like the one this stack runs on) processes a 3-minute song in well under a minute. CPU-only mode is supported but slower.",
  },
  {
    q: "Which models are included?",
    a: "All the open-source favorites: BS-RoFormer, Mel-Band RoFormer, MDX23C, HTDemucs, and more — 80+ architectures. Models auto-download on first use from their verified Hugging Face sources.",
  },
  {
    q: "What is the ensemble engine?",
    a: "Ensembling runs 2–6 models on the same track and fuses their stems in the frequency or time domain (avg/median/max/min). This dramatically reduces artifacts and bleed — a feature the big sites charge extra for.",
  },
  {
    q: "Can I use it for commercial work?",
    a: "Yes. Because everything runs locally, there are no usage caps, no watermarks and no licensing restrictions beyond the model licenses themselves.",
  },
  {
    q: "Does it work with long files?",
    a: "Yes — up to 1 GB per upload. Long tracks are chunked automatically and reassembled seamlessly.",
  },
];

export function FAQ({ className }: { className?: string }) {
  return (
    <section id="faq" className={cn("mx-auto max-w-3xl px-4 py-16", className)}>
      <div className="mb-10 text-center">
        <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
          Frequently asked questions
        </h2>
        <p className="mt-3 text-muted-foreground">
          Everything you need to know about running UVR locally.
        </p>
      </div>
      <Accordion type="single" collapsible className="space-y-2">
        {FAQS.map((f, i) => (
          <div
            key={f.q}
            className={cn(
              "glass-card animate-slide-up px-5",
              `animation-delay-${(i + 1) * 100}`,
            )}
          >
            <AccordionItem value={f.q} className="border-0">
              <AccordionTrigger className="text-left">
                {f.q}
              </AccordionTrigger>
              <AccordionContent className="text-muted-foreground">
                {f.a}
              </AccordionContent>
            </AccordionItem>
          </div>
        ))}
      </Accordion>
    </section>
  );
}