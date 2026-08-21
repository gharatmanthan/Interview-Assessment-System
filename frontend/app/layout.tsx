import type { Metadata } from "next"
import "./globals.css"
import AppLayout from "@/components/app-layout"
import { Toaster } from "sonner"

export const metadata: Metadata = {
  title: "InterviewIQ",
  description: "AI-Powered Interview Assessment Platform",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="font-sans">
        <AppLayout>{children}</AppLayout>
        <Toaster position="top-right" richColors />
      </body>
    </html>
  )
}
