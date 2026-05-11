import "./globals.css";
import AppShell from "@/components/shell/AppShell";

export const metadata = {
  title: "Predictive E-commerce — by Aito",
  description:
    "Open-source reference: predictive search, recommendations, " +
    "catalog enrichment, and pattern discovery for online retail. " +
    "Powered by Aito.ai's predictive database — no model training, " +
    "no MLOps.",
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Nunito:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400&family=JetBrains+Mono:wght@400;500&family=Source+Code+Pro:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
