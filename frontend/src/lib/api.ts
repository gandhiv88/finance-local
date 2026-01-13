const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const TOKEN_KEY = "auth_token";

// ============================================================================
// Token management
// ============================================================================

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

// ============================================================================
// Generic fetch wrapper
// ============================================================================

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const headers = new Headers(options.headers);

  // Add auth header if token exists
  const token = getToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  // Auto-set JSON content type if body is an object (and not FormData)
  if (options.body && typeof options.body === "object" && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
    options.body = JSON.stringify(options.body);
  }

  const response = await fetch(url, { ...options, headers });

  if (!response.ok) {
    // Try to extract error message from backend
    let message = `Request failed with status ${response.status}`;
    try {
      const data = await response.json();
      if (data.detail) {
        message = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      }
    } catch {
      // Ignore JSON parse errors
    }
    throw new Error(message);
  }

  // Return empty object for 204 No Content
  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

// ============================================================================
// Types
// ============================================================================

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface User {
  id: number;
  household_id: number;
  name: string | null;
  email: string;
  role: string | null;
  is_active: boolean;
  created_at: string;
}

export interface BankAccount {
  id: number;
  household_id: number;
  bank_code: string | null;
  display_name: string;
  currency: string;
  created_at: string;
}

export interface ImportResult {
  id: number;
  bank_account_id: number;
  original_filename: string | null;
  bank_code: string | null;
  imported_count: number;
  skipped_count: number;
  warning_count: number;
  created_at: string;
}

export interface Category {
  id: number;
  household_id: number;
  name: string;
  parent_id: number | null;
  is_active: boolean;
  created_at: string;
}

export interface Merchant {
  id: number;
  household_id: number;
  merchant_key: string;
  display_name: string;
  default_category_id: number | null;
  confidence: number | null;
  created_at: string;
}

export interface Transaction {
  id: number;
  bank_account_id: number;
  import_id: number;
  posted_date: string;
  description: string;
  merchant: string | null;
  merchant_key: string | null;
  merchant_id: number | null;
  merchant_ref: Merchant | null;
  amount: string; // Decimal as string
  category_id: number | null;
  category: Category | null;
  is_reviewed: boolean;
  created_at: string;
}

export interface Budget {
  id: number;
  household_id: number;
  month: string;
  category_id: number;
  limit_amount: string;
  created_at: string;
}

export interface MonthlySummaryRow {
  month: string;
  category_id: number | null;
  category_name: string | null;
  income_total: string;
  expense_total: string;
  net_total: string;
  tx_count: number;
  budget_limit: string | null;
  budget_used_pct: number | null;
}

export interface Insight {
  type: string;
  title: string;
  detail: string;
  severity: "info" | "warning";
  // Optional metadata from backend
  category_id?: number | null;
  merchant_id?: number | null;
  amount?: string | null;
}

export interface ListTransactionsParams {
  account_id?: number;
  month?: string;
  category_id?: number;
  uncategorized?: boolean;
  page?: number;
  page_size?: number;
}

export interface TransactionsPage {
  items: Transaction[];
  total: number;
  page: number;
  page_size: number;
}

// ============================================================================
// API Methods
// ============================================================================

export async function login(email: string, password: string): Promise<LoginResponse> {
  return apiFetch<LoginResponse>("/auth/login", {
    method: "POST",
    body: { email, password } as unknown as BodyInit,
  });
}

export async function me(): Promise<User> {
  return apiFetch<User>("/auth/me");
}

export async function listAccounts(): Promise<BankAccount[]> {
  return apiFetch<BankAccount[]>("/accounts");
}

export async function uploadImport(bankAccountId: number, file: File): Promise<ImportResult> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("bank_account_id", String(bankAccountId));

  return apiFetch<ImportResult>("/imports", {
    method: "POST",
    body: formData,
  });
}

export async function listTransactions(params: ListTransactionsParams = {}): Promise<TransactionsPage> {
  const searchParams = new URLSearchParams();

  if (params.account_id !== undefined) {
    searchParams.set("account_id", String(params.account_id));
  }
  if (params.month) {
    searchParams.set("month", params.month);
  }
  if (params.category_id !== undefined) {
    searchParams.set("category_id", String(params.category_id));
  }
  if (params.uncategorized !== undefined) {
    searchParams.set("uncategorized", params.uncategorized ? "true" : "false");
  }
  if (params.page !== undefined) {
    searchParams.set("page", String(params.page));
  }
  if (params.page_size !== undefined) {
    searchParams.set("page_size", String(params.page_size));
  }

  const queryString = searchParams.toString();
  const path = queryString ? `/transactions?${queryString}` : "/transactions";

  return apiFetch<TransactionsPage>(path);
}

export interface PatchTransactionParams {
  category_id?: number | null;
  is_reviewed?: boolean;
  create_merchant_override?: boolean;
}

export async function patchTransaction(
  transactionId: number,
  params: PatchTransactionParams
): Promise<Transaction> {
  return apiFetch<Transaction>(`/transactions/${transactionId}`, {
    method: "PATCH",
    body: params as unknown as BodyInit,
  });
}

export async function listCategories(): Promise<Category[]> {
  return apiFetch<Category[]>("/categories");
}

export interface SeedCategoriesResponse {
  created: number;
}

export async function seedCategories(): Promise<SeedCategoriesResponse> {
  return apiFetch<SeedCategoriesResponse>("/categories/seed-defaults", { method: "POST" });
}

export async function listBudgets(month?: string): Promise<Budget[]> {
  const path = month ? `/budgets?month=${month}` : "/budgets";
  return apiFetch<Budget[]>(path);
}

export async function upsertBudget(payload: {
  month: string;
  category_id: number;
  limit_amount: string;
}): Promise<Budget> {
  return apiFetch<Budget>("/budgets", {
    method: "POST",
    body: payload as unknown as BodyInit,
  });
}

export async function deleteBudget(id: number): Promise<Budget> {
  return apiFetch<Budget>(`/budgets/${id}`, {
    method: "DELETE"
  });
}

export async function getMonthlyReport(
  monthFrom: string,
  monthTo: string,
  accountId?: number
): Promise<MonthlySummaryRow[]> {
  const params = new URLSearchParams({
    month_from: monthFrom,
    month_to: monthTo,
  });

  if (accountId !== undefined) {
    params.set("account_id", String(accountId));
  }

  return apiFetch<MonthlySummaryRow[]>(`/reports/monthly?${params.toString()}`);
}

export async function getMonthlyInsights(month: string): Promise<Insight[]> {
  return apiFetch<Insight[]>(`/insights/monthly?month=${month}`);
}

export interface RecategorizeMerchantResponse {
  updated: number;
}

export async function recategorizeMerchant(
  merchantId: number,
  onlyUncategorized: boolean = true
): Promise<RecategorizeMerchantResponse> {
  const params = new URLSearchParams({
    merchant_id: String(merchantId),
    only_uncategorized: String(onlyUncategorized),
  });
  return apiFetch<RecategorizeMerchantResponse>(
    `/maintenance/recategorize-merchant?${params.toString()}`,
    { method: "POST" }
  );
}

export interface BulkUpdateTransactionsParams {
  transaction_ids: number[];
  category_id?: number | null;
  is_reviewed?: boolean;
  apply_to_merchant?: boolean;
}

export interface BulkUpdateTransactionsResponse {
  updated_transactions: number;
  updated_merchants: number;
  skipped: number;
}

export async function bulkUpdateTransactions(
  params: BulkUpdateTransactionsParams
): Promise<BulkUpdateTransactionsResponse> {
  return apiFetch<BulkUpdateTransactionsResponse>("/transactions/bulk-update", {
    method: "POST",
    body: params as unknown as BodyInit,
  });
}

export async function createCategory(payload: {
  name: string;
  parent_id?: number | null;
}): Promise<Category> {
  return apiFetch<Category>("/categories", {
    method: "POST",
    body: payload as unknown as BodyInit,
  });
}

export async function updateCategory(
  id: number,
  payload: {
    name?: string;
    parent_id?: number | null;
    is_active?: boolean;
  }
): Promise<Category> {
  return apiFetch<Category>(`/categories/${id}`, {
    method: "PATCH",
    body: payload as unknown as BodyInit,
  });
}

export async function deleteCategory(id: number): Promise<Category> {
  return apiFetch<Category>(`/categories/${id}`, {
    method: "DELETE"
  });
}
