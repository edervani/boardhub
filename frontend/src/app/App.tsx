import { useEffect, useState } from "react";
import { LoginForm, RegisterForm } from "../features/auth/AuthForms";
import { GameList } from "../features/catalog/GameList";
import { LobbyPage } from "../features/lobby/LobbyPage";
import { GamePage } from "../features/tictactoe/GamePage";
import { History } from "../features/tictactoe/History";
import { MatchBoard } from "../features/tictactoe/MatchBoard";
import { ProfilePage } from "../features/profile/ProfilePage";
import { ApiError, api } from "../services/api";
import type { Me } from "../services/types";

type View = "jogos" | "jogar" | "online" | "historico" | "perfil" | "entrar" | "cadastro";

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
          <button className="secondary" onClick={() => setView("jogar")}>Jogar</button>
          {me ? (
            <>
              <button className="secondary" onClick={() => setView("online")}>Online</button>
              <button className="secondary" onClick={() => setView("historico")}>Histórico</button>
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
            {view === "jogar" && <GamePage me={me} />}
            {view === "online" && me && (
              <LobbyPage me={me} renderBoard={(p) => <MatchBoard {...p} />} />
            )}
            {view === "historico" && me && <History />}
            {view === "perfil" && me && <ProfilePage me={me} />}
            {view === "entrar" && <LoginForm onLogin={(m) => { setMe(m); setView("jogos"); }} />}
            {view === "cadastro" && <RegisterForm />}
          </>
        )}
      </main>
    </>
  );
}
