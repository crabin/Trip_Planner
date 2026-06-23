export interface TripRequestPayload {
  destination: string;
  start_date: string;
  end_date: string;
  travelers: number;
  budget: number;
  preferences: string[];
  pace?: string | null;
  dietary_preferences: string[];
  hotel_level?: string | null;
  special_notes?: string | null;
  deep_planning_reflection_rounds: number;
  deep_planning_search_engine: "tavily" | "searxng";
}

export interface TripEditPayload {
  trip_id: string;
  current_itinerary: Itinerary;
  user_instruction: string;
  edit_scope?: string | null;
  preserve_constraints: string[];
}

export interface SpotItem {
  name: string;
  start_time?: string | null;
  end_time?: string | null;
  description?: string | null;
  estimated_cost?: number | null;
  location?: string | null;
  image_url?: string | null;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  poi_id?: string | null;
  map_rating?: number | null;
  map_average_cost?: number | null;
  map_tags?: string[];
  map_tel?: string | null;
  map_distance_meters?: number | null;
  map_type?: string | null;
  map_typecode?: string | null;
  map_business_area?: string | null;
  map_open_time_today?: string | null;
  map_open_time_week?: string | null;
  map_query?: string | null;
  data_source?: string | null;
  source_id?: string | null;
  source_url?: string | null;
  review_count?: number | null;
  ranking_label?: string | null;
  recommendation_score?: number | null;
  recommendation_reason?: string | null;
  is_recommended?: boolean;
}

export interface MealItem {
  name: string;
  meal_type: string;
  estimated_cost?: number;
  notes?: string | null;
  image_url?: string | null;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  poi_id?: string | null;
  map_rating?: number | null;
  map_average_cost?: number | null;
  map_tags?: string[];
  map_tel?: string | null;
  map_distance_meters?: number | null;
  map_type?: string | null;
  map_typecode?: string | null;
  map_business_area?: string | null;
  map_open_time_today?: string | null;
  map_open_time_week?: string | null;
  map_query?: string | null;
  data_source?: string | null;
  source_id?: string | null;
  source_url?: string | null;
  review_count?: number | null;
  ranking_label?: string | null;
  recommendation_score?: number | null;
  recommendation_reason?: string | null;
  is_recommended?: boolean;
}

export interface HotelItem {
  name: string;
  level?: string | null;
  estimated_cost?: number;
  location?: string | null;
  address?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  image_url?: string | null;
  poi_id?: string | null;
  map_rating?: number | null;
  map_average_cost?: number | null;
  map_tags?: string[];
  map_tel?: string | null;
  map_distance_meters?: number | null;
  map_type?: string | null;
  map_typecode?: string | null;
  map_business_area?: string | null;
  map_open_time_today?: string | null;
  map_open_time_week?: string | null;
  map_query?: string | null;
  data_source?: string | null;
  source_id?: string | null;
  source_url?: string | null;
  review_count?: number | null;
  ranking_label?: string | null;
  recommendation_score?: number | null;
  recommendation_reason?: string | null;
  is_recommended?: boolean;
}

export interface TransportItem {
  mode: string;
  from_place?: string | null;
  to_place?: string | null;
  estimated_cost?: number;
  duration?: string | null;
  distance_km?: number | null;
  estimated_minutes?: number | null;
}

export interface DayPlan {
  day_index: number;
  date?: string | null;
  theme?: string | null;
  spots: SpotItem[];
  meals: MealItem[];
  hotel?: HotelItem | null;
  hotel_candidates?: HotelItem[];
  meal_candidates?: MealItem[];
  transport: TransportItem[];
  notes: string[];
}

export interface BudgetBreakdown {
  transport: number;
  hotel: number;
  meals: number;
  tickets: number;
  other: number;
  total: number;
}

export interface DisplayTextItem {
  key: string;
  label: string;
  value: string;
  source_path?: string | null;
}

export interface DisplayChecklistItem {
  key: string;
  text: string;
  checked: boolean;
  source_path?: string | null;
}

export interface DisplayBudgetItem {
  key: string;
  label: string;
  amount: number;
  formatted: string;
  source_path?: string | null;
}

export interface DisplayMapPoint {
  key: string;
  kind: "spot" | "meal" | "hotel";
  label: string;
  day_index: number;
  date?: string | null;
  theme: string;
  name: string;
  address: string;
  latitude?: number | null;
  longitude?: number | null;
  poi_id?: string | null;
  image_url?: string | null;
  description: string;
  rating?: number | null;
  average_cost?: number | null;
  estimated_cost?: number | null;
  tags: string[];
  distance_meters?: number | null;
  tel?: string | null;
  business_area?: string | null;
  open_time_today?: string | null;
  map_type?: string | null;
  recommended: boolean;
  source_path?: string | null;
}

export interface DisplayRecommendationItem {
  key: string;
  kind: "meal" | "hotel";
  day_index: number;
  date?: string | null;
  theme: string;
  title: string;
  subtitle: string;
  reason: string;
  image_url?: string | null;
  meta: string[];
  tags: string[];
  contact: string;
  note: string;
  source_path?: string | null;
}

export interface DisplayDayCard {
  key: string;
  day_index: number;
  title: string;
  subtitle: string;
  date?: string | null;
  theme: string;
  fields: DisplayTextItem[];
  notes: string[];
  source_path?: string | null;
}

export interface DisplaySection {
  key: string;
  title: string;
  kind:
    | "overview"
    | "budget"
    | "day_budget"
    | "tips"
    | "map"
    | "weather"
    | "recommendations"
    | "poi_details"
    | "daily_plan"
    | "editor";
  order: number;
  visible: boolean;
  summary: string;
  item_keys: string[];
}

export interface ItineraryDisplay {
  version: "itinerary-display-v1" | string;
  title: string;
  subtitle: string;
  overview: DisplayTextItem[];
  plan_highlights: DisplayTextItem[];
  confirmations: DisplayTextItem[];
  tips: string[];
  tip_items: DisplayChecklistItem[];
  budget_items: DisplayBudgetItem[];
  day_budget_items: DisplayBudgetItem[];
  map_points: DisplayMapPoint[];
  scenic_points: DisplayMapPoint[];
  hotel_recommendations: DisplayRecommendationItem[];
  meal_recommendations: DisplayRecommendationItem[];
  day_cards: DisplayDayCard[];
  sections: DisplaySection[];
}

export interface Itinerary {
  trip_id: string;
  destination: string;
  summary: string;
  days: DayPlan[];
  estimated_budget: number;
  budget_breakdown: BudgetBreakdown;
  tips: string[];
  source_notes: string[];
  display?: ItineraryDisplay | null;
}

export interface TripSaveResponse {
  message: string;
  trip_id: string;
}

export interface TripSummaryItem {
  trip_id: string;
  destination: string;
  summary: string;
  plan_type: "quick" | "deep";
  status: "generating" | "completed" | "failed";
  progress: number;
  display_title: string;
  detail_title: string;
  start_date?: string | null;
  end_date?: string | null;
  error_message?: string | null;
  has_detail: boolean;
  has_itinerary: boolean;
  has_report: boolean;
  report_id?: string | null;
  is_report_only: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TripListResponse {
  total: number;
  items: TripSummaryItem[];
}

export interface ChatbotConversationMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatbotSearchSource {
  title: string;
  url: string;
  content: string;
  published_date?: string | null;
  score?: number | null;
}

export interface ChatbotMessagePayload {
  message: string;
  trip_id?: string | null;
  current_itinerary?: Itinerary | null;
  history: ChatbotConversationMessage[];
}

export interface ChatbotMessageResponse {
  intent: "ask" | "update" | "search";
  reply: string;
  reason: string;
  updated_itinerary?: Itinerary | null;
  sources: ChatbotSearchSource[];
}

export interface TripDetailResponse {
  trip_id: string;
  plan_type: "quick" | "deep";
  status: "generating" | "completed" | "failed";
  progress: number;
  display_title: string;
  detail_title: string;
  start_date?: string | null;
  end_date?: string | null;
  itinerary?: Itinerary | null;
  deep_plan?: DeepPlanDocument | null;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface DeepPlanSource {
  section_title: string;
  query: string;
  title: string;
  url: string;
  content: string;
  score?: number | null;
  published_date?: string | null;
}

export interface DeepPlanDocument {
  markdown: string;
  sources: DeepPlanSource[];
}

export interface WeatherForecastDay {
  date?: string | null;
  week?: string | null;
  day_weather?: string | null;
  night_weather?: string | null;
  day_temp?: string | null;
  night_temp?: string | null;
  day_wind?: string | null;
  night_wind?: string | null;
}

export interface WeatherForecastResponse {
  city: string;
  province?: string | null;
  adcode?: string | null;
  report_time?: string | null;
  days: WeatherForecastDay[];
}
