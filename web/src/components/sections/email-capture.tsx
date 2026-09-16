"use client";

import * as React from "react";
import { Mail, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export function EmailCapture({ className }: { className?: string }) {
  const [email, setEmail] = React.useState("");
  const [done, setDone] = React.useState(false);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.includes("@")) return;
    setDone(true);
  };

  return (
    <section className={cn("mx-auto max-w-2xl px-4 py-16", className)}>
      <div className="glass-card p-8 text-center">
        <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">
          New models, straight to your inbox
        </h2>
        <p className="mt-2 text-muted-foreground">
          We ship new architectures weekly. No spam, unsubscribe anytime.
        </p>
        {done ? (
          <p className="mt-6 inline-flex items-center gap-2 rounded-full bg-emerald-500/10 px-4 py-2 text-sm font-medium text-emerald-600 dark:text-emerald-400">
            <Check className="h-4 w-4" /> You&apos;re on the list!
          </p>
        ) : (
          <form
            onSubmit={submit}
            className="mx-auto mt-6 flex max-w-md flex-col gap-3 sm:flex-row"
          >
            <div className="relative flex-1">
              <Mail className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="pl-9"
                aria-label="Email address"
              />
            </div>
            <Button type="submit">Subscribe</Button>
          </form>
        )}
      </div>
    </section>
  );
}