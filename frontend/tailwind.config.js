/** @type {import('tailwindcss').Config} */
export default {
  content: { relative: true, files: ['./index.html', './src/**/*.{ts,tsx}'] },
  theme: {
    extend: {
      colors: {
        background: 'hsl(var(--background))', foreground: 'hsl(var(--foreground))',
        card: 'hsl(var(--card))', 'card-foreground': 'hsl(var(--card-foreground))',
        popover: 'hsl(var(--popover))', 'popover-foreground': 'hsl(var(--popover-foreground))',
        muted: 'hsl(var(--muted))', 'muted-foreground': 'hsl(var(--muted-foreground))',
        border: 'hsl(var(--border))', input: 'hsl(var(--input))',
        primary: 'hsl(var(--primary))', 'primary-foreground': 'hsl(var(--primary-foreground))', ring: 'hsl(var(--ring))',
        accent: 'hsl(var(--accent))', 'accent-foreground': 'hsl(var(--accent-foreground))',
        destructive: 'hsl(var(--destructive))', success: 'hsl(var(--success))',
        warning: 'hsl(var(--warning))', info: 'hsl(var(--info))', critical: 'hsl(var(--critical))',
        sidebar: 'hsl(var(--sidebar))', 'sidebar-foreground': 'hsl(var(--sidebar-foreground))',
        'sidebar-accent': 'hsl(var(--sidebar-accent))', 'sidebar-border': 'hsl(var(--sidebar-border))',
        'chart-1': 'hsl(var(--chart-1))', 'chart-2': 'hsl(var(--chart-2))',
        'chart-3': 'hsl(var(--chart-3))', 'chart-4': 'hsl(var(--chart-4))'
      },
      borderRadius: { lg: 'var(--radius)', md: 'calc(var(--radius) - 2px)', sm: 'calc(var(--radius) - 4px)' }
    }
  },
  plugins: []
}
