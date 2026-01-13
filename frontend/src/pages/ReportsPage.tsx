import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  getMonthlyReport,
  listAccounts,
} from "../lib/api";
import type {
  BankAccount,
  MonthlySummaryRow,
} from "../lib/api";

// Color palette for category bars
const COLORS = [
  "#8884d8",
  "#82ca9d",
  "#ffc658",
  "#ff7300",
  "#00C49F",
  "#FFBB28",
  "#FF8042",
  "#a4de6c",
  "#d0ed57",
  "#83a6ed",
  "#8dd1e1",
  "#a28df9",
  "#f97a8d",
  "#c9b4f0",
];

interface MonthlyBarData {
  month: string;
  [category: string]: string | number;
}

interface MonthlyLineData {
  month: string;
  income: number;
  expenses: number;
  net: number;
}

function getDefaultMonthFrom(): string {
  const d = new Date();
  d.setMonth(d.getMonth() - 2); // 2 months back
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function getDefaultMonthTo(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function ReportsPage() {
  // Filter state
  const [monthFrom, setMonthFrom] = useState(getDefaultMonthFrom);
  const [monthTo, setMonthTo] = useState(getDefaultMonthTo);
  const [accountId, setAccountId] = useState<number | "">("");
  const [accounts, setAccounts] = useState<BankAccount[]>([]);

  // Data state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rawData, setRawData] = useState<MonthlySummaryRow[]>([]);

  // Derived chart data
  const [barData, setBarData] = useState<MonthlyBarData[]>([]);
  const [lineData, setLineData] = useState<MonthlyLineData[]>([]);
  const [categories, setCategories] = useState<string[]>([]);

  // Load accounts on mount
  useEffect(() => {
    listAccounts()
      .then(setAccounts)
      .catch((err) => console.error("Failed to load accounts:", err));
  }, []);

  // Transform raw data into chart-friendly formats
  const transformData = useCallback((rows: MonthlySummaryRow[]) => {
    // Group rows by month
    const monthMap = new Map<
      string,
      {
        categories: Map<string, number>;
        income: number;
        expenses: number;
        net: number;
      }
    >();

    // Track total spend per category for sorting
    const categoryTotals = new Map<string, number>();

    for (const row of rows) {
      const month = row.month;
      const categoryName = row.category_name || "Uncategorized";
      const expenseTotal = Math.abs(parseFloat(row.expense_total) || 0);
      const incomeTotal = parseFloat(row.income_total) || 0;
      const netTotal = parseFloat(row.net_total) || 0;

      if (!monthMap.has(month)) {
        monthMap.set(month, {
          categories: new Map(),
          income: 0,
          expenses: 0,
          net: 0,
        });
      }

      const monthData = monthMap.get(month)!;

      // Accumulate category expense (use absolute value for chart)
      const currentCatExpense = monthData.categories.get(categoryName) || 0;
      monthData.categories.set(categoryName, currentCatExpense + expenseTotal);

      // Accumulate totals
      monthData.income += incomeTotal;
      monthData.expenses += expenseTotal;
      monthData.net += netTotal;

      // Track overall category totals for sorting
      const currentTotal = categoryTotals.get(categoryName) || 0;
      categoryTotals.set(categoryName, currentTotal + expenseTotal);
    }

    // Sort categories by total spend descending
    const sortedCategories = Array.from(categoryTotals.entries())
      .filter(([, total]) => total > 0) // Only include categories with expenses
      .sort((a, b) => b[1] - a[1])
      .map(([name]) => name);

    // Build bar chart data (sorted by month)
    const sortedMonths = Array.from(monthMap.keys()).sort();
    const barChartData: MonthlyBarData[] = sortedMonths.map((month) => {
      const data = monthMap.get(month)!;
      const barRow: MonthlyBarData = { month };

      for (const cat of sortedCategories) {
        barRow[cat] = Math.round((data.categories.get(cat) || 0) * 100) / 100;
      }

      return barRow;
    });

    // Build line chart data
    const lineChartData: MonthlyLineData[] = sortedMonths.map((month) => {
      const data = monthMap.get(month)!;
      return {
        month,
        income: Math.round(data.income * 100) / 100,
        expenses: Math.round(data.expenses * 100) / 100,
        net: Math.round(data.net * 100) / 100,
      };
    });

    setBarData(barChartData);
    setLineData(lineChartData);
    setCategories(sortedCategories);
  }, []);

  // Run report
  const handleRun = async () => {
    if (!monthFrom || !monthTo) {
      setError("Please select both month from and month to.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const data = await getMonthlyReport(
        monthFrom,
        monthTo,
        accountId !== "" ? accountId : undefined
      );
      setRawData(data);
      transformData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load report");
    } finally {
      setLoading(false);
    }
  };

  const hasData = barData.length > 0 || lineData.length > 0;

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Reports
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        View monthly spending reports and trends.
      </Typography>

      {/* Filters */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={2} alignItems="center">
          <TextField
            label="From"
            type="month"
            value={monthFrom}
            onChange={(e) => setMonthFrom(e.target.value)}
            size="small"
            InputLabelProps={{ shrink: true }}
            sx={{ minWidth: 150 }}
          />
          <TextField
            label="To"
            type="month"
            value={monthTo}
            onChange={(e) => setMonthTo(e.target.value)}
            size="small"
            InputLabelProps={{ shrink: true }}
            sx={{ minWidth: 150 }}
          />
          <FormControl size="small" sx={{ minWidth: 180 }}>
            <InputLabel>Account</InputLabel>
            <Select<number | "">
              value={accountId}
              label="Account"
              onChange={(e) => {
                const val = e.target.value;
                setAccountId(val === "" ? "" : Number(val));
              }}
            >
              <MenuItem value="">All Accounts</MenuItem>
              {accounts.map((acc) => (
                <MenuItem key={acc.id} value={acc.id}>
                  {acc.display_name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <Button variant="contained" onClick={handleRun} disabled={loading}>
            {loading ? <CircularProgress size={24} /> : "Run"}
          </Button>
        </Stack>
      </Paper>

      {/* Error */}
      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {/* Loading */}
      {loading && (
        <Box display="flex" justifyContent="center" py={4}>
          <CircularProgress />
        </Box>
      )}

      {/* Empty state */}
      {!loading && !hasData && rawData.length === 0 && (
        <Paper sx={{ p: 4, textAlign: "center" }}>
          <Typography color="text.secondary">
            No data yet. Select a date range and click "Run" to generate a report.
          </Typography>
        </Paper>
      )}

      {/* Charts */}
      {!loading && hasData && (
        <Stack spacing={4}>
          {/* Stacked Bar Chart - Expenses by Category */}
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Expenses by Category
            </Typography>
            <ResponsiveContainer width="100%" height={400}>
              <BarChart data={barData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" />
                <YAxis
                  tickFormatter={(value) =>
                    `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                  }
                />
                <Tooltip
                  formatter={(value) => [
                    `$${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2 })}`,
                  ]}
                />
                <Legend />
                {categories.map((cat, idx) => (
                  <Bar
                    key={cat}
                    dataKey={cat}
                    stackId="expenses"
                    fill={COLORS[idx % COLORS.length]}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </Paper>

          {/* Line Chart - Income, Expenses, Net */}
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Income vs Expenses
            </Typography>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={lineData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="month" />
                <YAxis
                  tickFormatter={(value) =>
                    `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                  }
                />
                <Tooltip
                  formatter={(value) => [
                    `$${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2 })}`,
                  ]}
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="income"
                  stroke="#4caf50"
                  strokeWidth={2}
                  name="Income"
                />
                <Line
                  type="monotone"
                  dataKey="expenses"
                  stroke="#f44336"
                  strokeWidth={2}
                  name="Expenses"
                />
                <Line
                  type="monotone"
                  dataKey="net"
                  stroke="#2196f3"
                  strokeWidth={2}
                  name="Net"
                />
              </LineChart>
            </ResponsiveContainer>
          </Paper>
        </Stack>
      )}
    </Box>
  );
}
