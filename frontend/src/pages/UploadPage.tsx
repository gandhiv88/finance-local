import { useState, useEffect } from "react";
import {
  Typography,
  Box,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
  Alert,
  Paper,
  CircularProgress,
} from "@mui/material";
import { CloudUpload as UploadIcon } from "@mui/icons-material";
import { listAccounts, uploadImport } from "../lib/api";
import type { BankAccount, ImportResult } from "../lib/api";

export function UploadPage() {
  const [accounts, setAccounts] = useState<BankAccount[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<number | "">("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingAccounts, setLoadingAccounts] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);

  useEffect(() => {
    async function loadAccounts() {
      try {
        const data = await listAccounts();
        setAccounts(data);
        if (data.length === 1) {
          setSelectedAccountId(data[0].id);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load accounts");
      } finally {
        setLoadingAccounts(false);
      }
    }
    loadAccounts();
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0] || null;
    setFile(selectedFile);
    setResult(null);
    setError(null);
  };

  const handleUpload = async () => {
    if (!selectedAccountId || !file) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const importResult = await uploadImport(selectedAccountId, file);
      setResult(importResult);
      setFile(null);
      // Reset file input
      const fileInput = document.getElementById("file-input") as HTMLInputElement;
      if (fileInput) fileInput.value = "";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  };

  if (loadingAccounts) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", mt: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Upload Statement
      </Typography>
      <Typography color="text.secondary" sx={{ mb: 3 }}>
        Upload bank statements (PDF) to import transactions.
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {result && (
        <Alert severity="success" sx={{ mb: 2 }}>
          <Typography variant="subtitle2">Import #{result.id} completed</Typography>
          <Typography variant="body2">
            Imported: {result.imported_count} | Skipped: {result.skipped_count} | Warnings: {result.warning_count}
          </Typography>
        </Alert>
      )}

      <Paper sx={{ p: 3, maxWidth: 500 }}>
        <FormControl fullWidth sx={{ mb: 2 }}>
          <InputLabel id="account-select-label">Bank Account</InputLabel>
          <Select
            labelId="account-select-label"
            value={selectedAccountId}
            label="Bank Account"
            onChange={(e) => setSelectedAccountId(e.target.value as number)}
          >
            {accounts.map((account) => (
              <MenuItem key={account.id} value={account.id}>
                {account.display_name} ({account.bank_code || "Unknown"})
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        <Box sx={{ mb: 2 }}>
          <input
            id="file-input"
            type="file"
            accept=".pdf"
            onChange={handleFileChange}
            style={{ display: "none" }}
          />
          <label htmlFor="file-input">
            <Button variant="outlined" component="span" fullWidth>
              {file ? file.name : "Select PDF File"}
            </Button>
          </label>
        </Box>

        <Button
          variant="contained"
          fullWidth
          startIcon={loading ? <CircularProgress size={20} color="inherit" /> : <UploadIcon />}
          onClick={handleUpload}
          disabled={!selectedAccountId || !file || loading}
        >
          {loading ? "Uploading..." : "Upload"}
        </Button>
      </Paper>
    </Box>
  );
}
