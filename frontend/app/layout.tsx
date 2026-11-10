import type { Metadata, Viewport } from "next";
import { RegisterServiceWorker } from "@/components/register-sw";
import "./globals.css";

export const metadata: Metadata = {
  title: "EduCrew",
  description: "Faculty work log, QR maintenance tickets and smart class adjustment for CSE (AI & ML).",
  applicationName: "EduCrew",
  appleWebApp: { capable: true, title: "EduCrew", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  themeColor: "#1f5c63",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en-IN" className="h-full antialiased">
      <body className="min-h-full">
        {children}
        <RegisterServiceWorker />
      </body>
    </html>
  );
}
