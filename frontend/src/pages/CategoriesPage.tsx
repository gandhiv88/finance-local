import React, { useEffect, useState } from "react";
import {
  Typography,
  Button,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  TextField,
  Select,
  MenuItem,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Switch,
  FormControlLabel,
  IconButton,
  CircularProgress,
  Snackbar,
  Alert,
} from "@mui/material";
import EditIcon from "@mui/icons-material/Edit";
import DeleteIcon from "@mui/icons-material/Delete";
import { listCategories, seedCategories, createCategory, updateCategory, deleteCategory } from "../lib/api";
import type { Category } from "../lib/api";

export function CategoriesPage() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [createName, setCreateName] = useState("");
  const [createParent, setCreateParent] = useState<number | "" | null>("");
  const [editOpen, setEditOpen] = useState(false);
  const [editCategory, setEditCategory] = useState<Category | null>(null);
  const [editName, setEditName] = useState("");
  const [editParent, setEditParent] = useState<number | "" | null>("");
  const [editActive, setEditActive] = useState(true);

  // Map for parent name lookup
  const parentMap = React.useMemo(() => {
    const map: Record<number, string> = {};
    categories.forEach((cat) => {
      map[cat.id] = cat.name;
    });
    return map;
  }, [categories]);

  const loadCategories = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listCategories();
      setCategories(data);
    } catch (e: any) {
      setError(e.message || "Failed to load categories");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCategories();
  }, []);

  const handleSeed = async () => {
    setLoading(true);
    setError(null);
    try {
      await seedCategories();
      setSuccess("Seeded default categories");
      await loadCategories();
    } catch (e: any) {
      setError(e.message || "Failed to seed categories");
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!createName.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await createCategory({
        name: createName.trim(),
        parent_id: createParent === "" ? null : createParent,
      });
      setSuccess("Category created");
      setCreateName("");
      setCreateParent("");
      await loadCategories();
    } catch (e: any) {
      setError(e.message || "Failed to create category");
    } finally {
      setLoading(false);
    }
  };

  const openEdit = (cat: Category) => {
    setEditCategory(cat);
    setEditName(cat.name);
    setEditParent(cat.parent_id ?? "");
    setEditActive(cat.is_active);
    setEditOpen(true);
  };

  const handleEditSave = async () => {
    if (!editCategory) return;
    setLoading(true);
    setError(null);
    try {
      await updateCategory(editCategory.id, {
        name: editName.trim(),
        parent_id: editParent === "" ? null : editParent,
        is_active: editActive,
      });
      setSuccess("Category updated");
      setEditOpen(false);
      await loadCategories();
    } catch (e: any) {
      setError(e.message || "Failed to update category");
    } finally {
      setLoading(false);
    }
  };

  const handleDisable = async (cat: Category) => {
    setLoading(true);
    setError(null);
    try {
      await deleteCategory(cat.id);
      setSuccess("Category disabled");
      await loadCategories();
    } catch (e: any) {
      setError(e.message || "Failed to disable category");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <Typography variant="h4" gutterBottom>
        Categories
      </Typography>
      <Typography color="text.secondary" gutterBottom>
        Manage your spending categories.
      </Typography>
      <Button variant="contained" onClick={handleSeed} disabled={loading} sx={{ mb: 2 }}>
        Seed defaults
      </Button>
      <Paper sx={{ p: 2, mb: 2 }}>
        <Typography variant="h6" gutterBottom>
          Create Category
        </Typography>
        <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
          <TextField
            label="Name"
            value={createName}
            onChange={(e) => setCreateName(e.target.value)}
            size="small"
            sx={{ minWidth: 180 }}
          />
          <Select
            value={createParent ?? ""}
            onChange={(e) => setCreateParent(e.target.value === "" ? "" : Number(e.target.value))}
            displayEmpty
            size="small"
            sx={{ minWidth: 180 }}
          >
            <MenuItem value="">No parent</MenuItem>
            {categories
              .filter((cat) => cat.is_active)
              .map((cat) => (
                <MenuItem key={cat.id} value={cat.id}>
                  {cat.name}
                </MenuItem>
              ))}
          </Select>
          <Button variant="contained" onClick={handleCreate} disabled={loading || !createName.trim()}>
            Create
          </Button>
        </div>
      </Paper>
      <TableContainer component={Paper}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Active</TableCell>
              <TableCell>Parent</TableCell>
              <TableCell>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {categories.map((cat) => (
              <TableRow key={cat.id}>
                <TableCell>{cat.name}</TableCell>
                <TableCell>{cat.is_active ? "Yes" : "No"}</TableCell>
                <TableCell>{cat.parent_id ? parentMap[cat.parent_id] || "-" : "-"}</TableCell>
                <TableCell>
                  <IconButton size="small" onClick={() => openEdit(cat)} disabled={loading}>
                    <EditIcon fontSize="small" />
                  </IconButton>
                  <IconButton size="small" onClick={() => handleDisable(cat)} disabled={loading || !cat.is_active}>
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {loading && (
          <div style={{ textAlign: "center", padding: 16 }}>
            <CircularProgress size={24} />
          </div>
        )}
      </TableContainer>
      <Dialog open={editOpen} onClose={() => setEditOpen(false)}>
        <DialogTitle>Edit Category</DialogTitle>
        <DialogContent sx={{ minWidth: 320 }}>
          <TextField
            label="Name"
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            fullWidth
            sx={{ mb: 2 }}
          />
          <Select
            value={editParent ?? ""}
            onChange={(e) => setEditParent(e.target.value === "" ? "" : Number(e.target.value))}
            displayEmpty
            fullWidth
            sx={{ mb: 2 }}
          >
            <MenuItem value="">No parent</MenuItem>
            {categories
              .filter((cat) => cat.is_active && (!editCategory || cat.id !== editCategory.id))
              .map((cat) => (
                <MenuItem key={cat.id} value={cat.id}>
                  {cat.name}
                </MenuItem>
              ))}
          </Select>
          <FormControlLabel
            control={<Switch checked={editActive} onChange={(e) => setEditActive(e.target.checked)} />}
            label="Active"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditOpen(false)} disabled={loading}>
            Cancel
          </Button>
          <Button onClick={handleEditSave} variant="contained" disabled={loading || !editName.trim()}>
            Save
          </Button>
        </DialogActions>
      </Dialog>
      <Snackbar open={!!error} autoHideDuration={6000} onClose={() => setError(null)}>
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      </Snackbar>
      <Snackbar open={!!success} autoHideDuration={4000} onClose={() => setSuccess(null)}>
        <Alert severity="success" onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      </Snackbar>
    </div>
  );
}
