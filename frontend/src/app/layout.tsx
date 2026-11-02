import type { Metadata } from "next";
import "@/styles/globals.css";
import { Header } from "@/components/layout/Header";
import { QueryProvider } from "@/components/providers/QueryProvider";

export const metadata: Metadata = {
  title: "Kolkata PM2.5 — Hourly Estimation & Source Attribution",
  description:
    "Surface PM2.5 nowcasting, multi-horizon uncertainty forecasting, and lag-free SHAP causal source attribution across Kolkata CAAQMS stations.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-[#080d1a] text-slate-100 antialiased selection:bg-accent selection:text-white">
        <QueryProvider>
          <Header />
          <main>{children}</main>
        </QueryProvider>
      </body>
    </html>
  );
}

