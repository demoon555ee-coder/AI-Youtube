import "./globals.css";
import { LocaleProvider } from "../components/Locale";

export const metadata = {
  title: "YouTube AI — студия YouTube-каналов",
  description: "Единая AI-платформа для исследования, создания, производства, публикации и аналитики YouTube-контента"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="ru"><body><LocaleProvider><div className="app">{children}</div></LocaleProvider></body></html>;
}
