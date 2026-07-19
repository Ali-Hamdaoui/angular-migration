"use client";

import React, { useState } from "react";

interface AssistantResponse {
  response: string;
  status: string;
  conversation_id: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  deterministic_fallback: boolean;
  artifact_ids: string[];
}

interface ConversationInfo {
  conversation_id: string;
  run_id: string;
  actor: string;
  message_count: number;
  total_tokens_used: number;
  total_cost_usd: number;
  created_at: string;
  updated_at: string;
}

/**
 * Assistant Chat Panel — read-only evidence-grounded migration state assistant.
 * Never executes commands, approves decisions, or mutates workflow state.
 */
export default function AssistantChatPanel({ runId }: { runId: string }) {
  const [messages, setMessages] = useState<Array<{ role: string; content: string }>>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversation, setConversation] = useState<ConversationInfo | null>(null);
  const [showUsage, setShowUsage] = useState(false);

  const SUGGESTED_QUESTIONS = [
    "What is the current status of my migration?",
    "What evidence exists for this run?",
    "Why is approval needed?",
    "What failed or changed recently?",
    "Show me token usage and cost",
  ];

  async function sendMessage(question: string) {
    if (!question.trim() || loading) return;

    setLoading(true);
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: question }]);

    try {
      const response = await fetch(`/api/v1/runs/${runId}/assistant/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: question,
          idempotency_key: `msg-${runId}-${Date.now()}`,
          actor: "user",
          expected_state_version: 1,
          suggested_questions: SUGGESTED_QUESTIONS,
        }),
      });

      if (!response.ok) {
        throw new Error(`Assistant request failed: ${response.statusText}`);
      }

      const data: AssistantResponse = await response.json();
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: data.deterministic_fallback
            ? `${data.response}\n\n*(Deterministic fallback — LLM gateway not configured)*`
            : data.response,
        },
      ]);

      // Fetch conversation info for usage tracking
      fetchConversationInfo();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to get assistant response");
      setMessages((prev) => prev.slice(0, -1)); // Remove the user message on error
    } finally {
      setLoading(false);
      setInput("");
    }
  }

  async function fetchConversationInfo() {
    try {
      const response = await fetch(`/api/v1/runs/${runId}/assistant/messages?actor=user`);
      if (response.ok) {
        const data: ConversationInfo = await response.json();
        setConversation(data);
      }
    } catch {
      // Silently fail — conversation info is non-critical
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    sendMessage(input);
  }

  return (
    <div className="flex flex-col h-full border border-gray-200 rounded-lg bg-white">
      <div className="p-4 border-b border-gray-200">
        <h2 className="text-lg font-bold">Migration Assistant</h2>
        <p className="text-sm text-gray-500">
          Read-only assistant. Cannot execute commands or approve actions.
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-[300px]">
        {messages.length === 0 && !loading && (
          <div className="text-center text-gray-400 py-8">
            <p>Ask me about your migration state</p>
            <div className="mt-4 space-y-2">
              {SUGGESTED_QUESTIONS.slice(0, 3).map((q) => (
                <button
                  key={q}
                  onClick={() => sendMessage(q)}
                  className="block w-full text-left px-4 py-2 bg-gray-50 hover:bg-gray-100 rounded text-sm text-gray-700"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`p-3 rounded-lg ${
              msg.role === "user"
                ? "bg-blue-50 ml-8"
                : "bg-gray-50 mr-8"
            }`}
          >
            <p className="text-xs text-gray-400 mb-1">
              {msg.role === "user" ? "You" : "Assistant"}
            </p>
            <pre className="whitespace-pre-wrap text-sm font-sans">{msg.content}</pre>
          </div>
        ))}

        {loading && (
          <div className="bg-gray-50 p-3 rounded-lg mr-8">
            <p className="text-sm text-gray-500">Thinking...</p>
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded" role="alert">
            {error}
          </div>
        )}

        {messages.length > 0 && messages.length < 4 && (
          <div className="mt-4 space-y-2">
            <p className="text-xs text-gray-400">Suggested questions:</p>
            {SUGGESTED_QUESTIONS.map((q) => (
              <button
                key={q}
                onClick={() => sendMessage(q)}
                className="block w-full text-left px-4 py-2 bg-gray-50 hover:bg-gray-100 rounded text-sm text-gray-700 disabled:opacity-50"
                disabled={loading}
              >
                {q}
              </button>
            ))}
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="border-t border-gray-200 p-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about your migration..."
            className="flex-1 border border-gray-300 rounded px-3 py-2 text-sm"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={!input.trim() || loading}
            className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded text-sm disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </form>

      {conversation && (
        <div className="border-t border-gray-200 px-4 py-2">
          <button
            onClick={() => setShowUsage(!showUsage)}
            className="text-xs text-gray-400 hover:text-gray-600"
          >
            {showUsage ? "Hide" : "Show"} usage
          </button>
          {showUsage && (
            <div className="mt-1 text-xs text-gray-500">
              <span>Messages: {conversation.message_count} | </span>
              <span>Tokens: {conversation.total_tokens_used} | </span>
              <span>Cost: ${conversation.total_cost_usd.toFixed(4)}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
