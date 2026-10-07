import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Gold Market Intelligence",
  description: "CME / OI / Gamma / Order Flow market decision dashboard",
  viewport: "width=device-width, initial-scale=1, maximum-scale=1, viewport-fit=cover",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="th">
      <body>{children}</body>
    </html>
  );
}
