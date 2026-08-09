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

async function post<T>(path: string, body: unknown = {}): Promise<T> {
  const qs = new URLSearchParams({ store_id: String(STORE_ID) });
  const res = await fetch(`${BASE}${path}?${qs}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

async function postForm<T>(path: string, formData: FormData, params: Record<string, string | number | undefined> = {}): Promise<T> {
  const qs = new URLSearchParams({ store_id: String(STORE_ID) });
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined) continue;
    qs.set(k, String(v));
  }
  const res = await fetch(`${BASE}${path}?${qs}`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
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
  by_category: { category: string; orders: number; revenue: number; quantity: number }[];
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

export interface TrafficFunnel {
  view_item: number;
  add_to_cart: number;
  begin_checkout: number;
  add_payment_info: number;
  purchase: number;
  add_to_cart_rate: number;
  cart_abandonment_rate: number;
  checkout_abandonment_rate: number;
  payment_to_purchase_rate: number;
  overall_conversion_rate: number;
}

export interface TrafficData {
  has_data: boolean;
  data_through?: string | null;
  focus_date?: string | null;
  overview: TrafficOverview | null;
  conversion: TrafficConversion | null;
  funnel: TrafficFunnel | null;
  time_series: TrafficTimePoint[];
  sources: TrafficSource[];
  top_pages: TrafficPage[];
  geo: TrafficGeo[];
  devices: TrafficDevice[];
}

export interface CartFunnel {
  view_item: number;
  add_to_cart: number;
  begin_checkout: number;
  add_payment_info: number;
  purchase: number;
  remove_from_cart: number;
  abandoned: number;
  add_to_cart_rate: number;
  cart_abandonment_rate: number;
  checkout_abandonment_rate: number;
  payment_to_purchase_rate: number;
  overall_conversion_rate: number;
  avg_cart_value: number;
  avg_purchase_value: number;
}

export interface CartDeviceSegment {
  device: string;
  view_item: number;
  add_to_cart: number;
  begin_checkout: number;
  add_payment_info: number;
  purchase: number;
  remove_from_cart: number;
  add_to_cart_rate: number;
  cart_to_purchase_rate: number;
}

export interface CartProduct {
  name: string;
  item_id: string | null;
  add_to_cart: number;
  purchases: number;
  drop_off: number;
  drop_off_pct: number;
  revenue: number;
}

export interface CartOrderMetrics {
  total_orders: number;
  avg_order_value: number;
  avg_items_per_order: number;
  single_item_pct: number;
  multi_item_pct: number;
  discount_pct: number;
  avg_value_with_discount: number;
  avg_value_without_discount: number;
}

export interface CartData {
  period_days: number;
  has_funnel_data: boolean;
  funnel: CartFunnel | null;
  funnel_time_series: { date: string; view_item: number; add_to_cart: number; begin_checkout: number; purchase: number; remove_from_cart: number }[];
  device_segments: CartDeviceSegment[];
  top_abandoned_products: CartProduct[];
  order_metrics: CartOrderMetrics;
  items_histogram: { items: number; orders: number }[];
  abandoned_vs_purchased: { date: string; purchased: number; abandoned: number }[];
}

export interface TrackerEventSummary {
  period_days: number;
  total_events: number;
  distinct_users: number;
  since_iso: string;
  by_event: { event_name: string; count: number }[];
  top_urls: { url: string; count: number }[];
}

export interface PriceUpdateValidationError {
  row_number: number;
  code: string;
  error_message: string;
}

export interface PriceUpdateStats {
  total: number;
  processed: number;
  success: number;
  failed: number;
  skipped: number;
  warning: number;
  deactivated_variants: number;
  logs_total: number;
  logs_in_memory?: number;
  logs_dropped?: number;
  log_seq?: number;
  eta_seconds?: number | null;
  current_row_number?: number | null;
  current_code?: string | null;
  current_phase?: string | null;
  success_rate: number;
  failure_rate: number;
  coverage_rate: number;
}

export type PriceUpdateTargetMode = "product" | "variant";
export type PriceUpdateCsvDelimiter = "comma" | "semicolon" | "tab" | "pipe";

export interface PriceUpdateJob {
  job_id: string;
  store_id?: number;
  file_name: string;
  target_mode?: PriceUpdateTargetMode;
  csv_delimiter?: PriceUpdateCsvDelimiter;
  disable_extra_variants?: boolean;
  status: "PENDING" | "RUNNING" | "DONE" | "FAILED" | "CANCELLED";
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  fatal_error?: string | null;
  validation: {
    valid_rows: number;
    invalid_rows: number;
    errors: PriceUpdateValidationError[];
  };
  stats: PriceUpdateStats;
}

export interface PriceUpdateLogItem {
  timestamp: string;
  job_id: string;
  row_number: number;
  code: string;
  old_price: number | null;
  new_price: number | null;
  status: "SUCCESS" | "ERROR" | "WARNING" | "SKIPPED";
  message: string;
  http_status: number | null;
  request_id: string | null;
  comment: string | null;
}

export interface PriceUpdateLogsResponse {
  items: PriceUpdateLogItem[];
  page: number;
  per_page: number;
  total: number;
  pages: number;
  logs_dropped?: number;
  logs_in_memory?: number;
}

export interface StoreSyncStatus {
  store_id: number | null;
  scope: string | null;
  status: "idle" | "running" | "done" | "error";
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  result: Record<string, unknown> | null;
  already_running?: boolean;
}

// ─── Variant Code Generator ────────────────────────────────────────────────

export interface VariantGroup {
  group_id: number;
  name: string;
  product_count: number;
}

export interface SyncVariantGroupResult {
  group: VariantGroup;
  group_synced: number;
  products: number;
  stocks: number;
}

export interface VariantProduct {
  product_id: number;
  code: string;
  name: string;
  group_id: number | null;
}

export interface VariantStock {
  stock_id: number;
  code: string;
  active: boolean | null;
  extended: boolean | null;
  price: number;
}

// ─── Option detection ──────────────────────────────────────────────────────

export interface DetectedOptionValue {
  value_id: string;
  value_name: string;
  suggested_suffix: string;
}

export interface DetectedOptionGroup {
  group_id: string;
  role: "size" | "fabric" | "other";
  values: DetectedOptionValue[];
  available_values: DetectedOptionValue[];
}

export interface DetectOptionsResult {
  groups: DetectedOptionGroup[];
  total_stocks: number;
}

// ─── Apply codes job ───────────────────────────────────────────────────────

export interface OptionValueMapping {
  value_id: string;
  suffix: string;
}

export interface OptionGroupConfig {
  group_id: string;
  role: string;
  values: OptionValueMapping[];
}

export interface ApplyCodesRequest {
  store_id: number;
  product_ids: number[];
  option_groups: OptionGroupConfig[];
  prices: Record<string, number>;
  create_missing: boolean;
  supplement_mode?: boolean;
}

export interface ApplyCodesJob {
  status: "running" | "done";
  total: number;
  done: number;
  ok: number;
  skip: number;
  err: number;
  log: string[];
}

export interface CreateVariantStocksRequest {
  store_id: number;
  products: { product_id: number; code: string }[];
  segments: { name: string; values: string[] }[];
  default_price: number;
  skip_existing: boolean;
}

export interface CreateVariantStocksResult {
  results: { code: string; status: "created" | "skipped" | "error"; message?: string; stock_id?: number }[];
  summary: { created: number; skipped: number; errors: number; total: number };
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
  cart: (period = 30) => get<CartData>("/analytics/cart", { period }),
  tracker: (period = 7) => get<TrackerEventSummary>("/analytics/tracker", { period }),
  syncNow: (scope: "quick" | "all" | "orders" | "products" | "customers" | "reference" | "transform" | "ga4" = "quick") =>
    post<Record<string, unknown>>("/stores/sync-now", { store_id: STORE_ID, scope }),
  getSyncStatus: () => get<StoreSyncStatus>(`/stores/${STORE_ID}/sync-status`),
  createPriceUpdateJob: (
    file: File,
    options: {
      duplicate_mode?: "error" | "last_wins";
      target_mode?: PriceUpdateTargetMode;
      csv_delimiter?: PriceUpdateCsvDelimiter;
      disable_extra_variants?: boolean;
    } = {},
  ) => {
    const form = new FormData();
    form.append("file", file);
    return postForm<PriceUpdateJob>("/price-update/jobs", form, {
      duplicate_mode: options.duplicate_mode ?? "error",
      target_mode: options.target_mode ?? "product",
      csv_delimiter: options.csv_delimiter ?? "semicolon",
      disable_extra_variants: String(options.disable_extra_variants ?? true),
    });
  },
  getPriceUpdateJob: (jobId: string) => get<PriceUpdateJob>(`/price-update/jobs/${jobId}`),
  getActivePriceUpdateJob: () => get<{ job: PriceUpdateJob | null }>("/price-update/jobs/active"),
  getLatestPriceUpdateJob: () => get<{ job: PriceUpdateJob | null }>("/price-update/jobs/latest"),
  cancelPriceUpdateJob: (jobId: string) => post<{ job_id: string; status: string; cancel_requested: boolean }>(`/price-update/jobs/${jobId}/cancel`, {}),
  getPriceUpdateLogs: (
    jobId: string,
    params: {
      status?: "ALL" | "SUCCESS" | "ERROR" | "WARNING" | "SKIPPED";
      query?: string;
      page?: number;
      per_page?: number;
      tail?: number;
    } = {},
  ) => get<PriceUpdateLogsResponse>(`/price-update/jobs/${jobId}/logs`, params),
  getPriceUpdateLogsExportUrl: (jobId: string) => `${BASE}/price-update/jobs/${jobId}/logs/export.csv`,

  // Variant code generator
  getVariantGroups: (params: { refresh?: boolean } = {}) =>
    get<VariantGroup[]>("/variant-codes/groups", { refresh: params.refresh ? 1 : undefined }),
  syncVariantGroup: (groupId: number) =>
    post<SyncVariantGroupResult>(`/variant-codes/groups/${groupId}/sync`),
  searchVariantProducts: (params: { q?: string; group_id?: number; limit?: number } = {}) =>
    get<VariantProduct[]>("/variant-codes/search-products", params),
  getProductVariantStocks: (productId: number) =>
    get<VariantStock[]>(`/variant-codes/products/${productId}/stocks`),
  detectOptions: (productId: number) =>
    get<DetectOptionsResult>("/variant-codes/detect-options", { product_id: productId }),
  detectOptionsMulti: (productIds: number[]) =>
    get<DetectOptionsResult>("/variant-codes/detect-options-multi", { product_ids: productIds.join(",") }),
  startApplyCodes: (body: ApplyCodesRequest) =>
    post<{ job_id: string }>("/variant-codes/apply-codes/start", body),
  getApplyCodesJob: (jobId: string) =>
    get<ApplyCodesJob>(`/variant-codes/apply-codes/jobs/${jobId}`),
  createVariantStocks: (body: CreateVariantStocksRequest) =>
    post<CreateVariantStocksResult>("/variant-codes/create-stocks", body),
};
