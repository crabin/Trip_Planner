import Chat, { Bubble, useMessages, type MessageProps } from "@chatui/core";
import "@chatui/core/dist/index.css";
import DOMPurify from "dompurify";
import { marked } from "marked";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createRoot, type Root } from "react-dom/client";

import { sendChatbotMessage, sendChatbotMessageStream } from "../services/api";
import type {
  ChatbotConversationMessage,
  ChatbotMessageResponse,
  ChatbotResearchStep,
  Itinerary,
  TravelerProfile,
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
const TOGGLE_BUTTON_SIZE = 56;
const TOGGLE_DRAG_THRESHOLD = 4;
const CHATBOT_PANEL_GAP = 12;
const TRAVELER_PROFILE_STORAGE_KEY = "trip_planner.traveler_profile";
const CHATBOT_SUMMARY_STORAGE_KEY = "trip_planner.chatbot_summary";
const EMPTY_TRAVELER_PROFILE: TravelerProfile = {
  pace_preference: null,
  food_preferences: [],
  avoidances: [],
  interests: [],
  budget_sensitivity: null,
  confirmed_facts: [],
};
type ResizeDirection = "n" | "e" | "s" | "w" | "ne" | "nw" | "se" | "sw";
type Size = { width: number; height: number };
type Offset = { left: number; bottom: number };
type PanelLayout = {
  anchorLeft: number;
  anchorBottom: number;
  left: number;
  bottom: number;
  width: number;
  height: number;
};

function FloatingChatbotReact(props: FloatingChatbotProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isMaximized, setIsMaximized] = useState(false);
  const [customSize, setCustomSize] = useState(DEFAULT_CHATBOT_SIZE);
  const [customOffset, setCustomOffset] = useState(DEFAULT_CHATBOT_OFFSET);
  const [isDraggingToggle, setIsDraggingToggle] = useState(false);
  const [viewportSize, setViewportSize] = useState(() => getViewportSize());
  const [history, setHistory] = useState<ChatbotConversationMessage[]>([]);
  const [travelerProfile, setTravelerProfile] = useState<TravelerProfile>(() => loadTravelerProfile());
  const [conversationSummary, setConversationSummary] = useState(() => loadConversationSummary());
  const [isResponding, setIsResponding] = useState(false);
  const { messages, appendMsg, updateMsg } = useMessages([
    {
      type: "text",
      content: {
        text: "我是你的智旅顾问，会帮你把行程安排得更顺路、更符合预算和节奏。你可以直接说想改哪一天、查哪个景点，或让我帮你权衡两个方案。",
      },
      position: "left",
    },
  ]);
  const panelLayout = useMemo(
    () => getConstrainedPanelLayout(customSize, customOffset, viewportSize),
    [customOffset, customSize, viewportSize],
  );

  useEffect(() => {
    const handleResize = () => setViewportSize(getViewportSize());
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const toggleMaximized = useCallback(() => {
    setIsMaximized((value) => {
      if (value) {
        setCustomSize(DEFAULT_CHATBOT_SIZE);
        setCustomOffset(DEFAULT_CHATBOT_OFFSET);
      }
      return !value;
    });
  }, []);

  const navbar = useMemo(
    () => ({
      title: "智旅顾问",
      rightSlot: React.createElement(
        "button",
        {
          type: "button",
          className: "floating-chatbot__expand",
          "aria-label": isMaximized ? "恢复聊天窗口初始大小" : "最大化聊天窗口",
          title: isMaximized ? "恢复初始大小" : "最大化窗口",
          onClick: toggleMaximized,
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
    [isMaximized, toggleMaximized],
  );

  const handleResizeStart = useCallback((event: React.MouseEvent<HTMLElement>, direction: ResizeDirection) => {
    event.preventDefault();
    event.stopPropagation();
    setIsMaximized(false);

    const startX = event.clientX;
    const startY = event.clientY;
    const startSize = customSize;
    const startOffset = customOffset;
    const startActualLeft = panelLayout.left;
    const startActualBottom = panelLayout.bottom;
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
      let nextHeight = startSize.height;

      if (hasWest) {
        const nextActualLeft = clamp(
          startActualLeft + deltaX,
          PAGE_MARGIN,
          startRight - MIN_CHATBOT_SIZE.width,
        );
        nextWidth = startRight - nextActualLeft;
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
      } else if (hasNorth) {
        const maxHeight = Math.max(
          MIN_CHATBOT_SIZE.height,
          window.innerHeight - startActualBottom - PAGE_MARGIN,
        );
        nextHeight = clamp(startSize.height - deltaY, MIN_CHATBOT_SIZE.height, maxHeight);
      }

      setCustomSize({ width: nextWidth, height: nextHeight });
    };

    const handleMouseUp = () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.classList.remove("floating-chatbot-resizing");
    };

    document.body.classList.add("floating-chatbot-resizing");
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
  }, [customSize, panelLayout]);

  const handleTogglePointerDown = useCallback((event: React.PointerEvent<HTMLButtonElement>) => {
    if (isMaximized || event.button !== 0) {
      return;
    }

    event.preventDefault();
    const startX = event.clientX;
    const startY = event.clientY;
    const startOffset = customOffset;
    let hasDragged = false;

    const handlePointerMove = (moveEvent: PointerEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const deltaY = moveEvent.clientY - startY;
      if (!hasDragged && Math.hypot(deltaX, deltaY) < TOGGLE_DRAG_THRESHOLD) {
        return;
      }
      hasDragged = true;
      setIsDraggingToggle(true);

      const hostOffset = getHostOffset(window.innerWidth);
      const nextActualLeft = clamp(
        hostOffset.left + startOffset.left + deltaX,
        PAGE_MARGIN,
        window.innerWidth - TOGGLE_BUTTON_SIZE - PAGE_MARGIN,
      );
      const nextActualBottom = clamp(
        hostOffset.bottom + startOffset.bottom - deltaY,
        PAGE_MARGIN,
        window.innerHeight - TOGGLE_BUTTON_SIZE - PAGE_MARGIN,
      );
      setCustomOffset({
        left: nextActualLeft - hostOffset.left,
        bottom: nextActualBottom - hostOffset.bottom,
      });
    };

    const handlePointerUp = () => {
      document.removeEventListener("pointermove", handlePointerMove);
      document.removeEventListener("pointerup", handlePointerUp);
      document.body.classList.remove("floating-chatbot-dragging");
      window.setTimeout(() => setIsDraggingToggle(false), 0);
    };

    document.body.classList.add("floating-chatbot-dragging");
    document.addEventListener("pointermove", handlePointerMove);
    document.addEventListener("pointerup", handlePointerUp);
  }, [customOffset, isMaximized]);

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
      if (isResponding || type !== "text" || !text) {
        return;
      }

      setIsResponding(true);
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
          profile: travelerProfile,
          conversation_summary: conversationSummary,
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
            persistChatbotMemory(event.data, setTravelerProfile, setConversationSummary);
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
            profile: travelerProfile,
            conversation_summary: conversationSummary,
            history: nextHistory,
          });
          persistChatbotMemory(response, setTravelerProfile, setConversationSummary);
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
        appendAssistantMessage("智旅顾问暂时没有响应。请检查后端服务是否启动，稍后再试。");
      } finally {
        setIsResponding(false);
      }
    },
    [appendMsg, conversationSummary, history, isResponding, props, travelerProfile, updateMsg],
  );

  return React.createElement(
    "div",
    {
      className: [
        "floating-chatbot",
        isOpen ? "floating-chatbot--open" : "",
        isMaximized ? "floating-chatbot--maximized" : "",
        isResponding ? "floating-chatbot--responding" : "",
      ].filter(Boolean).join(" "),
      style: {
        "--floating-chatbot-width": `${customSize.width}px`,
        "--floating-chatbot-height": `${customSize.height}px`,
        "--floating-chatbot-left": `${customOffset.left}px`,
        "--floating-chatbot-bottom": `${customOffset.bottom}px`,
        "--floating-chatbot-panel-width": `${panelLayout.width}px`,
        "--floating-chatbot-panel-height": `${panelLayout.height}px`,
        "--floating-chatbot-panel-left": `${panelLayout.left - panelLayout.anchorLeft}px`,
        "--floating-chatbot-panel-bottom": `${panelLayout.bottom - panelLayout.anchorBottom}px`,
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
        placeholder: isResponding ? "智旅顾问正在思考..." : "输入想调整、查询或比较的旅行需求...",
        inputOptions: {
          disabled: isResponding,
        },
        onBeforeSend: () => !isResponding,
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
        "aria-label": isResponding ? "智旅顾问正在思考" : isOpen ? "收起智旅顾问" : "展开智旅顾问",
        title: isResponding ? "正在思考" : isOpen ? "收起智旅顾问" : "展开智旅顾问",
        onClick: () => {
          if (!isDraggingToggle) {
            setIsOpen((value) => !value);
          }
        },
        onPointerDown: handleTogglePointerDown,
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

function getViewportSize(): Size {
  if (typeof window === "undefined") {
    return { width: 1280, height: 800 };
  }
  return { width: window.innerWidth, height: window.innerHeight };
}

function getHostOffset(viewportWidth: number): Offset {
  return viewportWidth <= 640 ? { left: 16, bottom: 16 } : HOST_OFFSET;
}

function getConstrainedPanelLayout(size: Size, offset: Offset, viewportSize: Size): PanelLayout {
  const hostOffset = getHostOffset(viewportSize.width);
  const anchorLeft = hostOffset.left + offset.left;
  const anchorBottom = hostOffset.bottom + offset.bottom;
  const maxWidth = Math.max(MIN_CHATBOT_SIZE.width, viewportSize.width - PAGE_MARGIN * 2);
  const maxHeight = Math.max(MIN_CHATBOT_SIZE.height, viewportSize.height - PAGE_MARGIN * 2);
  const width = clamp(size.width, MIN_CHATBOT_SIZE.width, maxWidth);
  const preferredHeight = clamp(size.height, MIN_CHATBOT_SIZE.height, maxHeight);
  const spaceAboveToggle = viewportSize.height - anchorBottom - TOGGLE_BUTTON_SIZE - CHATBOT_PANEL_GAP - PAGE_MARGIN;
  const spaceBelowToggle = anchorBottom - CHATBOT_PANEL_GAP - PAGE_MARGIN;
  const opensAbove = spaceAboveToggle >= preferredHeight || spaceAboveToggle >= spaceBelowToggle;
  const availableHeight = Math.max(opensAbove ? spaceAboveToggle : spaceBelowToggle, MIN_CHATBOT_SIZE.height);
  const height = clamp(preferredHeight, MIN_CHATBOT_SIZE.height, Math.min(maxHeight, availableHeight));
  const preferredLeft = anchorLeft;
  const preferredBottom = opensAbove
    ? anchorBottom + TOGGLE_BUTTON_SIZE + CHATBOT_PANEL_GAP
    : anchorBottom - CHATBOT_PANEL_GAP - height;
  const left = clamp(preferredLeft, PAGE_MARGIN, viewportSize.width - width - PAGE_MARGIN);
  const bottom = clamp(preferredBottom, PAGE_MARGIN, viewportSize.height - height - PAGE_MARGIN);

  return {
    anchorLeft,
    anchorBottom,
    left,
    bottom,
    width,
    height,
  };
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

function loadTravelerProfile(): TravelerProfile {
  if (typeof window === "undefined") {
    return { ...EMPTY_TRAVELER_PROFILE };
  }
  try {
    const raw = window.localStorage.getItem(TRAVELER_PROFILE_STORAGE_KEY);
    if (!raw) {
      return { ...EMPTY_TRAVELER_PROFILE };
    }
    return normalizeTravelerProfile(JSON.parse(raw));
  } catch {
    return { ...EMPTY_TRAVELER_PROFILE };
  }
}

function loadConversationSummary(): string {
  if (typeof window === "undefined") {
    return "";
  }
  return window.localStorage.getItem(CHATBOT_SUMMARY_STORAGE_KEY) ?? "";
}

function persistChatbotMemory(
  response: ChatbotMessageResponse,
  setTravelerProfile: React.Dispatch<React.SetStateAction<TravelerProfile>>,
  setConversationSummary: React.Dispatch<React.SetStateAction<string>>,
): void {
  const nextProfile = normalizeTravelerProfile(response.profile);
  const nextSummary = response.conversation_summary ?? "";
  setTravelerProfile(nextProfile);
  setConversationSummary(nextSummary);
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(TRAVELER_PROFILE_STORAGE_KEY, JSON.stringify(nextProfile));
  window.localStorage.setItem(CHATBOT_SUMMARY_STORAGE_KEY, nextSummary);
}

function normalizeTravelerProfile(value: unknown): TravelerProfile {
  const source = isRecord(value) ? value : {};
  return {
    pace_preference: normalizeChoice(source.pace_preference, ["轻松", "适中", "紧凑"] as const),
    food_preferences: normalizeStringList(source.food_preferences),
    avoidances: normalizeStringList(source.avoidances),
    interests: normalizeStringList(source.interests),
    budget_sensitivity: normalizeChoice(source.budget_sensitivity, ["高", "中", "低"] as const),
    confirmed_facts: normalizeStringList(source.confirmed_facts),
  };
}

function normalizeChoice<T extends string>(value: unknown, allowed: readonly T[]): T | null {
  return allowed.includes(value as T) ? (value as T) : null;
}

function normalizeStringList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => String(item).trim()).filter(Boolean).slice(0, 20);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
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
  if (intent === "research" || intent === "risk_check" || intent === "compare") {
    return "我会先做实时查询，再给你整理结论。";
  }
  if (intent === "search") {
    return "我正在查询相关实时信息。";
  }
  if (intent === "update" || intent === "personalize") {
    return "我正在按你的要求调整当前行程。";
  }
  if (intent === "clarify") {
    return "我需要先确认关键信息，再给稳妥建议。";
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
