import Chat, { Bubble, useMessages, type MessageProps } from "@chatui/core";
import "@chatui/core/dist/index.css";
import React, { useCallback, useMemo, useState } from "react";
import { createRoot, type Root } from "react-dom/client";

import { sendChatbotMessage } from "../services/api";
import type { ChatbotConversationMessage, Itinerary } from "../types";

export interface FloatingChatbotProps {
  currentItinerary: Itinerary | null;
  onItineraryUpdated: (itinerary: Itinerary) => void;
}

function FloatingChatbotReact(props: FloatingChatbotProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [history, setHistory] = useState<ChatbotConversationMessage[]>([]);
  const { messages, appendMsg } = useMessages([
    {
      type: "text",
      content: {
        text: "你好，我是旅行助手。可以先帮你整理出行需求，再把关键信息带回规划页。",
      },
      position: "left",
    },
  ]);

  const navbar = useMemo(() => ({ title: "旅行助手" }), []);

  const renderMessageContent = useCallback((message: MessageProps) => {
    if (message.type !== "text") {
      return null;
    }

    return React.createElement(Bubble, {
      content: message.content?.text ?? "",
    });
  }, []);

  const handleSend = useCallback(
    async (type: string, content: string) => {
      const text = content.trim();
      if (type !== "text" || !text) {
        return;
      }

      appendMsg({
        type: "text",
        content: { text },
        position: "right",
      });

      const nextHistory: ChatbotConversationMessage[] = [
        ...history,
        { role: "user", content: text },
      ];
      setHistory(nextHistory);

      try {
        const response = await sendChatbotMessage({
          message: text,
          trip_id: props.currentItinerary?.trip_id ?? null,
          current_itinerary: props.currentItinerary,
          history: nextHistory,
        });

        appendMsg({
          type: "text",
          content: { text: response.reply },
          position: "left",
        });
        setHistory([
          ...nextHistory,
          { role: "assistant", content: response.reply },
        ]);

        if (response.updated_itinerary) {
          props.onItineraryUpdated(response.updated_itinerary);
        }
      } catch (error) {
        console.error(error);
        appendMsg({
          type: "text",
          content: {
            text: "聊天 agent 暂时没有响应。请检查后端服务是否启动，稍后再试。",
          },
          position: "left",
        });
      }
    },
    [appendMsg, history, props],
  );

  return React.createElement(
    "div",
    {
      className: `floating-chatbot${isOpen ? " floating-chatbot--open" : ""}`,
    },
    React.createElement(
      "section",
      {
        className: "floating-chatbot__panel",
        "aria-hidden": !isOpen,
      },
      React.createElement(Chat, {
        navbar,
        messages,
        placeholder: "输入旅行需求...",
        renderMessageContent,
        onSend: handleSend,
      }),
    ),
    React.createElement(
      "button",
      {
        type: "button",
        className: "floating-chatbot__toggle",
        "aria-expanded": isOpen,
        "aria-label": isOpen ? "收起旅行助手" : "展开旅行助手",
        title: isOpen ? "收起旅行助手" : "展开旅行助手",
        onClick: () => setIsOpen((value) => !value),
      },
      React.createElement(
        "span",
        {
          className: "floating-chatbot__toggle-mark",
          "aria-hidden": true,
        },
        isOpen ? "X" : "AI",
      ),
    ),
  );
}

export interface FloatingChatbotHandle {
  update: (props: FloatingChatbotProps) => void;
  unmount: () => void;
}

export function mountFloatingChatbot(
  container: HTMLElement,
  props: FloatingChatbotProps,
): FloatingChatbotHandle {
  const root: Root = createRoot(container);
  let currentProps = props;
  const render = () => root.render(React.createElement(FloatingChatbotReact, currentProps));
  render();

  return {
    update(nextProps: FloatingChatbotProps) {
      currentProps = nextProps;
      render();
    },
    unmount() {
      root.unmount();
    },
  };
}
