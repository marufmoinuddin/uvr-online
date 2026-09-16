import type { Metadata } from "next";
import { FreeOpenSection } from "@/components/sections/free-open";

export const metadata: Metadata = {
  title: "Free & open",
  description:
    "No subscriptions, no credits, no paid APIs. Everything runs locally on your own GPU with open-source models.",
};

export default function PricingPage() {
  return (
    <div className="pt-10">
      <FreeOpenSection />
    </div>
  );
}