import { useEffect, useState } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { getToken, clearToken, me } from "../lib/api";

interface AuthGuardProps {
  children: React.ReactNode;
}

export function AuthGuard({ children }: AuthGuardProps) {
  const [isChecking, setIsChecking] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const location = useLocation();

  useEffect(() => {
    async function validateToken() {
      const token = getToken();

      if (!token) {
        setIsAuthenticated(false);
        setIsChecking(false);
        return;
      }

      try {
        await me();
        setIsAuthenticated(true);
      } catch {
        // Token is invalid, clear it
        clearToken();
        setIsAuthenticated(false);
      } finally {
        setIsChecking(false);
      }
    }

    validateToken();
  }, []);

  if (isChecking) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh" }}>
        Loading...
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
