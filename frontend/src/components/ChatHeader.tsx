import React from 'react';
import { MenuIcon, UserIcon } from 'lucide-react';
export function ChatHeader({
  onMenuClick
}) {
  return <div className="flex justify-between items-center p-4 border-b border-gray-200 bg-white">
      <div className="flex items-center">
        <button onClick={onMenuClick} className="p-2 hover:bg-gray-100 rounded-md mr-4">
          <MenuIcon size={24} className="text-blue-400" />
        </button>
        <h1 className="text-2xl font-bold text-blue-400">QDOCTOR AI</h1>
      </div>
      <div className="w-10 h-10 rounded-full bg-blue-400 flex items-center justify-center">
        <UserIcon size={24} className="text-white" />
      </div>
    </div>;
}