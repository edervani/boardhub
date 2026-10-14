import { useEffect, useState, type FormEvent } from "react";
import { api, errorMessage } from "../../services/api";
import type { Me, Preferences, Profile } from "../../services/types";
import { StatsPanel } from "./StatsPanel";

export function ProfilePage({ me }: { me: Me }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const minor = me.age_band !== "18_plus";

  useEffect(() => {
    Promise.all([api<Profile>("GET", "/me/profile"), api<Preferences>("GET", "/me/preferences")])
      .then(([p, q]) => { setProfile(p); setPrefs(q); })
      .catch((e: unknown) => setError(errorMessage(e)));
  }, []);

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!profile || !prefs) return;
    setMsg(""); setError("");
    try {
      const patch: Record<string, unknown> = { bio: profile.bio ?? "", is_public: profile.is_public };
      // Menores só entram no ranking por decisão do responsável (RF-034): não enviam o campo.
      if (!minor) patch.show_in_ranking = profile.is_public && profile.show_in_ranking;
      const saved = await api<Profile>("PATCH", "/me/profile", patch);
      const p = await api<Preferences>("PUT", "/me/preferences", prefs);
      setProfile(saved); setPrefs(p); setMsg("Alterações salvas.");
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  if (!profile || !prefs) return error ? <p role="alert">{error}</p> : <p role="status">Carregando…</p>;
  return (
    <>
    <form onSubmit={save} aria-labelledby="profile-title">
      <h2 id="profile-title">Seu perfil</h2>
      <p>Nome de exibição: <strong>{profile.display_name}</strong></p>
      <label htmlFor="bio">Sobre você (até 160 caracteres)</label>
      <textarea id="bio" maxLength={160} value={profile.bio ?? ""}
        onChange={(e) => setProfile({ ...profile, bio: e.target.value })} />
      <label>
        <input type="checkbox" checked={profile.is_public} disabled={minor && !profile.is_public}
          onChange={(e) => setProfile({
            ...profile, is_public: e.target.checked,
            show_in_ranking: e.target.checked && profile.show_in_ranking,
          })} />{" "}
        Perfil público
      </label>
      {minor && <p>Perfis de menores só podem ser tornados públicos pelo responsável.</p>}
      <label>
        <input type="checkbox" checked={profile.is_public && profile.show_in_ranking}
          disabled={!profile.is_public || (minor && !profile.show_in_ranking)}
          aria-describedby="ranking-hint"
          onChange={(e) => setProfile({ ...profile, show_in_ranking: e.target.checked })} />{" "}
        Aparecer no ranking público
      </label>
      <p id="ranking-hint">
        {minor
          ? "Menores só aparecem no ranking por decisão do responsável; aqui você pode apenas sair dele."
          : "Só seu nome de exibição e seu rating aparecem, e só com perfil público e pelo menos 10 partidas ranqueadas."}
      </p>

      <h3>Preferências</h3>
      <label htmlFor="theme">Tema</label>
      <select id="theme" value={prefs.theme}
        onChange={(e) => setPrefs({ ...prefs, theme: e.target.value as Preferences["theme"] })}>
        <option value="system">Seguir o sistema</option>
        <option value="light">Claro</option>
        <option value="dark">Escuro</option>
      </select>
      <label htmlFor="motion">Animações</label>
      <select id="motion" value={prefs.motion}
        onChange={(e) => setPrefs({ ...prefs, motion: e.target.value as Preferences["motion"] })}>
        <option value="system">Seguir o sistema</option>
        <option value="full">Completas</option>
        <option value="reduced">Reduzidas</option>
        <option value="none">Nenhuma</option>
      </select>
      <label>
        <input type="checkbox" checked={prefs.sound}
          onChange={(e) => setPrefs({ ...prefs, sound: e.target.checked })} /> Som
      </label>
      <label>
        <input type="checkbox" checked={prefs.move_confirmation}
          onChange={(e) => setPrefs({ ...prefs, move_confirmation: e.target.checked })} />{" "}
        Confirmar jogada antes de enviar
      </label>
      {error && <p role="alert">{error}</p>}
      {msg && <p role="status">{msg}</p>}
      <p><button type="submit">Salvar</button></p>
    </form>
    <StatsPanel />
    </>
  );
}
