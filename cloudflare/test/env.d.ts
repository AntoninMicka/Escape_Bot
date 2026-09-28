declare namespace Cloudflare {
  interface Env {
    APP_ENV: string;
    ASSETS: Fetcher;
    GAME_SESSIONS: DurableObjectNamespace<
      import("../src/index").GameSession
    >;
  }
}
