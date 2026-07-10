import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Frontend Migration Factory",
  description: "Control Tower for backend-owned migration workflow state."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}