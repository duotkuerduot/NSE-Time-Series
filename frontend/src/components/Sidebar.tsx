import React from 'react';
import { PenIcon, SearchIcon, MoreVerticalIcon } from 'lucide-react';
export function Sidebar({
  isOpen,
  onClose,
  onNewChat
}) {
  return <div className={`w-[378px] bg-white border-r border-gray-200 transition-all duration-300 ${isOpen ? 'translate-x-0' : '-translate-x-full'} absolute h-full z-10`} onMouseLeave={onClose}>
      <div className="p-4 space-y-6">
        <div className="flex items-center space-x-3 p-2 hover:bg-gray-100 rounded-md cursor-pointer" onClick={onNewChat}>
          <div className="p-1 rounded bg-white border border-gray-300">
            <PenIcon size={20} />
          </div>
          <span className="font-medium">Start new chat</span>
        </div>
        <div className="flex items-center space-x-3 p-2 hover:bg-gray-100 rounded-md cursor-pointer">
          <SearchIcon size={24} />
          <span className="font-medium">Search chats</span>
        </div>
        <div className="mt-8">
          <h2 className="text-lg font-bold mb-2">Chat History</h2>
          <div className="flex justify-between items-center p-2 hover:bg-gray-100 rounded-md cursor-pointer">
            <span>2025 Policy Implementation...</span>
            <MoreVerticalIcon size={16} />
          </div>
        </div>
      </div>
    </div>;
}