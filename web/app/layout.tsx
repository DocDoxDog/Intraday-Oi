import "./globals.css";
export const metadata = { title: "OI Positioning Intelligence", description: "Market positioning terminal" };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}