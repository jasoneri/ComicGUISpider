export const ORIGINS = {
  MAIN: process.env.DOCS_MAIN_ORIGIN ?? "https://cgs.101114105.xyz",
  IMG: process.env.DOCS_IMG_ORIGIN ?? "https://img-cgs.101114105.xyz",
  RV: process.env.DOCS_RV_ORIGIN ?? "https://rv.101114105.xyz",
  GHSTAT: process.env.DOCS_GHSTAT_ORIGIN ?? "https://ghstat.101114105.xyz",
} as const;

const join = (origin: string, path = "") =>
  origin + (path.startsWith("/") ? path : `/${path}`);

export const URLS = {
  main: (path = "/") => join(ORIGINS.MAIN, path),
  img: (path = "/") => join(ORIGINS.IMG, path),
  rv: (path = "/") => join(ORIGINS.RV, path),
  ghstat: (path = "/") => join(ORIGINS.GHSTAT, path),
  assets: {
    logo: join(ORIGINS.IMG, "/file/1765128492268_cgs_eat.png"),
    rvLogo: join(ORIGINS.IMG, "/file/1766904566021_rv.png"),
  },
  pages: {
    rvFeed: join(ORIGINS.RV, "/contribute/feed"),
    quickStart: join(ORIGINS.MAIN, "/deploy/quick-start"),
    faq: join(ORIGINS.MAIN, "/faq"),
    featScript: join(ORIGINS.MAIN, "/feat/script"),
  },
} as const;

export const PLACEHOLDERS = {
  URL_MAIN: "{{URL_MAIN}}",
  URL_IMG: "{{URL_IMG}}",
  URL_RV: "{{URL_RV}}",
  URL_GHSTAT: "{{URL_GHSTAT}}",
} as const;

export const PLACEHOLDER_MAP = {
  [PLACEHOLDERS.URL_MAIN]: ORIGINS.MAIN,
  [PLACEHOLDERS.URL_IMG]: ORIGINS.IMG,
  [PLACEHOLDERS.URL_RV]: ORIGINS.RV,
  [PLACEHOLDERS.URL_GHSTAT]: ORIGINS.GHSTAT,
} as const;
