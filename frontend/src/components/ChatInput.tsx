import React, { useState } from 'react';
import { SendIcon } from 'lucide-react';
export function ChatInput({
  onSendMessage
}) {
  const [message, setMessage] = useState('');
  const handleSubmit = e => {
    e.preventDefault();
    if (message.trim()) {
      onSendMessage(message);
      setMessage('');
    }
  };
  return <div className="p-4 bg-white border-t border-gray-200">
      <form onSubmit={handleSubmit} className="max-w-4xl mx-auto">
        <div className="relative">
          <input type="text" value={message} onChange={e => setMessage(e.target.value)} placeholder="Ask Qdoctor anything" className="w-full px-6 py-4 pr-16 bg-white border border-gray-300 rounded-full focus:outline-none focus:ring-2 focus:ring-blue-400" />
          <button type="submit" className="absolute right-2 top-1/2 transform -translate-y-1/2 p-2 bg-teal-400 rounded-full hover:bg-teal-500 transition">
            <SendIcon size={24} className="text-white" />
          </button>
        </div>
      </form>
    </div>;
}