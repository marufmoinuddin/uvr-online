import type { Metadata } from "next";
import { HistoryView } from "@/components/scenes/history-view";

export const metadata: Metadata = {
  title: "Recent Jobs",
  description:
    "Every job processed on this machine — play, re-run or download previous results.",
};

export default function HistoryPage() {
  return <HistoryView />;
}