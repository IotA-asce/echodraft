import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "echodraft | Project Desk",
  description: "Local-first audiobook production workspace",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
