from fastapi import FastAPI
from app.api import (
    auth,
    bootstrap,
    admin_users,
    accounts,
    categories,
    me,
    imports,
    transactions,
    maintenance,
    rules,
)

app = FastAPI(title="Local Finance (Offline)")


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(bootstrap.router, prefix="", tags=["bootstrap"])
app.include_router(auth.router, prefix="", tags=["auth"])
app.include_router(admin_users.router, prefix="", tags=["admin"])
app.include_router(accounts.router, prefix="", tags=["accounts"])
app.include_router(categories.router, prefix="", tags=["categories"])
app.include_router(me.router, prefix="", tags=["me"])
app.include_router(imports.router, prefix="", tags=["imports"])
app.include_router(transactions.router, prefix="", tags=["transactions"])
app.include_router(maintenance.router, prefix="", tags=["maintenance"])
app.include_router(rules.router, prefix="", tags=["rules"])
