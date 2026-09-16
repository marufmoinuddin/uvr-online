import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Workbench } from "@/components/scenes/workbench";
import { SCENES, getScene } from "@/lib/models";
import type { SceneKey } from "@/lib/types";

export function generateStaticParams() {
  return SCENES.map((s) => ({ scene: s.key }));
}

export async function generateMetadata({
  params,
}: {
  params: { scene: string };
}): Promise<Metadata> {
  const meta = getScene(params.scene);
  return {
    title: meta.label,
    description: meta.description,
  };
}

export default function ScenePage({ params }: { params: { scene: string } }) {
  const scene = params.scene as SceneKey;
  if (!SCENES.some((s) => s.key === scene)) notFound();

  return <Workbench scene={scene} />;
}