/** Two-language UI. English by default; the choice is kept in localStorage and applied on reload. */
export type Lang = "en" | "pl";

function readLang(): Lang {
  try {
    return localStorage.getItem("lang") === "pl" ? "pl" : "en";
  } catch {
    return "en";
  }
}

export const lang: Lang = readLang();
export const locale = lang === "pl" ? "pl-PL" : "en-US";
document.documentElement.lang = lang;

/** Inline translation: t("Przychód", "Revenue"). */
export const t = (pl: string, en: string) => (lang === "pl" ? pl : en);

// ponytail: reload instead of a React context, fine while every string is read at render/module load.
export function setLang(next: Lang) {
  try {
    localStorage.setItem("lang", next);
  } catch {
    // storage blocked: the switch just won't stick
  }
  window.location.reload();
}
