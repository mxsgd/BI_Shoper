const BASE = "/api";
const STORE_ID = 1;

async function get<T>(path: string, params: Record<string, string | number | undefined | null> = {}): Promise<T> {
  const qs = new URLSearchParams({ store_id: String(STORE_ID) });
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null) continue;
    qs.set(k, String(v));
  }
  const res = await fetch(`${BASE}${path}?${qs}`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export interface OverviewData {
  period_days: number;
  focus_date?: string | null;
  date_from: string;
  date_to: string;
  revenue: number;
  revenue_delta_pct: number | null;
  orders: number;
  orders_delta_pct: number | null;
  aov: number;
  aov_delta_pct: number | null;
  customers: number;
  customers_delta_pct: number | null;
  avg_items_per_order: number;
  paid_pct: number;
}

export interface RevenuePoint {
  date: string;
  orders: number;
  revenue: number;
  discounts: number;
  shipping: number;
}

export interface RevenueData {
  period_days: number;
  group_by: string;
  focus_date?: string | null;
  time_series: RevenuePoint[];
  by_status: { status: string; orders: number; revenue: number }[];
  by_channel: { channel: string; orders: number; revenue: number }[];
}

export interface TopProduct {
  product_id: number;
  name: string;
  category: string | null;
  quantity: number;
  revenue: number;
  orders: number;
  revenue_pct: number;
  cumulative_pct: number;
}

export interface TopProductsData {
  period_days: number;
  sort_by: string;
  products: TopProduct[];
}

export interface CustomerSegment {
  type: string;
  count: number;
  revenue: number;
  avg_orders: number;
  avg_revenue: number;
}

export interface TopCustomer {
  customer_id: number;
  total_orders: number;
  total_revenue: number;
  first_order: string | null;
  last_order: string | null;
  type: string;
}

export interface CustomersData {
  period_days: number;
  segmentation: CustomerSegment[];
  top_customers: TopCustomer[];
  new_customers_monthly: { month: string; count: number }[];
  retention: {
    total_buyers: number;
    repeat_buyers: number;
    one_time_buyers: number;
    repeat_rate_pct: number;
  };
}

export interface TrendDaily {
  date: string;
  revenue: number;
  orders: number;
  ma7: number;
  ma30: number;
}

export interface TrendMonthly {
  month: string;
  revenue: number;
  orders: number;
  mom_growth_pct: number | null;
  yoy_growth_pct: number | null;
}

export interface TrendsData {
  period_days: number;
  daily: TrendDaily[];
  monthly: TrendMonthly[];
  weekday_pattern: { day_of_week: number; avg_revenue: number; avg_orders: number }[];
}

export interface CohortMonth {
  month_offset: number;
  active: number;
  retention_pct: number;
}

export interface Cohort {
  cohort_month: string;
  size: number;
  months: CohortMonth[];
}

export interface CohortData {
  cohorts: Cohort[];
}

export interface RfmSegment {
  name: string;
  count: number;
  avg_revenue: number;
  avg_orders: number;
  avg_recency_days: number;
}

export interface RfmData {
  segments: RfmSegment[];
  distribution: Record<string, number>;
  summary: {
    total_customers: number;
    avg_clv: number;
    total_revenue: number;
  };
}

export interface ChannelSummary {
  channel: string;
  total_orders: number;
  total_revenue: number;
  aov: number;
  pct_of_total: number;
}

export interface ChannelData {
  period_days: number;
  time_series: Record<string, unknown>[];
  channels: string[];
  summary: ChannelSummary[];
}

export interface TrafficOverview {
  sessions: number;
  users: number;
  new_users: number;
  bounce_rate: number;
  avg_session_duration: number;
}

export interface TrafficConversion {
  sessions: number;
  orders: number;
  conversion_rate: number;
  revenue: number;
  revenue_per_session: number;
}

export interface TrafficTimePoint {
  date: string;
  sessions: number;
  users: number;
  orders: number;
  conversion_rate: number;
}

export interface TrafficSource {
  source: string;
  medium: string;
  sessions: number;
  users: number;
  new_users: number;
  engaged: number;
  conversions: number;
}

export interface TrafficPage {
  page_path: string;
  views: number;
  avg_time: number;
  entrances: number;
}

export interface TrafficGeo {
  country: string;
  city: string;
  sessions: number;
  users: number;
}

export interface TrafficDevice {
  device_category: string;
  sessions: number;
  users: number;
  pct: number;
}

export interface TrafficData {
  has_data: boolean;
  focus_date?: string | null;
  overview: TrafficOverview | null;
  conversion: TrafficConversion | null;
  time_series: TrafficTimePoint[];
  sources: TrafficSource[];
  top_pages: TrafficPage[];
  geo: TrafficGeo[];
  devices: TrafficDevice[];
}

export const api = {
  overview: (period = 30, focusDate?: string) =>
    get<OverviewData>("/analytics/overview", { period, focus_date: focusDate || undefined }),
  revenue: (period = 30, group_by = "day", focusDate?: string) =>
    get<RevenueData>("/analytics/revenue", { period, group_by, focus_date: focusDate || undefined }),
  topProducts: (period = 90, limit = 20) => get<TopProductsData>("/analytics/top-products", { period, limit }),
  customers: (period = 90) => get<CustomersData>("/analytics/customers", { period }),
  trends: (period = 365) => get<TrendsData>("/analytics/trends", { period }),
  cohorts: (months = 12) => get<CohortData>("/analytics/cohorts", { months }),
  rfm: () => get<RfmData>("/analytics/rfm"),
  channels: (period = 90, group_by = "month") => get<ChannelData>("/analytics/channels", { period, group_by }),
  traffic: (period = 30, focusDate?: string) =>
    get<TrafficData>("/analytics/traffic", { period, focus_date: focusDate || undefined }),
};
