import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  CardActions,
  CardContent,
  CircularProgress,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import {
  Lightbulb as LightbulbIcon,
  Warning as WarningIcon,
} from "@mui/icons-material";
import { getMonthlyInsights } from "../lib/api";
import type { Insight } from "../lib/api";

function getCurrentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function InsightsPage() {
  const navigate = useNavigate();

  // State
  const [month, setMonth] = useState(getCurrentMonth);
  const [insights, setInsights] = useState<Insight[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasFetched, setHasFetched] = useState(false);

  // Fetch insights
  const fetchInsights = useCallback(async () => {
    if (!month) {
      setError("Please select a month.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const data = await getMonthlyInsights(month);
      setInsights(data);
      setHasFetched(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load insights");
    } finally {
      setLoading(false);
    }
  }, [month]);

  // Fetch on mount
  useEffect(() => {
    fetchInsights();
  }, [fetchInsights]);

  // Navigate to transactions with filters
  const handleViewTransactions = (insight: Insight) => {
    const params = new URLSearchParams({ month });

    if (insight.category_id) {
      params.set("category_id", String(insight.category_id));
    }
    // Note: merchant_id filter would need backend support
    // For now, we only support category_id navigation

    navigate(`/transactions?${params.toString()}`);
  };

  const getInsightIcon = (severity: string) => {
    if (severity === "warning") {
      return <WarningIcon color="warning" sx={{ fontSize: 40 }} />;
    }
    return <LightbulbIcon color="info" sx={{ fontSize: 40 }} />;
  };

  const getInsightColor = (severity: string) => {
    return severity === "warning" ? "warning.light" : "info.light";
  };

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Insights
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Get insights about your spending patterns.
      </Typography>

      {/* Filters */}
      <Paper sx={{ p: 2, mb: 3 }}>
        <Stack direction="row" spacing={2} alignItems="center">
          <TextField
            label="Month"
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            size="small"
            InputLabelProps={{ shrink: true }}
            sx={{ minWidth: 150 }}
          />
          <Button
            variant="contained"
            onClick={fetchInsights}
            disabled={loading}
          >
            {loading ? <CircularProgress size={24} /> : "Refresh"}
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
      {!loading && hasFetched && insights.length === 0 && (
        <Paper sx={{ p: 4, textAlign: "center" }}>
          <LightbulbIcon sx={{ fontSize: 48, color: "text.secondary", mb: 2 }} />
          <Typography color="text.secondary">
            No insights available for this month. Keep tracking your spending!
          </Typography>
        </Paper>
      )}

      {/* Insights list */}
      {!loading && insights.length > 0 && (
        <Stack spacing={2}>
          {insights.map((insight, idx) => (
            <Card
              key={idx}
              sx={{
                borderLeft: 4,
                borderColor: getInsightColor(insight.severity),
              }}
            >
              <CardContent>
                <Stack direction="row" spacing={2} alignItems="flex-start">
                  {getInsightIcon(insight.severity)}
                  <Box flex={1}>
                    <Typography variant="h6" gutterBottom>
                      {insight.title}
                    </Typography>
                    <Typography color="text.secondary">
                      {insight.detail}
                    </Typography>
                    {insight.amount && (
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{ mt: 1 }}
                      >
                        Amount: ${parseFloat(insight.amount).toLocaleString(undefined, {
                          minimumFractionDigits: 2,
                        })}
                      </Typography>
                    )}
                  </Box>
                </Stack>
              </CardContent>
              {insight.category_id && (
                <CardActions>
                  <Button
                    size="small"
                    onClick={() => handleViewTransactions(insight)}
                  >
                    View Transactions
                  </Button>
                </CardActions>
              )}
            </Card>
          ))}
        </Stack>
      )}
    </Box>
  );
}
