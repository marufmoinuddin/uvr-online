import Link from "next/link";
import { AudioWaveform, Home } from "lucide-react";
import { Button } from "@/components/ui/button";

/**
 * Branded 404 page — replaces the default Next.js not-found screen.
 */
export default function NotFound() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 px-4 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
        <AudioWaveform className="h-6 w-6" />
      </span>
      <p className="text-sm font-semibold uppercase tracking-wider text-primary">
        404
      </p>
      <h1 className="text-3xl font-bold tracking-tight">Page not found</h1>
      <p className="max-w-md text-sm text-muted-foreground">
        That page doesn&apos;t exist or has moved. Try one of the separation
        tools instead.
      </p>
      <Button asChild>
        <Link href="/tools/vocal-remover">
          <Home className="h-4 w-4" />
          Open the workbench
        </Link>
      </Button>
    </div>
  );
}