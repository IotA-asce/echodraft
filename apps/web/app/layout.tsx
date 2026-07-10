import type { Metadata } from "next";
import "./design-system/tokens.css";
import "./globals.css";
import { ToastProvider } from "./design-system";

export const metadata: Metadata = {
  title: "echodraft | Project Desk",
  description: "Local-first audiobook production workspace",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body><a className="skip-link" href="#main-content">Skip to content</a><ToastProvider>{children}</ToastProvider></body>
    </html>
  );
}
