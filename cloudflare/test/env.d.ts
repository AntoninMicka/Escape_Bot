declare namespace Cloudflare {
  interface Env {
    APP_ENV: string;
    GAME_SESSIONS: DurableObjectNamespace<
      import("../src/index").GameSession
    >;
  }
}
