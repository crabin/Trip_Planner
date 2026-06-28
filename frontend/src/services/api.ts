import axios from "axios";

import type {
  ChatbotMessagePayload,
  ChatbotMessageResponse,
  ChatbotStreamEvent,
  DestinationSpanCheckResponse,
  Itinerary,
  LocationSuggestionResponse,
  TripDetailResponse,
  TripEditPayload,
  TripListResponse,
  TripRequestPayload,
  TripSaveResponse,
  TripSummaryItem,
  WeatherForecastResponse,
} from "../types";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000,
});

export async function generateTrip(payload: TripRequestPayload): Promise<Itinerary> {
  const response = await api.post<Itinerary>("/trip/generate", payload);
  return response.data;
}

export async function generateDeepTrip(
  payload: TripRequestPayload
): Promise<TripSummaryItem> {
  const response = await api.post<TripSummaryItem>("/trip/deep-generate", payload);
  return response.data;
}

export async function editTrip(payload: TripEditPayload): Promise<Itinerary> {
  const response = await api.post<Itinerary>("/trip/edit", payload);
  return response.data;
}

export async function sendChatbotMessage(
  payload: ChatbotMessagePayload
): Promise<ChatbotMessageResponse> {
  const response = await api.post<ChatbotMessageResponse>("/chatbot/message", payload);
  return response.data;
}

export async function sendChatbotMessageStream(
  payload: ChatbotMessagePayload,
  onEvent: (event: ChatbotStreamEvent) => void
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/chatbot/message/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok || !response.body) {
    throw new Error(`聊天流式接口返回 ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });

    const parts = buffer.split(/\n\n/);
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const event = parseSseEvent(part);
      if (event) {
        onEvent(event);
      }
    }

    if (done) {
      break;
    }
  }

  const finalEvent = parseSseEvent(buffer);
  if (finalEvent) {
    onEvent(finalEvent);
  }
}

function parseSseEvent(chunk: string): ChatbotStreamEvent | null {
  const eventLine = chunk.split("\n").find((line) => line.startsWith("event:"));
  const dataLines = chunk
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart());

  if (!eventLine || dataLines.length === 0) {
    return null;
  }

  try {
    return {
      event: eventLine.slice(6).trim(),
      data: JSON.parse(dataLines.join("\n")),
    } as ChatbotStreamEvent;
  } catch {
    return null;
  }
}

export async function saveTrip(itinerary: Itinerary): Promise<TripSaveResponse> {
  const response = await api.post<TripSaveResponse>("/trip/save", {
    trip_id: itinerary.trip_id,
    itinerary,
    user_id: "frontend_demo_user",
  });
  return response.data;
}

export async function listTrips(): Promise<TripListResponse> {
  const response = await api.get<TripListResponse>("/trip");
  return response.data;
}

export async function getTripDetail(tripId: string): Promise<TripDetailResponse> {
  const response = await api.get<TripDetailResponse>(`/trip/${tripId}`);
  return response.data;
}

export async function getTripReport(reportId: string): Promise<TripDetailResponse> {
  const response = await api.get<TripDetailResponse>(`/trip/reports/${encodeURIComponent(reportId)}`);
  return response.data;
}

export async function getReportItinerary(reportId: string, force = false): Promise<Itinerary> {
  const response = await api.get<Itinerary>(`/trip/reports/${encodeURIComponent(reportId)}/itinerary`, {
    params: force ? { force: true } : undefined,
    timeout: 600000,
  });
  return response.data;
}

export async function getDeepPlanItinerary(tripId: string, force = false): Promise<Itinerary> {
  const response = await api.get<Itinerary>(`/trip/${encodeURIComponent(tripId)}/deep-itinerary`, {
    params: force ? { force: true } : undefined,
    timeout: 600000,
  });
  return response.data;
}

export function getReportMarkdownUrl(reportId: string): string {
  return `${API_BASE_URL}/trip/reports/${encodeURIComponent(reportId)}/markdown`;
}

export async function deleteTrip(tripId: string): Promise<void> {
  await api.delete(`/trip/${tripId}`);
}

export async function exportTripMarkdown(itinerary: Itinerary): Promise<Blob> {
  const response = await api.post<Blob>("/export/markdown", itinerary, {
    responseType: "blob",
  });
  return response.data;
}

export async function exportTripPdf(itinerary: Itinerary): Promise<Blob> {
  const response = await api.post<Blob>("/export/pdf", itinerary, {
    responseType: "blob",
  });
  return response.data;
}

export async function fetchWeatherForecast(city: string): Promise<WeatherForecastResponse> {
  const response = await api.get<WeatherForecastResponse>("/weather/forecast", {
    params: { city },
  });
  return response.data;
}

export async function fetchLocationSuggestions(
  keyword: string,
  limit = 10
): Promise<LocationSuggestionResponse> {
  const response = await api.get<LocationSuggestionResponse>("/location/suggestions", {
    params: { keyword, limit },
  });
  return response.data;
}

export async function checkDestinationSpan(
  destinations: string[]
): Promise<DestinationSpanCheckResponse> {
  const response = await api.post<DestinationSpanCheckResponse>("/location/span-check", {
    destinations,
  });
  return response.data;
}

export default api;
