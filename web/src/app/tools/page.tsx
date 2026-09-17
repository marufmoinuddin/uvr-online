import type { Metadata } from "next";
import { FeatureTour } from "@/components/sections/feature-tour";

export const metadata: Metadata = {
  title: "Tools",
  description:
    "Vocal remover, karaoke maker, stem splitter, noise removal and more — all running locally on your GPU.",
};

export default function ToolsPage() {
  return (
    <div className="pt-10">
      <h1 className="sr-only">Tools</h1>
      <FeatureTour />
    </div>
  );
}