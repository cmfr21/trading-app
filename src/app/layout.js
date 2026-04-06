import "./globals.css";

export const metadata = {
  title: "Trading Scanner",
  description: "Maquette Web App trading"
};

export default function RootLayout({ children }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
