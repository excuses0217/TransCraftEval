import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  BarChart3,
  ClipboardCheck,
  Clapperboard,
  FlaskConical,
  LayoutDashboard,
  Menu,
  SearchCheck,
  ShieldCheck,
  SlidersHorizontal,
  UsersRound,
} from 'lucide-react'
import type { WorkspacePurpose } from '../api/contracts'
import { Button } from '../components/ui/Button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/Select'
import { Sheet, SheetContent, SheetTitle } from '../components/ui/Sheet'
import { cn } from '../lib/utils'
import { useWorkspace } from './WorkspaceContext'

const groups = [
  {
    label: '工作台',
    items: [
      { to: '/overview', label: '审核概览', icon: BarChart3 },
      { to: '/workbench', label: '审核工作台', icon: LayoutDashboard },
      { to: '/tasks', label: '任务中心', icon: ClipboardCheck },
      { to: '/results', label: '审核结果', icon: ShieldCheck },
    ],
  },
  {
    label: '内容与规则',
    items: [
      { to: '/media', label: '媒资中心', icon: Clapperboard },
      { to: '/library/people', label: '审核对象库', icon: UsersRound },
    ],
  },
]

export function Layout() {
  const { purpose, setPurpose } = useWorkspace()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('yingjian-sidebar') === '1')
  const [mobile, setMobile] = useState(false)

  const toggle = () => setCollapsed(value => {
    const next = !value
    localStorage.setItem('yingjian-sidebar', next ? '1' : '0')
    return next
  })

  const currentLabel = location.pathname.startsWith('/library/')
    ? '审核对象库'
    : [...groups.flatMap(group => group.items), ...(purpose === 'validation' ? [{ to: '/validation/tools', label: '技术验证', icon: FlaskConical }] : [])]
      .find(item => location.pathname === item.to || (item.to !== '/overview' && location.pathname.startsWith(`${item.to}/`)))?.label ?? '映鉴'

  const nav = (mobileMode = false) => <>
    <div className={cn('flex h-14 items-center', collapsed && !mobileMode ? 'justify-center px-2' : 'px-3')}>
      {(!collapsed || mobileMode) && <div className="flex min-w-0 flex-1 items-center gap-3">
        <span className="grid size-8 shrink-0 place-items-center rounded-md bg-primary text-sm font-semibold tracking-tight text-primary-foreground">映</span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold tracking-tight text-foreground">映鉴</p>
          <p className="truncate text-[11px] text-muted-foreground">智能媒资审核</p>
        </div>
      </div>}
      {collapsed && !mobileMode && <span className="grid size-8 shrink-0 place-items-center rounded-md bg-primary text-sm font-semibold text-primary-foreground">映</span>}
    </div>

    <div className={cn('pb-3', collapsed && !mobileMode ? 'px-2' : 'px-3')}>
      {(!collapsed || mobileMode) && <p className="mb-1.5 px-2 text-[11px] font-medium text-muted-foreground">工作空间</p>}
      {collapsed && !mobileMode ? (
        <span className="mx-auto block size-2 rounded-full bg-success" title={purpose === 'production' ? '生产审核' : '算法验证'} />
      ) : (
        <Select value={purpose} onValueChange={value => setPurpose(value as WorkspacePurpose)}>
          <SelectTrigger aria-label="切换工作空间" className="h-9 w-full border-sidebar-border bg-background text-foreground shadow-none">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="production">生产审核</SelectItem>
            <SelectItem value="validation">算法验证</SelectItem>
          </SelectContent>
        </Select>
      )}
    </div>

    <nav className={cn('min-h-0 flex-1 space-y-5 overflow-y-auto py-2', collapsed && !mobileMode ? 'px-2' : 'px-3')} aria-label="主导航">
      {groups.map(group => <div key={group.label}>
        {(!collapsed || mobileMode) && <p className="px-2 pb-1.5 text-[11px] font-medium text-muted-foreground">{group.label}</p>}
        <div className="space-y-0.5">
          {group.items.map(item => <NavLink key={item.to} to={item.to} onClick={() => setMobile(false)} title={collapsed && !mobileMode ? item.label : undefined} className={({ isActive }) => cn(
            'flex h-8 items-center rounded-md text-sm transition-colors',
            collapsed && !mobileMode ? 'justify-center' : 'gap-2.5 px-2.5',
            (isActive || (item.to === '/library/people' && location.pathname.startsWith('/library/')))
              ? 'bg-sidebar-accent font-medium text-foreground shadow-sm ring-1 ring-border'
              : 'text-sidebar-foreground hover:bg-muted hover:text-foreground',
          )}><item.icon className="size-4 shrink-0" />{(!collapsed || mobileMode) && <span className="truncate">{item.label}</span>}</NavLink>)}
        </div>
      </div>)}
      {purpose === 'validation' && <div>
        {(!collapsed || mobileMode) && <p className="px-2 pb-1.5 text-[11px] font-medium text-muted-foreground">算法运营</p>}
        <NavLink to="/validation/tools" onClick={() => setMobile(false)} title={collapsed && !mobileMode ? '技术验证' : undefined} className={({ isActive }) => cn('flex h-8 items-center rounded-md text-sm transition-colors', collapsed && !mobileMode ? 'justify-center' : 'gap-2.5 px-2.5', isActive ? 'bg-sidebar-accent font-medium text-foreground shadow-sm ring-1 ring-border' : 'text-sidebar-foreground hover:bg-muted hover:text-foreground')}><FlaskConical className="size-4 shrink-0" />{(!collapsed || mobileMode) && '技术验证'}</NavLink>
      </div>}
    </nav>

    <div className={cn('border-t border-sidebar-border py-3', collapsed && !mobileMode ? 'px-2' : 'px-3')}>
      {collapsed && !mobileMode ? <SearchCheck className="mx-auto size-4 text-muted-foreground" /> : <div className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs text-muted-foreground"><SlidersHorizontal className="size-4" /><span>本地运行 · 数据不出域</span></div>}
    </div>
  </>

  return <div className="flex h-[100dvh] overflow-hidden bg-sidebar">
    <aside className={cn('hidden h-full shrink-0 flex-col bg-sidebar text-sidebar-foreground transition-[width] duration-200 md:flex', collapsed ? 'w-14' : 'w-56')}>{nav()}</aside>
    <Sheet open={mobile} onOpenChange={setMobile}>
      <SheetContent closeLabel="关闭导航" className="w-72 border-sidebar-border bg-sidebar p-0 text-sidebar-foreground">
        <SheetTitle className="sr-only">主导航</SheetTitle>
        <div className="flex h-full flex-col">{nav(true)}</div>
      </SheetContent>
    </Sheet>
    <div className="m-0 flex min-w-0 flex-1 flex-col overflow-hidden bg-background md:my-2 md:mr-2 md:rounded-xl md:border md:shadow-sm">
      <header className="flex h-14 shrink-0 items-center justify-between border-b bg-background/95 px-3 backdrop-blur sm:px-4">
        <div className="flex min-w-0 items-center gap-2">
          <Button variant="ghost" size="icon-sm" onClick={() => window.innerWidth < 768 ? setMobile(true) : toggle()} aria-label={collapsed ? '展开导航' : '收起导航'}><Menu /></Button>
          <span className="h-4 w-px bg-border" />
          <p className="truncate text-sm"><span className="text-muted-foreground">{purpose === 'production' ? '生产审核' : '算法验证'}</span><span className="px-2 text-border">/</span><span className="font-medium text-foreground">{currentLabel}</span></p>
        </div>
      </header>
      <div className="app-surface scrollbar-stable min-h-0 flex-1 overflow-auto"><Outlet /></div>
    </div>
  </div>
}
