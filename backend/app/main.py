from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import (
    auth,
    bootstrap,
    admin_users,
    accounts,
    budgets,
    categories,
    me,
    imports,
    transactions,
    maintenance,
    rules,
    learning,
    reports,
    insights,
)
from app.ml.routes import router as ml_router

app = FastAPI(title="Local Finance (Offline)")

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(bootstrap.router, prefix="", tags=["bootstrap"])
app.include_router(auth.router, prefix="", tags=["auth"])
app.include_router(admin_users.router, prefix="", tags=["admin"])
app.include_router(accounts.router, prefix="", tags=["accounts"])
app.include_router(budgets.router, prefix="", tags=["budgets"])
app.include_router(categories.router, prefix="", tags=["categories"])
app.include_router(me.router, prefix="", tags=["me"])
app.include_router(imports.router, prefix="", tags=["imports"])
app.include_router(transactions.router, prefix="", tags=["transactions"])
app.include_router(maintenance.router, prefix="", tags=["maintenance"])
app.include_router(rules.router, prefix="", tags=["rules"])
app.include_router(learning.router, prefix="", tags=["learning"])
app.include_router(reports.router, prefix="", tags=["reports"])
app.include_router(insights.router, prefix="", tags=["insights"])
app.include_router(ml_router)
