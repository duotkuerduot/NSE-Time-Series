import React, { useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { ChatHeader } from './components/ChatHeader';
import { ChatArea } from './components/ChatArea';
import { ChatInput } from './components/ChatInput';

// Define message types
type GreetingMessage = { type: 'greeting'; content: { hello: string; name: string } };
type UserAssistantMessage = { type: 'user' | 'assistant'; content: string };
type Message = GreetingMessage | UserAssistantMessage;

export function App() {
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      type: 'greeting',
      content: {
        hello: 'Hello',
        name: 'Duot!'
      }
    },
    {
      type: 'user',
      content: "What are the key points in Kenya's Mental Health Policies?"
    },
    {
      type: 'assistant',
      content: 'The key points reflect a major shift from a custodial, institutionalized approach to a more modern, community-based, and rights-focused model of care.'
    },
    {
      type: 'user',
      content: 'Elaborate More'
    }
  ]);
  const [isThinking, setIsThinking] = useState<boolean>(false);

  const toggleSidebar = (): void => {
    setSidebarOpen(!sidebarOpen);
  };

  const closeSidebar = (): void => {
    setSidebarOpen(false);
  };

  const startNewChat = (): void => {
    setMessages([
      {
        type: 'greeting',
        content: {
          hello: 'Hello',
          name: 'Duot!'
        }
      }
    ]);
    closeSidebar();
  };

  const sendMessage = async (message: string): Promise<void> => {
    if (!message.trim()) return;
    setMessages(prev => [
      ...prev,
      {
        type: 'user',
        content: message
      }
    ]);
    setIsThinking(true);
    try {
      const response = await fetch('http://127.0.0.1:8000/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session_id: 'frontend' })
      });
      const data = await response.json();
      setMessages(prev => [
        ...prev,
        {
          type: 'assistant',
          content: data.response || 'Sorry, no answer received from backend.'
        }
      ]);
    } catch (error) {
      console.error('Error sending message:', error);
      setMessages(prev => [
        ...prev,
        {
          type: 'assistant',
          content: 'Error connecting to backend. Please check your server.'
        }
      ]);
    }
    setIsThinking(false);
  };

  return (
    <div className="flex h-screen w-full bg-white overflow-hidden">
      <Sidebar isOpen={sidebarOpen} onClose={closeSidebar} onNewChat={startNewChat} />
      <div className="flex flex-col flex-grow">
        <ChatHeader onMenuClick={toggleSidebar} />
        <ChatArea messages={messages} isThinking={isThinking} />
        <ChatInput onSendMessage={sendMessage} />
      </div>
    </div>
  );
}