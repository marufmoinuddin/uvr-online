import { Hero } from "@/components/layout/hero";
import { SceneTabs } from "@/components/layout/scene-tabs";
import { FAQ } from "@/components/sections/faq";
import { DesktopAppBanner } from "@/components/sections/desktop-app-banner";
import { FeatureTour } from "@/components/sections/feature-tour";

export default function HomePage() {
  return (
    <>
      <Hero />
      <div className="mx-auto max-w-container px-4 pb-8">
        <SceneTabs active="vocal-remover" />
      </div>
      <FeatureTour />
      <FAQ />
      <DesktopAppBanner />
    </>
  );
}