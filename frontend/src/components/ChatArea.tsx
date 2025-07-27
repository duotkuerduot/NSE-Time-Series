import React from 'react';
export function ChatArea({
  messages,
  isThinking
}) {
  return <div className="flex-grow overflow-y-auto p-4 bg-gradient-to-b from-blue-100 to-blue-200">
      <div className="max-w-4xl mx-auto">
        {messages.map((message, index) => <div key={index} className="mb-6">
            {message.type === 'greeting' && <div className="text-center text-3xl font-medium my-8">
                <span className="text-teal-400">{message.content.hello} </span>
                <span className="text-amber-600">{message.content.name}</span>
              </div>}
            {message.type === 'user' && <div className="flex justify-end mb-4">
                <div className="bg-white rounded-2xl py-3 px-4 max-w-md shadow">
                  <p>{message.content}</p>
                </div>
              </div>}
            {message.type === 'assistant' && <div className="bg-blue-100 p-6 rounded-lg mb-4">
                <p className="text-gray-800">{message.content}</p>
              </div>}
          </div>)}
        {isThinking && <div className="text-teal-500 mt-4">Qdoctor is Thinking...</div>}
      </div>
    </div>;
}