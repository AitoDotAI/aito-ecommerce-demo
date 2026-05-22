import "./globals.css";
import Script from "next/script";
import AppShell from "@/components/shell/AppShell";
import Analytics from "@/components/shell/Analytics";

// Same GA4 property as the other Aito demos so cohorts can be split
// across demos via the `surface` Amplitude property. Hardcoded literal
// — measurement ID is public anyway (visible in the deployed bundle
// since GA4 was launched).
const GA_MEASUREMENT_ID = "G-FDTBRCMZWJ";

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
        <Analytics />
        {/* GA4 + Amplitude carry production telemetry. Both are no-op
            on localhost — `lib/analytics.ts:isProductionHost`
            short-circuits Amplitude, and GA's `config` only emits
            after the scripts load on a real host. */}
        <Script
          src={`https://www.googletagmanager.com/gtag/js?id=${GA_MEASUREMENT_ID}`}
          strategy="afterInteractive"
        />
        <Script id="ga-init" strategy="afterInteractive">
          {`
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag('js', new Date());
            gtag('config', '${GA_MEASUREMENT_ID}', {
              anonymize_ip: true,
              cookie_expires: 0,
            });
          `}
        </Script>
      </body>
    </html>
  );
}
