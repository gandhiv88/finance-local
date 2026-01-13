# Finance Local

A self-hosted personal finance manager for tracking accounts, transactions, budgets, and spending insights. Built with FastAPI (Python backend) and React (TypeScript frontend).

## Features
- Multi-account, multi-user, household-based finance tracking
- Import bank statements (CSV/Excel)
- Categorize transactions (with merchant/category learning)
- Set and track monthly budgets by category
- Monthly/annual reports and insights
- Soft-delete, edit, and bulk update transactions
- Admin/member roles
- Dockerized for easy deployment

## Tech Stack
- **Backend:** FastAPI, SQLAlchemy, Alembic, PostgreSQL
- **Frontend:** React, Vite, MUI, TypeScript
- **Deployment:** Docker, Nginx, Docker Compose

## Quick Start

### Prerequisites
- Docker & Docker Compose

### 1. Clone the repository
```sh
git clone https://github.com/gandhiv88/finance-local.git
cd finance-local
```

### 2. Configure environment
- Copy `.env.example` to `.env` and set secrets/DB info as needed.

### 3. Start the stack
```sh
docker-compose up --build
```
- Backend: http://localhost:8000
- Frontend: http://localhost:5173

### 4. Create an admin user
- Register via the frontend or use the backend `/auth/register` endpoint.

### 5. Import your first statement
- Go to **Upload** in the UI and follow instructions.

## Development
- Backend: `cd backend && uvicorn app.main:app --reload`
- Frontend: `cd frontend && npm install && npm run dev`

## Data & Privacy
- All your data stays local. The `data/` folder and PDF statements are excluded from git by `.gitignore`.

## License
MIT
