import { PT_Sans } from "next/font/google";
import "leaflet/dist/leaflet.css";
import "./globals.css";

const ptSans = PT_Sans({
  subsets: ["latin"],
  weight: ["400", "700"],
  style: ["normal", "italic"],
  variable: "--font-pt-sans"
});

export const metadata = {
  title: "Pathfinder - Shortest Route",
  description: "Find the shortest route between nodes"
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className={ptSans.variable}>{children}</body>
    </html>
  );
}
