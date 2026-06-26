import Chat, { Bubble, useMessages, type MessageProps } from "@chatui/core";
import "@chatui/core/dist/index.css";
import DOMPurify from "dompurify";
import { marked } from "marked";
import React, { useCallback, useMemo, useState } from "react";
import { createRoot, type Root } from "react-dom/client";

import { sendChatbotMessage, sendChatbotMessageStream } from "../services/api";
import type {
  ChatbotConversationMessage,
  ChatbotMessageResponse,
  ChatbotResearchStep,
  Itinerary,
} from "../types";

export interface FloatingChatbotProps {
  currentItinerary: Itinerary | null;
  onItineraryUpdated: (itinerary: Itinerary) => void;
}

const DEFAULT_CHATBOT_SIZE = { width: 380, height: 560 };
const MIN_CHATBOT_SIZE = { width: 340, height: 420 };
const PAGE_MARGIN = 16;
const HOST_OFFSET = { left: 24, bottom: 24 };
const DEFAULT_CHATBOT_OFFSET = { left: 0, bottom: 0 };
type ResizeDirection = "n" | "e" | "s" | "w" | "ne" | "nw" | "se" | "sw";

function FloatingChatbotReact(props: FloatingChatbotProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isMaximized, setIsMaximized] = useState(false);
  const [customSize, setCustomSize] = useState(DEFAULT_CHATBOT_SIZE);
  const [customOffset, setCustomOffset] = useState(DEFAULT_CHATBOT_OFFSET);
  const [history, setHistory] = useState<ChatbotConversationMessage[]>([]);
  const { messages, appendMsg, updateMsg } = useMessages([
    {
      type: "text",
      content: {
        text: "我是你的智旅顾问，可以帮你查实时信息、检查风险，也能直接调整当前行程。",
      },
      position: "left",
    },
  ]);

  const navbar = useMemo(
    () => ({
      title: "旅行助手",
      rightSlot: React.createElement(
        "button",
        {
          type: "button",
          className: "floating-chatbot__expand",
          "aria-label": isMaximized ? "最小化聊天窗口" : "最大化聊天窗口",
          title: isMaximized ? "最小化窗口" : "最大化窗口",
          onClick: () => setIsMaximized((value) => !value),
        },
        React.createElement(
          "span",
          {
            "aria-hidden": true,
          },
          isMaximized ? "−" : "□",
        ),
      ),
    }),
    [isMaximized],
  );

  const handleResizeStart = useCallback((event: React.MouseEvent<HTMLElement>, direction: ResizeDirection) => {
    event.preventDefault();
    event.stopPropagation();
    setIsMaximized(false);

    const startX = event.clientX;
    const startY = event.clientY;
    const startSize = customSize;
    const startOffset = customOffset;
    const startActualLeft = HOST_OFFSET.left + startOffset.left;
    const startActualBottom = HOST_OFFSET.bottom + startOffset.bottom;
    const startRight = startActualLeft + startSize.width;
    const startTop = window.innerHeight - startActualBottom - startSize.height;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const deltaY = moveEvent.clientY - startY;
      const hasWest = direction.includes("w");
      const hasEast = direction.includes("e");
      const hasNorth = direction.includes("n");
      const hasSouth = direction.includes("s");
      let nextWidth = startSize.width;
      let nextLeft = startOffset.left;
      let nextHeight = startSize.height;
      let nextBottom = startOffset.bottom;

      if (hasWest) {
        const nextActualLeft = clamp(
          startActualLeft + deltaX,
          PAGE_MARGIN,
          startRight - MIN_CHATBOT_SIZE.width,
        );
        nextWidth = startRight - nextActualLeft;
        nextLeft = nextActualLeft - HOST_OFFSET.left;
      } else if (hasEast) {
        const maxWidth = Math.max(
          MIN_CHATBOT_SIZE.width,
          window.innerWidth - startActualLeft - PAGE_MARGIN,
        );
        nextWidth = clamp(startSize.width + deltaX, MIN_CHATBOT_SIZE.width, maxWidth);
      }

      if (hasSouth) {
        const nextActualBottom = clamp(
          startActualBottom - deltaY,
          PAGE_MARGIN,
          window.innerHeight - startTop - MIN_CHATBOT_SIZE.height,
        );
        nextHeight = window.innerHeight - startTop - nextActualBottom;
        nextBottom = nextActualBottom - HOST_OFFSET.bottom;
      } else if (hasNorth) {
        const maxHeight = Math.max(
          MIN_CHATBOT_SIZE.height,
          window.innerHeight - startActualBottom - PAGE_MARGIN,
        );
        nextHeight = clamp(startSize.height - deltaY, MIN_CHATBOT_SIZE.height, maxHeight);
      }

      setCustomSize({ width: nextWidth, height: nextHeight });
      setCustomOffset({ left: nextLeft, bottom: nextBottom });
    };

    const handleMouseUp = () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.classList.remove("floating-chatbot-resizing");
    };

    document.body.classList.add("floating-chatbot-resizing");
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
  }, [customOffset, customSize]);

  const renderMessageContent = useCallback((message: MessageProps) => {
    if (message.type !== "text") {
      return null;
    }

    const researchSteps = message.content?.researchSteps as ChatbotResearchStep[] | undefined;
    const text = message.content?.text ?? "";
    const isMarkdown = Boolean(message.content?.markdown);
    const isReport = Boolean(message.content?.report);
    return React.createElement(
      "div",
      { className: `floating-chatbot__message${isReport ? " floating-chatbot__message--report" : ""}` },
      isMarkdown
        ? React.createElement("div", {
            className: "floating-chatbot__markdown",
            dangerouslySetInnerHTML: { __html: renderMarkdown(text) },
          })
        : React.createElement(Bubble, {
            content: text,
          }),
      researchSteps?.length
        ? React.createElement(
            "div",
            { className: "floating-chatbot__research" },
            React.createElement(
              "div",
              { className: "floating-chatbot__research-title" },
              hasActiveStep(researchSteps) ? "正在实时调研" : "调研过程",
            ),
            researchSteps.map((step) =>
              React.createElement(
                "div",
                {
                  key: step.id,
                  className: `floating-chatbot__research-step floating-chatbot__research-step--${step.status}`,
                },
                React.createElement("span", { className: "floating-chatbot__research-status" }, statusLabel(step.status)),
                React.createElement(
                  "div",
                  { className: "floating-chatbot__research-body" },
                  React.createElement("div", { className: "floating-chatbot__research-step-title" }, step.title),
                  step.query
                    ? React.createElement("div", { className: "floating-chatbot__research-query" }, step.query)
                    : null,
                  step.summary
                    ? React.createElement("div", { className: "floating-chatbot__research-summary" }, step.summary)
                    : null,
                ),
              ),
            ),
          )
        : null,
    );
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

      const appendAssistantMessage = (
        assistantText: string,
        options: { researchSteps?: ChatbotResearchStep[]; markdown?: boolean; report?: boolean } = {},
      ) => {
        appendMsg({
          type: "text",
          content: {
            text: assistantText,
            researchSteps: options.researchSteps ?? [],
            markdown: options.markdown ?? false,
            report: options.report ?? false,
          },
          position: "left",
        });
      };

      const updateAssistantMessage = (
        messageId: string,
        assistantText: string,
        options: { researchSteps?: ChatbotResearchStep[]; markdown?: boolean; report?: boolean } = {},
      ) => {
        updateMsg(messageId, {
          type: "text",
          content: {
            text: assistantText,
            researchSteps: options.researchSteps ?? [],
            markdown: options.markdown ?? false,
            report: options.report ?? false,
          },
          position: "left",
        });
      };

      try {
        let response: ChatbotMessageResponse | null = null;
        let visibleSteps: ChatbotResearchStep[] = [];
        let queryCardMessageId: string | null = null;
        let researchCardMessageId: string | null = null;

        await sendChatbotMessageStream({
          message: text,
          trip_id: props.currentItinerary?.trip_id ?? null,
          current_itinerary: props.currentItinerary,
          history: nextHistory,
        }, (event) => {
          if (event.event === "intent") {
            if (event.data.intent !== "search") {
              appendAssistantMessage(intentLabel(event.data.intent));
            }
            return;
          }
          if (event.event === "query_plan") {
            visibleSteps = event.data;
            queryCardMessageId = appendMsg({
              type: "text",
              content: {
                text: "实时查询进度",
                researchSteps: visibleSteps,
                markdown: false,
                report: false,
              },
              position: "left",
            });
            return;
          }
          if (event.event === "query_step") {
            visibleSteps = upsertResearchStep(visibleSteps, event.data);
            if (queryCardMessageId) {
              updateAssistantMessage(queryCardMessageId, "实时查询进度", {
                researchSteps: visibleSteps,
              });
            } else {
              queryCardMessageId = appendMsg({
                type: "text",
                content: {
                  text: "实时查询进度",
                  researchSteps: visibleSteps,
                  markdown: false,
                  report: false,
                },
                position: "left",
              });
            }
            return;
          }
          if (event.event === "research_plan") {
            visibleSteps = event.data;
            researchCardMessageId = appendMsg({
              type: "text",
              content: {
                text: "调研进度",
                researchSteps: visibleSteps,
                markdown: false,
                report: false,
              },
              position: "left",
            });
            return;
          }
          if (event.event === "research_step") {
            visibleSteps = upsertResearchStep(visibleSteps, event.data);
            if (researchCardMessageId) {
              updateAssistantMessage(researchCardMessageId, "调研进度", {
                researchSteps: visibleSteps,
              });
            } else {
              researchCardMessageId = appendMsg({
                type: "text",
                content: {
                  text: "调研进度",
                  researchSteps: visibleSteps,
                  markdown: false,
                  report: false,
                },
                position: "left",
              });
            }
            return;
          }
          if (event.event === "final") {
            response = event.data;
            visibleSteps = event.data.research_steps;
            if (queryCardMessageId && visibleSteps.length) {
              updateAssistantMessage(queryCardMessageId, "实时查询完成", {
                researchSteps: visibleSteps,
              });
            } else if (researchCardMessageId && visibleSteps.length) {
              updateAssistantMessage(researchCardMessageId, "调研完成", {
                researchSteps: visibleSteps,
              });
            } else {
              appendAssistantMessage("实时查询完成，我开始整理最终建议。");
            }
            appendAssistantMessage(event.data.reply, {
              researchSteps: queryCardMessageId || researchCardMessageId ? [] : visibleSteps,
              markdown: true,
              report: true,
            });
            return;
          }
          if (event.event === "error") {
            throw new Error(event.data.message);
          }
        });

        if (!response) {
          response = await sendChatbotMessage({
            message: text,
            trip_id: props.currentItinerary?.trip_id ?? null,
            current_itinerary: props.currentItinerary,
            history: nextHistory,
          });
          appendAssistantMessage(response.reply, {
            researchSteps: response.research_steps,
            markdown: true,
            report: true,
          });
        }

        setHistory([
          ...nextHistory,
          { role: "assistant", content: response.reply },
        ]);

        if (response.updated_itinerary) {
          props.onItineraryUpdated(response.updated_itinerary);
        }
      } catch (error) {
        console.error(error);
        appendAssistantMessage("聊天 agent 暂时没有响应。请检查后端服务是否启动，稍后再试。");
      }
    },
    [appendMsg, history, props, updateMsg],
  );

  return React.createElement(
    "div",
    {
      className: [
        "floating-chatbot",
        isOpen ? "floating-chatbot--open" : "",
        isMaximized ? "floating-chatbot--maximized" : "",
      ].filter(Boolean).join(" "),
      style: {
        "--floating-chatbot-width": `${customSize.width}px`,
        "--floating-chatbot-height": `${customSize.height}px`,
        "--floating-chatbot-left": `${customOffset.left}px`,
        "--floating-chatbot-bottom": `${customOffset.bottom}px`,
      } as React.CSSProperties,
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
      ...(["n", "e", "s", "w", "ne", "nw", "se", "sw"] as ResizeDirection[]).map(
        (direction) =>
          React.createElement(
            "button",
            {
              key: direction,
              type: "button",
              className: `floating-chatbot__resize floating-chatbot__resize--${direction}`,
              "aria-label": "拖拽调整聊天窗口大小",
              title: "拖拽调整大小",
              onMouseDown: (event) => handleResizeStart(event, direction),
            },
            React.createElement("span", { "aria-hidden": true }),
          ),
      ),
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

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function statusLabel(status: ChatbotResearchStep["status"]): string {
  if (status === "completed") {
    return "OK";
  }
  if (status === "failed") {
    return "!";
  }
  if (status === "running") {
    return "...";
  }
  return "-";
}

function renderMarkdown(text: string): string {
  const html = marked.parse(text, { async: false }) as string;
  return DOMPurify.sanitize(html);
}

function hasActiveStep(steps: ChatbotResearchStep[]): boolean {
  return steps.some((step) => step.status === "running" || step.status === "pending");
}

function upsertResearchStep(
  steps: ChatbotResearchStep[],
  nextStep: ChatbotResearchStep,
): ChatbotResearchStep[] {
  const index = steps.findIndex((step) => step.id === nextStep.id);
  if (index === -1) {
    return [...steps, nextStep];
  }
  return steps.map((step, stepIndex) => (stepIndex === index ? nextStep : step));
}

function intentLabel(intent: ChatbotMessageResponse["intent"]): string {
  if (intent === "research" || intent === "risk_check") {
    return "我会先做实时查询，再给你整理结论。";
  }
  if (intent === "search") {
    return "我正在查询相关实时信息。";
  }
  if (intent === "update") {
    return "我正在按你的要求调整当前行程。";
  }
  return "我正在整理回答。";
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
