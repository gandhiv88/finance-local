import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  IconButton,
  InputAdornment,
  Paper,
  Snackbar,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { Save as SaveIcon } from "@mui/icons-material";
import dayjs from "dayjs";
import {
  listBudgets,
  listCategories,
  upsertBudget,
} from "../lib/api";
import type { Budget, Category } from "../lib/api";

function getCurrentMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function BudgetsPage() {
  const [month, setMonth] = useState(getCurrentMonth());
  const [categories, setCategories] = useState<Category[]>([]);
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editLimits, setEditLimits] = useState<Record<number, string>>({});
  const [savingId, setSavingId] = useState<number | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      setError(null);
      try {
        const [cats, buds] = await Promise.all([
          listCategories(),
          listBudgets(month),
        ]);
        setCategories(cats);
        setBudgets(buds);
        setEditLimits({});
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load budgets");
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, [month]);

  // Map category_id to budget limit
  const budgetMap = Object.fromEntries(
    budgets.map((b) => [b.category_id, b.limit_amount])
  );

  const handleLimitChange = (catId: number, value: string) => {
    setEditLimits((prev) => ({ ...prev, [catId]: value }));
  };

  const handleSave = async (catId: number) => {
    setSavingId(catId);
    try {
      const limit = editLimits[catId] ?? budgetMap[catId] ?? "";
      if (!limit || isNaN(Number(limit))) return;
      await upsertBudget({ month, category_id: catId, limit_amount: limit });
      // Reload budgets
      const buds = await listBudgets(month);
      setBudgets(buds);
      setEditLimits((prev) => ({ ...prev, [catId]: "" }));
      setSuccess("Budget saved");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save budget");
    } finally {
      setSavingId(null);
    }
  };

  // Optional: Copy from previous month
  const handleCopyPrevious = async () => {
    const prev = dayjs(month + "-01").subtract(1, "month").format("YYYY-MM");
    try {
      const prevBudgets = await listBudgets(prev);
      const newLimits: Record<number, string> = {};
      prevBudgets.forEach((b) => {
        newLimits[b.category_id] = b.limit_amount;
      });
      setEditLimits(newLimits);
      setSuccess(`Copied budgets from ${prev}`);
    } catch (err) {
      setError("Failed to copy from previous month");
    }
  };

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Budgets
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Set and track your monthly budgets.
      </Typography>
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
          <Button onClick={handleCopyPrevious} variant="outlined" size="small">
            Copy from previous month
          </Button>
        </Stack>
      </Paper>
      {error && (
        <Paper sx={{ p: 2, mb: 2 }}>
          <Typography color="error">{error}</Typography>
        </Paper>
      )}
      {loading ? (
        <Box display="flex" justifyContent="center" py={4}>
          <CircularProgress />
        </Box>
      ) : (
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Category</TableCell>
                <TableCell align="right">Budget Limit ($)</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {categories.map((cat) => (
                <TableRow key={cat.id}>
                  <TableCell>{cat.name}</TableCell>
                  <TableCell align="right">
                    <TextField
                      value={editLimits[cat.id] ?? budgetMap[cat.id] ?? ""}
                      onChange={(e) => handleLimitChange(cat.id, e.target.value)}
                      size="small"
                      type="number"
                      inputProps={{ min: 0, step: "0.01" }}
                      sx={{ maxWidth: 120 }}
                      InputProps={{
                        endAdornment: (
                          <InputAdornment position="end">USD</InputAdornment>
                        ),
                      }}
                    />
                  </TableCell>
                  <TableCell align="right">
                    <IconButton
                      color="primary"
                      onClick={() => handleSave(cat.id)}
                      disabled={savingId === cat.id}
                      size="small"
                    >
                      <SaveIcon />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
      <Snackbar open={!!success} autoHideDuration={4000} onClose={() => setSuccess(null)}>
        <Alert severity="success" onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      </Snackbar>
    </Box>
  );
}
