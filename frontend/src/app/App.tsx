import { useEffect, useState } from "react";
import { LoginForm, RegisterForm } from "../features/auth/AuthForms";
import { GameList } from "../features/catalog/GameList";
import { LobbyPage } from "../features/lobby/LobbyPage";
import { GamePage } from "../features/tictactoe/GamePage";
import { History } from "../features/tictactoe/History";
import { AcademyPage } from "../features/academy/AcademyPage";
import { ReviewPage } from "../features/academy/ReviewPage";
import { MatchBoard } from "../features/tictactoe/MatchBoard";
import { ProfilePage } from "../features/profile/ProfilePage";
import { RankingPage } from "../features/ranking/RankingPage";
import { ApiError, api } from "../services/api";
import type { Me } from "../services/types";

type View = "jogos" | "jogar" | "online" | "historico" | "ranking" | "academy" | "revisao" | "perfil" | "entrar" | "cadastro";

export function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);
  const [view, setView] = useState<View>("jogos");
  const [reviewId, setReviewId] = useState("");

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
          <button className="secondary" onClick={() => setView("ranking")}>Ranking</button>
          {me ? (
            <>
              <button className="secondary" onClick={() => setView("online")}>Online</button>
              <button className="secondary" onClick={() => setView("historico")}>Histórico</button>
              <button className="secondary" onClick={() => setView("academy")}>Academy</button>
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
                        {view === "historico" && me && <History onReview={(id) => { setReviewId(id); setView("revisao"); }} />}
            {view === "ranking" && <RankingPage me={me} />}
            {view === "academy" && me && <AcademyPage />}
            {view === "revisao" && me && <ReviewPage matchId={reviewId} onBack={() => setView("historico")} />}
            {view === "perfil" && me && <ProfilePage me={me} />}
            {view === "entrar" && <LoginForm onLogin={(m) => { setMe(m); setView("jogos"); }} />}
            {view === "cadastro" && <RegisterForm />}
          </>
        )}
      </main>
    </>
  );
}
