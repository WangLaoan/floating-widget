import React from "react";

interface TopBarProps {
  updateTime: string;
  onRefresh: () => void;
}

const TopBar: React.FC<TopBarProps> = ({ updateTime, onRefresh }) => {
  const handleClose = () => {
    window.electronAPI?.hideWindow();
  };

  const handleMinimize = () => {
    window.electronAPI?.minimizeWindow();
  };

  return (
    <div
      className="flex items-center justify-between px-3 py-2 select-none"
      style={{ WebkitAppRegion: "drag" } as React.CSSProperties}
    >
      {/* Left: Title + Update time */}
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-cyan-400 shadow-[0_0_6px_rgba(56,189,248,0.6)]" />
          <span className="text-xs font-semibold text-slate-200 tracking-wider">
            估值温度
          </span>
        </div>
        <span className="text-[10px] text-slate-500 font-mono">
          {updateTime}
        </span>
      </div>

      {/* Right: Action buttons */}
      <div
        className="flex items-center gap-1"
        style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}
      >
        {/* Refresh */}
        <button
          onClick={onRefresh}
          className="w-6 h-6 flex items-center justify-center rounded-md
                     bg-slate-700/40 hover:bg-slate-600/60
                     text-slate-400 hover:text-cyan-400
                     transition-colors duration-200"
          title="刷新数据"
        >
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2" />
          </svg>
        </button>

        {/* Minimize */}
        <button
          onClick={handleMinimize}
          className="w-6 h-6 flex items-center justify-center rounded-md
                     bg-slate-700/40 hover:bg-slate-600/60
                     text-slate-400 hover:text-slate-200
                     transition-colors duration-200"
          title="最小化"
        >
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          >
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>

        {/* Close */}
        <button
          onClick={handleClose}
          className="w-6 h-6 flex items-center justify-center rounded-md
                     bg-slate-700/40 hover:bg-red-500/70
                     text-slate-400 hover:text-white
                     transition-colors duration-200"
          title="关闭窗口"
        >
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>
    </div>
  );
};

export default TopBar;
