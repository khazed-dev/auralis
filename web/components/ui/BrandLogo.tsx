import Image from "next/image";

export function BrandLogo({ priority = false }: { priority?: boolean }) {
  return (
    <span className="brand-logo" aria-label="Auralis">
      <Image src="/logo-auralis.png" alt="Auralis" width={160} height={160} priority={priority} />
    </span>
  );
}
