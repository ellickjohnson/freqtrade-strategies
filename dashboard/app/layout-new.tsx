import './globals.css'

export const metadata = {
  title: 'Freqtrade Strategy Dashboard',
  description: 'Monitor and manage multiple trading strategies with real-time insights',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-slate-950 text-slate-50 antialiased">
        {children}
      </body>
    </html>
  )
}