import "./globals.css";

export const metadata = {
  title: "Trading Scanner",
  description: "Scanner crypto avec prix live et alertes"
};

export default function RootLayout({ children }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
