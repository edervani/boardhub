import { useEffect, useState } from "react";
import { LoginForm, RegisterForm } from "../features/auth/AuthForms";
import { GameList } from "../features/catalog/GameList";
import { ProfilePage } from "../features/profile/ProfilePage";
import { ApiError, api } from "../services/api";
import type { Me } from "../services/types";

type View = "jogos" | "perfil" | "entrar" | "cadastro";

export function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);
  const [view, setView] = useState<View>("jogos");

  useEffect(() => {
    api<Me>("GET", "/me")
      .then(setMe)
      .catch((e: unknown) => { if (!(e instanceof ApiError && e.status === 401)) console.error(e); })
      .finally(() => setReady(true));
  }, []);

  async function logout() {
    await api<void>("POST", "/auth/logout");
    setMe(null); setView("jogos");
  }

  return (
    <>
      <header>
        <nav aria-label="Principal">
          <strong>BoardHub</strong>
          <button className="secondary" onClick={() => setView("jogos")}>Jogos</button>
          {me ? (
            <>
              <button className="secondary" onClick={() => setView("perfil")}>Perfil</button>
              <button className="secondary" onClick={() => void logout()}>Sair</button>
            </>
          ) : (
            <>
              <button className="secondary" onClick={() => setView("entrar")}>Entrar</button>
              <button className="secondary" onClick={() => setView("cadastro")}>Criar conta</button>
            </>
          )}
        </nav>
      </header>
      <main>
        <h1>BoardHub</h1>
        {!ready ? <p role="status">Carregando…</p> : (
          <>
            {view === "jogos" && <GameList />}
            {view === "perfil" && me && <ProfilePage me={me} />}
            {view === "entrar" && <LoginForm onLogin={(m) => { setMe(m); setView("jogos"); }} />}
            {view === "cadastro" && <RegisterForm />}
          </>
        )}
      </main>
    </>
  );
}
