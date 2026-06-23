import axios from "axios";

import type {
  Itinerary,
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
  });
  return response.data;
}

export async function getDeepPlanItinerary(tripId: string, force = false): Promise<Itinerary> {
  const response = await api.get<Itinerary>(`/trip/${encodeURIComponent(tripId)}/deep-itinerary`, {
    params: force ? { force: true } : undefined,
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

export default api;
