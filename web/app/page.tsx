import { FeatureGrid } from "@/components/landing/FeatureGrid";
import { Footer } from "@/components/landing/Footer";
import { Header } from "@/components/landing/Header";
import { Hero } from "@/components/landing/Hero";
import { Pricing } from "@/components/landing/Pricing";
import { SourceAnswers } from "@/components/landing/SourceAnswers";
import { Stats } from "@/components/landing/Stats";

export default function Home() {
  return (
    <>
      <Header />
      <main>
        <Hero />
        <Stats />
        <FeatureGrid />
        <SourceAnswers />
        <Pricing />
      </main>
      <Footer />
    </>
  );
}
