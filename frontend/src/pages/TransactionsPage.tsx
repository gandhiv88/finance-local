import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import {
    Typography,
    Box,
    FormControl,
    InputLabel,
    Select,
    MenuItem,
    FormControlLabel,
    Checkbox,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    TablePagination,
    Paper,
    CircularProgress,
    Alert,
    Button,
    Tooltip,
    Snackbar,
} from "@mui/material";
import { Save as SaveIcon } from "@mui/icons-material";
import {
    listAccounts,
    listCategories,
    listTransactions,
    patchTransaction,
    recategorizeMerchant,
    bulkUpdateTransactions,
} from "../lib/api";
import type { BankAccount, Category, Transaction } from "../lib/api";
import dayjs from "dayjs";
import { DatePicker } from "@mui/x-date-pickers/DatePicker";

function getCurrentMonth(): string {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export function TransactionsPage() {
    const [searchParams] = useSearchParams();

    // Filter state - initialize from URL params if present
    const [accounts, setAccounts] = useState<BankAccount[]>([]);
    const [categories, setCategories] = useState<Category[]>([]);
    const [selectedAccountId, setSelectedAccountId] = useState<number | "">(() => {
        const param = searchParams.get("account_id");
        return param ? Number(param) : "";
    });
    const [month, setMonth] = useState<string>(() => {
        return searchParams.get("month") || getCurrentMonth();
    });
    const [selectedCategoryId, setSelectedCategoryId] = useState<number | "">(() => {
        const param = searchParams.get("category_id");
        return param ? Number(param) : "";
    });
    const [uncategorizedOnly, setUncategorizedOnly] = useState(() => {
        return searchParams.get("uncategorized") === "true";
    });

    // Data state
    const [transactions, setTransactions] = useState<Transaction[]>([]);
    const [loading, setLoading] = useState(false);
    const [loadingInitial, setLoadingInitial] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Pagination state (page is 0-based for MUI)
    const [page, setPage] = useState(0);
    const [rowsPerPage, setRowsPerPage] = useState(50);
    const [total, setTotal] = useState(0);

    // Snackbar state
    const [snackbarOpen, setSnackbarOpen] = useState(false);
    const [snackbarMessage, setSnackbarMessage] = useState("");

    // Bulk selection state
    const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

    // Bulk action state
    const [bulkCategoryId, setBulkCategoryId] = useState<number | "">("");
    const [bulkMarkReviewed, setBulkMarkReviewed] = useState(false);
    const [bulkApplyToMerchant, setBulkApplyToMerchant] = useState(false);
    const [bulkLoading, setBulkLoading] = useState(false);

    // Load accounts and categories on mount
    useEffect(() => {
        async function loadInitialData() {
            try {
                const [accountsData, categoriesData] = await Promise.all([
                    listAccounts(),
                    listCategories(),
                ]);
                setAccounts(accountsData);
                setCategories(categoriesData);
                if (accountsData.length === 1) {
                    setSelectedAccountId(accountsData[0].id);
                }
            } catch (err) {
                setError(err instanceof Error ? err.message : "Failed to load data");
            } finally {
                setLoadingInitial(false);
            }
        }
        loadInitialData();
    }, []);

    // Load transactions when filters or pagination change
    const loadTransactions = useCallback(async () => {
        setLoading(true);
        setError(null);

        try {
            const data = await listTransactions({
                account_id: selectedAccountId || undefined,
                month: month || undefined,
                category_id: selectedCategoryId || undefined,
                uncategorized: uncategorizedOnly || undefined,
                page: page + 1, // API is 1-indexed, MUI is 0-indexed
                page_size: rowsPerPage,
            });
            setTransactions(data.items);
            setTotal(data.total);
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to load transactions");
        } finally {
            setLoading(false);
        }
    }, [selectedAccountId, month, selectedCategoryId, uncategorizedOnly, page, rowsPerPage]);

    // Reset page when filters change
    useEffect(() => {
        setPage(0);
        clearSelection();
    }, [selectedAccountId, month, selectedCategoryId, uncategorizedOnly]);

    // Clear selection when page or rowsPerPage changes
    useEffect(() => {
        clearSelection();
    }, [page, rowsPerPage]);

    // Load transactions when page/rowsPerPage change or after filter reset
    useEffect(() => {
        if (!loadingInitial) {
            loadTransactions();
        }
    }, [loadTransactions, loadingInitial]);

    // Handle category change
    const handleCategoryChange = async (
        transaction: Transaction,
        categoryId: number | null
    ) => {
        try {
            const updated = await patchTransaction(transaction.id, {
                category_id: categoryId,
                is_reviewed: true,
            });
            setTransactions((prev) =>
                prev.map((t) => (t.id === updated.id ? updated : t))
            );
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to update transaction");
        }
    };

    // Handle "Apply to merchant" - sets merchant default category and recategorizes
    const handleApplyToMerchant = async (transaction: Transaction) => {
        if (!transaction.category_id) return;

        try {
            // 1. Patch transaction with create_merchant_override
            const updated = await patchTransaction(transaction.id, {
                category_id: transaction.category_id,
                is_reviewed: true,
                create_merchant_override: true,
            });

            // Update the transaction in the list
            setTransactions((prev) =>
                prev.map((t) => (t.id === updated.id ? updated : t))
            );

            // 2. Get merchant_id from response and recategorize other transactions
            const merchantId = updated.merchant_id ?? updated.merchant_ref?.id;
            if (merchantId) {
                const result = await recategorizeMerchant(merchantId);

                // 3. Show snackbar with result
                setSnackbarMessage(`Applied to merchant. Updated ${result.updated} transactions.`);
                setSnackbarOpen(true);

                // 4. Reload transactions to reflect changes
                await loadTransactions();
            } else {
                setSnackbarMessage("Applied to merchant.");
                setSnackbarOpen(true);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to apply to merchant");
        }
    };

    // Handle reviewed toggle
    const handleReviewedChange = async (transaction: Transaction, isReviewed: boolean) => {
        try {
            const updated = await patchTransaction(transaction.id, {
                is_reviewed: isReviewed,
            });
            setTransactions((prev) =>
                prev.map((t) => (t.id === updated.id ? updated : t))
            );
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to update transaction");
        }
    };

    // Bulk selection helpers - never mutate, always clone
    const toggleSelect = (id: number) => {
        setSelectedIds((prev) => {
            const next = new Set(prev);
            if (next.has(id)) {
                next.delete(id);
            } else {
                next.add(id);
            }
            return next;
        });
    };

    const selectAll = (ids: number[]) => {
        setSelectedIds(new Set(ids));
    };

    const clearSelection = () => {
        setSelectedIds(new Set());
    };

    // Bulk action handler
    const handleBulkApply = async () => {
        if (selectedIds.size === 0) return;

        setBulkLoading(true);
        try {
            const result = await bulkUpdateTransactions({
                transaction_ids: Array.from(selectedIds),
                category_id: bulkCategoryId !== "" ? bulkCategoryId : undefined,
                is_reviewed: bulkMarkReviewed ? true : undefined,
                apply_to_merchant: bulkApplyToMerchant,
            });

            setSnackbarMessage(
                `Updated ${result.updated_transactions} transactions, ${result.updated_merchants} merchants. Skipped ${result.skipped}.`
            );
            setSnackbarOpen(true);

            // Clear selection and bulk action state
            clearSelection();
            setBulkCategoryId("");
            setBulkMarkReviewed(false);
            setBulkApplyToMerchant(false);

            // Reload transactions
            await loadTransactions();
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to bulk update");
        } finally {
            setBulkLoading(false);
        }
    };

    // Format amount with color
    const formatAmount = (amount: string) => {
        const num = parseFloat(amount);
        const formatted = new Intl.NumberFormat("en-US", {
            style: "currency",
            currency: "USD",
        }).format(Math.abs(num));
        return {
            text: num < 0 ? `-${formatted}` : formatted,
            color: num > 0 ? "success.main" : "error.main",
        };
    };

    if (loadingInitial) {
        return (
            <Box sx={{ display: "flex", justifyContent: "center", mt: 4 }}>
                <CircularProgress />
            </Box>
        );
    }

    return (
        <Box>
            <Typography variant="h4" gutterBottom>
                Transactions
            </Typography>

            {error && (
                <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
                    {error}
                </Alert>
            )}

            {/* Filters */}
            <Paper sx={{ p: 2, mb: 3 }}>
                <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", alignItems: "center" }}>
                    <FormControl sx={{ minWidth: 200 }}>
                        <InputLabel id="account-filter-label">Account</InputLabel>
                        <Select
                            labelId="account-filter-label"
                            value={selectedAccountId}
                            label="Account"
                            onChange={(e) => setSelectedAccountId(e.target.value as number)}
                        >
                            <MenuItem value="">All Accounts</MenuItem>
                            {accounts.map((account) => (
                                <MenuItem key={account.id} value={account.id}>
                                    {account.display_name}
                                </MenuItem>
                            ))}
                        </Select>
                    </FormControl>

                    <DatePicker
                        label="Month"
                        views={["year", "month"]}
                        value={month ? dayjs(`${month}-01`) : null}
                        onChange={(v) => setMonth(v ? v.format("YYYY-MM") : "")}
                    />

                    <FormControl sx={{ minWidth: 180 }}>
                        <InputLabel id="category-filter-label">Category</InputLabel>
                        <Select<number | "">
                            labelId="category-filter-label"
                            value={selectedCategoryId}
                            label="Category"
                            onChange={(e) => {
                                const val = e.target.value;
                                setSelectedCategoryId(val === "" ? "" : Number(val));
                            }}
                        >
                            <MenuItem value="">All Categories</MenuItem>
                            {categories.map((cat) => (
                                <MenuItem key={cat.id} value={cat.id}>
                                    {cat.name}
                                </MenuItem>
                            ))}
                        </Select>
                    </FormControl>

                    <FormControlLabel
                        control={
                            <Checkbox
                                checked={uncategorizedOnly}
                                onChange={(e) => setUncategorizedOnly(e.target.checked)}
                            />
                        }
                        label="Uncategorized only"
                    />

                    {loading && <CircularProgress size={24} />}
                </Box>
            </Paper>

            {/* Bulk Action Bar */}
            {selectedIds.size > 0 && (
                <Paper sx={{ p: 2, mb: 2, bgcolor: "action.selected" }}>
                    <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", alignItems: "center" }}>
                        <Typography variant="body2" sx={{ fontWeight: 500 }}>
                            {selectedIds.size} selected
                        </Typography>

                        <FormControl size="small" sx={{ minWidth: 150 }}>
                            <InputLabel id="bulk-category-label">Category</InputLabel>
                            <Select
                                labelId="bulk-category-label"
                                value={bulkCategoryId}
                                label="Category"
                                onChange={(e) => setBulkCategoryId(e.target.value as number | "")}
                            >
                                <MenuItem value="">
                                    <em>No change</em>
                                </MenuItem>
                                {categories.map((cat) => (
                                    <MenuItem key={cat.id} value={cat.id}>
                                        {cat.name}
                                    </MenuItem>
                                ))}
                            </Select>
                        </FormControl>

                        <FormControlLabel
                            control={
                                <Checkbox
                                    checked={bulkMarkReviewed}
                                    onChange={(e) => setBulkMarkReviewed(e.target.checked)}
                                    size="small"
                                />
                            }
                            label="Mark reviewed"
                        />

                        <FormControlLabel
                            control={
                                <Checkbox
                                    checked={bulkApplyToMerchant}
                                    onChange={(e) => setBulkApplyToMerchant(e.target.checked)}
                                    size="small"
                                    disabled={bulkCategoryId === ""}
                                />
                            }
                            label="Apply to merchant"
                        />

                        <Button
                            variant="contained"
                            onClick={handleBulkApply}
                            disabled={bulkLoading || (bulkCategoryId === "" && !bulkMarkReviewed)}
                        >
                            {bulkLoading ? <CircularProgress size={20} /> : "Apply"}
                        </Button>

                        <Button
                            variant="text"
                            onClick={clearSelection}
                            disabled={bulkLoading}
                        >
                            Clear selection
                        </Button>
                    </Box>
                </Paper>
            )}

            {/* Transactions Table */}
            <TableContainer component={Paper}>
                <Table size="small">
                    <TableHead>
                        <TableRow>
                            <TableCell padding="checkbox">
                                <Checkbox
                                    indeterminate={
                                        selectedIds.size > 0 &&
                                        selectedIds.size < transactions.length
                                    }
                                    checked={
                                        transactions.length > 0 &&
                                        selectedIds.size === transactions.length
                                    }
                                    onChange={(e) =>
                                        e.target.checked
                                            ? selectAll(transactions.map((tx) => tx.id))
                                            : clearSelection()
                                    }
                                    disabled={transactions.length === 0}
                                />
                            </TableCell>
                            <TableCell>Date</TableCell>
                            <TableCell>Description</TableCell>
                            <TableCell align="right">Amount</TableCell>
                            <TableCell>Category</TableCell>
                            <TableCell align="center">Reviewed</TableCell>
                            <TableCell>Actions</TableCell>
                        </TableRow>
                    </TableHead>
                    <TableBody>
                        {transactions.length === 0 ? (
                            <TableRow>
                                <TableCell colSpan={7} align="center">
                                    {selectedAccountId
                                        ? "No transactions found"
                                        : "Select an account to view transactions"}
                                </TableCell>
                            </TableRow>
                        ) : (
                            transactions.map((tx) => {
                                const amount = formatAmount(tx.amount);
                                const isSelected = selectedIds.has(tx.id);
                                return (
                                    <TableRow
                                        key={tx.id}
                                        hover
                                        selected={isSelected}
                                    >
                                        <TableCell padding="checkbox">
                                            <Checkbox
                                                checked={isSelected}
                                                onChange={() => toggleSelect(tx.id)}
                                            />
                                        </TableCell>
                                        <TableCell sx={{ whiteSpace: "nowrap" }}>
                                            {tx.posted_date}
                                        </TableCell>
                                        <TableCell>
                                            <Tooltip title={tx.description} placement="top-start">
                                                <Box
                                                    sx={{
                                                        maxWidth: 300,
                                                        overflow: "hidden",
                                                        textOverflow: "ellipsis",
                                                        whiteSpace: "nowrap",
                                                    }}
                                                >
                                                    {tx.description}
                                                </Box>
                                            </Tooltip>
                                            {tx.merchant_key && (
                                                <Typography variant="caption" color="text.secondary" display="block">
                                                    {tx.merchant_key}
                                                </Typography>
                                            )}
                                        </TableCell>
                                        <TableCell align="right" sx={{ color: amount.color, fontWeight: 500 }}>
                                            {amount.text}
                                        </TableCell>
                                        <TableCell>
                                            <FormControl size="small" sx={{ minWidth: 150 }}>
                                                <Select<number | "">
                                                    value={tx.category_id ?? ""}
                                                    displayEmpty
                                                    onChange={(e) => {
                                                        const value = e.target.value;
                                                        handleCategoryChange(
                                                            tx,
                                                            value === "" ? null : (value as number)
                                                        );
                                                    }}
                                                >
                                                    <MenuItem value="">
                                                        <em>Uncategorized</em>
                                                    </MenuItem>
                                                    {categories.map((cat) => (
                                                        <MenuItem key={cat.id} value={cat.id}>
                                                            {cat.name}
                                                        </MenuItem>
                                                    ))}
                                                </Select>
                                            </FormControl>
                                        </TableCell>
                                        <TableCell align="center">
                                            <Checkbox
                                                checked={tx.is_reviewed}
                                                onChange={(e) => handleReviewedChange(tx, e.target.checked)}
                                                size="small"
                                            />
                                        </TableCell>
                                        <TableCell>
                                            {tx.merchant_key && (
                                                <Tooltip title="Apply this category to all transactions from this merchant">
                                                    <span>
                                                        <Button
                                                            size="small"
                                                            startIcon={<SaveIcon />}
                                                            onClick={() => handleApplyToMerchant(tx)}
                                                            disabled={!tx.category_id}
                                                        >
                                                            Apply to merchant
                                                        </Button>
                                                    </span>
                                                </Tooltip>
                                            )}
                                        </TableCell>
                                    </TableRow>
                                );
                            })
                        )}
                    </TableBody>
                </Table>
            </TableContainer>

            <TablePagination
                component="div"
                count={total}
                page={page}
                onPageChange={(_e, newPage) => setPage(newPage)}
                rowsPerPage={rowsPerPage}
                onRowsPerPageChange={(e) => {
                    setRowsPerPage(parseInt(e.target.value, 10));
                    setPage(0);
                }}
                rowsPerPageOptions={[10, 25, 50, 100]}
            />

            <Snackbar
                open={snackbarOpen}
                autoHideDuration={4000}
                onClose={() => setSnackbarOpen(false)}
                message={snackbarMessage}
            />
        </Box>
    );
}
