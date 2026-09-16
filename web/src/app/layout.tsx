import type { Metadata, Viewport } from "next";
import "@/styles/globals.css";
import { AppShell } from "@/components/layout/app-shell";

export const metadata: Metadata = {
  title: {
    default: "UVR Local — Vocal Remover & Stem Splitter on your GPU",
    template: "%s · UVR Local",
  },
  description:
    "Professional vocal remover, karaoke maker and stem splitter running 100% locally on your own GPU. No uploads, no limits.",
  keywords: [
    "vocal remover",
    "stem splitter",
    "karaoke maker",
    "acapella extractor",
    "music source separation",
    "BS-RoFormer",
    "Mel-Band RoFormer",
  ],
  openGraph: {
    title: "UVR Local",
    description: "Separate vocals & instruments on your own GPU.",
    type: "website",
  },
  icons: {
    icon: "/logo.svg",
    apple: "/logo.svg",
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#08090a" },
  ],
  width: "device-width",
  initialScale: 1,
};

const themeInit = `(function(){try{var t=localStorage.getItem('uvr-local-store');var theme='system';if(t){try{theme=JSON.parse(t).state.theme||'system'}catch(e){}}var dark=theme==='dark'||(theme==='system'&&window.matchMedia('(prefers-color-scheme: dark)').matches);var r=document.documentElement;r.classList.toggle('dark',dark);r.style.colorScheme=dark?'dark':'light'}catch(e){}})();`;

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
      </head>
      <body className="min-h-[100dvh] font-sans">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}