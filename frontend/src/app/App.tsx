import { useEffect, useState } from "react";
import { LoginForm, RegisterForm } from "../features/auth/AuthForms";
import { GameList } from "../features/catalog/GameList";
import { LobbyPage } from "../features/lobby/LobbyPage";
import { GamePage } from "../features/tictactoe/GamePage";
import { History } from "../features/tictactoe/History";
import { AcademyPage } from "../features/academy/AcademyPage";
import { ReviewPage } from "../features/academy/ReviewPage";
import { MatchBoard } from "../features/tictactoe/MatchBoard";
import { GuardianPage } from "../features/guardian/GuardianPage";
import { AchievementsPage } from "../features/engagement/AchievementsPage";
import { DailyPage } from "../features/engagement/DailyPage";
import { NotificationBell } from "../features/engagement/NotificationBell";
import { PrivacyPage } from "../features/profile/PrivacyPage";
import { ProfilePage } from "../features/profile/ProfilePage";
import { RankingPage } from "../features/ranking/RankingPage";
import { ApiError, api, errorMessage } from "../services/api";
import type { Me } from "../services/types";

type View = "jogos" | "jogar" | "online" | "historico" | "ranking" | "academy" | "desafio" | "conquistas" | "revisao" | "perfil" | "responsavel" | "privacidade" | "entrar" | "cadastro";

export function App() {
  const [me, setMe] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);
  const [view, setView] = useState<View>("jogos");
  const [reviewId, setReviewId] = useState("");
  const [notice, setNotice] = useState("");
  // Conta em período de arrependimento (RF-030): o servidor só aceita /me e o cancelamento.
  const pending = Boolean(me?.deletion_scheduled_for);
  // Painel do responsável (RF-034): contas 18+ com e-mail confirmado.
  const guardian = Boolean(me && me.age_band === "18_plus" && me.email_verified);

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

  function deletionScheduled(scheduledFor: string) {
    setMe(null); setView("entrar");
    setNotice(`Exclusão agendada para ${new Date(scheduledFor).toLocaleDateString("pt-BR")}. ` +
      "Você saiu de todos os dispositivos. Para desistir, entre de novo até essa data e cancele.");
  }

  async function deletionCancelled() {
    try {
      setMe(await api<Me>("GET", "/me"));
      setNotice("Exclusão cancelada. Sua conta voltou ao normal.");
    } catch (err) {
      setNotice(errorMessage(err));
    }
  }

  return (
    <>
      <header>
        <nav aria-label="Principal">
          <strong>BoardHub</strong>
          {!pending && <button className="secondary" onClick={() => setView("jogos")}>Jogos</button>}
          {!pending && <button className="secondary" onClick={() => setView("jogar")}>Jogar</button>}
          {!pending && <button className="secondary" onClick={() => setView("ranking")}>Ranking</button>}
          {me && pending ? (
            <>
              <button className="secondary" onClick={() => setView("privacidade")}>Privacidade</button>
              <button className="secondary" onClick={() => void logout()}>Sair</button>
            </>
          ) : me ? (
            <>
              <button className="secondary" onClick={() => setView("online")}>Online</button>
              <button className="secondary" onClick={() => setView("historico")}>Histórico</button>
              <button className="secondary" onClick={() => setView("academy")}>Academy</button>
              <button className="secondary" onClick={() => setView("desafio")}>Desafio</button>
              <button className="secondary" onClick={() => setView("conquistas")}>Conquistas</button>
              <button className="secondary" onClick={() => setView("perfil")}>Perfil</button>
              {guardian && <button className="secondary" onClick={() => setView("responsavel")}>Responsável</button>}
              <button className="secondary" onClick={() => setView("privacidade")}>Privacidade</button>
              <NotificationBell />
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
        {notice && <p role="status">{notice}</p>}
        {!ready ? <p role="status">Carregando…</p> : me && pending ? (
          <PrivacyPage me={me} onDeletionScheduled={deletionScheduled}
            onDeletionCancelled={() => void deletionCancelled()} />
        ) : (
          <>
            {view === "jogos" && <GameList />}
            {view === "jogar" && <GamePage me={me} />}
            {view === "online" && me && (
              <LobbyPage me={me} renderBoard={(p) => <MatchBoard {...p} />} />
            )}
                        {view === "historico" && me && <History onReview={(id) => { setReviewId(id); setView("revisao"); }} />}
            {view === "ranking" && <RankingPage me={me} />}
            {view === "academy" && me && <AcademyPage />}
            {view === "desafio" && me && <DailyPage />}
            {view === "conquistas" && me && <AchievementsPage />}
            {view === "revisao" && me && <ReviewPage matchId={reviewId} onBack={() => setView("historico")} />}
            {view === "perfil" && me && <ProfilePage me={me} />}
            {view === "responsavel" && me && guardian && <GuardianPage />}
            {view === "privacidade" && me && (
              <PrivacyPage me={me} onDeletionScheduled={deletionScheduled}
                onDeletionCancelled={() => void deletionCancelled()} />
            )}
            {view === "entrar" && <LoginForm onLogin={(m) => { setMe(m); setNotice(""); setView("jogos"); }} />}
            {view === "cadastro" && <RegisterForm />}
          </>
        )}
      </main>
    </>
  );
}
