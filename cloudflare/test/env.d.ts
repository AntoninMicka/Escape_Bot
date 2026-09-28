declare namespace Cloudflare {
  interface Env {
    APP_ENV: string;
    ADMIN_TOKEN?: string;
    ASSETS: Fetcher;
    GAME_SESSIONS: DurableObjectNamespace<
      import("../src/index").GameSession
    >;
  }
}
