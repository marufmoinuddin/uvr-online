import type { Metadata } from "next";
import { FAQ } from "@/components/sections/faq";

export const metadata: Metadata = {
  title: "FAQ",
  description: "Frequently asked questions about running UVR locally.",
};

export default function FaqPage() {
  return (
    <div className="pt-10">
      <h1 className="sr-only">FAQ</h1>
      <FAQ />
    </div>
  );
}