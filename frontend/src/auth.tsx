import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api, tokens } from "./api";
import type { Me } from "./types";

interface AuthContextValue {
  me: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (input: {
    tenant_name: string;
    email: string;
    password: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    if (!tokens.access() && !tokens.refresh()) {
      setLoading(false);
      return;
    }
    api
      .me()
      .then((user) => {
        if (active) setMe(user);
      })
      .catch(() => {
        tokens.clear();
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const onExpired = () => setMe(null);
    window.addEventListener("instarix:auth-expired", onExpired);
    return () => window.removeEventListener("instarix:auth-expired", onExpired);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    await api.login(email, password);
    setMe(await api.me());
  }, []);

  const register = useCallback(
    async (input: { tenant_name: string; email: string; password: string }) => {
      await api.register(input);
      setMe(await api.me());
    },
    [],
  );

  const logout = useCallback(async () => {
    await api.logout();
    setMe(null);
  }, []);

  return (
    <AuthContext.Provider value={{ me, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth precisa estar dentro de AuthProvider");
  return context;
}
