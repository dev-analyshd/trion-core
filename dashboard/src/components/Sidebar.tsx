'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Activity, Layers, Network, Shield, Database,
  Cpu, GitBranch, ChevronLeft, ChevronRight, Brain
} from 'lucide-react';
import clsx from 'clsx';
import { useState } from 'react';

const NAV = [
  {
    section: 'Intelligence',
    items: [
      { href: '/', label: 'Overview', icon: Activity },
      { href: '/entity', label: 'Entity Intel', icon: Brain },
      { href: '/feed', label: 'Live Feed', icon: Layers },
    ],
  },
  {
    section: 'Data Layers',
    items: [
      { href: '/chains', label: 'Chain Network', icon: Network },
      { href: '/anima', label: 'FAISS ANIMA', icon: Cpu },
      { href: '/leaderboard', label: 'Leaderboard', icon: GitBranch },
    ],
  },
  {
    section: 'Infrastructure',
    items: [
      { href: '/contracts', label: 'Contracts', icon: Shield },
      { href: '/zg', label: '0G Network', icon: Database },
    ],
  },
];

export default function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={clsx(
        'flex flex-col h-full bg-sidebar border-r border-border transition-all duration-200 flex-shrink-0',
        collapsed ? 'w-14' : 'w-[232px]'
      )}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-3 py-4 border-b border-border flex-shrink-0 min-h-[56px]">
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none" className="flex-shrink-0">
          <polygon points="14,2 26,9 26,19 14,26 2,19 2,9" fill="none" stroke="#00c2ff" strokeWidth="1.5"/>
          <polygon points="14,7 21,11 21,17 14,21 7,17 7,11" fill="rgba(0,194,255,0.08)" stroke="#00c2ff" strokeWidth="1" opacity="0.6"/>
          <circle cx="14" cy="14" r="3" fill="#00c2ff" opacity="0.9"/>
        </svg>
        {!collapsed && (
          <div className="flex flex-col overflow-hidden">
            <span className="text-[15px] font-bold tracking-widest text-cyan uppercase">TRION</span>
            <span className="text-[9px] tracking-[0.14em] text-t3 uppercase">Truth Oracle</span>
          </div>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 py-2 overflow-y-auto scrollable">
        {NAV.map((group) => (
          <div key={group.section}>
            {!collapsed && (
              <p className="px-3 py-2 pt-4 text-[9px] font-semibold tracking-[0.14em] uppercase text-t3">
                {group.section}
              </p>
            )}
            {group.items.map(({ href, label, icon: Icon }) => {
              const active = pathname === href;
              return (
                <Link
                  key={href}
                  href={href}
                  className={clsx(
                    'flex items-center gap-2.5 px-3 py-2 mx-1 rounded relative transition-all duration-150',
                    active
                      ? 'bg-[rgba(0,194,255,0.08)] text-cyan'
                      : 'text-t2 hover:bg-border hover:text-t1'
                  )}
                  title={collapsed ? label : undefined}
                >
                  {active && (
                    <span className="absolute left-0 top-0.5 bottom-0.5 w-0.5 bg-cyan rounded-full" />
                  )}
                  <Icon
                    size={15}
                    className={clsx('flex-shrink-0', active ? 'text-cyan' : 'opacity-60')}
                  />
                  {!collapsed && (
                    <span className="text-[12px] font-medium whitespace-nowrap">{label}</span>
                  )}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      {/* Author */}
      {!collapsed && (
        <div className="border-t border-border p-3 flex-shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-full bg-[rgba(0,194,255,0.15)] border border-cyan flex items-center justify-center flex-shrink-0">
              <span className="text-cyan text-[11px] font-bold">HY</span>
            </div>
            <div className="overflow-hidden">
              <p className="text-[12px] font-semibold text-t1 truncate">Hudu Yusuf</p>
              <p className="text-[10px] text-t3">Analys · Creator</p>
            </div>
          </div>
        </div>
      )}

      {/* Collapse toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="border-t border-border flex items-center justify-center h-9 text-t3 hover:text-cyan hover:bg-border transition-colors"
      >
        {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
      </button>
    </aside>
  );
}
