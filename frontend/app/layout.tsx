import type { Metadata } from "next";
import "./globals.css";
import { Header } from "../components/layout/Header";
import { Sidebar } from "../components/layout/Sidebar";

export const metadata: Metadata = {
  title: "AI Interview Studio — Career-Readiness & Adaptive Intelligence",
  description: "Enterprise-grade adaptive learning, real-world scenario challenges, and AI mock interview simulations.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-white text-[#111827] antialiased min-h-screen flex flex-col font-sans">
        <Header />
        <div className="flex flex-1 min-h-[calc(100vh-3.5rem)]">
          <Sidebar />
          <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto w-full bg-white">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
