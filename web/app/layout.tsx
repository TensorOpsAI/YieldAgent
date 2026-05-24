import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "YieldAgent Workspace",
  description: "Campaign operations interface for governed ad agents"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
