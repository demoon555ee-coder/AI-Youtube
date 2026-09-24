import "./globals.css";
import { LocaleProvider } from "../components/Locale";

export const metadata = {
  title: "YouTube AI Platform",
  description: "Autonomous YouTube content operating system"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="ru"><body><LocaleProvider><div className="app">{children}</div></LocaleProvider></body></html>;
}
