import "./globals.css";

export const metadata = {
  title: "YouTube AI Platform",
  description: "Autonomous YouTube content operating system"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <div className="app">{children}</div>;
}
