import type { Metadata } from "next";
import "./globals.css";
import { PRODUCT_DESCRIPTION, PRODUCT_NAME } from "@/content/uiCopy";

export const metadata: Metadata = {
  title: PRODUCT_NAME,
  description: PRODUCT_DESCRIPTION
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}